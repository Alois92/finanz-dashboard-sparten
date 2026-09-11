"""QA1-06: static-neu/index.html soll ein Daten-URI-Favicon setzen, damit der
Browser keine (im Serverlog als 404 auftauchende) Anfrage auf /favicon.ico
mehr schickt.
"""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "static-neu" / "index.html"


class FaviconTest(unittest.TestCase):
    def test_icon_link_vorhanden(self):
        quelltext = INDEX_HTML.read_text(encoding="utf-8")
        self.assertIn('<link rel="icon" href="data:,">', quelltext)


if __name__ == "__main__":
    unittest.main()
