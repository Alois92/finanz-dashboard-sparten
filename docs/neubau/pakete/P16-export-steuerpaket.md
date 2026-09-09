# P16: Export-Profile und Steuerpaket als ZIP

Meilenstein M6 (Backend kann früher gebaut werden, nach P12 und P13). Modell: `gpt-5.6-luna`, Aufwand medium. Branch `pkt/p16-export-steuerpaket` von `neubau`.

## 1. Ziel

Die Auswahl für den Steuer-Export wird je Jahr und Sparte gespeichert, getrennt vom fachlichen Feld `steuer_relevant`. Der Export liefert ein ZIP mit Excel-Liste, Belegfotos und Inhaltsliste, dessen Summen exakt zur vorher gezeigten Vorschau passen.

## 2. Kontext

Lies `docs/neubau/ARCHITEKTUR.md` Abschnitt 9, dann `app/routers/export.py` (bestehender XLSX-Export mit drei Blättern, Druckbericht), `app/routers/belege.py` (Dateiablage, `beleg.pfad`, `buchung_beleg`), `app/auswertungen.py` (P20, Filter), `app/bereiche.py`, `scripts/test_export_integration.py`, `tests/`.

## 3. Schnittstellen

Migration `db/migrations/010_export_profil.sql` (und `db/schema.sql`):

```sql
CREATE TABLE export_profil (
    id              INTEGER PRIMARY KEY,
    bereich_id      INTEGER NOT NULL REFERENCES bereich(id),
    sparte_id       INTEGER REFERENCES sparte(id),          -- NULL = alle Sparten des Bereichs
    jahr            INTEGER NOT NULL,
    name            TEXT NOT NULL DEFAULT 'Steuer',
    erstellt_am     TEXT NOT NULL DEFAULT (datetime('now')),
    aktualisiert_am TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (bereich_id, sparte_id, jahr, name)
);
CREATE TABLE export_profil_ausschluss (
    profil_id    INTEGER NOT NULL REFERENCES export_profil(id) ON DELETE CASCADE,
    kategorie_id INTEGER REFERENCES kategorie(id),
    buchung_id   INTEGER REFERENCES buchung(id),
    CHECK ((kategorie_id IS NULL) <> (buchung_id IS NULL))
);
CREATE INDEX idx_export_ausschluss_profil ON export_profil_ausschluss (profil_id);
```

Router `app/routers/export.py` erweitern:

```
GET  /api/export/profil?bereich_id=&sparte_id=&jahr=        → Profil (wird bei Bedarf leer angelegt) mit Ausschlüssen
PUT  /api/export/profil/{id}   {kategorie_ids: [...], buchung_ids: [...]}   → ersetzt Ausschlüsse
POST /api/export/profil/{id}/uebernehmen-vom-vorjahr        → kopiert Kategorie-Ausschlüsse des Vorjahresprofils (Buchungen nicht)
POST /api/export/vorschau      {profil_id, nur_suchtreffer?: bool, q?: str}
     → {revision, zeilen: [{buchung_id, datum, text, kategorie, betrag_cent, anteil_cent, belege: [ids]}], summen: {anzahl, einnahmen_cent, ausgaben_cent},
        ausgeschlossen: {kategorien: n, buchungen: n}, belege_fehlend: [{buchung_id, beleg_id, dateiname}]}
     revision = sha256 über sortierte Buchungs-IDs + Versionen + Ausschlüsse + Profil.aktualisiert_am
POST /api/export/paket         {profil_id, revision, nur_suchtreffer?: bool, q?: str, trotz_fehlender_belege?: bool}
     → application/zip; 409, wenn revision nicht mehr stimmt; 422, wenn Belege fehlen und trotz_fehlender_belege nicht gesetzt
GET  /api/export/xlsx  und  /export/bericht  bleiben, nehmen zusätzlich profil_id und verwenden dieselbe Auswahlbasis
```

ZIP-Inhalt:
- `Buchungen_<Sparte>_<Jahr>.xlsx`: bestehende Blätter, gefiltert auf die Auswahl; bei Splits nur die ausgewählten Zeilen, Spalte „Anteil".
- `Belege/<JJJJ-MM-TT>_<Betrag mit Komma>_EUR_B<buchung_id>_Beleg<beleg_id>.<ext>`: Originaldatei, einmal je Beleg, auch wenn mehrfach verknüpft.
- `INHALT.txt`: Erstellungszeit, Bereich, Sparte, Jahr, Profilname, Revision, Anzahl Buchungen, Summen, Liste der Belegdateien mit Buchungs-IDs, Liste fehlender Belege.

Regeln:
- Ausschluss einer Kategorie entfernt nur deren Zeilen; Ausschluss einer Buchung entfernt alle Zeilen.
- Suche (`q`) grenzt standardmäßig nur die Vorschau ein; `nur_suchtreffer=true` macht sie exportwirksam und wird in `INHALT.txt` vermerkt.
- „Alle Sparten" = alle Sparten des Bereichs; Bereichsprüfung überall.
- Umbuchungen, stornierte Buchungen und `neutral=1`-Zeilen sind nie enthalten.
- Temporäre Dateien nur unter dem Datenverzeichnis (`<DB-Ordner>/tmp/`), nach dem Senden gelöscht. Nur Standardbibliothek `zipfile` und vorhandenes `openpyxl`.

## 4. Nicht-Ziele

Kein Frontend. Keine PDF-Erzeugung der Belege, keine Umwandlung von Bildformaten. Kein Versand.

## 5. Schritte

1. Migration 010, `schema.sql`.
2. Profil-Endpoints.
3. Vorschau mit Revision.
4. Paket als ZIP, Dateinamen, Inhaltsliste.
5. Bestehenden XLSX-Export auf die Auswahlbasis umstellen.
6. Tests, Gesamtlauf, Bericht.

## 6. Tests

Neue Datei `tests/test_export_profil.py`:
- Profil anlegen, Kategorie und eine Buchung ausschließen: Vorschau-Summen entsprechen den verbleibenden Zeilen; Split-Buchung mit ausgeschlossener Kategorie zeigt nur den Rest-Anteil.
- Paket erzeugen: ZIP enthält Excel, Belege mit korrekten Namen (Datum, Betrag, IDs), `INHALT.txt`; Excel-Summe = Vorschau-Summe.
- Beleg-Datei fehlt: Vorschau listet sie; Paket ohne `trotz_fehlender_belege` → 422; mit → ZIP mit Vermerk.
- Buchung nach Vorschau geändert → Paket mit alter Revision → 409.
- Suche ohne `nur_suchtreffer` ändert den Paketumfang nicht; mit ändert ihn und `INHALT.txt` vermerkt es.
- Ein Beleg an zwei Buchungen liegt einmal im ZIP, beide Buchungen verweisen darauf.
- Vereins-Sparte erscheint mit `bereich_id=1` nie im Paket.
- Vorjahr übernehmen kopiert nur Kategorie-Ausschlüsse.
- Migration 010 zweimal idempotent.

## 7. Fertig heißt

- [ ] Alle Tests grün, vollständige Ausgabe im Bericht.
- [ ] ZIP einmal von Hand geöffnet und gegen die Vorschau geprüft (Schritte im Bericht).
- [ ] Migration zweimal über den Runner; `schema.sql` und Nachzug gleich.
- [ ] Keine Geheimnisse, keine neuen Abhängigkeiten.
- [ ] Bericht geschrieben.

## 8. Bericht zurück

Geänderte und neue Dateien mit je einem Satz. Vollständige Testausgabe. Offene Punkte mit Grund. Keine Commits, kein Push.
