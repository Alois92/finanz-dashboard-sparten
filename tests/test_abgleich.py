"""F-N4: Manueller Bankumsatz wird beim Abgleich nur einmal gezählt."""
import unittest

import test_konten_bewegungen as konten_tests


class AbgleichTest(unittest.TestCase):
    setUp = konten_tests.KontenApiTest.setUp
    request = konten_tests.KontenApiTest.request
    payload = konten_tests.KontenApiTest.payload
    konto = konten_tests.KontenApiTest.konto
    stand = konten_tests.KontenApiTest.stand

    def buchung(self, konto, datum='2026-01-02', cent=150, typ='ausgabe'):
        payload = {**self.payload(), 'bankkonto_id': konto, 'datum': datum, 'typ': typ}
        payload['zeilen'][0]['betrag_cent'] = cent
        status, body = self.request('POST', '/api/buchungen', payload)
        self.assertEqual(201, status, body)
        return body['id']

    def umsatz(self, konto, datum='03.01.2026', betrag='-1,50', text='Banktest'):
        raw = (f'--n4\r\nContent-Disposition: form-data; name="bankkonto_id"\r\n\r\n{konto}\r\n'
               '--n4\r\nContent-Disposition: form-data; name="datei"; filename="test.csv"\r\n'
               'Content-Type: text/csv\r\n\r\nDatum;Betrag;Text\n'
               f'{datum};{betrag};{text}\n\r\n--n4--\r\n').encode()
        status, body = self.request('POST', '/api/import/csv', raw=raw,
                                    content_type='multipart/form-data; boundary=n4')
        self.assertEqual(200, status, body)
        return self.con.execute('SELECT id FROM bankumsatz WHERE bankkonto_id=? ORDER BY id DESC', (konto,)).fetchone()[0]

    def zuordnen(self, uid, bid):
        return self.request('POST', f'/api/bankumsaetze/{uid}/zuordnen', {'buchung_id': bid})

    def loesen(self, uid):
        return self.request('POST', f'/api/bankumsaetze/{uid}/zuordnung-loesen')

    def test_abgleich_und_loesen_idempotent_mit_echten_staenden(self):
        kid = self.konto()
        self.request('POST', f'/api/konten/{kid}/anker',
                     {'stichtag': '2026-01-01', 'saldo_cent': 1000, 'quelle': 'manuell'})
        bid = self.buchung(kid)
        mid = self.con.execute('SELECT bewegung_id FROM buchung_bewegung WHERE buchung_id=?', (bid,)).fetchone()[0]
        uid = self.umsatz(kid)
        self.assertEqual(-300, self.stand(kid))
        self.assertEqual(700, self.request('GET', f'/api/konten/{kid}/stand')[1]['stand_cent'])
        status, body = self.request('GET', f'/api/bankumsaetze/{uid}/kandidaten')
        self.assertEqual((200, {'kandidaten': [{'buchung_id': bid, 'datum': '2026-01-02',
                          'betrag_cent': -150, 'text': 'Lernmarker', 'abstand_tage': 1}]}), (status, body))
        vorher = self.request('GET', f'/api/konten/{kid}/offene-abgleiche')
        self.assertEqual(200, vorher[0])
        self.assertEqual((1, 1), (vorher[1]['manuelle_anzahl'], vorher[1]['umsaetze_anzahl']))
        zeilen = list(self.con.execute('SELECT * FROM buchungszeile WHERE buchung_id=?', (bid,)))
        antwort = self.zuordnen(uid, bid)
        self.assertEqual(200, antwort[0], antwort)
        self.assertEqual(antwort, self.zuordnen(uid, bid))
        self.assertEqual(-150, self.stand(kid))
        self.assertEqual(850, self.request('GET', f'/api/konten/{kid}/stand')[1]['stand_cent'])
        self.assertIsNotNone(self.con.execute('SELECT storniert_am FROM bewegung WHERE id=?', (mid,)).fetchone()[0])
        self.assertEqual([], self.request('GET', f'/api/bankumsaetze/{uid}/kandidaten')[1]['kandidaten'])
        self.assertEqual(0, self.request('GET', f'/api/konten/{kid}/offene-abgleiche')[1]['manuelle_anzahl'])
        self.assertEqual(200, self.loesen(uid)[0])
        self.assertEqual(200, self.loesen(uid)[0])
        self.assertEqual(-300, self.stand(kid))
        self.assertIsNone(self.con.execute('SELECT storniert_am FROM bewegung WHERE id=?', (mid,)).fetchone()[0])
        self.assertEqual(vorher, self.request('GET', f'/api/konten/{kid}/offene-abgleiche'))
        self.assertEqual(zeilen, list(self.con.execute('SELECT * FROM buchungszeile WHERE buchung_id=?', (bid,))))
        self.assertEqual(200, self.zuordnen(uid, bid)[0])
        self.assertEqual(2, self.con.execute('SELECT count(*) FROM bewegung WHERE konto_id=?', (kid,)).fetchone()[0])

    def test_kandidaten_datum_sortierung_vorzeichen_und_konto(self):
        kid = self.konto()
        ids = [self.buchung(kid, datum=d) for d in ('2026-01-08', '2026-01-02', '2026-01-03', '2025-12-29')]
        self.buchung(kid, datum='2026-01-09')
        self.buchung(kid, datum='2025-12-28')
        self.buchung(kid, cent=151)
        self.buchung(self.konto())
        self.con.execute("UPDATE kategorie SET richtung='beides' WHERE id=?", (self.kategorien[self.haupt],))
        self.con.commit()
        self.buchung(kid, typ='einnahme')
        uid = self.umsatz(kid)
        status, body = self.request('GET', f'/api/bankumsaetze/{uid}/kandidaten')
        self.assertEqual(200, status, body)
        self.assertEqual([ids[2], ids[1], ids[3], ids[0]], [r['buchung_id'] for r in body['kandidaten']])

    def test_konflikte_und_bereich_ohne_aenderung(self):
        kid = self.konto()
        bid = self.buchung(kid)
        falsch = self.buchung(kid, cent=151)
        uid = self.umsatz(kid)
        for fremd in (falsch, self.buchung(self.konto())):
            status, body = self.zuordnen(uid, fremd)
            self.assertEqual(409, status, body)
            self.assertIn('detail', body)
        for method, path, body in (
            ('GET', f'/bankumsaetze/{uid}/kandidaten', None),
            ('POST', f'/bankumsaetze/{uid}/zuordnen', {'buchung_id': bid}),
            ('POST', f'/bankumsaetze/{uid}/zuordnung-loesen', None),
            ('GET', f'/konten/{kid}/offene-abgleiche', None),
        ):
            self.assertEqual(404, self.request(method, '/api'+path+'?bereich_id=2', body)[0])
        self.assertEqual(404, self.zuordnen(uid, self.buchungen[self.verein])[0])
        self.assertEqual(-451, self.stand(kid))
        self.assertEqual(200, self.zuordnen(uid, bid)[0])
        self.assertEqual(409, self.zuordnen(uid, self.buchung(kid))[0])
        other = self.umsatz(kid, text='Anderer Umsatz')
        self.assertEqual(409, self.zuordnen(other, bid)[0])

    def test_bestehendes_verbuchen_nicht_loesen(self):
        kid = self.konto()
        uid = self.umsatz(kid)
        status, body = self.request('POST', f'/api/bankumsaetze/{uid}/verbuchen',
                                    {'sparte_id': self.haupt, 'kategorie_id': self.kategorien[self.haupt]})
        self.assertEqual(201, status, body)
        self.assertEqual(409, self.loesen(uid)[0])
        self.assertEqual(-150, self.stand(kid))

    def test_put_erhaelt_ruecknahme_und_version(self):
        kid = self.konto()
        bid = self.buchung(kid)
        uid = self.umsatz(kid)
        self.assertEqual(200, self.zuordnen(uid, bid)[0])
        payload = {**self.payload(), 'bankkonto_id': kid, 'version': 1, 'text': 'Korrigiert'}
        self.assertEqual(409, self.request('PUT', f'/api/buchungen/{bid}', payload)[0])
        payload['version'] = 2
        self.assertEqual(200, self.request('PUT', f'/api/buchungen/{bid}', payload)[0])
        self.assertEqual(200, self.loesen(uid)[0])
        self.assertEqual(-300, self.stand(kid))

    def test_loesen_nach_betragsaenderung_stellt_aktuelle_buchung_her(self):
        kid = self.konto()
        bid = self.buchung(kid)
        uid = self.umsatz(kid)
        self.assertEqual(200, self.zuordnen(uid, bid)[0])
        payload = {**self.payload(), 'bankkonto_id': kid, 'version': 2}
        payload['zeilen'][0]['betrag_cent'] = 200
        self.assertEqual(200, self.request('PUT', f'/api/buchungen/{bid}', payload)[0])
        self.assertEqual(200, self.loesen(uid)[0])
        self.assertEqual(-350, self.stand(kid))

    def test_put_darf_konto_nicht_entfernen_solange_abgeglichen(self):
        kid = self.konto()
        bid = self.buchung(kid)
        uid = self.umsatz(kid)
        self.assertEqual(200, self.zuordnen(uid, bid)[0])
        payload = {**self.payload(), 'bankkonto_id': None, 'version': 2}
        self.assertEqual(409, self.request('PUT', f'/api/buchungen/{bid}', payload)[0])
        self.assertEqual(200, self.loesen(uid)[0])

    def test_einnahme_und_gegenzeichen(self):
        kid = self.konto()
        self.con.execute("UPDATE kategorie SET richtung='beides' WHERE id=?", (self.kategorien[self.haupt],))
        self.con.commit()
        ausgabe = self.buchung(kid)
        einnahme = self.buchung(kid, typ='einnahme')
        uid = self.umsatz(kid, betrag='1,50')
        self.assertEqual(409, self.zuordnen(uid, ausgabe)[0])
        self.assertEqual(200, self.zuordnen(uid, einnahme)[0])
        self.assertEqual(0, self.stand(kid))

    def test_offene_liste_ohne_kandidat_ignoriert_und_storniert(self):
        kid = self.konto()
        self.buchung(kid)
        uid = self.umsatz(kid)
        self.umsatz(kid, betrag='-9,99')
        self.request('POST', '/api/bewegungen', {'konto_id': kid, 'datum': '2026-01-01', 'betrag_signed_cent': 50})
        status, body = self.request('GET', f'/api/konten/{kid}/offene-abgleiche')
        self.assertEqual(200, status)
        self.assertEqual((2, 1), (body['manuelle_anzahl'], body['umsaetze_anzahl']))
        self.request('PATCH', f'/api/bankumsaetze/{uid}', {'importstatus': 'ignoriert'})
        self.assertEqual([], self.request('GET', f'/api/konten/{kid}/offene-abgleiche')[1]['offene_umsaetze'])
        self.assertEqual([], self.request('GET', f'/api/bankumsaetze/{uid}/kandidaten')[1]['kandidaten'])

    def test_schreibfehler_rollt_gesamte_zuordnung_zurueck(self):
        import sqlite3
        from app.abgleich import zuordnen
        from app.bereiche import Bereich
        kid = self.konto()
        bid = self.buchung(kid)
        uid = self.umsatz(kid)
        self.con.executescript("""CREATE TRIGGER n4_fehler BEFORE INSERT ON buchung_bewegung
            BEGIN SELECT RAISE(ABORT, 'Testabbruch'); END;""")
        with self.assertRaises(sqlite3.IntegrityError):
            zuordnen(self.con, uid, bid, Bereich(1))
        self.assertEqual(-300, self.stand(kid))
        self.assertIsNone(self.con.execute('SELECT bankumsatz_id FROM buchung WHERE id=?', (bid,)).fetchone()[0])
        self.assertEqual('offen', self.con.execute('SELECT importstatus FROM bankumsatz WHERE id=?', (uid,)).fetchone()[0])
        self.assertFalse(self.con.in_transaction)

    def test_loesen_nach_neuer_db_verbindung(self):
        import sqlite3
        from app.abgleich import loesen
        from app.bereiche import Bereich
        kid = self.konto()
        bid = self.buchung(kid)
        uid = self.umsatz(kid)
        self.assertEqual(200, self.zuordnen(uid, bid)[0])
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        try:
            self.assertEqual('offen', loesen(con, uid, Bereich(1))['importstatus'])
        finally:
            con.close()
        self.assertEqual(-300, self.stand(kid))

    def test_parallele_zuordnungen_belegen_umsatz_nur_einmal(self):
        from concurrent.futures import ThreadPoolExecutor
        import sqlite3
        from fastapi import HTTPException
        from app.abgleich import zuordnen
        from app.bereiche import Bereich
        kid = self.konto()
        bids = [self.buchung(kid), self.buchung(kid)]
        uid = self.umsatz(kid)

        def assign(bid):
            con = sqlite3.connect(self.path)
            con.row_factory = sqlite3.Row
            try:
                zuordnen(con, uid, bid, Bereich(1))
                return 200
            except HTTPException as exc:
                return exc.status_code
            finally:
                con.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual([200, 409], sorted(pool.map(assign, bids)))
        self.assertEqual(-300, self.stand(kid))
        self.assertEqual(1, self.con.execute('SELECT count(*) FROM buchung WHERE bankumsatz_id=?', (uid,)).fetchone()[0])

    def test_loesefehler_rollt_alle_aenderungen_zurueck(self):
        import sqlite3
        from app.abgleich import loesen
        from app.bereiche import Bereich
        kid = self.konto()
        bid = self.buchung(kid)
        uid = self.umsatz(kid)
        self.assertEqual(200, self.zuordnen(uid, bid)[0])
        self.con.executescript("""CREATE TRIGGER n4_fehler BEFORE UPDATE ON bankumsatz
            BEGIN SELECT RAISE(ABORT, 'Testabbruch'); END;""")
        with self.assertRaises(sqlite3.IntegrityError):
            loesen(self.con, uid, Bereich(1))
        self.assertEqual(-150, self.stand(kid))
        self.assertEqual(uid, self.con.execute('SELECT bankumsatz_id FROM buchung WHERE id=?', (bid,)).fetchone()[0])
        self.assertEqual(2, self.con.execute('SELECT count(*) FROM buchung_bewegung WHERE buchung_id=?', (bid,)).fetchone()[0])

    def test_unbekannte_ids_und_strikter_body(self):
        kid = self.konto()
        uid = self.umsatz(kid)
        self.assertEqual(404, self.zuordnen(uid, 99999)[0])
        for method, suffix in (('GET', 'kandidaten'), ('POST', 'zuordnung-loesen')):
            self.assertEqual(404, self.request(method, f'/api/bankumsaetze/99999/{suffix}')[0])
        self.assertEqual(404, self.request('GET', '/api/konten/99999/offene-abgleiche')[0])
        for value in ('3', True, 1.5, 0, None):
            self.assertEqual(422, self.zuordnen(uid, value)[0])
