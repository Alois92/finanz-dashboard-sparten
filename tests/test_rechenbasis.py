"""P20: feste Daten, echte Tabellen und echte ASGI-Endpunkte."""
import base64
import unittest
from unittest.mock import patch

import test_bereiche


class RechenbasisTest(unittest.TestCase):
    setUp = test_bereiche.BereicheTest.setUp
    request = test_bereiche.BereicheTest.request

    def add(self, datum, cent, typ='ausgabe', sid=None, kid=None, neutral=0):
        sid = sid or self.haupt
        kid = kid or self.kategorien[sid]
        bid = self.con.execute('INSERT INTO buchung(sparte_id,datum,typ,text) VALUES(?,?,?,?)',
                               (sid, datum, typ, 'P20')).lastrowid
        self.con.execute('INSERT INTO buchungszeile(buchung_id,kategorie_id,betrag_cent,neutral) VALUES(?,?,?,?)',
                         (bid, kid, cent, neutral))
        self.con.commit()
        return bid

    def get(self, route, query='jahr=2026&stichtag=2026-09-08'):
        status, data = self.request('GET', '/api/' + route + '?' + query)
        self.assertEqual(200, status, data)
        return data

    def test_uebersicht_liste_kacheln_drilldown(self):
        self.add('2026-02-01', 10000, 'einnahme')
        self.add('2026-03-01', 2000)
        u = self.get('uebersicht')
        b = self.get('buchungen')
        self.assertEqual(10000, u['ist']['einnahmen_cent'])
        self.assertEqual(2100, u['ist']['ausgaben_cent'])
        self.assertEqual(u['ist']['ausgaben_cent'], b['summen']['ausgaben_cent'])
        self.assertEqual(2100, sum(s['ausgaben_cent'] for s in u['sparten']))
        d = self.get('buchungen', f'jahr=2026&stichtag=2026-09-08&kategorie_id={self.kategorien[self.haupt]}')
        self.assertEqual(2100, d['summen']['ausgaben_cent'])

    def test_erwartung_und_vordatierung(self):
        self.add('2025-11-15', 3000)
        self.add('2026-11-15', 9999)
        u = self.get('uebersicht')
        self.assertEqual(100, u['ist']['ausgaben_cent'])
        self.assertEqual(3100, u['erwartung']['ausgaben_cent'])
        u = self.get('uebersicht', 'jahr=2026&stichtag=2026-12-31')
        self.assertEqual(u['ist'], u['erwartung'])
        self.assertIsNone(self.get('uebersicht', 'jahr=2025&stichtag=2026-09-08')['erwartung'])

    def test_schaltjahr(self):
        self.add('2023-02-28', 200)
        self.add('2023-03-01', 300)
        self.assertEqual(300, self.get('uebersicht', 'jahr=2024&stichtag=2024-02-29')['erwartung']['ausgaben_cent'])

    def test_matrix_beide_richtungen_und_inaktiv(self):
        self.add('2026-02-01', 10000, 'einnahme')
        self.add('2026-03-01', 2000)
        self.con.execute('UPDATE kategorie SET aktiv=0 WHERE id=?', (self.kategorien[self.haupt],))
        m = self.get('jahresmatrix', 'jahre=2025,2026&stichtag=2026-09-08')
        row = m['zeilen'][0]
        self.assertEqual(0, row['aktiv'])
        self.assertEqual({'einnahmen_cent': 10000, 'ausgaben_cent': 2100}, row['werte']['2026'])
        self.assertTrue(row['ohne_vorjahr'])

    def test_cursor_250_gleiches_datum(self):
        ids = [self.add('2026-06-06', 10) for _ in range(250)]
        query = 'jahr=2026&monat=2026-06&limit=100'
        seen = []
        for count in (100, 100, 50):
            page = self.get('buchungen', query)
            self.assertEqual(250, page['summen']['anzahl'])
            self.assertEqual(count, len(page['buchungen']))
            seen.extend(b['id'] for b in page['buchungen'])
            cursor = page['naechster_cursor']
            if cursor:
                self.assertEqual(f'2026-06-06|{seen[-1]}', base64.b64decode(cursor).decode())
                query = 'jahr=2026&monat=2026-06&limit=100&cursor=' + cursor
        self.assertIsNone(cursor)
        self.assertEqual(list(reversed(ids)), seen)

    def test_bereich_nur_bereich_id_und_validierung(self):
        self.con.execute("UPDATE sparte SET typ='verein',geschuetzt=1 WHERE id=?", (self.haupt,))
        self.con.execute("UPDATE sparte SET typ='privat',geschuetzt=0 WHERE id=?", (self.verein,))
        self.assertEqual(100, self.get('uebersicht')['ist']['ausgaben_cent'])
        self.assertEqual(900, self.get('uebersicht', 'bereich_id=2&jahr=2026')['ist']['ausgaben_cent'])
        for route in ('uebersicht', 'jahresmatrix', 'buchungen'):
            for query in ('bereich_id=999', f'sparte_id={self.verein}', f'kategorie_id={self.kategorien[self.verein]}'):
                self.assertEqual(404, self.request('GET', f'/api/{route}?{query}')[0])
        for query in ('richtung=falsch', 'zahlungsart=falsch', 'stichtag=2026-99-01', 'jahr=0', 'von=2026-02-01&bis=2026-01-01'):
            self.assertEqual(422, self.request('GET', '/api/uebersicht?' + query)[0])

    def test_miete_fehlend_ab_fuenf_tagen(self):
        for m in range(1, 13):
            self.add(f'2025-{m:02}-03', 10000, 'einnahme')
        early = self.get('uebersicht', 'jahr=2026&stichtag=2026-09-05')['hinweise']
        late = self.get('uebersicht')['hinweise']
        self.assertFalse(any(h['art'] == 'einnahme_fehlt' for h in early))
        self.assertTrue(any(h['art'] == 'einnahme_fehlt' for h in late))

    def test_hinweis_aus_wertaenderung_und_bereich(self):
        h = next(h for h in self.get('uebersicht')['hinweise'] if h['art'] == 'groesste_buchung')
        status, _ = self.request('POST', '/api/hinweise/aus', {'schluessel': h['schluessel'], 'bis_wert': h['wert']})
        self.assertEqual(200, status)
        self.assertNotIn(h, self.get('uebersicht')['hinweise'])
        self.assertEqual([], self.get('hinweise/aus', 'bereich_id=2'))
        self.add('2026-04-01', 200)
        self.assertTrue(any(x['art'] == h['art'] for x in self.get('uebersicht')['hinweise']))

    def test_zeitzonen_rueckfall(self):
        from app import rechenbasis
        from datetime import date
        from zoneinfo import ZoneInfoNotFoundError
        with patch.object(rechenbasis, 'ZoneInfo', side_effect=ZoneInfoNotFoundError):
            self.assertEqual(date.today().isoformat(), rechenbasis.stichtag_heute())

    def test_filter_standardstichtag_auch_ohne_http(self):
        from app.rechenbasis import Filter, stichtag_heute, summen
        self.add('2099-01-01', 12300)
        f = Filter()
        self.assertEqual(stichtag_heute(), f.stichtag)
        self.assertEqual(100, summen(self.con, f)['ausgaben_cent'])

    def test_gruppen_split_richtung_und_zahlungsart(self):
        k2 = self.con.execute("INSERT INTO kategorie(sparte_id,name,richtung) VALUES(?,'Zweite','ausgabe')", (self.haupt,)).lastrowid
        bid = self.add('2026-05-01', 300, 'einnahme')
        self.con.execute('INSERT INTO buchungszeile(buchung_id,kategorie_id,betrag_cent) VALUES(?,?,700)', (bid, k2))
        g1 = self.con.execute("INSERT INTO globale_kategoriegruppe(name) VALUES('P20-A')").lastrowid
        g2 = self.con.execute("INSERT INTO globale_kategoriegruppe(name) VALUES('P20-B')").lastrowid
        self.con.executemany('INSERT INTO kategorie_globalgruppe VALUES(?,?)', [(k2, g1), (k2, g2)])
        ag = self.con.execute("INSERT INTO auswertungsgruppe(name) VALUES('P20')").lastrowid
        self.con.execute('INSERT INTO auswertungsgruppe_sparte VALUES(?,?)', (ag, self.haupt))
        self.con.commit()
        query = f'jahr=2026&richtung=einnahme&globalgruppe_id={g1}&auswertungsgruppe_id={ag}&zahlungsart=bank'
        self.assertEqual(700, self.get('uebersicht', query)['ist']['einnahmen_cent'])
        b = self.get('buchungen', query)
        self.assertEqual(700, b['summen']['einnahmen_cent'])
        self.assertEqual(700, b['buchungen'][0]['filter_betrag_cent'])
        self.assertEqual(0, self.get('uebersicht', query.replace('bank', 'bar'))['ist']['einnahmen_cent'])

    def test_cursor_und_matrix_validierung(self):
        for cursor in ('2026-01-01_1', '!!!', base64.b64encode(b'2026-01-01|0').decode()):
            self.assertEqual(422, self.request('GET', '/api/buchungen?cursor=' + cursor)[0])
        for years in ('abc', '1,2026', '2026,'):
            self.assertEqual(422, self.request('GET', '/api/jahresmatrix?jahre=' + years)[0])

    def test_kennzahl_rechnet_alle_terme_in_einer_abfrage(self):
        from app.kennzahlen import wert
        kid = self.con.execute("INSERT INTO kennzahl(sparte_id,name) VALUES(?,'P20')", (self.haupt,)).lastrowid
        self.con.execute("INSERT INTO kennzahl_term(kennzahl_id,kategorie_id,messgroesse,vorzeichen) VALUES(?,?,'netto',1)", (kid, self.kategorien[self.haupt]))
        self.add('2026-03-03', 300, 'einnahme')
        statements = []
        self.con.set_trace_callback(statements.append)
        try:
            self.assertEqual(200, wert(self.con, kid, 2026, {'bereich_id': 1}))
        finally:
            self.con.set_trace_callback(None)
        self.assertEqual(1, sum(s.lstrip().upper().startswith('SELECT') for s in statements))

    def test_matrix_zeigt_kategorie_mit_nur_vorjahresrest(self):
        kid = self.con.execute("INSERT INTO kategorie(sparte_id,name,richtung) VALUES(?,'Nur Vorjahr','ausgabe')", (self.haupt,)).lastrowid
        self.add('2025-11-15', 12300, kid=kid)
        m = self.get('jahresmatrix', 'jahre=2026&stichtag=2026-09-08')
        row = next((r for r in m['zeilen'] if r['kategorie_id'] == kid), None)
        self.assertIsNotNone(row)
        self.assertEqual(12300, row['erwartung_cent']['ausgaben'])

    def test_alte_suche_behaelt_zukunftstreffer(self):
        bid = self.add('2099-01-01', 50)
        self.assertIn(bid, [r['id'] for r in self.get('buchungen/suche', 'q=P20')])

    def test_standard_und_freier_zeitraum_sind_konsistent(self):
        self.add('2025-11-15', 12300)
        for query in ('stichtag=2026-09-08', 'von=2025-01-01&bis=2026-06-30&stichtag=2026-09-08'):
            self.assertEqual(self.get('uebersicht', query)['ist']['ausgaben_cent'],
                             self.get('buchungen', query)['summen']['ausgaben_cent'])

    def test_ignorierte_bankumsaetze_sind_nicht_offen(self):
        kid = self.con.execute("INSERT INTO bankkonto(name,sparte_id) VALUES('P20',?)", (self.haupt,)).lastrowid
        self.con.execute("INSERT INTO bankumsatz(bankkonto_id,datum,betrag_cent,import_hash,importstatus) VALUES(?,'2026-06-01',100,'P20','ignoriert')", (kid,))
        self.con.commit()
        self.assertFalse(any(h['art'] == 'bankumsaetze_offen' for h in self.get('uebersicht')['hinweise']))
        self.con.execute("UPDATE bankumsatz SET importstatus='offen' WHERE import_hash='P20'")
        self.con.commit()
        self.assertTrue(any(h['art'] == 'bankumsaetze_offen' for h in self.get('uebersicht')['hinweise']))


class RechenwegeTest(unittest.TestCase):
    """Jede Zeile aus 10.1 isoliert: Kostenbasis gegenüber realer Geldbewegung."""
    request = test_bereiche.BereicheTest.request

    def setUp(self):
        test_bereiche.BereicheTest.setUp(self)
        from app.bewegungen import kassa_fuer_sparte
        from app.bereiche import Bereich
        self.zahler = self.con.execute("SELECT id FROM sparte WHERE bereich_id=1 AND typ='privat' AND id<>? ORDER BY id", (self.haupt,)).fetchone()[0]
        self.konten = {}
        for sid in (self.haupt, self.zahler):
            kid = kassa_fuer_sparte(self.con, sid, Bereich(1))
            self.konten[sid] = kid
            self.con.execute("INSERT INTO kontostand_anker(konto_id,stichtag,saldo_cent,quelle) VALUES(?,'2025-12-31',100000,'manuell')", (kid,))
        self.con.commit()

    def buchen(self, cent=1000, **extra):
        payload = {'sparte_id': self.haupt, 'datum': '2026-03-01', 'typ': 'ausgabe', 'zahlungsart': 'bar',
                   'zeilen': [{'kategorie_id': self.kategorien[self.haupt], 'betrag_cent': cent}], **extra}
        status, data = self.request('POST', '/api/buchungen', payload)
        self.assertEqual(201, status, data)
        return data

    def sums(self, sid=None):
        from app.rechenbasis import Filter, summen
        return summen(self.con, Filter(sparte_id=sid or self.haupt, jahr=2026))

    def stand(self, sid=None):
        from app.konten import kontostand
        return kontostand(self.con, self.konten[sid or self.haupt], '2026-09-08')['stand_cent']

    def test_10_1_normale_einnahme_und_ausgabe(self):
        self.buchen()
        self.buchen(300, typ='einnahme')
        self.assertEqual({'einnahmen_cent': 300, 'ausgaben_cent': 1100, 'saldo_cent': -800}, self.sums())
        self.assertEqual(99300, self.stand())

    def test_10_1_umbuchung(self):
        status, data = self.request('POST', '/api/umbuchungen', {
            'von_sparte_id': self.haupt, 'nach_sparte_id': self.zahler,
            'datum': '2026-03-01', 'betrag_cent': 1000, 'zahlungsart': 'bar'})
        self.assertEqual(201, status, data)
        self.assertEqual(100, self.sums()['ausgaben_cent'])
        self.assertEqual(99000, self.stand())
        self.assertEqual(101000, self.stand(self.zahler))

    def rate(self):
        from app.bewegungen import synchronisiere_buchung
        from app.bereiche import Bereich
        b = self.buchen(200)
        self.con.execute('INSERT INTO buchungszeile(buchung_id,kategorie_id,betrag_cent,neutral) VALUES(?,?,800,1)',
                         (b['id'], self.kategorien[self.haupt]))
        synchronisiere_buchung(self.con, b['id'], Bereich(1))
        self.con.commit()

    def test_10_1_neutrale_tilgung(self):
        self.rate()
        self.assertEqual(300, self.sums()['ausgaben_cent'])
        self.assertEqual(99000, self.stand())

    def test_10_1_kreditzins(self):
        self.rate()
        status, rows = self.request('GET', f'/api/buchungen?kategorie_id={self.kategorien[self.haupt]}&jahr=2026')
        self.assertEqual(200, status)
        self.assertEqual(300, rows['summen']['ausgaben_cent'])
        self.assertEqual(800, rows['buchungen'][0]['neutral_cent'])
        self.assertEqual(99000, self.stand())

    def test_10_1_auslage(self):
        self.buchen(1000, bezahlt_von_sparte_id=self.zahler)
        self.assertEqual(1100, self.sums()['ausgaben_cent'])
        self.assertEqual(0, self.sums(self.zahler)['ausgaben_cent'])
        self.assertEqual(100000, self.stand())
        self.assertEqual(99000, self.stand(self.zahler))

    def test_10_1_ausgleich(self):
        b = self.buchen(1000, bezahlt_von_sparte_id=self.zahler)
        aid = self.con.execute('SELECT id FROM auslage WHERE buchung_id=?', (b['id'],)).fetchone()[0]
        before = self.con.execute('SELECT COUNT(*) FROM buchung').fetchone()[0]
        status, data = self.request('POST', '/api/ausgleiche', {
            'von_sparte_id': self.haupt, 'nach_sparte_id': self.zahler, 'auslage_ids': [aid],
            'datum': '2026-03-02', 'betrag_cent': 400, 'zahlungsart': 'bar'})
        self.assertEqual(201, status, data)
        self.assertEqual(before, self.con.execute('SELECT COUNT(*) FROM buchung').fetchone()[0])
        self.assertEqual(1100, self.sums()['ausgaben_cent'])
        self.assertEqual(99600, self.stand())
        self.assertEqual(99400, self.stand(self.zahler))

    def test_10_1_kassadifferenz(self):
        kid = self.con.execute("INSERT INTO kategorie(sparte_id,name,richtung) VALUES(?,'Kassadifferenz','beides')", (self.haupt,)).lastrowid
        self.con.commit()
        self.buchen(50, zeilen=[{'kategorie_id': kid, 'betrag_cent': 50}])
        self.assertEqual(150, self.sums()['ausgaben_cent'])
        self.assertEqual(99950, self.stand())

    def test_10_1_geloeschte_buchung(self):
        b = self.buchen()
        self.assertEqual(204, self.request('DELETE', f"/api/buchungen/{b['id']}")[0])
        self.assertEqual(100, self.sums()['ausgaben_cent'])
        self.assertEqual(100000, self.stand())

    def test_konten_je_waehrung_ohne_anker(self):
        self.con.execute("INSERT INTO bankkonto(name,waehrung) VALUES('Dollar','USD')")
        self.con.commit()
        status, u = self.request('GET', '/api/uebersicht?jahr=2026&stichtag=2026-09-08')
        self.assertEqual(200, status, u)
        self.assertEqual(200000, u['konten_je_waehrung']['EUR']['stand_cent'])
        self.assertIsNone(u['konten_je_waehrung']['USD']['stand_cent'])
        self.assertIsNone(next(k for k in u['konten'] if k['waehrung'] == 'USD')['stand_cent'])

    def test_kontencursor_gleiches_format(self):
        self.buchen(100)
        self.buchen(200)
        status, first = self.request('GET', f'/api/konten/{self.konten[self.haupt]}/bewegungen?limit=1')
        self.assertEqual(200, status)
        row = first['bewegungen'][0]
        self.assertEqual(f"{row['datum']}|{row['id']}", base64.b64decode(first['naechster_cursor']).decode())
        status, second = self.request('GET', f"/api/konten/{self.konten[self.haupt]}/bewegungen?limit=1&cursor={first['naechster_cursor']}")
        self.assertEqual(200, status)
        self.assertNotEqual(row['id'], second['bewegungen'][0]['id'])
