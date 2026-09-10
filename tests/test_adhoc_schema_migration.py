import pathlib
import re
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from app import backup, db, migrate


class AdhocSchemaMigrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="finanz-a4-")
        self.addCleanup(self.temp.cleanup)
        self.path = pathlib.Path(self.temp.name) / "test.db"
        self.con = sqlite3.connect(self.path)
        self.addCleanup(self.con.close)
        self.con.executescript(db.SCHEMA.read_text(encoding="utf-8"))
        migrate.alle_markieren(self.con)
        self.con.execute("DELETE FROM schema_version WHERE version = 11")
        self.con.executescript("""
            INSERT INTO sparte(id, name, kuerzel, typ, farbe, sortierung) VALUES
                (1, 'Privat', 'PV', 'privat', NULL, 10),
                (2, 'Eigene Farbe', 'HOF', 'hof', '#123456', 20),
                (3, 'Eigen B', 'B', 'sonstiges', '', 40),
                (4, 'Eigen A', 'A', 'sonstiges', NULL, 30);
            INSERT INTO beleg(id, dateiname, pfad) VALUES(1, 'test.jpg', 'test.jpg');
        """)

    def test_fehlende_objekte_werden_mit_identischer_struktur_nachgezogen(self):
        expected = self.con.execute(
            "SELECT type, name, sql FROM sqlite_master "
            "WHERE tbl_name = 'beleg_auswertung' ORDER BY name"
        ).fetchall()
        self.con.execute("DROP TABLE beleg_auswertung")
        self.con.commit()

        self.assertEqual([11], migrate.anwenden(self.con, None))

        actual = self.con.execute(
            "SELECT type, name, sql FROM sqlite_master "
            "WHERE tbl_name = 'beleg_auswertung' ORDER BY name"
        ).fetchall()
        normalize = lambda rows: [(kind, name, re.sub(r"\s+", "", sql))
                                  for kind, name, sql in rows]
        self.assertEqual(normalize(expected), normalize(actual))
        self.assertEqual([], self.con.execute("PRAGMA foreign_key_check").fetchall())

    def test_vorhandene_objekte_daten_und_farben_bleiben_erhalten(self):
        self.con.execute("INSERT INTO beleg_auswertung(beleg_id, status, ergebnis_json) "
                         "VALUES(1, 'fertig', '{}')")
        self.con.commit()
        self.assertEqual([11], migrate.anwenden(self.con, None))
        self.assertEqual([(1, '#6AA9FF'), (2, '#123456'), (3, '#C084FC'), (4, '#2DD4BF')],
                         self.con.execute("SELECT id, farbe FROM sparte ORDER BY id").fetchall())
        before = list(self.con.iterdump())
        self.assertEqual([], migrate.anwenden(self.con, None))
        migration = next(p for v, _, p in migrate.liste_migrationen() if v == 11)
        migrate._lade_python_migration(migration).up(self.con)
        self.con.commit()
        self.assertEqual(before, list(self.con.iterdump()))

    def test_start_ohne_nachzug_fuehrt_keine_schema_oder_farbaenderungen_aus(self):
        migrate.alle_markieren(self.con)
        statements = []
        connect = db.get_connection

        def traced_connection():
            con = connect()
            con.set_trace_callback(statements.append)
            return con

        with (patch.object(db, "DB_PATH", self.path),
              patch.object(db, "get_connection", side_effect=traced_connection)):
            db.init_db()

        self.assertEqual([], [sql for sql in statements
                             if re.match(r"\s*(CREATE|ALTER|DROP|UPDATE|INSERT|DELETE)\b",
                                         sql, re.I)])

    def test_sicherung_enthaelt_stand_vor_schema_und_farbnachzug(self):
        self.con.execute("DROP TABLE beleg_auswertung")
        self.con.commit()
        with (patch.object(db, "DB_PATH", self.path),
              patch.object(backup, "DB_PATH", self.path),
              patch.object(backup, "DB_PERSISTENT", True),
              patch.object(backup, "BACKUP_ZIEL2", None)):
            db.init_db()
        copies = list(self.path.parent.glob("backup/*-vor-nachzug-v11.db"))
        self.assertEqual(1, len(copies))
        con = sqlite3.connect(copies[0])
        try:
            self.assertIsNone(con.execute("SELECT 1 FROM sqlite_master "
                                          "WHERE name='beleg_auswertung'").fetchone())
            self.assertIsNone(con.execute("SELECT farbe FROM sparte WHERE id=1").fetchone()[0])
        finally:
            con.close()
