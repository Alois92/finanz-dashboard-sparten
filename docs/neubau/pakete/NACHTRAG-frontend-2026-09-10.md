# Gemeinsamer Nachtrag für die Frontend-Pakete P31, P40, P41, P42, P50, P60 (Fable, 10. September 2026) — verbindlich

Gilt zusätzlich zur jeweiligen Karte und hat bei Widersprüchen Vorrang. Die Pakete laufen **gleichzeitig** in getrennten Worktrees auf demselben Stand von `neubau` (nach P20, P30, P61, A5/A6, N4). Damit die sechs Zweige ohne Konflikte zusammengeführt werden können, gelten harte Grenzen.

## 1. Arbeitsort, Zweig, Interpreter

| Paket | Worktree | Zweig |
|---|---|---|
| P31 Übersicht | `C:\Users\lblet\dev\wt-p31` | `pkt/p31-seite-uebersicht` |
| P40 Erfassen | `C:\Users\lblet\dev\wt-p40` | `pkt/p40-erfassen-fluss` |
| P41 Konten/Ausgleich | `C:\Users\lblet\dev\wt-p41` | `pkt/p41-konten-ausgleich` |
| P42 Bankimport | `C:\Users\lblet\dev\wt-p42` | `pkt/p42-bankimport-zuordnung` |
| P50 Buchungsliste | `C:\Users\lblet\dev\wt-p50` | `pkt/p50-buchungsliste-bearbeiten` |
| P60 Export | `C:\Users\lblet\dev\wt-p60` | `pkt/p60-export-oberflaeche` |

Tests: `C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Scripts\python.exe -m unittest discover -s tests`, vorher `FINANZ_DB` auf eine Wegwerf-Datei unter `%TEMP%`. Startet die Auth-Suite in der Sandbox nicht, das im Bericht sagen und die eigene Testdatei isoliert grün zeigen (`discover -s tests -p test_<paket>.py`). Der Kopf fährt die Gesamtsuite. Keine Commits, kein Push, keine neuen Abhängigkeiten, keine Migration.

## 2. Das Gerüst aus P30 ist die Grundlage

`static-neu/` existiert (`docs/neubau/abnahme/P30.md`, `docs/neubau/berichte/P30-runde1.md`): `app.js` (Zustand, Hash-Router, Bereich, Sparten, Gruppen, Jahre, Theme), `api.js` (`fetch`-Hülle mit `bereich_id`, `client_request_id`, 401-Umleitung, Fehlerobjekt mit `detail`), `format.js`, `ui.js` (Toast, Drilldown-Dialog, Sheet), `charts.js` (SVG-Monatsbalken, Sparkline), `pages/<seite>.js` mit `export function render(root, state)`. Vor dem Bauen alles lesen. Design und Texte kommen aus `docs/neubau/prototyp/prototyp.html`.

## 3. Konfliktregeln (wichtigste Regel dieses Nachtrags)

- **Jedes Paket schreibt nur in sein eigenes Seitenmodul** `static-neu/pages/<seite>.js` und bei Bedarf in eine **neue** Datei `static-neu/pages/<seite>.css`, die das Modul beim ersten `render` selbst per `<link>` nachlädt. Weitere neue Dateien nur unter `static-neu/pages/<seite>-*.js`.
- **Nicht anfassen:** `app.js`, `api.js`, `ui.js`, `format.js`, `charts.js`, `style.css`, `index.html`. Fehlt dort etwas Unverzichtbares, im Bericht unter „Wunsch an das Gerüst“ mit Begründung eintragen und im eigenen Modul einen lokalen Ersatz bauen. Ausnahme: `charts.js` darf **nur P31** erweitern.
- Backend: nur die in der eigenen Karte genannten Router. Neue Endpunkte, die die Karte verlangt, in den vorhandenen Router-Dateien am Ende ergänzen, nie bestehende Funktionen umsortieren. Keine Änderung an `app/rechenbasis.py`, `db/schema.sql`, `app/migrate.py`.
- Tests: eine eigene neue Datei `tests/test_<paket>.py` (z. B. `test_p31_uebersicht.py`). Bestehende Testdateien nicht ändern; ist eine Erwartung dort falsch, im Bericht nennen.
- Keine Änderung an `static-studio/`.

## 4. Echte Endpunkte und Antwort-JSON (Prozessregel 4)

Die Karten wurden vor P20 geschrieben. Verbindlich sind die **heutigen** Router. Vor dem Bauen die Router lesen und die exakte Antwort mit dem Testclient aufzeichnen; jeden verwendeten Endpunkt mit wörtlichem Antwort-JSON in den Bericht schreiben.

- Auswertung: `app/routers/dashboard.py` mit `GET /api/uebersicht`, `GET /api/jahresmatrix`, `GET /api/hinweise/aus`, `POST /api/hinweise/aus`, `GET /api/jahre`; Filtervertrag in `app/rechenbasis.py` (`Filter`: `bereich_id, sparte_id, auswertungsgruppe_id, globalgruppe_id, jahr, von, bis, kategorie_id, richtung, zahlungsart, stichtag, monat`). Beschreibung: `docs/neubau/berichte/P20-runde1.md`, `docs/neubau/abnahme/P20.md`.
- Buchungen: `app/routers/buchungen.py` mit `GET /api/buchungen` (Seiten mit `naechster_cursor`, `summen` über alle Treffer, `filter_betrag_cent` bei Kategorie- oder Gruppenfilter), `POST`, `PUT`, `DELETE`, Umbuchungen.
- Konten, Bewegungen, Anker, Kassa: `app/routers/konten.py`; Auslagen und Ausgleich: `app/routers/auslagen.py`.
- Bankimport: `app/routers/import_bank.py`; Abgleich (N4, neu): `GET /api/bankumsaetze/{id}/kandidaten`, `POST /api/bankumsaetze/{id}/zuordnen`, `POST /api/bankumsaetze/{id}/zuordnung-loesen`, `GET /api/konten/{id}/offene-abgleiche`, wörtliches JSON in `docs/neubau/berichte/N4-runde1.md` und Festlegungen in `docs/neubau/abnahme/N4.md`.
- Kategorien, Regeln, Kennzahlen: `app/routers/kennzahlen.py`, `app/routers/stammdaten.py`, `app/regeln.py`.
- Export: `app/routers/export.py` (Profile, Steuerpaket als ZIP).
- Betrieb: `GET /api/betrieb/status` (Sicherungsergebnis seit A5/A6), `GET /api/schema` (`instanz`).

Nennt die Karte einen Endpunkt, den es nicht gibt, und wäre er klein und eindeutig: im eigenen Router ergänzen, mit Test, und im Bericht als „ergänzt“ führen. Wäre er groß oder unklar: nicht bauen, im Bericht als „fehlt, Kopf entscheidet“ führen und die Seite ohne diesen Teil fertigstellen.

## 5. Verhalten, das für alle Seiten gilt

- Bereich 2 (Verein) ist nie in Gesamtzahlen; jeder API-Aufruf trägt `bereich_id` aus dem Zustand (macht `api.js`).
- Beträge kommen in Cent als Ganzzahl; Anzeige über `fmtEur` aus `format.js`.
- Fehler aus der API (`detail`) als Toast zeigen, nie stumm schlucken. 409 bei `client_request_id`-Wiederholung ist kein Fehler für den Nutzer.
- Handy (< 760 px) ist gleichwertig: Sheet statt Sidebar, Bottom-Navigation bleibt sichtbar, Eingaben mit passender Tastatur (`inputmode`).
- Zugänglichkeit wie im Prototyp: Fokusstile, `aria-*`, Dialoge mit `inert` und Fokusfalle über `ui.js`.
- Keine externen Netzaufrufe, keine Bibliotheken, keine Schriften von außen.

## 6. Bericht

`docs/neubau/berichte/<Paket>-runde1.md` und `docs/neubau/berichte/<Paket>-tests.txt`. Inhalt: Dateien je ein Satz; **jeder verwendete Endpunkt mit wörtlichem Antwort-JSON**; was im Browser geprüft wurde oder nicht geprüft werden konnte (Playwright läuft in der Sandbox meist nicht, dann so sagen); „Wunsch an das Gerüst“; offene Punkte mit Grund. Keine Rückfragen, Entscheidungen begründet treffen.
