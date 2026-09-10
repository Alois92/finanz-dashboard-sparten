"""N5: Tagesendanker und Saldo-Ketten in beiden CSV-Sortierrichtungen."""
import io
import sqlite3
import tempfile
import unittest
from pathlib import Path

from starlette.datastructures import UploadFile

from app import db
from app.konten import kontostand
from app.routers.import_bank import import_csv


class ImportankerTest(unittest.TestCase):
    def setUp(self):
        tempdir = tempfile.TemporaryDirectory(prefix="finanz-importanker-")
        self.addCleanup(tempdir.cleanup)
        self.con = sqlite3.connect(Path(tempdir.name) / "test.db")
        self.addCleanup(self.con.close)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys=ON")
        self.con.executescript(db.SCHEMA.read_text(encoding="utf-8"))
        self.con.executescript(db.SEED.read_text(encoding="utf-8"))
        self.zeilen = (Path(__file__).parent / "fixtures" / "saldo_absteigend.csv").read_text(encoding="utf-8").splitlines()

    def konto(self):
        return self.con.execute("INSERT INTO bankkonto(name) VALUES('N5-Test')").lastrowid

    def importieren(self, konto_id, zeilen, dateiname="saldo.csv"):
        return import_csv(
            bankkonto_id=konto_id, con=self.con,
            datei=UploadFile(filename=dateiname, file=io.BytesIO(
                ("\n".join(zeilen) + "\n").encode("utf-8"))),
        )

    def test_anker_ist_tagesendsaldo_in_beiden_richtungen(self):
        for absteigend in (True, False):
            with self.subTest(absteigend=absteigend):
                konto_id = self.konto()
                zeilen = self.zeilen if absteigend else self.zeilen[:1] + self.zeilen[:0:-1]
                self.importieren(konto_id, zeilen)
                stand = kontostand(self.con, konto_id, "2026-03-02")
                self.assertEqual(11500, stand["stand_cent"])
                self.assertEqual("2026-03-02", stand["anker"]["stichtag"])
                self.assertEqual(0, stand["bewegungen_seit_anker"])

    def test_saldokette_in_beiden_richtungen_auch_an_einem_tag(self):
        for nur_ein_tag in (False, True):
            for absteigend in (True, False):
                with self.subTest(nur_ein_tag=nur_ein_tag, absteigend=absteigend):
                    daten = self.zeilen[1:3] if nur_ein_tag else self.zeilen[1:]
                    if not absteigend:
                        daten = daten[::-1]
                    konto_id = self.konto()
                    result = self.importieren(konto_id, self.zeilen[:1] + daten)
                    self.assertIs(True, result["saldo_ok"])
                    self.assertIsNone(result["saldo_hinweis"])
                    self.assertEqual(11500, kontostand(self.con, konto_id, "2026-03-02")["stand_cent"])

    def test_reimport_korrigiert_anker_auch_bei_nur_dubletten(self):
        konto_id = self.konto()
        zeilen = self.zeilen[:1] + self.zeilen[:0:-1]
        self.importieren(konto_id, zeilen)
        anker_id = self.con.execute("SELECT id FROM kontostand_anker WHERE konto_id=?", (konto_id,)).fetchone()[0]
        korrigiert = [z.replace("100,00", "200,00").replace("120,00", "220,00").replace("115,00", "215,00") for z in zeilen]
        result = self.importieren(konto_id, korrigiert, "korrigiert.csv")
        self.assertEqual(0, result["neu"])
        self.assertEqual(3, result["dubletten"])
        self.assertIs(True, result["saldo_ok"])
        anker = self.con.execute("SELECT * FROM kontostand_anker WHERE konto_id=?", (konto_id,)).fetchall()
        self.assertEqual(1, len(anker))
        self.assertEqual(anker_id, anker[0]["id"])
        self.assertEqual(21500, anker[0]["saldo_cent"])
        self.assertIn("korrigiert.csv", anker[0]["notiz"])

    def test_echte_saldoluecke_bleibt_in_beiden_richtungen_sichtbar(self):
        for absteigend in (True, False):
            with self.subTest(absteigend=absteigend):
                zeilen = [z.replace("100,00", "99,00") for z in self.zeilen]
                if not absteigend:
                    zeilen = zeilen[:1] + zeilen[:0:-1]
                result = self.importieren(self.konto(), zeilen)
                self.assertIs(False, result["saldo_ok"])
                self.assertIn("Saldo-Sprung in CSV-Zeile", result["saldo_hinweis"])
