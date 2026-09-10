"""P40: Erfassen-Fluss mit Auto-Kategorie und Auslagen erfassen.

Prueft: Ausliefern der neuen Seite, die von erfassen.js tatsaechlich
gelesenen Endpunkt-Felder, sowie das Anlegen einer Buchung inkl.
Idempotenz ueber client_request_id (wie vom P40-Paket verlangt).
"""
import pathlib
import subprocess
import sys
import unittest

import test_bereiche as bereiche_tests

ROOT = pathlib.Path(__file__).resolve().parents[1]


class ErfassenSeiteTest(unittest.TestCase):
    """Nutzt dieselbe echte ASGI-Anwendung wie test_bereiche.py."""

    request = bereiche_tests.BereicheTest.request
    setUp = bereiche_tests.BereicheTest.setUp

    def test_erfassen_js_wird_ausgeliefert(self):
        status, body = self.request("GET", "/neu/pages/erfassen.js")
        self.assertEqual(200, status)
        # body ist bytes (kein JSON) -> enthaelt den erwarteten Export.
        self.assertIn(b"export async function render", body)

    def test_erfassen_css_wird_ausgeliefert(self):
        status, body = self.request("GET", "/neu/pages/erfassen.css")
        self.assertEqual(200, status)
        self.assertIn(b"erfassen-page", body)

    def test_neu_startseite_erreichbar(self):
        status, _body = self.request("GET", "/neu/")
        self.assertEqual(200, status)

    def test_sparten_liefert_von_js_gelesene_felder(self):
        status, sparten = self.request("GET", "/api/sparten")
        self.assertEqual(200, status, sparten)
        # erfassen.js liest: id, name, typ (fuer Auslage-Filter "privat").
        for feld in ("id", "name", "typ"):
            self.assertIn(feld, sparten[0])
        self.assertTrue(any(s["typ"] == "privat" for s in sparten))

    def test_kategorien_liefert_von_js_gelesene_felder(self):
        kategorie_id = self.kategorien[self.haupt]
        status, kategorien = self.request(
            "GET", f"/api/kategorien?sparte_id={self.haupt}&nur_aktive=true")
        self.assertEqual(200, status, kategorien)
        gefunden = next(k for k in kategorien if k["id"] == kategorie_id)
        # erfassen.js liest: id, name, richtung (Filter nach Richtung).
        for feld in ("id", "name", "richtung"):
            self.assertIn(feld, gefunden)

    def test_konten_liefert_von_js_gelesene_felder(self):
        status, konto = self.request("POST", "/api/konten", {
            "name": "Testkonto", "art": "bank", "sparte_id": self.haupt,
        })
        self.assertEqual(201, status, konto)
        status, konten = self.request("GET", "/api/konten")
        self.assertEqual(200, status, konten)
        gefunden = next(k for k in konten if k["id"] == konto["id"])
        # erfassen.js liest: id, name, sparte_id, art, aktiv.
        for feld in ("id", "name", "sparte_id", "art", "aktiv"):
            self.assertIn(feld, gefunden)

    def test_parse_liefert_von_js_gelesene_felder(self):
        status, vorschlag = self.request("POST", "/api/parse", {"text": "Testtext 12,50"})
        self.assertEqual(200, status, vorschlag)
        # erfassen.js liest: sparte_id, sparte_name, kategorie_id,
        # kategorie_name, betrag_cent.
        for feld in ("sparte_id", "sparte_name", "kategorie_id", "kategorie_name", "betrag_cent"):
            self.assertIn(feld, vorschlag)

    def test_buchungsliste_liefert_von_js_gelesene_felder(self):
        status, antwort = self.request(
            "GET", f"/api/buchungen?sparte_id={self.haupt}&limit=7")
        self.assertEqual(200, status, antwort)
        # erfassen.js liest: buchungen[].{text,datum,typ,betrag_cent,zeilen,auslage}.
        self.assertIn("buchungen", antwort)
        buchung = next(b for b in antwort["buchungen"] if b["id"] == self.buchungen[self.haupt])
        for feld in ("text", "datum", "typ", "betrag_cent", "zeilen"):
            self.assertIn(feld, buchung)
        self.assertIn("bezahlt_von_sparte_id", buchung)


class ErfassenBuchungTest(unittest.TestCase):
    request = bereiche_tests.BereicheTest.request
    setUp = bereiche_tests.BereicheTest.setUp

    def payload(self, **extra):
        return {
            "sparte_id": self.haupt, "datum": "2026-09-10", "typ": "ausgabe",
            "zahlungsart": "bar", "text": "Erfassen-Testbuchung",
            "zeilen": [{"kategorie_id": self.kategorien[self.haupt], "betrag_cent": 4590}],
            **extra,
        }

    def test_buchung_mit_client_request_id_und_idempotenz(self):
        payload = self.payload(client_request_id="p40-test-1")
        status, erste = self.request("POST", "/api/buchungen", payload)
        self.assertEqual(201, status, erste)
        self.assertEqual(4590, erste["betrag_cent"])
        self.assertEqual("bar", erste["zahlungsart"])

        status2, wiederholt = self.request("POST", "/api/buchungen", payload)
        self.assertEqual(200, status2, wiederholt)
        self.assertEqual(erste["id"], wiederholt["id"])

        anzahl = self.con.execute(
            "SELECT COUNT(*) FROM buchung WHERE client_request_id = ?",
            ("p40-test-1",),
        ).fetchone()[0]
        self.assertEqual(1, anzahl, "Wiederholung mit gleicher client_request_id darf kein Duplikat anlegen")

    def test_buchung_mit_bezahlt_von_sparte_erzeugt_auslage(self):
        zahler = self.con.execute(
            "SELECT id FROM sparte WHERE typ = 'privat' AND bereich_id = 1"
        ).fetchone()
        if zahler is None:
            self.skipTest("Keine private Sparte im Testschema vorhanden")
        payload = self.payload(
            bezahlt_von_sparte_id=zahler[0], client_request_id="p40-auslage-1")
        status, buchung = self.request("POST", "/api/buchungen", payload)
        self.assertEqual(201, status, buchung)
        self.assertEqual(zahler[0], buchung["bezahlt_von_sparte_id"])
        self.assertIn("auslage", buchung)
        self.assertEqual(4590, buchung["auslage"]["offen_cent"])

    def test_fehlerhafte_auslage_liefert_detail_fuer_toast(self):
        status, fehler = self.request("POST", "/api/buchungen", self.payload(
            typ="einnahme", bezahlt_von_sparte_id=self.haupt))
        self.assertEqual(422, status, fehler)
        self.assertIn("detail", fehler)


class ErfassenJsSyntaxTest(unittest.TestCase):
    """node --check fuer alle neuen/geaenderten JS-Dateien des Pakets."""

    def test_node_check_erfassen_js(self):
        pfad = ROOT / "static-neu" / "pages" / "erfassen.js"
        ergebnis = subprocess.run(["node", "--check", str(pfad)], capture_output=True, text=True)
        self.assertEqual(0, ergebnis.returncode, ergebnis.stderr)


if __name__ == "__main__":
    unittest.main()
