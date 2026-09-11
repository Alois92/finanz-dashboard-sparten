# F-tests-017 – Runde 1, 11. September 2026

Auftrag: 15 nach Migration 016/017 (P50b/P51) fehlschlagende Bestandstests
reparieren. Arbeitsverzeichnis `C:\Users\lblet\dev\wt-testfix`, Zweig
`fix/tests-migration-017`, abgezweigt von `neubau` Stand 8744564. Ausgangslage
laut `%LOCALAPPDATA%\Temp\abn-p51-suite.log`: 435 Tests, `failures=14,
errors=1, skipped=1`.

Geändert wurden ausschließlich Tests (`tests/*.py`, `tests/snapshots/*.json`).
Kein Eingriff in `app/`, `db/schema.sql`, `db/migrations/`, `db/seed.sql`,
Frontend oder Router.

## Gruppe 1 – Feste Migrationslisten/-nummern

Betroffen: `test_auslagen.py`, `test_bereiche_migration.py`,
`test_konten_bewegungen.py`, `test_kredit.py`, `test_migrate.py`,
`test_migrationsprotokoll.py`, `test_saldoanker.py`.

Alle Stellen mit `[…, 15]` als erwartetem Rückgabewert von
`migrate.anwenden(con, None)` wurden auf `[…, 15, 16, 17]` erweitert (in
`test_kredit.py` zusätzlich `[15]` → `[15, 16, 17]`, dort waren nur Versionen
≤14 vormarkiert). `test_p20_migration.py` war **nicht** betroffen: dort wird
über `migrate.alle_markieren()` zunächst der volle Endstand markiert und
anschließend gezielt nur eine einzelne Version wieder ausgetragen, sodass
`anwenden()` dort weiterhin nur genau diese eine Version nachzieht.

In `test_migrate.py`: die Liste der `(nummer, name)`-Paare um
`(16, 'buchung_aenderung'), (17, 'storno_erstattung')` ergänzt (zwei
Vorkommen: `test_neue_datenbank_ist_auf_version_15_...` und
`test_alte_datenbank_erhaelt_basis_version_...`), `"aktuell": 15` →
`"aktuell": 17` in beiden betroffenen Assertions (Status-Dict und
`/api/schema`-Antwort in `test_schema_endpoint_liefert_erwartete_felder`).

Wie in der Auftragskarte vorgegeben wurde dem bestehenden Muster gefolgt
(siehe `git log -p --follow tests/test_migrate.py` zu Migration 015: dort
wurden dieselben Literale ebenfalls einfach um den neuen Eintrag ergänzt,
nicht aus `app/migrate.py` abgeleitet). Ein Ableiten aus
`migrate.liste_migrationen()` wäre an diesen Stellen möglich gewesen, hätte
aber den bewusst harten Soll-Vergleich (Regressionsschutz gegen eine
versehentlich verschobene/fehlende Migration) entwertet.

**P20-Snapshot** (`test_p20_snapshots.py` / `tests/snapshots/p20_alt.json`):
Diff-Analyse ergab, dass sich gegenüber dem eingefrorenen Vor-Umbau-Stand
ausschließlich zwei neue, stets `null`e Felder je Buchung im Suchergebnis
(`/api/buchungen/suche?q=marker`) ergeben: `original_id` und `storniert_am`
(aus Migration 017). Beide Felder wurden den beiden betroffenen
JSON-Objekten in `p20_alt.json` hinzugefügt (Wert `null`, wie von der App
tatsächlich geliefert). Keine sonstigen Abweichungen; alle übrigen Endpunkte
unverändert.

**Zusatzfund in dieser Gruppe (nicht in der Auftragskarte benannt):**
`test_bereiche_migration.test_schema_and_migration_have_identical_structure`
und `test_migration_assigns_domains_and_removes_only_foreign_memberships`
blieben nach der reinen Listen-Korrektur mit einem Struktur-Diff rot
(`(17, 'version', ...)` vs. `(17, 'original_id', ...)`). Ursache: die
Testmethode `old_schema()` entfernt bislang nur `kredit_id`, `version` und
`client_request_id` aus `buchung`, um einen vor-P12-Altstand zu simulieren,
den `migrate.anwenden()` dann komplett neu hochzieht. Die P51-Spalten
`buchung.original_id`/`storniert_am` blieben dabei unangetastet stehen (sie
existieren ja schon im per `schema.sql` aufgesetzten Startzustand). Beim
Nachzug hängt Migration 012 `version`/`client_request_id`/`kredit_id` dann
per `ALTER TABLE ... ADD COLUMN` ans Ende der *aktuellen* Spaltenliste –
**hinter** die bereits vorhandenen `original_id`/`storniert_am` – statt wie
in einem frischen `schema.sql` **davor**. Migration 017 selbst greift dank
des generischen ADD-COLUMN-Wächters in `app/migrate.py::_sql_migration` nur
noch idempotent durch (Spalten schon da → übersprungen), ändert die
Reihenfolge also nicht mehr.

Fix in `old_schema()`: zusätzlich `original_id`/`storniert_am` aus `buchung`
und `original_zeile_id` aus `buchungszeile` entfernen, bevor die älteren
Spalten fallen – exakt das gleiche Prinzip, das die Methode bereits für
`kredit_id` verwendet (Kommentar an Ort und Stelle verweist darauf). Da die
Views `v_zeile`/`v_einnahmen_ausgaben` (Migration 017) `buchung.storniert_am`
referenzieren, mussten sie vor dem Spaltenwegfall zunächst auf den
Vor-017-Stand aus Migration 007 zurückgesetzt werden (`DROP VIEW`/
`CREATE VIEW` mit dem dortigen Text); die spätere erneute Anwendung von
Migration 007 und 017 während `migrate.anwenden()` stellt danach wieder den
Endstand her. Kein Eingriff in `app/migrate.py` oder die Migrationen nötig.

## Gruppe 2 – P50b-Verlauf-Endpunkt

`test_p50_buchungen.test_verlauf_endpunkt_existiert_in_diesem_paket_nicht`
dokumentierte bewusst die von P50b geschlossene Lücke (`GET
/api/buchungen/{id}/verlauf` → 404). `tests/test_p50b_verlauf.py` deckt den
tatsächlichen Endpunkt bereits vollständig und in beide Richtungen ab:
`test_put_aendert_datum_und_zeilenbetrag_protokolliert_beide` prüft `GET
.../verlauf` → 200 mit Liste (inkl. Sortierung neueste zuerst),
`test_verlauf_fremder_bereich_404` prüft weiterhin den 404-Fall für falschen
Bereich. Der veraltete Test wurde **gelöscht** (Methode
`test_verlauf_endpunkt_existiert_in_diesem_paket_nicht` in
`tests/test_p50_buchungen.py`, durch einen Verweiskommentar auf
`test_p50b_verlauf.py` ersetzt), nicht ins Gegenteil umgeschrieben, um keine
Dopplung zu `test_p50b_verlauf.py` zu erzeugen. Das erklärt die Zielzahl von
434 statt 435 Tests.

## Gruppe 3 – Echter Fehler: `test_migrationsprobe`

Symptom: `test_neutral_und_kostenstorno_werden_als_abweichung_gemeldet` →
`sqlite3.OperationalError: duplicate column name: storniert_am` beim direkten
`con.execute('ALTER TABLE buchung ADD COLUMN storniert_am TEXT')` im Test.

**Root-Cause-Analyse** (vor jeder Änderung reproduziert, siehe unten):
`self.probe.lauf(self.source, work)` zu Beginn des Tests führt bereits den
vollständigen Migrationsnachzug bis Version 17 aus. Migration 017 legt
`buchung.storniert_am` dabei selbst an. Der Test simuliert im Anschluss
händisch einen fiktiven Altbestand mit *zusätzlichen*, nicht offiziell
migrierten Kostenstorno-Spalten (Muster aus einer früheren Studio-Version) –
das war zulässig, solange `buchung.storniert_am` aus der offiziellen
Migration noch nicht existierte. Seit Migration 017 existiert die Spalte
aber bereits nach `lauf()`, wodurch das erneute `ALTER TABLE ... ADD COLUMN`
im Test auf eine echte Dopplung läuft.

Geprüft wurde, ob `app/migrate.py`/Migration 017 selbst robust gegen einen
*vor* dem Nachzug bereits vorhandenen `buchung.storniert_am` sind – das war
bereits der Fall, unabhängig von dieser Änderung: `_sql_migration()` in
`app/migrate.py` erkennt jedes `ALTER TABLE ... ADD COLUMN` per Regex, prüft
per `PRAGMA table_info` auf die Zielspalte und überspringt die Anweisung,
falls sie schon existiert (bestehender, migrationsübergreifender
Mechanismus, nicht neu für 017; siehe Log-Zeile "ADD COLUMN uebersprungen").
Nachweis per Reproduktionsskript (Fixture + `ALTER TABLE buchung ADD COLUMN
storniert_am TEXT` **vor** `probe.lauf(...)`, danach `probe.lauf(...)`
aufgerufen): Ergebnis `erfolgreich: True`,
`kostenstorno_spalten: {'buchung': True, 'buchungszeile': False}` – der
Nachzug bricht nicht ab und die Migrationsprobe meldet die Spalte weiterhin
korrekt als vorhanden. Migration 017 und `app/migrate.py` mussten daher
**nicht** geändert werden; `db/schema.sql` blieb ebenfalls unverändert.

Fix ausschließlich in `tests/test_migrationsprobe.py`: vor dem `ALTER TABLE
buchung ADD COLUMN storniert_am TEXT` wird per
`self.probe._spalten(con, 'buchung')` (vorhandener Helfer im geprüften
Skript) geprüft, ob die Spalte nicht schon da ist; nur dann wird sie noch
angelegt. Das `UPDATE buchung SET storniert_am=...` bleibt unverändert
bestehen und befüllt die (jetzt schon vorhandene) Spalte. Das
`buchungszeile.storniert_am`-`ALTER TABLE` bleibt unverändert, da diese
Spalte in keiner offiziellen Migration existiert (reiner Testaufbau für den
Zeilen-Kostenstorno).

Anschließend geprüft: `scripts/migrationsprobe.py` meldet mit einem
Altbestand, der `buchung.storniert_am` bereits vor dem Nachzug besitzt,
weiterhin `kostenstorno_spalten.buchung: True` (siehe Reproduktion oben) –
die Abweichungsmeldung bleibt also erhalten. `tests/test_p51_storno.py`
(Vergleich `schema.sql` vs. zweifacher Nachzug) blieb im Gesamtlauf grün.

## Prüfung

Interpreter: `C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Scripts\python.exe`.
`set FINANZ_DB=%TEMP%\testfix.db` (bzw. je Lauf ein frischer Dateiname),
niemals `FINANZ_TEST_AUTH_BYPASS`.

Erster Gesamtlauf nach Gruppen 1+2+3 (vor dem oben beschriebenen
Zusatzfund) zeigte noch einen Rest-Fehler in
`test_bereiche_migration.test_schema_and_migration_have_identical_structure`.
Nach dessen Behebung (`old_schema()` wie oben beschrieben ergänzt):

```
----------------------------------------------------------------------
Ran 434 tests in 201.592s

OK (skipped=1)
```

434 statt 435 Tests, da `test_verlauf_endpunkt_existiert_in_diesem_paket_nicht`
gelöscht wurde (Gruppe 2, siehe oben). Der eine Skip ist unverändert der
bestehende `test_store_setzt_dateimodus_0600` (POSIX-Dateirechte unter
Windows), nicht durch diese Änderung verursacht. `git diff --stat` zeigt
ausschließlich Änderungen unter `tests/`:

```
tests/snapshots/p20_alt.json      |  8 ++++++--
tests/test_auslagen.py            |  2 +-
tests/test_bereiche_migration.py  | 38 ++++++++++++++++++++++++++++++++++----
tests/test_konten_bewegungen.py   |  2 +-
tests/test_kredit.py              |  4 ++--
tests/test_migrate.py             |  8 ++++----
tests/test_migrationsprobe.py     |  8 +++++++-
tests/test_migrationsprotokoll.py |  2 +-
tests/test_p50_buchungen.py       |  6 +-----
tests/test_saldoanker.py          |  2 +-
10 files changed, 58 insertions(+), 22 deletions(-)
```

## Offene Punkte

- Keine bekannten offenen Testfehler. Der Gesamtlauf war zum Abschluss grün
  (434, OK, skipped=1).
- Nicht geprüft: Verhalten in einer echten Produktionskopie (außerhalb des
  Auftrags dieser Runde, ausschließlich synthetische/Testdatenbanken unter
  `%TEMP%` verwendet).
- Die in der Auftragskarte nicht erwähnte Korrektur an
  `test_bereiche_migration.old_schema()` ist ein Fund dieser Runde und oben
  ausführlich begründet; falls das als Scope-Erweiterung gilt, bitte gegenprüfen.
- `db/schema.sql`, `app/migrate.py`, die Migrationen, Frontend, Router und
  `db/seed.sql` wurden nicht angefasst.
