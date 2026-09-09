# P11: Konten aller Arten, Bewegungen und Transfers

Meilenstein M1. Modell: `gpt-6-astra`, Aufwand high. Branch `pkt/p11-konten-bewegungen` von `neubau` (nach P10).

## 1. Ziel

Geldbewegungen werden getrennt von Kostenbuchungen gespeichert: jedes Konto (Bank, Karte, Kassa, später Depot und Wallet) hat Bewegungen, Transfers verbinden zwei Konten, und Buchungen sind mit den Bewegungen verknüpft, die sie bezahlt haben. Bestehende Daten werden nachgezogen, ohne etwas zu erfinden.

## 2. Kontext

Lies `docs/neubau/ARCHITEKTUR.md` Abschnitt 3, 4 und 13, dann `db/schema.sql`, `app/routers/buchungen.py` (Buchung anlegen, Umbuchungen mit `transfer_gruppe_id`, PUT, DELETE), `app/routers/import_bank.py` (Bankumsatz verbuchen), `app/routers/stammdaten.py`, `app/bereiche.py` (P10), `tests/test_umbuchungen.py`, `tests/test_import_bank.py`.

## 3. Schnittstellen

Migration `db/migrations/004_konten_bewegungen.sql` (und `db/schema.sql`):

```sql
ALTER TABLE bankkonto ADD COLUMN art TEXT NOT NULL DEFAULT 'bank' CHECK (art IN ('bank','karte','kassa','depot','wallet'));
ALTER TABLE bankkonto ADD COLUMN waehrung TEXT NOT NULL DEFAULT 'EUR';
ALTER TABLE bankkonto ADD COLUMN kartenendnummer TEXT;
ALTER TABLE bankkonto ADD COLUMN sortierung INTEGER NOT NULL DEFAULT 0;

CREATE TABLE transfer (
    id            INTEGER PRIMARY KEY,
    art           TEXT NOT NULL CHECK (art IN ('bankomat','umbuchung','ausgleich','kartenabrechnung','sonstig')),
    von_konto_id  INTEGER REFERENCES bankkonto(id),
    nach_konto_id INTEGER REFERENCES bankkonto(id),
    datum         TEXT NOT NULL,
    betrag_cent   INTEGER NOT NULL CHECK (betrag_cent > 0),
    notiz         TEXT,
    storniert_am  TEXT,
    erstellt_am   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE bewegung (
    id                 INTEGER PRIMARY KEY,
    konto_id           INTEGER NOT NULL REFERENCES bankkonto(id),
    datum              TEXT NOT NULL,
    valuta             TEXT,
    betrag_signed_cent INTEGER NOT NULL,
    waehrung           TEXT NOT NULL DEFAULT 'EUR',
    art                TEXT NOT NULL DEFAULT 'zahlung' CHECK (art IN ('zahlung','transfer','gebuehr','zins','trade')),
    transfer_id        INTEGER REFERENCES transfer(id),
    bankumsatz_id      INTEGER UNIQUE REFERENCES bankumsatz(id),
    text               TEXT,
    gegenpartei        TEXT,
    quelle             TEXT NOT NULL CHECK (quelle IN ('manuell','import','ausgleich','kredit','nachzug')),
    storniert_am       TEXT,
    erstellt_am        TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE buchung_bewegung (
    buchung_id          INTEGER NOT NULL REFERENCES buchung(id) ON DELETE CASCADE,
    bewegung_id         INTEGER NOT NULL REFERENCES bewegung(id) ON DELETE CASCADE,
    anteil_signed_cent  INTEGER NOT NULL,
    PRIMARY KEY (buchung_id, bewegung_id)
);
CREATE INDEX idx_bewegung_konto_datum ON bewegung (konto_id, datum);
CREATE INDEX idx_bewegung_transfer ON bewegung (transfer_id);
CREATE INDEX idx_buchung_bewegung_bewegung ON buchung_bewegung (bewegung_id);
```

Nachzug der Bestandsdaten in derselben Migration (als `004_konten_bewegungen.py` mit `up(con)`, das zuerst das SQL ausführt und dann die Daten überträgt):
1. Je aktiver Sparte ein Konto `art='kassa'`, `name='Kassa <Sparte>'`, `sparte_id`, `bereich_id` der Sparte, wenn noch keines existiert.
2. Je `bankumsatz` eine Bewegung `quelle='import'`, `bankumsatz_id`, Betrag und Datum aus dem Umsatz.
3. Je Buchung mit `bankumsatz_id`: Verknüpfung `buchung_bewegung` mit Anteil = signierter Buchungsbetrag (Ausgabe negativ, Einnahme positiv).
4. Je Buchung mit `zahlungsart='bar'` und Typ Einnahme oder Ausgabe: Bewegung `quelle='nachzug'` auf der Kassa der Sparte plus Verknüpfung.
5. Je Umbuchungspaar (`transfer_gruppe_id`): ein `transfer` mit `art='umbuchung'`, Konten nur, wenn eindeutig aus `bankkonto_id` der beiden Buchungen ableitbar, sonst NULL und Notiz „Konten ungeklärt"; zwei Bewegungen nur, wenn Konten bekannt.
6. Buchungen mit `zahlungsart` bank oder karte ohne `bankumsatz_id`: keine Bewegung, sie erscheinen als „Zahlung unbekannt" (Liste am Ende der Migration im Log mit Anzahl).

Neuer Router `app/routers/konten.py` (Präfix `/api`):

```
GET    /api/konten?bereich_id=            → [{id, name, art, waehrung, sparte_id, iban, bank, kartenendnummer, aktiv, sortierung}]
POST   /api/konten                        {name, art, waehrung?, sparte_id?, iban?, bank?, kartenendnummer?}  → 201
PATCH  /api/konten/{id}                   Teilfelder wie POST plus aktiv, sortierung
GET    /api/konten/{id}/bewegungen?von=&bis=&limit=100&cursor=   → {bewegungen: [...], naechster_cursor}
POST   /api/bewegungen                    {konto_id, datum, betrag_signed_cent, text?, gegenpartei?, art?}  quelle='manuell' → 201
POST   /api/transfers                     {art, von_konto_id, nach_konto_id, datum, betrag_cent, notiz?} → erzeugt Transfer + zwei Bewegungen, 201
DELETE /api/transfers/{id}                setzt storniert_am am Transfer und beiden Bewegungen
```

Regeln:
- `POST /api/buchungen` erzeugt bei `zahlungsart='bar'` automatisch eine Bewegung auf der Kassa der Sparte (Zahler-Sparte, sobald P12 Auslagen liefert) und die Verknüpfung; bei `bankkonto_id` mit `bankumsatz_id` die Verknüpfung zur importierten Bewegung; bei bank/karte ohne Umsatz eine vorläufige Bewegung `quelle='manuell'` auf `bankkonto_id`, wenn gesetzt.
- `PUT /api/buchungen/{id}` passt Anteil und Kassa-Bewegung an; `DELETE` storniert die vorläufigen Bewegungen (importierte bleiben).
- `POST /api/umbuchungen` bleibt aus Kompatibilität, erzeugt intern einen Transfer `art='umbuchung'` mit den Konten der Sparten (Kassa bei bar) und verweist mit `transfer_gruppe_id` weiter auf die beiden Buchungen.
- `/api/bankkonten` bleibt als Alias von `/api/konten` (gleiche Antwort).
- Kontostand vorläufig: `GET /api/konten/{id}/stand` = Summe aller nicht stornierten Bewegungen (Anker kommen in P13).
- Alle Endpoints mit Bereichsprüfung aus P10.

## 4. Nicht-Ziele

Keine Saldoanker, keine Kassazählung (P13). Keine Auslagen (P12). Kein Frontend. Keine Umdeutung alter Kategorien.

## 5. Schritte

1. Migration 004 als Python-Migration mit Datenübertragung und Log.
2. Router `konten.py`, Registrierung in `app/main.py`.
3. Buchungs-Router: Bewegungen bei anlegen, ändern, löschen; Umbuchung als Transfer.
4. Tests, Gesamtlauf, Bericht.

## 6. Tests

Neue Datei `tests/test_konten_bewegungen.py`:
- Migration 004 auf einer Datenbank mit: zwei Sparten, einem Bankkonto, drei Bankumsätzen, zwei verbuchten Umsätzen, zwei Barbuchungen, einem Umbuchungspaar mit bekannten Konten, einem Paar ohne Konten → Kassen je Sparte vorhanden, Bewegungen je Umsatz, Verknüpfungen korrekt, Transfer mit Konten und Transfer ohne Konten mit Notiz; Summe je Konto stimmt; zweiter Lauf idempotent.
- `POST /api/buchungen` bar → Kassa-Bewegung mit negativem Betrag bei Ausgabe, positiv bei Einnahme; Kontostand der Kassa ändert sich entsprechend.
- Umbuchung Bank → Kassa derselben Sparte (Bankomat) ist erlaubt und erzeugt zwei Bewegungen mit entgegengesetztem Vorzeichen.
- Transfer stornieren: Kontostände wieder wie vorher, Bewegungen bleiben sichtbar mit `storniert_am`.
- Kontostand rechnet ausschließlich aus Bewegungen; eine Buchung ohne Bewegung ändert keinen Kontostand.
- `POST /api/konten` mit `art='kassa'` ohne `sparte_id` → 422.
- Bereichsprüfung: Konto aus Bereich 2 in Buchung aus Bereich 1 → 404.
- Bestehende Tests grün.

## 7. Fertig heißt

- [ ] Alle Tests grün, vollständige Ausgabe im Bericht.
- [ ] Migration zweimal über den Runner; Migrationslog nennt Anzahl Kassen, Bewegungen, Transfers, ungeklärte Fälle.
- [ ] `schema.sql` und Nachzug ergeben dieselben Tabellen, Spalten, Indizes.
- [ ] Keine Geheimnisse, keine echten Namen.
- [ ] Bericht geschrieben.

## 8. Bericht zurück

Geänderte und neue Dateien mit je einem Satz. Vollständige Testausgabe. Migrationslog eines Testlaufs. Offene Punkte mit Grund. Keine Commits, kein Push.
