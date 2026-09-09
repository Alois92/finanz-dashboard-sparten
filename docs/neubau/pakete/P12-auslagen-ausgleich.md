# P12: Auslagen und Ausgleich mit Zuordnungen

Meilenstein M1. Modell: `gpt-6-astra`, Aufwand high. Branch `pkt/p12-auslagen-ausgleich` von `neubau` (nach P11).

## 1. Ziel

Eine privat bezahlte Ausgabe für eine andere Sparte bleibt bei der Sparte, der die Kosten gehören, und erzeugt eine offene Forderung des Zahlers. Ein Ausgleich zahlt Forderungen ganz oder teilweise, nachvollziehbar je Auslage, wiederholungssicher, mit Rücknahme.

## 2. Kontext

Lies `docs/neubau/ARCHITEKTUR.md` Abschnitt 4 und 5, dann `app/routers/buchungen.py`, `app/routers/konten.py` (P11), `app/bereiche.py` (P10), `db/schema.sql`, `tests/test_konten_bewegungen.py`. Fachliche Vorgabe des Nutzers: Ausgleich jederzeit, Teilbeträge erlaubt, meist bar an die Privatperson, manchmal Überweisung; negative Kassa warnt, sperrt nicht.

## 3. Schnittstellen

Migration `db/migrations/005_auslagen_ausgleich.sql` (und `db/schema.sql`):

```sql
ALTER TABLE buchung ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE buchung ADD COLUMN client_request_id TEXT;
CREATE UNIQUE INDEX idx_buchung_client_request ON buchung (client_request_id) WHERE client_request_id IS NOT NULL;

CREATE TABLE auslage (
    id               INTEGER PRIMARY KEY,
    buchung_id       INTEGER NOT NULL UNIQUE REFERENCES buchung(id) ON DELETE CASCADE,
    zahler_sparte_id INTEGER NOT NULL REFERENCES sparte(id),
    zahler_konto_id  INTEGER REFERENCES bankkonto(id),
    betrag_cent      INTEGER NOT NULL CHECK (betrag_cent > 0),
    erstellt_am      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE ausgleich (
    id                INTEGER PRIMARY KEY,
    transfer_id       INTEGER NOT NULL REFERENCES transfer(id),
    datum             TEXT NOT NULL,
    von_sparte_id     INTEGER NOT NULL REFERENCES sparte(id),   -- zahlt (z. B. Hof)
    nach_sparte_id    INTEGER NOT NULL REFERENCES sparte(id),   -- erhält (z. B. Privatperson)
    betrag_cent       INTEGER NOT NULL CHECK (betrag_cent > 0),
    zahlungsart       TEXT NOT NULL CHECK (zahlungsart IN ('bar','bank')),
    client_request_id TEXT UNIQUE,
    aufgehoben_am     TEXT,
    notiz             TEXT,
    erstellt_am       TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE ausgleich_zuordnung (
    ausgleich_id INTEGER NOT NULL REFERENCES ausgleich(id) ON DELETE CASCADE,
    auslage_id   INTEGER NOT NULL REFERENCES auslage(id) ON DELETE CASCADE,
    betrag_cent  INTEGER NOT NULL CHECK (betrag_cent > 0),
    PRIMARY KEY (ausgleich_id, auslage_id)
);
CREATE INDEX idx_auslage_zahler ON auslage (zahler_sparte_id);
```

Buchung anlegen und ändern (`POST`/`PUT /api/buchungen`): neues optionales Feld `bezahlt_von_sparte_id`. Regeln:
- Nur bei `typ='ausgabe'`; bei Einnahmen 422.
- `bezahlt_von_sparte_id` muss eine Sparte mit `typ='privat'` desselben Bereichs sein und ungleich `sparte_id`; sonst 422.
- Erzeugt `auslage` mit `betrag_cent` = Buchungsbetrag; die Kassa-Bewegung (bei bar) liegt auf der Kassa des Zahlers, nicht der Ziel-Sparte (Anpassung der Logik aus P11).
- `PUT`: Betrag darf nicht unter die Summe der Zuordnungen nicht aufgehobener Ausgleiche fallen → 409 mit `{"detail": "...", "ausgleiche": [ids]}`. Entfernen von `bezahlt_von_sparte_id` nur, wenn keine Zuordnungen bestehen.
- `client_request_id` optional; gleicher Schlüssel mit gleichen Nutzdaten (SHA-256 des kanonischen JSON) → dieselbe Antwort (200 statt 201, gleiche Buchungs-ID); gleicher Schlüssel mit anderen Nutzdaten → 409.
- `version`: `PUT` verlangt `version` im Body; stimmt sie nicht → 409. Antworten enthalten die neue Version.

Neuer Router `app/routers/auslagen.py` (Präfix `/api`):

```
GET  /api/auslagen?bereich_id=&stichtag=&sparte_id=&zahler_sparte_id=
     → [{zahler_sparte_id, sparte_id, offen_cent, anzahl, auslagen: [{id, buchung_id, datum, text, kategorie, betrag_cent, offen_cent}]}]
     gruppiert nach (Zahler, Ziel-Sparte); offen = betrag − Zuordnungen nicht aufgehobener Ausgleiche bis stichtag (Standard heute)
POST /api/ausgleiche
     {von_sparte_id, nach_sparte_id, auslage_ids: [...], datum, betrag_cent, zahlungsart, von_konto_id?, nach_konto_id?, client_request_id?, notiz?}
     → 201 {id, transfer_id, zuordnungen: [{auslage_id, betrag_cent}], warnungen: ["Kassa Hof hat nur 8.744,69 €, danach negativ"]}
DELETE /api/ausgleiche/{id}   → aufgehoben_am setzen, Transfer stornieren (P11), 204
GET  /api/ausgleiche?bereich_id=&sparte_id=&jahr=   → Liste mit Zuordnungen
```

Regeln für `POST /api/ausgleiche`:
- Alle `auslage_ids` gehören zu Buchungen der `von_sparte_id` mit Zahler `nach_sparte_id` und haben offen > 0; sonst 422.
- `betrag_cent` ≤ Summe der offenen Beträge der gewählten Auslagen; sonst 422 mit Summe.
- Verteilung FIFO nach Buchungsdatum, dann Auslage-ID.
- Konten: bei `bar` Standard Kassa der `von_sparte_id` → Kassa der `nach_sparte_id`; bei `bank` müssen `von_konto_id` und `nach_konto_id` angegeben sein. Transfer `art='ausgleich'` mit zwei Bewegungen `quelle='ausgleich'`.
- Kassa-Warnung: bei `bar` und Kontostand der Quell-Kassa < Betrag → Warnung im Antwortfeld, kein Abbruch.
- Datum: gültiges ISO-Datum, nicht in der Zukunft, nicht vor dem ältesten gewählten Auslagen-Datum; sonst 422.
- `client_request_id` wie bei Buchungen.
- Buchungen mit Auslage in Listen (`GET /api/buchungen`) tragen `auslage: {zahler_sparte_id, offen_cent, ausgeglichen: bool}`.

## 4. Nicht-Ziele

Kein Frontend. Keine Saldoanker (P13). Keine Änderung an Import oder Regeln. Keine automatische Umdeutung der Kategorie „Hohenegg" oder anderer Altdaten.

## 5. Schritte

1. Migration 005 und `schema.sql`.
2. Buchungs-Router: `bezahlt_von_sparte_id`, `client_request_id`, `version`, Kassa des Zahlers.
3. Router `auslagen.py`: Liste, Ausgleich anlegen, aufheben, Liste der Ausgleiche.
4. Tests, Gesamtlauf, Bericht.

## 6. Tests

Neue Datei `tests/test_auslagen.py`:
- Hofausgabe 100 € bar, `bezahlt_von_sparte_id` = Privatsparte: Auslage offen 100 €, Kassa der Privatsparte −100 €, Kassa des Hofs unverändert, Hof-Ausgaben +100 €, Privat-Ausgaben unverändert.
- Ausgleich 30 € bar: Zuordnung 30 €, offen 70 €, Hof-Kassa −30 €, Privat-Kassa +30 €, Einnahmen und Ausgaben beider Sparten unverändert.
- Zweiter Ausgleich mit demselben `client_request_id` und denselben Daten → 200, keine zweite Zuordnung; mit anderen Daten → 409.
- Ausgleich über 80 € bei 70 € offen → 422.
- Ausgleich aufheben: offen wieder 100 €, Transfer storniert, Kontostände wie vorher.
- `PUT` der Buchung auf 20 € bei 30 € zugeordnet → 409 mit Ausgleichs-ID; `PUT` mit falscher `version` → 409.
- Einnahme mit `bezahlt_von_sparte_id` → 422; Zahler aus anderem Bereich → 404.
- FIFO: drei Auslagen (10, 20, 30 € an drei Tagen), Ausgleich 25 € → Zuordnungen 10 und 15, dritte unberührt.
- Kassa-Warnung: Hof-Kassa 10 €, Ausgleich 30 € bar → 201 mit Warnung.
- Migration 005 zweimal idempotent.

## 7. Fertig heißt

- [ ] Alle Tests grün, vollständige Ausgabe im Bericht.
- [ ] Migration zweimal über den Runner; `schema.sql` und Nachzug gleich.
- [ ] Keine Geheimnisse, keine echten Namen.
- [ ] Bericht geschrieben.

## 8. Bericht zurück

Geänderte und neue Dateien mit je einem Satz. Vollständige Testausgabe. Offene Punkte mit Grund. Keine Commits, kein Push.
