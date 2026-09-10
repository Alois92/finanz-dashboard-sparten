import pathlib
import sqlite3
import tempfile
import unittest
from contextlib import closing

from app import migrate


class HinweisMigrationTest(unittest.TestCase):
    def test_014_zweimal_und_frischschema_exakt(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            with closing(sqlite3.connect(pathlib.Path(tmp) / 'alt.db')) as con:
                con.executescript((root / 'db/schema.sql').read_text(encoding='utf-8'))
                expected = con.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall()
                migrate.alle_markieren(con)
                con.execute('DROP TABLE hinweis_aus')
                con.execute('DELETE FROM schema_version WHERE version=14')
                con.commit()
                self.assertEqual([14], migrate.anwenden(con, None))
                self.assertEqual([], migrate.anwenden(con, None))
                self.assertEqual(expected, con.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall())
                con.executescript((root / 'db/migrations/014_hinweis_aus.sql').read_text(encoding='utf-8'))
                con.execute("INSERT INTO hinweis_aus(bereich_id,schluessel) VALUES(1,'x'),(2,'x')")
                with self.assertRaises(sqlite3.IntegrityError):
                    con.execute("INSERT INTO hinweis_aus(bereich_id,schluessel) VALUES(1,'x')")
