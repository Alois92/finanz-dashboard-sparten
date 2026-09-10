"""P11: echtes Schema, ASGI-Endpunkte und kopierte P10-Bestandsdaten."""
from contextlib import closing
import pathlib
import sqlite3
import tempfile
import unittest

from app import db, migrate
import test_bereiche as bereiche_tests


def bestand(con):
    con.executescript((pathlib.Path(__file__).parent / 'fixtures/schema_p10.sql').read_text(encoding='utf-8'))
    con.executemany("INSERT INTO schema_version(version,name) VALUES(?,?)", [(1,'schema_version'), (2,'import_batch_erkennung'), (3,'bereiche')])
    con.executescript("""
        INSERT INTO sparte(id,name,typ) VALUES(1,'Test A','privat'),(2,'Test B','hof');
        INSERT INTO bankkonto(id,name,sparte_id) VALUES(1,'Testbank',1);
        INSERT INTO kategorie(id,sparte_id,name,richtung) VALUES(1,1,'Test','beides'),(2,2,'Test','beides');
        INSERT INTO bankumsatz(id,bankkonto_id,datum,betrag_cent,import_hash) VALUES
          (1,1,'2026-01-01',-100,'a'),(2,1,'2026-01-02',200,'b'),(3,1,'2026-01-03',300,'c');
    """)
    rows = [(1,'ausgabe','bank',1,None,100), (1,'einnahme','bank',2,None,200),
            (1,'ausgabe','bar',None,None,50), (2,'einnahme','bar',None,None,80),
            (1,'umbuchung','bank',None,'bekannt',70), (2,'umbuchung','bank',None,'bekannt',70),
            (1,'umbuchung','bank',None,'offen',90), (2,'umbuchung','bank',None,'offen',90),
            (1,'ausgabe','karte',None,None,40)]
    for sid, typ, zahlung, uid, gruppe, cent in rows:
        bid = con.execute("INSERT INTO buchung(sparte_id,datum,typ,zahlungsart,bankumsatz_id,transfer_gruppe_id,bankkonto_id) VALUES(?,'2026-01-02',?,?,?,?,?)",
                          (sid,typ,zahlung,uid,gruppe,1 if uid or gruppe == 'bekannt' else None)).lastrowid
        con.execute("INSERT INTO buchungszeile(buchung_id,kategorie_id,betrag_cent) VALUES(?,?,?)",(bid,sid,cent))
    con.commit()


class KontenMigrationTest(unittest.TestCase):
    def test_bestandskopie_nachzug_und_schema_identisch(self):
        with tempfile.TemporaryDirectory(prefix='finanz-p11-') as tmp:
            with closing(sqlite3.connect(pathlib.Path(tmp)/'bestand.db')) as original:
                bestand(original)
                with closing(sqlite3.connect(pathlib.Path(tmp)/'kopie.db')) as con:
                    original.backup(con)
                    con.row_factory = sqlite3.Row
                    vorher = [dict(r) for r in con.execute('SELECT * FROM v_einnahmen_ausgaben')]
                    self.assertEqual([4, 5, 6, 7, 8, 9, 12], migrate.anwenden(con, None))
                    self.assertEqual(2, con.execute("SELECT count(*) FROM bankkonto WHERE art='kassa'").fetchone()[0])
                    self.assertEqual(3, con.execute("SELECT count(*) FROM bewegung WHERE quelle='import'").fetchone()[0])
                    self.assertEqual(2, con.execute('SELECT count(*) FROM transfer').fetchone()[0])
                    self.assertEqual(6, con.execute('SELECT count(*) FROM buchung_bewegung').fetchone()[0])
                    self.assertEqual(400, con.execute('SELECT sum(betrag_signed_cent) FROM bewegung WHERE konto_id=1').fetchone()[0])
                    self.assertEqual([-50,80], [r[0] for r in con.execute("SELECT sum(m.betrag_signed_cent) FROM bewegung m JOIN bankkonto k ON k.id=m.konto_id WHERE k.art='kassa' GROUP BY k.sparte_id ORDER BY k.sparte_id")])
                    self.assertIn('Konten ungeklärt', con.execute('SELECT notiz FROM transfer WHERE von_konto_id IS NULL').fetchone()[0])
                    snapshot = '\n'.join(con.iterdump())
                    self.assertEqual([], migrate.anwenden(con, None))
                    self.assertEqual(snapshot, '\n'.join(con.iterdump()))
                    migrate._lade_python_migration(db.BASE/'db/migrations/004_konten_bewegungen.py').up(con)
                    con.commit()
                    self.assertEqual(snapshot, '\n'.join(con.iterdump()))
                    nachher = [dict(r) for r in con.execute('SELECT * FROM v_einnahmen_ausgaben')]
                    self.assertEqual(
                        vorher,
                        [{k: z[k] for k in vorher[0]} for z in nachher] if vorher else nachher,
                    )
                    self.assertEqual([], list(con.execute('PRAGMA foreign_key_check')))
                    with closing(sqlite3.connect(':memory:')) as neu:
                        neu.executescript(db.SCHEMA.read_text(encoding='utf-8'))
                        tables = [r[0] for r in neu.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
                        self.assertEqual(tables, [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")])
                        for table in tables:
                            for pragma in ('table_info','foreign_key_list','index_list'):
                                self.assertEqual([tuple(r) for r in neu.execute(f'PRAGMA {pragma}({table})')], [tuple(r) for r in con.execute(f'PRAGMA {pragma}({table})')], (table,pragma))


class KontenApiTest(unittest.TestCase):
    setUp = bereiche_tests.BereicheTest.setUp
    request = bereiche_tests.BereicheTest.request
    payload = bereiche_tests.BereicheTest.payload

    def konto(self, **extra):
        status, result = self.request('POST','/api/konten', {'name':'Testkonto','art':'bank', **extra})
        self.assertEqual(201,status,result)
        return result['id']

    def stand(self, kid):
        status, result = self.request('GET',f'/api/konten/{kid}/stand')
        self.assertEqual(200,status,result)
        return result['saldo_cent']

    def test_konten_alias_validierung_und_bereich(self):
        self.assertEqual(422,self.request('POST','/api/konten',{'name':'Kassa','art':'kassa'})[0])
        kid = self.konto(art='kassa',sparte_id=self.haupt)
        self.assertEqual(409,self.request('POST','/api/konten',{'name':'Doppelt','art':'kassa','sparte_id':self.haupt})[0])
        self.assertEqual(self.request('GET','/api/konten'), self.request('GET','/api/bankkonten'))
        self.assertEqual(200,self.request('PATCH',f'/api/konten/{kid}',{'sortierung':5,'aktiv':0})[0])
        self.assertEqual(422,self.request('PATCH',f'/api/konten/{kid}',{'sparte_id':None})[0])
        self.assertEqual(404,self.request('POST','/api/konten',{'name':'Fremd','art':'bank','sparte_id':self.verein})[0])
        for path in (f'/api/konten/{kid}/stand',f'/api/konten/{kid}/bewegungen'):
            self.assertEqual(404,self.request('GET',path+'?bereich_id=2')[0])

    def test_bar_anlegen_aendern_loeschen(self):
        b = {**self.payload(), 'zahlungsart':'bar'}
        status, result = self.request('POST','/api/buchungen',b)
        self.assertEqual(201,status,result)
        kid = self.con.execute("SELECT id FROM bankkonto WHERE art='kassa' AND sparte_id=?",(self.haupt,)).fetchone()[0]
        self.assertEqual(-150,self.stand(kid))
        mid = self.con.execute('SELECT bewegung_id FROM buchung_bewegung WHERE buchung_id=?',(result['id'],)).fetchone()[0]
        b['typ'] = 'einnahme'
        b['version'] = result['version']
        self.assertEqual(200,self.request('PUT',f"/api/buchungen/{result['id']}",b)[0])
        self.assertEqual(150,self.stand(kid))
        self.assertEqual(mid,self.con.execute('SELECT bewegung_id FROM buchung_bewegung WHERE buchung_id=?',(result['id'],)).fetchone()[0])
        self.assertEqual(204,self.request('DELETE',f"/api/buchungen/{result['id']}")[0])
        self.assertEqual(0,self.stand(kid))
        self.assertIsNotNone(self.con.execute('SELECT storniert_am FROM bewegung WHERE id=?',(mid,)).fetchone()[0])

    def test_bankomat_storno_und_cursor(self):
        bank = self.konto(sparte_id=self.haupt)
        kassa = self.konto(art='kassa',sparte_id=self.haupt)
        status, transfer = self.request('POST','/api/transfers',{'art':'bankomat','von_konto_id':bank,'nach_konto_id':kassa,'datum':'2026-01-03','betrag_cent':1000})
        self.assertEqual(201,status,transfer)
        self.assertEqual((-1000,1000),(self.stand(bank),self.stand(kassa)))
        self.assertEqual(404,self.request('DELETE',f"/api/transfers/{transfer['id']}?bereich_id=2")[0])
        self.assertEqual(204,self.request('DELETE',f"/api/transfers/{transfer['id']}")[0])
        self.assertEqual((0,0),(self.stand(bank),self.stand(kassa)))
        for n in range(3):
            self.assertEqual(201,self.request('POST','/api/bewegungen',{'konto_id':bank,'datum':'2026-01-04','betrag_signed_cent':n+1})[0])
        result = self.request('GET',f'/api/konten/{bank}/bewegungen?limit=2')[1]
        next_page = self.request('GET',f"/api/konten/{bank}/bewegungen?limit=2&cursor={result['naechster_cursor']}")[1]
        self.assertEqual(4,len({r['id'] for r in result['bewegungen']+next_page['bewegungen']}))
        self.assertIsNotNone(next_page['bewegungen'][-1]['storniert_am'])
        self.assertIsNone(next_page['naechster_cursor'])
        self.assertEqual(422,self.request('GET',f'/api/konten/{bank}/bewegungen?cursor=kaputt')[0])

    def test_unbekannte_zahlung_und_fremdes_konto(self):
        kid = self.konto()
        self.assertEqual(201,self.request('POST','/api/buchungen',self.payload())[0])
        self.assertTrue(any(r.get('zahlungsstatus')=='Zahlung unbekannt' for r in self.request('GET','/api/buchungen')[1]))
        self.assertEqual(0,self.stand(kid))
        fremd = self.con.execute("INSERT INTO bankkonto(name,bereich_id) VALUES('Fremd',2)").lastrowid
        self.con.commit()
        self.assertEqual(404,self.request('POST','/api/buchungen',{**self.payload(),'bankkonto_id':fremd})[0])
        self.assertEqual(404,self.request('POST','/api/bewegungen',{'konto_id':fremd,'datum':'2026-01-01','betrag_signed_cent':5})[0])

    def test_import_verknuepfung_und_vorlaeufige_bewegung(self):
        kid = self.konto()
        status,b = self.request('POST','/api/buchungen',{**self.payload(),'bankkonto_id':kid})
        self.assertEqual(201,status,b)
        self.assertEqual(-150,self.stand(kid))
        uid = self.con.execute("INSERT INTO bankumsatz(bankkonto_id,datum,betrag_cent,import_hash) VALUES(?,'2026-01-02',-150,'test')",(kid,)).lastrowid
        self.con.commit()
        updated = {**self.payload(), 'bankkonto_id': kid, 'bankumsatz_id': uid, 'version': b['version']}
        self.assertEqual(200,self.request('PUT',f"/api/buchungen/{b['id']}",updated)[0])
        self.assertEqual(-150,self.stand(kid))
        self.assertEqual(1,self.con.execute("SELECT count(*) FROM bewegung WHERE quelle='import'").fetchone()[0])
        self.assertEqual(204,self.request('DELETE',f"/api/buchungen/{b['id']}")[0])
        self.assertEqual(-150,self.stand(kid))

    def test_csv_und_kassa_importverbot(self):
        import io
        from fastapi import UploadFile, HTTPException
        from app.routers.import_bank import import_csv, verbuche_umsatz, UmsatzVerbuchenIn
        kid = self.konto()
        def upload():
            return UploadFile(filename='test.csv',file=io.BytesIO(b'Datum;Betrag;Text\n01.01.2026;-1,50;Test\n'))
        result = import_csv(kid,upload(),self.con)
        self.assertEqual(1,result['neu'])
        self.assertEqual(-150,self.stand(kid))
        self.assertEqual(0,import_csv(kid,upload(),self.con)['neu'])
        uid = self.con.execute('SELECT id FROM bankumsatz WHERE bankkonto_id=?',(kid,)).fetchone()[0]
        verbuche_umsatz(uid,UmsatzVerbuchenIn(sparte_id=self.haupt,kategorie_id=self.kategorien[self.haupt]),self.con)
        self.assertEqual(-150,self.stand(kid))
        cash = self.konto(art='kassa',sparte_id=self.haupt)
        with self.assertRaises(HTTPException) as ctx:
            import_csv(cash,upload(),self.con)
        self.assertEqual(422,ctx.exception.status_code)

    def test_put_prueft_erhaltenen_umsatz_und_oeffnet_abgeloesten(self):
        kid = self.konto()
        other = self.konto()
        uid = self.con.execute("INSERT INTO bankumsatz(bankkonto_id,datum,betrag_cent,import_hash) VALUES(?,'2026-01-02',-150,'put')",(kid,)).lastrowid
        self.con.commit()
        payload = {**self.payload(),'bankkonto_id':kid,'bankumsatz_id':uid}
        status,b = self.request('POST','/api/buchungen',payload)
        self.assertEqual(201,status,b)
        self.assertEqual(422, self.request(
            'PUT', f"/api/buchungen/{b['id']}",
            {**self.payload(), 'bankkonto_id': other, 'version': b['version']},
        )[0])
        self.assertEqual(200, self.request(
            'PUT', f"/api/buchungen/{b['id']}",
            {**self.payload(), 'bankkonto_id': None, 'bankumsatz_id': None, 'version': b['version']},
        )[0])
        self.assertEqual('offen',self.con.execute('SELECT importstatus FROM bankumsatz WHERE id=?',(uid,)).fetchone()[0])

    def test_kompatible_barumbuchung_und_storno(self):
        sid = self.con.execute("INSERT INTO sparte(name,typ) VALUES('Testziel','privat')").lastrowid
        self.con.commit()
        status,t = self.request('POST','/api/umbuchungen',{'von_sparte_id':self.haupt,'nach_sparte_id':sid,'zahlungsart':'bar','datum':'2026-01-01','betrag_cent':250})
        self.assertEqual(201,status,t)
        self.assertEqual([-250,250],[r[0] for r in self.con.execute('SELECT betrag_signed_cent FROM bewegung WHERE transfer_id=? ORDER BY id',(t['transfer_id'],))])
        self.assertEqual(204,self.request('DELETE',f"/api/buchungen/{t['buchung_ids'][0]}")[0])
        self.assertEqual(0,self.con.execute('SELECT count(*) FROM bewegung WHERE transfer_id=? AND storniert_am IS NULL',(t['transfer_id'],)).fetchone()[0])

    def test_notiz_kann_keinen_fremden_transfer_stornieren(self):
        sid = self.con.execute("INSERT INTO sparte(name,typ) VALUES('Testziel','privat')").lastrowid
        self.con.commit()
        status,t = self.request('POST','/api/umbuchungen',{'von_sparte_id':self.haupt,'nach_sparte_id':sid,'datum':'2026-01-01','betrag_cent':50})
        self.assertEqual(201,status,t)
        ids = [self.request('POST','/api/konten?bereich_id=2',{'name':str(n),'art':'bank'})[1]['id'] for n in (1,2)]
        status,foreign = self.request('POST','/api/transfers?bereich_id=2',{'art':'umbuchung','von_konto_id':ids[0],'nach_konto_id':ids[1],'datum':'2026-01-01','betrag_cent':50,'notiz':'Nachzug Umbuchung '+t['transfer_gruppe_id']})
        self.assertEqual(201,status,foreign)
        self.assertEqual(204,self.request('DELETE',f"/api/buchungen/{t['buchung_ids'][0]}")[0])
        self.assertIsNone(self.con.execute('SELECT storniert_am FROM transfer WHERE id=?',(foreign['id'],)).fetchone()[0])

    def test_geteilten_import_loeschen_und_transferimport_erhalten(self):
        from app.bewegungen import import_bewegung
        from app.bereiche import Bereich
        kid = self.konto()
        uid = self.con.execute("INSERT INTO bankumsatz(bankkonto_id,datum,betrag_cent,import_hash) VALUES(?,'2026-01-02',-300,'geteilt')",(kid,)).lastrowid
        self.con.commit()
        payload = {**self.payload(),'bankkonto_id':kid,'bankumsatz_id':uid}
        ids = [self.request('POST','/api/buchungen',payload)[1]['id'] for _ in range(2)]
        self.assertEqual(204,self.request('DELETE',f'/api/buchungen/{ids[0]}')[0])
        self.assertEqual('verbucht',self.con.execute('SELECT importstatus FROM bankumsatz WHERE id=?',(uid,)).fetchone()[0])
        mid = import_bewegung(self.con,uid,Bereich(1))
        target = self.konto()
        tid = self.con.execute("INSERT INTO transfer(art,von_konto_id,nach_konto_id,datum,betrag_cent) VALUES('umbuchung',?,?,'2026-01-02',300)",(kid,target)).lastrowid
        self.con.execute("UPDATE bewegung SET art='transfer',transfer_id=? WHERE id=?",(tid,mid))
        self.con.commit()
        self.assertEqual(204,self.request('DELETE',f'/api/buchungen/{ids[1]}')[0])
        self.assertEqual(-300,self.stand(kid))
        self.assertIsNone(self.con.execute('SELECT storniert_am FROM bewegung WHERE id=?',(mid,)).fetchone()[0])
