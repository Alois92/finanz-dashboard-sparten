import pathlib
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from app import migrate

BASE = pathlib.Path(__file__).resolve().parents[1]
TABLES = ('sparte', 'bankkonto', 'beleg', 'regel', 'globale_kategoriegruppe', 'auswertungsgruppe')


class BereicheMigrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='finanz-bereiche-')
        self.addCleanup(self.temp.cleanup)
        self.con = sqlite3.connect(pathlib.Path(self.temp.name) / 'test.db')
        self.addCleanup(self.con.close)
        self.con.executescript((BASE / 'db/schema.sql').read_text(encoding='utf-8'))

    def old_schema(self):
        self.con.execute('PRAGMA foreign_keys = OFF')
        for table in ('request_wiederholung', 'ausgleich_zuordnung', 'ausgleich',
                      'auslage', 'buchung_bewegung', 'bewegung', 'transfer'):
            self.con.execute(f'DROP TABLE {table}')
        self.con.execute('DROP INDEX idx_buchung_client_request')
        for column in ('version', 'client_request_id'):
            self.con.execute(f'ALTER TABLE buchung DROP COLUMN {column}')
        for column in ('art','waehrung','kartenendnummer','sortierung'):
            self.con.execute(f'ALTER TABLE bankkonto DROP COLUMN {column}')
        for table in TABLES:
            self.con.execute(f'DROP INDEX IF EXISTS idx_{table}_bereich')
            if 'bereich_id' in [r[1] for r in self.con.execute(f'PRAGMA table_info({table})')]:
                self.con.execute(f'ALTER TABLE {table} DROP COLUMN bereich_id')
        self.con.execute('DROP TABLE IF EXISTS bereich')
        self.con.commit()
        self.con.execute('PRAGMA foreign_keys = ON')

    def test_migration_assigns_domains_and_removes_only_foreign_memberships(self):
        self.old_schema()
        self.con.executescript("""
            INSERT INTO sparte(id,name,typ) VALUES(10,'Haupt','privat'),(20,'Verein','verein');
            INSERT INTO bankkonto(id,name,sparte_id) VALUES(1,'Verein',20),(2,'Ohne',NULL);
            INSERT INTO beleg(id,dateiname,pfad,sparte_id) VALUES(1,'a','a',20),(2,'b','b',NULL);
            INSERT INTO regel(id,name,ziel_sparte_id) VALUES(1,'Verein',20),(2,'Ohne',NULL);
            INSERT INTO kategorie(id,sparte_id,name,richtung) VALUES(1,20,'V','ausgabe'),(2,10,'H','ausgabe');
            INSERT INTO auswertungsgruppe(id,name) VALUES(1,'Gemischt'),(2,'Leer');
            INSERT INTO auswertungsgruppe_sparte VALUES(1,20),(1,10);
            INSERT INTO globale_kategoriegruppe(id,name) VALUES(1,'Gemischt'),(2,'Leer');
            INSERT INTO kategorie_globalgruppe VALUES(2,1),(1,1);
        """)
        with self.assertLogs('finanz.migrate', level='INFO') as logs:
            self.assertEqual([1,2,3,4,5,6,7,9], migrate.anwenden(self.con, None))
        for table in ('bankkonto','beleg','regel'):
            self.assertEqual([(1,2),(2,1)], self.con.execute(f'SELECT id,bereich_id FROM {table} WHERE id IN (1,2) ORDER BY id').fetchall())
        self.assertEqual([(10,1),(20,2)],self.con.execute("SELECT sparte_id,bereich_id FROM bankkonto WHERE art='kassa' ORDER BY sparte_id").fetchall())
        self.assertEqual([(1,10)], self.con.execute('SELECT * FROM auswertungsgruppe_sparte').fetchall())
        self.assertEqual([(1,1)], self.con.execute('SELECT * FROM kategorie_globalgruppe').fetchall())
        self.assertEqual([(1,2),(2,1)], self.con.execute('SELECT id,bereich_id FROM globale_kategoriegruppe ORDER BY id').fetchall())
        self.assertIn('auswertungsgruppe_sparte: 1', '\n'.join(logs.output))
        self.assertIn('kategorie_globalgruppe: 1', '\n'.join(logs.output))
        before = list(self.con.iterdump())
        self.assertEqual([], migrate.anwenden(self.con, None))
        self.assertEqual(before, list(self.con.iterdump()))
        # Auch das SQL selbst muss bereits nachgezogenes Schema akzeptieren.
        self.con.execute('DELETE FROM schema_version WHERE version=3')
        self.con.commit()
        self.assertEqual([3], migrate.anwenden(self.con, None))
        self.assertEqual([(1,10)], self.con.execute('SELECT * FROM auswertungsgruppe_sparte').fetchall())
        self.assertEqual([(1,1)], self.con.execute('SELECT * FROM kategorie_globalgruppe').fetchall())
        self.assertEqual(1, self.con.execute('PRAGMA foreign_keys').fetchone()[0])
        self.assertEqual([], self.con.execute('PRAGMA foreign_key_check').fetchall())

    def test_current_schema_accepts_migration_and_seed_has_separate_domains(self):
        self.con.executescript((BASE / 'db/seed.sql').read_text(encoding='utf-8'))
        self.assertEqual([(2,)], self.con.execute("SELECT DISTINCT bereich_id FROM sparte WHERE typ='verein'").fetchall())
        self.assertEqual(0, self.con.execute('SELECT COUNT(*) FROM auswertungsgruppe_sparte x JOIN sparte s ON s.id=x.sparte_id JOIN auswertungsgruppe g ON g.id=x.auswertungsgruppe_id WHERE s.bereich_id<>g.bereich_id').fetchone()[0])
        self.assertIn((3,'bereiche'), migrate.status(self.con)['anstehend'])
        self.assertEqual([1,2,3,4,5,6,7,9], migrate.anwenden(self.con, None))
        self.assertEqual([], migrate.anwenden(self.con, None))
        self.assertEqual([(2,)], self.con.execute("SELECT DISTINCT bereich_id FROM sparte WHERE typ='verein'").fetchall())
        self.assertEqual(0, self.con.execute('SELECT COUNT(*) FROM auswertungsgruppe_sparte x JOIN sparte s ON s.id=x.sparte_id JOIN auswertungsgruppe g ON g.id=x.auswertungsgruppe_id WHERE s.bereich_id<>g.bereich_id').fetchone()[0])

    def test_schema_and_migration_have_identical_structure(self):
        def structure(con):
            tables = [row[0] for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )]
            result = {}
            for table in tables:
                columns = con.execute(f'PRAGMA table_info({table})').fetchall()
                foreign_keys = sorted(con.execute(f'PRAGMA foreign_key_list({table})'))
                indexes = sorted(
                    (row[1], row[2], tuple(con.execute(f'PRAGMA index_info({row[1]})')))
                    for row in con.execute(f'PRAGMA index_list({table})')
                )
                result[table] = columns, foreign_keys, indexes
            return result
        expected = structure(self.con)
        self.old_schema()
        self.assertEqual([1,2,3,4,5,6,7,9], migrate.anwenden(self.con, None))
        self.assertEqual(expected, structure(self.con))

    def test_sql_runner_rolls_back_fk_failure_and_restores_enforcement(self):
        directory = pathlib.Path(self.temp.name) / 'migrations'
        directory.mkdir()
        (directory / '777_invalid.sql').write_text(
            "CREATE TABLE child(id INTEGER REFERENCES sparte(id)); "
            "INSERT INTO child VALUES(999999); SELECT 'must not be logged';",
            encoding='utf-8',
        )
        with patch.object(migrate, 'MIGRATIONS_DIR', directory):
            with self.assertNoLogs('finanz.migrate', level='INFO'):
                with self.assertRaises(migrate.MigrationsFehler):
                    migrate.anwenden(self.con, None)
        self.assertIsNone(self.con.execute("SELECT 1 FROM sqlite_master WHERE name='child'").fetchone())
        self.assertIsNone(self.con.execute('SELECT 1 FROM schema_version WHERE version=777').fetchone())
        self.assertEqual(1, self.con.execute('PRAGMA foreign_keys').fetchone()[0])

    def test_sql_runner_logs_skipped_existing_column(self):
        directory = pathlib.Path(self.temp.name) / 'migrations'
        directory.mkdir()
        self.con.execute("CREATE TABLE beispiel(wert TEXT DEFAULT 'alt')")
        self.con.commit()
        (directory / '777_spalte.sql').write_text(
            "ALTER TABLE beispiel ADD COLUMN wert INTEGER DEFAULT 42;"
            "ALTER TABLE beispiel ADD COLUMN neu TEXT;", encoding='utf-8',
        )
        with patch.object(migrate, 'MIGRATIONS_DIR', directory):
            with self.assertLogs('finanz.migrate', level='INFO') as logs:
                self.assertEqual([777], migrate.anwenden(self.con, None))
        self.assertTrue(any(record.levelname == 'INFO' and
                            all(text in record.getMessage() for text in ('777', 'beispiel', 'wert', 'uebersprungen'))
                            for record in logs.records))
        columns = self.con.execute('PRAGMA table_info(beispiel)').fetchall()
        self.assertEqual(('wert', 'TEXT', 0, "'alt'"), columns[0][1:5])
        self.assertEqual('neu', columns[1][1])
        with patch.object(migrate, 'MIGRATIONS_DIR', directory):
            self.assertEqual([], migrate.anwenden(self.con, None))

    def test_sql_runner_preserves_trigger_and_string_semicolons(self):
        directory = pathlib.Path(self.temp.name) / 'migrations'
        directory.mkdir()
        (directory / '777_trigger.sql').write_text("""
            CREATE TABLE counter(value INTEGER);
            INSERT INTO counter VALUES(0);
            CREATE TABLE event(value TEXT);
            CREATE TRIGGER count_event AFTER INSERT ON event BEGIN
                UPDATE counter SET value=value+1;
                UPDATE counter SET value=value+1;
            END;
            INSERT INTO event VALUES('a;b');
            SELECT 'event: ' || value FROM event;
        """, encoding='utf-8')
        with patch.object(migrate, 'MIGRATIONS_DIR', directory):
            with self.assertLogs('finanz.migrate', level='INFO') as logs:
                self.assertEqual([777], migrate.anwenden(self.con, None))
        self.assertEqual(2, self.con.execute('SELECT value FROM counter').fetchone()[0])
        self.assertIn('event: a;b', '\n'.join(logs.output))


if __name__ == '__main__':
    unittest.main()
