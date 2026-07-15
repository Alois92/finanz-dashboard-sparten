# Design: Abschlusspaket Finanz-Dashboard (2026-07-15)

Vom Benutzer genehmigter Umfang für den Projektabschluss. Fünf Bausteine,
umgesetzt in dieser Reihenfolge. Jeder Baustein ist einzeln testbar und wird
einzeln committet.

## Kontext

- Backend: FastAPI (`app/`), Router unter `app/routers/*`, alle mit Prefix `/api`.
- DB: SQLite, Schema in `db/schema.sql`. Beträge immer in Cent.
  Die Tabellen `regel`, `auswertungsgruppe`, `auswertungsgruppe_sparte`,
  `globale_kategoriegruppe`, `kategorie_globalgruppe` existieren bereits —
  es fehlen nur Endpunkte und Oberfläche.
- Frontend: statisches HTML/JS ohne Build (`static-studio/`): `index.html`,
  `app.js`, `charts.js` (eigene Canvas/SVG-Charts, kein Framework).
- Bestehende Muster beibehalten: deutsche UI-Texte, keine externen
  JS-Abhängigkeiten, DB-Zugriff über `app/db.py`.

## Baustein 1: Auswertungsgruppen in der Oberfläche

**Ziel:** Kategorien über Sparten hinweg gruppieren (z. B. „Versicherungen
gesamt") und im Dashboard auswerten.

- Neuer Router `app/routers/gruppen.py`:
  - CRUD für `globale_kategoriegruppe` (Name, Beschreibung)
  - Zuordnung Kategorien ↔ Gruppe (`kategorie_globalgruppe`, n:m)
  - CRUD für `auswertungsgruppe` + Zuordnung Sparten
- Stammdaten-Tab im Studio erweitert: Bereich „Gruppen" — Gruppe anlegen,
  umbenennen, löschen; Kategorien per Checkboxliste zuordnen.
- Dashboard-Endpunkt (`dashboard.py`): optionaler Parameter
  `globalgruppe_id` — Summen/Verlauf gefiltert auf die Kategorien der Gruppe,
  über alle Sparten hinweg.
- Dashboard-UI: Gruppen-Auswahl neben der bestehenden Sparten-Auswahl.
- Löschen einer Gruppe löscht nur die Gruppe/Zuordnungen, nie Buchungen.

## Baustein 2: Drill-down-Diagramme

**Ziel:** Klick auf Diagrammelement zeigt die zugehörigen Einzelbuchungen.

- `charts.js`: Klick-Erkennung auf Balken (Monat) und Segmente (Kategorie);
  Callback mit `{monat, kategorie_id, sparte_id}`.
- Neuer/erweiterter Endpunkt Buchungsliste mit Filtern `monat` (JJJJ-MM),
  `kategorie_id`, `sparte_id`, `globalgruppe_id` (Baustein 1 mitbenutzen).
- UI: Klick öffnet ein Panel/Modal mit der gefilterten Buchungsliste
  (Datum, Text, Kategorie, Betrag, Summe). Von dort „Bearbeiten" wie in der
  bestehenden Buchungsliste. Schließen führt zum Dashboard zurück.
- Hover-Cursor auf klickbaren Elementen, damit erkennbar ist, dass Klick geht.

## Baustein 3: Regelvorschläge beim Bankimport

**Ziel:** Bekannte Umsätze bekommen automatisch Kategorie-/Sparten-Vorschlag.

- Tabelle `regel` verwenden (existiert). Regeln machen nur Vorschläge,
  buchen nie automatisch.
- **Lernen:** Beim manuellen Zuordnen eines Bankumsatzes (bestehender Flow in
  `import_bank.py`) wird automatisch eine Regel angelegt/aktualisiert:
  `bedingung_text` = normalisierter Empfänger/Verwendungszweck-Kern,
  Ziel = gewählte Sparte/Kategorie/Typ. Doppelte Regeln (gleicher
  Bedingungstext) werden aktualisiert statt dupliziert.
- **Anwenden:** Beim Laden offener Bankumsätze prüft das Backend alle aktiven
  Regeln (Reihenfolge: `prioritaet`, dann längster Treffer).
  Treffer = `bedingung_text` kommt (case-insensitiv) im Umsatztext vor und
  optionale Betragsgrenzen/Bankkonto passen. Antwort enthält je Umsatz
  `vorschlag: {sparte_id, kategorie_id, typ, regel_id}`.
- UI Bankimport: Vorschläge vorausgefüllt und visuell markiert („Vorschlag").
  Einzeln bestätigen wie bisher; zusätzlich Button
  „Alle Vorschläge übernehmen" (verbucht alle Umsätze mit Vorschlag).
- Stammdaten: Bereich „Regeln" — Liste aller Regeln mit Bedingungstext und
  Ziel, aktiv/inaktiv schaltbar, löschbar. Keine manuelle Regel-Neuanlage in
  v1 (Regeln entstehen durchs Zuordnen).

## Baustein 4: PDF-/XLSX-Exportpakete

**Ziel:** Druckfertiger Jahresbericht und mehrblättriger Excel-Export.

- Neuer Router `app/routers/export.py`.
- **XLSX** (`GET /api/export/xlsx?von=&bis=&sparte_id=`): Arbeitsmappe mit
  Blättern „Buchungen", „Monatssummen", „Kategorien" (je Sparte und gesamt).
  Bibliothek: `openpyxl` (neue Abhängigkeit in `requirements.txt`).
- **PDF-Jahresbericht** (`GET /api/export/pdf?jahr=&sparte_id=`):
  Deckblatt mit Jahreszahlen gesamt, dann je Sparte eine Seite mit
  Einnahmen/Ausgaben/Saldo, Monatstabelle und Kategoriensummen.
  Umsetzung als druckoptimierte HTML-Seite + `window.print()` ist erlaubt,
  falls eine PDF-Bibliothek zu schwergewichtig ist — Entscheidung beim
  Implementieren; bevorzugt echte PDF-Datei via `reportlab`, Fallback
  Druck-HTML. Beträge im Format 1.234,56 €.
- UI: Export-Bereich (bei den bestehenden Export-/Sicherungsfunktionen) mit
  Zeitraum-/Sparten-Auswahl und zwei Buttons.

## Baustein 5: Volltextsuche + Backup-Check

- **Suche:** Endpunkt `GET /api/buchungen/suche?q=` — durchsucht Text/Notiz/
  Kontakt der Buchungen (LIKE, case-insensitiv), max. 200 Treffer, neueste
  zuerst. UI: Suchfeld in der Buchungsliste, Ergebnis nutzt die bestehende
  Tabellen-Darstellung.
- **Backup-Check:** `app/backup.py` prüfen — läuft die Sicherung zuverlässig
  (auch auf Netzlaufwerk ohne WAL)? Falls Lücken: beheben, sonst nur kurz
  dokumentieren. Keine neuen Features.

## Fehlerbehandlung (alle Bausteine)

- Backend validiert IDs und Parameter, antwortet mit 400/404 + deutscher
  Fehlermeldung; Frontend zeigt Fehler wie bisher als Hinweis an.
- Exporte und Regelanwendung dürfen bei fehlerhaften Einzeldatensätzen nicht
  komplett abbrechen (überspringen + zählen).

## Tests / Verifikation

- Für jeden Baustein: API-Test über die laufende App (uvicorn) mit echten
  Requests, plus Klick-Test der UI im Browser (Playwright vorhanden).
- Bestehende Funktionen (Erfassen, Bankimport, Dashboard) nach jedem
  Baustein kurz gegenprüfen (Regression).

## Nicht im Umfang

Budgetplanung, Mehrbenutzer, Cloud-Sync, manuelle Regel-Erstellmaske,
Diagramm-Framework-Wechsel.
