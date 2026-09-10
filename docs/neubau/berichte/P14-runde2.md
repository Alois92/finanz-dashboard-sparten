# P14 – Runde 2

## Ergebnis

Die Runde konnte in dieser Ausführungsumgebung nicht mit einer grünen Gesamtsuite abgeschlossen werden. Es wurden keine Tests und keine Produktionsdateien geändert. Die beiden Dateien unter `docs/superpowers/` wurden entfernt; das dadurch leere Verzeichnis konnte die verwaltete Dateisandbox nicht löschen.

## Ursachenbefund

Die Strukturdiagnose mit SQLite `:memory:` ergibt nach `db/schema.sql` sowie nach der Bestandsmigration 1–4 und 007 identische Tabellen, Spalten, Fremdschlüssel und Indizes. Die vier genannten sichtbaren Tests haben dagegen einen widersprüchlichen Versionsvertrag:

- `test_current_schema_accepts_migration_and_seed_has_separate_domains` und `test_schema_and_migration_have_identical_structure` erwarten `[1, 2, 3, 4]`, obwohl Migration 007 registriert ist.
- `test_migration_assigns_domains_and_removes_only_foreign_memberships` erwartet denselben alten Migrationsstand.
- `test_bestandskopie_nachzug_und_schema_identisch` erwartet nur `[4]`, vergleicht danach aber eine Bestandsdatenbank ohne 007 mit einem neuen Schema, das P14 bereits enthält.
- `tests/test_kredit.py::KreditMigrationTest::test_migration_007_zweimal_und_view` erwartet ausdrücklich `[7]`.

Ein Spezialfall im allgemeinen Runner oder ein Verschieben von P14 in eine frühere Migration würde diesen Widerspruch nur verdecken und die Idempotenz-/Versionssemantik brechen. Die Struktur selbst ist nach dem vollständigen Nachzug bereits gleich.

## Vollständige verfügbare Testausgabe

Interpreter: `C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Scripts\python.exe`

### Einzeltests (Umgebungsbefund)

```text
test_current_schema_accepts_migration_and_seed_has_separate_domains ... ERROR
test_migration_assigns_domains_and_removes_only_foreign_memberships ... ERROR
test_schema_and_migration_have_identical_structure ... ERROR
test_bestandskopie_nachzug_und_schema_identisch ... ERROR

sqlite3.OperationalError: unable to open database file
ModuleNotFoundError: No module named 'test_bereiche'

----------------------------------------------------------------------
Ran 4 tests in 0.063s

FAILED (errors=7)
```

Der zweite Lauf mit `TEMP`/`TMP` im Worktree reproduzierte denselben SQLite-Fehler:

```text
sqlite3.OperationalError: unable to open database file
PermissionError: [WinError 5] Zugriff verweigert
```

### Gesamtsuite

Befehl:

```text
C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Scripts\python.exe -u -m unittest discover -s tests -v
```

Nach 30 Sekunden Laufzeit war noch keine Testzeile ausgegeben und der Prozess lief weiter. Gemäß Arbeitsauftrag wurde der Lauf nicht als fachliche Blockade interpretiert und nicht wegen eines vermuteten Testfehlers abgebrochen.

### In-Memory-Strukturprobe

```text
migrations [(1, 'schema_version'), (2, 'import_batch_erkennung'),
 (3, 'bereiche'), (4, 'konten_bewegungen'), (7, 'kredit')]
fresh apply [1, 2, 3, 4, 7]
old apply [4, 7]
table diff set()
dump equal False
first dump diff: fresh schema has `bereich_id ... REFERENCES bereich(id),`,
legacy ALTER TABLE has the same column without the trailing comma
```

Die letzte Abweichung betrifft nur die SQLite-Dump-Textdarstellung der bereits vorhandenen Bereichsspalten; `PRAGMA table_info`, `foreign_key_list` und `index_list` sind gleich.

Keine Commits und kein Push wurden ausgeführt.
