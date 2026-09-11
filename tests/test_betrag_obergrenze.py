"""QA2-05/QA2-05b: Plausibilitaets-Obergrenze fuer alle Cent-Betraege aus Nutzereingaben.

100 Mio. Euro = 10 Mrd. Cent (schemas.BETRAG_CENT_MAX). Positive Felder: le=Grenze.
Signierte Felder (Saldo-Anker, Zaehlung, Bewegung): zusaetzlich ge=-Grenze.
Geprueft werden die Pydantic-Feldmetadaten aller betroffenen Modelle (damit kein
Feld still ohne Grenze bleibt) und das Verhalten an der Grenze je Art.
"""
import os
import tempfile
import unittest

TEST_DIR = None
if not os.environ.get("FINANZ_DB"):
    TEST_DIR = tempfile.TemporaryDirectory(prefix="finanz-obergrenze-")
    os.environ["FINANZ_DB"] = os.path.join(TEST_DIR.name, "obergrenze.db")

from pydantic import ValidationError

from app import schemas
from app.routers import auslagen, beleg_auswertung, buchungen, konten, kredite

OBERGRENZE = schemas.BETRAG_CENT_MAX

# (Modell, Feldname, signiert)
FELDER = [
    (schemas.ZeileIn, "betrag_cent", False),
    (auslagen.AusgleichIn, "betrag_cent", False),
    (buchungen.UmbuchungIn, "betrag_cent", False),
    (buchungen.ErstattenZeileIn, "betrag_cent", False),
    (beleg_auswertung.UebernehmenPosition, "betrag_cent", False),
    (konten.TransferIn, "betrag_cent", False),
    (konten.BewegungIn, "betrag_signed_cent", True),
    (konten.AnkerIn, "saldo_cent", True),
    (konten.ZaehlungIn, "gezaehlt_cent", True),
    (kredite.KreditIn, "monatsrate_cent", False),
    (kredite.KreditPatch, "monatsrate_cent", False),
    (kredite.JahreszinsIn, "zins_cent", False),
    (kredite.JahreszinsIn, "restschuld_cent", False),
    (kredite.RateIn, "betrag_cent", False),
]


def _grenzen(modell, feld):
    """(ge, le) aus den Pydantic-Metadaten des Felds; None, falls nicht gesetzt."""
    ge = le = None
    for meta in modell.model_fields[feld].metadata:
        if getattr(meta, "le", None) is not None:
            le = meta.le
        if getattr(meta, "ge", None) is not None:
            ge = meta.ge
    return ge, le


class BetragObergrenzeTest(unittest.TestCase):
    def test_konstante_ist_100_millionen_euro(self):
        self.assertEqual(10_000_000_000, OBERGRENZE)

    def test_alle_betragsfelder_haben_die_obergrenze(self):
        for modell, feld, signiert in FELDER:
            with self.subTest(modell=modell.__name__, feld=feld):
                ge, le = _grenzen(modell, feld)
                self.assertEqual(OBERGRENZE, le, "Obergrenze fehlt")
                if signiert:
                    self.assertEqual(-OBERGRENZE, ge, "Untergrenze fuer signiertes Feld fehlt")

    def test_grenzwert_erlaubt_darueber_abgelehnt_positiv(self):
        schemas.ZeileIn(kategorie_id=1, betrag_cent=OBERGRENZE)
        with self.assertRaises(ValidationError):
            schemas.ZeileIn(kategorie_id=1, betrag_cent=OBERGRENZE + 1)

    def test_grenzwert_erlaubt_darueber_abgelehnt_signiert(self):
        basis = {"stichtag": "2026-09-11", "quelle": "manuell"}
        konten.AnkerIn.model_validate({**basis, "saldo_cent": -OBERGRENZE})
        konten.AnkerIn.model_validate({**basis, "saldo_cent": OBERGRENZE})
        with self.assertRaises(ValidationError):
            konten.AnkerIn.model_validate({**basis, "saldo_cent": -OBERGRENZE - 1})
        with self.assertRaises(ValidationError):
            konten.AnkerIn.model_validate({**basis, "saldo_cent": OBERGRENZE + 1})


if __name__ == "__main__":
    unittest.main()
