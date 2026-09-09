# P50: Buchungsliste mit Suche und Filtern, Bearbeiten mit Historie

Meilenstein M5. Modell: `gpt-5.6-luna`, Aufwand medium. Branch `pkt/p50-buchungsliste-bearbeiten` von `neubau` (nach P20, P30).

## 1. Ziel

Jede Buchung lässt sich in einer durchsuch- und filterbaren Liste finden und öffnen. Jede Änderung an Kopf oder Zeilen einer bestehenden Buchung wird feldweise mit altem und neuem Wert protokolliert, damit später nachvollziehbar ist, wer wann was warum geändert hat — ohne dass das die laufende Erfassung verlangsamt.

## 2. Kontext

Lies `docs/neubau/ARCHITEKTUR.md` Abschnitt 4 (Felder `version`, `client_request_id`, Tabelle `buchung_aenderung`) und 8 (Filtervertrag), dann `app/routers/buchungen.py` (`update_buchung`, bereits mit `version`-Prüfung aus P12, `_buchung_detail`), `app/auswertungen.py` und `GET /api/buchungen` mit Cursor aus P20, `app/bereiche.py`, `app/schemas.py` (`BuchungIn`), `docs/neubau/pakete/P30-frontend-geruest.md` für Gerüst, Router und Zustand von `static-neu`, `docs/neubau/prototyp/prototyp.html` Abschnitt „Buchungen" (`renderBuchungen`, `tableRows`, `editBooking`) als Vorlage für Liste, Spalten und Bedienung. `pages/erfassen.js` aus dem Frontend-Gerüst ist noch nicht gebaut; dieses Paket baut das Bearbeiten deshalb als eigenständigen Dialog innerhalb von `pages/buchungen.js`, nicht als Umleitung auf eine Erfassungsseite.

## 3. Schnittstellen

Migration `db/migrations/011_buchung_aenderung.sql` (und `db/schema.sql`):

```sql
CREATE TABLE buchung_aenderung (
    id          INTEGER PRIMARY KEY,
    buchung_id  INTEGER NOT NULL REFERENCES buchung(id) ON DELETE CASCADE,
    zeitpunkt   TEXT NOT NULL DEFAULT (datetime('now')),
    feld        TEXT NOT NULL,
    alt         TEXT,
    neu         TEXT,
    grund       TEXT
);
CREATE INDEX idx_buchung_aenderung_buchung ON buchung_aenderung (buchung_id, zeitpunkt);
```

`app/routers/buchungen.py`:

```
PUT /api/buchungen/{id}   Body wie bisher (BuchungIn + version), zusätzlich optionales Feld grund: str | None
    → vergleicht vor dem Schreiben Kopf-Felder (sparte_id, datum, typ, zahlungsart, kontakt_id, person_id, text, notiz)
      und Zeilen (per Zeilen-ID: geändert, neu, entfernt) mit dem alten Stand und schreibt je geänderter Einheit
      genau eine Zeile in buchung_aenderung; unveränderte Felder erzeugen keinen Eintrag; kein inhaltlicher
      Unterschied → keine Einträge, Antwort wie bisher
GET /api/buchungen/{id}/verlauf?bereich_id=   → [{id, feld, alt, neu, grund, zeitpunkt}] absteigend nach zeitpunkt
```

Regeln für die Protokollierung:
- Kopf-Felder: `feld` = Spaltenname, `alt`/`neu` als Text (Zahlen und Daten als String, `NULL` bleibt `null`).
- Zeilen: neue Zeile → `feld='zeile_neu'`, `neu` = JSON `{kategorie_id, betrag_cent, notiz}`; entfernte Zeile → `feld='zeile_entfernt'`, `alt` = dasselbe JSON der alten Zeile; geänderte Zeile (gleiche `id`, anderer `kategorie_id`/`betrag_cent`/`notiz`) → ein Eintrag je geändertem Unterfeld, `feld='zeile_<id>_<unterfeld>'`.
- `grund` steht auf jedem in diesem Aufruf erzeugten Eintrag; ohne Angabe bleibt er `NULL`.
- Die bestehende `version`-Prüfung (409 bei Konflikt) aus P12 bleibt unverändert vor der Protokollierung; ein 409 erzeugt keinen Eintrag.
- `GET /api/buchungen/{id}/verlauf` prüft die Buchung über `pruefe_buchung` gegen den Bereich (404 bei fremdem Bereich).

`GET /api/buchungen` (aus P20) bleibt unverändert in diesem Paket; die Liste im Frontend nutzt genau diesen Endpoint mit `q`, Cursor und dem Filtervertrag (`sparte_id`, `auswertungsgruppe_id`, `von`/`bis`/`jahr`, `kategorie_id`, `richtung`, `zahlungsart`).

Frontend `static-neu/pages/buchungen.js` (`export function render(root, state)`):
- Kopfzeile mit Suchfeld (`q`, debounced), Filterleiste aus dem Gerüst (Zeitraum, Richtung, Zahlungsart, Kategorie) plus lokale Auswahl der Sparte/Gruppe aus dem Zustand.
- Tabelle im Aufbau des Prototyps (`tableRows`): Datum, Text, Kategorie mit Sparten-Kürzel bei mehreren Sparten, Zahlungsart, Belegsymbol, Betrag mit Vorzeichen, Aktion „bearbeiten"; „mehr laden" über den Cursor aus P20; Summenzeile aus `summen`.
- Bearbeiten-Dialog: alle Kopf-Felder und Zeilen editierbar (gleiche Validierung wie serverseitig: Zeilen-Summe, Kategorie muss zur Sparte gehören), Pflichtfeld „Grund" nur als Vorschlagsfeld (nicht erzwungen), Speichern ruft `PUT /api/buchungen/{id}` mit `version` aus der geladenen Buchung; 409 lädt die Buchung neu und zeigt einen Hinweis statt stillschweigend zu überschreiben.
- Historie-Ansicht im selben Dialog: Liste aus `GET /api/buchungen/{id}/verlauf`, je Eintrag „Feld: alt → neu, Zeitpunkt, Grund".

## 4. Nicht-Ziele

Keine Schnellerfassung (`pages/erfassen.js`, eigenes Paket). Kein Storno, keine Erstattung (P51). Keine Änderung an `GET /api/buchungen` oder am Filtervertrag aus P20. Keine Protokollierung beim Anlegen (`POST /api/buchungen`) oder Löschen, nur bei `PUT`.

## 5. Schritte

1. Migration 011, `schema.sql`.
2. `PUT /api/buchungen/{id}` um Vergleich und Protokollierung erweitern, `GET /api/buchungen/{id}/verlauf`.
3. `static-neu/pages/buchungen.js`: Liste, Filter, Suche, Bearbeiten-Dialog, Historie-Ansicht; Route in `app.js` eintragen (Platzhalter aus P30 ersetzen).
4. Tests, Gesamtlauf, Bericht.

## 6. Tests

Neue Datei `tests/test_buchungen_historie.py`:
- `PUT` ändert Datum und den Betrag einer bestehenden Zeile: `buchung_aenderung` enthält je einen Eintrag für `datum` und `zeile_<id>_betrag_cent` mit korrektem alt/neu; `GET /verlauf` liefert beide, neuester zuerst.
- `PUT` mit identischen Werten (keine inhaltliche Änderung) erzeugt keine Einträge.
- `PUT` mit `grund="Tippfehler"`: alle in diesem Aufruf erzeugten Einträge tragen den Grund.
- `PUT` mit neuer Zeile und entfernter Zeile: `zeile_neu` und `zeile_entfernt` mit passendem JSON.
- `PUT` mit falscher `version` → weiterhin 409 (Regression aus P12), keine Einträge in `buchung_aenderung`.
- `GET /api/buchungen/{id}/verlauf` einer Buchung aus fremdem Bereich → 404.
- Bestehende Tests aus P12 und P20 (`version`-Prüfung, Cursor-Liste, Suche) bleiben grün.
- `node --check static-neu/pages/buchungen.js` fehlerfrei.

## 7. Fertig heißt

- [ ] Alle Tests grün, vollständige Ausgabe im Bericht.
- [ ] Migration zweimal über den Runner; `schema.sql` und Nachzug gleich.
- [ ] Buchungsliste im Browser einmal geprüft: Suche, Filter, Bearbeiten, Historie sichtbar (Schritte im Bericht, oder ausdrücklich benannt, falls nicht möglich).
- [ ] Keine Geheimnisse, keine echten Namen.
- [ ] Bericht geschrieben.

## 8. Modell und Aufwand

`gpt-5.6-luna`, Aufwand medium: normale Umsetzung nach klarer Vorgabe (Diff-Protokollierung, Listen-Seite nach Prototyp-Vorlage), keine Architekturentscheidung.

## 9. Bericht zurück

Geänderte und neue Dateien mit je einem Satz. Vollständige Testausgabe. Offene Punkte mit Grund. Keine Commits, kein Push.
