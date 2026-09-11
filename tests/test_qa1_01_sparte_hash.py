"""QA1-01: Sparten-Wechsel muss die ID im Hash abbilden (#/sparte/<id>),
damit die URL teilbar bleibt und die Zurueck-Taste zwischen zuvor
besuchten Sparten wechseln kann. Der Gruppen-Hash (#/sparte/gruppe-<id>,
P32b) muss dabei weiter Vorrang behalten.

Da es fuer das Vanilla-JS-Frontend keine DOM-Testumgebung (jsdom o.ae.) im
Projekt gibt, prueft dieser Test den Quelltext direkt (gleiches Muster wie
tests/test_qa2_04_client_request_id.py).
"""
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPARTE_JS = ROOT / "static-neu" / "pages" / "sparte.js"
UEBERSICHT_JS = ROOT / "static-neu" / "pages" / "uebersicht.js"
APP_JS = ROOT / "static-neu" / "app.js"


class SparteHashJsTest(unittest.TestCase):
    def setUp(self):
        self.sparte = SPARTE_JS.read_text(encoding="utf-8")
        self.uebersicht = UEBERSICHT_JS.read_text(encoding="utf-8")
        self.app = APP_JS.read_text(encoding="utf-8")

    def test_node_check_geaenderte_dateien(self):
        for pfad in (SPARTE_JS, UEBERSICHT_JS, APP_JS):
            ergebnis = subprocess.run(["node", "--check", str(pfad)], capture_output=True, text=True)
            self.assertEqual(0, ergebnis.returncode, f"{pfad}: {ergebnis.stderr}")

    def test_sync_normalisiert_hash_nicht_mehr_zurueck(self):
        # syncSparteAusHash darf den Hash nicht mehr auf "#/sparte" ohne ID kuerzen.
        start = self.sparte.index("function syncSparteAusHash")
        ende = self.sparte.index("\n}\n", start)
        block = self.sparte[start:ende]
        self.assertNotIn("location.hash", block)

    def test_waehle_sparte_schreibt_id_in_hash(self):
        start = self.sparte.index("function waehleSparte")
        ende = self.sparte.index("\n}\n", start)
        block = self.sparte[start:ende]
        self.assertIn("'#/sparte/' + id", block)

    def test_uebersicht_go_sparte_schreibt_id_in_hash(self):
        start = self.uebersicht.index("function goSparte")
        ende = self.uebersicht.index("\n}\n", start)
        block = self.uebersicht[start:ende]
        self.assertIn("'#/sparte/' + state.sparteId", block)

    def test_render_zieht_bekannte_sparte_in_hash_nach(self):
        self.assertIn("location.hash = '#/sparte/' + sparteId", self.sparte)

    def test_gruppen_hash_bleibt_vorrangig(self):
        # P32b-Verhalten (Gruppen-Hash gewinnt, Kopf-Wahl raeumt ihn) darf nicht entfernt sein.
        self.assertIn("gruppenZustand.suffix = null;\n      location.hash = '#/sparte';", self.sparte)
        self.assertIn("parseGruppeId(suffix)", self.sparte)

    def test_set_filter_schreibt_hash_nur_auf_sparte_seite(self):
        start = self.app.index("function setFilter")
        ende = self.app.index("\n}\n", start)
        block = self.app[start:ende]
        self.assertIn("state.route==='sparte'", block)
        self.assertIn("#/sparte/${state.sparteId}", block)


if __name__ == "__main__":
    unittest.main()
