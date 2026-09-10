"""P52: Kredit-Oberflaeche unter /neu.

Deckt aus Frontend-Sicht ab, was static-neu/pages/kredit.js tatsaechlich
verwendet: Seite/Modul/CSS werden ausgeliefert, Route ist in app.js registriert,
und der Vertrag der in P14 definierten Endpunkte (/api/kredite,
/api/kredite/{id}/jahre/{jahr}, /api/kredite/{id}/raten,
/api/kredite/{id}/raten/zuordnen) passt zu den Feldern, die die Seite liest.
Keine Migration, kein neuer Router-Endpunkt (app/routers/kredite.py und
app/kredite.py bleiben unveraendert).
"""
import asyncio
import json
import os
import pathlib
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from app import db
from app.main import app

ROOT = pathlib.Path(__file__).resolve().parents[1]


class P52KreditTest(unittest.TestCase):
    def setUp(self):
        self.path = pathlib.Path(tempfile.mktemp(prefix="finanz-p52-", suffix=".db"))
        self.addCleanup(lambda: self.path.unlink(missing_ok=True))
        con = sqlite3.connect(self.path, check_same_thread=False)
        con.row_factory = sqlite3.Row
        self.addCleanup(con.close)
        con.executescript(db.SCHEMA.read_text(encoding="utf-8"))
        con.executescript(db.SEED.read_text(encoding="utf-8"))
        self.con = con
        self.sparte_id = con.execute(
            "SELECT id FROM sparte WHERE typ <> 'verein' ORDER BY id LIMIT 1"
        ).fetchone()[0]
        con.execute(
            "INSERT INTO kategorie(sparte_id,name,richtung) VALUES(?,?,?)",
            (self.sparte_id, "P52-Zins", "ausgabe"),
        )
        self.kat_zins_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        con.execute(
            "INSERT INTO kategorie(sparte_id,name,richtung) VALUES(?,?,?)",
            (self.sparte_id, "P52-Tilgung", "ausgabe"),
        )
        self.kat_rate_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        con.commit()

        env = patch.dict(
            os.environ,
            {"FINANZ_DB": str(self.path), "FINANZ_TEST_AUTH_BYPASS": "1", "FINANZ_INSTANZ": "test"},
        )
        env.start()
        self.addCleanup(env.stop)

        def connection():
            yield con

        app.dependency_overrides[db.db_dep] = connection
        self.addCleanup(app.dependency_overrides.pop, db.db_dep)

    def request(self, method, url, body=None):
        parts = urlsplit(url)
        messages = []
        body_bytes = json.dumps(body).encode() if body is not None else b""

        async def run():
            sent = False
            complete = asyncio.Event()

            async def receive():
                nonlocal sent
                if not sent:
                    sent = True
                    return {"type": "http.request", "body": body_bytes}
                await complete.wait()
                return {"type": "http.disconnect"}

            async def send(message):
                messages.append(message)
                if message["type"] == "http.response.body" and not message.get("more_body"):
                    complete.set()

            headers = [(b"host", b"localhost")]
            if body is not None:
                headers.append((b"content-type", b"application/json"))
            scope = {
                "type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"}, "http_version": "1.1",
                "method": method, "scheme": "http", "path": parts.path, "raw_path": parts.path.encode(),
                "query_string": parts.query.encode(), "headers": headers,
                "client": ("127.0.0.1", 50000), "server": ("localhost", 80), "root_path": "",
            }
            await app(scope, receive, send)

        asyncio.run(run())
        status = next(m["status"] for m in messages if m["type"] == "http.response.start")
        resp_body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
        if not resp_body:
            return status, None
        try:
            return status, json.loads(resp_body)
        except (ValueError, UnicodeDecodeError):
            return status, resp_body

    def _kredit_anlegen(self):
        body = {
            "sparte_id": self.sparte_id,
            "name": "P52-Testkredit",
            "monatsrate_cent": 50000,
            "beginn": "2025-01-01",
            "zinssatz": 0.035,
            "kategorie_zins_id": self.kat_zins_id,
            "kategorie_rate_id": self.kat_rate_id,
        }
        status, data = self.request("POST", "/api/kredite?bereich_id=1", body)
        self.assertEqual(201, status, data)
        return data

    # ---------- Seite/Modul ausgeliefert ----------

    def test_seite_und_modul_werden_ausgeliefert(self):
        status, _ = self.request("GET", "/neu/")
        self.assertEqual(200, status)
        status, body = self.request("GET", "/neu/pages/kredit.js")
        self.assertEqual(200, status)
        self.assertIn(b"export function render", body)
        status, _ = self.request("GET", "/neu/pages/kredit.css")
        self.assertEqual(200, status)

    def test_route_ist_in_app_js_registriert(self):
        status, body = self.request("GET", "/neu/app.js")
        self.assertEqual(200, status)
        text = body.decode("utf-8")
        self.assertIn("kredit:['Kredit','kredit']", text)

    # ---------- Vertrag: Kredit anlegen ----------

    def test_kredit_anlegen_liefert_felder_die_die_seite_liest(self):
        data = self._kredit_anlegen()
        for feld in ("id", "name", "sparte_id", "monatsrate_cent", "beginn", "jahre"):
            self.assertIn(feld, data)
        self.assertEqual([], data["jahre"])

    # ---------- Vertrag: Jahr bestaetigen mit Abweichung ----------

    def test_jahr_bestaetigen_mit_11_statt_12_raten_zeigt_abweichung(self):
        kredit = self._kredit_anlegen()
        kredit_id = kredit["id"]
        for monat in range(1, 12):  # 11 Raten statt 12
            status, _ = self.request(
                "POST", f"/api/kredite/{kredit_id}/raten?bereich_id=1",
                {"datum": f"2025-{monat:02d}-05", "betrag_cent": 50000},
            )
            self.assertEqual(201, status)
        status, data = self.request(
            "PUT", f"/api/kredite/{kredit_id}/jahre/2025?bereich_id=1",
            {"zins_cent": 110000, "restschuld_cent": 4500000},
        )
        self.assertEqual(200, status, data)
        self.assertIn("raten", data)
        self.assertIn("verteilt_cent", data)
        self.assertIn("abweichungen", data)
        self.assertEqual(11, data["raten"])
        self.assertTrue(any("11 Raten" in a and "statt 12" in a for a in data["abweichungen"]))

    # ---------- Vertrag: Ratentabelle mit Zins/Tilgung ----------

    def test_ratenliste_liefert_zins_und_tilgung_getrennt(self):
        kredit = self._kredit_anlegen()
        kredit_id = kredit["id"]
        status, rate = self.request(
            "POST", f"/api/kredite/{kredit_id}/raten?bereich_id=1",
            {"datum": "2025-03-05", "betrag_cent": 50000},
        )
        self.assertEqual(201, status, rate)
        for feld in ("id", "kredit_id", "datum", "betrag_cent", "zins_cent", "tilgung_cent", "status", "hinweis"):
            self.assertIn(feld, rate)
        status, raten = self.request("GET", f"/api/kredite/{kredit_id}/raten?bereich_id=1&jahr=2025")
        self.assertEqual(200, status, raten)
        self.assertEqual(1, len(raten))
        for feld in ("id", "kredit_id", "datum", "betrag_cent", "zins_cent", "tilgung_cent", "status"):
            self.assertIn(feld, raten[0])

    # ---------- Vertrag: bestehende Buchungen zuordnen ----------

    def test_zuordnen_verknuepft_bestehende_buchung_mit_dem_kredit(self):
        kredit = self._kredit_anlegen()
        kredit_id = kredit["id"]
        self.con.execute(
            "INSERT INTO buchung(sparte_id,datum,typ,betrag_cent,zahlungsart,text) "
            "VALUES(?,?, 'ausgabe', 50000, 'bank', 'Alte Kreditrate')",
            (self.sparte_id, "2024-06-05"),
        )
        buchung_id = self.con.execute("SELECT last_insert_rowid()").fetchone()[0]
        self.con.execute(
            "INSERT INTO buchungszeile(buchung_id,kategorie_id,betrag_cent) VALUES(?,?,?)",
            (buchung_id, self.kat_rate_id, 50000),
        )
        self.con.commit()

        status, buchungen = self.request(
            "GET", f"/api/buchungen?bereich_id=1&sparte_id={self.sparte_id}&jahr=2024"
        )
        self.assertEqual(200, status, buchungen)
        kandidat = next(b for b in buchungen["buchungen"] if b["id"] == buchung_id)
        self.assertIsNone(kandidat["kredit_id"])
        self.assertTrue(any(z["kategorie_id"] == self.kat_rate_id for z in kandidat["zeilen"]))

        status, data = self.request(
            "POST", f"/api/kredite/{kredit_id}/raten/zuordnen?bereich_id=1",
            {"buchung_ids": [buchung_id]},
        )
        self.assertEqual(200, status, data)
        self.assertEqual({"raten": 1, "buchung_ids": [buchung_id]}, data)
        neuer_kredit_id = self.con.execute(
            "SELECT kredit_id FROM buchung WHERE id=?", (buchung_id,)
        ).fetchone()[0]
        self.assertEqual(kredit_id, neuer_kredit_id)


if __name__ == "__main__":
    unittest.main()
