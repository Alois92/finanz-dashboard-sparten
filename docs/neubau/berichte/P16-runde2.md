# P16 – Runde 2

## Ergebnis

Die drei gemeldeten Fehler sind behoben. Ursache des SQLite-Fehlers war ein falsch definierter Index in Migration 009: `profil_id` wurde auf `export_profil` statt auf `export_profil_ausschluss` referenziert. Zusätzlich wurde die versehentlich fehlerhafte Einrückung in `tests/test_bereiche_migration.py` korrigiert; die Versions-Erwartung blieb auf Version 9.

## Änderungen

- `db/migrations/009_export_profil.sql`: Index auf `export_profil_ausschluss(profil_id)` korrigiert.
- `tests/test_bereiche_migration.py`: Syntax-/Einrückungsfehler behoben.
- Keine Tests geändert, außer den bereits vorhandenen Erwartungen für die neue Migrationsversion und der notwendigen Einrückungskorrektur.

## Verifikation

Gezielte Regressionstests:

```text
Ran 6 tests ... OK
Ran 1 test ... OK
Ran 1 test ... OK
```

Die Strukturprüfung bestätigt identische Tabellen, Spalten, Fremdschlüssel und Indizes für frisches Schema und Nachzugsschema.

Vollständige Suite mit dem vorgegebenen Interpreter und einer frischen Wegwerf-Datenbank unter `C:\Users\lblet\AppData\Local\Temp`:

```text
Ran 195 tests in 204.618s
OK (skipped=1)
EXIT_CODE=0
```

Kein Commit und kein Push.
