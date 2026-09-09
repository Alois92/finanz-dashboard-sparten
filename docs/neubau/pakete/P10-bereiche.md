# P10: Bereiche (Mandanten) mit zentraler Prüfung

Meilenstein M1. Modell: `gpt-6-astra`, Aufwand high. Branch `pkt/p10-bereiche` von `neubau`.

## 1. Ziel

Der Verein ist ein eigener Datenbereich in derselben Datenbank: eigene Sparten, Konten, Belege, Regeln und Gruppen, nie in Summen, Listen, Suche oder Export des Hauptbereichs. Jeder Endpoint löst den Bereich zentral auf und prüft referenzierte Kennungen dagegen.

## 2. Kontext

Lies `docs/neubau/ARCHITEKTUR.md` Abschnitt 2 und 8, dann `db/schema.sql`, `app/db.py` (`db_dep`), alle Router in `app/routers/` (welche Tabellen sie lesen und schreiben), `app/auth.py` (wie `AuthMiddleware` Requests durchlässt), `app/migrate.py`, `tests/test_auto_kategorien.py` und `tests/test_buchungen_suche.py` als Muster für API-Tests mit Wegwerf-Datenbank.

## 3. Schnittstellen

Migration `db/migrations/003_bereiche.sql` (und `db/schema.sql`):

```sql
CREATE TABLE bereich (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    kuerzel     TEXT    NOT NULL UNIQUE,
    typ         TEXT    NOT NULL CHECK (typ IN ('haupt','verein')),
    aktiv       INTEGER NOT NULL DEFAULT 1 CHECK (aktiv IN (0,1)),
    sortierung  INTEGER NOT NULL DEFAULT 0
);
INSERT INTO bereich(id, name, kuerzel, typ, sortierung) VALUES (1, 'Haupt', 'HAUPT', 'haupt', 10), (2, 'Verein', 'VEREIN', 'verein', 20);
ALTER TABLE sparte ADD COLUMN bereich_id INTEGER NOT NULL DEFAULT 1 REFERENCES bereich(id);
ALTER TABLE bankkonto ADD COLUMN bereich_id INTEGER NOT NULL DEFAULT 1 REFERENCES bereich(id);
ALTER TABLE beleg ADD COLUMN bereich_id INTEGER NOT NULL DEFAULT 1 REFERENCES bereich(id);
ALTER TABLE regel ADD COLUMN bereich_id INTEGER NOT NULL DEFAULT 1 REFERENCES bereich(id);
ALTER TABLE globale_kategoriegruppe ADD COLUMN bereich_id INTEGER NOT NULL DEFAULT 1 REFERENCES bereich(id);
ALTER TABLE auswertungsgruppe ADD COLUMN bereich_id INTEGER NOT NULL DEFAULT 1 REFERENCES bereich(id);
UPDATE sparte SET bereich_id = 2 WHERE typ = 'verein';
UPDATE bankkonto SET bereich_id = (SELECT bereich_id FROM sparte WHERE sparte.id = bankkonto.sparte_id) WHERE sparte_id IS NOT NULL;
UPDATE beleg SET bereich_id = (SELECT bereich_id FROM sparte WHERE sparte.id = beleg.sparte_id) WHERE sparte_id IS NOT NULL;
UPDATE regel SET bereich_id = (SELECT bereich_id FROM sparte WHERE sparte.id = regel.ziel_sparte_id) WHERE ziel_sparte_id IS NOT NULL;
CREATE INDEX idx_sparte_bereich ON sparte (bereich_id);
CREATE INDEX idx_bankkonto_bereich ON bankkonto (bereich_id);
CREATE INDEX idx_beleg_bereich ON beleg (bereich_id);
```

Gruppen: eine Auswertungsgruppe oder Kategoriegruppe darf nur Sparten beziehungsweise Kategorien eines Bereichs enthalten; Migration setzt `bereich_id` der Gruppe auf den Bereich ihrer ersten Sparte/Kategorie und entfernt Zuordnungen aus fremden Bereichen (Anzahl im Migrationslog).

Neues Modul `app/bereiche.py`:

```python
def bereich_dep(bereich_id: int = Query(1), con = Depends(db_dep)) -> Bereich   # 404 wenn unbekannt oder inaktiv
def pruefe_sparte(con, sparte_id, bereich) -> None      # 404, wenn Sparte nicht im Bereich
def pruefe_konto(con, konto_id, bereich) -> None
def pruefe_beleg(con, beleg_id, bereich) -> None
def pruefe_kategorie(con, kategorie_id, bereich) -> None  # über sparte
def pruefe_buchung(con, buchung_id, bereich) -> None      # über sparte
def sparten_ids(con, bereich) -> list[int]
```

`GET /api/bereiche` liefert `[{"id", "name", "kuerzel", "typ"}]` aller aktiven Bereiche.

Alle bestehenden `/api`-Endpoints nehmen `bereich_id` als Query-Parameter (Standard 1) über `bereich_dep` entgegen und filtern beziehungsweise prüfen:
- Lesen von Listen und Auswertungen (`/api/sparten`, `/api/kategorien`, `/api/buchungen`, `/api/buchungen/suche`, `/api/dashboard`, `/api/jahresvergleich`, `/api/verlauf`, `/api/bankkonten`, `/api/bankumsaetze`, `/api/belege`, `/api/beleg-auswertungen`, `/api/regeln`, `/api/globalgruppen`, `/api/auswertungsgruppen`, `/api/export/xlsx`, `/export/bericht`): nur Datensätze des Bereichs.
- Schreiben (Buchung, Umbuchung, Kategorie, Beleg, Bankkonto, Import, Regel, Gruppen, Verbuchen, Übernehmen): alle referenzierten Sparten, Konten, Belege, Kategorien, Buchungen gehören zum Bereich, sonst 404 (kein 403, um Existenz nicht preiszugeben).
- Umbuchungen und Auslagen nie über Bereichsgrenzen.
- `app/regeln.py`: `aktive_regeln(con, bereich_id)` und `finde_regel(..., bereich_id)`; Schnellerfassung, Bankimport und Fotoauswertung übergeben den Bereich. Die Foto-Auswertung in `app/auswertung.py` speichert `bereich_id` am Beleg.

Frontend (`static-studio/app.js`): nur minimal, damit die bestehende Oberfläche weiter funktioniert: `bereich_id=1` an alle API-Aufrufe anhängen (zentral in der `api()`-Hilfsfunktion). Kein Umschalter, der kommt mit dem neuen Frontend.

## 4. Nicht-Ziele

Kein zweiter Login, keine Benutzertabelle. Keine neue Oberfläche. Keine Änderung an Konten- oder Bewegungslogik (P11). Keine Datenbereinigung.

## 5. Schritte

1. Migration 003 und `schema.sql`; Migrationslog für entfernte Gruppen-Zuordnungen.
2. `app/bereiche.py` mit Dependency und Prüfungen.
3. Router für Router umstellen; je Router die Tests aus 6 ergänzen, bevor der nächste Router folgt.
4. Regeln, Schnellerfassung, Foto-Auswertung.
5. Frontend-Minimaländerung.
6. Gesamtlauf, Bericht mit Liste aller geänderten Endpoints.

## 6. Tests

Neue Datei `tests/test_bereiche.py` mit Wegwerf-Datenbank, in der der Seed zwei Bereiche hat (Sparte mit `typ='verein'` in Bereich 2):
- `GET /api/bereiche` liefert beide Bereiche.
- `GET /api/sparten?bereich_id=2` liefert nur die Vereinssparte; ohne Parameter nur Hauptsparten.
- Buchung im Bereich 1 mit Kategorie aus Bereich 2 → 404. Beleg aus Bereich 2 an Buchung aus Bereich 1 → 404. Umbuchung zwischen Bereichen → 404.
- `GET /api/dashboard` (Bereich 1) enthält keine Vereinsbuchungen; mit `bereich_id=2` nur Vereinsbuchungen.
- `GET /api/buchungen/suche?q=...` findet Vereinsbuchungen nur mit `bereich_id=2`.
- `GET /api/export/xlsx` (Bereich 1) enthält keine Vereinsbuchungen.
- Regeln: eine Regel aus Bereich 2 trifft in der Schnellerfassung des Bereichs 1 nicht.
- Migration 003 auf einer Datenbank mit Vereinssparte, Vereinskonto, gemischter Auswertungsgruppe: Zuordnungen korrekt, fremde Gruppenzuordnung entfernt; zweiter Lauf idempotent.
- Bestehende Tests bleiben grün (ohne Parameter gilt Bereich 1).

## 7. Fertig heißt

- [ ] Alle Tests grün, vollständige Ausgabe im Bericht.
- [ ] Liste aller Endpoints mit Bereichsprüfung im Bericht; kein Endpoint ohne.
- [ ] Migration zweimal über den Runner gelaufen.
- [ ] `schema.sql` und Nachzug ergeben dieselben Spalten und Indizes.
- [ ] Keine Geheimnisse, keine echten Namen.
- [ ] Bericht geschrieben.

## 8. Bericht zurück

Geänderte und neue Dateien mit je einem Satz. Liste der Endpoints mit Art der Prüfung. Vollständige Testausgabe. Offene Punkte mit Grund. Keine Commits, kein Push.
