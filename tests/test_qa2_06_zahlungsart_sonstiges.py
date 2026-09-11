"""QA2-06: Buchungsliste-Filter "Zahlungsart" muss "Sonstiges" anbieten,
wie es beim Erfassen und im Bearbeiten-Dialog bereits moeglich ist -- sonst
lassen sich Buchungen mit zahlungsart='sonstiges' nicht gezielt filtern.
"""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "static-neu" / "index.html"


class ZahlungsartFilterTest(unittest.TestCase):
    def test_filter_zahlungsart_enthaelt_sonstiges(self):
        quelltext = INDEX_HTML.read_text(encoding="utf-8")
        start = quelltext.index('id="filter-zahlungsart"')
        ende = quelltext.index("</select>", start)
        block = quelltext[start:ende]
        self.assertIn('value="sonstiges"', block)
        self.assertIn('value="bar"', block)
        self.assertIn('value="bank"', block)
        self.assertIn('value="karte"', block)


if __name__ == "__main__":
    unittest.main()
