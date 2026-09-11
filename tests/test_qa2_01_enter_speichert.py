"""QA2-01: Enter im Schnellerfassungs-Textfeld muss direkt speichern
(Shift+Enter bleibt ein Zeilenumbruch), P40-Vorgabe.

Quelltextpruefung wie bei den anderen JS-Befunden dieser Runde, da keine
DOM-Testumgebung im Projekt vorhanden ist.
"""
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
ERFASSEN_JS = ROOT / "static-neu" / "pages" / "erfassen.js"


class EnterSpeichertTest(unittest.TestCase):
    def setUp(self):
        self.quelltext = ERFASSEN_JS.read_text(encoding="utf-8")

    def test_node_check(self):
        ergebnis = subprocess.run(["node", "--check", str(ERFASSEN_JS)], capture_output=True, text=True)
        self.assertEqual(0, ergebnis.returncode, ergebnis.stderr)

    def test_textarea_hat_enter_handler(self):
        start = self.quelltext.index("textArea.addEventListener('keydown'")
        ende = self.quelltext.index("});", start)
        block = self.quelltext[start:ende]
        self.assertIn("e.key === 'Enter'", block)
        self.assertIn("!e.shiftKey", block)
        self.assertIn("form.requestSubmit()", block)
        self.assertIn("e.preventDefault()", block)


if __name__ == "__main__":
    unittest.main()
