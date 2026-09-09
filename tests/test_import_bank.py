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


TEST_DIR = None
if not os.environ.get("FINANZ_DB"):
    TEST_DIR = tempfile.TemporaryDirectory(prefix="finanz-import-bank-")
    os.environ["FINANZ_DB"] = str(Path(TEST_DIR.name) / "import-bank-test.db")

from app.db import get_connection, init_db
from app.routers.import_bank import (
    UmsatzVerbuchenIn, dekodiere, erkenne_spalten, erkenne_trennzeichen,
    import_csv, parse_betrag_cent, parse_datum, verbuche_umsatz,
)


class ParserTest(unittest.TestCase):
    def test_parse_betrag_cent(self):
        self.assertEqual(-123456, parse_betrag_cent("-1.234,56"))
        self.assertEqual(123456, parse_betrag_cent("1234.56"))
        self.assertEqual(123456, parse_betrag_cent("1,234.56"))
        self.assertEqual(0, parse_betrag_cent("0,00"))
        with self.assertRaises(ValueError):
            parse_betrag_cent("abc")

    def test_parse_datum(self):
        self.assertEqual("2025-12-31", parse_datum("31.12.2025"))
        self.assertEqual("2025-12-31", parse_datum("2025-12-31"))
        self.assertEqual("2025-12-31", parse_datum("12/31/2025"))
        with self.assertRaises(ValueError):
            parse_datum("31.02.2025")

    def test_erkennung_und_utf16(self):
        text, kodierung = dekodiere("Datum,Betrag\n31.12.2025,\"1,00\"\n".encode("utf-16"))
        self.assertEqual("utf-16", kodierung)
        self.assertEqual(",", erkenne_trennzeichen(text))
        spalten = erkenne_spalten(["Eigener Kontoname", "Buchungsdatum", "Betrag", "Buchungs-Details", "Partnername", "Partner IBAN"])
        self.assertEqual({"datum": 1, "betrag": 2, "text": 3, "gegenpartei": 4, "iban": 5, "waehrung": None, "saldo": None}, spalten)


def _upload(inhalt: bytes, dateiname: str = "umsaetze.csv") -> UploadFile:
    return UploadFile(file=io.BytesIO(inhalt), filename=dateiname)


CSV_INHALT = (
    "Buchungstag;Betrag;Verwendungszweck;Beguenstigter\n"
    "01.03.2026;-1.234,56;Einkauf Supermarkt;Handelskette AG\n"
    "02.03.2026;2.500,00;Gehalt Maerz;Arbeitgeber GmbH\n"
).encode("utf-8-sig")

GEORGE_FIXTURE = Path(__file__).parent / "fixtures" / "george_2025_auszug.csv"


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

    def test_semikolon_beispiel_prueft_und_speichert_saldo(self):
        con = get_connection()
        self.addCleanup(con.close)
        ergebnis = import_csv(
            bankkonto_id=self.bankkonto_id,
            datei=_upload(Path("beispiele/bank_beispiel.csv").read_bytes()),
            con=con,
        )
        self.assertTrue(ergebnis["saldo_ok"])
        self.assertEqual(
            [350000, 265000, 252655, 245875, 247109],
            [row[0] for row in con.execute(
                "SELECT saldo_nachher_cent FROM bankumsatz ORDER BY datum"
            )],
        )

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

    def test_george_fixture_importiert_alle_zeilen_und_erkennt_spalten(self):
        con = get_connection()
        self.addCleanup(con.close)
        ergebnis = import_csv(bankkonto_id=self.bankkonto_id, datei=_upload(GEORGE_FIXTURE.read_bytes()), con=con)
        self.assertEqual(8, ergebnis["neu"])
        self.assertEqual("utf-16", ergebnis["erkannt"]["kodierung"])
        self.assertEqual(",", ergebnis["erkannt"]["trennzeichen"])
        self.assertEqual(8, ergebnis["erkannt"]["zeilen_gesamt"])
        self.assertEqual(0, len(ergebnis["erkannt"]["zeilen_ungueltig"]))
        row = con.execute("SELECT text, gegenpartei, iban_gegenpartei FROM bankumsatz ORDER BY id LIMIT 1").fetchone()
        self.assertEqual("Zahlung für Käsekuchen", row["text"])
        self.assertEqual("Fiktive Partnerin", row["gegenpartei"])
        self.assertEqual("DE00123456789012345678", row["iban_gegenpartei"])
        self.assertIsNone(ergebnis["saldo_ok"])
        self.assertIn("keine saldospalte", ergebnis["saldo_hinweis"].lower())

    def test_george_identische_zeilen_bleiben_zwei_und_reimport_ist_dubletten(self):
        con = get_connection()
        self.addCleanup(con.close)
        erste = import_csv(bankkonto_id=self.bankkonto_id, datei=_upload(GEORGE_FIXTURE.read_bytes()), con=con)
        zweite = import_csv(bankkonto_id=self.bankkonto_id, datei=_upload(GEORGE_FIXTURE.read_bytes()), con=con)
        self.assertEqual(8, erste["neu"])
        self.assertEqual(0, zweite["neu"])
        self.assertEqual(8, zweite["dubletten"])
        self.assertEqual(2, con.execute("SELECT COUNT(*) FROM bankumsatz WHERE text = 'Doppelte Testzahlung'").fetchone()[0])

    def test_alter_fingerabdruck_verhindert_neuen_umsatz(self):
        con = get_connection()
        self.addCleanup(con.close)
        import hashlib
        alter = hashlib.sha256(f"{self.bankkonto_id}|2025-12-31|100|Alte Testzahlung".encode()).hexdigest()
        con.execute("INSERT INTO bankumsatz(bankkonto_id, datum, betrag_cent, text, import_hash) VALUES(?,?,?,?,?)", (self.bankkonto_id, "2025-12-31", 100, "Alte Testzahlung", alter))
        con.commit()
        csv_inhalt = "Buchungsdatum,Betrag,Buchungs-Details\n31.12.2025,\"1,00\",Alte Testzahlung\n".encode("utf-16")
        self.assertEqual(0, import_csv(bankkonto_id=self.bankkonto_id, datei=_upload(csv_inhalt), con=con)["neu"])

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
