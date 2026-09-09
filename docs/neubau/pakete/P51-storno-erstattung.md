# P51: Storno und Erstattung in beide Richtungen

Meilenstein M5. Modell: `gpt-6-astra`, Aufwand medium. Branch `pkt/p51-storno-erstattung` von `neubau` (nach P50).

## 1. Ziel

Eine fehlerhafte Buchung lässt sich stornieren, ohne sie zu löschen, und der Storno lässt sich zurücknehmen, falls er ein Versehen war. Geld, das teilweise oder ganz zurückkommt (Rückerstattung einer Ausgabe) oder das man selbst teilweise zurückzahlt (Rücküberweisung einer zu hohen Einnahme), wird als eigene, verknüpfte Buchung erfasst und mindert die Nettosumme der ursprünglichen Kategorie, ohne den ursprünglichen Betrag zu verändern.

## 2. Kontext

Lies `docs/neubau/ARCHITEKTUR.md` Abschnitt 4, dann `docs/neubau/pakete/P50-buchungsliste-bearbeiten.md` (Historie, `buchung_aenderung`, Frontend-Struktur der Buchungsliste), `app/routers/buchungen.py` (`_buchung_detail`, `update_buchung`, `_pruefe_buchungsreferenzen`), `app/routers/kredite.py` und `db/schema.sql` (Views `v_zeile`, `v_einnahmen_ausgaben`, wie P14 sie zuletzt definiert hat), `app/bereiche.py`. Fachliche Entscheidung des Nutzers: Storno wirkt in beide Richtungen (stornieren und der Storno selbst lässt sich zurücknehmen); Erstattung gibt es für Ausgaben (Geld kommt zurück, wird als Einnahme gebucht) genauso wie für Einnahmen (Geld wird zurückgezahlt, wird als Ausgabe gebucht).

## 3. Schnittstellen

Migration `db/migrations/012_storno_erstattung.sql` (und `db/schema.sql`):

```sql
ALTER TABLE buchung ADD COLUMN original_id INTEGER REFERENCES buchung(id);
ALTER TABLE buchung ADD COLUMN storniert_am TEXT;

DROP VIEW v_einnahmen_ausgaben;
DROP VIEW v_zeile;
CREATE VIEW v_zeile AS
SELECT
    bz.id            AS zeile_id,
    b.id             AS buchung_id,
    b.sparte_id      AS sparte_id,
    b.datum          AS datum,
    b.typ            AS typ,
    CASE b.typ WHEN 'ausgabe' THEN -bz.betrag_cent ELSE bz.betrag_cent END AS betrag_signed_cent,
    bz.betrag_cent   AS betrag_cent,
    bz.kategorie_id  AS kategorie_id,
    bz.neutral       AS neutral,
    b.storniert_am   AS storniert_am,
    CASE WHEN b.typ = 'umbuchung' THEN 1 ELSE 0 END AS ist_transfer
FROM buchungszeile bz
JOIN buchung b ON b.id = bz.buchung_id;
CREATE VIEW v_einnahmen_ausgaben AS
SELECT * FROM v_zeile WHERE ist_transfer = 0 AND neutral = 0 AND storniert_am IS NULL;
```

`app/routers/buchungen.py`, neue Endpunkte (Präfix `/api`):

```
POST /api/buchungen/{id}/stornieren        {grund?: str} → 200, setzt storniert_am; 409 wenn bereits storniert; 422 bei typ='umbuchung'
POST /api/buchungen/{id}/entstornieren     {grund?: str} → 200, setzt storniert_am = NULL; 409 wenn nicht storniert
POST /api/buchungen/{id}/erstatten
     {datum, zeilen: [{original_zeile_id, betrag_cent, kategorie_id?}], zahlungsart?, kontakt_id?, text?, grund?}
     → 201, legt eine neue Buchung an mit original_id = id, sparte_id wie das Original,
       typ = Gegenrichtung des Originals ('ausgabe' → 'einnahme', 'einnahme' → 'ausgabe'),
       je original_zeile_id eine Zeile mit kategorie_id (Standard: dieselbe Kategorie wie die Originalzeile)
GET  /api/buchungen/{id}   (bestehende Detail-Funktion _buchung_detail erweitern)
     → zusätzlich {original_id, storniert_am, erstattungen: [{id, datum, betrag_cent, storniert_am}],
                    netto_cent}   netto_cent = Kopfbetrag minus Summe nicht stornierter Erstattungen
```

Regeln:
- Stornieren/Entstornieren: nur auf Buchungen `typ IN ('einnahme','ausgabe')`, mit Bereichsprüfung (`pruefe_buchung`); jeder Aufruf schreibt einen Eintrag in `buchung_aenderung` (aus P50) mit `feld='storniert_am'`, altem und neuem Wert und `grund`.
- Umbuchungen werden weiterhin nur über `DELETE /api/buchungen/{id}` entfernt (unverändert aus P11/bestehendem Code); `stornieren` auf einer Umbuchung → 422.
- Erstattung:
  - Nur auf einer nicht stornierten Buchung `typ IN ('einnahme','ausgabe')`; auf einer stornierten Buchung → 409; auf einer Erstattung selbst (die also schon `original_id` trägt) → 422, es gibt keine Erstattung einer Erstattung.
  - Jede `original_zeile_id` muss zur Original-Buchung gehören; die verwendete Zielkategorie (Standard oder `kategorie_id`) muss `richtung='beides'` haben, sonst 422 mit Klartext, welche Kategorie fehlt.
  - Je `original_zeile_id` darf die Summe aller nicht stornierten Erstattungen ihren `betrag_cent` nicht übersteigen; sonst 422 mit `{"detail": "...", "zeile_id": ..., "bereits_erstattet_cent": ..., "rest_cent": ...}`.
  - Die neue Buchung erbt `sparte_id` des Originals; `bereich_dep` prüft trotzdem, dass beide im selben Bereich liegen.
  - Erstattung lernt keine Regel (anders als normale Buchungen; `original_id` ist gesetzt → `_lerne_regel` wird nicht aufgerufen).
- `GET /api/buchungen` (aus P20) und die Buchungsliste (P50) zeigen stornierte Buchungen weiterhin, durchgestrichen/markiert (`storniert_am` im Antwortfeld ist dafür bereits vorgesehen), zählen aber nicht mehr in Summen (View-Filter).

Frontend `static-neu/pages/buchungen.js` (aus P50 erweitern):
- Zeilenaktionen: „Stornieren" (mit Grund-Feld im Bestätigungsdialog), bei stornierten Zeilen stattdessen „Storno zurücknehmen"; visuelle Markierung analog zu den stillgelegten Kategorien im Prototyp (`katStillPill`-Muster).
- Im Bearbeiten-Dialog ein Abschnitt „Erstattungen": Liste bestehender Erstattungen mit Betrag und Datum, „Erstattung erfassen" öffnet ein kleines Formular je Zeile (Betrag vorbelegt mit dem offenen Rest, Zieldatum, optional andere Kategorie aus den `richtung='beides'`-Kategorien der Sparte).

## 4. Nicht-Ziele

Keine Änderung an Auslagen/Ausgleich (P12) oder Kredit (P14, P52). Keine automatische Erstattungs-Erkennung aus Bankimport. Keine Löschung stornierter Buchungen.

## 5. Schritte

1. Migration 012 (Views neu, `original_id`, `storniert_am`), `schema.sql`.
2. Stornieren/Entstornieren-Endpunkte mit Protokollierung.
3. Erstattungs-Endpunkt mit Zeilen-Validierung.
4. `_buchung_detail` erweitern; Frontend-Erweiterung in `pages/buchungen.js`.
5. Tests, Gesamtlauf, Bericht.

## 6. Tests

Neue Datei `tests/test_storno_erstattung.py`:
- Ausgabe stornieren: `storniert_am` gesetzt, taucht in `v_einnahmen_ausgaben`-Summen nicht mehr auf, bleibt in `GET /api/buchungen` sichtbar mit `storniert_am`.
- Storno zurücknehmen: `storniert_am` wieder `NULL`, zählt wieder in den Summen.
- Zweimal hintereinander stornieren → zweiter Aufruf 409; Entstornieren einer nicht stornierten Buchung → 409.
- Ausgabe 100 € teilweise erstatten (60 €): neue Buchung `typ='einnahme'`, `original_id` gesetzt; `GET /api/buchungen/{id}` der Originalbuchung zeigt `netto_cent=4000`; Ausgaben- und Einnahmensumme der Sparte zeigen beide Zeilen getrennt.
- Übererstattung (mehr als der offene Rest einer Zeile) → 422 mit `rest_cent`.
- Erstattung mit Zielkategorie ohne `richtung='beides'` → 422.
- Einnahme erstatten (Rücküberweisung): neue Buchung `typ='ausgabe'`, gleiche Regeln.
- Erstattung auf `typ='umbuchung'` → 422; Erstattung auf bereits stornierter Buchung → 409; Erstattung einer Erstattung → 422.
- Stornieren protokolliert einen Eintrag in `buchung_aenderung` (aus P50) mit `feld='storniert_am'`.
- Migration 012 zweimal idempotent; `v_zeile` liefert `storniert_am` und `neutral`; bestehende Tests aus P14 (neutral-Filter) und P20 (Summen) bleiben grün.
- `node --check static-neu/pages/buchungen.js` fehlerfrei.

## 7. Fertig heißt

- [ ] Alle Tests grün, vollständige Ausgabe im Bericht.
- [ ] Migration zweimal über den Runner; `schema.sql` und Nachzug gleich (inklusive Views).
- [ ] Storno, Storno-Rücknahme und Erstattung einmal im Browser geprüft oder ausdrücklich benannt, falls nicht möglich.
- [ ] Keine Geheimnisse, keine echten Namen.
- [ ] Bericht geschrieben.

## 8. Modell und Aufwand

`gpt-6-astra`, Aufwand medium: berührt Geldflüsse und eine bestehende Auswertungs-View direkt, verlangt sorgfältige Fallunterscheidung (beide Richtungen, Teil-Erstattung, Bereichsprüfung), aber keine neue Architektur.

## 9. Bericht zurück

Geänderte und neue Dateien mit je einem Satz. Vollständige Testausgabe. Offene Punkte mit Grund. Keine Commits, kein Push.
