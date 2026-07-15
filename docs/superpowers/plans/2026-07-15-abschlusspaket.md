# Abschlusspaket Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die vier offenen Ausbaustufen aus Konzept 13.2 plus Volltextsuche fertigstellen: Auswertungsgruppen, Drill-down-Diagramme, Regelvorschläge, PDF/XLSX-Export, Suche + Backup-Check.

**Architecture:** FastAPI-Router unter `app/routers/` (Prefix `/api`), SQLite-Zugriff über `app/db.py` (`db_dep`), statisches Frontend ohne Build in `static-studio/` (`index.html`, `app.js`, `charts.js`). Die DB-Tabellen für Gruppen und Regeln existieren bereits in `db/schema.sql`.

**Tech Stack:** Python 3, FastAPI, SQLite (sqlite3-Stdlib), openpyxl (vorhanden), Vanilla-JS mit Inline-SVG-Charts.

**Spec:** `docs/superpowers/specs/2026-07-15-abschlusspaket-design.md` — vor Beginn lesen.

## Global Constraints

- Beträge immer als Ganzzahl in **Cent** (`betrag_cent`); Anzeige `de-DE`-Format mit €.
- Deutsche UI-Texte und Fehlermeldungen; Code/Bezeichner englisch-technisch wie im Bestand.
- Keine neuen JS-Abhängigkeiten, kein Build-Schritt; Charts nur in `charts.js` erweitern.
- Kein WAL, DB-Zugriff nur über `db_dep` aus `app/db.py`.
- HTML-Ausgaben im Frontend immer über die vorhandene `esc()`-Escaping-Hilfe.
- Bestehende Endpunkte nicht umbenennen; nur additive Änderungen an Antwort-JSON.
- Kein pytest-Setup vorhanden — Verifikation über laufende App (`.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000`) mit echten HTTP-Requests und Browser-Klicktest.
- Nach jedem Task: Regressionscheck (Dashboard lädt, Buchung erfassen geht, Bankimport-Seite lädt) und ein Commit.
- Arbeitsverzeichnis: `finanz-dashboard-sparten/` (eigenes Git-Repo).

---

### Task 1: Auswertungsgruppen (Backend + UI) — Codex

**Files:**
- Create: `app/routers/gruppen.py`
- Modify: `app/main.py` (Router registrieren), `app/schemas.py` (GruppeIn), `app/routers/dashboard.py` (`globalgruppe_id`-Filter), `static-studio/index.html`, `static-studio/app.js`
- DB: Tabellen `globale_kategoriegruppe`, `kategorie_globalgruppe` existieren bereits (schema.sql:54, 73)

**Interfaces (Produces):**
- `GET /api/globalgruppen` → `[{id, name, beschreibung, kategorie_ids: [int]}]`
- `POST /api/globalgruppen` Body `{name, beschreibung?}` → 201 + Objekt
- `PUT /api/globalgruppen/{id}` Body `{name, beschreibung?, kategorie_ids: [int]}` — ersetzt Name + Zuordnungen
- `DELETE /api/globalgruppen/{id}` → 204 (löscht nur Gruppe + Zuordnungen, CASCADE)
- `GET /api/dashboard|/api/verlauf|/api/jahresvergleich` akzeptieren zusätzlich `globalgruppe_id: int | None` — filtert auf `v.kategorie_id IN (SELECT kategorie_id FROM kategorie_globalgruppe WHERE globalgruppe_id = ?)`; kombinierbar mit `sparte_id`.

**Steps:**
- [ ] `gruppen.py` mit den vier Endpunkten schreiben (Muster: `stammdaten.py`; 404 bei unbekannter ID, 400 bei leerem Namen, Namen `strip()`en). Router in `main.py` registrieren.
- [ ] `_where()` in `dashboard.py` um `globalgruppe_id` erweitern; alle drei Endpunkte durchreichen.
- [ ] API testen: Gruppe „Versicherungen gesamt" anlegen, 2 Kategorien aus verschiedenen Sparten zuordnen, `GET /api/dashboard?globalgruppe_id=1` — Summen müssen nur diese Kategorien enthalten. Ungültige ID → 404.
- [ ] UI Stammdaten-Tab: Bereich „Gruppen" — Liste, Anlegen, Umbenennen, Löschen (mit `confirm()`), Kategorien-Checkboxliste (gruppiert nach Sparte). Muster der bestehenden Kategorien-Pflege in `app.js` folgen.
- [ ] UI Dashboard: Gruppen-Dropdown neben der Sparten-Auswahl („Alle Sparten / Sparte X / Gruppe: Y"); Auswahl setzt `globalgruppe_id` statt `sparte_id`.
- [ ] Browser-Klicktest + Regressionscheck, dann Commit: `Auswertungsgruppen: Backend-CRUD, Dashboard-Filter und Stammdaten-UI`

### Task 2: Drill-down-Diagramme — Opus

**Files:**
- Modify: `static-studio/charts.js` (Klick-Callbacks), `static-studio/app.js` (Panel + Datenladen), `static-studio/index.html`, `static-studio/style.css`, `app/routers/buchungen.py` (`monat`-Filter)

**Interfaces:**
- Consumes: `GET /api/buchungen` (buchungen.py:65) hat bereits Filter `sparte_id` u. a. — prüfen und um `monat` (Format `JJJJ-MM`) und `kategorie_id` ergänzen, falls nicht vorhanden.
- Produces: `Charts.barGroup(el, {…, onBarClick(monatLabel, seriesName)})` und Klick auf Kategorie-Zeilen in `rankList` via `onRowClick(row)`; `app.js`-Funktion `zeigeDrilldown({monat?, kategorie_id?, sparte_id?, titel})` öffnet Panel mit Buchungstabelle.

**Steps:**
- [ ] `buchungen.py` `list_buchungen` um `monat: str | None` (SQL: `strftime('%Y-%m', datum) = ?`) und `kategorie_id: int | None` erweitern; per curl testen.
- [ ] `charts.js`: `barGroup` bekommt optionalen `onBarClick`; Balken erhalten `cursor:pointer` und Klick-Handler (Event-Delegation über `data-`-Attribute am `<rect>`). `rankList` analog `onRowClick`.
- [ ] `app.js`: Drilldown-Panel (Modal oder Slide-in, Muster vorhandener Modals nutzen) mit Titel, Buchungstabelle (Datum, Text, Kategorie, Sparte, Betrag, Summe unten) und Schließen-Button; „Bearbeiten"-Aktion je Zeile öffnet den bestehenden Bearbeiten-Dialog.
- [ ] Verlauf-Chart (Monatsbalken) und Kategorien-Ranking im Dashboard verdrahten; aktive Filter (Zeitraum, Sparte/Gruppe) werden in den Drilldown übernommen.
- [ ] Browser-Klicktest: Monat anklicken → nur Buchungen dieses Monats; Kategorie anklicken → nur diese Kategorie. Regressionscheck, Commit: `Drill-down: Klick auf Diagramme zeigt Einzelbuchungen`

### Task 3: Regelvorschläge beim Bankimport — Codex

**Files:**
- Modify: `app/routers/import_bank.py` (Lernen in `verbuche_umsatz`, Vorschläge in `list_bankumsaetze`, Endpunkt „alle übernehmen"), `static-studio/app.js`, `static-studio/index.html`
- Create: Regel-Endpunkte (in `import_bank.py` oder neuem `app/routers/regeln.py`)
- DB: Tabelle `regel` existiert (schema.sql:221)

**Interfaces (Produces):**
- `list_bankumsaetze` liefert je offenem Umsatz zusätzlich `vorschlag: {sparte_id, kategorie_id, typ, regel_id, regel_name} | null`
- `GET /api/regeln` → `[{id, name, aktiv, prioritaet, bedingung_text, ziel_sparte_id, ziel_kategorie_id, ziel_typ}]`
- `PATCH /api/regeln/{id}` Body `{aktiv: 0|1}`; `DELETE /api/regeln/{id}` → 204
- `POST /api/bankumsaetze/vorschlaege-uebernehmen` Body `{umsatz_ids: [int]}` → `{verbucht: n, uebersprungen: n}` (verbucht jeden Umsatz mit seinem Regelvorschlag; Fehler einzelner Umsätze überspringen und zählen)

**Kernlogik:**
- Normalisierung `_regel_text(umsatz)`: Empfängername, sonst erster aussagekräftiger Teil des Verwendungszwecks; lowercase, Mehrfach-Leerzeichen zusammenfassen, Ziffernfolgen >4 Stellen entfernen (Rechnungsnummern), max. 60 Zeichen.
- Lernen in `verbuche_umsatz`: nach erfolgreichem Verbuchen `INSERT` bzw. `UPDATE` der Regel mit gleichem `bedingung_text` (Ziel = gewählte Sparte/Kategorie/Typ, `name` = Bedingungstext).
- Matching: aktive Regeln nach `prioritaet ASC`, dann längster `bedingung_text` zuerst; Treffer wenn `bedingung_text` case-insensitiv im normalisierten Umsatztext enthalten und optionale Betrags-/Kontobedingungen passen. Erster Treffer gewinnt.
- Regeln machen **nur Vorschläge** — nie automatisch verbuchen.

**Steps:**
- [ ] Normalisierung + Matching + Lernen implementieren; Regel-Endpunkte anlegen (Router ggf. in `main.py` registrieren).
- [ ] API-Test: Umsatz manuell verbuchen → `GET /api/regeln` enthält neue Regel; zweiten CSV-Import mit gleichem Empfänger laden → `vorschlag` gefüllt; `vorschlaege-uebernehmen` verbucht.
- [ ] UI Bankimport: Vorschlag füllt Sparte/Kategorie/Typ vor, sichtbares Badge „Vorschlag: <Regelname>"; Button „Alle Vorschläge übernehmen" mit Ergebnismeldung („5 verbucht, 1 übersprungen").
- [ ] UI Stammdaten: Bereich „Regeln" — Liste, aktiv/inaktiv-Schalter, Löschen mit `confirm()`.
- [ ] Browser-Klicktest + Regressionscheck (normaler Bankimport ohne Regeln funktioniert unverändert), Commit: `Regelvorschlaege: lernen beim Zuordnen, Vorschlaege beim Bankimport`

### Task 4: PDF-/XLSX-Exportpakete — Opus

**Files:**
- Create: `app/routers/export.py`
- Modify: `app/main.py`, `static-studio/index.html`, `static-studio/app.js`, ggf. `requirements.txt`

**Interfaces (Produces):**
- `GET /api/export/xlsx?von=&bis=&sparte_id=` → XLSX-Download (`StreamingResponse`, Blätter: „Buchungen" [Datum, Sparte, Kategorie, Typ, Text, Kontakt, Betrag €], „Monatssummen" [Monat, Einnahmen, Ausgaben, Saldo], „Kategorien" [Sparte, Kategorie, Einnahmen, Ausgaben, Saldo]). Beträge als Zahl mit Format `#.##0,00 €` (openpyxl `number_format`), nicht als Text.
- `GET /export/bericht?jahr=&sparte_id=` → druckoptimierte HTML-Seite (eigene Route ohne `/api`): Deckblatt (Jahr, Einnahmen/Ausgaben/Saldo gesamt), je Sparte Abschnitt mit Monatstabelle + Kategoriensummen; `@media print`-CSS, Button „Drucken / Als PDF speichern" (`window.print()`). **Entscheidung:** Druck-HTML statt reportlab — keine neue Abhängigkeit, Browser-PDF reicht.

**Steps:**
- [ ] `export.py` mit XLSX-Endpunkt (Daten wie `dashboard.py`-Queries auf `v_einnahmen_ausgaben` + Buchungsliste); Router registrieren.
- [ ] XLSX per curl herunterladen, in Excel/LibreOffice öffnen: 3 Blätter, Beträge als Zahl, Filter `sparte_id` wirkt.
- [ ] Bericht-Route mit HTML-Template (f-String oder `templates`-frei inline, Muster: statisches HTML; alle Werte escapen) + Druck-CSS.
- [ ] UI: Im bestehenden Export-/Sicherungsbereich Zeitraum/Sparte-Auswahl + Buttons „Excel-Export" (Download) und „Jahresbericht" (öffnet neue Registerkarte).
- [ ] Browser-Test beider Wege + Regressionscheck, Commit: `Exportpakete: XLSX mit drei Blaettern und druckbarer Jahresbericht`

### Task 5: Volltextsuche + Backup-Check — wer zuerst frei ist

**Files:**
- Modify: `app/routers/buchungen.py` (Suchfilter in `list_buchungen` oder eigener Endpunkt `GET /api/buchungen/suche`), `static-studio/app.js`, `static-studio/index.html`; prüfen: `app/backup.py`

**Steps:**
- [ ] Suche: Parameter `q` — `LOWER` LIKE über Buchungstext, Notiz und Kontaktname (JOINs prüfen in `list_buchungen`), max. 200 Treffer neueste zuerst; per curl testen (Umlaute!).
- [ ] UI: Suchfeld über der Buchungsliste (Enter oder 300-ms-Debounce), nutzt bestehende Tabellen-Darstellung; leerer `q` = normale Liste.
- [ ] Backup-Check: `app/backup.py` lesen, Sicherung einmal real auslösen und Ergebnisdatei prüfen (auch Pfad auf Netzlaufwerk). Nur echte Lücken beheben, sonst kurzen Befund in `docs/` notieren.
- [ ] Regressionscheck, Commit: `Volltextsuche in Buchungen; Backup geprueft`

---

## Abschluss

- [ ] Alle fünf Bausteine gegen die Spec prüfen (Spec-Abdeckung Punkt für Punkt)
- [ ] README „Nächste Schritte" aktualisieren (erledigte Punkte streichen)
- [ ] Finaler Regressionstest der Kernflüsse im Browser
