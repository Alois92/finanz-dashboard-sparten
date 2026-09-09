"""Bereichsgrenzen fuer Bank-, Regel- und Excel-Import-Endpunkte."""
import unittest
import test_bereiche


class BereicheImportTest(unittest.TestCase):
    setUp = test_bereiche.BereicheTest.setUp
    request = test_bereiche.BereicheTest.request

    def bankdaten(self):
        self.konten, self.umsaetze, self.regeln = {}, {}, {}
        for domain, sid in ((1, self.haupt), (2, self.verein)):
            konto = self.con.execute(
                'INSERT INTO bankkonto(name,sparte_id,bereich_id) VALUES(?,?,?)',
                (f'Konto {domain}', sid, domain),
            ).lastrowid
            umsatz = self.con.execute(
                "INSERT INTO bankumsatz(bankkonto_id,datum,betrag_cent,text,import_hash) VALUES(?,'2026-01-02',-100,'Marker',?)",
                (konto, f"hash-{domain}"),
            ).lastrowid
            regel = self.con.execute(
                "INSERT INTO regel(name,bedingung_text,ziel_sparte_id,ziel_kategorie_id,bereich_id) VALUES('Marker','marker',?,?,?)",
                (sid, self.kategorien[sid], domain),
            ).lastrowid
            self.konten[domain], self.umsaetze[domain], self.regeln[domain] = konto, umsatz, regel
        self.con.commit()

    def upload(self, endpoint, field, value):
        raw = (
            f'--p10\r\nContent-Disposition: form-data; name="{field}"\r\n\r\n{value}\r\n'
            '--p10\r\nContent-Disposition: form-data; name="datei"; filename="test.csv"\r\n'
            'Content-Type: text/csv\r\n\r\nDatum;Betrag\n01.01.2026;-1,00\r\n--p10--\r\n'
        ).encode()
        return self.request('POST', endpoint, raw=raw, content_type='multipart/form-data; boundary=p10')

    def test_lists_and_foreign_filters(self):
        self.bankdaten()
        for path, expected in (('bankkonten', self.konten), ('bankumsaetze', self.umsaetze), ('regeln', self.regeln)):
            for domain in (1, 2):
                status, rows = self.request('GET', f'/api/{path}?bereich_id={domain}')
                self.assertEqual(200, status)
                self.assertEqual([expected[domain]], [r['id'] for r in rows])
        self.assertEqual(404, self.request('GET', f'/api/bankumsaetze?bankkonto_id={self.konten[2]}')[0])
        self.assertEqual(404, self.request('GET', '/api/bankkonten?bereich_id=999')[0])

    def test_account_creation_and_import_reject_foreign_references(self):
        self.bankdaten()
        self.assertEqual(404, self.request('POST', '/api/bankkonten', {'name':'Fremd','sparte_id':self.verein})[0])
        status, row = self.request('POST', '/api/bankkonten?bereich_id=2', {'name':'Ungebunden'})
        self.assertEqual(201, status)
        self.assertEqual(2, self.con.execute('SELECT bereich_id FROM bankkonto WHERE id=?', (row['id'],)).fetchone()[0])
        self.assertEqual(404, self.upload('/api/import/csv','bankkonto_id',self.konten[2])[0])
        self.assertEqual(404, self.upload('/api/import/excel','sparte_id',self.verein)[0])
        self.assertEqual(200, self.upload('/api/import/csv?bereich_id=2','bankkonto_id',self.konten[2])[0])

    def test_foreign_mutations_are_404_and_do_not_write(self):
        self.bankdaten()
        body = {'sparte_id':self.haupt,'kategorie_id':self.kategorien[self.haupt]}
        before = list(self.con.iterdump())
        for endpoint, method, payload in (
            (f'/api/bankumsaetze/{self.umsaetze[2]}/verbuchen','POST',body),
            (f'/api/bankumsaetze/{self.umsaetze[1]}/verbuchen','POST',{**body,'kategorie_id':self.kategorien[self.verein]}),
            (f'/api/bankumsaetze/{self.umsaetze[2]}','PATCH',{'importstatus':'ignoriert'}),
            (f'/api/regeln/{self.regeln[2]}','PATCH',{'aktiv':0}),
            (f'/api/regeln/{self.regeln[2]}','DELETE',None),
        ):
            self.assertEqual(404, self.request(method,endpoint,payload)[0], endpoint)
        self.assertEqual(before, list(self.con.iterdump()))

    def test_batch_checks_all_ids_before_first_commit(self):
        self.bankdaten()
        before = list(self.con.iterdump())
        status, _ = self.request('POST','/api/bankumsaetze/vorschlaege-uebernehmen',{'umsatz_ids':[self.umsaetze[1],self.umsaetze[2]]})
        self.assertEqual(404,status)
        self.assertEqual(before,list(self.con.iterdump()))

    def test_rule_learning_stays_in_domain(self):
        self.bankdaten()
        foreign_before = tuple(self.con.execute('SELECT * FROM regel WHERE id=?',(self.regeln[1],)).fetchone())
        status, _ = self.request('POST', f'/api/bankumsaetze/{self.umsaetze[2]}/verbuchen?bereich_id=2', {'sparte_id':self.verein,'kategorie_id':self.kategorien[self.verein]})
        self.assertEqual(201,status)
        self.assertEqual(foreign_before,tuple(self.con.execute('SELECT * FROM regel WHERE id=?',(self.regeln[1],)).fetchone()))
        self.assertEqual(2,self.con.execute('SELECT COUNT(*) FROM regel').fetchone()[0])
        self.con.execute("DELETE FROM regel WHERE bereich_id=2")
        umsatz = self.con.execute(
            "INSERT INTO bankumsatz(bankkonto_id,datum,betrag_cent,text,import_hash) "
            "VALUES(?,'2026-01-03',-100,'Neues Muster','neuer-hash')",
            (self.konten[2],),
        ).lastrowid
        self.con.commit()
        status, _ = self.request(
            'POST', f'/api/bankumsaetze/{umsatz}/verbuchen?bereich_id=2',
            {'sparte_id': self.verein, 'kategorie_id': self.kategorien[self.verein]},
        )
        self.assertEqual(201, status)
        self.assertEqual(2, self.con.execute(
            "SELECT bereich_id FROM regel WHERE bedingung_text='neues muster'"
        ).fetchone()[0])

    def test_foreign_and_inconsistent_rules_are_not_proposed(self):
        self.bankdaten()
        self.con.execute('DELETE FROM regel WHERE bereich_id=1')
        self.con.execute("INSERT INTO regel(name,bedingung_text,ziel_sparte_id,ziel_kategorie_id,bereich_id) VALUES('Kaputt','marker',?,?,1)",(self.verein,self.kategorien[self.verein]))
        self.con.commit()
        status, rows = self.request('GET','/api/bankumsaetze')
        self.assertEqual(200,status)
        self.assertIsNone(rows[0]['vorschlag'])

    def test_domain_two_rule_and_batch_mutations(self):
        self.bankdaten()
        for aktiv in (0, 1):
            status, row = self.request(
                'PATCH', f'/api/regeln/{self.regeln[2]}?bereich_id=2', {'aktiv': aktiv},
            )
            self.assertEqual(200, status)
            self.assertEqual(self.regeln[2], row['id'])
        status, result = self.request(
            'POST', '/api/bankumsaetze/vorschlaege-uebernehmen?bereich_id=2',
            {'umsatz_ids': [self.umsaetze[2]]},
        )
        self.assertEqual(200, status)
        self.assertEqual({'verbucht': 1, 'uebersprungen': 0}, result)
        self.assertEqual('offen', self.con.execute(
            'SELECT importstatus FROM bankumsatz WHERE id=?', (self.umsaetze[1],),
        ).fetchone()[0])
        self.assertEqual(204, self.request(
            'DELETE', f'/api/regeln/{self.regeln[2]}?bereich_id=2',
        )[0])
