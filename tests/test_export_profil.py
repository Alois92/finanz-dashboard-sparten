import io
import json
import os
import pathlib
import sqlite3
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from app import db, migrate
from app.main import app


class ExportProfilTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.tmp._finalizer.detach()
        self.auth_env = patch.dict(os.environ, {"FINANZ_TEST_AUTH_BYPASS": "1"})
        self.auth_env.start()
        self.addCleanup(self.auth_env.stop)
        self.path = ":memory:"
        con = sqlite3.connect(self.path, check_same_thread=False)
        con.row_factory = sqlite3.Row
        con.executescript(db.SCHEMA.read_text(encoding="utf-8"))
        con.executescript(db.SEED.read_text(encoding="utf-8"))
        con.commit()
        migrate.alle_markieren(con)
        self.con = con
        self.sid = con.execute("SELECT id FROM sparte WHERE typ <> 'verein' LIMIT 1").fetchone()[0]
        self.k1 = con.execute("INSERT INTO kategorie(sparte_id,name,richtung) VALUES(?,?,?)", (self.sid, "Erste", "ausgabe")).lastrowid
        self.k2 = con.execute("INSERT INTO kategorie(sparte_id,name,richtung) VALUES(?,?,?)", (self.sid, "Zweite", "ausgabe")).lastrowid
        self.bid = self._booking("2026-01-02", "Buchung", [(self.k1, 700), (self.k2, 300)])
        self.con.commit()
        def connection():
            yield self.con
        app.dependency_overrides[db.db_dep] = connection
        self.addCleanup(app.dependency_overrides.pop, db.db_dep)
        self.addCleanup(self.con.close)

    def _booking(self, datum, text, lines):
        bid = self.con.execute("INSERT INTO buchung(sparte_id,datum,typ,text) VALUES(?,?,?,?)", (self.sid, datum, "ausgabe", text)).lastrowid
        for kid, amount in lines:
            self.con.execute("INSERT INTO buchungszeile(buchung_id,kategorie_id,betrag_cent) VALUES(?,?,?)", (bid, kid, amount))
        return bid

    def request(self, method, url, body=None):
        from urllib.parse import urlsplit
        import asyncio
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
            await app({"type":"http", "asgi":{"version":"3.0","spec_version":"2.4"},"http_version":"1.1","method":method,"scheme":"http","path":parts.path,"raw_path":parts.path.encode(),"query_string":parts.query.encode(),"headers":[(b"host",b"localhost"),(b"content-type",b"application/json")],"client":("127.0.0.1",1),"server":("localhost",80),"root_path":""}, receive, send)
        asyncio.run(run())
        status = next(m["status"] for m in messages if m["type"] == "http.response.start")
        content = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
        try:
            return status, json.loads(content)
        except (ValueError, UnicodeDecodeError):
            return status, content

    def test_vorschau_respektiert_kategorie_und_buchungsausschluss(self):
        status, profil = self.request("GET", f"/api/export/profil?bereich_id=1&sparte_id={self.sid}&jahr=2026")
        self.assertEqual(200, status)
        self.assertEqual([], profil["ausschluesse"])
        status, profil = self.request("PUT", f"/api/export/profil/{profil['id']}?bereich_id=1", {"kategorie_ids": [self.k1], "buchung_ids": []})
        self.assertEqual(200, status)
        status, preview = self.request("POST", "/api/export/vorschau?bereich_id=1", {"profil_id": profil["id"]})
        self.assertEqual(200, status)
        self.assertEqual(1, preview["summen"]["anzahl"])
        self.assertEqual(300, preview["summen"]["ausgaben_cent"])
        self.assertEqual(1, preview["ausgeschlossen"]["kategorien"])

    def test_paket_enthaelt_excel_und_inhalt(self):
        _, profil = self.request("GET", f"/api/export/profil?sparte_id={self.sid}&jahr=2026")
        status, package = self.request("POST", "/api/export/paket", {"profil_id": profil["id"], "revision": profil["revision"]})
        self.assertEqual(200, status)
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            self.assertIn("INHALT.txt", archive.namelist())
            self.assertTrue(any(name.endswith(".xlsx") for name in archive.namelist()))

    def test_alte_revision_wird_abgewiesen(self):
        _, profil = self.request("GET", f"/api/export/profil?sparte_id={self.sid}&jahr=2026")
        self.con.execute("UPDATE buchung SET text='geändert' WHERE id=?", (self.bid,))
        self.con.commit()
        status, result = self.request("POST", "/api/export/paket", {"profil_id": profil["id"], "revision": profil["revision"]})
        self.assertEqual(409, status)
        self.assertIn("Revision", result["detail"])


if __name__ == "__main__":
    unittest.main()
