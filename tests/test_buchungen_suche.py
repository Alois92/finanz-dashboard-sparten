import pathlib
import sqlite3
import tempfile
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db import db_dep
from app.routers import buchungen


ROOT = pathlib.Path(__file__).resolve().parents[1]


class BuchungenSucheApiTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = pathlib.Path(self.tempdir.name) / "suche.db"
        self.con = sqlite3.connect(self.db_path, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys = ON")
        self.con.executescript((ROOT / "db" / "schema.sql").read_text(encoding="utf-8"))
        self.con.executescript((ROOT / "db" / "seed.sql").read_text(encoding="utf-8"))
        self.sparte_id = self.con.execute("SELECT id FROM sparte ORDER BY id LIMIT 1").fetchone()[0]
        self.kategorie_id = self.con.execute(
            "INSERT INTO kategorie(sparte_id, name, richtung) VALUES(?, 'Test', 'beides')",
            (self.sparte_id,),
        ).lastrowid
        self.con.commit()

        app = FastAPI()
        app.include_router(buchungen.router, prefix="/api")

        def override_db():
            yield self.con

        app.dependency_overrides[db_dep] = override_db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.con.close()
        self.tempdir.cleanup()

    def _buchung(self, *, text="", notiz=None, kontakt_id=None, datum="2026-01-01"):
        cur = self.con.execute(
            "INSERT INTO buchung(sparte_id, datum, typ, text, notiz, kontakt_id) "
            "VALUES(?, ?, 'ausgabe', ?, ?, ?)",
            (self.sparte_id, datum, text, notiz, kontakt_id),
        )
        self.con.execute(
            "INSERT INTO buchungszeile(buchung_id, kategorie_id, betrag_cent) VALUES(?, ?, 100)",
            (cur.lastrowid, self.kategorie_id),
        )
        self.con.commit()
        return cur.lastrowid

    def test_sucht_case_insensitiv_in_text_notiz_und_kontakt(self):
        kontakt_id = self.con.execute(
            "INSERT INTO kontakt(name) VALUES(?)", ("\u00c4rztin Maier",)
        ).lastrowid
        text_id = self._buchung(text="\u00d6L f\u00fcr Traktor", datum="2026-03-03")
        notiz_id = self._buchung(text="B\u00fcro", notiz="SonderNotiz", datum="2026-03-02")
        kontakt_buchung_id = self._buchung(
            text="Ordination", kontakt_id=kontakt_id, datum="2026-03-01"
        )

        self.assertEqual(
            [row["id"] for row in self.client.get("/api/buchungen/suche", params={"q": "\u00f6l"}).json()],
            [text_id],
        )
        self.assertEqual(
            [row["id"] for row in self.client.get("/api/buchungen/suche", params={"q": "sonderNOTIZ"}).json()],
            [notiz_id],
        )
        self.assertEqual(
            [row["id"] for row in self.client.get("/api/buchungen/suche", params={"q": "\u00e4rZTIN"}).json()],
            [kontakt_buchung_id],
        )

    def test_liefert_hoechstens_200_neueste_buchungen(self):
        ids = [self._buchung(text="Grenzfall") for _ in range(205)]

        response = self.client.get("/api/buchungen/suche", params={"q": "grenzFALL"})

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(len(result), 200)
        self.assertEqual([row["id"] for row in result], list(reversed(ids))[:200])
        self.assertIn("zeilen", result[0])
        self.assertIn("belege", result[0])

