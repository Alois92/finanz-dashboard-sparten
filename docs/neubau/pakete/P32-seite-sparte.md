# P32: Seite Sparte mit Kennzahlen-Anzeige

Meilenstein M3. Modell: `gpt-5.6-luna`, Aufwand medium. Branch `pkt/p32-seite-sparte` von `neubau` (nach P31).

## 1. Ziel

`static-neu/pages/sparte.js` zeigt eine einzelne Sparte (oder eine Auswertungsgruppe mehrerer Sparten): Kennzahlen-Zeile, eigene Kennzahlen (nur Anzeige, kein Editor), Barkassa, offene Auslagen der Sparte, Kategorien im Jahresvergleich (Matrix), größte Ausgabenkategorien, Jahresverlauf. Alle Daten aus bestehenden Endpoints, keine Demo-Daten.

## 2. Kontext

Lies zuerst `docs/neubau/pakete/P31-seite-uebersicht.md` (dieselbe Seiten-Anbindungslogik, `render(root, state)`-Signatur, Wiederverwendung von `api.js`/`format.js`/`charts.js`/`ui.js` aus P30 gilt hier genauso), dann `docs/neubau/pakete/P20-auswertungen-filtervertrag.md` (`GET /api/uebersicht`, `GET /api/jahresmatrix`, `GET /api/buchungen`), `docs/neubau/pakete/P15-kategorien-regeln-kennzahlen.md` (`GET /api/kennzahlen`), `docs/neubau/pakete/P12-auslagen-ausgleich.md` (`GET /api/auslagen`), `docs/neubau/pakete/P13-saldoanker-kassa.md` (`GET /api/konten` mit `art='kassa'`, `stand_cent`). Im Prototyp `docs/neubau/prototyp/prototyp.html`: `<section class="page" id="page-sparte">` (Zeile ~534) für Markup, im Skript `renderSparte`, `kennzahlWert`, `KENNZAHLEN`/`KENNZAHLEN_IDS` (Zeile ~1429–1500) für Aufbau — die dortige Berechnung (`kennzahlWert`, `proj`, Matrix-Schätzung `est`) wird **nicht** übernommen, sie kommt fertig gerechnet vom Server (`wert_cent`, `monatsdurchschnitt_cent` aus `/api/kennzahlen`; `werte`, `erwartung_cent` je Kategorie aus `/api/jahresmatrix`). Die eigenen Kennzahlen sind in P15 bereits mit `POST`/`PUT`/`DELETE /api/kennzahlen` als vollständige API angelegt; diese Karte zeigt sie nur an — ein Editor („+ Kennzahl anlegen") ist nicht Teil von M3 (siehe Nicht-Ziele).

## 3. Schnittstellen

Datei `static-neu/pages/sparte.js`, `export function render(root, state)`. `state.route` liefert die gewählte Sparte oder Gruppe (Router aus P30, Format dort ablesen: Hash-Route `#/sparte/<id|gruppe>`).

```
GET /api/uebersicht?bereich_id=&jahr=&sparte_id=<id>            (bei Gruppen: &auswertungsgruppe_id=<id> statt sparte_id)
 → wie in P31 für die KPI-Zeile (ist, erwartung, vorjahr_*, monate)
GET /api/jahresmatrix?bereich_id=&sparte_id=<id>&jahre=<Liste aus state, Standard: laufendes Jahr und die drei davor>
 → {jahre, stichtag, zeilen: [{kategorie_id, name, sparte_id, aktiv, richtung, werte: {"<jahr>": {einnahmen_cent, ausgaben_cent}}, erwartung_cent: {einnahmen, ausgaben}|null, monatsdurchschnitt_cent}], summen}
GET /api/kennzahlen?sparte_id=<id>&jahr=<state.filter.jahr>      (nur bei einzelner Sparte, nicht bei Gruppen — Kennzahlen sind je Sparte definiert)
 → [{id, name, terme, wert_cent, monatsdurchschnitt_cent}]
GET /api/auslagen?bereich_id=&sparte_id=<id>                     (Sparte als Ziel oder Zahler; beide Rollen anzeigen)
 → [{zahler_sparte_id, sparte_id, offen_cent, anzahl, auslagen: [...]}]
GET /api/konten?bereich_id=&sparte_id=<id>                       (client-seitig auf art === 'kassa' filtern, genau ein Treffer je Sparte)
 → [{id, name, art, sparte_id, stand_cent, datenstand, ...}]
```

Aufbau der Seite (Klassen/IDs aus dem Prototyp):

- **KPI-Zeile** (`#s-kpis`): wie in P31 beschrieben, aber mit dem Filter `sparte_id`/`auswertungsgruppe_id` aus der Route.
- **Eigene Kennzahlen** (`#s-kz`): ein `.kzc`-Eintrag je Kennzahl aus `GET /api/kennzahlen`: Name, Formel-Zeile aus `terme` zusammensetzen (`+`/`−` nach `vorzeichen`, Kategoriename aus den bereits geladenen Kategorien aus `GET /api/kategorien?sparte_id=<id>` auflösen — ein zusätzlicher Aufruf dieser Seite), Wert `wert_cent` (`fmtEur`, positiv/negativ eingefärbt), Monatsdurchschnitt `monatsdurchschnitt_cent`. Bei einer Gruppe (mehrere Sparten): Abschnitt entfällt ganz, kein leerer Kasten. Kein „+ Kennzahl anlegen"-Kasten mit Funktion — falls aus optischen Gründen ein Hinweistext „Kennzahl anlegen kommt in einem späteren Ausbauschritt" gewünscht ist, als reiner Text ohne Formular; wenn das den Rahmen sprengt, ganz weglassen.
- **Barkassa** (`#s-kassa`): bei einzelner Sparte ein Kassa-Eintrag (`stand_cent`, `datenstand`); bei Gruppe: ein Eintrag je Sparte der Gruppe.
- **Auslagen** (`#s-auslagen`): Einträge aus `GET /api/auslagen`, getrennt nach „schuldet" (Sparte ist `zahler_sparte_id`) und „wird geschuldet" (Sparte ist Ziel); Klick öffnet `drill({rows: ...})` wie in P31.
- **Kategorien im Jahresvergleich** (`#s-matrix`, `#s-years`): Tabelle aus `jahresmatrix.zeilen`, gruppiert nach `richtung` (Block „Einnahmen", Block „Ausgaben", wie `block()` im Prototyp, aber Werte und `erwartung_cent` direkt aus der Antwort, keine eigene Schätzung). Stillgelegte Kategorien (`aktiv=0`) mit Pille „stillgelegt" wie im Prototyp, bleiben in der Matrix. Jahres-Chips (`#s-years`) steuern den `jahre`-Parameter des nächsten Aufrufs (kein reines Client-Filtern wie im Prototyp, da der Server die Erwartung nur für angefragte Jahre liefert); mindestens ein Jahr muss aktiv bleiben. Zellklick öffnet `drill({kategorie_id, jahr, typ})`.
- **Wohin das Geld geht** (`#s-top-aus`): aus `GET /api/uebersicht`-Feld `top.ausgaben` (gleicher Aufruf wie für die KPI-Zeile, kein Zusatzaufruf).
- **Verlauf** (`#s-verlauf`): aus `monate` derselben Antwort, wie in P31.

Keine neuen Backend-Endpoints.

## 4. Nicht-Ziele

Kein Formular zum Anlegen, Ändern oder Löschen einer Kennzahl (API aus P15 existiert, UI dafür ist nicht Teil von M3). Keine Änderung an `app.js`/`api.js`/`ui.js`/`charts.js`/`format.js` aus P30 außer einer im Bericht benannten, notwendigen Ergänzung, falls dort etwas fehlt. Keine Änderung an `pages/uebersicht.js` aus P31 oder anderen Seiten. Kein Bearbeiten von Buchungen von dieser Seite aus (das ist `pages/erfassen.js`/`pages/buchungen.js`, nicht Teil dieser Karte).

## 5. Schritte

1. `pages/sparte.js` schreiben: Datenabrufe, Aufbau aller Abschnitte aus 3, Unterscheidung Einzelsparte/Gruppe.
2. Jahres-Chips mit erneutem Serverabruf statt Client-Filterung.
3. Drilldown-Verdrahtung.
4. Node-Syntaxprüfung, Tests.
5. Browserprüfung, Bericht.

## 6. Tests

Testinterpreter `C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Scripts\python.exe`, `FINANZ_DB` je Test über `tempfile.TemporaryDirectory()` auf eine Wegwerf-Datenbank unter `C:\Users\lblet\AppData\Local\Temp`, niemals die echte Datenbank. Fixtures mit echter Struktur (Bereiche, Sparten, Kategorien, Kennzahlen mit Termen, Buchungen über mehrere Jahre, mindestens eine stillgelegte Kategorie mit Historie, mindestens eine Auslage).

Neue Datei `tests/test_static_neu_sparte.py`:
- `GET /neu/pages/sparte.js` liefert 200 und JavaScript-Text, der auf `api.js` und die Endpoints aus 3 referenziert.
- `node --check static-neu/pages/sparte.js` (überspringen mit Meldung, wenn `node` fehlt).
- Seed mit einer Sparte und einer Kennzahl mit Termen (`plus`: eine Einnahmekategorie, `minus`: eine Ausgabekategorie): `GET /api/kennzahlen?sparte_id=&jahr=` liefert `wert_cent` gleich Einnahmen minus Ausgaben dieser Kategorien — Kontrolle, dass die Karte den richtigen Endpoint mit den richtigen Parametern erwartet, keine Neuberechnung im Frontend nötig.
- `GET /api/jahresmatrix?sparte_id=&jahre=<zwei Jahre>` enthält die stillgelegte Kategorie mit `aktiv=0` weiterhin in `zeilen`.
- Antwortform aller vier Endpoints aus 3 enthält alle Felder, die `pages/sparte.js` verwendet (Vertragstest wie in P31).

Browserprüfung (Playwright, falls möglich, sonst im Bericht begründen): Sparten-Seite lädt ohne Konsolenfehler, Kennzahlen-Zeile zeigt Werte, Matrix zeigt mehrere Jahre, Jahres-Chip abwählen lädt neu, Kassa- und Auslagen-Karten zeigen Daten, Klick in der Matrix öffnet den Drilldown.

## 7. Fertig heißt

- [ ] Alle Tests grün, vollständige Ausgabe im Bericht (oder begründet übersprungen).
- [ ] Kein Kennzahl-Editor im Code (nur Anzeige).
- [ ] Keine Geheimnisse, keine echten Namen.
- [ ] Bericht geschrieben.

## 8. Modell und Aufwand

`gpt-5.6-luna`, Aufwand medium. Anbindung mehrerer bestehender, bereits spezifizierter Endpoints an das Gerüst aus P30; die Matrix-Tabelle ist die aufwendigste Komponente, aber ohne eigene Rechenlogik. Effort **nicht** high.

## 9. Bericht zurück

Geänderte und neue Dateien mit je einem Satz. Vollständige Testausgabe. Was im Browser geprüft wurde oder nicht geprüft werden konnte, mit Grund. Offene Punkte. Keine Commits, kein Push.
