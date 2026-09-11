"""P60b: zwei kleine Schulden aus der P60-Abnahme.

1. GET /export/bericht verlangte jahr auch bei profil_id, obwohl der Profil-Zweig
   jahr inhaltlich gar nicht braucht (er nimmt das Jahr aus dem Profil). jahr ist
   jetzt nur noch ohne profil_id Pflicht.
2. Der Ausschluss-Dialog in static-neu/pages/export.js holte Buchungen nur mit
   Limit 1000 auf einer einzigen Seite; er geht jetzt seitenweise über den Cursor
   von GET /api/buchungen (Muster aus pages/buchungen.js), bis naechster_cursor
   leer ist.

tests/test_p60_export.py bleibt unveraendert (dokumentiert dort weiterhin die alte
Lücke als Kommentar/Testname, siehe Bericht).
"""
import pathlib
import subprocess
import sys
import unittest

import test_bereiche

ROOT = pathlib.Path(__file__).resolve().parents[1]


class ExportBerichtOhneJahrTest(unittest.TestCase):
    setUp = test_bereiche.BereicheTest.setUp
    request = test_bereiche.BereicheTest.request

    def _profil(self, sparte_id, jahr=2026):
        status, profil = self.request(
            "GET", f"/api/export/profil?bereich_id=1&sparte_id={sparte_id}&jahr={jahr}")
        self.assertEqual(200, status, profil)
        return profil

    def test_bericht_mit_profil_id_ohne_jahr_liefert_200(self):
        profil = self._profil(self.haupt)
        status, body = self.request(
            "GET", f"/export/bericht?bereich_id=1&profil_id={profil['id']}")
        self.assertEqual(200, status, body)
        text = body.decode("utf-8") if isinstance(body, (bytes, bytearray)) else body
        self.assertIn("Export-Profil", text)

    def test_bericht_mit_profil_id_und_jahr_bleibt_unveraendert_200(self):
        # jahr wird von export.js weiterhin mitgeschickt (siehe pages/export.js); ein
        # gleichzeitig gesetztes jahr darf den profil_id-Zweig nicht stoeren.
        profil = self._profil(self.haupt)
        status, body = self.request(
            "GET", f"/export/bericht?bereich_id=1&profil_id={profil['id']}&jahr=2026")
        self.assertEqual(200, status, body)

    def test_bericht_ohne_profil_id_und_ohne_jahr_bleibt_400(self):
        status, ergebnis = self.request("GET", "/export/bericht?bereich_id=1")
        self.assertEqual(400, status, ergebnis)
        self.assertIn("jahr", ergebnis.get("detail", ""))

    def test_bericht_ohne_profil_id_mit_ungueltigem_jahr_bleibt_400(self):
        status, ergebnis = self.request("GET", "/export/bericht?bereich_id=1&jahr=abcd")
        self.assertEqual(400, status, ergebnis)


class ExportAusschlussDialogSeitenweiseTest(unittest.TestCase):
    """Der Ausschluss-Dialog darf nicht mehr bei Limit 1000/einer Seite abbrechen."""

    def test_export_js_geht_seitenweise_ueber_den_cursor(self):
        text = (ROOT / "static-neu" / "pages" / "export.js").read_text(encoding="utf-8")
        self.assertIn("naechster_cursor", text)
        self.assertIn("while (cursor)", text)
        # Die alte Ein-Seiten-Grenze (fixes Limit 1000, keine Schleife) darf nicht mehr
        # vorkommen, insbesondere nicht mehr als Text "1000 Zeilen" im Dialog.
        self.assertNotIn("limit: 1000", text)
        self.assertNotIn("1000 Zeilen", text)

    def test_node_syntax(self):
        node = None
        for name in ("node", "node.exe"):
            found = subprocess.run(["where" if sys.platform == "win32" else "which", name],
                                    capture_output=True, text=True)
            if found.returncode == 0:
                node = name
                break
        if node is None:
            self.skipTest("node ist in dieser Umgebung nicht verfuegbar")
        result = subprocess.run([node, "--check", str(ROOT / "static-neu/pages/export.js")],
                                 capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)


class BuchungenSeitenweiseUeberCursorTest(unittest.TestCase):
    """Bestaetigt, dass GET /api/buchungen selbst bei kleinem Limit mehrere Seiten
    liefert und die letzte Seite naechster_cursor=None zurueckgibt - genau das Muster,
    dem export.js jetzt folgt."""
    setUp = test_bereiche.BereicheTest.setUp
    request = test_bereiche.BereicheTest.request

    def test_zwei_seiten_bei_kleinem_limit(self):
        kategorie_id = self.con.execute(
            "INSERT INTO kategorie(sparte_id,name,richtung) VALUES(?,?,?)",
            (self.haupt, "P60b-Kategorie", "ausgabe")).lastrowid
        for i in range(5):
            bid = self.con.execute(
                "INSERT INTO buchung(sparte_id,datum,typ,text) VALUES(?,?,?,?)",
                (self.haupt, f"2026-01-{i + 1:02d}", "ausgabe", f"P60b-{i}")).lastrowid
            self.con.execute(
                "INSERT INTO buchungszeile(buchung_id,kategorie_id,betrag_cent) VALUES(?,?,?)",
                (bid, kategorie_id, 100 + i))
        self.con.commit()

        gesehen = []
        cursor = None
        seiten = 0
        while True:
            url = f"/api/buchungen?bereich_id=1&jahr=2026&sparte_id={self.haupt}&limit=2"
            if cursor:
                url += f"&cursor={cursor}"
            status, daten = self.request("GET", url)
            self.assertEqual(200, status, daten)
            gesehen.extend(b["id"] for b in daten["buchungen"])
            cursor = daten["naechster_cursor"]
            seiten += 1
            if not cursor:
                break
            self.assertLess(seiten, 20, "Schleife sollte terminieren")
        # 5 neue plus 1 aus dem Setup-Fixture der Sparte "haupt".
        self.assertEqual(6, len(set(gesehen)))
        self.assertGreater(seiten, 1, "bei Limit 2 und 6 Buchungen sollten mehrere Seiten noetig sein")


if __name__ == "__main__":
    unittest.main()
