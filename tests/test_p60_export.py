"""P60 – Export-Oberfläche für das Steuerpaket.

Prüft, dass die neue Seite ausgeliefert wird, dass die von export.js
verwendeten Endpunkte tatsächlich die dort ausgelesenen Felder liefern
(profil, vorschau, paket, buchungsliste) und dass die neu angelegten bzw.
geänderten JS-Dateien syntaktisch fehlerfrei sind (node --check).
"""
import asyncio
import io
import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from urllib.parse import urlsplit

from app import db, migrate
from app.main import app

ROOT = pathlib.Path(__file__).resolve().parents[1]


class ExportSeiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.tmp._finalizer.detach()
        self.auth_env = patch.dict(os.environ, {
            "FINANZ_TEST_AUTH_BYPASS": "1",
            "FINANZ_DB": str(pathlib.Path(tempfile.gettempdir()) / "finanz-p60-testdummy.db"),
        })
        self.auth_env.start()
        self.addCleanup(self.auth_env.stop)
        con = sqlite3.connect(":memory:", check_same_thread=False)
        con.row_factory = sqlite3.Row
        con.executescript(db.SCHEMA.read_text(encoding="utf-8"))
        con.executescript(db.SEED.read_text(encoding="utf-8"))
        con.commit()
        migrate.alle_markieren(con)
        self.con = con
        self.sid = con.execute("SELECT id FROM sparte WHERE typ <> 'verein' ORDER BY id LIMIT 1").fetchone()[0]
        self.verein_sid = con.execute("SELECT id FROM sparte WHERE typ = 'verein' ORDER BY id LIMIT 1").fetchone()[0]
        self.k1 = con.execute("INSERT INTO kategorie(sparte_id,name,richtung) VALUES(?,?,?)", (self.sid, "P60-Erste", "ausgabe")).lastrowid
        self.k2 = con.execute("INSERT INTO kategorie(sparte_id,name,richtung) VALUES(?,?,?)", (self.sid, "P60-Zweite", "einnahme")).lastrowid
        self.bid1 = self._booking("2026-02-10", "P60 Ausgabe", "ausgabe", [(self.k1, 1500)])
        self.bid2 = self._booking("2026-03-05", "P60 Einnahme", "einnahme", [(self.k2, 5000)])
        self.con.commit()

        def connection():
            yield self.con
        app.dependency_overrides[db.db_dep] = connection
        self.addCleanup(app.dependency_overrides.pop, db.db_dep)
        self.addCleanup(self.con.close)

    def _booking(self, datum, text, typ, lines):
        bid = self.con.execute(
            "INSERT INTO buchung(sparte_id,datum,typ,text) VALUES(?,?,?,?)",
            (self.sid, datum, typ, text)).lastrowid
        for kid, amount in lines:
            self.con.execute(
                "INSERT INTO buchungszeile(buchung_id,kategorie_id,betrag_cent) VALUES(?,?,?)",
                (bid, kid, amount))
        return bid

    def request(self, method, url, body=None):
        parts = urlsplit(url)
        data = json.dumps(body).encode() if body is not None else b""
        messages = []

        async def run():
            sent = False
            done = asyncio.Event()

            async def receive():
                nonlocal sent
                if not sent:
                    sent = True
                    return {"type": "http.request", "body": data}
                await done.wait()
                return {"type": "http.disconnect"}

            async def send(message):
                messages.append(message)
                if message["type"] == "http.response.body" and not message.get("more_body"):
                    done.set()

            await app({
                "type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
                "http_version": "1.1", "method": method, "scheme": "http",
                "path": parts.path, "raw_path": parts.path.encode(),
                "query_string": parts.query.encode(),
                "headers": [(b"host", b"localhost"), (b"content-type", b"application/json")],
                "client": ("127.0.0.1", 1), "server": ("localhost", 80), "root_path": "",
            }, receive, send)

        asyncio.run(run())
        status = next(m["status"] for m in messages if m["type"] == "http.response.start")
        headers = dict((k.decode(), v.decode()) for k, v in
                       next(m["headers"] for m in messages if m["type"] == "http.response.start"))
        content = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
        return status, headers, content

    def request_json(self, method, url, body=None):
        status, headers, content = self.request(method, url, body)
        return status, json.loads(content)

    # -- Seite wird ausgeliefert -------------------------------------------------

    def test_export_seite_wird_ausgeliefert(self):
        status, headers, content = self.request("GET", "/neu/pages/export.js")
        self.assertEqual(200, status)
        self.assertIn("javascript", headers.get("content-type", ""))
        self.assertIn(b"export async function render", content)

    def test_export_css_wird_ausgeliefert(self):
        status, headers, _content = self.request("GET", "/neu/pages/export.css")
        self.assertEqual(200, status)

    # -- Profil: die von export.js gelesenen Felder ------------------------------

    def test_profil_liefert_die_von_export_js_gelesenen_felder(self):
        status, profil = self.request_json(
            "GET", f"/api/export/profil?bereich_id=1&sparte_id={self.sid}&jahr=2026")
        self.assertEqual(200, status)
        for feld in ("id", "name", "kategorie_ids", "buchung_ids", "revision"):
            self.assertIn(feld, profil, f"Feld {feld} fehlt in /api/export/profil")
        self.assertEqual([], profil["kategorie_ids"])
        self.assertEqual([], profil["buchung_ids"])

    def test_put_uebernimmt_ausschluesse_und_liefert_neue_revision(self):
        _, profil = self.request_json(
            "GET", f"/api/export/profil?bereich_id=1&sparte_id={self.sid}&jahr=2026")
        status, geaendert = self.request_json(
            "PUT", f"/api/export/profil/{profil['id']}?bereich_id=1",
            {"kategorie_ids": [self.k1], "buchung_ids": []})
        self.assertEqual(200, status)
        self.assertEqual([self.k1], geaendert["kategorie_ids"])
        self.assertNotEqual(profil["revision"], geaendert["revision"])

    def test_vorjahr_uebernehmen_antwortet_mit_profil(self):
        _, profil = self.request_json(
            "GET", f"/api/export/profil?bereich_id=1&sparte_id={self.sid}&jahr=2026")
        status, ergebnis = self.request_json(
            "POST", f"/api/export/profil/{profil['id']}/uebernehmen-vom-vorjahr?bereich_id=1")
        self.assertEqual(200, status)
        self.assertIn("kategorie_ids", ergebnis)

    # -- Vorschau: Felder, die export.js zur Anzeige braucht ---------------------

    def test_vorschau_liefert_summen_ausgeschlossen_und_fehlende_belege(self):
        _, profil = self.request_json(
            "GET", f"/api/export/profil?bereich_id=1&sparte_id={self.sid}&jahr=2026")
        status, vorschau = self.request_json(
            "POST", "/api/export/vorschau?bereich_id=1", {"profil_id": profil["id"]})
        self.assertEqual(200, status)
        self.assertEqual(2, vorschau["summen"]["anzahl"])
        self.assertEqual(5000, vorschau["summen"]["einnahmen_cent"])
        self.assertEqual(1500, vorschau["summen"]["ausgaben_cent"])
        self.assertIn("kategorien", vorschau["ausgeschlossen"])
        self.assertIn("buchungen", vorschau["ausgeschlossen"])
        self.assertEqual([], vorschau["belege_fehlend"])
        self.assertIn("revision", vorschau)

    def test_vorschau_respektiert_nur_suchtreffer(self):
        _, profil = self.request_json(
            "GET", f"/api/export/profil?bereich_id=1&sparte_id={self.sid}&jahr=2026")
        status, vorschau = self.request_json(
            "POST", "/api/export/vorschau?bereich_id=1",
            {"profil_id": profil["id"], "q": "Einnahme", "nur_suchtreffer": True})
        self.assertEqual(200, status)
        self.assertEqual(1, vorschau["summen"]["anzahl"])
        self.assertEqual(5000, vorschau["summen"]["einnahmen_cent"])

    # -- Paket: Content-Type und Fehlerverträge, die export.js auswertet ---------

    def test_paket_antwortet_mit_content_type_zip(self):
        _, profil = self.request_json(
            "GET", f"/api/export/profil?bereich_id=1&sparte_id={self.sid}&jahr=2026")
        _, vorschau = self.request_json(
            "POST", "/api/export/vorschau?bereich_id=1", {"profil_id": profil["id"]})
        status, headers, content = self.request(
            "POST", "/api/export/paket?bereich_id=1",
            {"profil_id": profil["id"], "revision": vorschau["revision"]})
        self.assertEqual(200, status)
        self.assertEqual("application/zip", headers.get("content-type"))
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            self.assertIn("INHALT.txt", archive.namelist())

    def test_paket_meldet_409_bei_veralteter_revision(self):
        _, profil = self.request_json(
            "GET", f"/api/export/profil?bereich_id=1&sparte_id={self.sid}&jahr=2026")
        status, ergebnis = self.request_json(
            "POST", "/api/export/paket?bereich_id=1",
            {"profil_id": profil["id"], "revision": "veraltet"})
        self.assertEqual(409, status)
        self.assertIn("detail", ergebnis)

    def test_paket_meldet_422_bei_fehlendem_beleg(self):
        beleg_id = self.con.execute(
            "INSERT INTO beleg(bereich_id,dateiname,pfad) VALUES(1,?,?)",
            ("fehlt.jpg", str(pathlib.Path(tempfile.gettempdir()) / "p60-nicht-vorhanden.jpg"))).lastrowid
        self.con.execute(
            "INSERT INTO buchung_beleg(buchung_id,beleg_id) VALUES(?,?)", (self.bid1, beleg_id))
        self.con.commit()
        _, profil = self.request_json(
            "GET", f"/api/export/profil?bereich_id=1&sparte_id={self.sid}&jahr=2026")
        _, vorschau = self.request_json(
            "POST", "/api/export/vorschau?bereich_id=1", {"profil_id": profil["id"]})
        self.assertTrue(vorschau["belege_fehlend"])
        status, ergebnis = self.request_json(
            "POST", "/api/export/paket?bereich_id=1",
            {"profil_id": profil["id"], "revision": vorschau["revision"]})
        self.assertEqual(422, status)
        status, headers, content = self.request(
            "POST", "/api/export/paket?bereich_id=1",
            {"profil_id": profil["id"], "revision": vorschau["revision"], "trotz_fehlender_belege": True})
        self.assertEqual(200, status)
        self.assertEqual("application/zip", headers.get("content-type"))

    # -- Rohexporte, die die Weitere-Exporte-Links ansteuern ---------------------

    def test_xlsx_export_mit_profil_id_liefert_xlsx_content_type(self):
        _, profil = self.request_json(
            "GET", f"/api/export/profil?bereich_id=1&sparte_id={self.sid}&jahr=2026")
        status, headers, _content = self.request(
            "GET", f"/api/export/xlsx?bereich_id=1&profil_id={profil['id']}")
        self.assertEqual(200, status)
        self.assertEqual(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers.get("content-type"))

    def test_jahresbericht_mit_profil_id_braucht_kein_jahr_mehr(self):
        """P60b (Kopf-Nachzug nach Abnahme P60): mit profil_id kommt das Jahr aus dem
        Profil, jahr ist nur noch ohne Profil Pflicht. Vorher dokumentierte dieser
        Test die Lücke (422 ohne jahr)."""
        _, profil = self.request_json(
            "GET", f"/api/export/profil?bereich_id=1&sparte_id={self.sid}&jahr=2026")
        status, headers, content = self.request(
            "GET", f"/export/bericht?bereich_id=1&profil_id={profil['id']}")
        self.assertEqual(200, status)
        self.assertIn(b"Export-Profil", content)
        status, headers, content = self.request(
            "GET", f"/export/bericht?bereich_id=1&profil_id={profil['id']}&jahr=2026")
        self.assertEqual(200, status)
        self.assertIn("text/html", headers.get("content-type", ""))
        self.assertIn(b"Export-Profil", content)

    # -- Buchungsliste, die der Ausschluss-Dialog laedt ---------------------------

    def test_buchungen_liste_liefert_zeilen_mit_kategorie_fuer_den_dialog(self):
        status, daten = self.request_json(
            "GET", f"/api/buchungen?bereich_id=1&jahr=2026&sparte_id={self.sid}&limit=1000")
        self.assertEqual(200, status)
        self.assertEqual(2, len(daten["buchungen"]))
        erste = daten["buchungen"][0]
        for feld in ("id", "datum", "typ", "text", "zeilen"):
            self.assertIn(feld, erste)
        self.assertIn("kategorie_name", erste["zeilen"][0])
        self.assertIn("kategorie_id", erste["zeilen"][0])

    # -- Bereich 2 (Verein) bleibt auf seine eigenen Daten beschraenkt -----------

    def test_verein_bereich_sieht_nur_eigene_buchungen_im_export(self):
        v_kat = self.con.execute(
            "INSERT INTO kategorie(sparte_id,name,richtung) VALUES(?,?,?)",
            (self.verein_sid, "Verein-Kat", "ausgabe")).lastrowid
        bid = self.con.execute(
            "INSERT INTO buchung(sparte_id,datum,typ,text) VALUES(?,?,?,?)",
            (self.verein_sid, "2026-04-01", "ausgabe", "Vereinsausgabe")).lastrowid
        self.con.execute(
            "INSERT INTO buchungszeile(buchung_id,kategorie_id,betrag_cent) VALUES(?,?,?)",
            (bid, v_kat, 900))
        self.con.commit()
        status, profil = self.request_json(
            "GET", f"/api/export/profil?bereich_id=2&sparte_id={self.verein_sid}&jahr=2026")
        self.assertEqual(200, status)
        status, vorschau = self.request_json(
            "POST", "/api/export/vorschau?bereich_id=2", {"profil_id": profil["id"]})
        self.assertEqual(200, status)
        self.assertEqual(1, vorschau["summen"]["anzahl"])
        self.assertEqual(900, vorschau["summen"]["ausgaben_cent"])
        # Das Profil aus Bereich 2 ist in Bereich 1 nicht sichtbar (bereich_id fix);
        # PUT auf die fremde Bereich-1-Anfrage dient als Zugriffsprobe.
        status, ergebnis = self.request_json(
            "PUT", f"/api/export/profil/{profil['id']}?bereich_id=1",
            {"kategorie_ids": [], "buchung_ids": []})
        self.assertEqual(404, status)


class SyntaxCheckTests(unittest.TestCase):
    """node --check auf allen fuer P60 neu angelegten/geaenderten JS-Dateien."""

    def test_node_check_export_dateien(self):
        dateien = [
            ROOT / "static-neu" / "pages" / "export.js",
        ]
        node = self._node_binary()
        if node is None:
            self.skipTest("node ist in dieser Umgebung nicht verfuegbar")
        for datei in dateien:
            with self.subTest(datei=str(datei)):
                ergebnis = subprocess.run(
                    [node, "--check", str(datei)],
                    capture_output=True, text=True)
                self.assertEqual(
                    0, ergebnis.returncode,
                    f"node --check fehlgeschlagen fuer {datei}:\n{ergebnis.stderr}")

    @staticmethod
    def _node_binary():
        from shutil import which
        return which("node")


if __name__ == "__main__":
    unittest.main()
