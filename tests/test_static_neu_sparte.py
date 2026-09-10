"""P32: Seite Sparte - Auslieferung, Node-Syntax, Feldvertrag der fünf verwendeten Endpoints."""
import pathlib
import subprocess
import sys
import unittest

import test_bereiche

ROOT = pathlib.Path(__file__).resolve().parents[1]


class SparteSeiteTest(unittest.TestCase):
    setUp = test_bereiche.BereicheTest.setUp
    request = test_bereiche.BereicheTest.request

    def get(self, route, query=''):
        status, data = self.request('GET', '/api/' + route + ('?' + query if query else ''))
        self.assertEqual(200, status, data)
        return data

    def _kategorien(self):
        ein = self.con.execute(
            "INSERT INTO kategorie(sparte_id,name,richtung) VALUES(?,?,?)",
            (self.haupt, 'P32-Miete', 'einnahme'),
        ).lastrowid
        aus = self.con.execute(
            "INSERT INTO kategorie(sparte_id,name,richtung) VALUES(?,?,?)",
            (self.haupt, 'P32-Instandhaltung', 'ausgabe'),
        ).lastrowid
        self.con.commit()
        return ein, aus

    def _buchung(self, kategorie_id, typ, cent, datum):
        bid = self.con.execute(
            "INSERT INTO buchung(sparte_id,datum,typ,text) VALUES(?,?,?,?)",
            (self.haupt, datum, typ, f'P32-{typ}'),
        ).lastrowid
        self.con.execute(
            "INSERT INTO buchungszeile(buchung_id,kategorie_id,betrag_cent) VALUES(?,?,?)",
            (bid, kategorie_id, cent),
        )
        self.con.commit()
        return bid

    # ---------- Auslieferung ----------

    def test_seite_wird_ausgeliefert(self):
        status, body = self.request('GET', '/neu/pages/sparte.js')
        self.assertEqual(200, status)
        text = body.decode('utf-8') if isinstance(body, (bytes, bytearray)) else body
        self.assertIn("import {api}", text)
        for endpoint in ('/uebersicht', '/jahresmatrix', '/kennzahlen', '/auslagen', '/konten'):
            self.assertIn(endpoint, text, f'{endpoint} wird von der Seite nicht referenziert')

    def test_node_syntax(self):
        node = None
        for name in ('node', 'node.exe'):
            found = subprocess.run(['where' if sys.platform == 'win32' else 'which', name],
                                    capture_output=True, text=True)
            if found.returncode == 0:
                node = name
                break
        if node is None:
            self.skipTest('node ist in dieser Umgebung nicht verfügbar')
        result = subprocess.run([node, '--check', str(ROOT / 'static-neu/pages/sparte.js')],
                                 capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)

    # ---------- Kennzahl: Wert kommt fertig vom Server, keine Neuberechnung im Frontend ----------
    #
    # GET /api/kennzahlen ist beim Bauen dieser Karte als grundsätzlich defekt aufgefallen:
    # app/routers/kennzahlen.py Zeile 67-70 selektiert "id" unqualifiziert aus einem Join von
    # kennzahl UND sparte (beide haben eine Spalte "id") - das schlägt bei jedem Aufruf mit
    # "sqlite3.OperationalError: ambiguous column name: id" fehl, unabhängig von sparte_id/jahr.
    # Diese Karte darf laut Auftrag keine Backend-Datei ändern ("keine Backend-Änderung"), daher
    # bleibt der Fehler bestehen; die Seite fängt ihn clientseitig ab (Toast statt Absturz), die
    # betroffenen Tests überspringen sich selbst mit Verweis auf den Bericht. Siehe
    # docs/neubau/berichte/P32-runde1.md, Abschnitt "Wunsch ans Gerüst / gefundener Fehler".

    def _kennzahlen_get(self, query):
        # Der frühere Selbst-Skip (ambiguous column name: id) ist seit dem Kopf-Nachzug in
        # app/routers/kennzahlen.py nicht mehr nötig; Fehler sollen hier echt fehlschlagen.
        return self.request('GET', '/api/' + 'kennzahlen' + ('?' + query if query else ''))

    def test_kennzahl_wert_gleich_einnahmen_minus_ausgaben(self):
        ein, aus = self._kategorien()
        self._buchung(ein, 'einnahme', 100000, '2026-02-01')
        self._buchung(aus, 'ausgabe', 30000, '2026-03-01')
        status, kennzahl = self.request('POST', '/api/kennzahlen', {
            'sparte_id': self.haupt, 'name': 'P32-Testkennzahl',
            'terme': [
                {'kategorie_id': ein, 'messgroesse': 'einnahmen', 'vorzeichen': 1},
                {'kategorie_id': aus, 'messgroesse': 'ausgaben', 'vorzeichen': -1},
            ],
        })
        self.assertEqual(201, status, kennzahl)
        status, data = self._kennzahlen_get(f'sparte_id={self.haupt}&jahr=2026')
        self.assertEqual(200, status, data)
        eintrag = next(k for k in data if k['id'] == kennzahl['id'])
        self.assertEqual(70000, eintrag['wert_cent'])
        self.assertIn('monatsdurchschnitt_cent', eintrag)

    # ---------- Jahresmatrix: stillgelegte Kategorie bleibt mit Historie sichtbar ----------

    def test_jahresmatrix_enthaelt_stillgelegte_kategorie(self):
        _, aus = self._kategorien()
        alt = self.con.execute(
            "INSERT INTO kategorie(sparte_id,name,richtung) VALUES(?,?,?)",
            (self.haupt, 'P32-Stillgelegt', 'ausgabe'),
        ).lastrowid
        self.con.commit()
        self._buchung(alt, 'ausgabe', 12000, '2025-05-01')
        self.con.execute("UPDATE kategorie SET aktiv=0 WHERE id=?", (alt,))
        self.con.commit()
        data = self.get('jahresmatrix', f'sparte_id={self.haupt}&jahre=2025,2026')
        zeile = next((z for z in data['zeilen'] if z['kategorie_id'] == alt), None)
        self.assertIsNotNone(zeile, 'stillgelegte Kategorie fehlt in der Matrix')
        self.assertEqual(0, zeile['aktiv'])
        self.assertEqual(12000, zeile['werte']['2025']['ausgaben_cent'])

    # ---------- Auslagen: Ziel-Sparte und Zahler-Sparte beide auffindbar ----------

    def test_auslage_ueber_sparte_id_und_zahler_sparte_id_auffindbar(self):
        _, aus = self._kategorien()
        zahler = self.con.execute(
            "INSERT INTO sparte(name,typ) VALUES('P32-Zahler','privat')"
        ).lastrowid
        self.con.commit()
        status, buchung = self.request('POST', '/api/buchungen', {
            'sparte_id': self.haupt, 'datum': '2026-01-10', 'typ': 'ausgabe',
            'zahlungsart': 'bar', 'bezahlt_von_sparte_id': zahler,
            'zeilen': [{'kategorie_id': aus, 'betrag_cent': 5000}],
        })
        self.assertEqual(201, status, buchung)
        als_ziel = self.get('auslagen', f'sparte_id={self.haupt}')
        self.assertEqual(1, len(als_ziel))
        self.assertEqual(zahler, als_ziel[0]['zahler_sparte_id'])
        self.assertEqual(5000, als_ziel[0]['offen_cent'])
        als_zahler = self.get('auslagen', f'zahler_sparte_id={zahler}')
        self.assertEqual(1, len(als_zahler))
        self.assertEqual(self.haupt, als_zahler[0]['sparte_id'])

    # ---------- Kassa: /api/konten liefert alle Konten des Bereichs, Seite filtert client-seitig ----------

    def test_kassa_konto_ueber_konten_liste_auffindbar(self):
        status, konto = self.request('POST', '/api/konten', {
            'name': 'P32-Kassa', 'art': 'kassa', 'sparte_id': self.haupt,
        })
        self.assertEqual(201, status, konto)
        konten = self.get('konten')
        treffer = [k for k in konten if k['art'] == 'kassa' and k['sparte_id'] == self.haupt]
        self.assertEqual(1, len(treffer))
        for key in ('stand_cent', 'datenstand', 'hinweis'):
            self.assertIn(key, treffer[0])

    # ---------- Feldvertrag: die vier funktionierenden Endpoints aus Abschnitt 3 ----------
    # (GET /api/kennzahlen ist derzeit defekt, siehe oben - eigener Test test_kennzahl_wert_...)

    def test_antwortform_der_vier_funktionierenden_endpoints(self):
        ein, aus = self._kategorien()
        self._buchung(ein, 'einnahme', 50000, '2026-02-01')
        self._buchung(aus, 'ausgabe', 15000, '2026-03-01')
        self.request('POST', '/api/konten', {'name': 'P32-Kassa2', 'art': 'kassa', 'sparte_id': self.haupt})

        uebersicht = self.get('uebersicht', f'sparte_id={self.haupt}&jahr=2026&stichtag=2026-09-10')
        for key in ('jahr', 'ist', 'erwartung', 'vorjahr_gesamt', 'monate', 'top'):
            self.assertIn(key, uebersicht)
        for key in ('einnahmen', 'ausgaben', 'vorjahr_einnahmen', 'vorjahr_ausgaben'):
            self.assertIn(key, uebersicht['monate'])
        for key in ('ausgaben', 'einnahmen'):
            self.assertIn(key, uebersicht['top'])
        if uebersicht['top']['ausgaben']:
            for key in ('kategorie_id', 'name', 'betrag_cent', 'anteil'):
                self.assertIn(key, uebersicht['top']['ausgaben'][0])

        matrix = self.get('jahresmatrix', f'sparte_id={self.haupt}&jahre=2026')
        for key in ('jahre', 'stichtag', 'zeilen', 'summen'):
            self.assertIn(key, matrix)
        zeile = next(z for z in matrix['zeilen'] if z['kategorie_id'] == aus)
        for key in ('kategorie_id', 'name', 'sparte_id', 'aktiv', 'richtung', 'werte', 'erwartung_cent', 'monatsdurchschnitt_cent'):
            self.assertIn(key, zeile)

        zahler = self.con.execute("INSERT INTO sparte(name,typ) VALUES('P32-Zahler2','privat')").lastrowid
        self.con.commit()
        status, _ = self.request('POST', '/api/buchungen', {
            'sparte_id': self.haupt, 'datum': '2026-01-15', 'typ': 'ausgabe',
            'zahlungsart': 'bar', 'bezahlt_von_sparte_id': zahler,
            'zeilen': [{'kategorie_id': aus, 'betrag_cent': 2500}],
        })
        self.assertEqual(201, status)
        auslagen = self.get('auslagen', f'sparte_id={self.haupt}')
        for key in ('zahler_sparte_id', 'sparte_id', 'offen_cent', 'anzahl', 'auslagen'):
            self.assertIn(key, auslagen[0])
        for key in ('text', 'datum', 'kategorie', 'offen_cent'):
            self.assertIn(key, auslagen[0]['auslagen'][0])

        konten = self.get('konten')
        for key in ('id', 'name', 'art', 'sparte_id', 'stand_cent', 'datenstand'):
            self.assertIn(key, konten[0])

    def test_antwortform_kennzahlen_endpoint(self):
        ein, _ = self._kategorien()
        status, kennzahl = self.request('POST', '/api/kennzahlen', {
            'sparte_id': self.haupt, 'name': 'P32-Vertragstest',
            'terme': [{'kategorie_id': ein, 'messgroesse': 'einnahmen', 'vorzeichen': 1}],
        })
        self.assertEqual(201, status, kennzahl)
        status, kennzahlen = self._kennzahlen_get(f'sparte_id={self.haupt}&jahr=2026')
        self.assertEqual(200, status, kennzahlen)
        for key in ('id', 'name', 'terme', 'wert_cent', 'monatsdurchschnitt_cent'):
            self.assertIn(key, kennzahlen[0])
        for key in ('kategorie_id', 'messgroesse', 'vorzeichen'):
            self.assertIn(key, kennzahlen[0]['terme'][0])


if __name__ == '__main__':
    unittest.main()
