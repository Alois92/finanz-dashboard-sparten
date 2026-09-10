import asyncio
import datetime as dt
import os
import pathlib
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from app import backup, db, migrate


class NachzugSicherungTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="finanz-a1-")
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.db_path = self.root / "test.db"
        self.ordner = self.root / "backup"
        self.migrationen = self.root / "migrations"
        self.migrationen.mkdir()
        for p in (
            patch.object(db, "DB_PATH", self.db_path),
            patch.object(db, "DB_PERSISTENT", True),
            patch.object(backup, "DB_PATH", self.db_path),
            patch.object(backup, "DB_PERSISTENT", True),
            patch.object(backup, "BACKUP_ZIEL2", None),
            patch.object(migrate, "MIGRATIONS_DIR", self.migrationen),
        ):
            p.start()
            self.addCleanup(p.stop)
        db.init_db()
        self._schreibe("CREATE TABLE marker(wert TEXT)")
        self._schreibe("INSERT INTO marker VALUES('morgens')")

    def _schreibe(self, sql):
        con = db.get_connection()
        try:
            con.execute(sql)
            con.commit()
        finally:
            con.close()

    def _werte(self, pfad):
        con = sqlite3.connect(pfad)
        try:
            self.assertEqual("ok", con.execute("PRAGMA integrity_check").fetchone()[0])
            return con.execute("SELECT wert FROM marker ORDER BY rowid").fetchall()
        finally:
            con.close()

    def _migration(self, version):
        (self.migrationen / f"{version:03d}_marker.sql").write_text(
            f"INSERT INTO marker VALUES('nachzug-{version}');", encoding="utf-8"
        )

    def test_nachzug_sichert_aktuellen_stand_trotz_tageskopie(self):
        tageskopie = pathlib.Path(backup.sichere_datenbank())
        self._schreibe("INSERT INTO marker VALUES('abends')")
        self._migration(1)
        self._migration(2)

        db.init_db()

        sicherungen = list(self.ordner.glob("finanz-????-??-??-????-vor-nachzug-v2.db"))
        self.assertEqual(1, len(sicherungen))
        self.assertEqual([("morgens",)], self._werte(tageskopie))
        self.assertEqual([("morgens",), ("abends",)], self._werte(sicherungen[0]))
        self.assertEqual(
            [("morgens",), ("abends",), ("nachzug-1",), ("nachzug-2",)],
            self._werte(self.db_path),
        )

    def test_zwei_nachzuege_in_derselben_minute_ueberschreiben_nichts(self):
        self._migration(1)
        zeitpunkt = dt.datetime(2026, 9, 10, 18, 30)
        with patch.object(backup.dt, "datetime") as zeit:
            zeit.now.return_value = zeitpunkt
            db.init_db()
            erste = list(self.ordner.glob("finanz-*-vor-nachzug-*.db"))
            self.assertEqual(1, len(erste))
            vorher = erste[0].read_bytes()
            # Derselbe Zielstand kann nach einem Ruecksetzen erneut anstehen.
            self._schreibe("DELETE FROM schema_version WHERE version = 1")
            db.init_db()
        sicherungen = list(self.ordner.glob("finanz-*-vor-nachzug-*.db"))
        self.assertEqual(2, len(sicherungen))
        self.assertEqual(vorher, erste[0].read_bytes())
        zweite = next(p for p in sicherungen if p != erste[0])
        self.assertEqual([("morgens",), ("nachzug-1",)], self._werte(zweite))

    def test_rotation_behaelt_zehn_nachzuege_unabhaengig_von_tageskopien(self):
        self.ordner.mkdir()
        tage = []
        for index in range(31):
            tag = dt.date(2026, 1, 1) + dt.timedelta(days=index)
            pfad = self.ordner / f"finanz-{tag.isoformat()}.db"
            pfad.write_bytes(b"tageskopie")
            tage.append(pfad)
        alte = []
        for index in range(12):
            pfad = self.ordner / f"finanz-2020-01-01-{index:04d}-vor-nachzug-v1.db"
            pfad.write_bytes(b"nachzug")
            os.utime(pfad, (1000 + index, 1000 + index))
            alte.append(pfad)
        backup._rotiere(self.ordner)
        self.assertFalse(tage[0].exists())
        self.assertTrue(all(p.exists() for p in tage[1:]))
        self.assertTrue(all(p.exists() for p in alte[-10:]))

        self._migration(1)
        db.init_db()

        aktuelle = set(self.ordner.glob("finanz-*-vor-nachzug-*.db"))
        self.assertEqual(10, len(aktuelle))
        self.assertTrue(set(alte[-9:]).issubset(aktuelle))
        self.assertTrue(all(not p.exists() for p in alte[:3]))

    def test_schreibfehler_stoppt_pflichtnachzug(self):
        self.ordner.write_text("kein Verzeichnis", encoding="utf-8")
        self._migration(1)
        with self.assertRaises(migrate.MigrationsFehler):
            db.init_db()
        self.assertEqual([("morgens",)], self._werte(self.db_path))

    def test_wegwerf_datenbank_ueberspringt_sicherung(self):
        self.ordner.write_text("kein Verzeichnis", encoding="utf-8")
        self._migration(1)
        with patch.object(backup, "DB_PERSISTENT", False):
            db.init_db()
        self.assertEqual([("morgens",), ("nachzug-1",)], self._werte(self.db_path))

    def test_sicherungsfehler_startet_app_schreibgeschuetzt(self):
        from app import main

        self.ordner.write_text("kein Verzeichnis", encoding="utf-8")
        self._migration(1)
        self.addCleanup(setattr, main.app.state, "schreibgeschuetzt", False)
        self.addCleanup(setattr, main.app.state, "migrationsfehler", None)

        async def start():
            async with main.lifespan(main.app):
                self.assertTrue(main.app.state.schreibgeschuetzt)
                self.assertIn("Sicherung vor Nachzug fehlgeschlagen", main.app.state.migrationsfehler)

        asyncio.run(start())
        self.assertEqual([("morgens",)], self._werte(self.db_path))

    def test_ungueltige_kopie_stoppt_nachzug_und_entfernt_tempdateien(self):
        self._migration(1)
        with (
            patch.object(backup, "_ist_gueltige_sqlite_datei", return_value=False),
            self.assertRaises(migrate.MigrationsFehler),
        ):
            db.init_db()
        self.assertEqual([], list(self.ordner.iterdir()))
        self.assertEqual([("morgens",)], self._werte(self.db_path))

    def test_zwoelf_frische_sicherungen_behalten_die_letzten_zehn(self):
        pfade = []
        for index in range(12):
            self._schreibe(f"INSERT INTO marker VALUES('stand-{index}')")
            pfad = backup.sichere_datenbank(vor_nachzug_version=1)
            self.assertIsNotNone(pfad)
            pfade.append(pathlib.Path(pfad))
        self.assertEqual(12, len(set(pfade)))
        self.assertEqual(set(pfade[-10:]), set(self.ordner.glob("*.db")))
        for index in range(2, 12):
            self.assertEqual((f"stand-{index}",), self._werte(pfade[index])[-1])

    def test_rotation_ordnet_gleiche_zeitstempel_nach_laufender_nummer(self):
        self.ordner.mkdir()
        pfade = []
        for nummer in range(1, 12):
            zusatz = "" if nummer == 1 else f"-{nummer}"
            pfad = self.ordner / f"finanz-2026-09-10-1830-vor-nachzug-v1{zusatz}.db"
            pfad.write_bytes(b"sicherung")
            os.utime(pfad, (1000, 1000))
            pfade.append(pfad)
        backup._rotiere_nachzug(self.ordner)
        self.assertEqual(set(pfade[1:]), set(self.ordner.glob("*.db")))

    def test_cli_sichert_frisch_und_bricht_bei_sicherungsfehler_ab(self):
        tageskopie = pathlib.Path(backup.sichere_datenbank())
        self._schreibe("INSERT INTO marker VALUES('abends')")
        self._migration(1)
        with patch("sys.argv", ["app.migrate", "apply"]):
            self.assertEqual(0, migrate._main())
        sicherungen = list(self.ordner.glob("finanz-*-vor-nachzug-v1.db"))
        self.assertEqual(1, len(sicherungen))
        self.assertEqual([("morgens",), ("abends",)], self._werte(sicherungen[0]))
        self.assertEqual([("morgens",)], self._werte(tageskopie))
        self._migration(2)
        with (
            patch("sys.argv", ["app.migrate", "apply"]),
            patch.object(backup, "sichere_datenbank", return_value=None),
            self.assertRaises(migrate.MigrationsFehler),
        ):
            migrate._main()
