"""P12: Auslagen und Ausgleich über die echte ASGI-Anwendung."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import pathlib
import sqlite3
import tempfile
from threading import Barrier
import unittest

from app import db, migrate

import test_bereiche as bereiche_tests


class AuslagenTest(unittest.TestCase):
    request = bereiche_tests.BereicheTest.request

    def setUp(self):
        bereiche_tests.BereicheTest.setUp(self)
        self.zahler = self.con.execute(
            "SELECT id FROM sparte WHERE typ = 'privat' AND bereich_id = 1 ORDER BY id"
        ).fetchone()[0]
        self.hof = self.con.execute(
            "INSERT INTO sparte(name, typ) VALUES('Testhof', 'hof')"
        ).lastrowid
        self.kategorie = self.con.execute(
            "INSERT INTO kategorie(sparte_id, name, richtung) VALUES(?, 'Testkosten', 'beides')",
            (self.hof,),
        ).lastrowid
        self.con.commit()

    def payload(self, cent=10000, **extra):
        return {
            'sparte_id': self.hof, 'datum': '2026-01-01', 'typ': 'ausgabe',
            'zahlungsart': 'bar', 'bezahlt_von_sparte_id': self.zahler,
            'zeilen': [{'kategorie_id': self.kategorie, 'betrag_cent': cent}],
            **extra,
        }

    def auslage(self, cent=10000, **extra):
        status, b = self.request('POST', '/api/buchungen', self.payload(cent, **extra))
        self.assertEqual(201, status, b)
        aid = self.con.execute(
            'SELECT id FROM auslage WHERE buchung_id = ?', (b['id'],)
        ).fetchone()[0]
        return b, aid

    def ausgleich_payload(self, ids, cent=3000, **extra):
        return {
            'von_sparte_id': self.hof, 'nach_sparte_id': self.zahler,
            'auslage_ids': ids, 'datum': '2026-01-05', 'betrag_cent': cent,
            'zahlungsart': 'bar', **extra,
        }

    def stand(self, sid):
        return self.con.execute(
            "SELECT COALESCE(SUM(m.betrag_signed_cent), 0) FROM bewegung m "
            "JOIN bankkonto k ON k.id = m.konto_id "
            "WHERE k.sparte_id = ? AND k.art = 'kassa' AND m.storniert_am IS NULL",
            (sid,),
        ).fetchone()[0]

    def offen(self):
        status, groups = self.request('GET', '/api/auslagen')
        self.assertEqual(200, status, groups)
        return sum(g['offen_cent'] for g in groups)

    def test_auslage_teilausgleich_ruecknahme_und_kosten(self):
        vorher = [tuple(r) for r in self.con.execute('SELECT * FROM v_einnahmen_ausgaben')]
        b, aid = self.auslage()
        self.assertEqual((-10000, 0), (self.stand(self.zahler), self.stand(self.hof)))
        self.assertEqual(10000, self.offen())
        kosten = [tuple(r) for r in self.con.execute('SELECT * FROM v_einnahmen_ausgaben')]
        self.assertNotEqual(vorher, kosten)
        self.assertEqual(10000, self.con.execute(
            "SELECT SUM(betrag_cent) FROM v_einnahmen_ausgaben WHERE sparte_id = ? AND typ = 'ausgabe'",
            (self.hof,),
        ).fetchone()[0])
        self.assertEqual([r for r in vorher if r[2] == self.zahler],
                         [r for r in kosten if r[2] == self.zahler])
        status, a = self.request('POST', '/api/ausgleiche', self.ausgleich_payload([aid]))
        self.assertEqual(201, status, a)
        self.assertEqual([{'auslage_id': aid, 'betrag_cent': 3000}], a['zuordnungen'])
        self.assertEqual((-7000, -3000), (self.stand(self.zahler), self.stand(self.hof)))
        self.assertEqual(7000, self.offen())
        self.assertEqual(kosten, [tuple(r) for r in self.con.execute('SELECT * FROM v_einnahmen_ausgaben')])
        listed = self.request('GET', '/api/buchungen')[1]['buchungen']
        self.assertEqual(7000, next(r for r in listed if r['id'] == b['id'])['auslage']['offen_cent'])
        self.assertEqual(204, self.request('DELETE', f"/api/ausgleiche/{a['id']}")[0])
        self.assertEqual(10000, self.offen())
        self.assertEqual((-10000, 0), (self.stand(self.zahler), self.stand(self.hof)))
        self.assertIsNotNone(self.con.execute(
            'SELECT storniert_am FROM transfer WHERE id = ?', (a['transfer_id'],)
        ).fetchone()[0])

    def test_idempotenz_buchung_und_ausgleich(self):
        payload = self.payload(client_request_id='buchung-1')
        status, b = self.request('POST', '/api/buchungen', payload)
        self.assertEqual(201, status, b)
        self.assertEqual((200, b), self.request('POST', '/api/buchungen', payload))
        self.assertEqual(409, self.request('POST', '/api/buchungen', {**payload, 'text': 'anders'})[0])
        aid = self.con.execute('SELECT id FROM auslage').fetchone()[0]
        payload = self.ausgleich_payload([aid], client_request_id='ausgleich-1')
        status, a = self.request('POST', '/api/ausgleiche', payload)
        self.assertEqual(201, status, a)
        self.assertEqual((200, a), self.request('POST', '/api/ausgleiche', payload))
        self.assertEqual(409, self.request('POST', '/api/ausgleiche', {**payload, 'betrag_cent': 2000})[0])
        self.assertEqual(1, self.con.execute('SELECT COUNT(*) FROM ausgleich_zuordnung').fetchone()[0])
        self.assertEqual(422, self.request('POST', '/api/ausgleiche', self.ausgleich_payload([aid], 8000))[0])

    def test_version_und_zuordnungssperre(self):
        b, aid = self.auslage()
        a = self.request('POST', '/api/ausgleiche', self.ausgleich_payload([aid]))[1]
        path = f"/api/buchungen/{b['id']}"
        status, conflict = self.request('PUT', path, self.payload(2000, version=b['version']))
        self.assertEqual(409, status, conflict)
        self.assertEqual([a['id']], conflict['ausgleiche'])
        self.assertEqual(409, self.request('PUT', path, self.payload(version=99))[0])
        self.assertEqual(422, self.request('PUT', path, self.payload())[0])
        self.assertEqual(409, self.request('PUT', path, self.payload(
            version=b['version'], bezahlt_von_sparte_id=None,
        ))[0])
        self.assertEqual(404, self.request('PUT', path, self.payload(
            version=b['version'], bezahlt_von_sparte_id=self.verein,
        ))[0])
        status, updated = self.request('PUT', path, self.payload(12000, version=b['version']))
        self.assertEqual(200, status, updated)
        self.assertEqual(2, updated['version'])
        self.assertEqual(9000, self.offen())

    def test_validierung_fifo_stichtag_und_warnung(self):
        self.assertEqual(422, self.request('POST', '/api/buchungen', self.payload(typ='einnahme'))[0])
        self.assertEqual(404, self.request('POST', '/api/buchungen', self.payload(
            bezahlt_von_sparte_id=self.verein,
        ))[0])
        ids = [self.auslage(cent, datum=f'2026-01-0{day}')[1]
               for day, cent in ((1, 1000), (2, 2000), (3, 3000))]
        status, a = self.request('POST', '/api/ausgleiche', self.ausgleich_payload(ids[::-1], 2500))
        self.assertEqual(201, status, a)
        self.assertEqual([{'auslage_id': ids[0], 'betrag_cent': 1000},
                          {'auslage_id': ids[1], 'betrag_cent': 1500}], a['zuordnungen'])
        self.assertTrue(a['warnungen'])
        groups = self.request('GET', '/api/auslagen?stichtag=2026-01-03')[1]
        self.assertEqual(6000, groups[0]['offen_cent'])
        self.assertEqual(3500, self.offen())
        for extra in ({'datum': '2099-01-01'}, {'datum': '2025-12-31'},
                      {'datum': '2026-02-30'}, {'auslage_ids': [ids[2], ids[2]]},
                      {'zahlungsart': 'bank'}, {'betrag_cent': 1.5}):
            self.assertEqual(422, self.request('POST', '/api/ausgleiche',
                                             self.ausgleich_payload([ids[2]], 100, **extra))[0])

    def test_bereichsgrenzen_und_bankausgleich(self):
        _, aid = self.auslage()
        for query in (f'sparte_id={self.verein}', f'zahler_sparte_id={self.verein}',
                      'bereich_id=999'):
            self.assertEqual(404, self.request('GET', '/api/auslagen?' + query)[0])
        self.assertEqual([], self.request('GET', '/api/auslagen?bereich_id=2')[1])
        self.assertEqual(404, self.request('POST', '/api/ausgleiche?bereich_id=2',
                                         self.ausgleich_payload([aid]))[0])
        ids = []
        for sid in (self.hof, self.zahler):
            status, konto = self.request('POST', '/api/konten', {
                'name': 'Testbank', 'art': 'bank', 'sparte_id': sid,
            })
            self.assertEqual(201, status, konto)
            ids.append(konto['id'])
        payload = self.ausgleich_payload([aid], zahlungsart='bank',
                                         von_konto_id=ids[0], nach_konto_id=ids[1])
        self.assertEqual(422, self.request('POST', '/api/ausgleiche', {
            **payload, 'von_konto_id': ids[1],
        })[0])
        status, a = self.request('POST', '/api/ausgleiche', payload)
        self.assertEqual(201, status, a)
        self.assertEqual([], a['warnungen'])
        movements = [tuple(r) for r in self.con.execute(
            'SELECT konto_id, betrag_signed_cent, quelle FROM bewegung WHERE transfer_id = ? '
            'ORDER BY id', (a['transfer_id'],),
        )]
        self.assertEqual([(ids[0], -3000, 'ausgleich'), (ids[1], 3000, 'ausgleich')], movements)
        self.assertEqual(404, self.request('DELETE', f"/api/ausgleiche/{a['id']}?bereich_id=2")[0])
        self.assertEqual([], self.request('GET', '/api/ausgleiche?bereich_id=2')[1])
        self.assertEqual([], self.request('GET', '/api/ausgleiche?jahr=2025')[1])
        self.assertEqual(a['zuordnungen'], self.request(
            'GET', f'/api/ausgleiche?sparte_id={self.zahler}&jahr=2026',
        )[1][0]['zuordnungen'])
        self.assertEqual(404, self.request('GET', f'/api/ausgleiche?sparte_id={self.verein}')[0])

    def test_historie_replay_nach_aenderung_und_aufhebung(self):
        b, aid = self.auslage(client_request_id='historie-b')
        status, neu = self.request('PUT', f"/api/buchungen/{b['id']}", self.payload(
            11000, version=1,
        ))
        self.assertEqual(200, status, neu)
        self.assertEqual((200, b), self.request('POST', '/api/buchungen', self.payload(
            client_request_id='historie-b',
        )))
        payload = self.ausgleich_payload([aid], client_request_id='historie-a')
        _, a = self.request('POST', '/api/ausgleiche', payload)
        self.assertEqual(409, self.request('DELETE', f"/api/transfers/{a['transfer_id']}")[0])
        self.assertEqual(409, self.request('DELETE', f"/api/buchungen/{b['id']}")[0])
        self.assertEqual(204, self.request('DELETE', f"/api/ausgleiche/{a['id']}")[0])
        snapshot = '\n'.join(self.con.iterdump())
        self.assertEqual(204, self.request('DELETE', f"/api/ausgleiche/{a['id']}")[0])
        self.assertEqual((200, a), self.request('POST', '/api/ausgleiche', payload))
        self.assertEqual(snapshot, '\n'.join(self.con.iterdump()))
        self.assertEqual(409, self.request('PUT', f"/api/buchungen/{b['id']}", self.payload(
            version=2, bezahlt_von_sparte_id=None,
        ))[0])
        self.assertEqual(409, self.request('DELETE', f"/api/buchungen/{b['id']}")[0])

    def test_zeilen_ids_bleiben_stabil_und_fremde_werden_abgewiesen(self):
        b, _ = self.auslage()
        zeile = b['zeilen'][0]
        self.con.execute('UPDATE buchungszeile SET steuer_relevant = 1 WHERE id = ?', (zeile['id'],))
        self.con.commit()
        payload = self.payload(version=1, zeilen=[{**zeile, 'betrag_cent': 12000}])
        status, neu = self.request('PUT', f"/api/buchungen/{b['id']}", payload)
        self.assertEqual(200, status, neu)
        self.assertEqual(zeile['id'], neu['zeilen'][0]['id'])
        self.assertEqual(1, self.con.execute(
            'SELECT steuer_relevant FROM buchungszeile WHERE id = ?', (zeile['id'],)
        ).fetchone()[0])
        foreign = self.con.execute(
            'SELECT id FROM buchungszeile WHERE buchung_id = ?', (self.buchungen[self.verein],)
        ).fetchone()[0]
        self.assertEqual(404, self.request('PUT', f"/api/buchungen/{b['id']}", self.payload(
            version=2, zeilen=[{**zeile, 'id': foreign}],
        ))[0])

    def test_fehlgeschlagener_ausgleich_rollt_kassenanlage_zurueck(self):
        _, aid = self.auslage()
        self.con.execute("UPDATE bankkonto SET waehrung = 'USD' WHERE sparte_id = ?",
                         (self.zahler,))
        self.con.commit()
        vorher = '\n'.join(self.con.iterdump())
        self.assertEqual(422, self.request('POST', '/api/ausgleiche', self.ausgleich_payload([aid]))[0])
        self.assertEqual(vorher, '\n'.join(self.con.iterdump()))

    def test_replay_nach_kategoriestilllegung_und_unbenutzter_auslage(self):
        b, aid = self.auslage(client_request_id='stillgelegt')
        rest, rest_id = self.auslage(datum='2026-01-02')
        payload = self.ausgleich_payload([aid, rest_id], client_request_id='ungenutzt')
        status, a = self.request('POST', '/api/ausgleiche', payload)
        self.assertEqual(201, status, a)
        self.assertEqual(204, self.request('DELETE', f"/api/buchungen/{rest['id']}")[0])
        self.con.execute('UPDATE kategorie SET aktiv = 0 WHERE id = ?', (self.kategorie,))
        self.con.commit()
        self.assertEqual((200, b), self.request('POST', '/api/buchungen', self.payload(
            client_request_id='stillgelegt',
        )))
        self.assertEqual((200, a), self.request('POST', '/api/ausgleiche', payload))
        self.assertEqual(409, self.request('POST', '/api/ausgleiche?bereich_id=2', payload)[0])

    def test_kassawarnung_zehn_euro_und_volle_tilgung(self):
        b, aid = self.auslage()
        konto = self.request('POST', '/api/konten', {
            'name': 'Kassa Testhof', 'art': 'kassa', 'sparte_id': self.hof,
        })[1]
        self.request('POST', '/api/bewegungen', {
            'konto_id': konto['id'], 'datum': '2026-01-01', 'betrag_signed_cent': 1000,
        })
        status, a = self.request('POST', '/api/ausgleiche', self.ausgleich_payload([aid]))
        self.assertEqual(201, status, a)
        self.assertEqual(['Kassa Testhof hat nur 10,00 €, danach negativ'], a['warnungen'])
        self.assertEqual(201, self.request('POST', '/api/ausgleiche',
                                         self.ausgleich_payload([aid], 7000))[0])
        self.assertEqual([], self.request('GET', '/api/auslagen')[1])
        listed = next(r for r in self.request('GET', '/api/buchungen')[1]['buchungen'] if r['id'] == b['id'])
        self.assertEqual({'zahler_sparte_id': self.zahler, 'offen_cent': 0, 'ausgeglichen': True},
                         listed['auslage'])

    def test_textkorrektur_bei_zulaessigem_rueckdatiertem_ausgleich(self):
        _, a1 = self.auslage(1000)
        b, a2 = self.auslage(2000, datum='2026-01-10')
        status, a = self.request('POST', '/api/ausgleiche', self.ausgleich_payload([a1, a2], 2500))
        self.assertEqual(201, status, a)
        status, neu = self.request('PUT', f"/api/buchungen/{b['id']}", self.payload(
            2000, datum='2026-01-10', version=1, text='Korrigierter Text',
        ))
        self.assertEqual(200, status, neu)
        self.assertEqual('Korrigierter Text', neu['text'])

    def test_parallele_requests_serialisieren_offen_version_und_request_id(self):
        from fastapi import HTTPException
        from app.bereiche import Bereich
        from app.routers.auslagen import AusgleichIn, create_ausgleich
        from app.routers.buchungen import create_buchung, update_buchung
        from app.schemas import BuchungIn

        def parallel(aktion):
            barrier = Barrier(2)

            def run(_):
                with closing(sqlite3.connect(self.path)) as con:
                    con.row_factory = sqlite3.Row
                    con.execute('PRAGMA foreign_keys = ON')
                    barrier.wait(timeout=5)
                    try:
                        result = aktion(con)
                        return result.status_code if hasattr(result, 'status_code') else 201
                    except HTTPException as exc:
                        return exc.status_code

            with ThreadPoolExecutor(max_workers=2) as pool:
                return sorted(pool.map(run, range(2)))

        b, aid = self.auslage()
        modell = AusgleichIn(**self.ausgleich_payload([aid], 6000))
        self.assertEqual([201, 422], parallel(lambda con: create_ausgleich(modell, con, Bereich(1))))
        self.assertEqual(4000, self.offen())
        modell_b = BuchungIn(**self.payload(version=1, text='Neue Fassung'))
        self.assertEqual([201, 409], parallel(
            lambda con: update_buchung(b['id'], modell_b, con, Bereich(1)),
        ))
        neu = BuchungIn(**self.payload(client_request_id='parallel-b'))
        self.assertEqual([200, 201], parallel(lambda con: create_buchung(neu, con, Bereich(1))))
        self.assertEqual(1, self.con.execute(
            "SELECT COUNT(*) FROM buchung WHERE client_request_id = 'parallel-b'",
        ).fetchone()[0])


class AuslagenMigrationTest(unittest.TestCase):
    def test_nachzug_zweimal_und_schema_identisch(self):
        with tempfile.TemporaryDirectory(prefix='finanz-p12-migration-') as tmp:
            with closing(sqlite3.connect(pathlib.Path(tmp) / 'bestand.db')) as con:
                con.row_factory = sqlite3.Row
                con.executescript((pathlib.Path(__file__).parent / 'fixtures/schema_p11.sql').read_text(
                    encoding='utf-8',
                ))
                con.executescript(db.SEED.read_text(encoding='utf-8'))
                con.executemany('INSERT INTO schema_version(version, name) VALUES(?, ?)',
                                [(v, name) for v, name, _ in migrate.liste_migrationen() if v <= 4])
                con.commit()
                self.assertEqual([5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15], migrate.anwenden(con, None))
                snapshot = '\n'.join(con.iterdump())
                self.assertEqual([], migrate.anwenden(con, None))
                self.assertEqual(snapshot, '\n'.join(con.iterdump()))
                # Auch bereits vorhandene P12-Objekte ohne Versionsmarke sind wiederanwendbar.
                con.execute('DELETE FROM schema_version WHERE version = 5')
                con.commit()
                self.assertEqual([5], migrate.anwenden(con, None))
                self.assertEqual([], list(con.execute('PRAGMA foreign_key_check')))
                with closing(sqlite3.connect(pathlib.Path(tmp) / 'neu.db')) as neu:
                    neu.executescript(db.SCHEMA.read_text(encoding='utf-8'))
                    tables = [r[0] for r in neu.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
                    )]
                    self.assertEqual(tables, [r[0] for r in con.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
                    )])
                    for table in tables:
                        for pragma in ('table_info', 'foreign_key_list', 'index_list'):
                            self.assertEqual(
                                [tuple(r) for r in neu.execute(f'PRAGMA {pragma}({table})')],
                                [tuple(r) for r in con.execute(f'PRAGMA {pragma}({table})')],
                                (table, pragma),
                            )


if __name__ == '__main__':
    unittest.main()
