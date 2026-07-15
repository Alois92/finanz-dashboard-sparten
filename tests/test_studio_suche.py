import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class StudioSucheTest(unittest.TestCase):
    def test_suchfeld_nutzt_server_suche_mit_debounce_und_normale_leerliste(self):
        app_js = (ROOT / "static-studio" / "app.js").read_text(encoding="utf-8")
        index_html = (ROOT / "static-studio" / "index.html").read_text(encoding="utf-8")

        self.assertIn('id="l-suche"', index_html)
        self.assertIn("Buchungstext, Notiz oder Kontakt", index_html)
        self.assertIn('"/buchungen/suche?q=" + encodeURIComponent(suche)', app_js)
        self.assertIn('"/buchungen?" + filterQuery()', app_js)
        self.assertIn("setTimeout(ladeBuchungen, 300)", app_js)


if __name__ == "__main__":
    unittest.main()

