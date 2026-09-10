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


class StaticNeuTest(unittest.TestCase):
    def setUp(self):
        self.path = pathlib.Path(tempfile.mktemp(prefix="finanz-p30-", suffix=".db"))
        self.addCleanup(lambda: self.path.unlink(missing_ok=True))
        con = sqlite3.connect(self.path, check_same_thread=False)
        con.row_factory = sqlite3.Row
        self.addCleanup(con.close)
        con.executescript(db.SCHEMA.read_text(encoding="utf-8"))
        con.executescript(db.SEED.read_text(encoding="utf-8"))
        sparte = con.execute("SELECT id FROM sparte WHERE typ <> 'verein' ORDER BY id LIMIT 1").fetchone()[0]
        con.execute("INSERT INTO kategorie(sparte_id,name,richtung) VALUES(?,?,?)", (sparte, "P30-Test", "ausgabe"))
        kategorie = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        con.execute("INSERT INTO buchung(sparte_id,datum,typ,text) VALUES(?,?,?,?)", (sparte, "2024-02-03", "ausgabe", "P30"))
        buchung = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        con.execute("INSERT INTO buchungszeile(buchung_id,kategorie_id,betrag_cent) VALUES(?,?,?)", (buchung, kategorie, 100))
        con.commit()
        env = patch.dict(os.environ, {"FINANZ_DB": str(self.path), "FINANZ_TEST_AUTH_BYPASS": "1", "FINANZ_INSTANZ": "test"})
        env.start()
        self.addCleanup(env.stop)
        def connection():
            yield con
        app.dependency_overrides[db.db_dep] = connection
        self.addCleanup(app.dependency_overrides.pop, db.db_dep)

    def request(self, method, url):
        parts = urlsplit(url)
        messages = []
        async def run():
            sent = False
            complete = asyncio.Event()
            async def receive():
                nonlocal sent
                if not sent:
                    sent = True
                    return {"type": "http.request", "body": b""}
                await complete.wait()
                return {"type": "http.disconnect"}
            async def send(message):
                messages.append(message)
                if message["type"] == "http.response.body" and not message.get("more_body"):
                    complete.set()
            scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"}, "http_version": "1.1",
                     "method": method, "scheme": "http", "path": parts.path, "raw_path": parts.path.encode(),
                     "query_string": parts.query.encode(), "headers": [(b"host", b"localhost")],
                     "client": ("127.0.0.1", 50000), "server": ("localhost", 80), "root_path": ""}
            await app(scope, receive, send)
        asyncio.run(run())
        status = next(m["status"] for m in messages if m["type"] == "http.response.start")
        body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
        try:
            return status, json.loads(body)
        except (ValueError, UnicodeDecodeError):
            return status, body

    def test_frontend_assets_and_schema_contract(self):
        self.assertEqual(200, self.request("GET", "/neu/")[0])
        self.assertIn(b"import ", self.request("GET", "/neu/app.js")[1])
        status, schema = self.request("GET", "/api/schema")
        self.assertEqual(200, status)
        self.assertEqual("test", schema["instanz"])

    def test_neu_ohne_login_wird_wie_studio_umgeleitet(self):
        with patch.dict(os.environ, {"FINANZ_TEST_AUTH_BYPASS": "0"}):
            status, _body = self.request("GET", "/neu/")
        self.assertEqual(303, status)

    def test_jahre_enthalten_buchungsjahre_und_laufendes_jahr_absteigend(self):
        status, data = self.request("GET", "/api/jahre")
        self.assertEqual(200, status, data)
        self.assertEqual(sorted(set([2024, 2026]), reverse=True), data["jahre"])


if __name__ == "__main__":
    unittest.main()
