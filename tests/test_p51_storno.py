"""P51: Storno beidseitig und Erstattung als verknuepfte Gegenbuchung (Migration 017).

Folgt demselben ASGI-Testharness wie tests/test_p50b_verlauf.py.
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


class P51StornoErstattungTest(unittest.TestCase):
    def setUp(self):
        self.path = pathlib.Path(tempfile.mktemp(prefix="finanz-p51-", suffix=".db"))
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
            (self.sparte_id, "P51-Ausgabe", "ausgabe"),
        )
        self.kat_ausgabe_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        con.execute(
            "INSERT INTO kategorie(sparte_id,name,richtung) VALUES(?,?,?)",
            (self.sparte_id, "P51-Beides", "beides"),
        )
        self.kat_beides_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        con.execute(
            "INSERT INTO kategorie(sparte_id,name,richtung) VALUES(?,?,?)",
            (self.sparte_id, "P51-Einnahme", "einnahme"),
        )
        self.kat_einnahme_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Ausgabe 100 EUR (fuer Storno- und Erstattungstests)
        con.execute(
            "INSERT INTO buchung(sparte_id,datum,typ,zahlungsart,text) VALUES(?,?,?,?,?)",
            (self.sparte_id, "2026-02-01", "ausgabe", "bar", "P51 Ausgabe"),
        )
        self.ausgabe_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        con.execute(
            "INSERT INTO buchungszeile(buchung_id,kategorie_id,betrag_cent) VALUES(?,?,?)",
            (self.ausgabe_id, self.kat_beides_id, 10000),
        )
        self.ausgabe_zeile_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Einnahme 50 EUR (fuer Ruecküberweisung)
        con.execute(
            "INSERT INTO buchung(sparte_id,datum,typ,zahlungsart,text) VALUES(?,?,?,?,?)",
            (self.sparte_id, "2026-02-02", "einnahme", "bar", "P51 Einnahme"),
        )
        self.einnahme_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        con.execute(
            "INSERT INTO buchungszeile(buchung_id,kategorie_id,betrag_cent) VALUES(?,?,?)",
            (self.einnahme_id, self.kat_beides_id, 5000),
        )
        self.einnahme_zeile_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]

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

    def _summen(self, typ=None):
        f = f"/api/buchungen?bereich_id=1&sparte_id={self.sparte_id}&jahr=2026"
        if typ:
            f += f"&typ={typ}"
        status, data = self.request("GET", f)
        self.assertEqual(200, status, data)
        return data["summen"]

    # ---------- Storno ----------

    def test_stornieren_setzt_storniert_am_und_zaehlt_nicht_mehr_in_summen(self):
        vorher = self._summen()
        status, data = self.request("POST", f"/api/buchungen/{self.ausgabe_id}/stornieren?bereich_id=1", {})
        self.assertEqual(200, status, data)
        self.assertIsNotNone(data["storniert_am"])
        nachher = self._summen()
        self.assertEqual(vorher["ausgaben_cent"] - 10000, nachher["ausgaben_cent"])
        status, liste = self.request(
            "GET", f"/api/buchungen?bereich_id=1&sparte_id={self.sparte_id}&jahr=2026"
        )
        row = next(b for b in liste["buchungen"] if b["id"] == self.ausgabe_id)
        self.assertIsNotNone(row["storniert_am"])

    def test_entstornieren_setzt_storniert_am_zurueck_und_zaehlt_wieder(self):
        self.request("POST", f"/api/buchungen/{self.ausgabe_id}/stornieren?bereich_id=1", {})
        vorher = self._summen()
        status, data = self.request("POST", f"/api/buchungen/{self.ausgabe_id}/entstornieren?bereich_id=1", {})
        self.assertEqual(200, status, data)
        self.assertIsNone(data["storniert_am"])
        nachher = self._summen()
        self.assertEqual(vorher["ausgaben_cent"] + 10000, nachher["ausgaben_cent"])

    def test_zweimal_stornieren_gibt_409_entstornieren_ohne_storno_gibt_409(self):
        status, _ = self.request("POST", f"/api/buchungen/{self.ausgabe_id}/stornieren?bereich_id=1", {})
        self.assertEqual(200, status)
        status, data = self.request("POST", f"/api/buchungen/{self.ausgabe_id}/stornieren?bereich_id=1", {})
        self.assertEqual(409, status, data)
        status, data = self.request("POST", f"/api/buchungen/{self.einnahme_id}/entstornieren?bereich_id=1", {})
        self.assertEqual(409, status, data)

    def test_stornieren_umbuchung_gibt_422(self):
        status, umbuchung = self.request("POST", "/api/umbuchungen?bereich_id=1", {
            "von_sparte_id": self.sparte_id,
            "nach_sparte_id": self._andere_sparte(),
            "datum": "2026-02-05", "betrag_cent": 500, "zahlungsart": "bar",
        })
        self.assertEqual(201, status, umbuchung)
        status, data = self.request(
            "POST", f"/api/buchungen/{umbuchung['buchung_ids'][0]}/stornieren?bereich_id=1", {}
        )
        self.assertEqual(422, status, data)

    def test_stornieren_protokolliert_buchung_aenderung(self):
        status, _ = self.request("POST", f"/api/buchungen/{self.ausgabe_id}/stornieren?bereich_id=1", {"grund": "Fehlbuchung"})
        self.assertEqual(200, status)
        rows = self.con.execute(
            "SELECT feld, alt, neu, grund FROM buchung_aenderung WHERE buchung_id=?", (self.ausgabe_id,)
        ).fetchall()
        self.assertEqual(1, len(rows))
        self.assertEqual("storniert_am", rows[0]["feld"])
        self.assertIsNone(rows[0]["alt"])
        self.assertIsNotNone(rows[0]["neu"])
        self.assertEqual("Fehlbuchung", rows[0]["grund"])

    def _andere_sparte(self):
        row = self.con.execute(
            "SELECT id FROM sparte WHERE typ <> 'verein' AND id <> ? ORDER BY id LIMIT 1",
            (self.sparte_id,),
        ).fetchone()
        if row:
            return row[0]
        return self.con.execute(
            "INSERT INTO sparte(name, kuerzel, typ) VALUES('P51 Zweit', 'P51Z', 'sonstiges')"
        ).lastrowid

    # ---------- Erstattung ----------

    def test_ausgabe_teilweise_erstatten_netto_und_getrennte_summen(self):
        status, data = self.request("POST", f"/api/buchungen/{self.ausgabe_id}/erstatten?bereich_id=1", {
            "datum": "2026-02-10",
            "zeilen": [{"original_zeile_id": self.ausgabe_zeile_id, "betrag_cent": 6000}],
        })
        self.assertEqual(201, status, data)
        self.assertEqual("einnahme", data["typ"])
        self.assertEqual(self.ausgabe_id, data["original_id"])

        status, original = self.request("GET", f"/api/buchungen/{self.ausgabe_id}?bereich_id=1")
        self.assertEqual(200, status, original)
        self.assertEqual(4000, original["netto_cent"])

        summen = self._summen()
        self.assertEqual(10000, summen["ausgaben_cent"])
        self.assertGreaterEqual(summen["einnahmen_cent"], 6000)

    def test_uebererstattung_gibt_422_mit_rest_cent(self):
        status, data = self.request("POST", f"/api/buchungen/{self.ausgabe_id}/erstatten?bereich_id=1", {
            "datum": "2026-02-10",
            "zeilen": [{"original_zeile_id": self.ausgabe_zeile_id, "betrag_cent": 10001}],
        })
        self.assertEqual(422, status, data)
        self.assertIn("rest_cent", data["detail"])
        self.assertEqual(10000, data["detail"]["rest_cent"])

    def test_erstattung_mit_kategorie_ohne_richtung_beides_gibt_422(self):
        status, data = self.request("POST", f"/api/buchungen/{self.ausgabe_id}/erstatten?bereich_id=1", {
            "datum": "2026-02-10",
            "zeilen": [{
                "original_zeile_id": self.ausgabe_zeile_id, "betrag_cent": 1000,
                "kategorie_id": self.kat_ausgabe_id,
            }],
        })
        self.assertEqual(422, status, data)

    def test_einnahme_erstatten_ruecküberweisung_wird_ausgabe(self):
        status, data = self.request("POST", f"/api/buchungen/{self.einnahme_id}/erstatten?bereich_id=1", {
            "datum": "2026-02-11",
            "zeilen": [{"original_zeile_id": self.einnahme_zeile_id, "betrag_cent": 2000}],
        })
        self.assertEqual(201, status, data)
        self.assertEqual("ausgabe", data["typ"])
        self.assertEqual(self.einnahme_id, data["original_id"])

    def test_erstattung_auf_umbuchung_stornierter_und_erstattung_der_erstattung_422_409_422(self):
        status, umbuchung = self.request("POST", "/api/umbuchungen?bereich_id=1", {
            "von_sparte_id": self.sparte_id,
            "nach_sparte_id": self._andere_sparte(),
            "datum": "2026-02-05", "betrag_cent": 500, "zahlungsart": "bar",
        })
        self.assertEqual(201, status, umbuchung)
        status, data = self.request(
            "POST", f"/api/buchungen/{umbuchung['buchung_ids'][0]}/erstatten?bereich_id=1",
            {"datum": "2026-02-06", "zeilen": [{"original_zeile_id": 1, "betrag_cent": 100}]},
        )
        self.assertEqual(422, status, data)

        self.request("POST", f"/api/buchungen/{self.ausgabe_id}/stornieren?bereich_id=1", {})
        status, data = self.request("POST", f"/api/buchungen/{self.ausgabe_id}/erstatten?bereich_id=1", {
            "datum": "2026-02-10",
            "zeilen": [{"original_zeile_id": self.ausgabe_zeile_id, "betrag_cent": 1000}],
        })
        self.assertEqual(409, status, data)

        status, erstattung = self.request("POST", f"/api/buchungen/{self.einnahme_id}/erstatten?bereich_id=1", {
            "datum": "2026-02-11",
            "zeilen": [{"original_zeile_id": self.einnahme_zeile_id, "betrag_cent": 1000}],
        })
        self.assertEqual(201, status, erstattung)
        status, data = self.request(
            "POST", f"/api/buchungen/{erstattung['id']}/erstatten?bereich_id=1",
            {"datum": "2026-02-12", "zeilen": [{"original_zeile_id": erstattung["zeilen"][0]["id"], "betrag_cent": 100}]},
        )
        self.assertEqual(422, status, data)


class Migration017Test(unittest.TestCase):
    """Migration zweimal ueber den Runner; schema.sql und Nachzug ergeben denselben Stand
    inklusive Views (Muster wie tests/test_migrationsprotokoll.py fuer 014/015)."""

    def test_017_zweimal_und_frischschema_exakt(self):
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
                con.execute('DROP VIEW v_einnahmen_ausgaben')
                con.execute('DROP VIEW v_zeile')
                con.execute("""
                    CREATE VIEW v_zeile AS
                    SELECT
                        bz.id AS zeile_id, b.id AS buchung_id, b.sparte_id AS sparte_id,
                        b.datum AS datum, b.typ AS typ,
                        CASE b.typ WHEN 'ausgabe' THEN -bz.betrag_cent ELSE bz.betrag_cent END AS betrag_signed_cent,
                        bz.betrag_cent AS betrag_cent, bz.kategorie_id AS kategorie_id, bz.neutral AS neutral,
                        CASE WHEN b.typ = 'umbuchung' THEN 1 ELSE 0 END AS ist_transfer
                    FROM buchungszeile bz JOIN buchung b ON b.id = bz.buchung_id
                """)
                con.execute(
                    "CREATE VIEW v_einnahmen_ausgaben AS "
                    "SELECT * FROM v_zeile WHERE ist_transfer = 0 AND neutral = 0"
                )
                con.execute('ALTER TABLE buchungszeile DROP COLUMN original_zeile_id')
                con.execute('ALTER TABLE buchung DROP COLUMN original_id')
                con.execute('ALTER TABLE buchung DROP COLUMN storniert_am')
                con.execute('DELETE FROM schema_version WHERE version=17')
                con.commit()
                self.assertEqual([17], migrate.anwenden(con, None))
                self.assertEqual([], migrate.anwenden(con, None))
                actual = con.execute(
                    "SELECT type,name,tbl_name,sql FROM sqlite_master "
                    "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
                ).fetchall()
                self.assertEqual(expected, actual)
                self.assertEqual([], con.execute('PRAGMA foreign_key_check').fetchall())
                cols = {r[1] for r in con.execute('PRAGMA table_info(v_zeile)')}
                # Views melden keine table_info-Spalten in aelteren SQLite-Versionen einheitlich;
                # daher direkt gegen die View selektieren.
                row = con.execute("SELECT storniert_am, neutral FROM v_zeile LIMIT 0").fetchall()
                self.assertEqual([], row)


class P51JsSyntaxTest(unittest.TestCase):
    def test_node_check_buchungen_js(self):
        path = ROOT / "static-neu" / "pages" / "buchungen.js"
        result = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
