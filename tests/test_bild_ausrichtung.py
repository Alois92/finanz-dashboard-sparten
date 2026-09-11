"""Quer liegende Belegfotos werden vor dem Modellaufruf auf Hochformat gedreht.

Hintergrund: Modellvergleich vom 11.09.2026 (outputs/modelltest/ERGEBNIS.md). Fotos aus
Messengern kommen ohne EXIF-Drehung und quer; kein Modell liest sie dann zuverlaessig.
"""
import base64
import importlib
import io
import os
import pathlib
import tempfile
import unittest

from PIL import Image


def _lade(pfad, quer_drehen):
    os.environ["FINANZ_BILD_QUER_DREHEN"] = quer_drehen
    from app import auswertung
    importlib.reload(auswertung)
    daten = base64.b64decode(auswertung._lade_bild_base64(pfad))
    return Image.open(io.BytesIO(daten)).size


class BildAusrichtungTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.quer = pathlib.Path(self.tmp.name) / "quer.jpg"
        Image.new("RGB", (1200, 500), (240, 240, 240)).save(self.quer, quality=80)
        self.hoch = pathlib.Path(self.tmp.name) / "hoch.jpg"
        Image.new("RGB", (500, 1200), (240, 240, 240)).save(self.hoch, quality=80)
        self._alt = os.environ.get("FINANZ_BILD_QUER_DREHEN")

    def tearDown(self):
        if self._alt is None:
            os.environ.pop("FINANZ_BILD_QUER_DREHEN", None)
        else:
            os.environ["FINANZ_BILD_QUER_DREHEN"] = self._alt
        from app import auswertung
        importlib.reload(auswertung)
        self.tmp.cleanup()

    def test_querformat_wird_hochkant_gedreht(self):
        breite, hoehe = _lade(self.quer, "1")
        self.assertGreater(hoehe, breite)
        self.assertEqual((500, 1200), (breite, hoehe))

    def test_hochformat_bleibt_unveraendert(self):
        self.assertEqual((500, 1200), _lade(self.hoch, "1"))

    def test_schalter_null_laesst_querformat_stehen(self):
        breite, hoehe = _lade(self.quer, "0")
        self.assertGreater(breite, hoehe)


if __name__ == "__main__":
    unittest.main()
