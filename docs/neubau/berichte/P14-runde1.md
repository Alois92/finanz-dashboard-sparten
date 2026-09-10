# P14 – Runde 1

## Ergebnis

P14 ist im Worktree `C:\Users\lblet\dev\wt-p14` auf Branch `pkt/p14-kredit` umgesetzt. Die Kreditrate besteht aus einer Ausgabe-Buchung mit Zinszeile (`neutral=0`) und Tilgungszeile (`neutral=1`); der volle Ratenbetrag bleibt als Bewegung erhalten, die View wertet nur den Zins aus.

## Geänderte und neue Dateien

- `app/kredite.py`: Enthält die reine, verlustfreie Division `verteile_zins`.
- `app/routers/kredite.py`: Implementiert Kreditliste, Anlage, Teiländerung, Jahresbestätigung, Ratenanlage, Ratenliste und explizite Zuordnung alter Buchungen.
- `app/main.py`: Registriert den Kreditrouter unter `/api`.
- `app/routers/buchungen.py`: Liefert `neutral` je Zeile und `neutral_cent` je Buchung in Detail-, Listen- und Suchantworten.
- `db/migrations/007_kredit.sql`: Zieht `neutral`, Views und Kredit-/Kreditjahr-Tabellen idempotent nach.
- `db/schema.sql`: Enthält denselben P14-Schema- und View-Stand für neue Datenbanken.
- `tests/test_kredit.py`: Prüft Centverteilung, Migration und die zentrale Kreditfachlogik einschließlich Schätzung und Bereichsvalidierung.
- `tests/test_migrate.py`: Erwartet die neue Fachversion 7 für neue und nachgezogene Datenbanken.
- `docs/superpowers/specs/2026-09-09-kredit-design.md`: Hält Designentscheidungen und begründete Annahmen fest.
- `docs/superpowers/plans/2026-09-09-kredit.md`: Hält die Implementierungsplanung fest.

## Endpunkte und Bereichsprüfung

Alle sieben Kreditendpunkte hängen über `BereichDep` von `bereich_dep` ab. Kredit, Sparte, Konto, Kategorien, Beleg und zuzuordnende Buchungen werden zusätzlich mit den Helfern aus `app/bereiche.py` geprüft; Konto- und Kategorie-Sparte werden fachlich abgeglichen. Keine Auth-, Health-, Schema- oder Betriebsroute erhielt eine Bereichsdependency.

- `GET /api/kredite?bereich_id=`: Liste des Bereichs.
- `POST /api/kredite`: Kreditanlage, 201.
- `PATCH /api/kredite/{id}`: Teiländerung einschließlich `aktiv`.
- `PUT /api/kredite/{id}/jahre/{jahr}`: Bestätigung, centgenaue Verteilung und Abweichungen.
- `POST /api/kredite/{id}/raten`: Ratenbuchung mit Schätzstatus, Bewegung und optionalem Bankumsatz.
- `GET /api/kredite/{id}/raten?jahr=`: Raten und Anteile.
- `POST /api/kredite/{id}/raten/zuordnen`: Nur ausdrücklich ausgewählte Altbuchungen werden umgedeutet.

## Centgenauer Nachweis

`verteile_zins(1205, 12)` liefert 12 Werte mit Summe 1205 und einer maximalen Differenz von 1 Cent. Die End-to-End-Probe legte zwölf Raten zu je 42.000 Cent an, bestätigte 120.000 Cent Jahreszins und ergab zwölf Zinszeilen zu je 10.000 Cent, zwölf Tilgungszeilen zu je 32.000 Cent, 120.000 Cent in `v_einnahmen_ausgaben` und -504.000 Cent in `bewegung`.

## Doppelnachzug

Die Bestandsdatenbank wurde aus `db/schema.sql` und `db/seed.sql` unter `C:\Users\lblet\AppData\Local\Temp\p14-bestand.db` erzeugt und für die Probe auf Version 4 zurückgesetzt. Der allgemeine Runner lieferte:

```text
{'db': 'C:\\Users\\lblet\\AppData\\Local\\Temp\\p14-bestand.db', 'first': [7], 'second': [], 'unchanged': True, 'neutral': ['neutral'], 'views': ['v_einnahmen_ausgaben', 'v_zeile']}
```

Damit wurde 007 genau einmal angewendet und der zweite Lauf änderte weder Schema noch Daten.

## Testausgabe

Verwendeter Interpreter: `C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Scripts\python.exe`.

P14-Kern- und Migrationstests:

```text
test_verteile_zins_erhaelt_jeden_cent (test_kredit.KreditLogikTest.test_verteile_zins_erhaelt_jeden_cent) ... ok
test_migration_007_zweimal_und_view (test_kredit.KreditMigrationTest.test_migration_007_zweimal_und_view) ... ok

----------------------------------------------------------------------
Ran 2 tests in 0.026s

OK
```

Direkte End-to-End-Probe:

```text
P14 smoke ok
```

Statische Verifikation:

```text
compileall: OK
git diff --check: OK
```

Der vorgeschriebene Interpreter enthält kein `pytest` (`No module named pytest`). Die vollständige `unittest`-Suite wurde gestartet; ihr erster unveränderter ASGI-Test blockiert bereits beim Request-Harness nach der Testüberschrift, daher konnte sie in dieser Umgebung nicht vollständig beendet werden. Ein unveränderter P10-Bereichstest zeigt denselben Blocker; es ist kein P14-Fehlernachweis.

## Annahmen

- Der interne Ratenmarker wird im vorhandenen `buchung.notiz`-Feld gespeichert, weil der Worktree die in ARCHITEKTUR Abschnitt 4 genannten P12-Felder noch nicht enthält und P14 keine neue Kredit-Fremdschlüsselspalte für `buchung` vorgibt.
- Ein Zins größer als der jeweilige Ratenbetrag wird abgelehnt, damit keine negative Tilgung entsteht.
- Für ein unbestätigtes Jahr wird der bestätigte Vorjahreszins durch die Anzahl der Vorjahresraten geteilt; ohne Vorjahr und ohne bekannte Restschuld ist der Zinsanteil 0 und der Hinweis wird sichtbar zurückgegeben.
- Weniger als zwölf Raten und von der Monatsrate abweichende Beträge werden ausschließlich als Abweichung gemeldet.
- Die im aktuellen Branch fehlende P12-Spalte `buchung.storniert_am` wird nicht erfunden; die Views filtern Transfers und neutrale Zeilen, wie die vorhandene Struktur es erlaubt.

## Offene Punkte

- Die komplette Suite benötigt eine Umgebung, in der das vorhandene ASGI-Test-Harness nicht blockiert; der Blocker tritt bereits ohne P14 im P10-Test auf.
- Die bestehende Branch-Struktur enthält noch kein `client_request_id`-Feld aus ARCHITEKTUR Abschnitt 4; P14 akzeptiert das Feld am Ratenendpoint, ohne diesen nicht gelieferten P12-Schemaumfang vorwegzunehmen.
- Es gibt kein Frontend und keine automatische Umdeutung alter Buchungen; beides ist gemäß P14 ausdrücklich Nicht-Ziel beziehungsweise nur über den Zuordnungsendpoint erlaubt.

Keine Commits und kein Push wurden ausgeführt.
