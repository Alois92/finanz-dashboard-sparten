# F-N3: Kreditraten über eigene Spalte statt Notiz-Marker

Fix aus der Schuldenliste (N3). Modell `gpt-5.6-luna`, Aufwand medium. Arbeitsort `C:\Users\lblet\dev\wt-n3-kreditrate`, Zweig `fix/n3-kreditrate-spalte` (auf `neubau`, Schema-Version 14). Keine Commits, kein Push.

## Befund

Kreditraten werden über den Freitext `buchung.notiz = 'Kreditrate:<id>'` erkannt (`app/routers/kredite.py`, Funktion bei Zeile 82, und alle Stellen, die diesen Marker lesen). Bearbeitet der Nutzer die Notiz, fällt die Rate still aus der Zinsverteilung.

## Ziel

- **Migration 015** `015_kredit_buchung.sql`: Spalte `buchung.kredit_id INTEGER NULL REFERENCES kredit(id)` plus Index. Nachzug: für jede Buchung mit Notiz-Muster `Kreditrate:<id>` und existierendem Kredit die Spalte setzen; der Marker in der Notiz bleibt stehen (kein Textverlust). Buchungen mit Marker auf nicht existierenden Kredit ins `migrationsprotokoll` (Migration 012 zeigt das Muster; falls SQL dafür nicht reicht, Migration als `.py` nach dem Muster von 012).
- `db/schema.sql` identisch nachziehen. Test nach Muster `tests/test_p20_migration.py`: exakter `sqlite_master`-Vergleich, Migration zweimal.
- Alle Lesestellen des Markers auf `kredit_id` umstellen. Schreibstellen setzen `kredit_id` und schreiben keinen Marker mehr in die Notiz. Die Notiz bleibt freies Feld des Nutzers.
- API: Buchungsantworten liefern `kredit_id`; Zuordnen und Lösen einer Rate setzt bzw. leert die Spalte.

## Nicht-Ziele

Keine Änderung an der Zins- und Tilgungsrechnung selbst (P14), kein Frontend.

## Tests

`tests/test_kredit.py` erweitern: Rate zuordnen → `kredit_id` gesetzt; Notiz frei editierbar ohne Verlust der Zuordnung; Nachzug setzt `kredit_id` aus altem Marker; Marker auf fehlenden Kredit landet im Protokoll. Alle Erwartungslisten in `tests/` um Version 15 ergänzen (`grep -rn "anwenden(" tests/`).

## Interpreter

`C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Scripts\python.exe -m unittest discover -s tests`, vorher `FINANZ_DB` auf eine Wegwerf-Datei unter `%TEMP%`. Sandbox-Probleme mit der Auth-Suite im Bericht nennen und die betroffenen Dateien isoliert grün zeigen.

## Fertig heißt

- [ ] Tests grün, Ausgabe in `docs/neubau/berichte/N3-tests.txt`
- [ ] Migration zweimal, `schema.sql` gleich Nachzug
- [ ] Kein Marker mehr in neuen Notizen, keine Geheimnisse, keine neuen Abhängigkeiten
- [ ] Bericht `docs/neubau/berichte/N3-runde1.md`: Dateien je ein Satz, offene Punkte mit Grund
