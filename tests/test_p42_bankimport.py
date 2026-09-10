"""P42: Bankimport-Seite (static-neu/pages/bankimport.js) gegen die echten
Endpunkte, die das Modul verwendet: POST /api/import/csv, GET /api/bankumsaetze,
POST .../verbuchen, PATCH /api/bankumsaetze/{id},
POST /api/bankumsaetze/vorschlaege-uebernehmen, GET .../kandidaten,
POST .../zuordnen, POST .../zuordnung-loesen (N4), GET /api/konten/{id}/offene-abgleiche
(N4), GET /api/konten, GET /api/kategorien. Nutzt dieselbe ASGI-Testinfrastruktur
wie tests/test_bereiche.py (kein httpx im venv vorhanden).
"""
import pathlib
import subprocess
import sys
import unittest

import test_bereiche as bereiche_tests

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "george_2025_auszug.csv"
ROOT = pathlib.Path(__file__).resolve().parent.parent


def multipart(bankkonto_id, dateiname, inhalt: bytes):
    boundary = "p42test"
    kopf = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="bankkonto_id"\r\n\r\n{bankkonto_id}\r\n'
        f'--{boundary}\r\nContent-Disposition: form-data; name="datei"; filename="{dateiname}"\r\n'
        'Content-Type: text/csv\r\n\r\n'
    ).encode()
    fuss = f'\r\n--{boundary}--\r\n'.encode()
    return kopf + inhalt + fuss, f'multipart/form-data; boundary={boundary}'


class P42SeiteAusgeliefertTest(unittest.TestCase):
    """Statische Auslieferung unter /neu, unabhaengig von der Datenbank."""

    def setUp(self):
        import os
        from unittest.mock import patch
        env = patch.dict(os.environ, {"FINANZ_TEST_AUTH_BYPASS": "1"})
        env.start()
        self.addCleanup(env.stop)

    def request_static(self, path):
        import asyncio
        from urllib.parse import urlsplit
        from app.main import app

        parts = urlsplit(path)
        scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
                  "http_version": "1.1", "method": "GET", "scheme": "http",
                  "path": parts.path, "raw_path": parts.path.encode(), "query_string": b"",
                  "headers": [(b"host", b"localhost")], "client": ("127.0.0.1", 50000),
                  "server": ("localhost", 80), "root_path": ""}
        messages = []

        async def run():
            async def receive():
                return {"type": "http.request", "body": b""}

            async def send(message):
                messages.append(message)
            await app(scope, receive, send)
        asyncio.run(run())
        status = next(m["status"] for m in messages if m["type"] == "http.response.start")
        body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
        return status, body

    def test_seite_und_modul_werden_ausgeliefert(self):
        status, body = self.request_static("/neu/")
        self.assertEqual(200, status)
        self.assertIn(b"<title>", body)

        status, body = self.request_static("/neu/pages/bankimport.js")
        self.assertEqual(200, status)
        self.assertIn(b"P42", body)
        self.assertIn(b"import/csv", body)

        status, body = self.request_static("/neu/pages/bankimport.css")
        self.assertEqual(200, status)
        self.assertIn(b"bi-acct", body)

    def test_node_check_js_dateien(self):
        node = None
        for kandidat in ("node", "node.exe"):
            try:
                subprocess.run([kandidat, "--version"], capture_output=True, check=True)
                node = kandidat
                break
            except (FileNotFoundError, subprocess.CalledProcessError):
                continue
        if node is None:
            self.skipTest("node nicht verfuegbar in dieser Umgebung")
        for datei in ("bankimport.js",):
            pfad = ROOT / "static-neu" / "pages" / datei
            result = subprocess.run([node, "--check", str(pfad)], capture_output=True)
            self.assertEqual(0, result.returncode, result.stderr.decode(errors="replace"))


class P42BankimportApiTest(unittest.TestCase):
    setUp = bereiche_tests.BereicheTest.setUp
    request = bereiche_tests.BereicheTest.request
    payload = bereiche_tests.BereicheTest.payload

    def konto(self, **extra):
        status, result = self.request('POST', '/api/konten', {'name': 'Testbank', 'art': 'bank', **extra})
        self.assertEqual(201, status, result)
        return result['id']

    def kategorie(self, sparte_id, richtung='ausgabe', name='Testkategorie'):
        status, result = self.request('POST', '/api/kategorien', {'sparte_id': sparte_id, 'name': name, 'richtung': richtung})
        self.assertEqual(201, status, result)
        return result['id']

    def upload(self, bankkonto_id, inhalt: bytes, dateiname='umsaetze.csv'):
        raw, content_type = multipart(bankkonto_id, dateiname, inhalt)
        status, result = self.request('POST', '/api/import/csv', raw=raw, content_type=content_type)
        return status, result

    # -- Konten- und Kategorien-Felder, die die Konten-Karte und das
    #    Verbuchen-Formular lesen. -------------------------------------------

    def test_konten_und_kategorien_liefern_die_vom_modul_gelesenen_felder(self):
        kid = self.konto(sparte_id=self.haupt)
        status, konten = self.request('GET', '/api/konten')
        self.assertEqual(200, status)
        eintrag = next(k for k in konten if k['id'] == kid)
        for feld in ('id', 'name', 'art', 'stand_cent', 'datenstand', 'letzter_import', 'iban', 'kartenendnummer'):
            self.assertIn(feld, eintrag)
        self.assertEqual('bank', eintrag['art'])

        self.kategorie(self.haupt)
        status, kategorien = self.request('GET', '/api/kategorien?nur_aktive=true')
        self.assertEqual(200, status)
        self.assertTrue(all(k['aktiv'] for k in kategorien))
        for feld in ('id', 'sparte_id', 'name', 'aktiv'):
            self.assertIn(feld, kategorien[0])

    # -- CSV-Upload mit einer Fixture aus tests/fixtures. ----------------------

    def test_upload_george_fixture_liefert_pruefbericht_felder(self):
        kid = self.konto(sparte_id=self.haupt)
        status, ergebnis = self.upload(kid, FIXTURE.read_bytes(), 'george_2025_auszug.csv')
        self.assertEqual(200, status, ergebnis)
        for feld in ('batch_id', 'neu', 'dubletten', 'gesamt', 'saldo_ok', 'saldo_hinweis', 'erkannt'):
            self.assertIn(feld, ergebnis)
        for feld in ('kodierung', 'trennzeichen', 'zeilen_gesamt', 'zeilen_ungueltig'):
            self.assertIn(feld, ergebnis['erkannt'])
        self.assertEqual(8, ergebnis['neu'])
        self.assertEqual(0, ergebnis['dubletten'])

        # Zweiter Import derselben Datei: Dublettenschutz, keine neuen Umsaetze.
        status2, ergebnis2 = self.upload(kid, FIXTURE.read_bytes(), 'george_2025_auszug.csv')
        self.assertEqual(200, status2, ergebnis2)
        self.assertEqual(0, ergebnis2['neu'])
        self.assertEqual(8, ergebnis2['dubletten'])

    def test_bankumsaetze_liste_hat_vorschlag_nur_fuer_offene(self):
        kid = self.konto(sparte_id=self.haupt)
        self.upload(kid, FIXTURE.read_bytes())
        status, umsaetze = self.request('GET', f'/api/bankumsaetze?bankkonto_id={kid}')
        self.assertEqual(200, status)
        self.assertEqual(8, len(umsaetze))
        for u in umsaetze:
            for feld in ('id', 'datum', 'betrag_cent', 'text', 'importstatus'):
                self.assertIn(feld, u)
            if u['importstatus'] == 'offen':
                self.assertIn('vorschlag', u)
            else:
                self.assertNotIn('vorschlag', u)

    def test_verbuchen_und_ignorieren(self):
        kid = self.konto(sparte_id=self.haupt)
        katid = self.kategorie(self.haupt)
        self.upload(kid, FIXTURE.read_bytes())
        _, umsaetze = self.request('GET', f'/api/bankumsaetze?bankkonto_id={kid}')
        ausgabe = next(u for u in umsaetze if u['betrag_cent'] < 0)
        einnahme = next(u for u in umsaetze if u['betrag_cent'] > 0)

        status, result = self.request('POST', f"/api/bankumsaetze/{ausgabe['id']}/verbuchen",
                                       {'sparte_id': self.haupt, 'kategorie_id': katid})
        self.assertEqual(201, status, result)
        for feld in ('buchung_id', 'typ', 'betrag_cent', 'regel_angelegt'):
            self.assertIn(feld, result)
        self.assertEqual('ausgabe', result['typ'])

        status, result = self.request('PATCH', f"/api/bankumsaetze/{einnahme['id']}", {'importstatus': 'ignoriert'})
        self.assertEqual(200, status, result)
        self.assertEqual({'id': einnahme['id'], 'importstatus': 'ignoriert'}, result)

        # Wieder oeffnen (vom Modul als "wieder oeffnen" angeboten).
        status, result = self.request('PATCH', f"/api/bankumsaetze/{einnahme['id']}", {'importstatus': 'offen'})
        self.assertEqual(200, status, result)
        self.assertEqual('offen', result['importstatus'])

    # -- Zuordnung zu bestehenden Buchungen ueber die N4-Endpunkte, die das
    #    Modul fuer "Zusammenfuehren" und "bestehender Buchung zuordnen" nutzt.

    def test_zuordnen_und_loesen_ueber_n4_endpunkte(self):
        kid = self.konto(sparte_id=self.haupt)
        katid = self.kategorie(self.haupt)
        status, buchung = self.request('POST', '/api/buchungen', {
            'sparte_id': self.haupt, 'datum': '2026-01-02', 'typ': 'ausgabe', 'zahlungsart': 'bank',
            'bankkonto_id': kid, 'text': 'Manuell erfasst',
            'zeilen': [{'kategorie_id': katid, 'betrag_cent': 150}],
        })
        self.assertEqual(201, status, buchung)
        buchung_id = buchung['id']

        csv_inhalt = (
            "Datum;Betrag;Text\n03.01.2026;-1,50;Banktest\n"
        ).encode('utf-8-sig')
        status, ergebnis = self.upload(kid, csv_inhalt, 'abgleich.csv')
        self.assertEqual(200, status, ergebnis)
        _, umsaetze = self.request('GET', f'/api/bankumsaetze?bankkonto_id={kid}')
        umsatz_id = next(u for u in umsaetze if u['text'] == 'Banktest')['id']

        status, kandidaten = self.request('GET', f'/api/bankumsaetze/{umsatz_id}/kandidaten')
        self.assertEqual(200, status)
        self.assertEqual([{'buchung_id': buchung_id, 'datum': '2026-01-02', 'betrag_cent': -150,
                           'text': 'Manuell erfasst', 'abstand_tage': 1}], kandidaten['kandidaten'])

        status, uebersicht = self.request('GET', f'/api/konten/{kid}/offene-abgleiche')
        self.assertEqual(200, status)
        for feld in ('konto_id', 'manuelle_anzahl', 'manuelle_bewegungen', 'umsaetze_anzahl', 'offene_umsaetze'):
            self.assertIn(feld, uebersicht)
        self.assertEqual(1, uebersicht['umsaetze_anzahl'])

        status, result = self.request('POST', f'/api/bankumsaetze/{umsatz_id}/zuordnen', {'buchung_id': buchung_id})
        self.assertEqual(200, status, result)
        self.assertEqual({'bankumsatz_id': umsatz_id, 'buchung_id': buchung_id, 'importstatus': 'verbucht'}, result)

        status, result = self.request('POST', f'/api/bankumsaetze/{umsatz_id}/zuordnung-loesen')
        self.assertEqual(200, status, result)
        self.assertEqual({'bankumsatz_id': umsatz_id, 'buchung_id': None, 'importstatus': 'offen'}, result)

    def test_sammeluebernahme_von_regelvorschlaegen(self):
        kid = self.konto(sparte_id=self.haupt)
        katid = self.kategorie(self.haupt)
        status, regel = self.request('POST', '/api/regeln', {
            'name': 'Testregel', 'bedingung_text': 'partnerin', 'ziel_kategorie_id': katid,
            'quelle': 'stichwort',
        })
        self.assertEqual(201, status, regel)

        status, ergebnis = self.upload(kid, FIXTURE.read_bytes())
        self.assertEqual(200, status, ergebnis)
        _, umsaetze = self.request('GET', f'/api/bankumsaetze?bankkonto_id={kid}')
        treffer = [u for u in umsaetze if u['importstatus'] == 'offen' and u.get('vorschlag')
                   and u['vorschlag']['kategorie_id'] == katid]
        self.assertTrue(treffer, 'Fixture enthaelt keinen zur Regel passenden Umsatz mehr')

        status, result = self.request('POST', '/api/bankumsaetze/vorschlaege-uebernehmen',
                                       {'umsatz_ids': [u['id'] for u in treffer]})
        self.assertEqual(200, status, result)
        self.assertEqual({'verbucht': len(treffer), 'uebersprungen': 0}, result)

        # Leere Liste bleibt ein no-op (Sammelknopf ist ohne Auswahl deaktiviert,
        # aber der Endpunkt soll trotzdem sauber antworten).
        status, result = self.request('POST', '/api/bankumsaetze/vorschlaege-uebernehmen', {'umsatz_ids': []})
        self.assertEqual(200, status, result)
        self.assertEqual({'verbucht': 0, 'uebersprungen': 0}, result)


if __name__ == '__main__':
    sys.path.insert(0, str(ROOT))
    unittest.main()
