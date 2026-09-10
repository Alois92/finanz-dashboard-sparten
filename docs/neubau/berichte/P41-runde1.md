# P41-runde1: Konten und Kassen verwalten, offene Auslagen, Ausgleich-Dialog

Zweig `pkt/p41-konten-ausgleich`, Worktree `C:\Users\lblet\dev\wt-p41`.

## 1. Geänderte und neue Dateien

- `static-neu/pages/konten.js` (ersetzt) — die eigentliche Konten-Seite: Kontenkarte nach Art gruppiert mit Stand/Datenstand-Badge, Anker- und Kassazählungs-Dialoge, Karte „Offene Auslagen" mit Drilldown, Ausgleich-Dialog inkl. Warnung, Ausgleichs-Historie mit Rücknahme.
- `static-neu/pages/konten.css` (neu) — Layout für Konto-/Auslagen-/Ausgleichszeilen, Badges, Fehlermeldungen; wird von `konten.js` beim ersten Aufruf selbst per `<link>` nachgeladen.
- `tests/test_p41_konten.py` (neu) — prüft Auslieferung der Seite/des Stylesheets, `node --check` für alle `konten*.js`, und dass jeder vom Modul gelesene Endpunkt die tatsächlich gelesenen Felder liefert (Kontenliste inkl. `hinweis`, Anker mit/ohne Differenz, Kassazählung + Buchen, Bewegungs-Cursor, offene Abgleiche, Auslagen/Ausgleich/Rücknahme).
- `app/routers/konten.py` (ergänzt, eine Zeile) — `GET /api/konten` liefert jetzt zusätzlich `hinweis` je Konto (bisher nur `stand_cent`, `datenstand`, `letzter_import`); Begründung siehe „Wunsch an das Gerüst / Feststellungen".

## 2. Verwendete Endpunkte mit wörtlichem Antwort-JSON

Aufgezeichnet mit dem FastAPI/ASGI-Testclient (Muster `tests/test_bereiche.py`), `FINANZ_TEST_AUTH_BYPASS=1`, `FINANZ_DB` auf eine Wegwerf-Datei unter `%TEMP%`. Vollständige Rohaufzeichnung liegt zusätzlich in `docs/neubau/berichte/P41-endpunkte.json`.

### POST /api/konten (Bankkonto anlegen)
```json
{"id":1,"name":"P41-Bank","art":"bank","waehrung":"EUR","sparte_id":1,"iban":null,"bank":null,"kartenendnummer":null,"aktiv":1,"sortierung":0}
```

### POST /api/konten (Kassa ohne Sparte) — HTTP 422
```json
{"detail":"Kassa benötigt sparte_id"}
```

### POST /api/konten (Kassakonto anlegen)
```json
{"id":2,"name":"P41-Kassa","art":"kassa","waehrung":"EUR","sparte_id":1,"iban":null,"bank":null,"kartenendnummer":null,"aktiv":1,"sortierung":0}
```

### GET /api/konten (nach der Ergänzung um `hinweis`)
```json
[
  {"id":1,"name":"P41-Bank","art":"bank","waehrung":"EUR","sparte_id":1,"iban":null,"bank":null,"kartenendnummer":null,"aktiv":1,"sortierung":0,"stand_cent":null,"datenstand":"unbekannt","letzter_import":null,"hinweis":""},
  {"id":3,"name":"P41-Karte","art":"karte","waehrung":"EUR","sparte_id":1,"iban":null,"bank":null,"kartenendnummer":null,"aktiv":1,"sortierung":0,"stand_cent":null,"datenstand":"unbekannt","letzter_import":null,"hinweis":""},
  {"id":2,"name":"P41-Kassa","art":"kassa","waehrung":"EUR","sparte_id":1,"iban":null,"bank":null,"kartenendnummer":null,"aktiv":1,"sortierung":0,"stand_cent":null,"datenstand":"unbekannt","letzter_import":null,"hinweis":""}
]
```

### POST /api/konten/{id}/anker (erster Anker, keine Differenz-Felder)
```json
{"id":1,"konto_id":2,"stichtag":"2026-08-01","saldo_cent":50000,"quelle":"manuell","beleg_id":null,"notiz":null}
```

### GET /api/konten/{id}/stand (nach einer Bewegung)
```json
{"konto_id":2,"stichtag":"2026-08-20","stand_cent":60000,"saldo_cent":10000,"anker":{"stichtag":"2026-08-01","saldo_cent":50000,"quelle":"manuell"},"bewegungen_seit_anker":1,"letzter_import":null,"import_alter_tage":null,"datenstand":"aktuell","hinweis":""}
```

### POST /api/konten/{id}/anker (zweiter Anker mit Differenz — wird ungeschönt angezeigt)
```json
{"id":2,"konto_id":2,"stichtag":"2026-08-20","saldo_cent":61500,"quelle":"manuell","gerechnet_cent":60000,"differenz_cent":1500,"beleg_id":null,"notiz":null}
```

### GET /api/konten/{id}/bewegungen?limit=1
```json
{"bewegungen":[{"id":1,"konto_id":2,"datum":"2026-08-15","valuta":null,"betrag_signed_cent":10000,"waehrung":"EUR","art":"zahlung","transfer_id":null,"bankumsatz_id":null,"text":null,"gegenpartei":null,"quelle":"manuell","storniert_am":null,"erstellt_am":"2026-09-10 19:33:16"}],"naechster_cursor":null}
```
(`naechster_cursor` ist bei weiteren Bewegungen ein nicht-`null`-Cursor-Wert; im eigenen Test mit drei Bewegungen/`limit=1` mit anschließender Folgeabfrage geprüft.)

### POST /api/konten/{id}/zaehlung
```json
{"id":1,"konto_id":2,"datum":"2026-08-21","gerechnet_cent":61500,"gezaehlt_cent":60000,"differenz_cent":-1500,"status":"offen","notiz":null}
```

### POST /api/konten/{id}/zaehlung/{id}/buchen
```json
{"id":1,"buchung_id":3,"gerechnet_cent":61500,"gezaehlt_cent":60000,"differenz_cent":-1500,"status":"geklaert"}
```

### GET /api/konten/{id}/offene-abgleiche
```json
{"konto_id":1,"manuelle_anzahl":0,"manuelle_bewegungen":[],"umsaetze_anzahl":0,"offene_umsaetze":[]}
```

### GET /api/auslagen
```json
[{"zahler_sparte_id":5,"sparte_id":7,"offen_cent":5000,"anzahl":1,"auslagen":[{"id":1,"buchung_id":4,"datum":"2026-08-05","text":null,"kategorie":"P41-Kosten","betrag_cent":5000,"offen_cent":5000}]}]
```

### POST /api/ausgleiche (bar, Teilbetrag, Kassa reicht nicht — Warnung, aber gebucht)
```json
{"id":1,"transfer_id":1,"zuordnungen":[{"auslage_id":1,"betrag_cent":2000}],"warnungen":["Kassa P41-Hof hat nur 0,00 €, danach negativ"]}
```

### GET /api/ausgleiche
```json
[{"id":1,"transfer_id":1,"datum":"2026-08-06","von_sparte_id":7,"nach_sparte_id":5,"betrag_cent":2000,"zahlungsart":"bar","client_request_id":null,"aufgehoben_am":null,"notiz":null,"erstellt_am":"2026-09-10 19:33:17","zuordnungen":[{"auslage_id":1,"betrag_cent":2000}]}]
```

### DELETE /api/ausgleiche/{id} — HTTP 204, danach ist der Betrag in `/api/auslagen` wieder voll offen.

Vollständige Rohaufzeichnung mit allen Zwischenschritten: `docs/neubau/berichte/P41-endpunkte.json`.

## 3. Fachliche Entscheidungen (ohne Rückfrage getroffen)

- **`von_sparte_id`/`nach_sparte_id` im Ausgleich**: `von_sparte_id` = die Sparte, der die Auslage gehört (`gruppe.sparte_id`, „Schuldner"), `nach_sparte_id` = die zahlende Privatsparte (`gruppe.zahler_sparte_id`, „Gläubiger"). Ergibt sich zwingend aus `app/routers/auslagen.py::create_ausgleich`, das genau diese Zuordnung prüft.
- **Zahlungsart `bank`**: Quell-/Zielkonto-Auswahl zeigt nur Konten mit `art='bank'` der jeweils passenden Sparte; ist keines vorhanden, bleibt die Auswahl leer und der Server liefert den 422-Fehler, der als Feldfehler angezeigt wird (keine eigene Doppel-Validierung).
- **`client_request_id`**: wird als UUID im Body von `POST /api/ausgleiche` mitgeschickt, weil `AusgleichIn`/`wiederhole()` das Feld aus dem Body und nicht aus dem von `api.js` gesetzten Header liest.
- **Rücknahme-Bestätigung**: eigener kleiner `drill()`-Dialog mit „Abbrechen"/„Zurücknehmen" statt `confirm()`, wie in der Karte gefordert.
- **Badge-Titel**: `hinweis` war in `GET /api/konten` bisher nicht enthalten (nur in `/stand` und `/anker`). Da die Karte ausdrücklich den `hinweis`-Text als Titel-Attribut verlangt, wurde das Feld am Ende der bestehenden `list_konten`-Funktion in `app/routers/konten.py` ergänzt (eine Zeile, rein additiv, keine Umsortierung). Kein neuer Endpunkt, daher „ergänzt" statt „fehlt".
- **Depot/Wallet**: eigene Gruppe „Depot/Wallet" nur gerendert, wenn mindestens ein solches Konto existiert (Karte verlangt das ausdrücklich).
- **Kassazählung ohne Differenz**: Karte verlangt den zweiten Schritt nur bei Differenz ≠ 0; bei Differenz 0 wird direkt geschlossen und ein Toast „keine Differenz" gezeigt (kein leerer Buchungsschritt).

## 4. Tests

Interpreter: `C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Scripts\python.exe`, `FINANZ_DB` auf eine Wegwerf-Datei unter `%TEMP%` (nie die echte Datenbank).

- `node --check static-neu/pages/konten.js` und `konten.css` (kein `--check` für CSS nötig/möglich; Syntaxprüfung erfolgt implizit durch den `<link>`-Ladeversuch im Testfall).
- `python -m unittest discover -s tests -p test_p41_konten.py`: **9 Tests, alle grün** (Auslieferung, `node --check`, Kontenliste-Felder inkl. `hinweis`, 422 bei Kassa ohne Sparte, Anker mit/ohne Differenz, Kassazählung + Buchen, Bewegungs-Cursor, offene Abgleiche, Auslagen/Ausgleich/Rücknahme End-to-End).
- Gesamtsuite `python -m unittest discover -s tests`: **307 Tests, OK, 1 übersprungen** (Laufzeit ca. 6:33 Min). Die im Log sichtbaren Tracebacks (Backup-Test mit absichtlich blockiertem Zielordner, absichtlich ungültige Bilddaten in der Fotoauswertung, fehlende Auth-Datei im Recovery-Test) sind erwartete stderr-Ausgaben bereits bestehender Fehlerpfad-Tests, keine Fehlschläge — das Endergebnis ist `OK`. Vollständige Ausgabe in `docs/neubau/berichte/P41-tests.txt`.

## 5. Serverstart und Browserprüfung

- `uvicorn app.main:app --port 8141` mit `FINANZ_TEST_AUTH_BYPASS=1` und `FINANZ_DB` auf eine Wegwerf-Datei: `GET /neu/` → 200, `GET /neu/pages/konten.js` → 200, `GET /neu/pages/konten.css` → 200, `GET /api/schema` → 200. Server danach beendet.
- **Playwright/Browser-Klick-Test war in dieser Sandbox nicht möglich** (kein Playwright-MCP mit erreichbarem Zielserver in diesem Arbeitsauftrag verfügbar; nur `curl`-Prüfung der Auslieferung). Nicht geprüft im echten Browser: visuelles Layout auf Handy-Breite, Fokusfalle/`inert` im `<dialog>` (kommt aus `ui.js`/`drill()`, dort bereits umgesetzt und von P41 nur konsumiert), tatsächliches Klickverhalten der Dialoge, Konsolenausgabe im laufenden Browser. Stattdessen wurde jeder verwendete Endpunkt reproduzierbar über den ASGI-Testclient durchgespielt (Abschnitt 2) und die vom Modul gelesenen Felder in `test_p41_konten.py` gegen die echten Antworten geprüft.

## 6. Wunsch an das Gerüst

- `ui.js` hat nur `toast`, `drill`, `sheet`, `closeSheet` — keinen generischen Formular-Dialog-Helfer mit z. B. eingebautem Fehler-/Lade-Zustand. `drill()` wurde (wie im vorhandenen `showGroupDialog`-Beispiel in `app.js`) auch für Formulare zweckentfremdet; für mehrschrittige Dialoge (Kassazählung → Differenz buchen) musste der zweite Schritt manuell in denselben `#drill-content` nachgerendert werden. Ein generischer Dialog-Helfer mit Schritt-Unterstützung wäre für künftige Pakete mit ähnlichen Abläufen nützlich, wurde hier aber nicht in `ui.js` selbst ergänzt (verboten laut Nachtrag), sondern lokal in `konten.js` gelöst.
- `GET /api/konten` lieferte `hinweis` nicht mit, obwohl die Karte das für den Badge-Titel voraussetzt; um `app/konten.py`/`app/rechenbasis.py` nicht anzufassen, wurde nur die Rückgabe in `app/routers/konten.py` um das bereits berechnete Feld ergänzt (siehe Abschnitt 3).

## 7. Offene Punkte

- Echte Browserprüfung (Playwright) steht aus; Grund siehe Abschnitt 5. Als Ersatz wurden alle verwendeten Endpunkte real durchgespielt (Abschnitt 2) und die vom Modul gelesenen Felder testweise gegen die echten Antworten geprüft (`tests/test_p41_konten.py`).
- Keine Migration, keine neue Abhängigkeit, kein Commit, kein Push.
- `app/routers/konten.py` wurde nur um ein zusätzliches Antwortfeld (`hinweis`) ergänzt; keine bestehende Funktion umsortiert oder inhaltlich sonst verändert.
