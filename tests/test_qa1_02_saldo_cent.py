"""QA1-02: GET /api/buchungen muss summen.saldo_cent liefern.

Der Drilldown-Dialog (uebersicht.js/sparte.js) liest summe.saldo_cent aus
der Antwort von GET /api/buchungen und zeigte bisher immer "Saldo € 0,00",
weil das Feld im summen-Objekt fehlte (nur einnahmen_cent/ausgaben_cent/
anzahl waren vorhanden).
"""
import test_bereiche as bereiche_tests


class SaldoCentInBuchungslisteTest(bereiche_tests.BereicheTest):
    def test_summen_enthaelt_saldo_cent(self):
        status, ergebnis = self.request("GET", f"/api/buchungen?sparte_id={self.haupt}")
        self.assertEqual(200, status, ergebnis)
        summen = ergebnis["summen"]
        self.assertIn("saldo_cent", summen)
        self.assertEqual(summen["einnahmen_cent"] - summen["ausgaben_cent"], summen["saldo_cent"])
        # Fixture legt eine Ausgabe ueber 100 Cent in self.haupt an.
        self.assertEqual(-100, summen["saldo_cent"])

    def test_saldo_cent_bei_einnahme_positiv(self):
        kid = self.con.execute(
            "INSERT INTO kategorie(sparte_id,name,richtung) VALUES(?,?,'einnahme')",
            (self.haupt, "QA1-02-Einnahme"),
        ).lastrowid
        self.con.commit()
        status, buchung = self.request("POST", "/api/buchungen", {
            "sparte_id": self.haupt, "datum": "2026-01-02", "typ": "einnahme",
            "zahlungsart": "bar", "zeilen": [{"kategorie_id": kid, "betrag_cent": 500}],
            "client_request_id": "qa1-02-test",
        })
        self.assertEqual(201, status, buchung)
        status, ergebnis = self.request("GET", f"/api/buchungen?sparte_id={self.haupt}")
        self.assertEqual(200, status, ergebnis)
        summen = ergebnis["summen"]
        # Fixture-Ausgabe (-100) + neue Einnahme (+500) = 400.
        self.assertEqual(400, summen["saldo_cent"])


if __name__ == "__main__":
    import unittest
    unittest.main()
