# P73: Mobil-Navigation und Handy-Fixes

Branch `pkt/p73-mobil-navigation` von `neubau` (Stand `7f31162`, enthält bereits P72/Betriebsseite). Auftrag auf Basis von `docs/neubau/berichte/QA-5-handy-375px.md` (Befunde QA5-01…04) und dem Gerüst aus `docs/neubau/abnahme/P30b.md`.

## Ziel

Handy-Bedienbarkeit von `static-neu/` bei 320–390 px herstellen, ohne Backend-Änderung:

1. **QA5-02 (hoch)**: Sidebar ist unter 760 px `display:none`, damit waren Sparte/Konten/Kredit/Kategorien/Export/Betrieb sowie Bereichswechsel, Theme, Passwort und Abmelden auf Mobil unerreichbar. Sechster Bottom-Nav-Eintrag „Mehr“ öffnet ein Sheet mit den fehlenden Routen (aus der `routes`-Map abgeleitet, nicht hart kodiert), Bereichswahl, Theme, Passwort-Link, Abmelden.
2. **QA5-01 (hoch)**: „Erfassen“-Seite überschritt den Viewport um 112 px bei 375 px (CSS-Grid ohne `min-width:0`).
3. **QA5-03 (mittel)**: Tap-Ziele der Listenaktionen (bearbeiten/stornieren, umbenennen/stilllegen) unter 40 px Höhe.
4. **QA5-04 (niedrig)**: horizontal scrollbare Tabellen ohne sichtbaren Hinweis.

## Umsetzung

**Frontend (`static-neu/`)**
- `index.html`: sechster Bottom-Nav-Knopf `<button data-route="mehr" aria-haspopup="dialog">≡<span>Mehr</span></button>`.
- `app.js`: `openMoreSheet()` (neu) baut das Sheet-Markup aus `Object.entries(routes)` abzüglich der im DOM vorhandenen `.mobile-nav [data-route]`-Einträge, ergänzt um Bereichs-Select, Theme-Umschalter, Passwort-Link, Abmelden-Knopf; Klick auf einen Eintrag schließt das Sheet und ruft `go()`; Fokus geht beim Öffnen auf den Sheet-Container (`node.tabIndex=-1;node.focus()`); Escape schließt über den bereits bestehenden globalen `keydown`-Handler (`closeSheet()`, unverändert aus dem P30b-Gerüst). `render()` unterscheidet jetzt bei den Bottom-Nav-Klicks zwischen echten Routen (`go()`) und dem Mehr-Knopf (`openMoreSheet()`).
- `style.css`:
  - `.mobile-nav button{min-height:44px;min-width:48px;flex:1 1 0}` (Tap-Fläche für sechs Einträge bei 320–390 px gesichert, gemessen 53–65 px Breite); `.mobile-nav span{font-size:9.5px}` (Beschriftung minimal verkleinert).
  - `dialog{max-width:calc(100vw - 16px);max-height:calc(100vh - 32px);overflow-y:auto}` im 760-px-Media-Query — betrifft `#drill` und den `wizard()`-Dialog gleichermaßen.
  - `.lnk,#k-table .act button{min-height:40px;padding:10px 6px !important;margin:0 2px}` (Buchungen bearbeiten/stornieren, Kategorien umbenennen/stilllegen; `!important` auf `padding`, weil `buchungen.css`/`kategorien.css` dieselbe Deklaration mit `padding:0` bei gleicher Spezifität *nach* `style.css` laden und sonst gewinnen würden). `.btn{min-height:40px}` als analoge Absicherung für Konten/Kredit/Belege, die reine `.btn`-Aktionen statt `.lnk` verwenden.
  - `.tscroll,.table-wrap{position:relative}` + `::after`-Verlaufsschatten am rechten Rand (reines CSS, kein JS).
  - `.grid.g2-1{grid-template-columns:1fr !important}`: zweite, vom QA5-01-Bericht nicht benannte Ursache — `erfassen.js` setzt die Zweispaltigkeit dieses Grids per Inline-`style`, das jede Stylesheet-Regel ohne `!important` schlägt; ohne diese Zeile blieb die Erfassen-Karte nach der `min-width:0`-Korrektur zwar überlauffrei, aber auf eine ~156 px schmale Spalte gequetscht statt nutzbar zu stapeln.
  - `.sheet{max-height:80vh;overflow-y:auto}`, `.sheet-head` (Kopfzeile mit Titel/Schließen-Knopf) neu, außerhalb des Media-Query (Sheet ist ohnehin nur über den nur-mobil sichtbaren Bottom-Nav-Knopf erreichbar).
- `pages/erfassen.css`: `.erfassen-page .quick-card form>*{min-width:0}` und `.erfassen-page .field input,.erfassen-page .field select{width:100%}` (QA5-01-Empfehlung).

**Tests**
- `tests/test_p73_mobil.py` (10 Tests, kein Browser nötig): `node --check app.js`; sechster Bottom-Nav-Eintrag mit `data-route="mehr"`; `mehr` ist keine echte Route in `routes`, `openMoreSheet` leitet Restrouten aus der Map ab; im 760-px-Media-Query: `.mobile-nav button` min-height/min-width, `dialog` max-width mit `100vw`, `.lnk`/`#k-table .act button` min-height, `.tscroll::after`-Verlaufsschatten vorhanden, Breakpoint unverändert bei 760 px; `erfassen.css` enthält die `min-width:0`-Korrektur; `.grid.g2-1` im Media-Query mit `!important`.

Siehe `docs/neubau/berichte/P73-runde1.md` für Ergebnis, Messwerte und offene Punkte.
