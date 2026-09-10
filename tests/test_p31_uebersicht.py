"""P31: Seite Übersicht - Auslieferung, Feldvertrag von /api/uebersicht, Node-Syntax."""
import pathlib
import subprocess
import sys
import unittest

import test_bereiche

ROOT = pathlib.Path(__file__).resolve().parents[1]


class UebersichtSeiteTest(unittest.TestCase):
    setUp = test_bereiche.BereicheTest.setUp
    request = test_bereiche.BereicheTest.request

    def get(self, route, query=''):
        status, data = self.request('GET', '/api/' + route + ('?' + query if query else ''))
        self.assertEqual(200, status, data)
        return data

    def test_seite_wird_ausgeliefert(self):
        status, body = self.request('GET', '/neu/pages/uebersicht.js')
        self.assertEqual(200, status)
        text = body.decode('utf-8') if isinstance(body, (bytes, bytearray)) else body
        self.assertIn('api/uebersicht'.split('/')[-1], text)  # 'uebersicht' referenziert
        self.assertIn("import {api}", text)

    def test_node_syntax_neue_und_geaenderte_dateien(self):
        node = None
        for name in ('node', 'node.exe'):
            found = subprocess.run(['where' if sys.platform == 'win32' else 'which', name],
                                    capture_output=True, text=True)
            if found.returncode == 0:
                node = name
                break
        if node is None:
            self.skipTest('node ist in dieser Umgebung nicht verfügbar')
        for relative in ('static-neu/pages/uebersicht.js', 'static-neu/pages/uebersicht.css',
                          'static-neu/charts.js'):
            path = ROOT / relative
            if path.suffix == '.css':
                continue  # node --check prueft nur JavaScript
            result = subprocess.run([node, '--check', str(path)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, f'{relative}: {result.stderr}')

    def _seed_zweiter_haupt_sparte_buchung(self):
        kat = self.con.execute(
            "SELECT id FROM kategorie WHERE sparte_id=?", (self.haupt,)).fetchone()[0]
        bid = self.con.execute(
            "INSERT INTO buchung(sparte_id,datum,typ,text) VALUES(?,?,?,?)",
            (self.haupt, '2026-03-01', 'einnahme', 'P31-Test-Einnahme')).lastrowid
        self.con.execute(
            "INSERT INTO buchungszeile(buchung_id,kategorie_id,betrag_cent) VALUES(?,?,?)",
            (bid, kat, 5000))
        self.con.commit()

    def test_bereichsgrenze_haupt_ohne_verein_sparte(self):
        self._seed_zweiter_haupt_sparte_buchung()
        u1 = self.get('uebersicht', f'bereich_id=1&jahr=2026&stichtag=2026-09-10')
        sparten1 = {s['sparte_id'] for s in u1['sparten']}
        self.assertNotIn(self.verein, sparten1)
        self.assertIn(self.haupt, sparten1)

    def test_bereichsgrenze_verein_nur_verein_sparte(self):
        u2 = self.get('uebersicht', f'bereich_id=2&jahr=2026&stichtag=2026-09-10')
        sparten2 = {s['sparte_id'] for s in u2['sparten']}
        self.assertEqual({self.verein}, sparten2)

    def test_uebersicht_enthaelt_alle_von_der_seite_gelesenen_felder(self):
        data = self.get('uebersicht', 'bereich_id=1&jahr=2026&stichtag=2026-09-10')
        for key in ('stichtag', 'jahr', 'ist', 'vorjahr_gesamt', 'erwartung', 'monate',
                    'sparten', 'top', 'hinweise', 'auslagen_offen', 'konten',
                    'konten_je_waehrung', 'datenstand'):
            self.assertIn(key, data, f'Feld {key} fehlt in /api/uebersicht')
        for key in ('einnahmen', 'ausgaben', 'vorjahr_einnahmen', 'vorjahr_ausgaben'):
            self.assertIn(key, data['monate'])
            self.assertEqual(12, len(data['monate'][key]))
        for key in ('ausgaben', 'einnahmen'):
            self.assertIn(key, data['top'])
        for sparte in data['sparten']:
            for key in ('sparte_id', 'name', 'kuerzel', 'farbe', 'einnahmen_cent',
                        'ausgaben_cent', 'saldo_cent'):
                self.assertIn(key, sparte)

    def test_hinweis_ausblenden_und_wieder_laden(self):
        self.con.execute("UPDATE buchung SET betrag_cent=100000 WHERE id=?", (self.buchungen[self.haupt],))
        self.con.execute("UPDATE buchungszeile SET betrag_cent=100000 WHERE buchung_id=?", (self.buchungen[self.haupt],))
        self.con.commit()
        data = self.get('uebersicht', 'bereich_id=1&jahr=2026&stichtag=2026-09-10')
        self.assertTrue(data['hinweise'], 'Testdaten sollten mindestens einen Hinweis erzeugen')
        hinweis = data['hinweise'][0]
        status, aus = self.request('POST', '/api/hinweise/aus?bereich_id=1',
                                   body={'schluessel': hinweis['schluessel'], 'bis_wert': hinweis['wert']})
        self.assertEqual(200, status, aus)
        self.assertEqual(hinweis['schluessel'], aus['schluessel'])
        status, liste = self.request('GET', '/api/hinweise/aus?bereich_id=1')
        self.assertEqual(200, status)
        self.assertTrue(any(e['schluessel'] == hinweis['schluessel'] for e in liste))
        neu = self.get('uebersicht', 'bereich_id=1&jahr=2026&stichtag=2026-09-10')
        self.assertNotIn(hinweis['schluessel'], {h['schluessel'] for h in neu['hinweise']})


if __name__ == '__main__':
    unittest.main()
