import datetime as dt
import pathlib
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from app import backup


class BackupTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tempdir.name)
        self.source = self.root / "quelle.db"
        con = sqlite3.connect(self.source)
        con.execute("CREATE TABLE marker(wert TEXT NOT NULL)")
        con.execute("INSERT INTO marker(wert) VALUES('vollstaendig')")
        con.commit()
        con.close()
        self.target = (
            self.root / "backup" / f"finanz-{dt.date.today().isoformat()}.db"
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def _source_connection(self):
        return sqlite3.connect(self.source)

    def test_beschaedigte_tagesdatei_wird_durch_gueltige_sicherung_ersetzt(self):
        self.target.parent.mkdir()
        self.target.write_bytes(b"")

        with (
            patch.object(backup, "DB_PATH", self.source),
            patch.object(backup, "DB_PERSISTENT", True),
            patch.object(backup, "get_connection", self._source_connection),
        ):
            result = backup.sichere_datenbank()

        self.assertEqual(result, str(self.target))
        con = sqlite3.connect(self.target)
        try:
            self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(con.execute("SELECT wert FROM marker").fetchone()[0], "vollstaendig")
        finally:
            con.close()

    def test_fehlgeschlagene_sicherung_hinterlaesst_keine_tagesdatei(self):
        class FehlerQuelle:
            def backup(self, ziel):
                ziel.execute("CREATE TABLE unvollstaendig(id INTEGER)")
                raise sqlite3.OperationalError("simulierter Abbruch")

            def close(self):
                pass

        with (
            patch.object(backup, "DB_PATH", self.source),
            patch.object(backup, "DB_PERSISTENT", True),
            patch.object(backup, "get_connection", return_value=FehlerQuelle()),
        ):
            result = backup.sichere_datenbank()

        self.assertIsNone(result)
        self.assertFalse(self.target.exists())

    def _sichere_mit_zweitziel(self, ziel2):
        with (
            patch.object(backup, "DB_PATH", self.source),
            patch.object(backup, "DB_PERSISTENT", True),
            patch.object(backup, "get_connection", self._source_connection),
            patch.object(backup, "BACKUP_ZIEL2", ziel2),
        ):
            return backup.sichere_datenbank()

    def test_zweitziel_erhaelt_eine_gueltige_zweitkopie(self):
        ziel2 = self.root / "nas"
        result = self._sichere_mit_zweitziel(ziel2)

        self.assertEqual(result, str(self.target))
        zweitkopie = ziel2 / self.target.name
        self.assertTrue(zweitkopie.exists())
        self.assertTrue(backup._ist_gueltige_sqlite_datei(zweitkopie))
        con = sqlite3.connect(zweitkopie)
        try:
            self.assertEqual(
                con.execute("SELECT wert FROM marker").fetchone()[0], "vollstaendig")
        finally:
            con.close()

    def test_unerreichbares_zweitziel_laesst_erstkopie_gueltig(self):
        # Nicht erreichbarer UNC-Pfad steht hier fuer "NAS gerade offline".
        result = self._sichere_mit_zweitziel(
            pathlib.Path(r"\\kein-host-xyz-existiert\share\backup"))

        self.assertEqual(result, str(self.target))
        self.assertTrue(backup._ist_gueltige_sqlite_datei(self.target))

    def test_ohne_zweitziel_bleibt_alles_wie_bisher(self):
        result = self._sichere_mit_zweitziel(None)

        self.assertEqual(result, str(self.target))
        self.assertEqual(
            sorted(p.name for p in self.target.parent.iterdir()),
            [self.target.name],
        )


if __name__ == "__main__":
    unittest.main()

