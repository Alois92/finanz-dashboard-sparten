# P51-runde1: P50b (Historie) und P51 (Storno/Erstattung)

Worktree `C:\Users\lblet\dev\wt-p51`, Zweig `pkt/p51-storno-erstattung` (von `neubau`, Stand cab766b).

## Ausgangslage bei Übernahme

Ein Vorgänger-Agent hatte beide Pakete bereits inhaltlich fertig implementiert
(Backend und Frontend, unkommittiert), war aber vor dem Commit am Kontingent
abgebrochen. Bei Übernahme lag Folgendes vor:

- Migration `016_buchung_aenderung.sql` (P50b: Tabelle `buchung_aenderung`;
  P43b: eigener Wert `'beleg_uebernahme'` für `request_wiederholung.art`) —
  vollständig.
- Migration `017_storno_erstattung.sql` (P51: `original_id`/`storniert_am`
  auf `buchung`, `original_zeile_id` auf `buchungszeile`, Views neu) —
  vollständig.
- `app/routers/buchungen.py`: Protokollierung in `_update_buchung`,
  `GET /api/buchungen/{id}/verlauf`, `GET /api/buchungen/{id}` (neuer
  Einzel-Endpunkt), `POST .../stornieren`, `.../entstornieren`,
  `.../erstatten`, `_buchung_detail` um `original_id`/`storniert_am`/
  `erstattungen`/`netto_cent`/`rest_cent` je Zeile erweitert — vollständig.
- `app/routers/beleg_auswertung.py`, `app/schemas.py`: P43b-Anpassung
  (eigener Wiederholungs-Topf) und `BuchungIn.grund` — vollständig.
- `static-neu/pages/buchungen.js`/`.css`: Storno-Aktion mit Markierung,
  Erstattungen-Abschnitt mit Rest-Vorbelegung, Historie-Anzeige —
  vollständig.
- `tests/test_p50b_verlauf.py` (10 Tests), `tests/test_p51_storno.py`
  (12 Tests) — beide bereits geschrieben und inhaltlich passend zur
  Implementierung.

Die Vorgänger-Meldung "Alle Teil-1-Tests grün, jetzt Gesamtsuite" war nicht
mehr nachvollziehbar zu verifizieren; die Gesamtsuite lief bei Übernahme
noch nie durch (siehe Bugs unten).

## Gefundene und behobene Bugs

Die Implementierung selbst war korrekt, aber zwei Stellen verletzten die
Idempotenz-Anforderung "Migration zweimal über den Runner; schema.sql und
Nachzug ergeben dasselbe Schema":

1. **`CREATE TABLE buchung_aenderung` ohne `IF NOT EXISTS`.** Mehrere
   Bestandstests (`test_bereiche_migration.py`, `test_kredit.py`,
   `test_saldoanker.py`, `test_migrationsprobe.py`) laden `schema.sql` roh
   und lassen `migrate.anwenden()` einen Teil der Migrationen erneut
   durchlaufen (Bestandsprobe für Nachzug). Da `schema.sql` die Tabelle
   bereits enthält, schlug Migration 16 mit
   `table buchung_aenderung already exists` fehl. Fix: `CREATE TABLE IF
   NOT EXISTS` und `CREATE INDEX IF NOT EXISTS`, analog zu
   `auslage`/`ausgleich`/`request_wiederholung`/`hinweis_aus` in
   `db/schema.sql` (gleiches, bereits etabliertes Muster).
2. **Spaltenreihenfolge nach Nachzug wich von `schema.sql` ab.** Der
   Vorgänger hatte `original_id`/`storniert_am`/`original_zeile_id` inline
   in `CREATE TABLE buchung`/`buchungszeile` deklariert. Nach einem echten
   Migrations-Nachzug (`ALTER TABLE ... ADD COLUMN`) landen neue Spalten
   aber immer am Tabellenende, nicht an der inline gewählten Stelle —
   `tests/test_p51_storno.py::test_017_zweimal_und_frischschema_exakt`
   verglich `sqlite_master.sql` von Frischschema vs. Nachzug und schlug
   fehl. Fix: `db/schema.sql` folgt jetzt demselben Muster wie `kredit_id`
   (Kommentar "Migration 015: Index zuletzt anlegen..." dort) —
   `original_id`/`storniert_am`/`original_zeile_id` werden nicht mehr
   inline deklariert, sondern per `ALTER TABLE ... ADD COLUMN` an der
   Stelle nachgezogen, die Migration 017 entspricht (nach dem
   `buchung_aenderung`-Block); die Views `v_zeile`/`v_einnahmen_ausgaben`
   wurden dorthin mitverschoben (identischer SQL-Text wie in der
   Migrationsdatei, damit `sqlite_master.sql` exakt übereinstimmt).

Nach beiden Fixes läuft `test_017_zweimal_und_frischschema_exakt` grün und
alle vorher an "table already exists" gescheiterten Bestandstests kommen
wieder bis zu ihrer eigentlichen Prüfung durch.

## Teil 1: P50b (Historie) und P43b (Wiederholungs-Topf)

- `db/migrations/016_buchung_aenderung.sql`, `db/schema.sql`: Tabelle
  `buchung_aenderung` (`buchung_id`, `zeitpunkt`, `feld`, `alt`, `neu`,
  `grund`, `quelle`); `request_wiederholung.art` um `'beleg_uebernahme'`
  erweitert (Rename+Neubau, da SQLite kein `ALTER ... ALTER CHECK` kennt).
- `app/routers/buchungen.py`: `_update_buchung` protokolliert Kopf- und
  Zeilenänderungen (je geändertes Feld ein Eintrag, unveränderte Felder
  erzeugen keinen); `GET /api/buchungen/{id}/verlauf` liefert die Historie
  neuester zuerst.
- `app/routers/beleg_auswertung.py`: `auswertung_uebernehmen` nutzt jetzt
  den eigenen Wiederholungs-Topf `'beleg_uebernahme'` statt sich `'buchung'`
  mit der normalen Erfassung zu teilen.
- `app/schemas.py`: `BuchungIn.grund` (optional, nur bei PUT ausgewertet).
- `static-neu/pages/buchungen.js`/`.css`: Abschnitt „Historie" im
  Bearbeiten-Dialog, Feld „Grund der Änderung".
- `tests/test_p50b_verlauf.py`: 10 Tests (Protokollierung Kopf/Zeilen,
  Verlauf-Reihenfolge, P43b-Topftrennung, `node --check`).

## Teil 2: P51 (Storno und Erstattung)

- `db/migrations/017_storno_erstattung.sql`, `db/schema.sql`: `buchung`
  bekommt `original_id`/`storniert_am`, `buchungszeile` bekommt
  `original_zeile_id`; Views `v_zeile`/`v_einnahmen_ausgaben` neu (Storno
  fällt aus den Summen).
- `app/routers/buchungen.py`: `GET /api/buchungen/{id}` (neuer
  Einzel-Endpunkt, von der Karte als "_buchung_detail erweitern"
  beschrieben — davor gab es nur die Liste); `POST .../stornieren`,
  `.../entstornieren` (mit Bereichsprüfung, 422 bei Umbuchung, 409 bei
  Doppel-Aktion, Protokollierung über `buchung_aenderung`); `POST
  .../erstatten` (Gegenrichtung, Zeilen-Validierung: Zielkategorie muss
  `richtung='beides'` haben, Summe aller Erstattungen je Zeile darf
  `betrag_cent` nicht übersteigen, keine Erstattung einer Erstattung, keine
  Erstattung auf stornierter/umgebuchter Buchung); `_buchung_detail` liefert
  zusätzlich `original_id`/`storniert_am`/`erstattungen`/`netto_cent` sowie
  je Zeile `bereits_erstattet_cent`/`rest_cent`.
- `static-neu/pages/buchungen.js`/`.css`: Stornieren/Storno-zurücknehmen
  als Zeilenaktion mit Markierung (durchgestrichen + Pill), Abschnitt
  „Erstattungen" im Bearbeiten-Dialog mit Rest-Vorbelegung je Zeile.
- `tests/test_p51_storno.py`: 12 Tests (Storno/Entstorno inkl.
  Summenwirkung und Doppel-409, Teil-/Vollerstattung beider Richtungen,
  Übererstattung-422, falsche Zielkategorie-422, Erstattung auf
  Umbuchung/Storno/Erstattung-Fehlerfälle, Migration-017-Idempotenz/
  Frischschema-Vergleich, `node --check`).

## Testzahlen

Gesamtsuite (`FINANZ_DB=%TEMP%\p51-test.db`,
`python -m unittest discover -s tests`): **419 Tests, 403 grün, 14
Failures, 1 Error, 1 skipped** (Sollwert laut Auftrag war 397 + 22 eigene
= 419, davon alle eigenen grün).

Alle 15 fehlschlagenden/fehlerhaften Tests sind **vorbestehende Tests**
außerhalb des erlaubten Scopes (nicht verändert) und scheitern an
**korrekten, durch die neuen Migrationen 16/17 verursachten** Abweichungen
von hartcodierten Erwartungen aus früheren Paketen:

- **11 Tests mit hartcodierter Migrationsliste/-anzahl bis 15**, jetzt
  16/17 zusätzlich vorhanden: `test_auslagen.py::test_nachzug_zweimal_und_schema_identisch`,
  `test_bereiche_migration.py::test_current_schema_accepts_migration_and_seed_has_separate_domains`,
  `::test_migration_assigns_domains_and_removes_only_foreign_memberships`,
  `::test_schema_and_migration_have_identical_structure`,
  `test_konten_bewegungen.py::test_bestandskopie_nachzug_und_schema_identisch`,
  `test_kredit.py::test_migration_007_zweimal_und_view`,
  `::test_migration_015_zieht_alte_marker_nach_und_protokolliert_fehlende_kredite`,
  `test_migrate.py::test_alte_datenbank_erhaelt_basis_version_und_einmalige_sicherung`,
  `::test_neue_datenbank_ist_auf_version_15_ohne_anstehende_migrationen`,
  `test_migrationsprotokoll.py::test_ungeklaerte_umbuchung_wird_nachzugfest_protokolliert_und_nicht_doppelt`,
  `test_saldoanker.py::test_migration_006_idempotent`.
- **1 Test mit hartcodiertem `status['aktuell']==15`**:
  `test_migrate.py::test_schema_endpoint_liefert_erwartete_felder`.
- **1 Test mit hypothetischer Spaltensimulation**:
  `test_migrationsprobe.py::test_neutral_und_kostenstorno_werden_als_abweichung_gemeldet`
  simuliert testintern eine (bis jetzt fiktive) Spalte
  `buchung.storniert_am` per `ALTER TABLE ... ADD COLUMN`, um Abweichungen
  in einem Vergleichswerkzeug zu prüfen. Seit Migration 017 ist
  `storniert_am` eine echte Spalte — der simulierte `ALTER` kollidiert
  jetzt mit der echten (`duplicate column name`).
- **1 Test mit veraltetem Snapshot ohne die neuen Antwortfelder**:
  `test_p20_snapshots.py::test_antworten_vor_umbau` vergleicht eine feste
  JSON-Erwartung ohne `kredit_id`/`original_id`/`storniert_am`/etc.
- **1 Test, der explizit die Abwesenheit des Verlauf-Endpunkts prüft**:
  `test_p50_buchungen.py::test_verlauf_endpunkt_existiert_in_diesem_paket_nicht`
  — durch P50b (dieses Paket) bewusst überholt, der Endpunkt soll jetzt
  existieren.

Keiner dieser Fälle deutet auf eine funktionale Regression hin; alle sind
direkte, erwartbare Folgen der beiden neuen, legitimen Migrationen bzw. der
mit P50b beauftragten Funktionalität. Weisungsgemäß wurden diese
Bestandstests nicht verändert.

`node --check static-neu/pages/buchungen.js` fehlerfrei.

## Browserprüfung (Teil 2)

Testinstanz: `FINANZ_DB=%TEMP%\p51-app.db`, `FINANZ_INSTANZ=test`,
`FINANZ_AUTH_FILE=%TEMP%\p51-auth.json`, `FINANZ_TEST_AUTH_BYPASS=1`,
uvicorn Port 8038 als eigener Prozess (PowerShell `Start-Process`).
Testdaten (Kategorien, eine Ausgabe 100 €) per API angelegt. Geprüft mit
Playwright-Tools unter `http://127.0.0.1:8038/neu/index.html#/buchungen`:

- **Verlauf nach PUT**: Text geändert + Grund „Testkorrektur" → Eintrag
  `text: "P51 Testausgabe" → "P51 Testausgabe geaendert" · Testkorrektur`
  erscheint sofort im Verlauf.
- **Stornieren**: Bestätigungsdialog + Grund-Prompt (`Testgrund Storno`)
  → Zeile durchgestrichen mit Pill „storniert", Button wird „Storno
  zurücknehmen", Summenzeile fällt von „Ausgaben € 100,00 · Saldo -€ 100,00"
  auf „€ 0,00 · € 0,00" (View-Filter greift sofort).
- **Storno zurücknehmen**: Summen und Markierung wieder wie vor dem
  Storno; beide Aktionen zusammen im Verlauf sichtbar
  (`storniert_am: – → ... · Testgrund Storno`, `storniert_am: ... → – `).
- **Erstattung mit Rest-Vorbelegung**: Formular zeigt „Rest € 100,00"
  vorbelegt; 60 € erfasst → neue Einnahme-Buchung mit `original_id`,
  `netto_cent` der Originalbuchung sinkt auf 4000, `rest_cent` der Zeile
  auf 4000; Liste zeigt beide Buchungen getrennt
  (Summen: Einnahmen € 60,00 · Ausgaben € 100,00 · Saldo -€ 40,00).
- **Überschreitung abgewiesen**: Erstattung über 50 € auf den verbliebenen
  Rest von 40 € → 422 mit `{"detail": "...", "zeile_id": 1,
  "bereits_erstattet_cent": 6000, "rest_cent": 4000}`.
- **Konsole**: keine Fehler außer dem irrelevanten `favicon.ico`-404.
- **Mobil 375 px**: Buchungsliste und Summenzeile sauber einspaltig,
  keine horizontale Überlauf, Bottom-Nav funktionsfähig (Screenshot
  geprüft).

Server danach beendet (`Stop-Process`), Testdatenbanken liegen nur unter
`%TEMP%`.

## Commits

Ein gemeinsamer Commit für beide Teile:

```
a00c8428cafac51ac76d6bc7704f1853b7711f3a
P50b: Historie je Buchung (Migration 016), Verlauf-Endpunkt und -Anzeige; P43b eigener Wiederholungs-Topf
P51: Storno beidseitig und Erstattung als verknuepfte Gegenbuchung (Migration 017)
```

**Begründung für den gemeinsamen statt zwei getrennte Commits**: Die vom
Vorgänger bereits verzahnt geschriebenen Dateien lassen sich nicht sauber
per Hunk trennen: `app/routers/buchungen.py` teilt `_buchung_detail`
zwischen beiden Paketen (Historie- und Storno/Erstattung-Felder im selben
Rückgabe-Dict), der neue `GET /api/buchungen/{id}`-Einzel-Endpunkt dient
sowohl dem Verlauf- als auch dem Erstattungs-Frontend; `db/schema.sql`
verschachtelt nach dem Idempotenz-Fix den `buchung_aenderung`-Block
(Teil 1) und die direkt anschließenden `ALTER TABLE`/View-Anweisungen
(Teil 2) im selben zusammenhängenden Abschnitt; `buchungen.js` rendert
Erstattungen- und Historie-Abschnitt im selben Dialog-Aufbau. Ein
`git add -p`-Split hätte das Risiko getragen, einen der beiden Teile in
einen inkonsistenten Zwischenzustand zu committen (z. B. Migration 017
ohne die zugehörige, in Migration 016 mitgelieferte
`buchung_aenderung`-Protokollierung der Storno-Aktionen). Laut Auftrag ist
ein gemeinsamer Commit in diesem Fall zulässig.

Nicht gepusht, nicht gemergt.

## Offene Punkte

- **15 vorbestehende Testfehler** wie oben beschrieben — echte, aber
  außerhalb des Auftragsscopes liegende Folgeschäden der neuen
  Migrationsnummern 16/17 bzw. der P50b-Funktionalität. Diese Tests
  gehören in einem eigenen kleinen Nachzug-Paket aktualisiert (hartcodierte
  Migrationslisten/-zahlen erhöhen, `test_migrationsprobe.py` anpassen an
  die jetzt echte `storniert_am`-Spalte, `test_p20_snapshots.py`-Snapshot
  erneuern, `test_p50_buchungen.py`-Test entfernen/umdrehen).
- Kein Playwright-Test für Erstattung einer Einnahme (Rücküberweisung) im
  Browser durchgeführt — nur die Ausgabenrichtung wurde interaktiv
  geprüft; die Gegenrichtung ist aber über
  `tests/test_p51_storno.py` unit-getestet.
- Keine Prüfung mit echten/größeren Datenmengen oder Mehrbenutzer-Szenario
  (außerhalb des Auftrags).
