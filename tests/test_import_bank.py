"""Tests fuer den Bank-CSV-Import (app/routers/import_bank.py).

Deckt ab: erfolgreichen Import, Dublettenschutz, Verbuchen eines Umsatzes
inkl. automatisch gelernter Regel, und dass eine kaputte/leere CSV einen
verstaendlichen 4xx-Fehler liefert statt eines 500ers.
"""
import io
import os
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException
from starlette.datastructures import UploadFile


TEST_DIR = tempfile.TemporaryDirectory(prefix="finanz-import-bank-")
os.environ["FINANZ_DB"] = str(Path(TEST_DIR.name) / "import-bank-test.db")

from app.db import get_connection, init_db
from app.routers.import_bank import (
    UmsatzVerbuchenIn, import_csv, verbuche_umsatz,
)


def _upload(inhalt: bytes, dateiname: str = "umsaetze.csv") -> UploadFile:
    return UploadFile(file=io.BytesIO(inhalt), filename=dateiname)


CSV_INHALT = (
    "Buchungstag;Betrag;Verwendungszweck;Beguenstigter\n"
    "01.03.2026;-1.234,56;Einkauf Supermarkt;Handelskette AG\n"
    "02.03.2026;2.500,00;Gehalt Maerz;Arbeitgeber GmbH\n"
).encode("utf-8-sig")


class ImportBankApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        con = get_connection()
        try:
            con.execute("DELETE FROM regel")
            con.execute("DELETE FROM buchungszeile")
            con.execute("DELETE FROM buchung")
            con.execute("DELETE FROM bankumsatz")
            con.execute("DELETE FROM import_batch")
            con.execute("DELETE FROM bankkonto")
            con.commit()
            self.sparte_id = con.execute(
                "INSERT INTO sparte(name, typ) VALUES('Testsparte Bank', 'privat')"
            ).lastrowid
            self.kategorie_id = con.execute(
                "INSERT INTO kategorie(sparte_id, name, richtung) "
                "VALUES(?, 'Ausgaben Test', 'ausgabe')", (self.sparte_id,)
            ).lastrowid
            self.bankkonto_id = con.execute(
                "INSERT INTO bankkonto(name, sparte_id) VALUES(?, ?)",
                ("Testkonto", self.sparte_id),
            ).lastrowid
            con.commit()
        finally:
            con.close()

    def test_erfolgreicher_import_mehrerer_umsaetze(self):
        con = get_connection()
        self.addCleanup(con.close)

        ergebnis = import_csv(
            bankkonto_id=self.bankkonto_id, datei=_upload(CSV_INHALT), con=con,
        )

        self.assertEqual(ergebnis["neu"], 2)
        self.assertEqual(ergebnis["dubletten"], 0)
        self.assertEqual(ergebnis["gesamt"], 2)

        rows = con.execute(
            "SELECT datum, betrag_cent, text, gegenpartei FROM bankumsatz "
            "WHERE bankkonto_id = ? ORDER BY datum", (self.bankkonto_id,)
        ).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["datum"], "2026-03-01")
        self.assertEqual(rows[0]["betrag_cent"], -123456)
        self.assertEqual(rows[0]["gegenpartei"], "Handelskette AG")
        self.assertEqual(rows[1]["datum"], "2026-03-02")
        self.assertEqual(rows[1]["betrag_cent"], 250000)

    def test_dublettenschutz_bei_wiederholtem_import(self):
        con = get_connection()
        self.addCleanup(con.close)

        import_csv(bankkonto_id=self.bankkonto_id, datei=_upload(CSV_INHALT), con=con)
        zweiter = import_csv(
            bankkonto_id=self.bankkonto_id, datei=_upload(CSV_INHALT), con=con,
        )

        self.assertEqual(zweiter["neu"], 0)
        self.assertEqual(zweiter["dubletten"], 2)
        anzahl = con.execute(
            "SELECT COUNT(*) AS n FROM bankumsatz WHERE bankkonto_id = ?",
            (self.bankkonto_id,),
        ).fetchone()["n"]
        self.assertEqual(anzahl, 2)

    def test_verbuchen_erzeugt_buchung_und_lernt_regel(self):
        con = get_connection()
        self.addCleanup(con.close)
        import_csv(bankkonto_id=self.bankkonto_id, datei=_upload(CSV_INHALT), con=con)
        umsatz_id = con.execute(
            "SELECT id FROM bankumsatz WHERE gegenpartei = 'Handelskette AG'"
        ).fetchone()["id"]

        result = verbuche_umsatz(
            umsatz_id,
            UmsatzVerbuchenIn(
                sparte_id=self.sparte_id,
                kategorie_id=self.kategorie_id,
                typ="ausgabe",
            ),
            con,
        )

        self.assertEqual(result["typ"], "ausgabe")
        self.assertEqual(result["betrag_cent"], 123456)
        self.assertTrue(result["regel_angelegt"])

        buchung = con.execute(
            "SELECT sparte_id, typ, betrag_cent, buchungsstatus FROM buchung "
            "WHERE id = ?", (result["buchung_id"],),
        ).fetchone()
        self.assertEqual(buchung["sparte_id"], self.sparte_id)
        self.assertEqual(buchung["typ"], "ausgabe")
        self.assertEqual(buchung["betrag_cent"], 123456)
        self.assertEqual(buchung["buchungsstatus"], "zugeordnet")

        self.assertEqual(
            con.execute(
                "SELECT importstatus FROM bankumsatz WHERE id = ?", (umsatz_id,)
            ).fetchone()["importstatus"],
            "verbucht",
        )

        regeln = con.execute("SELECT * FROM regel").fetchall()
        self.assertEqual(len(regeln), 1)
        self.assertEqual(regeln[0]["bedingung_text"], "handelskette ag")
        self.assertEqual(regeln[0]["ziel_kategorie_id"], self.kategorie_id)

    def test_kaputte_csv_liefert_4xx_statt_500(self):
        con = get_connection()
        self.addCleanup(con.close)

        with self.assertRaises(HTTPException) as ctx:
            import_csv(bankkonto_id=self.bankkonto_id, datei=_upload(b""), con=con)
        self.assertTrue(400 <= ctx.exception.status_code < 500)

        with self.assertRaises(HTTPException) as ctx:
            import_csv(
                bankkonto_id=self.bankkonto_id,
                datei=_upload("Nur;Kopfzeile;Ohne;Daten\n".encode("utf-8")),
                con=con,
            )
        self.assertTrue(400 <= ctx.exception.status_code < 500)

        # Ohne erkennbare Pflichtspalten (Datum/Betrag/Text) -> ebenfalls 4xx.
        with self.assertRaises(HTTPException) as ctx:
            import_csv(
                bankkonto_id=self.bankkonto_id,
                datei=_upload("A;B;C\n1;2;3\n".encode("utf-8")),
                con=con,
            )
        self.assertTrue(400 <= ctx.exception.status_code < 500)


if __name__ == "__main__":
    unittest.main()
