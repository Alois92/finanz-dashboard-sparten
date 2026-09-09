# P31: Seite Übersicht (Startseite)

Meilenstein M3. Modell: `gpt-5.6-luna`, Aufwand medium. Branch `pkt/p31-seite-uebersicht` von `neubau` (nach P30, P20, P12, P13).

## 1. Ziel

`static-neu/pages/uebersicht.js` zeigt die echte Startseite: große Jahreserwartung, Sparten-Kacheln mit „bisher", Hinweise, Konten/Kassen, offene Auslagen, Jahresverlauf, größte Kategorien. Alle Daten kommen aus `GET /api/uebersicht`, keine Demo-Daten. Der aktive Bereich (Haupt oder Verein) bestimmt vollständig, welche Sparten und Zahlen erscheinen; ein Wechsel zeigt ausschließlich die Zahlen dieses Bereichs.

## 2. Kontext

Lies zuerst `docs/neubau/pakete/P30-frontend-geruest.md` (das Gerüst, auf dem diese Karte aufbaut: `app.js`-Router, `api.js`, `format.js`, `charts.js`, `ui.js` sind fertig und werden wiederverwendet, nicht neu geschrieben), dann `docs/neubau/pakete/P20-auswertungen-filtervertrag.md` (Schema von `GET /api/uebersicht`, Filtervertrag, Hinweise mit `hinweis_aus`), `docs/neubau/pakete/P12-auslagen-ausgleich.md` (`auslagen_offen`-Feld), `docs/neubau/pakete/P13-saldoanker-kassa.md` (`konten`-Feld mit `stand_cent`/`datenstand`), `docs/neubau/ARCHITEKTUR.md` Abschnitt 8. Im Prototyp `docs/neubau/prototyp/prototyp.html`: Abschnitt `<section class="page" id="page-uebersicht">` (Zeile ~496) für Markup/Klassen, und im Skript `renderUebersicht`, `tileHtml`, `renderTop`, `renderHints`, `renderKonten` (ab Zeile ~1330) für Aufbau und Interaktion — die Rechenlogik dort (`proj`, `sum`, `monthSeries`, `kennzahlWert` u. Ä.) wird **nicht** übernommen, sie kommt fertig gerechnet vom Server. Die Kachel „Verein / ZINA" aus dem Prototyp (Zeile 1350f., `S[4]` als vierte Sparte) entfällt ersatzlos: ZINA ist ein eigener Bereich (P10), kein Sparten-Eintrag, und taucht deshalb nie zwischen den Haupt-Sparten-Kacheln auf, auch nicht als eigene Kachel auf dieser Seite — der Wechsel läuft ausschließlich über den Bereichsumschalter aus P30. `app.js` ruft beim Bereichswechsel dieselbe `render()`-Funktion der aktiven Seite erneut auf (aus P30 zu übernehmen, nicht zu ändern); diese Karte stellt sicher, dass `pages/uebersicht.js` bei jedem Aufruf `bereich_id` aus dem Zustand an `api.js` weitergibt (das hängt `api.js` laut P30 selbst an).

## 3. Schnittstellen

Datei `static-neu/pages/uebersicht.js`, Signatur `export function render(root, state)` (wie alle Seiten aus P30):

```
Aufruf: GET /api/uebersicht?bereich_id=&jahr=&sparte_id=&auswertungsgruppe_id=&globalgruppe_id=&von=&bis=&kategorie_id=&richtung=&zahlungsart=
        (Parameter aus state.filter, wie in P30 Kopfzeile/Filterleiste gepflegt; ohne sparte_id/gruppe = alle Sparten des Bereichs)
Antwort (P20): {stichtag, jahr, ist, vorjahr_gleicher_zeitraum, vorjahr_gesamt, erwartung|null,
                monate: {einnahmen[12], ausgaben[12], vorjahr_einnahmen[12], vorjahr_ausgaben[12]},
                sparten: [{sparte_id, name, kuerzel, farbe, einnahmen_cent, ausgaben_cent, saldo_cent}],
                top: {ausgaben: [{kategorie_id, name, sparte_id, betrag_cent, anteil}], einnahmen: [...]},
                hinweise: [{schluessel, art, text, drill: {...Filterparameter}}],
                auslagen_offen: [...], konten: [...], datenstand: {letzte_buchung, letzter_import}}
```

Aufbau der Seite (Klassen/IDs aus dem Prototyp übernehmen, `id`-Präfixe beibehalten):

- **KPI-Zeile** (`.grid.g3`, `#kpis`): drei Kacheln Einnahmen/Ausgaben/Saldo. Ist das gewählte Jahr das Stichtagsjahr und `erwartung` nicht `null`: große Zahl = `erwartung.*_cent`, darunter „bisher: {ist.*_cent}" klein (`fmtEur`); Vergleich zu `vorjahr_gesamt.*_cent` in Prozent (`fmtPct`, Farbe je nach `--ein`/`--aus`). Ist `erwartung` `null` (abgeschlossenes Jahr): große Zahl = `ist.*_cent`, Vergleich zu `vorjahr_gleicher_zeitraum` entfällt, stattdessen Vergleich zu `vorjahr_gesamt`. Sparkline aus `monate.einnahmen`/`ausgaben` bzw. der Differenz je Monat, Vorjahreslinie aus `monate.vorjahr_*` (Funktion `charts.js#sparkline` aus P30 verwenden, Signatur dort ablesen und übernehmen).
- **Filterhinweis** (`#filter-note`): sichtbar, wenn `state.filter` mehr als Jahr/Bereich enthält; Text „Filter aktiv: …" mit Link „zurücksetzen" (setzt Filter im Zustand zurück, `render()` erneut).
- **Sparten-Kacheln** (`#tiles-title`, `#tiles`): eine Kachel je Eintrag in `sparten` (`tileHtml`-Markup aus dem Prototyp: Name mit `farbe` als `--dot`, Saldo groß mit „bisher"-Zusatz falls Stichtagsjahr, Einnahmen/Ausgaben-Zeile, Balken mit Anteilen aus `einnahmen_cent`/`ausgaben_cent`). Klick auf eine Kachel: `go("sparte", sparte_id)` (Router-Funktion aus P30, exakte Signatur dort nachsehen und verwenden).
- **Hinweise** (`#hints`): ein `.hint-row` je Eintrag in `hinweise`, Text ist bereits fertig formatiert vom Server (`h.text` als HTML wie im Prototyp, aber serverseitig erzeugt — mit `esc()` nur einbetten, wenn die Karte selbst Text zusammensetzt; das `text`-Feld selbst gilt als bereits sicher und wird nicht doppelt escaped). Knopf „Buchungen zeigen" ruft `drill(h.drill)` aus `ui.js` (P30) mit den vom Server mitgelieferten Filterparametern auf. Knopf „×" ruft `POST /api/hinweise/aus {schluessel: h.schluessel, bis_wert: h.wert_hash}` (Feldname für den aktuellen Wert wie vom Server im Hinweis mitgeliefert — an der tatsächlichen Antwortform aus P20 orientieren, dort nachsehen, welches Feld den Vergleichswert für `bis_wert` trägt) und lädt danach `GET /api/uebersicht` neu; **kein `localStorage`** wie im Prototyp, die Ausblendung ist serverseitig aus P20.
- **Konten und Kassen** (`#konten`): ein `.konto`-Eintrag je `konten[i]` (Name, `stand_cent` als `fmtEur`, `datenstand`-Text, „Import N Tage alt"-Pill nur bei `datenstand === "veraltet"`). Keine `Beispiel`-Pille mehr (die war nur im Prototyp-Platzhalter).
- **Offene Auslagen** (`#auslagen`): ein Eintrag je Gruppe in `auslagen_offen` (Zahler, Ziel-Sparte, `offen_cent` Summe, Anzahl); Klick öffnet `drill({rows: ...})` — falls `auslagen_offen` keine Einzelbuchungen enthält, stattdessen `go("sparte", zahler_sparte_id)`.
- **Verlauf** (`#verlauf`): `charts.js#monthlyChart` (P30) mit `monate.einnahmen`, `monate.ausgaben`; Klick auf einen Monat öffnet `drill({monat: i+1, jahr: state.filter.jahr, ...restliche Filter})`.
- **Größte Posten** (`#top`, `#topseg`): Umschalter Ausgaben/Einnahmen (lokaler Seitenzustand, kein Reload), Balken aus `top.ausgaben`/`top.einnahmen` mit `betrag_cent`, `anteil` (bereits vom Server berechnet, nicht neu berechnen); Klick auf einen Balken öffnet `drill({kategorie_id, jahr: state.filter.jahr})`.

Keine neuen Backend-Endpoints. `POST /api/hinweise/aus` existiert bereits aus P20.

## 4. Nicht-Ziele

Keine ZINA-Kachel und kein Sparten-Eintrag „Verein" auf dieser Seite (das regelt der Bereichsumschalter aus P30 vollständig). Keine Änderung an `api.js`, `ui.js`, `charts.js`, `format.js`, `app.js` aus P30 außer, falls beim Einbau eine fehlende, in P30 bereits vorgesehene Funktion fehlt — dann in einer eigenen, im Bericht benannten Ergänzung nachziehen, keine Umgestaltung. Keine Änderung an anderen `pages/*.js`. Kein Bankimport-Hinweis-Zähler mit erfundener Zahl (der „14 Bankumsätze"-Hinweis im Prototyp war Demo-Text; echte Zahl kommt, falls vorhanden, aus `hinweise`, sonst entfällt der Hinweis ersatzlos).

## 5. Schritte

1. `pages/uebersicht.js` schreiben: Datenabruf über `api.js`, Aufbau aller Abschnitte aus 3.
2. Drilldown- und Navigations-Verdrahtung (`drill()`, `go()`).
3. Hinweis-Ausblenden über `POST /api/hinweise/aus`.
4. Node-Syntaxprüfung, Testdatenbank mit zwei Bereichen (Haupt und Verein) und mehreren Sparten aufsetzen, Tests schreiben.
5. Browserprüfung, Bericht.

## 6. Tests

Testinterpreter `C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Scripts\python.exe`. Jede Testfunktion setzt `FINANZ_DB` über `tempfile.TemporaryDirectory()` auf eine Wegwerf-Datenbank unter `C:\Users\lblet\AppData\Local\Temp`; niemals die echte Datenbank; Fixtures bilden die echte Struktur ab (Bereiche, Sparten, Kategorien, Buchungen wie im echten Schema, keine vereinfachte Variante).

Neue Datei `tests/test_static_neu_uebersicht.py`:
- `GET /neu/pages/uebersicht.js` (angemeldet) liefert 200 und JavaScript-Text, der auf `api.js`/`state.filter`/`bereich_id` referenziert (Vertragstest gegen Drift, kein DOM-Test).
- `node --check static-neu/pages/uebersicht.js` (per `subprocess`, `node` optional — wenn `node` in der Sandbox fehlt, Test überspringen mit klarer Meldung, nicht rot werden lassen).
- Seed mit Bereich Haupt und Bereich Verein, je zwei Sparten und Buchungen in beiden Bereichen: `GET /api/uebersicht?bereich_id=1` enthält in `sparten` keine Vereins-Sparte; `GET /api/uebersicht?bereich_id=2` enthält ausschließlich die Vereins-Sparte. Das ist der Vertrag, den die Seite unverändert weiterreicht (Bereichslogik selbst ist P10/P20, hier nur die Zusicherung, dass die Seite ihn nicht umgeht).
- Antwortform von `GET /api/uebersicht` enthält alle Felder, die `pages/uebersicht.js` laut 3. verwendet (`sparten`, `top`, `hinweise`, `konten`, `auslagen_offen`, `monate`, `erwartung`) — Test schlägt fehl, wenn eines fehlt, statt dass die Seite es im Browser still ignoriert.

Browserprüfung (Playwright, falls in der Sandbox möglich, sonst ausdrücklich im Bericht sagen, was nicht geprüft werden konnte): Übersicht lädt ohne Konsolenfehler mit Testdaten, Sparten-Kacheln zeigen Zahlen, Bereichsumschalter in der Sidebar (P30) wechselt zu „Verein" und zeigt nur dessen Sparte, Klick auf eine Kachel öffnet die Sparten-Seite, Klick auf einen Hinweis-Balken/Top-Balken öffnet den Drilldown mit passenden Zeilen.

## 7. Fertig heißt

- [ ] Alle Tests grün, vollständige Ausgabe im Bericht (oder begründet übersprungen, z. B. `node`/Playwright fehlt).
- [ ] Bereichswechsel im Browser geprüft: Verein erscheint nie zwischen den Haupt-Kacheln.
- [ ] Keine Demo-/Platzhalterzahlen mehr im Code (kein „14 Bankumsätze", keine „Beispiel"-Pille).
- [ ] Keine Geheimnisse, keine echten Namen.
- [ ] Bericht geschrieben.

## 8. Modell und Aufwand

`gpt-5.6-luna`, Aufwand medium. Reine Anbindung einer bestehenden, bereits spezifizierten API an ein bestehendes Gerüst (P30); keine neue Rechenlogik, kein neues Datenmodell. Effort **nicht** high — das ist vom Nutzer ausdrücklich untersagt.

## 9. Bericht zurück

Geänderte und neue Dateien mit je einem Satz. Vollständige Testausgabe. Was im Browser geprüft wurde oder nicht geprüft werden konnte, mit Grund. Offene Punkte. Keine Commits, kein Push.
