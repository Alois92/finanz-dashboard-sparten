# P30: Frontend-Gerüst `static-neu`

Meilenstein M3. Modell: `gpt-5.6-luna`, Aufwand medium. Branch `pkt/p30-frontend-geruest` von `neubau` (nach P20).

## 1. Ziel

Das neue Frontend entsteht als eigenes Verzeichnis `static-neu/`, während der Entwicklung unter `/neu` erreichbar, mit dem Gerüst aus dem Prototyp: Design-Tokens, Sidebar mit Bereichsumschalter, Kopfzeile mit Sparten-Dropdown und Jahreswahl, Filterleiste, Mobil-Navigation, Drilldown-Dialog, Toast, Hell/Dunkel. Seiten sind Module und zunächst Platzhalter; die Übersicht wird in P31 gefüllt.

## 2. Kontext

Lies `docs/neubau/ARCHITEKTUR.md` Abschnitt 11, dann den bereinigten Prototyp `docs/neubau/prototyp/prototyp.html` vollständig (CSS oben, HTML, `<script>` unten): Er ist die Vorlage für Aussehen, Aufbau, Texte und Verhalten. Übernimm CSS-Tokens, Klassen und Komponenten möglichst unverändert; die Demo-Daten und die Seed-Erzeugung im Prototyp werden **nicht** übernommen, alle Daten kommen aus der API. Dann `static-studio/index.html`, `static-studio/app.js` (heutiger Login-Ablauf, `api()`-Hilfsfunktion mit Sitzungsbehandlung, 401-Umleitung), `static-studio/login.html` und `static-studio/fonts/`, `app/main.py` (Mounts), `app/auth.py` (Login-Routen).

## 3. Schnittstellen

Verzeichnis `static-neu/`:

```
index.html                 Gerüst wie im Prototyp (Sidebar, Kopf, Filter, Seiten-Container, Drilldown, Mobil-Nav, Toast); <meta viewport>; Schriften lokal
style.css                  Tokens und Komponenten aus dem Prototyp; Hell/Dunkel über data-theme; Schriften aus ./fonts/ (Space Grotesk und JetBrains Mono liegen in static-studio/fonts, kopieren; Bricolage Grotesque und IBM Plex Sans nur, wenn als woff2 lokal ablegbar, sonst Fallback auf Space Grotesk/Systemschrift)
app.js                     ES-Modul: Zustand, Router (Hash-Routen #/uebersicht, #/sparte/<id|gruppe>, #/erfassen, #/buchungen, #/konten, #/kategorien, #/belege, #/bankimport, #/export), Seitenwechsel, Bereich, Theme, Start (Handy → #/erfassen, PC → #/uebersicht)
api.js                     fetch-Hülle: hängt bereich_id an, JSON, 401 → Login-Seite, 409/422/503 → Fehlerobjekt mit detail; client_request_id-Erzeugung (crypto.randomUUID)
format.js                  fmtEur (Intl einmalig), fmtDate, fmtPct, esc, parseBetrag (aus dem Prototyp übernehmen)
charts.js                  monthlyChart, sparkline aus dem Prototyp (SVG, ohne Bibliothek)
ui.js                      toast, drill (Dialog mit Fokusfalle, inert), sheet (Mobil), hinweise-Ausblenden über API
pages/uebersicht.js ... pages/export.js   je Modul `export function render(root, state)`; in P30 Platzhalter mit Seitentitel und „kommt in P3x“
login.html, login.js       aus static-studio übernehmen, Ziel nach Login: /neu/
```

`app/main.py`: `app.mount("/neu", StaticFiles(directory=BASE / "static-neu", html=True), name="neu")` vor den Studio-Mounts; `AuthMiddleware` schützt `/neu` wie `/studio` (prüfen, wie die Middleware Pfade behandelt, und ergänzen).

Verhalten des Gerüsts:
- Sidebar: Bereiche aus `GET /api/bereiche` (Umschalter oben, Bereich im Zustand und in jedem API-Aufruf), Hauptnavigation, Sparten aus `GET /api/sparten`, Gruppen aus `GET /api/auswertungsgruppen` plus „+ Gruppe anlegen" (Dialog → `POST /api/auswertungsgruppen`), Werkzeuge einklappbar (localStorage), Fuß mit Theme, Passwort ändern (Link auf bestehende Seite), Abmelden (`POST /api/auth/logout`).
- Kopfzeile: Seitentitel, Sparten-Dropdown (gekoppelt mit Sidebar), Jahreswahl aus den in der Datenbank vorhandenen Jahren (`GET /api/uebersicht` liefert `jahre` oder eigener kleiner Endpoint `GET /api/jahre`; falls nicht vorhanden, in diesem Paket als `GET /api/jahre?bereich_id=` ergänzen: Liste der Jahre mit Buchungen plus laufendes Jahr), „Mehr Filter" mit Richtung, Zahlungsart, Kategorie; aktive Filter sichtbar.
- Zustand in der URL (Hash) und `localStorage` (Bereich, Theme, Werkzeuge, zuletzt gewählte Sparte).
- Mobil (< 760 px): Bottom-Navigation mit Plus in der Mitte, Sheet für Sparten und Werkzeuge, Bereichsumschalter im Sheet.
- `FINANZ_INSTANZ=test` (Server liefert es in `GET /api/betrieb/status` oder `GET /api/schema`; in diesem Paket `GET /api/schema` um `instanz` ergänzen): Banner „TEST-INSTANZ" oben.
- Zugänglichkeit wie im Prototyp: Fokusstile, `aria-pressed`, `aria-expanded`, Dialog mit `role="dialog"`, `inert`, Toast mit `aria-live`.

## 4. Nicht-Ziele

Keine fertigen Seiteninhalte (P31 ff.). Keine Änderung an `static-studio`. Kein Build-Schritt, keine Bibliotheken, keine externen Schriftquellen.

## 5. Schritte

1. Verzeichnis, `index.html`, `style.css`, Schriften.
2. `api.js`, `format.js`, `ui.js`, `charts.js`.
3. `app.js` mit Router, Sidebar, Kopf, Filter, Mobil, Theme, Start.
4. Mount und Auth in `app/main.py`; `GET /api/jahre`, `instanz` in `/api/schema`.
5. Seiten-Platzhalter.
6. Tests, Browserprüfung, Bericht.

## 6. Tests

- `tests/test_static_neu.py`: `GET /neu/` ohne Login → 401/Umleitung wie bei `/studio`; mit Login → 200 und `index.html`; `GET /neu/app.js` liefert JavaScript; `GET /api/jahre` liefert Jahre mit Buchungen plus laufendes Jahr; `GET /api/schema` enthält `instanz`.
- Node-Syntaxprüfung aller `static-neu/*.js` und `pages/*.js` (`node --check`).
- Browserprüfung (Playwright, falls in der Sandbox möglich, sonst ausdrücklich sagen): Seite lädt ohne Konsolenfehler, Sidebar zeigt Sparten aus der Test-DB, Bereichsumschalter wechselt, Theme wechselt, 375 px zeigt Bottom-Navigation und startet auf Erfassen.

## 7. Fertig heißt

- [ ] Tests grün, Syntaxprüfung grün, Ausgabe im Bericht.
- [ ] Keine externen Netzaufrufe im Frontend (keine Google Fonts).
- [ ] Keine Geheimnisse, keine echten Namen im Code.
- [ ] Bericht mit Liste der Module und dem, was jede Seite als Platzhalter zeigt.

## 8. Bericht zurück

Geänderte und neue Dateien mit je einem Satz. Testausgabe. Was im Browser geprüft wurde oder nicht geprüft werden konnte. Offene Punkte mit Grund. Keine Commits, kein Push.

---

## 9. Nachtrag aus der Kontrolle (Fable, 10. September 2026) — verbindlich

- **Arbeitsort:** `C:\Users\lblet\dev\wt-p30`, Zweig `pkt/p30-frontend-geruest` (steht auf `neubau` nach P20). Keine Commits, kein Push.
- **Interpreter für Tests:** `C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Scripts\python.exe -m unittest discover -s tests`. Vorher **immer** `FINANZ_DB` auf eine Wegwerf-Datei unter `%TEMP%` setzen. Wird die Auth-Suite in der Sandbox wegen Dateirechten nicht startbar, das im Bericht sagen und mindestens `tests/test_static_neu.py` isoliert grün zeigen; die Gesamtsuite fährt der Kopf.
- **Login-Umleitung:** `AuthMiddleware` leitet unangemeldete Nicht-API-Pfade auf `/login.html` (Root-Mount des Studios) um; öffentliche Pfade sind `OEFFENTLICHE_PFADE` in `app/auth.py`. Für `/neu` ist **keine** eigene Login-Seite nötig: `login.html`/`login.js` in `static-neu/` nur, wenn `static-studio/login.js` nach dem Login fest auf `/studio` zeigt — dann Kopie mit Ziel `/neu/` und Pfade `/neu/login.html`, `/neu/login.js` in `OEFFENTLICHE_PFADE` aufnehmen. Sonst weglassen und im Bericht begründen.
- **`GET /api/jahre`:** neu in `app/routers/dashboard.py`, nutzt `rechenbasis.filter_dep`/`bereich_dep`, liefert `{"jahre":[...]}` absteigend aus `v_einnahmen_ausgaben` des Bereichs plus laufendes Jahr (`stichtag_heute()`), ohne Dubletten. Test dazu in `tests/test_static_neu.py`.
- **`instanz` in `/api/schema`:** Wert aus `os.environ.get("FINANZ_INSTANZ", "prod")`, nur `"test"` löst das Banner aus.
- **Echte Antwort-JSON der Endpunkte, die das Gerüst braucht** (Stand `neubau` nach P20): `GET /api/bereiche` → Liste `{id,name,kuerzel,typ,aktiv,sortierung}`; `GET /api/sparten?bereich_id=` → Liste `{id,name,kuerzel,farbe,typ,aktiv,...}`; `GET /api/auswertungsgruppen?bereich_id=` → Liste mit `sparten_ids`. Vor dem Bauen die Router lesen und die exakten Feldnamen übernehmen, nichts raten.
- **Playwright:** Ist in der Sandbox ein Browser verfügbar, die Browserprüfung aus Abschnitt 6 fahren; sonst ausdrücklich „nicht geprüft“ schreiben. Der Kopf prüft im Browser nach.
- **Sauberkeit:** keine `.tmp-tests`, keine Testdatenbanken im Repo lassen. Neue Dateien mit `git status` prüfen; die `.gitignore` schließt `*.csv` aus.
- **Bericht:** `docs/neubau/berichte/P30-runde1.md`, Testausgabe vollständig als `docs/neubau/berichte/P30-tests.txt`.
