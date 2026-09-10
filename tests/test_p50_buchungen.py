"""P50: Buchungsliste mit Suche/Filtern, Bearbeiten mit Versionssperre.

Deckt aus Frontend-Sicht ab, was static-neu/pages/buchungen.js tatsächlich
verwendet: Seite ausgeliefert, Listen-/Cursor-Vertrag aus P20, Bearbeiten mit
optimistischer Sperre (version, 409 bei Konflikt). Keine Migration und kein
neuer Router-Endpunkt in diesem Paket (siehe docs/neubau/berichte/P50-runde1.md,
"Wunsch an das Gerüst") - GET /verlauf bleibt daher bewusst ungetestet.
"""
import asyncio
import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from app import db
from app.main import app

ROOT = pathlib.Path(__file__).resolve().parents[1]


class P50BuchungenTest(unittest.TestCase):
    def setUp(self):
        self.path = pathlib.Path(tempfile.mktemp(prefix="finanz-p50-", suffix=".db"))
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
            (self.sparte_id, "P50-Test", "ausgabe"),
        )
        self.kategorie_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        con.execute(
            "INSERT INTO buchung(sparte_id,datum,typ,zahlungsart,text) VALUES(?,?,?,?,?)",
            (self.sparte_id, "2026-01-10", "ausgabe", "bar", "P50 Testbuchung"),
        )
        self.buchung_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        con.execute(
            "INSERT INTO buchungszeile(buchung_id,kategorie_id,betrag_cent) VALUES(?,?,?)",
            (self.buchung_id, self.kategorie_id, 1500),
        )
        con.execute(
            "INSERT INTO buchung(sparte_id,datum,typ,zahlungsart,text) VALUES(?,?,?,?,?)",
            (self.sparte_id, "2026-01-11", "ausgabe", "bar", "P50 Zweite Buchung"),
        )
        self.buchung_id2 = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        con.execute(
            "INSERT INTO buchungszeile(buchung_id,kategorie_id,betrag_cent) VALUES(?,?,?)",
            (self.buchung_id2, self.kategorie_id, 2500),
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

    def test_seite_und_modul_werden_ausgeliefert(self):
        status, body = self.request("GET", "/neu/")
        self.assertEqual(200, status)
        status, body = self.request("GET", "/neu/pages/buchungen.js")
        self.assertEqual(200, status)
        self.assertIn(b"export function render", body)
        status, body = self.request("GET", "/neu/pages/buchungen.css")
        self.assertEqual(200, status)

    # ---------- Listen-/Cursor-Vertrag (aus P20, hier: Felder die das Modul liest) ----------

    def test_liste_liefert_felder_die_das_modul_liest(self):
        status, data = self.request(
            "GET", f"/api/buchungen?bereich_id=1&sparte_id={self.sparte_id}&jahr=2026"
        )
        self.assertEqual(200, status, data)
        self.assertIn("buchungen", data)
        self.assertIn("summen", data)
        self.assertIn("naechster_cursor", data)
        summen = data["summen"]
        for feld in ("anzahl", "einnahmen_cent", "ausgaben_cent"):
            self.assertIn(feld, summen)
        zeile = data["buchungen"][0]
        for feld in ("id", "sparte_id", "datum", "typ", "zahlungsart", "text", "notiz",
                     "version", "betrag_cent", "zeilen", "belege"):
            self.assertIn(feld, zeile)
        self.assertIn("kategorie_id", zeile["zeilen"][0])
        self.assertIn("kategorie_name", zeile["zeilen"][0])
        self.assertIn("betrag_cent", zeile["zeilen"][0])

    def test_liste_mit_q_filtert_auf_text(self):
        status, data = self.request(
            "GET", f"/api/buchungen?bereich_id=1&jahr=2026&q=Zweite"
        )
        self.assertEqual(200, status, data)
        self.assertEqual(1, data["summen"]["anzahl"])
        self.assertEqual("P50 Zweite Buchung", data["buchungen"][0]["text"])

    def test_liste_mit_limit_liefert_cursor_und_naechste_seite_ist_vollstaendig(self):
        status, erste = self.request(
            "GET", f"/api/buchungen?bereich_id=1&jahr=2026&limit=1"
        )
        self.assertEqual(200, status, erste)
        self.assertEqual(1, len(erste["buchungen"]))
        self.assertIsNotNone(erste["naechster_cursor"])
        status, zweite = self.request(
            "GET",
            f"/api/buchungen?bereich_id=1&jahr=2026&limit=1&cursor={erste['naechster_cursor']}",
        )
        self.assertEqual(200, status, zweite)
        self.assertEqual(1, len(zweite["buchungen"]))
        self.assertNotEqual(erste["buchungen"][0]["id"], zweite["buchungen"][0]["id"])

    # ---------- Bearbeiten mit Versionssperre ----------

    def test_put_aendert_buchung_und_erhoeht_version(self):
        version = self.con.execute(
            "SELECT version FROM buchung WHERE id=?", (self.buchung_id,)
        ).fetchone()[0]
        body = {
            "sparte_id": self.sparte_id, "datum": "2026-01-15", "typ": "ausgabe",
            "zahlungsart": "bar", "text": "Geaendert", "zeilen": [
                {"kategorie_id": self.kategorie_id, "betrag_cent": 999}
            ], "version": version,
        }
        status, data = self.request(
            "PUT", f"/api/buchungen/{self.buchung_id}?bereich_id=1", body
        )
        self.assertEqual(200, status, data)
        self.assertEqual("Geaendert", data["text"])
        self.assertEqual(version + 1, data["version"])
        self.assertEqual(999, data["betrag_cent"])

    def test_put_mit_veralteter_version_liefert_409_und_aendert_nichts(self):
        version = self.con.execute(
            "SELECT version FROM buchung WHERE id=?", (self.buchung_id,)
        ).fetchone()[0]
        erster_body = {
            "sparte_id": self.sparte_id, "datum": "2026-01-16", "typ": "ausgabe",
            "zahlungsart": "bar", "text": "Erste Aenderung", "zeilen": [
                {"kategorie_id": self.kategorie_id, "betrag_cent": 111}
            ], "version": version,
        }
        status, _ = self.request("PUT", f"/api/buchungen/{self.buchung_id}?bereich_id=1", erster_body)
        self.assertEqual(200, status)
        # Zweiter PUT mit der jetzt veralteten (alten) version -> Konflikt, kein Schreibzugriff.
        konflikt_body = {**erster_body, "text": "Sollte nicht ankommen"}
        status, data = self.request("PUT", f"/api/buchungen/{self.buchung_id}?bereich_id=1", konflikt_body)
        self.assertEqual(409, status, data)
        text = self.con.execute(
            "SELECT text FROM buchung WHERE id=?", (self.buchung_id,)
        ).fetchone()[0]
        self.assertEqual("Erste Aenderung", text)
        self.assertNotEqual("Sollte nicht ankommen", text)

    def test_delete_entfernt_buchung(self):
        status, _ = self.request("DELETE", f"/api/buchungen/{self.buchung_id2}?bereich_id=1")
        self.assertEqual(204, status)
        row = self.con.execute(
            "SELECT id FROM buchung WHERE id=?", (self.buchung_id2,)
        ).fetchone()
        self.assertIsNone(row)

    # ---------- Historie fehlt bewusst (siehe Bericht) ----------

    def test_verlauf_endpunkt_existiert_in_diesem_paket_nicht(self):
        status, _ = self.request("GET", f"/api/buchungen/{self.buchung_id}/verlauf?bereich_id=1")
        self.assertEqual(404, status)


class P50JsSyntaxTest(unittest.TestCase):
    def test_node_check_js_dateien(self):
        for name in ("buchungen.js",):
            path = ROOT / "static-neu" / "pages" / name
            result = subprocess.run(
                ["node", "--check", str(path)], capture_output=True, text=True
            )
            self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
