import os
import tempfile
import unittest
from pathlib import Path


TEST_DIR = tempfile.TemporaryDirectory(prefix="finanz-schnellerfassung-")
os.environ["FINANZ_DB"] = str(Path(TEST_DIR.name) / "schnellerfassung-test.db")

from app.db import get_connection, init_db
from app.routers.schnellerfassung import ParseIn, parse_mehrere, parse_text


class SammeltextErfassungTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def test_mehrere_positionen_durch_komma_getrennt(self):
        con = get_connection()
        self.addCleanup(con.close)
        result = parse_mehrere(
            ParseIn(text="Essen 5, Einkaufen 18, Kino 27"), con,
        )
        eintraege = result["eintraege"]
        self.assertEqual(3, len(eintraege))
        self.assertEqual([500, 1800, 2700], [e["betrag_cent"] for e in eintraege])

    def test_dezimalkomma_bleibt_beim_splitten_erhalten(self):
        con = get_connection()
        self.addCleanup(con.close)
        result = parse_mehrere(
            ParseIn(text="Diesel 82,30; Kino 12"), con,
        )
        eintraege = result["eintraege"]
        self.assertEqual(2, len(eintraege))
        self.assertEqual(8230, eintraege[0]["betrag_cent"])
        self.assertEqual(1200, eintraege[1]["betrag_cent"])

    def test_mehrzeiliger_text_wird_je_zeile_geparst(self):
        con = get_connection()
        self.addCleanup(con.close)
        result = parse_mehrere(
            ParseIn(text="Essen 5\nEinkaufen 18\nKino 27"), con,
        )
        eintraege = result["eintraege"]
        self.assertEqual(3, len(eintraege))
        self.assertEqual([500, 1800, 2700], [e["betrag_cent"] for e in eintraege])

    def test_parse_verhaelt_sich_unveraendert(self):
        con = get_connection()
        self.addCleanup(con.close)
        vorschlag = parse_text(ParseIn(text="gestern Diesel 82,30 Hof"), con)
        self.assertEqual(8230, vorschlag["betrag_cent"])
        self.assertEqual("ausgabe", vorschlag["typ"])


if __name__ == "__main__":
    unittest.main()
