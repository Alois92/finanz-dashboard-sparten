"""P43: Foto-Übernahme als Buchung (Split über mehrere Positionen).

Ollama wird nie echt aufgerufen: Aufträge werden direkt mit status='fertig'
und festem ergebnis_json in die Wegwerf-DB geschrieben (app/auswertung.py
bleibt unangetastet). Läuft über die echte ASGI-Anwendung wie test_bereiche.py."""
import json
import pathlib
import subprocess
import unittest

import test_bereiche as bereiche_tests

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC = ROOT / "static-neu" / "pages"


class P43FotoTest(unittest.TestCase):
    setUp = bereiche_tests.BereicheTest.setUp
    request = bereiche_tests.BereicheTest.request

    def kategorie(self, sparte_id, name, richtung="ausgabe"):
        kid = self.con.execute(
            "INSERT INTO kategorie(sparte_id, name, richtung) VALUES(?, ?, ?)",
            (sparte_id, name, richtung),
        ).lastrowid
        self.con.commit()
        return kid

    def beleg(self, sparte_id, dateiname="rechnung.jpg"):
        bid = self.con.execute(
            "INSERT INTO beleg(sparte_id, dateiname, pfad) VALUES(?, ?, ?)",
            (sparte_id, dateiname, "nicht-vorhanden.jpg"),
        ).lastrowid
        self.con.commit()
        return bid

    def auftrag(self, beleg_id, status="fertig", ergebnis=None):
        aid = self.con.execute(
            "INSERT INTO beleg_auswertung(beleg_id, status, ergebnis_json) VALUES(?, ?, ?)",
            (beleg_id, status, json.dumps(ergebnis) if ergebnis is not None else None),
        ).lastrowid
        self.con.commit()
        return aid

    def _ergebnis(self):
        return {"haendler": "Testmarkt", "datum": "2026-08-01",
                "positionen": [{"text": "Brot", "betrag_cent": 300, "mwst_prozent": 10},
                               {"text": "Milch", "betrag_cent": 150, "mwst_prozent": 10}],
                "gesamt_cent": 450}

    # ---- Frontend-Syntax ----

    def test_belege_und_erfassen_js_haben_gueltige_syntax(self):
        for datei in (STATIC / "belege.js", STATIC / "erfassen.js"):
            result = subprocess.run(["node", "--check", str(datei)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, f"{datei}: {result.stderr}")

    # ---- POST .../uebernehmen ----

    def test_uebernehmen_zwei_positionen_erzeugt_split_buchung(self):
        kat1 = self.kategorie(self.haupt, "P43-Lebensmittel")
        kat2 = self.kategorie(self.haupt, "P43-Getraenke")
        beleg_id = self.beleg(self.haupt)
        auftrag_id = self.auftrag(beleg_id, ergebnis=self._ergebnis())

        status, res = self.request("POST", f"/api/beleg-auswertungen/{auftrag_id}/uebernehmen", {
            "sparte_id": self.haupt, "datum": "2026-08-01",
            "positionen": [
                {"text": "Brot", "betrag_cent": 300, "kategorie_id": kat1},
                {"text": "Milch", "betrag_cent": 150, "kategorie_id": kat2},
            ],
        })
        self.assertEqual(201, status, res)
        self.assertIn("buchung_id", res)
        self.assertIn("version", res)

        zeilen = self.con.execute(
            "SELECT betrag_cent FROM buchungszeile WHERE buchung_id = ?", (res["buchung_id"],)
        ).fetchall()
        self.assertEqual(2, len(zeilen))
        self.assertEqual(450, sum(z["betrag_cent"] for z in zeilen))

        verknuepft = self.con.execute(
            "SELECT 1 FROM buchung_beleg WHERE buchung_id = ? AND beleg_id = ?",
            (res["buchung_id"], beleg_id),
        ).fetchone()
        self.assertIsNotNone(verknuepft)

        auftrag_status = self.con.execute(
            "SELECT status FROM beleg_auswertung WHERE id = ?", (auftrag_id,)
        ).fetchone()["status"]
        self.assertEqual("verbucht", auftrag_status)

    def test_uebernehmen_ohne_status_fertig_liefert_409(self):
        kat1 = self.kategorie(self.haupt, "P43-Laufend")
        beleg_id = self.beleg(self.haupt)
        auftrag_id = self.auftrag(beleg_id, status="laeuft", ergebnis=self._ergebnis())

        status, res = self.request("POST", f"/api/beleg-auswertungen/{auftrag_id}/uebernehmen", {
            "sparte_id": self.haupt,
            "positionen": [{"text": "Brot", "betrag_cent": 300, "kategorie_id": kat1}],
        })
        self.assertEqual(409, status, res)

    def test_uebernehmen_sparte_aus_anderem_bereich_liefert_404(self):
        kat_verein = self.kategorien[self.verein]
        beleg_id = self.beleg(self.haupt)
        auftrag_id = self.auftrag(beleg_id, ergebnis=self._ergebnis())

        status, res = self.request("POST", f"/api/beleg-auswertungen/{auftrag_id}/uebernehmen", {
            "sparte_id": self.verein,
            "positionen": [{"text": "Brot", "betrag_cent": 300, "kategorie_id": kat_verein}],
        })
        self.assertEqual(404, status, res)

    def test_client_request_id_dedupe(self):
        kat1 = self.kategorie(self.haupt, "P43-Dedupe")
        beleg_id = self.beleg(self.haupt)
        auftrag_id = self.auftrag(beleg_id, ergebnis=self._ergebnis())
        payload = {
            "sparte_id": self.haupt,
            "positionen": [{"text": "Brot", "betrag_cent": 300, "kategorie_id": kat1}],
            "client_request_id": "p43-test-dedupe-1",
        }

        status1, res1 = self.request("POST", f"/api/beleg-auswertungen/{auftrag_id}/uebernehmen", payload)
        self.assertEqual(201, status1, res1)

        status2, res2 = self.request("POST", f"/api/beleg-auswertungen/{auftrag_id}/uebernehmen", payload)
        self.assertEqual(200, status2, res2)
        self.assertEqual(res1["buchung_id"], res2["buchung_id"])

        andere = dict(payload)
        andere["positionen"] = [{"text": "Anders", "betrag_cent": 500, "kategorie_id": kat1}]
        status3, res3 = self.request("POST", f"/api/beleg-auswertungen/{auftrag_id}/uebernehmen", andere)
        self.assertEqual(409, status3, res3)

    def test_bezahlt_von_sparte_id_erzeugt_auslage(self):
        kat1 = self.kategorie(self.haupt, "P43-Auslage")
        beleg_id = self.beleg(self.haupt)
        auftrag_id = self.auftrag(beleg_id, ergebnis=self._ergebnis())
        zahler_sparte = self.con.execute(
            "SELECT id FROM sparte WHERE typ = 'privat' AND id <> ? LIMIT 1", (self.haupt,)
        ).fetchone()[0]

        status, res = self.request("POST", f"/api/beleg-auswertungen/{auftrag_id}/uebernehmen", {
            "sparte_id": self.haupt, "bezahlt_von_sparte_id": zahler_sparte,
            "positionen": [{"text": "Brot", "betrag_cent": 300, "kategorie_id": kat1}],
        })
        self.assertEqual(201, status, res)

        auslage = self.con.execute(
            "SELECT zahler_sparte_id, betrag_cent FROM auslage WHERE buchung_id = ?",
            (res["buchung_id"],),
        ).fetchone()
        self.assertIsNotNone(auslage)
        self.assertEqual(zahler_sparte, auslage["zahler_sparte_id"])
        self.assertEqual(300, auslage["betrag_cent"])


if __name__ == "__main__":
    unittest.main()
