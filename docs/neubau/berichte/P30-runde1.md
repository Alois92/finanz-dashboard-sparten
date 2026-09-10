# P30 Runde 1 – Frontend-Gerüst `static-neu`

## Ergebnis

Das neue statische Frontend ist unter `/neu/` gemountet und verwendet ausschließlich lokale Assets sowie API-Daten. Die vorhandene Studio-Oberfläche blieb unverändert.

## Geänderte Dateien

- `app/main.py` mountet `static-neu/` vor den Studio-Mounts und ergänzt `instanz` in `/api/schema`.
- `app/routers/dashboard.py` ergänzt `GET /api/jahre` mit Jahren aus `v_einnahmen_ausgaben` plus laufendem Jahr, absteigend und ohne Duplikate.
- `app/routers/stammdaten.py` liefert bei `/api/bereiche` zusätzlich `aktiv` und `sortierung`.
- `tests/test_static_neu.py` prüft Frontend-Zugriff, JavaScript-Auslieferung, Auth-Umleitung, Instanzkennung und Jahresvertrag.
- `static-neu/index.html` enthält das zugängliche Gerüst mit Sidebar, Kopfzeile, Filtern, Dialog, Sheet, Toast und mobiler Navigation.
- `static-neu/style.css` enthält lokale Schriftdefinitionen, Design-Tokens, Hell/Dunkel-Modus, Komponenten und responsive Layoutregeln.
- `static-neu/app.js` enthält Zustand, Hash-Router, Bereichs-/Sparten-/Gruppen-/Jahres-Laden, Theme, Logout, Filterumschaltung und Gruppen-Dialog.
- `static-neu/api.js` enthält die JSON-Fetch-Hülle mit `bereich_id`, Client-Request-ID, 401-Weiterleitung und Fehlerobjekten.
- `static-neu/format.js` enthält `fmtEur`, `fmtDate`, `fmtPct`, `esc` und `parseBetrag`.
- `static-neu/ui.js` enthält Toast, Drilldown-Dialog und Mobil-Sheet-Helfer.
- `static-neu/charts.js` enthält bibliotheksfreie SVG-Sparkline- und Monatsbalken-Helfer.
- `static-neu/pages/*.js` enthält die neun P30-Seitenmodule als Platzhalter.
- `static-neu/fonts/*.woff2` kopiert die vorhandenen lokalen Space-Grotesk- und JetBrains-Mono-Schriften.

## Module und Platzhalter

| Modul | Anzeige |
|---|---|
| Übersicht | „Die Übersicht wird in P31 gefüllt.“ |
| Sparte | Platzhalter für P3x |
| Erfassen | Platzhalter für P3x |
| Buchungen | Platzhalter für P3x |
| Konten | Platzhalter für P3x |
| Kategorien | Platzhalter für P3x |
| Belege | Platzhalter für P3x |
| Bankimport | Platzhalter für P3x |
| Export | Platzhalter für P3x |

## Verifikation

Der isolierte P30-Testlauf ist mit 3 Tests grün; `node --check` war für 15 JavaScript-Dateien grün. Die vollständige Testausgabe steht in [P30-tests.txt](P30-tests.txt).

Die Browserprüfung konnte nicht durchgeführt werden: Playwright war wegen `CreateFileMapping ... Win32 error 5` in der Sandbox nicht startbar, und es war kein alternativer Browser verfügbar.

## Offene Punkte

- Die Seiteninhalte bleiben wie beauftragt Platzhalter und werden in P31 ff. gefüllt.
- Die Gesamtsuite konnte wegen des beschriebenen Sandbox-Hängers nicht abgeschlossen werden; der isolierte P30-Nachweis bleibt reproduzierbar.
- Ein separates `login.html`/`login.js` wurde nicht angelegt, weil die bestehende Middleware für `/neu` auf die bestehende öffentliche `/login.html` umleitet und der Login nach `/` zurückführt; dies ist für P30 der verbindliche Nachtragspfad.
- Die Browser-Interaktionen (Sidebar-Daten, Bereichswechsel, Theme und 375px-Erfassen) sind deshalb nicht visuell abgenommen.
