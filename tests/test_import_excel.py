"""Tests fuer den Excel-Kassabuch-Import (app/routers/import_excel.py).

Baut Test-Kassabuecher programmatisch mit openpyxl im Layout, das
_parse_kassabuch erwartet (siehe Docstring dort):
  Kopfzeile: Spalte A ('Dat.'), C (Text), D (Einnahmen), E (Ausgaben),
             ab Spalte L (Index KATEGORIE_SPALTE_AB=11) Kategorienamen.
  Erste Datenzeile: Kopfzeile-Index + 2 (eine Zeile wird uebersprungen).
  Fusszeile: 'BRUTTO...' o.ae. in Spalte C beendet das Blatt.
  Blaetter mit 'Jahres' im Namen werden uebersprungen.
"""
import datetime as dt
import io
import os
import tempfile
import unittest
from pathlib import Path

import openpyxl

TEST_DIR = tempfile.TemporaryDirectory(prefix="finanz-import-excel-")
os.environ["FINANZ_DB"] = str(Path(TEST_DIR.name) / "import-excel-test.db")

from app.db import get_connection, init_db
from app.routers.import_excel import import_excel

from starlette.datastructures import UploadFile


def _xlsx(sheets: dict[str, list[list]]) -> bytes:
    """Baut eine .xlsx-Datei aus {Blattname: Zeilen (Liste von Zellwerten)}."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, zeilen in sheets.items():
        ws = wb.create_sheet(title=name)
        for zeile in zeilen:
            ws.append(zeile)
    puffer = io.BytesIO()
    wb.save(puffer)
    return puffer.getvalue()


def _upload(inhalt: bytes, dateiname: str = "kassabuch.xlsx") -> UploadFile:
    return UploadFile(file=io.BytesIO(inhalt), filename=dateiname)


KOPFZEILE = [
    "Dat.", "Beleg", "Text", "Einnahmen", "Ausgaben",
    None, None, None, None, None, None,
    "Lebensmittel", "Sonstiges",
]
SUBHEADER = [None] * 13  # wird von _parse_kassabuch uebersprungen (kopf_idx + 1)


def _kassabuch_mit_daten() -> bytes:
    zeilen = [
        KOPFZEILE,
        SUBHEADER,
        # Ausgabe, volle Deckung durch eine Kategorie-Spalte (Lebensmittel).
        [dt.date(2026, 1, 5), "B1", "Wocheneinkauf", None, 45.50,
         None, None, None, None, None, None, 45.50, None],
        # Einnahme, volle Deckung durch eine andere Kategorie-Spalte (Sonstiges).
        [dt.date(2026, 1, 10), "B2", "Nebenverdienst", 1200.0, None,
         None, None, None, None, None, None, None, 1200.0],
        ["", "", "BRUTTO-EINNAHMEN", None, None],
    ]
    return _xlsx({"Jaenner": zeilen})


class ImportExcelApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        con = get_connection()
        try:
            con.execute("DELETE FROM buchungszeile")
            con.execute("DELETE FROM buchung")
            con.execute("DELETE FROM kategorie WHERE name IN "
                        "('Lebensmittel', 'Sonstiges')")
            con.commit()
            self.sparte_id = con.execute(
                "INSERT INTO sparte(name, typ) VALUES('Testsparte Excel', 'privat')"
            ).lastrowid
            con.commit()
        finally:
            con.close()

    def _import(self, rohdaten: bytes, modus: str, con):
        return import_excel(
            sparte_id=self.sparte_id, modus=modus,
            datei=_upload(rohdaten), con=con,
        )

    def test_pruefen_aendert_datenbank_nicht(self):
        con = get_connection()
        self.addCleanup(con.close)

        bericht = self._import(_kassabuch_mit_daten(), "pruefen", con)

        self.assertEqual(bericht["monate_mit_daten"], 1)
        self.assertEqual(bericht["buchungen_neu"], 2)
        self.assertEqual(bericht["eingespielt"], 0)
        anzahl = con.execute("SELECT COUNT(*) AS n FROM buchung "
                             "WHERE sparte_id = ?", (self.sparte_id,)).fetchone()["n"]
        self.assertEqual(anzahl, 0)

    def test_einspielen_legt_buchungen_an(self):
        con = get_connection()
        self.addCleanup(con.close)

        bericht = self._import(_kassabuch_mit_daten(), "einspielen", con)

        self.assertEqual(bericht["eingespielt"], 2)
        buchungen = con.execute(
            "SELECT b.typ, bz.betrag_cent FROM buchung b "
            "JOIN buchungszeile bz ON bz.buchung_id = b.id "
            "WHERE b.sparte_id = ? ORDER BY b.datum", (self.sparte_id,)
        ).fetchall()
        self.assertEqual(len(buchungen), 2)
        self.assertEqual(buchungen[0]["typ"], "ausgabe")
        self.assertEqual(buchungen[0]["betrag_cent"], 4550)
        self.assertEqual(buchungen[1]["typ"], "einnahme")
        self.assertEqual(buchungen[1]["betrag_cent"], 120000)
        bewegungen = con.execute("SELECT m.betrag_signed_cent FROM bewegung m JOIN bankkonto k ON k.id=m.konto_id WHERE k.sparte_id=? AND k.art='kassa' ORDER BY m.datum",(self.sparte_id,)).fetchall()
        self.assertEqual([-4550,120000],[r[0] for r in bewegungen])

    def test_dubletten_bei_wiederholtem_einspielen(self):
        con = get_connection()
        self.addCleanup(con.close)

        erster = self._import(_kassabuch_mit_daten(), "einspielen", con)
        self.assertEqual(erster["eingespielt"], 2)

        zweiter = self._import(_kassabuch_mit_daten(), "einspielen", con)
        self.assertEqual(zweiter["buchungen_neu"], 0)
        self.assertEqual(zweiter["duplikate"], 2)
        self.assertEqual(zweiter["eingespielt"], 0)

        anzahl = con.execute("SELECT COUNT(*) AS n FROM buchung "
                             "WHERE sparte_id = ?", (self.sparte_id,)).fetchone()["n"]
        self.assertEqual(anzahl, 2)

    def test_unbekannte_kategorien_werden_gemeldet(self):
        con = get_connection()
        self.addCleanup(con.close)

        bericht = self._import(_kassabuch_mit_daten(), "pruefen", con)

        self.assertEqual(bericht["neue_kategorien"], ["Lebensmittel", "Sonstiges"])

    def test_boesartiger_spaltenkopf_erzeugt_warnung_und_keine_kategorie(self):
        """F1: ein Spaltenkopf mit XSS-Payload darf keine Kategorie werden
        (die landet ungefiltert im Hinweistext der Uebersicht) - stattdessen
        Warnung und die Spalte wird ignoriert."""
        con = get_connection()
        self.addCleanup(con.close)

        payload = '<img src=x onerror=alert(1)>'
        kopfzeile = [
            "Dat.", "Beleg", "Text", "Einnahmen", "Ausgaben",
            None, None, None, None, None, None,
            payload, "Sonstiges",
        ]
        kassabuch = _xlsx({
            "Jaenner": [
                kopfzeile,
                SUBHEADER,
                [dt.date(2026, 1, 5), "B1", "Wocheneinkauf", None, 45.50,
                 None, None, None, None, None, None, 45.50, None],
            ]
        })

        bericht = self._import(kassabuch, "pruefen", con)

        self.assertNotIn(payload, bericht["neue_kategorien"])
        self.assertTrue(
            any("ungueltig" in w.lower() or "Spaltenkopf" in w for w in bericht["warnungen"]),
            bericht["warnungen"],
        )

        self._import(kassabuch, "einspielen", con)
        vorhanden = con.execute(
            "SELECT COUNT(*) AS n FROM kategorie WHERE name = ?", (payload,)
        ).fetchone()["n"]
        self.assertEqual(0, vorhanden)

    def test_leere_vorlage_erzeugt_warnung(self):
        """Aufgabe 1: eine Datei ohne jede Betragszeile darf nicht stillschweigend
        0 Buchungen und 0 Warnungen liefern."""
        con = get_connection()
        self.addCleanup(con.close)

        leere_vorlage = _xlsx({
            "Jaenner": [
                KOPFZEILE,
                SUBHEADER,
                # Direkt die Fusszeile - keine einzige Datenzeile mit Betrag.
                ["", "", "BRUTTO-EINNAHMEN", None, None],
            ]
        })

        bericht = self._import(leere_vorlage, "pruefen", con)

        self.assertEqual(bericht["monate_mit_daten"], 0)
        self.assertEqual(bericht["buchungen_neu"], 0)
        self.assertGreater(len(bericht["warnungen"]), 0)
        self.assertTrue(
            any("keine Buchungen" in w or "leer" in w.lower()
                for w in bericht["warnungen"])
        )

    def test_datei_ohne_kassabuch_layout_erzeugt_andere_warnung(self):
        """Kein Blatt hat eine erkennbare Kopfzeile -> eigener Hinweistext."""
        con = get_connection()
        self.addCleanup(con.close)

        keine_kopfzeile = _xlsx({"Blatt1": [["irgendwas", "hier", "steht"]]})

        bericht = self._import(keine_kopfzeile, "pruefen", con)

        self.assertEqual(bericht["buchungen_neu"], 0)
        self.assertGreater(len(bericht["warnungen"]), 0)
        self.assertTrue(
            any("Kassabuch" in w for w in bericht["warnungen"])
        )


if __name__ == "__main__":
    unittest.main()
