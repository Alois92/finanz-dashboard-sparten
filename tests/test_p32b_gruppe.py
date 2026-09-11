"""P32b: #/sparte/gruppe-<id> griff bisher nur, wenn im Kopf "Alle Sparten" stand
(gruppeId wurde nur berechnet, solange state.sparteId leer war). Jetzt gewinnt ein
expliziter Gruppen-Hash: beim Betreten räumt die Seite state.sparteId/state.filter.
sparteId/localStorage('neu-sparte') und löst wie waehleSparte() ein hashchange aus,
damit Kopf-Select und Sidebar "Alle Sparten" zeigen; wählt der Nutzer danach im Kopf
eine Sparte, entfernt die Seite beim nächsten Render das Gruppen-Suffix wieder.

Textprüfung wie die bestehenden statischen Tests (tests/test_static_neu_sparte.py):
prüft den Quelltext von static-neu/pages/sparte.js, keine Browser-/DOM-Ausführung.
"""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPARTE_JS = ROOT / "static-neu" / "pages" / "sparte.js"


class GruppenHashGewinntTest(unittest.TestCase):
    def setUp(self):
        self.text = SPARTE_JS.read_text(encoding="utf-8")

    def test_render_berechnet_gruppeid_unabhaengig_von_sparteid(self):
        # Die alte, fehlerhafte Bedingung "!state.sparteId ? parseGruppeId(suffix) : null"
        # darf nicht mehr vorkommen - sie ist der Grund, warum die Gruppe bei gesetzter
        # Sparte ignoriert wurde.
        self.assertNotIn("!state.sparteId ? parseGruppeId(suffix) : null", self.text)
        self.assertIn("const gruppeId = parseGruppeId(suffix);", self.text)

    def test_gruppen_zustand_verfolgt_den_zuletzt_betretenen_hash(self):
        self.assertIn("gruppenZustand", self.text)

    def test_betreten_der_gruppe_raeumt_sparte_und_loest_hashchange_aus(self):
        # Beim Betreten (state.sparteId noch gesetzt) wird die Sparte in state,
        # state.filter und localStorage geräumt und ein hashchange ausgelöst - wie in
        # waehleSparte(), damit Kopf-Select und Sidebar synchron "Alle Sparten" zeigen.
        self.assertIn("state.sparteId = '';", self.text)
        self.assertIn("if (state.filter) state.filter.sparteId = '';", self.text)
        self.assertIn("localStorage.setItem('neu-sparte', '');", self.text)
        self.assertIn("window.dispatchEvent(new Event('hashchange'));", self.text)

    def test_nachtraegliche_kopf_sparte_entfernt_gruppen_suffix(self):
        # Wählt der Nutzer danach im Kopf eine Sparte (state.sparteId erneut gesetzt,
        # gleicher Gruppen-Hash), muss die Seite beim nächsten Render das
        # Gruppen-Suffix aus dem Hash entfernen (zurück auf '#/sparte').
        self.assertIn("location.hash = '#/sparte';", self.text)

    def test_node_syntax(self):
        import subprocess
        import sys
        node = None
        for name in ("node", "node.exe"):
            found = subprocess.run(["where" if sys.platform == "win32" else "which", name],
                                    capture_output=True, text=True)
            if found.returncode == 0:
                node = name
                break
        if node is None:
            self.skipTest("node ist in dieser Umgebung nicht verfuegbar")
        result = subprocess.run([node, "--check", str(SPARTE_JS)],
                                 capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
