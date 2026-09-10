"""P61: ausschließlich synthetische Datenbanken unter TemporaryDirectory."""
from contextlib import closing
import hashlib
import json
import logging
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def fixture(path, version0=False):
    """P10-Schema und Buchungsmuster aus scripts/p11_nachzug_probe.py.

    Ohne seed.sql: nur zwei synthetische Sparten; ZINA ist das fachliche
    Kürzel zur Bereichsprüfung, kein Personenname. Version 0 entfernt auch
    die P01/P10-Nachrüstungen, damit wirklich alle Schritte Arbeit haben.
    """
    with closing(sqlite3.connect(path)) as con:
        con.executescript((ROOT / 'tests/fixtures/schema_p10.sql').read_text(encoding='utf-8'))
        con.executescript("""
            INSERT INTO sparte(id,name,kuerzel,typ,bereich_id) VALUES
              (1,'Probe A','TEST','privat',1),(2,'Probe B','ZINA','verein',2);
            INSERT INTO kategorie(id,sparte_id,name,richtung) VALUES
              (1,1,'Probe','beides'),(2,2,'Probe','beides');
            INSERT INTO bankkonto(id,sparte_id,name,bereich_id) VALUES
              (1,1,'Testbank A',1),(2,2,'Testbank B',2);
            INSERT INTO bankumsatz(id,bankkonto_id,datum,betrag_cent,import_hash) VALUES
              (1,1,'2025-01-02',-100,'probe-1'),
              (2,1,'2025-01-02',200,'probe-2'),
              (3,1,'2025-01-02',300,'probe-3');
        """)
        rows = [(1,2025,'ausgabe','bank',1,None,100,1),
                (1,2025,'einnahme','bank',2,None,200,1),
                (1,2026,'ausgabe','bar',None,None,50,None),
                (2,2026,'einnahme','bar',None,None,80,None),
                (1,2026,'umbuchung','bank',None,'probe-bekannt',70,1),
                (2,2026,'umbuchung','bank',None,'probe-bekannt',70,2),
                (1,2026,'umbuchung','bank',None,'probe-offen',90,None),
                (2,2026,'umbuchung','bank',None,'probe-offen',90,None),
                (1,2026,'ausgabe','karte',None,None,40,None)]
        for sid, year, typ, art, uid, group, cent, kid in rows:
            bid = con.execute('''INSERT INTO buchung(sparte_id,datum,typ,zahlungsart,
                bankumsatz_id,transfer_gruppe_id,bankkonto_id) VALUES(?,?,?,?,?,?,?)''',
                (sid,f'{year}-01-02',typ,art,uid,group,kid)).lastrowid
            # Split prüft, dass Zeilen und nicht Kopf/Bewegungen summiert werden.
            for amount in (cent - 1, 1):
                con.execute('INSERT INTO buchungszeile(buchung_id,kategorie_id,betrag_cent) VALUES(?,?,?)',
                            (bid,sid,amount))
        con.execute("UPDATE bankumsatz SET importstatus='verbucht' WHERE id IN (1,2)")
        if version0:
            con.execute('DROP TABLE schema_version')
            for index in ('idx_sparte_bereich','idx_bankkonto_bereich','idx_beleg_bereich'):
                con.execute(f'DROP INDEX {index}')
            for table in ('sparte','bankkonto','beleg','regel','globale_kategoriegruppe','auswertungsgruppe'):
                con.execute(f'ALTER TABLE {table} DROP COLUMN bereich_id')
            con.execute('DROP TABLE bereich')
            for column in ('dateihash','parser_version','zeitraum_von','zeitraum_bis','anzahl_ungueltig'):
                con.execute(f'ALTER TABLE import_batch DROP COLUMN {column}')
        else:
            con.executemany('INSERT INTO schema_version(version,name) VALUES(?,?)',
                            [(1,'schema_version'),(2,'import_batch_erkennung'),(3,'bereiche')])
        con.commit()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class MigrationsprobeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='p61-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'quelle.db'
        fixture(self.source)
        from scripts import migrationsprobe
        self.probe = migrationsprobe

    def connection(self, path):
        con = sqlite3.connect(path)
        self.addCleanup(con.close)
        return con

    def test_alt_rechnet_exakte_zeilensummen_ohne_umbuchungen(self):
        self.assertEqual({1: {2025: {'einnahmen_cent': 200, 'ausgaben_cent': 100},
                              2026: {'einnahmen_cent': 0, 'ausgaben_cent': 90}},
                          2: {2026: {'einnahmen_cent': 80, 'ausgaben_cent': 0}}},
                         self.probe.summen_je_sparte_jahr(self.connection(self.source)))

    def test_vergleich_union_und_ein_cent_ohne_float(self):
        large = 2**53 + 1
        alt = {1: {2025: {'einnahmen_cent': large, 'ausgaben_cent': 2}},
               2: {2024: {'einnahmen_cent': 1, 'ausgaben_cent': 0}}}
        neu = {1: {2025: {'einnahmen_cent': large+1, 'ausgaben_cent': 2}},
               3: {2026: {'einnahmen_cent': 0, 'ausgaben_cent': 4}}}
        diff = self.probe.vergleiche(alt, neu)
        self.assertFalse(diff['gleich'])
        self.assertEqual([(1,2025,'einnahmen_cent',large,large+1,1),
                          (2,2024,'einnahmen_cent',1,0,-1),
                          (3,2026,'ausgaben_cent',0,4,4)],
                         [tuple(d[k] for k in ('sparte_id','jahr','feld','alt_cent','neu_cent','differenz_cent'))
                          for d in diff['abweichungen']])
        self.assertEqual({'gleich': True, 'abweichungen': []}, self.probe.vergleiche({}, {}))

    def test_zwei_frische_laeufe_beider_altstaende(self):
        for version0 in (False, True):
            with self.subTest(version0=version0):
                source = self.root / f'quelle-{version0}.db'
                fixture(source, version0)
                before = sha(source)
                reports = []
                for n in (1,2):
                    work = self.root / f'lauf-{version0}-{n}'
                    report = self.probe.lauf(source, work)
                    reports.append(report)
                    self.assertTrue(report['erfolgreich'])
                    self.assertEqual({'gleich': True, 'abweichungen': []}, report['vergleich'])
                    self.assertEqual(1, report['ungeklaerte_transfers'])
                    self.assertEqual(1, report['zahlung_unbekannt'])
                    self.assertEqual({'buchung':9,'buchungszeile':18}, report['anzahl_vorher'])
                    self.assertEqual(report['anzahl_vorher'], report['anzahl_nachher'])
                    self.assertEqual([], report['foreign_key_check'])
                    self.assertEqual(['ok'], report['integrity_check'])
                    self.assertEqual([], report['zweiter_anwenden_lauf'])
                    self.assertEqual(list(range(1 if version0 else 4,15)), report['angewendet'])
                    self.assertTrue(report['bereiche']['korrekt'])
                    self.assertTrue(all(r['nachher'] == (2 if r['sparte_id']==2 else 1)
                                        for r in report['bereiche']['je_sparte_jahr']))
                    self.assertEqual(2, len(report['migrationsprotokoll']))
                    self.assertEqual(1, report['ungeklaerte_faelle']['log']['transfers'])
                    self.assertEqual(1, report['ungeklaerte_faelle']['log']['zahlungen'])
                    self.assertEqual(before, sha(source))
                    self.assertEqual(before, report['quelle_sha256_vorher'])
                    self.assertEqual(before, report['quelle_sha256_nachher'])
                    self.assertNotEqual(before, sha(work / 'kopie.db'))
                    backup = self.connection(work / 'sicherung.db')
                    self.assertEqual(3 if not version0 else 0,
                                     self.probe.migrate.status(backup)['aktuell'])
                    self.assertEqual(json.loads(json.dumps(report)),
                                     json.loads((work / 'bericht.json').read_text(encoding='utf-8')))
                for key in ('vergleich','summen_vorher','summen_nachher','ungeklaerte_transfers',
                            'zahlung_unbekannt','bereiche','anzahl_nachher'):
                    self.assertEqual(reports[0][key],reports[1][key])

    def test_neutral_und_kostenstorno_werden_als_abweichung_gemeldet(self):
        work = self.root / 'lauf'
        report = self.probe.lauf(self.source, work)
        con = self.connection(work / 'kopie.db')
        con.execute('UPDATE buchungszeile SET neutral=1 WHERE id=1')
        con.execute('ALTER TABLE buchungszeile ADD COLUMN storniert_am TEXT')
        con.execute("UPDATE buchungszeile SET storniert_am='2026-01-01' WHERE id=2")
        con.execute('ALTER TABLE buchung ADD COLUMN storniert_am TEXT')
        con.execute("UPDATE buchung SET storniert_am='2026-01-01' WHERE id=2")
        self.assertEqual(report['summen_vorher'], self.probe.summen_je_sparte_jahr(con))
        diff = self.probe.vergleiche(report['summen_vorher'], self.probe.summen_neu(con))
        self.assertFalse(diff['gleich'])
        self.assertEqual([-200,-100], [d['differenz_cent'] for d in diff['abweichungen']])
        self.assertTrue(all(d['sparte_id']==1 and d['jahr']==2025 for d in diff['abweichungen']))

    def test_bewegungsstorno_und_mehrfachzahlung_veraendern_keine_kosten(self):
        work = self.root / 'lauf'
        report = self.probe.lauf(self.source, work)
        con = self.connection(work / 'kopie.db')
        con.execute("UPDATE bewegung SET storniert_am='2026-01-01'")
        con.execute('INSERT INTO buchung_bewegung VALUES(1,2,-1)')
        self.assertEqual(report['summen_vorher'], self.probe.summen_neu(con))

    def test_falscher_bereich_macht_gesamtergebnis_negativ(self):
        con = self.connection(self.source)
        con.execute('UPDATE sparte SET bereich_id=1 WHERE id=2')
        con.commit()
        report = self.probe.lauf(self.source, self.root / 'lauf')
        self.assertTrue(report['vergleich']['gleich'])
        self.assertFalse(report['bereiche']['korrekt'])
        self.assertFalse(report['erfolgreich'])

    def test_fehlende_quelle_und_ungueltige_db(self):
        with self.assertRaisesRegex(FileNotFoundError, 'Quelle'):
            self.probe.lauf(self.root / 'fehlt.db', self.root / 'lauf')
        self.source.write_text('keine SQLite-Datenbank')
        with self.assertRaises(sqlite3.DatabaseError):
            self.probe.lauf(self.source, self.root / 'kaputt')

    def test_quelle_ziel_identisch_und_bestehende_artefakte_geschuetzt(self):
        before = sha(self.source)
        work = self.root / 'lauf'
        work.mkdir()
        for name in ('kopie.db','sicherung.db','bericht.json'):
            target = work / name
            target.write_text('behalten')
            with self.assertRaises((ValueError,FileExistsError)):
                self.probe.lauf(self.source, work)
            self.assertEqual('behalten', target.read_text())
            target.unlink()
        with self.assertRaises(ValueError):
            self.probe.lauf(self.source, self.root)
        self.assertEqual(before,sha(self.source))

    def test_finanz_db_und_wal_quelle_abgewiesen(self):
        with patch.dict(os.environ, {'FINANZ_DB':str(self.source)}):
            with self.assertRaisesRegex(ValueError,'FINANZ_DB'):
                self.probe.lauf(self.source,self.root / 'lauf')
        Path(str(self.source)+'-wal').write_bytes(b'offene Transaktionen')
        with self.assertRaisesRegex(ValueError,'WAL|Journal'):
            self.probe.lauf(self.source,self.root / 'lauf')

    def test_finanz_db_darf_auch_keines_der_schreibziele_sein(self):
        for name in ('kopie.db', 'sicherung.db', 'bericht.json'):
            with self.subTest(name=name):
                work = self.root / name.replace('.', '-')
                with patch.dict(os.environ, {'FINANZ_DB':str(work / name)}):
                    with self.assertRaisesRegex(ValueError, 'FINANZ_DB'):
                        self.probe.lauf(self.source, work)
                self.assertFalse(work.exists())

    def test_log_zustand_auch_bei_migrationsfehler_wiederhergestellt(self):
        logger = logging.getLogger('finanz.migrate')
        handlers, level = list(logger.handlers), logger.level
        with patch.object(self.probe.migrate,'anwenden',side_effect=RuntimeError('Probe-Abbruch')):
            with self.assertRaisesRegex(RuntimeError,'Probe-Abbruch'):
                self.probe.lauf(self.source,self.root / 'lauf')
        self.assertEqual(handlers,logger.handlers)
        self.assertEqual(level,logger.level)

    def cli(self,*args):
        return subprocess.run([sys.executable,'-m','scripts.migrationsprobe',str(self.source),*args],
                              cwd=ROOT, capture_output=True,text=True,encoding='utf-8',
                              env={**os.environ,'PYTHONIOENCODING':'utf-8','TEMP':str(self.root),
                                   'TMP':str(self.root)},timeout=60)

    def test_cli_explizit_und_temp_bericht_bleibt_erhalten(self):
        result = self.cli('--arbeitsordner',str(self.root / 'cli'))
        self.assertEqual(0,result.returncode,result.stderr)
        for term in ('Sparte','2025','Abweichungen','Bereiche','ungeklärt','Migrationsprotokoll'):
            self.assertIn(term,result.stdout)
        result = self.cli()
        self.assertEqual(0,result.returncode,result.stderr)
        report_path = Path(result.stdout.split('Bericht: ')[-1].strip())
        self.assertTrue(report_path.is_file())
        self.assertFalse(list(self.root.glob('p61-arbeit-*')))
        self.assertTrue(json.loads(report_path.read_text(encoding='utf-8'))['erfolgreich'])

    def test_cli_fehler_und_fachliche_abweichung_exitcode(self):
        con = self.connection(self.source)
        con.execute('UPDATE sparte SET bereich_id=1 WHERE id=2')
        con.commit()
        self.assertEqual(1,self.cli('--arbeitsordner',str(self.root / 'falsch')).returncode)
        con.close()
        self.source.unlink()
        result = self.cli()
        self.assertEqual(2,result.returncode)
        self.assertIn('Quelle',result.stderr)


if __name__ == '__main__':
    unittest.main()
