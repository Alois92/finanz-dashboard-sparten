# QA-5 — Handy-Ansicht 375×812 px

Instanz: `http://127.0.0.1:8051/` (Wegwerf-Kopie, Schema 17, 25 Buchungen 2026, Login-Bypass). Serverlog `C:\Users\lblet\AppData\Local\Temp\qa-8051.log` geprüft — während der gesamten Sitzung ausschließlich `200 OK` bzw. harmlose `404` auf `/favicon.ico`, keine `4xx/5xx` auf `/api/*`.

## 1. Messmethode und Zuverlässigkeit der Emulation

**Werkzeugwechsel während der Sitzung:** Der Auftrag sah ausschließlich Playwright-MCP-Werkzeuge vor. `mcp__playwright__browser_navigate` lieferte jedoch bei jedem Versuch (4×) den Fehler `Browser is already in use for …mcp-chrome-4b3d451, use --isolated to run multiple instances of the same browser` — das Profil war durch mehrere bereits laufende, verwaiste `chrome.exe`-Prozesse (gestartet 13:04 Uhr, vermutlich Rest einer vorherigen Sitzung) dauerhaft blockiert. Die Koordination hat daraufhin ausdrücklich angewiesen, ersatzweise auf `mcp__Claude_Browser__*` auszuweichen und jede Messung per `javascript_tool` zu verifizieren. Der gesamte Bericht basiert entsprechend auf `Claude_Browser`, nicht auf Playwright.

**Zentraler Befund zur Emulation:** `resize_window(width:375, height:812)` setzt **nicht** zuverlässig `window.innerWidth` — dieser Wert bleibt instabil und ist auf dieser Instanz irreführend (siehe unten). Zuverlässig und reproduzierbar ist dagegen `document.documentElement.clientWidth`:

| Angefragte Breite | `clientWidth` | `outerWidth`/`screen.width` |
|---|---|---|
| 375×812 | **375** (exakt) | korrekt |
| 320×568 | **320** (exakt) | korrekt |
| 300×600 | **300** (exakt) | korrekt |
| 200×400 | **200** (exakt) | korrekt |

`document.documentElement.clientWidth`/`clientHeight` (bzw. `document.body.clientWidth`) trafen bei **jeder** getesteten Breite exakt den angeforderten Wert — die Emulation selbst ist also stabil und korrekt; sie muss nur an der richtigen Stelle gemessen werden. `window.innerWidth` dagegen lieferte auf Seiten **ohne** horizontalen Inhalts-Overflow ebenfalls den korrekten Wert (z. B. 375 auf der Übersicht), sprang aber auf Seiten **mit** echtem CSS-Overflow (siehe QA5-01) exakt auf den Wert von `scrollWidth` hoch (z. B. 487 statt 375 auf „Erfassen") — `window.innerWidth` ist in diesem Werkzeug also kein verlässliches Viewport-Maß, sobald eine Seite bereits überbreiten Inhalt hat. Alle Messungen in diesem Bericht verwenden deshalb `document.documentElement.clientWidth/clientHeight` als Sollgröße und `document.documentElement.scrollWidth` zum Overflow-Nachweis, plus `getBoundingClientRect()` einzelner Elemente zur Ursachenklärung. `matchMedia('(max-width:760px)')` (Breakpoint aller `pages/*.css`) war bei 375 px durchgehend `true`.

**Zusätzliche Werkzeug-Einschränkung (Klicks per Koordinate):** Klicks über `computer.left_click` mit `ref` aus `find`/`read_page` landeten wiederholt auf dem falschen Element (z. B. „stornieren" öffnete den „bearbeiten"-Dialog). Ursache vermutlich dieselbe Koordinaten-/Skalierungs-Inkonsistenz wie bei `innerWidth`. Nach diesem Befund wurden alle weiteren Interaktionen per `javascript_tool` (`element.click()` auf gezielt selektierte Elemente) ausgelöst — das war zuverlässig und reproduzierbar.

**Screenshots:** `computer.screenshot` lieferte brauchbare Bilder, zeigte aber bei einem geöffneten Dialog auf der „Erfassen"-Seite den Dialog sichtbar rechts abgeschnitten, obwohl `getBoundingClientRect()`/`clientWidth` für denselben Dialog keinen Overflow gegenüber dem 375-px-Viewport auswiesen (dialogeigenes Zentrieren nutzt offenbar denselben verzerrten Wert wie `innerWidth`, siehe QA5-01-Zusatz). Screenshots wurden deshalb nur ergänzend zur Illustration verwendet, nicht als Overflow-Nachweis; maßgeblich sind die JS-Messungen. Ein Screenshot-Timeout trat einmal auf (Erstattungsformular) — gemäß Anweisung wurde ohne Screenshot weitergemacht.

**Screenshot-Dateien:** `mcp__Claude_Browser__computer` (Screenshot-Aktion) liefert Bilder nur inline in die Konversation zurück, nicht als Datei mit wählbarem Pfad — anders als das eigentlich vorgesehene `mcp__playwright__browser_take_screenshot` (mit `filename`), das wegen der Profil-Blockade nicht nutzbar war. Es konnten deshalb **keine Screenshot-Dateien** unter `C:\Users\lblet\AppData\Local\Temp\qa-8051\screens\` abgelegt werden (Ordner wurde angelegt, blieb aber leer). Alle Bildbefunde in diesem Bericht wurden live im Werkzeug gesichtet, sind aber nicht als Datei referenzierbar. Das ist eine reine Werkzeug-Einschränkung dieser Sitzung, kein App-Befund.

## 2. Ergebnis je Seite/Dialog (375×812, `clientWidth`-Messung)

| Seite/Dialog | Erreichbar auf Mobil? | Overflow (`scrollWidth` > `clientWidth`) | Befund |
|---|---|---|---|
| Übersicht (`#/uebersicht`) | Ja (Bottom-Nav „Start") | Nein (375=375) | OK |
| Sparte (`#/sparte/1`) | **Nein** über UI, nur Deep-Link | Nein | siehe QA5-02 |
| Erfassen (`#/erfassen`) | Ja (Bottom-Nav „＋") | **Ja — 112 px** (375→487) | **QA5-01** |
| Buchungen (`#/buchungen`) | Ja (Bottom-Nav „≣") | Nein — Tabelle korrekt in eigenem `.tscroll`-Container (overflow-x:auto) gekapselt | OK, aber QA5-03 (Tap-Ziele) |
| Konten (`#/konten`) | **Nein** über UI, nur Deep-Link | Nein | siehe QA5-02 |
| Kredit (`#/kredit`) | **Nein** über UI, nur Deep-Link | Nein | siehe QA5-02; Testdaten ohne Kredit, „Jahr bestätigen" nicht erreichbar |
| Kategorien (`#/kategorien`) | **Nein** über UI, nur Deep-Link | Nein — Tabelle/Reiter korrekt gekapselt (`.tscroll`, `.kattabs`, beide overflow-x:auto) | OK, aber QA5-03 |
| Belege (`#/belege`) | Ja (Bottom-Nav „▣") | Nein | OK; „Beleg prüfen"-Dialog in Testdaten nicht erreichbar (keine offenen Prüfungen) |
| Bankimport (`#/bankimport`) | Ja (Bottom-Nav „⇄") | Nein (Tabelle ebenfalls in Scroll-Container, `.card-head` bricht korrekt um) | OK; „Zuordnen"-Dialog in Testdaten nicht erreichbar (kein Bankkonto angelegt) |
| Export (`#/export`) | **Nein** über UI, nur Deep-Link | Nein | siehe QA5-02 |
| Dialog „Buchung bearbeiten" | über Buchungen erreichbar | Nein, 341×778 px, sauber im Viewport, `overflow-y:auto` | OK |
| Dialog „Buchung stornieren" | über Buchungen erreichbar | Nein, kompakt, mittig | OK |
| Dialog „Erstattung erfassen" (Teil von „bearbeiten") | über Buchungen erreichbar | Nein laut `clientWidth`-Messung | OK (Screenshot-Timeout, siehe oben) |
| Dialog „Neue Kategorie" | über Erfassen (`+ Neue`-Button neben Kategorie) erreichbar | Dialog selbst nicht durch Dokument-Overflow erfasst, aber `getBoundingClientRect()` zeigt `right: 412` bei Viewport 375 → **sichtbar rechts abgeschnitten** | **QA5-01 (Zusatzsymptom)** |
| Dialog „Zuordnen" (Bankimport) | nicht erreichbar | — | Testdaten: kein Bankkonto angelegt, nicht geprüft |
| Dialog „Beleg prüfen" | nicht erreichbar | — | Testdaten: keine Belege zur Prüfung, nicht geprüft |
| Dialog „Jahr bestätigen" (Kredit) | nicht erreichbar | — | Testdaten: „Kein Kredit erfasst.", nicht geprüft |
| Dunkel-Theme (Stichprobe Übersicht) | — | Nein | OK, guter Kontrast, Bottom-Nav klar lesbar |
| Hell-Theme (Standard) | — | Nein (außer Erfassen) | OK |

## 3. Befunde

### QA5-01 — „Erfassen"-Seite überschreitet den 375-px-Viewport um 112 px (hoch)

- **Seite:** Erfassen (`#/erfassen`), Standardansicht ohne Interaktion.
- **Schritte:** Seite bei 375×812 öffnen, `document.documentElement.scrollWidth` messen.
- **Messwert:** `clientWidth 375` / `scrollWidth 487` → **112 px horizontaler Seiten-Overflow**, reproduzierbar auch bei 320 px (`scrollWidth 455`, Overflow 135 px) und 300 px.
- **Ursache (Elementkette per `getBoundingClientRect()` von `#ef-betrag` nach oben verfolgt):**
  `#ef-form` (das `<form>` in `.quick-card`, `display:grid;gap:14px` laut `static-neu/pages/erfassen.css:1`) hat selbst nur `156px` Breite (durch das umgebende zweispaltige Grid `.grid.g2-1` in `style.css` vorgegeben), aber sein Kind `.ef-amount-row` (und in der Folge `.field`, `#ef-betrag`, `#ef-sparte`, `#ef-text`, `#ef-zahlungsart` usw.) hat eine explizit berechnete Breite von `400.8px` — deutlich breiter als der eigene Grid-Container. Klassisches CSS-Grid-Verhalten: Ohne `min-width:0` auf den Grid-Items wird die Spur von deren Inhalts-Mindestbreite (`min-content`, hier durch `<input>`/`<select>` ohne eigene Breitenbegrenzung) aufgebläht, statt sich an der `156px`-Spur zu orientieren.
- **Dateien:** `static-neu/pages/erfassen.css:1` (`.erfassen-page .quick-card form{display:grid;gap:14px}`, kein `min-width:0`); Zusammenspiel mit `style.css` (`.grid.g2-1`, `.quick-card`, minifiziert, Regel nicht zeilengenau zitierbar).
- **Auswirkung:** Die komplette Buchungserfassung — das mobil meistgenutzte Formular der App laut Bottom-Nav-Mittelposition „＋" — ist bei 375 px horizontal nicht vollständig sichtbar, ohne dass die Seite selbst horizontal scrollbar wäre (kein sichtbarer Scroll-Indikator, `body{overflow:visible}`); Nutzer:innen müssen die ganze Seite seitwärts wischen, um Eingabefelder und den „Buchung speichern"-Button vollständig zu erreichen.
- **Empfehlung:** `min-width:0` auf die Grid-Items in `.erfassen-page .quick-card form` (bzw. auf `.ef-amount-row`, `.field`) ergänzen.

**Zusatzsymptom (selbe Ursache):** Der Dialog „Neue Kategorie" (ausgelöst über `#ef-newcat`, „+ Neue" neben dem Kategorie-Feld auf Erfassen) zentriert sich sichtbar außerhalb des Viewports — `getBoundingClientRect()` liefert `left:75 / right:412` bei `clientWidth:375`, mit einem `margin` von `74.5625px`, das exakt der halben Differenz zu `487px` (der überbreiten Seite) entspricht. Der native `<dialog>`-Zentrieralgorithmus scheint sich hier am selben verzerrten Bezugswert wie `window.innerWidth` zu orientieren statt am tatsächlichen `clientWidth`. Ob das auf einem echten Mobilgerät (mit korrekt geclamptem Layout-Viewport) identisch reproduziert, konnte in dieser Sitzung nicht unabhängig verifiziert werden — die zugrundeliegende Seiten-Überbreite (QA5-01) ist aber in jedem Fall real und sollte ohnehin behoben werden, was dieses Symptom voraussichtlich mitlöst.

### QA5-02 — Fünf von zehn Hauptseiten sind auf Mobil über keine UI erreichbar (hoch)

- **Seiten:** Sparte, Konten, Kredit, Kategorien, Export.
- **Schritte:** Bei 375×812 die Seite öffnen (beliebige Route), Bottom-Nav und Sidebar prüfen.
- **Messwert/Befund:** `#sidebar` hat `display:none` bei ≤760 px (dieselbe Instanz, in der `#mobile-nav` `display:flex` hat). `#mobile-nav` enthält laut `index.html:23` nur `data-route="uebersicht|buchungen|erfassen|belege|bankimport"` — fünf von zehn in `app.js:5` definierten Routen (`routes = {uebersicht, sparte, erfassen, buchungen, konten, kredit, kategorien, belege, bankimport, export}`). Es existiert **kein** Hamburger-/Mehr-Menü-Button, der die restlichen Routen erreichbar macht (im Markup nicht vorhanden, `grep` nach „menu-toggle/hamburger/sidebar-toggle" ohne Treffer).
- **Zusätzlich betroffen:** Da `#sidebar` auch den Bereichs-Umschalter (Haupt/Verein), „Passwort ändern", den Theme-Umschalter (`#theme-toggle`) und „Abmelden" enthält (`app.js:74`), sind auch **diese vier Funktionen auf Mobil über keine UI erreichbar** — nur per Deep-Link (Sparte/Konten/Kredit/Kategorien/Export) bzw. gar nicht (Bereichswechsel, Theme, Passwort, Logout).
- **Auswirkung:** Auf einem echten Handy kann eine Nutzerin ohne Lesezeichen/Deep-Link weder Konten noch Kredite noch Kategorien noch den Export öffnen, den Bereich nicht wechseln, das Theme nicht umschalten und sich nicht abmelden. Das ist keine kosmetische Lücke, sondern eine grundsätzliche Bedienbarkeitseinschränkung der Mobil-Ansicht.
- **Dateien:** `static-neu/index.html:14` (`<aside class="side" id="sidebar">`, keine mobile Alternative), `:23` (`#mobile-nav`, nur 5 Routen), `static-neu/app.js:74` (Sidebar-Inhalt inkl. Bereich/Theme/Logout/Passwort), CSS-Regel `#sidebar{display:none}` unterhalb 760 px (in `style.css`, minifiziert).
- **Empfehlung:** Mobiles Menü (z. B. Slide-in-Drawer oder „Mehr"-Button im Bottom-Nav) ergänzen, das mindestens Sparte/Konten/Kredit/Kategorien/Export sowie Bereichswechsel, Theme, Passwort und Logout erreichbar macht.

### QA5-03 — Viele Tap-Ziele deutlich unter 40 px Höhe (mittel)

- **Seiten:** durchgängig, am auffälligsten Buchungen und Kategorien.
- **Messwert (`getBoundingClientRect().height` aller sichtbaren `button/a/input/select`):**
  - Buchungen: „bearbeiten"/„stornieren" je **21 px** Höhe.
  - Kategorien: „umbenennen"/„stilllegen" je **19 px** Höhe (`k-table`-Zeilen).
  - Übersicht: Schließen-Button „×" auf Hinweiskarten **20×18 px**; „Ausgaben"/„Einnahmen"-Umschalter **29 px**.
  - Durchgehend: die drei Kopf-Filter „Alle Sparte(n)"/Jahr/„Mehr Filter" **37 px** (knapp unter der 40-px-Richtwerte, aber grenzwertig).
- **Auswirkung:** Reale Fehlbedienungsgefahr bei „bearbeiten" vs. „stornieren" (21 px, dicht nebeneinander in derselben Tabellenzeile) und bei „umbenennen" vs. „stilllegen" (19 px) — letzteres ist eine folgenreiche Aktion (Kategorie stilllegen).
- **Dateien:** `static-neu/pages/buchungen.js`/`.css`, `static-neu/pages/kategorien.js`/`.css` (Tabellen-Action-Links, keine expliziten `min-height`/Padding-Regeln für Touch-Ziele gefunden).
- **Einordnung:** Kein Blocker (Buttons sind technisch klickbar, auch mit Touch), aber abweichend von gängigen Touch-Ziel-Richtwerten (z. B. WCAG 2.5.8 „Target Size (Minimum)" 24×24 CSS-px als Minimum, 44px als Empfehlung); „umbenennen/stilllegen" mit 19 px unterschreitet auch die WCAG-Mindestgröße knapp.

### QA5-04 — Horizontal scrollbare Tabellen/Reiter ohne sichtbaren Hinweis (niedrig, kosmetisch)

- **Seiten:** Buchungen (`.tscroll`, Tabelle 994 px in 318 px Container), Kategorien (Tabelle `.tscroll` sowie Sparten-Reiter `.kattabs`, 552 px in 318 px Container), Bankimport (Umsatztabelle).
- **Befund:** Technisch sauber gelöst (`overflow-x:auto` in einem eigenen Container, kein Seiten-Overflow) — aber es gibt keinen sichtbaren Scrollindikator (Schatten/Pfeil), sodass auf den ersten Blick nicht erkennbar ist, dass rechts weitere Spalten/Reiter folgen.
- **Auswirkung:** Rein kosmetisch/Entdeckbarkeit, keine Funktionsblockade.

## 4. Nicht geprüft / offene Punkte

- **Dialog „Zuordnen" (Bankimport):** Testinstanz hat kein Bank-/Kartenkonto angelegt (`„Zuerst unter Konten ein Bank- oder Kartenkonto anlegen."`) — Dialog war ohne Dateneingriff (außerhalb des erlaubten Scopes: nur Bericht/Screenshots, keine Datenänderung an anderen Bereichen) nicht erreichbar.
- **Dialog „Beleg prüfen":** Testinstanz hat keine offenen Beleg-Auswertungen (`„Keine Belege zur Prüfung."`).
- **Dialog „Jahr bestätigen" (Kredit):** Testinstanz hat keinen Kredit angelegt (`„Kein Kredit erfasst."`).
- **Dialog „Erstattung erfassen":** Formular öffnete sich laut `clientWidth`-Messung ohne Overflow, aber der zugehörige Screenshot scheiterte an einem 5-Sekunden-Timeout; nicht visuell verifiziert, nur per JS-Messung.
- **Stichproben 390×844 und 320×568:** 320×568 wurde für den Emulations-Nachweis genutzt (siehe Abschnitt 1) und zeigte denselben QA5-01-Overflow (135 px statt 112 px) auf Erfassen — sonst nicht seitenweise wiederholt (Zeitgründe/Scope: Fokus auf 375×812 wie im Auftrag priorisiert). 390×844 wurde nicht separat durchlaufen.
- **Tastaturfokus-Verhalten** (Eingabefeld springt beim Fokussieren nicht aus dem Bild) wurde nicht mit echtem Tastatur-Overlay (das gibt es in dieser Desktop-Emulation nicht) geprüft, nur indirekt über `scrollIntoView`-Verhalten der Dialoge (`overflow-y:auto`, funktionierte in den geprüften Dialogen).
- **Bearbeiten/Konto-Dialog, Anfangsstand-Dialog, Kassa-gezählt-Dialog (Konten-Seite):** wegen QA5-02 (Konten-Seite nicht über Bottom-Nav erreichbar) nur der Seiten-Overflow der Konten-Liste selbst geprüft, die dortigen Dialoge nicht einzeln geöffnet (Zeitgründe).
- Funktionale Tiefenprüfung (Betragslogik, Validierung, Backend-Verhalten) war nicht Auftragsgegenstand dieser Runde und wurde nicht wiederholt; das betrifft ausschließlich Darstellung/Bedienbarkeit bei 375 px.

## 5. Gesamturteil

Die Emulation war entgegen der Erfahrung der vier vorherigen Tester **verlässlich**, sobald `document.documentElement.clientWidth` statt `window.innerWidth` gemessen wird — das erklärt vermutlich einen Teil der früher als „Emulation unsicher" gewerteten Befunde rückwirkend als Messfehler, nicht als Layoutfehler. Die eigentliche Mobil-Bedienbarkeit hat aber zwei ernste Lücken: Die „Erfassen"-Seite (das für Mobilnutzung zentrale Formular) läuft bei 375 px real 112 px über den Viewport hinaus (QA5-01, CSS-Grid-Ursache klar lokalisiert), und fünf der zehn Hauptseiten plus Bereichswechsel/Theme/Passwort/Logout sind auf Mobil über keine UI erreichbar, weil die Sidebar unterhalb 760 px komplett verschwindet, ohne dass ein Ersatzmenü existiert (QA5-02). Beide Befunde sollten vor einer produktiven Mobilnutzung behoben werden. Die übrigen sechs erreichbaren Seiten sowie die getesteten Dialoge (Bearbeiten, Stornieren, teilweise Erstattung) sind sauber im Viewport, nutzen für breite Tabellen korrekt gekapselte Scroll-Container und funktionieren in Hell- wie Dunkel-Theme ohne Konsolen- oder Serverfehler; kleinere Tap-Ziel- und Entdeckbarkeits-Schwächen (QA5-03, QA5-04) sind nachrangig.
