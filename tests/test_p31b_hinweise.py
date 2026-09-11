"""P31b: Hinweistexte aus rechenbasis.hinweise() enthielten rohe Cent
("Größte Buchung: 5099 Cent."). Der Server liefert jetzt zusätzlich wert_cent als
Zahl (dort, wo der Hinweis einen Geldbetrag meint) und formatiert text bereits als
Euro-Betrag wie format.js (fmtEur) ihn im Frontend zeigt ("50,99 €").
uebersicht.js zeigt weiterhin unverändert h.text - dafür war keine Frontend-Änderung
nötig, siehe Bericht.
"""
import unittest

import test_bereiche


class HinweistexteOhneRoheCentTest(unittest.TestCase):
    setUp = test_bereiche.BereicheTest.setUp
    request = test_bereiche.BereicheTest.request

    def get(self, route, query=''):
        status, data = self.request('GET', '/api/' + route + ('?' + query if query else ''))
        self.assertEqual(200, status, data)
        return data

    def _kategorie(self, name, richtung='ausgabe'):
        kid = self.con.execute(
            "INSERT INTO kategorie(sparte_id,name,richtung) VALUES(?,?,?)",
            (self.haupt, name, richtung)).lastrowid
        self.con.commit()
        return kid

    def _buchung(self, kategorie_id, typ, cent, datum):
        bid = self.con.execute(
            "INSERT INTO buchung(sparte_id,datum,typ,text) VALUES(?,?,?,?)",
            (self.haupt, datum, typ, f"P31b-{typ}")).lastrowid
        self.con.execute(
            "INSERT INTO buchungszeile(buchung_id,kategorie_id,betrag_cent) VALUES(?,?,?)",
            (bid, kategorie_id, cent))
        self.con.commit()
        return bid

    def test_groesste_buchung_ohne_rohe_cent_und_mit_wert_cent(self):
        kat = self._kategorie('P31b-Groesste')
        self._buchung(kat, 'ausgabe', 5099, '2026-02-10')
        hinweise = self.get('uebersicht', f'sparte_id={self.haupt}&jahr=2026&stichtag=2026-09-10')['hinweise']
        hinweis = next(h for h in hinweise if h['art'] == 'groesste_buchung')
        self.assertEqual(5099, hinweis['wert_cent'])
        self.assertNotIn('Cent', hinweis['text'])
        self.assertIn('50,99', hinweis['text'])
        self.assertIn('€', hinweis['text'])

    def test_auslagen_offen_ohne_rohe_cent_und_mit_wert_cent(self):
        aus_kat = self._kategorie('P31b-Auslage')
        zahler = self.con.execute(
            "INSERT INTO sparte(name,typ) VALUES('P31b-Zahler','privat')").lastrowid
        self.con.commit()
        status, buchung = self.request('POST', '/api/buchungen', {
            'sparte_id': self.haupt, 'datum': '2026-03-01', 'typ': 'ausgabe',
            'zahlungsart': 'bar', 'bezahlt_von_sparte_id': zahler,
            'zeilen': [{'kategorie_id': aus_kat, 'betrag_cent': 12345}],
        })
        self.assertEqual(201, status, buchung)
        hinweise = self.get('uebersicht', f'sparte_id={self.haupt}&jahr=2026&stichtag=2026-09-10')['hinweise']
        hinweis = next(h for h in hinweise if h['art'] == 'auslagen_offen')
        self.assertEqual(12345, hinweis['wert_cent'])
        self.assertNotIn('Cent', hinweis['text'])
        self.assertIn('123,45', hinweis['text'])

    def test_nicht_monetaere_hinweise_bleiben_ohne_wert_cent(self):
        # kategorie_anteil ist prozentual, kein Geldbetrag - wert_cent bleibt None.
        kat = self._kategorie('P31b-Anteil')
        self._buchung(kat, 'ausgabe', 2000, '2026-04-01')
        hinweise = self.get('uebersicht', f'sparte_id={self.haupt}&jahr=2026&stichtag=2026-09-10')['hinweise']
        hinweis = next(h for h in hinweise if h['art'] == 'kategorie_anteil')
        self.assertIsNone(hinweis['wert_cent'])
        self.assertIn('%', hinweis['text'])

    def test_ausblenden_ueber_wert_funktioniert_weiterhin(self):
        # bestehendes Verhalten (test_rechenbasis.py) darf durch das neue Feld
        # wert_cent nicht brechen: 'wert' bleibt das Vergleichsfeld fuers Ausblenden.
        kat = self._kategorie('P31b-Ausblenden')
        self._buchung(kat, 'ausgabe', 777, '2026-05-01')
        hinweise = self.get('uebersicht', f'sparte_id={self.haupt}&jahr=2026&stichtag=2026-09-10')['hinweise']
        hinweis = next(h for h in hinweise if h['art'] == 'groesste_buchung')
        status, _ = self.request('POST', '/api/hinweise/aus',
                                 {'schluessel': hinweis['schluessel'], 'bis_wert': hinweis['wert']})
        self.assertEqual(200, status)
        neu = self.get('uebersicht', f'sparte_id={self.haupt}&jahr=2026&stichtag=2026-09-10')['hinweise']
        self.assertFalse(any(h['schluessel'] == hinweis['schluessel'] for h in neu))


if __name__ == '__main__':
    unittest.main()
