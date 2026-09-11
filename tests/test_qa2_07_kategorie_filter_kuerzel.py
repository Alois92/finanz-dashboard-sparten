"""QA2-07: Kategorie-Filter soll gleichnamige Kategorien verschiedener
Sparten mit Sparten-Kuerzel kennzeichnen, wenn "Alle Sparten" gewaehlt ist.

Quelltextpruefung von drawKategorieFilter() in static-neu/app.js, da keine
DOM-Testumgebung im Projekt vorhanden ist.
"""
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP_JS = ROOT / "static-neu" / "app.js"


class KategorieFilterKuerzelTest(unittest.TestCase):
    def setUp(self):
        self.quelltext = APP_JS.read_text(encoding="utf-8")
        start = self.quelltext.index("async function drawKategorieFilter")
        ende = self.quelltext.index("\n}\n", start)
        self.block = self.quelltext[start:ende]

    def test_node_check(self):
        ergebnis = subprocess.run(["node", "--check", str(APP_JS)], capture_output=True, text=True)
        self.assertEqual(0, ergebnis.returncode, ergebnis.stderr)

    def test_dubletten_werden_gezaehlt(self):
        self.assertIn("anzahlProName", self.block)

    def test_kuerzel_nur_ohne_sparten_filter(self):
        self.assertIn("if(state.sparteId||", self.block)

    def test_kuerzel_aus_sparte_id_aufgeloest(self):
        self.assertIn("state.sparten.find(s=>s.id===k.sparte_id)", self.block)


if __name__ == "__main__":
    unittest.main()
