"""P50b: Historie je Buchung (Migration 016), Verlauf-Endpunkt und -Anzeige.
P43b: request_wiederholung.art bekommt einen eigenen Wert 'beleg_uebernahme'.

Folgt dem ASGI-Testharness aus tests/test_p50_buchungen.py, damit kein TestClient
noetig ist (die Sandbox startet die Auth-Suite nicht immer, siehe NACHTRAG).
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


class P50bVerlaufTest(unittest.TestCase):
    def setUp(self):
        self.path = pathlib.Path(tempfile.mktemp(prefix="finanz-p50b-", suffix=".db"))
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
            (self.sparte_id, "P50b-Test", "ausgabe"),
        )
        self.kategorie_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        con.execute(
            "INSERT INTO kategorie(sparte_id,name,richtung) VALUES(?,?,?)",
            (self.sparte_id, "P50b-Test-2", "ausgabe"),
        )
        self.kategorie_id2 = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        con.execute(
            "INSERT INTO buchung(sparte_id,datum,typ,zahlungsart,text) VALUES(?,?,?,?,?)",
            (self.sparte_id, "2026-01-10", "ausgabe", "bar", "P50b Testbuchung"),
        )
        self.buchung_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        con.execute(
            "INSERT INTO buchungszeile(buchung_id,kategorie_id,betrag_cent) VALUES(?,?,?)",
            (self.buchung_id, self.kategorie_id, 1500),
        )
        self.zeile_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
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

    def _version(self):
        return self.con.execute(
            "SELECT version FROM buchung WHERE id=?", (self.buchung_id,)
        ).fetchone()[0]

    def _verlauf(self):
        rows = self.con.execute(
            "SELECT feld, alt, neu, grund, zeitpunkt FROM buchung_aenderung "
            "WHERE buchung_id=? ORDER BY id", (self.buchung_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ---------- Kopf- und Zeilenaenderung ----------

    def test_put_aendert_datum_und_zeilenbetrag_protokolliert_beide(self):
        body = {
            "sparte_id": self.sparte_id, "datum": "2026-02-20", "typ": "ausgabe",
            "zahlungsart": "bar", "text": "P50b Testbuchung", "zeilen": [
                {"id": self.zeile_id, "kategorie_id": self.kategorie_id, "betrag_cent": 2000}
            ], "version": self._version(),
        }
        status, data = self.request("PUT", f"/api/buchungen/{self.buchung_id}?bereich_id=1", body)
        self.assertEqual(200, status, data)
        eintraege = self._verlauf()
        felder = {e["feld"]: e for e in eintraege}
        self.assertIn("datum", felder)
        self.assertEqual("2026-01-10", felder["datum"]["alt"])
        self.assertEqual("2026-02-20", felder["datum"]["neu"])
        feld_betrag = f"zeile_{self.zeile_id}_betrag_cent"
        self.assertIn(feld_betrag, felder)
        self.assertEqual("1500", felder[feld_betrag]["alt"])
        self.assertEqual("2000", felder[feld_betrag]["neu"])

        status, verlauf = self.request("GET", f"/api/buchungen/{self.buchung_id}/verlauf?bereich_id=1")
        self.assertEqual(200, status, verlauf)
        self.assertEqual(2, len(verlauf))
        # neuester zuerst -> absteigend nach zeitpunkt/id
        self.assertGreaterEqual(verlauf[0]["id"], verlauf[1]["id"])

    def test_put_mit_identischen_werten_erzeugt_keine_eintraege(self):
        body = {
            "sparte_id": self.sparte_id, "datum": "2026-01-10", "typ": "ausgabe",
            "zahlungsart": "bar", "text": "P50b Testbuchung", "zeilen": [
                {"id": self.zeile_id, "kategorie_id": self.kategorie_id, "betrag_cent": 1500}
            ], "version": self._version(),
        }
        status, data = self.request("PUT", f"/api/buchungen/{self.buchung_id}?bereich_id=1", body)
        self.assertEqual(200, status, data)
        self.assertEqual([], self._verlauf())

    def test_put_mit_grund_traegt_alle_eintraege_dieses_aufrufs(self):
        body = {
            "sparte_id": self.sparte_id, "datum": "2026-03-01", "typ": "ausgabe",
            "zahlungsart": "bank", "text": "Neuer Text", "zeilen": [
                {"id": self.zeile_id, "kategorie_id": self.kategorie_id, "betrag_cent": 1500}
            ], "version": self._version(), "grund": "Tippfehler",
        }
        status, data = self.request("PUT", f"/api/buchungen/{self.buchung_id}?bereich_id=1", body)
        self.assertEqual(200, status, data)
        eintraege = self._verlauf()
        self.assertGreaterEqual(len(eintraege), 3)  # datum, zahlungsart, text
        for e in eintraege:
            self.assertEqual("Tippfehler", e["grund"])

    def test_put_mit_neuer_und_entfernter_zeile(self):
        body = {
            "sparte_id": self.sparte_id, "datum": "2026-01-10", "typ": "ausgabe",
            "zahlungsart": "bar", "text": "P50b Testbuchung", "zeilen": [
                {"kategorie_id": self.kategorie_id2, "betrag_cent": 700}
            ], "version": self._version(),
        }
        status, data = self.request("PUT", f"/api/buchungen/{self.buchung_id}?bereich_id=1", body)
        self.assertEqual(200, status, data)
        eintraege = self._verlauf()
        neu = [e for e in eintraege if e["feld"] == "zeile_neu"]
        entfernt = [e for e in eintraege if e["feld"] == "zeile_entfernt"]
        self.assertEqual(1, len(neu))
        self.assertEqual(1, len(entfernt))
        neu_json = json.loads(neu[0]["neu"])
        self.assertEqual(self.kategorie_id2, neu_json["kategorie_id"])
        self.assertEqual(700, neu_json["betrag_cent"])
        alt_json = json.loads(entfernt[0]["alt"])
        self.assertEqual(self.kategorie_id, alt_json["kategorie_id"])
        self.assertEqual(1500, alt_json["betrag_cent"])

    def test_put_mit_falscher_version_bleibt_409_ohne_eintraege(self):
        body = {
            "sparte_id": self.sparte_id, "datum": "2026-04-01", "typ": "ausgabe",
            "zahlungsart": "bar", "text": "Sollte nicht protokolliert werden", "zeilen": [
                {"id": self.zeile_id, "kategorie_id": self.kategorie_id, "betrag_cent": 999}
            ], "version": self._version() + 5,
        }
        status, data = self.request("PUT", f"/api/buchungen/{self.buchung_id}?bereich_id=1", body)
        self.assertEqual(409, status, data)
        self.assertEqual([], self._verlauf())

    def test_verlauf_fremder_bereich_404(self):
        status, data = self.request(
            "GET", f"/api/buchungen/{self.buchung_id}/verlauf?bereich_id=2"
        )
        self.assertEqual(404, status, data)

    # ---------- P43b: eigener Wiederholungs-Topf ----------

    def test_request_wiederholung_erlaubt_beleg_uebernahme_und_lehnt_unbekannt_ab(self):
        self.con.execute(
            "INSERT INTO request_wiederholung(art, client_request_id, bereich_id, nutzdaten_hash, antwort_json) "
            "VALUES('beleg_uebernahme', 'test-req-1', 1, 'hash', '{}')"
        )
        self.con.commit()
        row = self.con.execute(
            "SELECT art FROM request_wiederholung WHERE client_request_id='test-req-1'"
        ).fetchone()
        self.assertEqual("beleg_uebernahme", row["art"])
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute(
                "INSERT INTO request_wiederholung(art, client_request_id, bereich_id, nutzdaten_hash, antwort_json) "
                "VALUES('unbekannt', 'test-req-2', 1, 'hash', '{}')"
            )

    def test_beleg_auswertung_nutzt_beleg_uebernahme_topf(self):
        quelle = (ROOT / "app" / "routers" / "beleg_auswertung.py").read_text(encoding="utf-8")
        self.assertIn("wiederhole(con, 'beleg_uebernahme', body, bereich)", quelle)
        self.assertIn("speichere_antwort(con, 'beleg_uebernahme', body, bereich, ergebnis_antwort)", quelle)


class Migration016Test(unittest.TestCase):
    """Migration zweimal ueber den Runner; schema.sql und Nachzug ergeben denselben Stand
    (Muster wie tests/test_migrationsprotokoll.py fuer 014/015)."""

    def test_016_zweimal_und_frischschema_exakt(self):
        from contextlib import closing
        from app import migrate

        root = pathlib.Path(__file__).resolve().parents[1]
        schema = (root / 'db/schema.sql').read_text(encoding='utf-8')
        with tempfile.TemporaryDirectory() as tmp:
            with closing(sqlite3.connect(pathlib.Path(tmp) / 'alt.db')) as con:
                con.executescript(schema)
                expected = con.execute(
                    "SELECT type,name,tbl_name,sql FROM sqlite_master "
                    "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
                ).fetchall()
                migrate.alle_markieren(con)
                con.execute('DROP TABLE buchung_aenderung')
                con.execute('ALTER TABLE request_wiederholung RENAME TO request_wiederholung_alt')
                con.execute("""
                    CREATE TABLE request_wiederholung (
                        art TEXT NOT NULL CHECK (art IN ('buchung','ausgleich')),
                        client_request_id TEXT NOT NULL,
                        bereich_id INTEGER NOT NULL REFERENCES bereich(id),
                        nutzdaten_hash TEXT NOT NULL,
                        antwort_json TEXT NOT NULL,
                        PRIMARY KEY (art, client_request_id)
                    )
                """)
                con.execute(
                    "INSERT INTO request_wiederholung "
                    "SELECT art, client_request_id, bereich_id, nutzdaten_hash, antwort_json "
                    "FROM request_wiederholung_alt"
                )
                con.execute('DROP TABLE request_wiederholung_alt')
                con.execute('DELETE FROM schema_version WHERE version=16')
                con.commit()
                self.assertEqual([16], migrate.anwenden(con, None))
                self.assertEqual([], migrate.anwenden(con, None))
                actual = con.execute(
                    "SELECT type,name,tbl_name,sql FROM sqlite_master "
                    "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
                ).fetchall()
                self.assertEqual(expected, actual)
                self.assertEqual([], con.execute('PRAGMA foreign_key_check').fetchall())
                con.execute(
                    "INSERT INTO request_wiederholung(art, client_request_id, bereich_id, nutzdaten_hash, antwort_json) "
                    "VALUES('beleg_uebernahme', 'x', 1, 'h', '{}')"
                )
                with self.assertRaises(sqlite3.IntegrityError):
                    con.execute(
                        "INSERT INTO request_wiederholung(art, client_request_id, bereich_id, nutzdaten_hash, antwort_json) "
                        "VALUES('unbekannt', 'y', 1, 'h', '{}')"
                    )


class P50bJsSyntaxTest(unittest.TestCase):
    def test_node_check_buchungen_js(self):
        path = ROOT / "static-neu" / "pages" / "buchungen.js"
        result = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
