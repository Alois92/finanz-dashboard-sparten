import pathlib
import sqlite3
import tempfile
import unittest
from contextlib import closing

from app import db, migrate
from app.main import app
import test_bereiche as bereiche_tests
from test_konten_bewegungen import bestand


class MigrationsprotokollTest(unittest.TestCase):
    def test_ungeklaerte_umbuchung_wird_nachzugfest_protokolliert_und_nicht_doppelt(self):
        with tempfile.TemporaryDirectory(prefix="finanz-n6-") as tmp:
            path = pathlib.Path(tmp) / "bestand.db"
            with closing(sqlite3.connect(path)) as con:
                bestand(con)
                self.assertEqual([4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15], migrate.anwenden(con, None))
                eintrag = con.execute(
                    "SELECT version, art, objektkennung, hinweis FROM migrationsprotokoll "
                    "WHERE art='umbuchung_ungeklaert'"
                ).fetchone()
                self.assertEqual(4, eintrag[0])
                self.assertIn("Umbuchungsgruppe offen", eintrag[3])
                self.assertEqual([], migrate.anwenden(con, None))
                self.assertEqual(1, con.execute(
                    "SELECT count(*) FROM migrationsprotokoll WHERE objektkennung=?",
                    (eintrag[2],),
                ).fetchone()[0])


class MigrationsprotokollApiTest(unittest.TestCase):
    setUp = bereiche_tests.BereicheTest.setUp
    request = bereiche_tests.BereicheTest.request

    def test_endpunkt_liefert_protokoll_mit_bereichsdependency(self):
        self.con.execute(
            "INSERT INTO migrationsprotokoll(version, art, objektkennung, hinweis) "
            "VALUES(4, 'umbuchung_ungeklaert', 'umbuchungsgruppe:offen', "
            "'Umbuchungsgruppe offen konnte nicht eindeutig auf Konten aufgeloest werden.')"
        )
        self.con.commit()
        status, result = self.request("GET", "/api/betrieb/migrationsprotokoll")
        self.assertEqual(200, status)
        self.assertEqual("umbuchung_ungeklaert", result[0]["art"])
        self.assertIn("nicht eindeutig", result[0]["hinweis"])
        self.assertEqual(404, self.request("GET", "/api/betrieb/migrationsprotokoll?bereich_id=999")[0])


if __name__ == "__main__":
    unittest.main()
