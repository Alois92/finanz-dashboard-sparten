# P15: Kategorien pflegen, Regeln mit Herkunft, eigene Kennzahlen

Meilenstein M1. Modell: `gpt-5.6-luna`, Aufwand medium. Branch `pkt/p15-kategorien-regeln-kennzahlen` von `neubau` (nach P10).

## 1. Ziel

Kategorien lassen sich umbenennen und stilllegen, ohne dass Historie verloren geht. Regeln tragen ihre Herkunft (gelernt, Stichwort, manuell) als Feld, nur freigegebene Lernregeln verbuchen automatisch, und Stichwörter sind Vorschläge. Eigene Kennzahlen sind über Kategorie-IDs definiert und rechnen Einnahmen, Ausgaben und Netto getrennt.

## 2. Kontext

Lies `docs/neubau/ARCHITEKTUR.md` Abschnitt 7, dann `app/routers/stammdaten.py`, `app/regeln.py`, `app/routers/import_bank.py` (`_lerne_regel`, Vorschläge, `/api/regeln`), `app/routers/schnellerfassung.py`, `app/auswertung.py` (Regelnutzung), `app/bereiche.py`, `tests/test_regeln.py`, `tests/test_auto_kategorien.py`.

## 3. Schnittstellen

Migration `db/migrations/008_regeln_kennzahlen.sql` (und `db/schema.sql`):

```sql
ALTER TABLE regel ADD COLUMN quelle TEXT NOT NULL DEFAULT 'gelernt' CHECK (quelle IN ('gelernt','stichwort','manuell'));
ALTER TABLE regel ADD COLUMN auto_verbuchen INTEGER NOT NULL DEFAULT 0 CHECK (auto_verbuchen IN (0,1));
ALTER TABLE regel ADD COLUMN eingabe_sparte_id INTEGER REFERENCES sparte(id);
ALTER TABLE regel ADD COLUMN gelernt_aus_buchung_id INTEGER REFERENCES buchung(id);
ALTER TABLE regel ADD COLUMN erstellt_am TEXT NOT NULL DEFAULT (datetime('now'));
UPDATE regel SET auto_verbuchen = 1 WHERE quelle = 'gelernt';   -- bisherige gelernte Regeln behalten ihr heutiges Verhalten

CREATE TABLE kennzahl (
    id          INTEGER PRIMARY KEY,
    sparte_id   INTEGER NOT NULL REFERENCES sparte(id),
    name        TEXT NOT NULL,
    sortierung  INTEGER NOT NULL DEFAULT 0,
    aktiv       INTEGER NOT NULL DEFAULT 1 CHECK (aktiv IN (0,1))
);
CREATE TABLE kennzahl_term (
    id           INTEGER PRIMARY KEY,
    kennzahl_id  INTEGER NOT NULL REFERENCES kennzahl(id) ON DELETE CASCADE,
    kategorie_id INTEGER NOT NULL REFERENCES kategorie(id),
    messgroesse  TEXT NOT NULL CHECK (messgroesse IN ('einnahmen','ausgaben','netto')),
    vorzeichen   INTEGER NOT NULL CHECK (vorzeichen IN (1,-1))
);
```

Kategorien (`app/routers/stammdaten.py`):

```
PATCH /api/kategorien/{id}   {name?, aktiv?, richtung?, sortierung?} → 200 Kategorie
GET   /api/kategorien?sparte_id=&nur_aktive=false   → liefert stillgelegte mit aktiv=0 mit; Standard nur_aktive=false
```
Umbenennen ändert nur `name`; Regeln und Kennzahlen verweisen über IDs und bleiben gültig. Stilllegen verhindert die Auswahl in Schnellerfassung/Vorschlägen, ändert keine Auswertung.

Regeln (`app/routers/import_bank.py` oder neuer Router `app/routers/regeln.py`):

```
GET   /api/regeln?bereich_id=&quelle=&sparte_id=
POST  /api/regeln     {name, bedingung_text, ziel_kategorie_id, ziel_sparte_id?, ziel_typ?, quelle: 'stichwort'|'manuell', auto_verbuchen?, eingabe_sparte_id?, bankkonto_id?, bedingung_betrag_von_cent?, bedingung_betrag_bis_cent?, prioritaet?} → 201
PATCH /api/regeln/{id}   alle Felder außer id; aktiv
POST  /api/regeln/vorschau   {bedingung_text, ziel_kategorie_id, bankkonto_id?} → {treffer: [{bankumsatz_id, datum, text, betrag_cent}], anzahl}   gegen offene Bankumsätze des Bereichs
```

`app/regeln.py`:
- `finde_regel(con_oder_regeln, text, *, sparte_id=None, konto_id=None, bereich_id=1) -> dict|None` — Ergebnis enthält zusätzlich `quelle` und `auto_verbuchen`. Regeln mit `eingabe_sparte_id` gelten nur für diese Sparte; ohne `eingabe_sparte_id` für alle Sparten des Bereichs. Ist `sparte_id` gegeben (Schnellerfassung, Foto), werden nur Regeln berücksichtigt, deren Zielkategorie in dieser Sparte liegt; die Sparte wird nie durch die Regel gewechselt.
- Mehrere gleich gute Treffer mit unterschiedlichen Zielkategorien → `konflikt: True` mit Liste; Aufrufer zeigen Vorschläge, verbuchen nicht automatisch.
- Zielkategorie stillgelegt → Regel wird nicht angewendet.
- Bankimport: automatisch verbuchen nur bei `quelle='gelernt'` und `auto_verbuchen=1` ohne Konflikt; `stichwort`/`manuell` erzeugen `vorschlag`.
- Lernen (`_lerne_regel`): nur aus manuell bestätigten Buchungen (nicht aus automatisch verbuchten Umsätzen), nicht aus Splits mit mehr als einer Kategorie, mit `eingabe_sparte_id` = Sparte der Buchung und `gelernt_aus_buchung_id`; eine manuell deaktivierte Regel (`aktiv=0`) wird durch Lernen nicht reaktiviert.

Kennzahlen (neuer Router `app/routers/kennzahlen.py`):

```
GET    /api/kennzahlen?sparte_id=&jahr=   → [{id, name, terme: [...], wert_cent, monatsdurchschnitt_cent}]
POST   /api/kennzahlen      {sparte_id, name, terme: [{kategorie_id, messgroesse, vorzeichen}]} → 201
PUT    /api/kennzahlen/{id} {name?, terme?} → ersetzt Terme
DELETE /api/kennzahlen/{id} → 204
```
Berechnung in `app/kennzahlen.py`: `wert(con, kennzahl_id, jahr, filter)`: je Term `einnahmen` = Summe Einnahmen der Kategorie, `ausgaben` = Summe Ausgaben, `netto` = Einnahmen − Ausgaben; multipliziert mit Vorzeichen, aufsummiert. Jede Buchungszeile zählt nur einmal je Term. Monatsdurchschnitt = Wert / Monate mit Daten (laufendes Jahr: bis Stichtag).

## 4. Nicht-Ziele

Kein Frontend. Keine Ollama-Anbindung. Keine Löschung von Kategorien. Kein Zusammenlegen.

## 5. Schritte

1. Migration 008, `schema.sql`.
2. Kategorien-PATCH und Listenparameter.
3. Regel-Felder, `finde_regel` mit Kontext, Lernen mit Herkunft, Vorschau, Router.
4. Kennzahlen-Modul und Router.
5. Tests, Gesamtlauf, Bericht.

## 6. Tests

`tests/test_regeln.py`, `tests/test_auto_kategorien.py` erweitern und neu `tests/test_kennzahlen.py`:
- Kategorie umbenennen: Regel und Kennzahl zeigen weiterhin auf dieselbe ID, Kennzahlwert unverändert.
- Stillgelegte Kategorie: `GET /api/kategorien` mit `aktiv=0` enthalten; Schnellerfassung schlägt sie nicht vor; Dashboard-Summen unverändert.
- Stichwort-Regel trifft im Bankimport → `vorschlag`, kein automatisches Verbuchen; gelernte Regel mit `auto_verbuchen=1` verbucht.
- Regel mit `eingabe_sparte_id` Hof trifft in der Schnellerfassung der Privatsparte nicht.
- Zwei Regeln mit gleichem Text und verschiedenen Zielen → Konflikt, kein automatisches Verbuchen.
- Lernen aus Split mit zwei Kategorien erzeugt keine Regel; Lernen aus einfacher Buchung erzeugt Regel mit `quelle='gelernt'`, `gelernt_aus_buchung_id`.
- Deaktivierte Regel bleibt nach erneutem Speichern derselben Buchung deaktiviert.
- Kennzahl „Tiererlöse minus Futter" mit Terms (Einnahmen Tier +1 einnahmen, Futtermittel −1 ausgaben): Wert stimmt; gemischte Kategorie (Einnahme 100, Ausgabe 20) mit `netto` → 80.
- Migration 008 zweimal idempotent.

## 7. Fertig heißt

- [ ] Alle Tests grün, vollständige Ausgabe im Bericht.
- [ ] Migration zweimal über den Runner; `schema.sql` und Nachzug gleich.
- [ ] Keine Geheimnisse.
- [ ] Bericht geschrieben.

## 8. Bericht zurück

Geänderte und neue Dateien mit je einem Satz. Vollständige Testausgabe. Offene Punkte mit Grund. Keine Commits, kein Push.
