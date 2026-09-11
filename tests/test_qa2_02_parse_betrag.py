"""QA2-02: parseBetrag() muss Dezimalpunkt/-komma korrekt von Tausendertrennzeichen
unterscheiden (Befund: "12.50" wurde bisher zu 1250 statt 12,50 verfaelscht).

Fuehrt den Node-Test tests/js/parse_betrag.test.mjs per subprocess aus
(Muster wie ErfassenJsSyntaxTest in test_p40_erfassen.py).
"""
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class ParseBetragJsTest(unittest.TestCase):
    def test_node_check_format_js(self):
        pfad = ROOT / "static-neu" / "format.js"
        ergebnis = subprocess.run(["node", "--check", str(pfad)], capture_output=True, text=True)
        self.assertEqual(0, ergebnis.returncode, ergebnis.stderr)

    def test_parse_betrag_faelle(self):
        pfad = ROOT / "tests" / "js" / "parse_betrag.test.mjs"
        ergebnis = subprocess.run(["node", str(pfad)], capture_output=True, text=True)
        self.assertEqual(0, ergebnis.returncode, ergebnis.stdout + ergebnis.stderr)


if __name__ == "__main__":
    unittest.main()
