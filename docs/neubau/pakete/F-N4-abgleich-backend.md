# F-N4: Abgleich manuell erfasster Bankbuchungen mit importierten Umsätzen (Backend)

Fix aus der Schuldenliste (N4), Backend-Anteil für P42. Modell `gpt-6-astra`, Aufwand medium. Arbeitsort `C:\Users\lblet\dev\wt-n4-abgleich`, Zweig `fix/n4-abgleich-backend` (auf `neubau`, Schema-Version 14). Keine Commits, kein Push. **Keine neue Migration.** Falls doch zwingend: Nummer **016** und Begründung im Bericht.

## Befund

Eine manuell erfasste Bankbuchung erzeugt eine Bewegung `quelle='manuell'` (`app/bewegungen.py` ab Zeile 90). Der spätere CSV-Import erzeugt für denselben Umsatz eine zweite Bewegung `quelle='import'` (`import_bewegung` in `app/routers/import_bank.py`, Aufruf bei Zeile 276). Solange beide nicht einander zugeordnet sind, zählt der Kontostand doppelt. Architektur Abschnitt 3 verlangt: beim späteren Abgleich wird die manuelle Bewegung durch die importierte ersetzt, nicht addiert.

## Ziel

1. `GET /api/bankumsaetze/{id}/kandidaten` (Bereich über `bereich_dep`): Buchungen desselben Kontos ohne `bankumsatz_id`, Betrag gleich (Vorzeichen beachten), Datum plus/minus 5 Tage, sortiert nach Datumsabstand. Antwort `{"kandidaten":[{"buchung_id","datum","betrag_cent","text","abstand_tage"}]}`.
2. `POST /api/bankumsaetze/{id}/zuordnen`, Body `{"buchung_id": int}`: prüft Bereich, Konto und Betrag; setzt `buchung.bankumsatz_id` und `bankumsatz.importstatus='verbucht'`; storniert die manuelle Bewegung der Buchung (`storniert_am`) und hängt die importierte Bewegung an die Buchung (`buchung_bewegung`). Betragsabweichung → 409 mit `detail`. Wiederholung ist idempotent.
3. `POST /api/bankumsaetze/{id}/zuordnung-loesen`: kehrt das um (manuelle Bewegung wieder aktiv, Umsatz wieder `offen`, `bankumsatz_id` leer).
4. `GET /api/konten/{id}/offene-abgleiche`: Anzahl und Liste manueller Bewegungen ohne Umsatz sowie offene Umsätze mit mindestens einem Kandidaten. Grundlage für einen Hinweis in der Übersicht (P31).

Die vorhandene Übernahme eines Umsatzes als neue Buchung im Bankimport bleibt unverändert. Die neue Zuordnung ist der zweite Weg für bereits erfasste Buchungen.

## Tests

Neue Datei `tests/test_abgleich.py`: manuelle Bankbuchung plus Import desselben Umsatzes → Kontostand vor Zuordnung doppelt, nach Zuordnung einfach; Kandidatenliste findet die Buchung; falscher Betrag → 409; Lösen stellt den Zustand her; Bereich 2 sieht einen Umsatz aus Bereich 1 nicht (404).

## Interpreter

`C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Scripts\python.exe -m unittest discover -s tests`, vorher `FINANZ_DB` auf eine Wegwerf-Datei unter `%TEMP%`. Sandbox-Probleme mit der Auth-Suite im Bericht nennen und die betroffenen Dateien isoliert grün zeigen.

## Fertig heißt

- [ ] Tests grün, Ausgabe in `docs/neubau/berichte/N4-tests.txt`
- [ ] Antwort-JSON aller neuen Endpunkte wörtlich im Bericht (Grundlage für die P42-Karte)
- [ ] Keine Geheimnisse, keine neuen Abhängigkeiten
- [ ] Bericht `docs/neubau/berichte/N4-runde1.md`
