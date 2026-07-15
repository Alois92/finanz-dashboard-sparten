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


if __name__ == "__main__":
    unittest.main()

