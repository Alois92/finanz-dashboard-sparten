# P00: Versionierter Schema-Nachzug mit Sicherung

Meilenstein M0. Modell: Standard-Codex, Aufwand medium. Branch `neubau/p00-schema-nachzug` von `neubau`.

## 1. Ziel

Bestehende und neue Datenbanken erreichen über nummerierte Migrationsdateien denselben Schemastand, mit Sicherung vor jedem Nachzug und sauberem Abbruch bei Fehlern. Die App führt den Nachzug beim Start aus, und ein Kommandozeilenaufruf zeigt Status und wendet an.

## 2. Kontext

Lies `docs/neubau/ARCHITEKTUR.md` Abschnitt 10, dann `app/db.py` (Datenbankpfad, `init_db`, vorhandene Nachrüstungen), `app/backup.py` (Sicherungsfunktion, wiederverwenden), `app/main.py` (Start, Mounts, Lifespan), `db/schema.sql`, `tests/test_backup.py` als Muster für Tests mit Wegwerf-Datenbank.

## 3. Schnittstellen

Tabelle, in `db/schema.sql` ergänzen:

```sql
CREATE TABLE schema_version (
    version        INTEGER PRIMARY KEY,
    name           TEXT    NOT NULL,
    angewendet_am  TEXT    NOT NULL DEFAULT (datetime('now'))
);
```

Verzeichnis `db/migrations/`, Dateien `NNN_name.sql` (mit `executescript` ausführbar) oder `NNN_name.py` mit `def up(con: sqlite3.Connection) -> None`. `NNN` dreistellig, fortlaufend ab 001. Für dieses Paket existiert genau eine Migration `001_schema_version.py`, die nichts tut außer die eigene Existenz zu dokumentieren (leeres `up`). Sie dient als Beweis, dass der Mechanismus läuft.

Modul `app/migrate.py`:

```python
def liste_migrationen() -> list[tuple[int, str, pathlib.Path]]          # sortiert nach Version
def status(con) -> dict   # {"aktuell": int, "anstehend": [(version, name), ...], "basis": bool}
def basis_setzen(con) -> None       # bestehende DB ohne schema_version: Tabelle anlegen, Version 0 "basis" eintragen
def alle_markieren(con) -> None     # neue DB: alle Migrationen als angewendet eintragen, ohne sie auszuführen
def anwenden(con, sicherung: Callable[[], pathlib.Path] | None) -> list[int]
    # vor der ersten anstehenden Migration sicherung() aufrufen (Pfad loggen);
    # je Migration: BEGIN, ausführen, INSERT schema_version, COMMIT; bei Fehler ROLLBACK und MigrationsFehler mit Version und Ursache;
    # gibt angewendete Versionen zurück
class MigrationsFehler(Exception): version: int
```

Einbindung in `app/db.py`: `init_db()` erzeugt neue Datenbanken aus `schema.sql` und ruft danach `alle_markieren`; bei bestehenden Datenbanken ohne `schema_version` ruft es `basis_setzen`, danach `anwenden` mit der Sicherungsfunktion aus `app/backup.py`. Die bestehenden Ad-hoc-Nachrüstungen in `init_db` bleiben in diesem Paket unverändert (sie wandern in P01 in Migrationen).

Einbindung in `app/main.py`: Der Nachzug läuft beim Start vor dem ersten Request und vor Hintergrundaufgaben. Schlägt er fehl, setzt die App `app.state.schreibgeschuetzt = True` mit der Fehlermeldung; alle schreibenden Endpoints (POST, PUT, PATCH, DELETE) antworten dann mit 503 und `{"detail": "Datenbank-Nachzug fehlgeschlagen: …"}`. Lesen bleibt möglich. Umsetzung als Middleware oder Dependency, eine Stelle.

Endpoint `GET /api/schema` (angemeldet wie die übrigen `/api`-Routen): `{"aktuell": 1, "anstehend": [], "schreibgeschuetzt": false, "fehler": null}`.

Kommandozeile: `python -m app.migrate status` und `python -m app.migrate apply`, beide mit `FINANZ_DB` oder `instance/db_location.txt` wie die App. `apply` legt die Sicherung an und druckt die angewendeten Versionen.

## 4. Nicht-Ziele

Keine inhaltlichen Schemaänderungen (keine neuen Fachtabellen). Keine Änderung an bestehenden Endpoints außer dem Schreibschutz. Kein Umbau von `app/backup.py`, nur Wiederverwendung. Keine Frontend-Änderung.

## 5. Schritte

1. `schema_version` in `db/schema.sql` ergänzen.
2. `db/migrations/001_schema_version.py` anlegen.
3. `app/migrate.py` schreiben.
4. `init_db` erweitern, Startlogik in `app/main.py` einbinden, Schreibschutz und `GET /api/schema`.
5. Tests schreiben, ausführen, Bericht.

## 6. Tests

Datei `tests/test_migrate.py`, jede Prüfung mit eigener Wegwerf-Datenbank über `FINANZ_DB` (Muster siehe `tests/test_backup.py`):

- Neue Datenbank: nach `init_db` enthält `schema_version` die Version 1, `status()` meldet nichts Anstehendes.
- Alte Datenbank: Datenbank aus `db/schema.sql` ohne die Tabelle `schema_version` erzeugen (Tabelle nach dem Einspielen droppen), `init_db` aufrufen: Version 0 „basis" und Version 1 vorhanden; Sicherungsdatei wurde angelegt (Pfad prüfen); zweiter Aufruf wendet nichts an und legt keine zweite Sicherung an.
- Fehlerfall: temporäre Migration `999_kaputt.sql` mit ungültigem SQL in ein Testverzeichnis legen (Migrationsverzeichnis über Parameter oder Monkeypatch austauschbar machen), `anwenden` löst `MigrationsFehler` mit `version == 999` aus, `schema_version` enthält 999 nicht, die Datenbank ist danach unverändert benutzbar.
- Schreibschutz: mit gesetztem `app.state.schreibgeschuetzt` liefert `POST /api/kategorien` 503, `GET /api/sparten` 200.
- `GET /api/schema` liefert die erwarteten Felder.

Vollständiger Lauf: `python -m unittest discover -s tests` muss grün bleiben, auch die bestehenden Tests.

## 7. Fertig heißt

- [ ] Alle Tests grün, Ausgabe im Bericht.
- [ ] `python -m app.migrate status` und `apply` funktionieren auf einer Kopie einer bestehenden Datenbank (Wegwerf-DB aus `schema.sql`), zweimal hintereinander ohne Fehler.
- [ ] `db/schema.sql` und Nachzug ergeben denselben Stand (Test „neue DB" gegen Test „alte DB": gleiche Tabellenliste).
- [ ] Keine Geheimnisse, keine Änderung an Auth oder Validierung, keine neuen Abhängigkeiten.
- [ ] Bericht geschrieben.

## 8. Bericht zurück

Geänderte und neue Dateien mit je einem Satz. Vollständige Testausgabe. Offene Punkte mit Grund. Keine Commits, kein Push: Claude übernimmt Abnahme und Merge.
