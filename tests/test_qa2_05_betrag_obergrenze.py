"""QA2-05: Buchungsbetraege brauchen eine Plausibilitaets-Obergrenze.

Bisher wurde z.B. betrag_cent=999999999999 (~10 Mrd. Euro) anstandslos mit
201 gespeichert und verzerrte sofort alle Summen. ZeileIn.betrag_cent hat
jetzt le=BETRAG_CENT_MAX (100 Mio. Euro in Cent, app/schemas.py).
"""
import test_bereiche as bereiche_tests
from app.schemas import BETRAG_CENT_MAX


class BetragObergrenzeTest(bereiche_tests.BereicheTest):
    def test_riesenbetrag_wird_mit_422_abgelehnt(self):
        status, fehler = self.request("POST", "/api/buchungen", {
            "sparte_id": self.haupt, "datum": "2026-01-02", "typ": "ausgabe",
            "zahlungsart": "bar",
            "zeilen": [{"kategorie_id": self.kategorien[self.haupt], "betrag_cent": 999999999999}],
            "client_request_id": "qa2-05-zu-hoch",
        })
        self.assertEqual(422, status, fehler)

    def test_grenzwert_wird_noch_akzeptiert(self):
        status, buchung = self.request("POST", "/api/buchungen", {
            "sparte_id": self.haupt, "datum": "2026-01-02", "typ": "ausgabe",
            "zahlungsart": "bar",
            "zeilen": [{"kategorie_id": self.kategorien[self.haupt], "betrag_cent": BETRAG_CENT_MAX}],
            "client_request_id": "qa2-05-grenzwert",
        })
        self.assertEqual(201, status, buchung)

    def test_knapp_darueber_wird_abgelehnt(self):
        status, fehler = self.request("POST", "/api/buchungen", {
            "sparte_id": self.haupt, "datum": "2026-01-02", "typ": "ausgabe",
            "zahlungsart": "bar",
            "zeilen": [{"kategorie_id": self.kategorien[self.haupt], "betrag_cent": BETRAG_CENT_MAX + 1}],
            "client_request_id": "qa2-05-knapp-drueber",
        })
        self.assertEqual(422, status, fehler)


if __name__ == "__main__":
    import unittest
    unittest.main()
