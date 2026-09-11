"""P71: Rechnungen als Text-PDF auswerten (Textebene per pypdf, kein OCR).

Ollama wird nie echt aufgerufen: app.auswertung._ollama_aufruf wird ueber
patch.object gemockt (gleiches Muster wie test_beleg_auswertung.py). Test-PDFs
werden zur Laufzeit im Temp-Ordner erzeugt (pypdf PdfWriter + handgebauter
Text-Content-Stream mit Helvetica-Font - pypdf selbst bietet keine
High-Level-API zum Schreiben von Text, siehe Bericht P71-runde1.md), keine
Binaerdateien im Repo.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, StreamObject

TEST_DIR = tempfile.TemporaryDirectory(prefix="finanz-p71-")
os.environ["FINANZ_DB"] = str(Path(TEST_DIR.name) / "p71-test.db")

from app import auswertung
from app.db import DB_PATH, get_connection, init_db
from app.routers.beleg_auswertung import auswerten_anfordern


def _text_pdf(pfad: Path, text: str, seiten: int = 1, seitenbreite: int = 600, seitenhoehe: int = 800) -> None:
    """Text-PDF mit `seiten` Seiten erzeugen, jede mit dem gleichen `text`.

    pypdf.PdfWriter hat keine Methode, um Text auf eine Seite zu schreiben -
    dafuer wird hier ein minimaler PDF-Content-Stream (BT/Tj/ET-Operatoren mit
    Helvetica-Font) von Hand gebaut und der Seite als Contents-Stream
    zugewiesen. pypdf liest das beim Extrahieren wieder korrekt aus.
    """
    writer = PdfWriter()
    escaped = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    for _ in range(seiten):
        page = writer.add_blank_page(width=seitenbreite, height=seitenhoehe)
        font = DictionaryObject()
        font[NameObject("/Type")] = NameObject("/Font")
        font[NameObject("/Subtype")] = NameObject("/Type1")
        font[NameObject("/BaseFont")] = NameObject("/Helvetica")
        font_ref = writer._add_object(font)
        fontdict = DictionaryObject()
        fontdict[NameObject("/F1")] = font_ref
        resources = DictionaryObject()
        resources[NameObject("/Font")] = fontdict
        page[NameObject("/Resources")] = resources
        content = StreamObject()
        content.set_data(f"BT /F1 10 Tf 10 750 Td ({escaped}) Tj ET".encode("latin-1"))
        content_ref = writer._add_object(content)
        page[NameObject("/Contents")] = content_ref
    with open(pfad, "wb") as f:
        writer.write(f)


def _leere_pdf(pfad: Path) -> None:
    """PDF mit einer Seite ohne Content-Stream (wie ein Scan ohne Textebene)."""
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with open(pfad, "wb") as f:
        writer.write(f)


def _kaputte_pdf(pfad: Path) -> None:
    pfad.write_bytes(b"das ist kein PDF, nur Muell-Bytes")


class PdfTextExtraktionTest(unittest.TestCase):
    """Punkt 1 der Karte: _pdf_text isoliert pruefen."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory(prefix="finanz-p71-pdf-")
        self.addCleanup(self.tempdir.cleanup)

    def _pfad(self, name):
        return Path(self.tempdir.name) / name

    def test_text_wird_gelesen_und_leerraum_normalisiert(self):
        pfad = self._pfad("rechnung.pdf")
        _text_pdf(pfad, "Testrechnung   mit   mehreren   Leerzeichen   und   genug   Text")
        text, gekuerzt = auswertung._pdf_text(pfad)
        self.assertIn("Testrechnung mit mehreren Leerzeichen", text)
        self.assertFalse(gekuerzt)
        self.assertNotIn("  ", text)

    def test_seiten_und_zeichenlimit_greift(self):
        pfad = self._pfad("lang.pdf")
        # Jede Seite liefert 3000 sichtbare Zeichen; ueber PDF_MAX_SEITEN (5)
        # Seiten hinweg damit sicher ueber PDF_MAX_ZEICHEN (12000) hinaus.
        lange_zeile = "A" * 3000
        seiten = auswertung.PDF_MAX_SEITEN + 5
        _text_pdf(pfad, lange_zeile, seiten=seiten)
        text, gekuerzt = auswertung._pdf_text(pfad)
        self.assertTrue(gekuerzt)
        self.assertEqual(auswertung.PDF_MAX_ZEICHEN, len(text))

    def test_leere_seite_wirft_textebene_fehler(self):
        pfad = self._pfad("scan.pdf")
        _leere_pdf(pfad)
        with self.assertRaises(ValueError) as ctx:
            auswertung._pdf_text(pfad)
        self.assertIn("Textebene", str(ctx.exception))

    def test_kaputte_datei_wirft_valueerror(self):
        pfad = self._pfad("kaputt.pdf")
        _kaputte_pdf(pfad)
        with self.assertRaises(ValueError):
            auswertung._pdf_text(pfad)


class PdfAuswertungTest(unittest.TestCase):
    """Punkte 2-4 der Karte: _auswerten/_verarbeite_naechsten_auftrag mit PDF."""

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
                "INSERT INTO sparte(name, typ) VALUES('Testsparte P71', 'privat')"
            ).lastrowid
            self.kategorie_id = con.execute(
                "INSERT INTO kategorie(sparte_id, name, richtung) "
                "VALUES(?, 'Buerobedarf P71', 'ausgabe')", (self.sparte_id,)
            ).lastrowid
            con.commit()
        finally:
            con.close()
        self.belege_ordner = DB_PATH.parent / "belege" / str(self.sparte_id)
        self.belege_ordner.mkdir(parents=True, exist_ok=True)

    def _lege_beleg_an(self, pfad: Path, dateiname: str):
        con = get_connection()
        try:
            cur = con.execute(
                "INSERT INTO beleg(sparte_id, dateiname, pfad) VALUES(?,?,?)",
                (self.sparte_id, dateiname, str(pfad)),
            )
            con.commit()
            return cur.lastrowid
        finally:
            con.close()

    def _gemockte_antwort(self):
        return {
            "message": {
                "content": json.dumps({
                    "haendler": "Bueromarkt Test",
                    "datum": "2026-09-01",
                    "positionen": [
                        {"text": "Buerobedarf P71 Einkauf", "betrag_cent": 1234,
                         "mwst_prozent": 20},
                    ],
                    "gesamt_cent": 1234,
                }),
            },
        }

    def test_auswerten_mit_pdf_sendet_text_ohne_bild_und_liefert_quelle_pdf_text(self):
        pfad = self.belege_ordner / "1_rechnung.pdf"
        _text_pdf(pfad, "Bueromarkt Test Rechnung ueber 12,34 EUR")
        beleg_id = self._lege_beleg_an(pfad, "rechnung.pdf")
        con = get_connection()
        self.addCleanup(con.close)

        aufgezeichnete_body = {}

        def gemockter_aufruf(url, body):
            aufgezeichnete_body.update(body)
            return self._gemockte_antwort()

        with patch.object(auswertung, "_ollama_aufruf", side_effect=gemockter_aufruf):
            ergebnis = auswertung._auswerten(con, beleg_id)

        self.assertNotIn("images", aufgezeichnete_body["messages"][0])
        self.assertTrue(
            aufgezeichnete_body["messages"][0]["content"].startswith(auswertung.PROMPT_TEXT)
        )
        self.assertEqual("pdf_text", ergebnis["quelle"])
        self.assertEqual(1, len(ergebnis["positionen"]))
        self.assertEqual(self.kategorie_id, ergebnis["positionen"][0]["kategorie_id"])
        self.assertEqual("Buerobedarf P71", ergebnis["positionen"][0]["kategorie_name"])

    def test_auswerten_mit_jpg_unveraendert_quelle_foto(self):
        pfad = self.belege_ordner / "2_kassenbon.jpg"
        pfad.write_bytes(b"fake-jpeg-bytes")
        beleg_id = self._lege_beleg_an(pfad, "kassenbon.jpg")
        con = get_connection()
        self.addCleanup(con.close)

        aufgezeichnete_body = {}

        def gemockter_aufruf(url, body):
            aufgezeichnete_body.update(body)
            return self._gemockte_antwort()

        with patch.object(auswertung, "_ollama_aufruf", side_effect=gemockter_aufruf):
            ergebnis = auswertung._auswerten(con, beleg_id)

        self.assertIn("images", aufgezeichnete_body["messages"][0])
        self.assertEqual(auswertung.PROMPT, aufgezeichnete_body["messages"][0]["content"])
        self.assertEqual("foto", ergebnis["quelle"])

    def test_endpunkt_akzeptiert_pdf_und_scan_ohne_textebene_scheitert_mit_meldung(self):
        pfad = self.belege_ordner / "3_scan.pdf"
        _leere_pdf(pfad)
        beleg_id = self._lege_beleg_an(pfad, "scan.pdf")
        con = get_connection()
        self.addCleanup(con.close)

        # Endpunkt (POST /api/belege/{id}/auswerten -> auswerten_anfordern) muss
        # die PDF-Endung annehmen, nicht schon hier ablehnen.
        auftrag = auswerten_anfordern(beleg_id, con)
        self.assertEqual("offen", auftrag["status"])

        with patch.object(auswertung, "_ollama_aufruf") as mock_aufruf:
            bearbeitet = auswertung._verarbeite_naechsten_auftrag()
        mock_aufruf.assert_not_called()  # _pdf_text scheitert schon vorher

        self.assertTrue(bearbeitet)
        row = con.execute(
            "SELECT status, fehler FROM beleg_auswertung WHERE id = ?", (auftrag["id"],)
        ).fetchone()
        self.assertEqual("fehler", row["status"])
        self.assertIn("Textebene", row["fehler"])


if __name__ == "__main__":
    unittest.main()
