# P14: Kredit mit Jahreszins, Zins und Tilgung getrennt

Meilenstein M1. Modell: `gpt-5.6-luna`, Aufwand medium. Branch `pkt/p14-kredit` von `neubau` (nach P11).

## 1. Ziel

Eine Kreditrate ist ein Geldabfluss mit zwei Wirkungen: der Zinsanteil ist eine Ausgabe, die Tilgung mindert die Schuld und zählt nicht als Ausgabe. Der Nutzer trägt einmal im Jahr Zins und Restschuld aus dem Kredit-Kontoauszug ein; die App verteilt den Zins centgenau auf die vorhandenen Raten und schätzt das laufende Jahr nach dem Vorjahr.

## 2. Kontext

Lies `docs/neubau/ARCHITEKTUR.md` Abschnitt 4 (Feld `neutral`) und 6, dann `app/routers/buchungen.py`, `app/routers/konten.py` (P11), `db/schema.sql` (View `v_einnahmen_ausgaben`, Trigger auf `buchungszeile`), `app/bereiche.py`, `tests/test_umbuchungen.py`. Fachliche Vorgabe: Fixzins-Annuität, monatlich gleiche Rate, jährlicher Kredit-Kontoauszug mit Zinsen und Restschuld.

## 3. Schnittstellen

Migration `db/migrations/007_kredit.sql` (und `db/schema.sql`):

```sql
ALTER TABLE buchungszeile ADD COLUMN neutral INTEGER NOT NULL DEFAULT 0 CHECK (neutral IN (0,1));
DROP VIEW v_einnahmen_ausgaben;
CREATE VIEW v_einnahmen_ausgaben AS SELECT * FROM v_zeile WHERE ist_transfer = 0 AND neutral = 0;
-- v_zeile muss neutral mitliefern: View neu anlegen mit bz.neutral AS neutral (und in P12 ergänztes storniert_am der Buchung berücksichtigen, falls vorhanden)

CREATE TABLE kredit (
    id                 INTEGER PRIMARY KEY,
    sparte_id          INTEGER NOT NULL REFERENCES sparte(id),
    konto_id           INTEGER REFERENCES bankkonto(id),
    name               TEXT NOT NULL,
    monatsrate_cent    INTEGER NOT NULL CHECK (monatsrate_cent > 0),
    zinssatz           REAL,
    beginn             TEXT NOT NULL,
    kategorie_zins_id  INTEGER NOT NULL REFERENCES kategorie(id),
    kategorie_rate_id  INTEGER NOT NULL REFERENCES kategorie(id),   -- bisherige Kategorie der Rate, z. B. Kreditrückzahlung
    aktiv              INTEGER NOT NULL DEFAULT 1 CHECK (aktiv IN (0,1))
);
CREATE TABLE kredit_jahr (
    kredit_id        INTEGER NOT NULL REFERENCES kredit(id) ON DELETE CASCADE,
    jahr             INTEGER NOT NULL,
    zins_cent        INTEGER NOT NULL,
    restschuld_cent  INTEGER,
    status           TEXT NOT NULL CHECK (status IN ('geschaetzt','bestaetigt')),
    beleg_id         INTEGER REFERENCES beleg(id),
    aktualisiert_am  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (kredit_id, jahr)
);
```

Buchungsmodell: Eine Rate ist eine Buchung `typ='ausgabe'` mit zwei Zeilen: Zins (`kategorie_zins_id`, `neutral=0`) und Tilgung (`kategorie_rate_id`, `neutral=1`). Der Kopfbetrag bleibt die volle Rate (Trigger summiert beide Zeilen), der Geldabfluss ist die volle Rate, in Einnahmen/Ausgaben zählt nur die Zinszeile.

Router `app/routers/kredite.py` (Präfix `/api`):

```
GET   /api/kredite?bereich_id=            → Liste mit {id, name, sparte_id, monatsrate_cent, beginn, jahre: [{jahr, zins_cent, restschuld_cent, status}]}
POST  /api/kredite                        {sparte_id, konto_id?, name, monatsrate_cent, zinssatz?, beginn, kategorie_zins_id, kategorie_rate_id} → 201
PATCH /api/kredite/{id}                   Teilfelder, aktiv
PUT   /api/kredite/{id}/jahre/{jahr}      {zins_cent, restschuld_cent?, beleg_id?} → status 'bestaetigt'; verteilt den Zins auf die Raten des Jahres (siehe Regeln); Antwort {raten: n, verteilt_cent, abweichungen: [...]}
POST  /api/kredite/{id}/raten             {datum, betrag_cent?, bankumsatz_id?, client_request_id?} → legt eine Ratenbuchung an (Betrag Standard monatsrate_cent), Zinsanteil nach Schätzung; 201
GET   /api/kredite/{id}/raten?jahr=       → Liste der Ratenbuchungen mit Zins- und Tilgungsanteil
```

Regeln:
- Verteilung bestätigter Jahreszins: `zins_cent` durch Anzahl der Raten des Jahres, Rest cent-weise auf die ersten Raten; Summe der Zinszeilen = `zins_cent` exakt. Tilgung = Rate − Zins je Buchung.
- Schätzung für Jahre ohne Bestätigung: Zinsanteil je Rate = bestätigter Vorjahreszins / Raten des Vorjahres; ohne Vorjahr: `zinssatz` × geschätzte Restschuld / 12, falls `zinssatz` vorhanden, sonst 0 mit Hinweis „Zinsanteil unbekannt, ganze Rate vorläufig als Tilgung" (Status `geschaetzt`, in der Antwort sichtbar).
- Abweichungen: Jahr mit weniger als 12 Raten oder Ratenbeträge ≠ `monatsrate_cent` → in `abweichungen` benennen, nicht erfinden.
- Bestehende Buchungen der Kategorie `kategorie_rate_id` (z. B. „Kreditrückzahlung") werden **nicht** automatisch umgedeutet; ein eigener Endpoint `POST /api/kredite/{id}/raten/zuordnen {buchung_ids: [...]}` wandelt ausgewählte bestehende Buchungen in Ratenbuchungen um (Zeilen aufteilen), nur auf ausdrücklichen Aufruf.
- Buchungen mit `neutral=1`-Zeilen sind in `GET /api/buchungen` gekennzeichnet (`neutral_cent`).
- Alle Endpoints mit Bereichsprüfung.

## 4. Nicht-Ziele

Kein Frontend. Keine Sondertilgungen, keine variablen Zinsen, keine Gebühren (als `abweichungen` melden). Keine automatische Umdeutung alter Buchungen.

## 5. Schritte

1. Migration 007, Views, `schema.sql`.
2. `app/kredite.py` mit Verteilung und Schätzung als reine Funktionen (`verteile_zins(zins_cent, raten) -> list[int]`).
3. Router.
4. Tests, Gesamtlauf, Bericht.

## 6. Tests

Neue Datei `tests/test_kredit.py`:
- `verteile_zins(1205, 12)` → 12 Werte, Summe 1205, Differenz zwischen größtem und kleinstem ≤ 1.
- Kredit anlegen, 12 Raten 2025 à 420 € anlegen (geschätzt), Jahreszins 2025 bestätigen mit 1.200 €: jede Rate hat Zinszeile 100 €, Tilgung 320 €; Ausgaben der Sparte 2025 enthalten 1.200 € Zins, nicht 5.040 €; Kontostand (Bewegungen) zeigt −5.040 €.
- Nur 11 Raten im Jahr: Bestätigung verteilt auf 11 und meldet Abweichung.
- Rate 2026 ohne Bestätigung: Zinsanteil = 100 € aus Vorjahr, Status geschätzt.
- Zuordnen bestehender Buchungen: zwei Buchungen der Ratenkategorie werden zu Raten; unbeteiligte Buchungen unverändert.
- `v_einnahmen_ausgaben` enthält keine `neutral=1`-Zeilen; bestehende Tests grün.
- Migration 007 zweimal idempotent; Views danach vorhanden.

## 7. Fertig heißt

- [ ] Alle Tests grün, vollständige Ausgabe im Bericht.
- [ ] Migration zweimal über den Runner; `schema.sql` und Nachzug gleich (inklusive Views).
- [ ] Keine Geheimnisse.
- [ ] Bericht geschrieben.

## 8. Bericht zurück

Geänderte und neue Dateien mit je einem Satz. Vollständige Testausgabe. Offene Punkte mit Grund. Keine Commits, kein Push.
