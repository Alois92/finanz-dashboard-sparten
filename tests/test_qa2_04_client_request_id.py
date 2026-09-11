"""QA2-04: client_request_id im Erfassen-Formular muss ueber Wiederholungen
stabil bleiben (nicht bei jedem Speichern-Klick neu erzeugt werden), damit
die serverseitige Dedup-Pruefung nach einem Netzwerkfehler/Retry greift.

Da es fuer das Vanilla-JS-Frontend keine DOM-Testumgebung (jsdom o.ae.) im
Projekt gibt, prueft dieser Test den Quelltext direkt: der submit-Handler
darf keine eigene crypto.randomUUID() mehr erzeugen, sondern muss die einmal
in M.requestId abgelegte id verwenden.
"""
import pathlib
import re
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
ERFASSEN_JS = ROOT / "static-neu" / "pages" / "erfassen.js"


class ClientRequestIdStabilTest(unittest.TestCase):
    def setUp(self):
        self.quelltext = ERFASSEN_JS.read_text(encoding="utf-8")

    def test_node_check_erfassen_js(self):
        ergebnis = subprocess.run(["node", "--check", str(ERFASSEN_JS)], capture_output=True, text=True)
        self.assertEqual(0, ergebnis.returncode, ergebnis.stderr)

    def test_payload_verwendet_gemerkte_request_id(self):
        self.assertIn("client_request_id: M.requestId", self.quelltext)

    def test_submit_handler_erzeugt_keine_neue_id(self):
        start = self.quelltext.index("form.addEventListener('submit'")
        ende = self.quelltext.index("\n  });\n", start)
        submit_block = self.quelltext[start:ende]
        self.assertNotIn("crypto.randomUUID()", submit_block,
                          "Der submit-Handler darf client_request_id nicht neu erzeugen, "
                          "sonst erkennt der Server einen Retry nicht als Wiederholung.")

    def test_neue_id_bei_formularaufbau_und_reset(self):
        # Einmal beim Aufbau des Formulars (render) und einmal nach erfolgreichem
        # Speichern/Zuruecksetzen (formularZuruecksetzen) soll eine neue id erzeugt werden.
        treffer = re.findall(r"M\.requestId\s*=\s*crypto\.randomUUID\(\)", self.quelltext)
        self.assertEqual(2, len(treffer), self.quelltext)


if __name__ == "__main__":
    unittest.main()
