# P13: Saldoanker, Kontostände, Kassazählung

Meilenstein M1. Modell: `gpt-5.6-luna`, Aufwand medium. Branch `pkt/p13-saldoanker-kassa` von `neubau` (nach P11).

## 1. Ziel

Jeder Kontostand ergibt sich aus einem datierten Anker (Auszug oder Eingabe) plus allen späteren Bewegungen. Unbekannte Anfangsstände werden als unbekannt gezeigt, nie als Null. Die Kassa kann gezählt werden; eine Differenz bleibt offen, bis der Nutzer sie klärt.

## 2. Kontext

Lies `docs/neubau/ARCHITEKTUR.md` Abschnitt 3 (Absatz Anker und Zählung), `app/routers/konten.py` (P11), `app/routers/import_bank.py` (`bankumsatz.saldo_nachher_cent`, Importzeitpunkt in `import_batch`), `app/bereiche.py`, `tests/test_konten_bewegungen.py`.

## 3. Schnittstellen

Migration `db/migrations/006_saldoanker_kassa.sql` (und `db/schema.sql`):

```sql
CREATE TABLE kontostand_anker (
    id          INTEGER PRIMARY KEY,
    konto_id    INTEGER NOT NULL REFERENCES bankkonto(id),
    stichtag    TEXT NOT NULL,                      -- Tagesendstand
    saldo_cent  INTEGER NOT NULL,
    quelle      TEXT NOT NULL CHECK (quelle IN ('auszug','manuell','import')),
    beleg_id    INTEGER REFERENCES beleg(id),
    notiz       TEXT,
    erstellt_am TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (konto_id, stichtag)
);
CREATE TABLE kassazaehlung (
    id             INTEGER PRIMARY KEY,
    konto_id       INTEGER NOT NULL REFERENCES bankkonto(id),
    datum          TEXT NOT NULL,
    gerechnet_cent INTEGER NOT NULL,
    gezaehlt_cent  INTEGER NOT NULL,
    differenz_cent INTEGER NOT NULL,
    status         TEXT NOT NULL DEFAULT 'offen' CHECK (status IN ('offen','geklaert')),
    notiz          TEXT,
    buchung_id     INTEGER REFERENCES buchung(id),
    erstellt_am    TEXT NOT NULL DEFAULT (datetime('now'))
);
```

Endpoints in `app/routers/konten.py`:

```
GET  /api/konten/{id}/stand?stichtag=
     → {konto_id, stichtag, stand_cent|null, anker: {stichtag, saldo_cent, quelle}|null,
        bewegungen_seit_anker: n, letzter_import: "2026-09-03"|null, import_alter_tage: n|null,
        datenstand: "aktuell"|"veraltet"|"unbekannt", hinweis: "..."}
     stand = letzter Anker ≤ stichtag + Summe nicht stornierter Bewegungen mit datum > anker.stichtag und ≤ stichtag;
     ohne Anker: stand_cent null, datenstand "unbekannt"; import_alter_tage > 30 → "veraltet"
POST /api/konten/{id}/anker        {stichtag, saldo_cent, quelle, beleg_id?, notiz?} → 201
     Antwort enthält zusätzlich {"gerechnet_cent": ..., "differenz_cent": ...}, wenn ein früherer Anker existiert:
     Differenz = neuer Saldo − (früherer Anker + Bewegungen dazwischen); sie wird zurückgegeben, nicht still korrigiert
GET  /api/konten/{id}/anker        → Liste
DELETE /api/konten/{id}/anker/{anker_id}  → 204
POST /api/konten/{id}/zaehlung     {datum, gezaehlt_cent, notiz?}   nur für art='kassa'
     → 201 {id, gerechnet_cent, differenz_cent, status: "offen"}
POST /api/konten/{id}/zaehlung/{zaehlung_id}/buchen   {kategorie_id, text?}
     → erzeugt eine Buchung (Einnahme bei positiver Differenz, Ausgabe bei negativer) in der Sparte der Kassa mit der übergebenen Kategorie,
       eine Bewegung auf der Kassa über die Differenz (quelle 'manuell'), setzt status 'geklaert' und buchung_id; 201
GET  /api/kassazaehlungen?bereich_id=&status=  → Liste
GET  /api/konten?bereich_id=  liefert je Konto zusätzlich {stand_cent|null, datenstand, letzter_import}
```

Regeln:
- Anker mit `quelle='import'` werden vom CSV-Import automatisch gesetzt, wenn die Datei eine Saldospalte hat (Bankumsatz `saldo_nachher_cent` der jüngsten Zeile) — nur ergänzen, falls P01 die Spalte erkennt; sonst weglassen und im Bericht nennen.
- Ein Anker ist ein Tagesendstand; Bewegungen desselben Tages gelten als enthalten.
- Neue Bewegungen vor dem jüngsten Anker verändern den Stand nicht, erzeugen aber einen Hinweis „Bewegung vor dem letzten Anker" in `GET /api/konten/{id}/stand` (Feld `hinweis`).
- Kassazählung nur für `art='kassa'`, sonst 422. Nachträgliche Buchungen vor einer offenen Zählung ändern `gerechnet_cent` nicht; der Stand-Endpoint meldet dann „Zählung prüfen".
- Kategorie „Kassadifferenz" wird je Sparte bei Bedarf angelegt (Richtung `beides`).
- Alle Endpoints mit Bereichsprüfung.

## 4. Nicht-Ziele

Kein PDF-Parser. Kein Frontend. Keine Änderung an Auslagen oder Buchungen außer der Differenzbuchung.

## 5. Schritte

1. Migration 006, `schema.sql`.
2. Standberechnung als Funktion `kontostand(con, konto_id, stichtag) -> dict` in `app/konten.py` (neues Modul, vom Router genutzt).
3. Endpoints Anker, Zählung, Liste.
4. Tests, Gesamtlauf, Bericht.

## 6. Tests

Neue Datei `tests/test_saldoanker.py`:
- Konto ohne Anker: `stand_cent` null, `datenstand` unbekannt.
- Anker 1.000 € am 31.08., Bewegungen +200 am 02.09. und −50 am 05.09.: Stand am 08.09. = 1.150 €; Stand am 01.09. = 1.000 €.
- Zweiter Anker am 07.09. mit 1.100 €: Antwort nennt Differenz −50 €; Stand am 08.09. = 1.100 € minus/plus Bewegungen nach dem 07.09.
- Bewegung am 15.08. nach Anker-Anlage: Stand unverändert, `hinweis` gesetzt.
- Import 40 Tage alt → `datenstand` veraltet.
- Kassazählung: gerechnet 300 €, gezählt 280 €: Differenz −20 €, Status offen; buchen mit Kategorie: Ausgabe 20 € in der Sparte, Kassa-Bewegung −20 €, Status geklärt, Stand danach 280 €.
- Zählung auf Bankkonto → 422.
- Bereich: Anker auf Konto aus Bereich 2 mit `bereich_id=1` → 404.
- Migration 006 zweimal idempotent.

## 7. Fertig heißt

- [ ] Alle Tests grün, vollständige Ausgabe im Bericht.
- [ ] Migration zweimal über den Runner; `schema.sql` und Nachzug gleich.
- [ ] Keine Geheimnisse.
- [ ] Bericht geschrieben.

## 8. Bericht zurück

Geänderte und neue Dateien mit je einem Satz. Vollständige Testausgabe. Offene Punkte mit Grund. Keine Commits, kein Push.
