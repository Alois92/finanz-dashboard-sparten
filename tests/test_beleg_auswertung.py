"""Feature B: lokale Foto-Auswertung (Ollama), Auftragsverwaltung und
Kategorien-Mapping. Ollama wird NICHT echt aufgerufen - app.auswertung
._ollama_aufruf wird gemockt (monkeypatch via unittest.mock.patch.object)."""
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pydantic

TEST_DIR = tempfile.TemporaryDirectory(prefix="finanz-auswertung-")
os.environ["FINANZ_DB"] = str(Path(TEST_DIR.name) / "auswertung-test.db")

from app import auswertung
from app.db import DB_PATH, get_connection, init_db
from app.routers.beleg_auswertung import (
    AuswertungStatusIn, auswerten_anfordern, setze_auswertungsstatus,
)


class BelegAuswertungTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        con = get_connection()
        try:
            con.execute("DELETE FROM beleg_auswertung")
            con.execute("DELETE FROM beleg")
            con.commit()
            self.sparte_id = con.execute(
                "INSERT INTO sparte(name, typ) VALUES('Testsparte BA', 'privat')"
            ).lastrowid
            self.kategorie_id = con.execute(
                "INSERT INTO kategorie(sparte_id, name, richtung) "
                "VALUES(?, 'Lebensmittel BA', 'ausgabe')", (self.sparte_id,)
            ).lastrowid
            con.commit()
        finally:
            con.close()
        # Beleg-Datei physisch anlegen (Inhalt ist fuer die gemockten Tests egal,
        # nur die Endung muss zu den erlaubten Bildformaten gehoeren).
        belege_ordner = DB_PATH.parent / "belege" / str(self.sparte_id)
        belege_ordner.mkdir(parents=True, exist_ok=True)
        self.beleg_pfad = belege_ordner / "1_kassenbon.jpg"
        self.beleg_pfad.write_bytes(b"fake-jpeg-bytes")

    def _lege_beleg_an(self, dateiname="kassenbon.jpg"):
        con = get_connection()
        try:
            cur = con.execute(
                "INSERT INTO beleg(sparte_id, dateiname, pfad) VALUES(?,?,?)",
                (self.sparte_id, dateiname, str(self.beleg_pfad)),
            )
            con.commit()
            return cur.lastrowid
        finally:
            con.close()

    def test_auftrag_anlegen_und_dedupe(self):
        beleg_id = self._lege_beleg_an()
        con = get_connection()
        self.addCleanup(con.close)

        erster = auswerten_anfordern(beleg_id, con)
        self.assertEqual("offen", erster["status"])
        zweiter = auswerten_anfordern(beleg_id, con)
        self.assertEqual(erster["id"], zweiter["id"])

        anzahl = con.execute(
            "SELECT COUNT(*) AS n FROM beleg_auswertung WHERE beleg_id = ?",
            (beleg_id,),
        ).fetchone()["n"]
        self.assertEqual(1, anzahl)

    def test_verarbeitung_gemockt_setzt_fertig_und_mapped_kategorie(self):
        beleg_id = self._lege_beleg_an()
        con = get_connection()
        self.addCleanup(con.close)
        auftrag = auswerten_anfordern(beleg_id, con)

        gemockte_antwort = {
            "message": {
                "content": json.dumps({
                    "haendler": "Testmarkt",
                    "datum": "2026-07-15",
                    "positionen": [
                        {"text": "Lebensmittel BA Einkauf", "betrag_cent": 1234},
                    ],
                    "gesamt_cent": 1234,
                }),
            },
        }
        with patch.object(auswertung, "_ollama_aufruf", return_value=gemockte_antwort):
            bearbeitet = auswertung._verarbeite_naechsten_auftrag()

        self.assertTrue(bearbeitet)
        row = con.execute(
            "SELECT status, ergebnis_json FROM beleg_auswertung WHERE id = ?",
            (auftrag["id"],),
        ).fetchone()
        self.assertEqual("fertig", row["status"])
        ergebnis = json.loads(row["ergebnis_json"])
        self.assertEqual("Testmarkt", ergebnis["haendler"])
        self.assertEqual(1, len(ergebnis["positionen"]))
        self.assertEqual(self.kategorie_id, ergebnis["positionen"][0]["kategorie_id"])
        self.assertEqual("Lebensmittel BA", ergebnis["positionen"][0]["kategorie_name"])

    def test_ollama_nicht_erreichbar_bleibt_offen(self):
        beleg_id = self._lege_beleg_an()
        con = get_connection()
        self.addCleanup(con.close)
        auftrag = auswerten_anfordern(beleg_id, con)

        with patch.object(
            auswertung, "_ollama_aufruf",
            side_effect=urllib.error.URLError("Verbindung abgelehnt"),
        ):
            bearbeitet = auswertung._verarbeite_naechsten_auftrag()

        self.assertTrue(bearbeitet)
        row = con.execute(
            "SELECT status, fehler, versuche FROM beleg_auswertung WHERE id = ?",
            (auftrag["id"],),
        ).fetchone()
        self.assertEqual("offen", row["status"])
        self.assertEqual(1, row["versuche"])
        self.assertIn(auswertung.OLLAMA_URL, row["fehler"])

    def _verarbeite_mit_antwort(self, positionen, gesamt_cent):
        """Legt einen Beleg + Auftrag an, mockt die Ollama-Antwort mit den
        gegebenen Positionen/Gesamt und gibt das gespeicherte Ergebnis-Dict."""
        beleg_id = self._lege_beleg_an()
        con = get_connection()
        self.addCleanup(con.close)
        auftrag = auswerten_anfordern(beleg_id, con)
        gemockte_antwort = {
            "message": {
                "content": json.dumps({
                    "haendler": "Testmarkt",
                    "datum": "2026-07-15",
                    "positionen": positionen,
                    "gesamt_cent": gesamt_cent,
                }),
            },
        }
        with patch.object(auswertung, "_ollama_aufruf", return_value=gemockte_antwort):
            auswertung._verarbeite_naechsten_auftrag()
        row = con.execute(
            "SELECT ergebnis_json FROM beleg_auswertung WHERE id = ?",
            (auftrag["id"],),
        ).fetchone()
        return json.loads(row["ergebnis_json"])

    def test_brutto_mit_mwst_je_position(self):
        # (a) Netto-Positionen mit MwSt-Satz -> Brutto exakt gleich Gesamt.
        ergebnis = self._verarbeite_mit_antwort(
            [{"text": "Artikel A", "betrag_cent": 1000, "mwst_prozent": 20},
             {"text": "Artikel B", "betrag_cent": 2000, "mwst_prozent": 20}],
            gesamt_cent=3600,
        )
        betraege = [p["betrag_cent"] for p in ergebnis["positionen"]]
        self.assertEqual([1200, 2400], betraege)
        self.assertEqual(3600, sum(betraege))
        self.assertTrue(ergebnis.get("brutto_aufgeschlagen"))
        self.assertIn("Netto-Preise erkannt", ergebnis["hinweis"])

    def test_brutto_proportional_ohne_mwst(self):
        # (b) Netto-Positionen ohne MwSt-Satz -> proportional, Summe exakt Gesamt.
        ergebnis = self._verarbeite_mit_antwort(
            [{"text": "Artikel A", "betrag_cent": 1000, "mwst_prozent": None},
             {"text": "Artikel B", "betrag_cent": 500, "mwst_prozent": None}],
            gesamt_cent=1800,
        )
        betraege = [p["betrag_cent"] for p in ergebnis["positionen"]]
        self.assertEqual(1800, sum(betraege))
        self.assertTrue(ergebnis.get("brutto_aufgeschlagen"))
        self.assertIn("Netto-Preise erkannt", ergebnis["hinweis"])

    def test_stimmige_bruttosumme_unveraendert(self):
        # (c) Summe passt zum Gesamt -> keine Aenderung, kein Hinweis.
        ergebnis = self._verarbeite_mit_antwort(
            [{"text": "Artikel A", "betrag_cent": 1200, "mwst_prozent": 20},
             {"text": "Artikel B", "betrag_cent": 800, "mwst_prozent": 10}],
            gesamt_cent=2000,
        )
        betraege = [p["betrag_cent"] for p in ergebnis["positionen"]]
        self.assertEqual([1200, 800], betraege)
        self.assertNotIn("hinweis", ergebnis)
        self.assertNotIn("brutto_aufgeschlagen", ergebnis)

    def test_absurde_abweichung_nur_pruefhinweis(self):
        # (d) Faktor 2.0 -> Betraege unveraendert, nur Pruef-Hinweis.
        ergebnis = self._verarbeite_mit_antwort(
            [{"text": "Artikel A", "betrag_cent": 1000, "mwst_prozent": None}],
            gesamt_cent=2000,
        )
        self.assertEqual(1000, ergebnis["positionen"][0]["betrag_cent"])
        self.assertNotIn("brutto_aufgeschlagen", ergebnis)
        self.assertIn("bitte prüfen", ergebnis["hinweis"])

    def test_rabatt_wird_mitskaliert(self):
        # (e) Rabatt (negative Position) im proportionalen Fall bleibt sinnvoll.
        ergebnis = self._verarbeite_mit_antwort(
            [{"text": "Artikel A", "betrag_cent": 1000, "mwst_prozent": None},
             {"text": "Rabatt", "betrag_cent": -200, "mwst_prozent": None}],
            gesamt_cent=960,
        )
        betraege = [p["betrag_cent"] for p in ergebnis["positionen"]]
        self.assertEqual(960, sum(betraege))
        # Der Rabatt bleibt negativ, die groesste Position positiv.
        self.assertLess(betraege[1], 0)
        self.assertGreater(betraege[0], 0)
        self.assertTrue(ergebnis.get("brutto_aufgeschlagen"))

    def test_status_endpoint_erlaubt_nur_verworfen_oder_verbucht(self):
        beleg_id = self._lege_beleg_an()
        con = get_connection()
        self.addCleanup(con.close)
        auftrag = auswerten_anfordern(beleg_id, con)

        ergebnis = setze_auswertungsstatus(
            auftrag["id"], AuswertungStatusIn(status="verbucht"), con,
        )
        self.assertEqual("verbucht", ergebnis["status"])

        with self.assertRaises(pydantic.ValidationError):
            AuswertungStatusIn(status="offen")


if __name__ == "__main__":
    unittest.main()
