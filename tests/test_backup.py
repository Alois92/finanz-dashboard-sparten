import datetime as dt
import hashlib
import json
import pathlib
import shutil
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
        con.execute("CREATE TABLE beleg(id INTEGER PRIMARY KEY, dateiname TEXT NOT NULL, pfad TEXT NOT NULL, sparte_id INTEGER)")
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

    def _lege_belege_an(self, *dateien):
        belege = self.root / "belege"
        con = sqlite3.connect(self.source)
        con.execute("CREATE TABLE IF NOT EXISTS beleg(id INTEGER PRIMARY KEY, dateiname TEXT NOT NULL, pfad TEXT NOT NULL, sparte_id INTEGER)")
        for beleg_id, (name, inhalt) in enumerate(dateien, 1):
            sparte_id = beleg_id
            pfad = belege / str(sparte_id) / f"{beleg_id}_{name}"
            pfad.parent.mkdir(parents=True, exist_ok=True)
            pfad.write_bytes(inhalt)
            con.execute(
                "INSERT INTO beleg(id, dateiname, pfad, sparte_id) VALUES(?,?,?,?)",
                (beleg_id, name, str(pfad), sparte_id),
            )
        con.commit()
        con.close()
        return belege

    def _sichere(self):
        with (
            patch.object(backup, "DB_PATH", self.source),
            patch.object(backup, "DB_PERSISTENT", True),
            patch.object(backup, "get_connection", self._source_connection),
        ):
            return backup.sichere_datenbank()

    def test_belege_manifest_und_pruefsummen_werden_gesichert(self):
        belege = self._lege_belege_an(("rechnung-a.pdf", b"A"), ("rechnung-b.pdf", b"BB"))

        self.assertEqual(self._sichere(), str(self.target))
        zielordner = self.target.parent / f"belege-{dt.date.today().isoformat()}"
        manifest = json.loads(
            (self.target.parent / f"manifest-{dt.date.today().isoformat()}.json").read_text()
        )
        self.assertEqual(
            {eintrag["datei"] for eintrag in manifest["belege"]},
            {"1/1_rechnung-a.pdf", "2/2_rechnung-b.pdf"},
        )
        for beleg_id, name in ((1, "rechnung-a.pdf"), (2, "rechnung-b.pdf")):
            self.assertEqual(
                hashlib.sha256((belege / str(beleg_id) / f"{beleg_id}_{name}").read_bytes()).hexdigest(),
                hashlib.sha256((zielordner / str(beleg_id) / f"{beleg_id}_{name}").read_bytes()).hexdigest(),
            )
        with patch.object(backup, "DB_PATH", self.source):
            pruefung = backup.pruefe_sicherung(dt.date.today().isoformat())
        self.assertEqual({"db_ok": True, "belege_ok": 2, "belege_fehlend": 0, "manifest_ok": True}, pruefung)

    def test_fehlender_beleg_steht_im_manifest_und_db_sicherung_bleibt_erfolgreich(self):
        belege = self._lege_belege_an(("fehlt.pdf", b"X"))
        (belege / "1" / "1_fehlt.pdf").unlink()

        self.assertEqual(self._sichere(), str(self.target))
        manifest = json.loads(
            (self.target.parent / f"manifest-{dt.date.today().isoformat()}.json").read_text()
        )
        self.assertEqual([{"beleg_id": 1, "pfad": str(belege / "1" / "1_fehlt.pdf")}], manifest["fehlend"])

    def test_zweiter_lauf_am_selben_tag_ist_idempotent(self):
        self._lege_belege_an(("rechnung.pdf", b"A"))
        self._sichere()
        manifest = self.target.parent / f"manifest-{dt.date.today().isoformat()}.json"
        belegkopie = self.target.parent / f"belege-{dt.date.today().isoformat()}" / "1" / "1_rechnung.pdf"
        vorher = (manifest.read_bytes(), belegkopie.stat().st_mtime_ns)

        self._sichere()

        self.assertEqual(vorher, (manifest.read_bytes(), belegkopie.stat().st_mtime_ns))

    def test_rotation_entfernt_db_belegordner_und_manifest_gemeinsam(self):
        backup_dir = self.source.parent / "backup"
        tage = [dt.date.today() - dt.timedelta(days=offset) for offset in range(31, 0, -1)]
        for tag in tage:
            datum = tag.isoformat()
            (backup_dir / f"finanz-{datum}.db").parent.mkdir(parents=True, exist_ok=True)
            (backup_dir / f"finanz-{datum}.db").write_bytes(b"db")
            (backup_dir / f"belege-{datum}").mkdir()
            (backup_dir / f"belege-{datum}" / "x.pdf").write_bytes(b"x")
            (backup_dir / f"manifest-{datum}.json").write_text("{}")

        backup._rotiere(backup_dir)

        self.assertFalse((backup_dir / f"finanz-{(dt.date.today() - dt.timedelta(days=31)).isoformat()}.db").exists())
        self.assertFalse((backup_dir / f"belege-{(dt.date.today() - dt.timedelta(days=31)).isoformat()}").exists())
        self.assertFalse((backup_dir / f"manifest-{(dt.date.today() - dt.timedelta(days=31)).isoformat()}.json").exists())
        self.assertTrue((backup_dir / f"finanz-{(dt.date.today() - dt.timedelta(days=1)).isoformat()}.db").exists())

    def test_pruefe_sicherung_erkennt_manipulierte_belegkopie(self):
        self._lege_belege_an(("rechnung.pdf", b"A"))
        self._sichere()
        (self.target.parent / f"belege-{dt.date.today().isoformat()}" / "1" / "1_rechnung.pdf").write_bytes(b"manipuliert")

        with patch.object(backup, "DB_PATH", self.source):
            pruefung = backup.pruefe_sicherung(dt.date.today().isoformat())

        self.assertEqual({"db_ok": True, "belege_ok": 0, "belege_fehlend": 1, "manifest_ok": False}, pruefung)

    def test_betriebsstatus_enthaelt_nur_oeffentliche_sicherungsfelder(self):
        self._lege_belege_an(("rechnung.pdf", b"A"))
        self._sichere()
        from app import main

        with (
            patch.object(main, "get_connection", return_value=sqlite3.connect(self.source)),
            patch.object(main, "migrationsstatus", return_value={"aktuell": 2, "anstehend": []}),
            patch.object(backup, "DB_PATH", self.source),
            patch.object(backup, "BACKUP_ZIEL2", None),
        ):
            try:
                status = main.betrieb_status()
            finally:
                main.get_connection.return_value.close()

        self.assertEqual(
            {
                "schema": {"aktuell": 2, "anstehend": []},
                "sicherung": {
                    "letzte": dt.date.today().isoformat(),
                    "db_ok": True,
                    "belege_ok": 1,
                    "belege_fehlend": 0,
                    "zweitziel": "nicht konfiguriert",
                },
                "schreibgeschuetzt": False,
            },
            status,
        )

    def test_identische_originalnamen_in_verschiedenen_sparten_bleiben_getrennt(self):
        belege = self.root / "belege"
        con = sqlite3.connect(self.source)
        con.execute("CREATE TABLE IF NOT EXISTS beleg(id INTEGER PRIMARY KEY, dateiname TEXT NOT NULL, pfad TEXT NOT NULL, sparte_id INTEGER)")
        for beleg_id, sparte_id, inhalt in ((1, 10, b"eins"), (2, 20, b"zwei")):
            pfad = belege / str(sparte_id) / f"{beleg_id}_rechnung.pdf"
            pfad.parent.mkdir(parents=True, exist_ok=True)
            pfad.write_bytes(inhalt)
            con.execute("INSERT INTO beleg(id, dateiname, pfad, sparte_id) VALUES(?,?,?,?)", (beleg_id, "rechnung.pdf", str(pfad), sparte_id))
        con.commit()
        con.close()

        self._sichere()
        zielordner = self.target.parent / f"belege-{dt.date.today().isoformat()}"
        self.assertEqual(sorted(p.relative_to(zielordner).as_posix() for p in zielordner.rglob("*") if p.is_file()), ["10/1_rechnung.pdf", "20/2_rechnung.pdf"])
        self.assertEqual((zielordner / "10/1_rechnung.pdf").read_bytes(), b"eins")
        self.assertEqual((zielordner / "20/2_rechnung.pdf").read_bytes(), b"zwei")
        with patch.object(backup, "DB_PATH", self.source):
            pruefung = backup.pruefe_sicherung(dt.date.today().isoformat())
        self.assertEqual(pruefung, {"db_ok": True, "belege_ok": 2, "belege_fehlend": 0, "manifest_ok": True})

    def test_geloeschte_belegkopie_wird_beim_zweiten_lauf_erneuert(self):
        self._lege_belege_an(("rechnung.pdf", b"A"))
        self._sichere()
        ziel = self.target.parent / f"belege-{dt.date.today().isoformat()}" / "1" / "1_rechnung.pdf"
        ziel.unlink()

        self._sichere()

        self.assertEqual(ziel.read_bytes(), b"A")
        with patch.object(backup, "DB_PATH", self.source):
            pruefung = backup.pruefe_sicherung(dt.date.today().isoformat())
        self.assertTrue(pruefung["manifest_ok"])

    def test_belegsicherung_ohne_db_kopie_schreibt_db_null(self):
        self._lege_belege_an(("rechnung.pdf", b"A"))
        datum = "2099-01-02"
        with (
            patch.object(backup, "DB_PATH", self.source),
            patch.object(backup, "get_connection", self._source_connection),
        ):
            result = backup.sichere_belege(datum)

        manifest = json.loads((self.source.parent / "backup" / f"manifest-{datum}.json").read_text())
        self.assertIsNone(manifest["db"])
        self.assertEqual(result["belege"][0]["datei"], "1/1_rechnung.pdf")

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
            [
                f"belege-{dt.date.today().isoformat()}",
                self.target.name,
                f"manifest-{dt.date.today().isoformat()}.json",
            ],
        )


if __name__ == "__main__":
    unittest.main()

