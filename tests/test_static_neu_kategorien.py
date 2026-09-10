"""P33: Kategorienpflege unter /neu.

Deckt aus Frontend-Sicht ab, was static-neu/pages/kategorien.js tatsaechlich
verwendet (Auftragskarte P33, Abschnitt 3 und 6): Seite ausgeliefert, Umbenennen
ohne ID-Aenderung, Stichwort als echter regel-Datensatz anlegen/entfernen,
Aggregation der bereichsweiten Jahresmatrix ueber eine globale Kategoriegruppe
mit Kategorien aus zwei Sparten, sowie die Antwortfelder, die die Seite laut
Karte liest.
"""
import asyncio
import json
import os
import pathlib
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from app import db
from app.main import app

ROOT = pathlib.Path(__file__).resolve().parents[1]


class P33KategorienTest(unittest.TestCase):
    def setUp(self):
        self.path = pathlib.Path(tempfile.mktemp(prefix="finanz-p33-", suffix=".db"))
        self.addCleanup(lambda: self.path.unlink(missing_ok=True))
        con = sqlite3.connect(self.path, check_same_thread=False)
        con.row_factory = sqlite3.Row
        self.addCleanup(con.close)
        con.executescript(db.SCHEMA.read_text(encoding="utf-8"))
        con.executescript(db.SEED.read_text(encoding="utf-8"))
        self.con = con

        sparten = [r["id"] for r in con.execute(
            "SELECT id FROM sparte WHERE typ <> 'verein' ORDER BY id LIMIT 2"
        ).fetchall()]
        self.sparte_a, self.sparte_b = sparten

        con.execute("INSERT INTO kategorie(sparte_id,name,richtung) VALUES(?,?,?)",
                     (self.sparte_a, "P33 Futtermittel", "ausgabe"))
        self.kategorie_a = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        con.execute("INSERT INTO kategorie(sparte_id,name,richtung,aktiv) VALUES(?,?,?,0)",
                     (self.sparte_a, "P33 Stillgelegt", "ausgabe"))
        self.kategorie_still = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        con.execute("INSERT INTO kategorie(sparte_id,name,richtung) VALUES(?,?,?)",
                     (self.sparte_b, "P33 Reparaturen", "ausgabe"))
        self.kategorie_b = con.execute("SELECT last_insert_rowid()").fetchone()[0]

        jahr = "2026"
        for kategorie_id, sparte_id, betrag in (
            (self.kategorie_a, self.sparte_a, 12000),
            (self.kategorie_b, self.sparte_b, 5000),
        ):
            con.execute(
                "INSERT INTO buchung(sparte_id,datum,typ,zahlungsart,text) VALUES(?,?,?,?,?)",
                (sparte_id, f"{jahr}-03-10", "ausgabe", "bar", "P33 Testbuchung"),
            )
            buchung_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
            con.execute(
                "INSERT INTO buchungszeile(buchung_id,kategorie_id,betrag_cent) VALUES(?,?,?)",
                (buchung_id, kategorie_id, betrag),
            )

        # Stichwort-Regel (quelle='stichwort') fuer kategorie_a.
        con.execute(
            "INSERT INTO regel(name,bedingung_text,ziel_sparte_id,ziel_kategorie_id,quelle,"
            "bereich_id) VALUES(?,?,?,?,?,1)",
            ("lagerhaus", "lagerhaus", self.sparte_a, self.kategorie_a, "stichwort"),
        )
        self.regel_stichwort = con.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Gelernte Regel (quelle='gelernt') fuer kategorie_b, mit Konto.
        con.execute(
            "INSERT INTO bankkonto(name,art,waehrung,bereich_id) VALUES(?,?,?,1)",
            ("P33 Testkonto", "bank", "EUR"),
        )
        self.konto_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        con.execute(
            "INSERT INTO regel(name,bedingung_text,ziel_sparte_id,ziel_kategorie_id,quelle,"
            "bankkonto_id,bereich_id) VALUES(?,?,?,?,?,?,1)",
            ("werkstatt", "werkstatt", self.sparte_b, self.kategorie_b, "gelernt", self.konto_id),
        )
        self.regel_gelernt = con.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Globale Kategoriegruppe mit Kategorien aus zwei Sparten.
        con.execute("INSERT INTO globale_kategoriegruppe(name,bereich_id) VALUES(?,1)",
                     ("P33 Gruppe",))
        self.gruppe_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        con.executemany(
            "INSERT INTO kategorie_globalgruppe(kategorie_id,globalgruppe_id) VALUES(?,?)",
            [(self.kategorie_a, self.gruppe_id), (self.kategorie_b, self.gruppe_id)],
        )
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

    # ---------- Seite ausgeliefert ----------

    def test_seite_liefert_js_das_auf_api_und_endpunkte_verweist(self):
        status, body = self.request("GET", "/neu/pages/kategorien.js")
        self.assertEqual(200, status)
        text = body.decode("utf-8") if isinstance(body, (bytes, bytearray)) else body
        self.assertIn("from '../api.js'", text)
        self.assertIn("export async function render", text)
        for endpunkt in ("/kategorien", "/jahresmatrix", "/regeln", "/globalgruppen"):
            self.assertIn(endpunkt, text)

    def test_node_check_kategorien_js(self):
        node = None
        try:
            node = subprocess.run(["node", "--version"], capture_output=True, text=True)
        except FileNotFoundError:
            pass
        if not node or node.returncode != 0:
            self.skipTest("node ist in dieser Umgebung nicht verfuegbar")
        pfad = ROOT / "static-neu" / "pages" / "kategorien.js"
        result = subprocess.run(["node", "--check", str(pfad)], capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)

    # ---------- Umbenennen aendert nur den Namen ----------

    def test_patch_kategorie_aendert_nur_namen_id_bleibt_stabil(self):
        status, vorher = self.request(
            "GET", f"/api/regeln?bereich_id=1&quelle=stichwort"
        )
        self.assertEqual(200, status)
        self.assertTrue(any(r["ziel_kategorie_id"] == self.kategorie_a for r in vorher))

        status, data = self.request(
            "PATCH", f"/api/kategorien/{self.kategorie_a}?bereich_id=1", {"name": "Neuer Name"}
        )
        self.assertEqual(200, status, data)
        self.assertEqual("Neuer Name", data["name"])
        self.assertEqual(self.kategorie_a, data["id"])

        status, nachher = self.request("GET", "/api/regeln?bereich_id=1&quelle=stichwort")
        self.assertEqual(200, status)
        self.assertTrue(any(r["ziel_kategorie_id"] == self.kategorie_a for r in nachher))

        status, matrix = self.request(
            "GET", f"/api/jahresmatrix?bereich_id=1&sparte_id={self.sparte_a}&jahre=2026",
        )
        self.assertEqual(200, status)
        zeile = next(z for z in matrix["zeilen"] if z["kategorie_id"] == self.kategorie_a)
        self.assertEqual("Neuer Name", zeile["name"])
        self.assertEqual(12000, zeile["werte"]["2026"]["ausgaben_cent"])

    # ---------- Stichwort anlegen und entfernen ----------

    def test_stichwort_anlegen_und_entfernen(self):
        status, data = self.request(
            "POST", "/api/regeln?bereich_id=1",
            {"name": "spar", "bedingung_text": "spar", "ziel_kategorie_id": self.kategorie_b,
             "quelle": "stichwort"},
        )
        self.assertEqual(201, status, data)
        neue_regel_id = data["id"]

        status, liste = self.request("GET", "/api/regeln?bereich_id=1&quelle=stichwort")
        self.assertEqual(200, status)
        self.assertTrue(any(r["id"] == neue_regel_id and r["aktiv"] for r in liste))

        status, data = self.request(
            "PATCH", f"/api/regeln/{neue_regel_id}?bereich_id=1", {"aktiv": False}
        )
        self.assertEqual(200, status, data)
        self.assertEqual(0, data["aktiv"])

        status, liste = self.request("GET", "/api/regeln?bereich_id=1&quelle=stichwort")
        self.assertEqual(200, status)
        aktive = [r for r in liste if r["id"] == neue_regel_id and r["aktiv"]]
        self.assertEqual([], aktive)

    # ---------- Gelernte Regel abschalten ----------

    def test_gelernte_regel_abschalten(self):
        status, liste = self.request("GET", "/api/regeln?bereich_id=1&quelle=gelernt")
        self.assertEqual(200, status)
        self.assertTrue(any(r["id"] == self.regel_gelernt and r["aktiv"] for r in liste))

        status, data = self.request(
            "PATCH", f"/api/regeln/{self.regel_gelernt}?bereich_id=1", {"aktiv": False}
        )
        self.assertEqual(200, status, data)

        status, liste = self.request("GET", "/api/regeln?bereich_id=1&quelle=gelernt")
        self.assertEqual(200, status)
        aktive = [r for r in liste if r["id"] == self.regel_gelernt and r["aktiv"]]
        self.assertEqual([], aktive)

    # ---------- Globale Gruppe ueber zwei Sparten: Aggregationsweg ----------

    def test_globalgruppe_summe_aus_bereichsweiter_jahresmatrix_entspricht_einzelsparten(self):
        status, gruppen = self.request("GET", "/api/globalgruppen?bereich_id=1")
        self.assertEqual(200, status, gruppen)
        gruppe = next(g for g in gruppen if g["id"] == self.gruppe_id)
        self.assertEqual(sorted([self.kategorie_a, self.kategorie_b]), sorted(gruppe["kategorie_ids"]))

        status, bereichsweit = self.request("GET", "/api/jahresmatrix?bereich_id=1&jahre=2026")
        self.assertEqual(200, status, bereichsweit)
        by_id = {z["kategorie_id"]: z for z in bereichsweit["zeilen"]}
        summe_bereichsweit = sum(
            by_id[kid]["werte"]["2026"]["ausgaben_cent"] for kid in gruppe["kategorie_ids"]
        )

        status, matrix_a = self.request(
            "GET", f"/api/jahresmatrix?bereich_id=1&sparte_id={self.sparte_a}&jahre=2026"
        )
        self.assertEqual(200, status)
        zeile_a = next(z for z in matrix_a["zeilen"] if z["kategorie_id"] == self.kategorie_a)
        status, matrix_b = self.request(
            "GET", f"/api/jahresmatrix?bereich_id=1&sparte_id={self.sparte_b}&jahre=2026"
        )
        self.assertEqual(200, status)
        zeile_b = next(z for z in matrix_b["zeilen"] if z["kategorie_id"] == self.kategorie_b)

        summe_einzeln = zeile_a["werte"]["2026"]["ausgaben_cent"] + zeile_b["werte"]["2026"]["ausgaben_cent"]
        self.assertEqual(summe_einzeln, summe_bereichsweit)
        self.assertEqual(12000 + 5000, summe_bereichsweit)

    # ---------- Antwortform der verwendeten Endpunkte (Vertragstest) ----------

    def test_antwortformen_enthalten_die_von_kategorien_js_verwendeten_felder(self):
        status, kategorien = self.request(
            "GET", f"/api/kategorien?bereich_id=1&sparte_id={self.sparte_a}&nur_aktive=false"
        )
        self.assertEqual(200, status)
        for feld in ("id", "sparte_id", "parent_id", "name", "richtung", "aktiv", "sortierung"):
            self.assertIn(feld, kategorien[0])

        status, matrix = self.request(
            "GET", f"/api/jahresmatrix?bereich_id=1&sparte_id={self.sparte_a}&jahre=2026"
        )
        self.assertEqual(200, status)
        zeile = next(z for z in matrix["zeilen"] if z["kategorie_id"] == self.kategorie_a)
        for feld in ("kategorie_id", "werte", "monatsdurchschnitt_cent", "name", "sparte_id", "aktiv", "richtung"):
            self.assertIn(feld, zeile)
        self.assertIn("einnahmen_cent", zeile["werte"]["2026"])
        self.assertIn("ausgaben_cent", zeile["werte"]["2026"])

        status, regeln = self.request("GET", "/api/regeln?bereich_id=1&quelle=stichwort")
        self.assertEqual(200, status)
        for feld in ("id", "name", "bedingung_text", "ziel_kategorie_id", "quelle",
                     "auto_verbuchen", "aktiv", "erstellt_am", "bankkonto_id", "eingabe_sparte_id"):
            self.assertIn(feld, regeln[0])

        status, gruppen = self.request("GET", "/api/globalgruppen?bereich_id=1")
        self.assertEqual(200, status)
        for feld in ("id", "name", "beschreibung", "kategorie_ids"):
            self.assertIn(feld, gruppen[0])

        status, konten = self.request("GET", "/api/konten?bereich_id=1")
        self.assertEqual(200, status)
        self.assertIn("name", konten[0])


if __name__ == "__main__":
    unittest.main()
