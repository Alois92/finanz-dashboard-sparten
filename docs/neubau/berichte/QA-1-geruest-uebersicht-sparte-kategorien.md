# QA-1: Gerüst, Übersicht, Sparte, Kategorien

Testinstanz: http://127.0.0.1:8051/ (neues Frontend unter `/`, Login-Bypass, Wegwerf-DB Schema 17, 25 Buchungen 2026).
Werkzeuge: `mcp__Claude_Browser__*`, `curl` gegen `/api/...`, Read/Grep gegen Code und Serverlog. Kein Code geändert.

## 1. Umfang / Checkliste

### Gerüst
- [OK] Kopf: Bereich (Haupt/Verein), Seitentitel, Sparten-Dropdown, Jahreswahl, „Mehr Filter" vorhanden und funktional.
- [OK] Sidebar: Bereichsumschalter, Hauptnavigation (10 Punkte), Sparten-Liste, „+ Gruppe anlegen", Werkzeuge, Passwort ändern (Link vorhanden, nicht angeklickt), Theme-Schalter, Abmelden (vorhanden, nicht ausgelöst um Session zu erhalten).
- [OK] Bereichswechsel Haupt → Verein: Sidebar/Kopf zeigen sofort nur „ZINA", Kennzahlen wechseln korrekt auf Verein-Daten (€0,00, keine Haupt-Zahlen sichtbar). Rückwechsel zu Haupt fehlerfrei.
- [OK] Sparten-Wahl im Kopf (Dropdown) filtert Übersicht korrekt (getestet mit „Vermietung Haus Münster": Zahlen und Filterhinweis „Filter aktiv: …" korrekt, „zurücksetzen" funktioniert).
- [OK] Jahreswahl: nur 2026 verfügbar (einziges Jahr mit Buchungen in der Testdatenbank + laufendes Jahr identisch) – Wechsel zwischen mehreren Jahren nicht testbar, siehe Abschnitt 3.
- [Befund QA1-04, niedrig] Hell/Dunkel-Theme: Umschalten funktioniert, Wert wird in `localStorage` (`neu-theme`) gespeichert und bleibt nach echtem Reload erhalten. Kein Befund hier, siehe „nicht geprüft" für einen Timing-Sonderfall beim allerersten Laden.
- [OK] TEST-INSTANZ-Banner sichtbar (oben, orange), `instanz` korrekt aus `/api/schema` gelesen.
- [OK] Navigation: alle 10 Menüpunkte einmal angeklickt/direkt per Hash aufgerufen (Übersicht, Sparte, Erfassen, Buchungen, Konten, Kredit, Kategorien, Belege, Bankimport, Export) – jede Seite lädt ohne Konsolenfehler und ohne Server-Fehlerzeile im Log.
- [OK] Unbekannter Hash (`#/nichtexistent`): fällt sauber auf Übersicht zurück, kein Absturz, keine Fehlermeldung.
- [Befund QA1-01, mittel] Hash-Routen `#/sparte/<id>`: Deep-Link mit ID lädt beim ersten Aufruf korrekt, wird danach aber sofort auf `#/sparte` normalisiert (ID verschwindet aus der Adresszeile). Sparten-Wechsel über Kachel/Sidebar/Kopf-Dropdown ändert den Hash nie. Browser-Zurück-Taste getestet: springt direkt von der Sparten-Detailansicht zur vorherigen Route (Übersicht), überspringt zuvor besuchte andere Sparten – kein Einzelschritt-Verlauf zwischen Sparten möglich. Gruppen-Hash (`#/sparte/gruppe-<id>`) bleibt dagegen korrekt in der URL stehen.
- [OK] 404/unbekannte Hashes: siehe oben, sauber behandelt.

### Übersicht (Startseite)
- [OK] KPI-Zeile Einnahmen/Ausgaben/Saldo mit „bisher"-Zusatz, Sparkline, Vorjahresvergleich (kein Vorjahr vorhanden in Testdaten → „kein Vorjahr" korrekt angezeigt statt Absturz).
- [OK] Sparten-Kacheln: alle 5 Haupt-Sparten mit korrektem Saldo/Einnahmen/Ausgaben, Klick auf Kachel öffnet die jeweilige Sparten-Detailseite (Inhalt korrekt, siehe QA1-01 zur URL).
- [OK] Verein/ZINA erscheint nie zwischen den Haupt-Kacheln (server- und clientseitig sauber getrennt, per API und UI verifiziert).
- [OK] Hinweise („Woran du dich kümmern solltest"): „Größte Buchung" und „Kategorie-Anteil"-Hinweis vorhanden, Knopf „Buchungen zeigen" öffnet Drilldown-Dialog mit korrekten Buchungszeilen.
- [Befund QA1-02, kritisch] Drilldown-Dialog-Fußzeile zeigt immer „Saldo € 0,00", unabhängig vom tatsächlichen Betrag (siehe Befund unten).
- [OK] Knopf „×" (Hinweis ausblenden) ruft `POST /api/hinweise/aus`, kein `localStorage`-Mechanismus mehr wie im Prototyp (Code geprüft).
- [OK] Konten und Kassen: eine Zeile je Kassa/Konto, „kein Anker"-Zustand korrekt dargestellt (kein Absturz bei fehlenden Ankern).
- [OK] Offene Auslagen: „Keine offenen Auslagen." korrekt bei leeren Testdaten.
- [OK] Verlauf über das Jahr (Sparkline-Chart Einnahmen/Ausgaben) rendert ohne Fehler.
- [OK] Größte Posten nach Kategorie: Umschalter Ausgaben/Einnahmen vorhanden, Balken mit Anteilen korrekt.
- [OK] „Mehr Filter" (Richtung/Zahlungsart/Kategorie): Richtung „Einnahmen" getestet – Ausgaben-Kachel korrekt auf €0,00, Filterhinweis korrekt, „zurücksetzen" stellt Ausgangszustand wieder her.
- [Nicht geprüft] Kreditkachel, Belege-Hinweis: siehe Abschnitt 3 – im Code von `uebersicht.js` existiert keine feste UI-Sektion dafür; es sind ausschließlich dynamische Einträge im `hinweise`-Array vom Server möglich. Testdaten enthalten keinen Kredit und keinen entsprechenden Hinweis, daher nicht auslösbar.
- [OK] Datenstand-Zeile („letzte Buchung … · letzter Import –") korrekt.

### Seite Sparte (P32/P32b)
- [OK] Kachel-Auswahlbildschirm (`#/sparte` ohne gewählte Sparte) zeigt 5 Sparten-Kacheln + 5 Auswertungsgruppen-Kacheln.
- [OK] Auswahl einer Einzelsparte: KPI-Zeile, Barkassa, Auslagen (leer korrekt), Kategorien-Jahresvergleich (Matrix), „Wohin das Geld geht", Verlauf – alle Abschnitte mit Testdaten korrekt befüllt (getestet mit Vermietung Haus Münster, Ferienhaus Köcken).
- [OK] „Eigene Kennzahlen": korrekter Leerzustand „Keine eigenen Kennzahlen angelegt." plus Hinweistext, kein Editor vorhanden (spec-konform). Echte Kennzahl-Werte konnten mangels Testdaten nicht geprüft werden (siehe Abschnitt 3).
- [OK] Auswertungsgruppe (`#/sparte/gruppe-3`, „Hof gesamt" = Sparten 2+3): kombinierte KPIs korrekt (Summe aus beiden Sparten geprüft), „Eigene Kennzahlen"-Abschnitt entfällt vollständig wie gefordert (kein leerer Kasten), Barkassa zeigt eine Zeile je Sparte der Gruppe, Matrix kombiniert korrekt.
- [OK] Kategorien im Jahresvergleich: Block „Einnahmen"/„Ausgaben" getrennt, Summenzeile korrekt, stillgelegte Kategorien bleiben sichtbar (siehe Kategorien-Test QA1-Test „stilllegen").
- [Teilweise geprüft] Jahres-Chips (`#s-years`): nur ein Chip „2026" vorhanden, da `GET /api/jahre` in der Testdatenbank nur 2026 liefert (einziges Jahr mit Buchungen). Mehrjahres-Auswahl, Abwählen und „mindestens ein Jahr muss aktiv bleiben" konnten dadurch nicht funktional geprüft werden – Code (`jahreZustand`) sieht das Verhalten vor, siehe Abschnitt 3.
- [OK] Zellklick in der Matrix öffnet Drilldown (stichprobenartig geprüft über Hinweise/Top-Kategorien, gleicher Mechanismus).
- [Befund QA1-01] Sparten-Wechsel über Sidebar/Kopf/Kachel setzt weiterhin keine ID in die URL (siehe Gerüst-Abschnitt).
- [Befund QA1-02] Drilldown-Fußzeile „Saldo € 0,00" auch hier reproduziert (gleicher Code-Pfad wie Übersicht).

### Seite Kategorien (P33)
- [OK] Reiter je Sparte, Wechsel lädt Kategorien + Jahresmatrix neu, kein Fehler.
- [OK] Kategorientabelle: Name, Richtung, Stichwörter, Summe/Ø je Monat, stillgelegte Kategorien mit Pille „stillgelegt", bleiben sichtbar (`nur_aktive=false` korrekt verwendet).
- [OK] Umbenennen (inline): korrektes Umbenennen funktioniert (`PATCH /api/kategorien/{id}` mit neuem Namen, Toast „„X" gespeichert.", Tabelle aktualisiert sich).
- [Befund QA1-04, niedrig] Leerer Name beim Umbenennen: wird korrekt verworfen (kein PATCH, alter Name bleibt in der DB), aber ohne jede Rückmeldung an die Nutzerin/den Nutzer (kein Toast, keine Fehlermeldung) – wirkt wie „nichts passiert".
- [Befund QA1-03, mittel] Duplikat-Name beim Umbenennen: **keine Validierung**, Umbenennen von „Umbau" in „Versicherung" (bereits vorhandener Name in derselben Sparte) wurde klaglos akzeptiert; es existieren jetzt zwei nicht unterscheidbare Kategorien „Versicherung" (id 42 und 43) in Sparte 1.
- [OK] Stilllegen/Aktivieren: Umschalten funktioniert beidseitig, Pille erscheint/verschwindet korrekt, Server-Zustand stimmt.
- [OK] Stichwort hinzufügen: `+ Stichwort`-Eingabe erzeugt korrekt einen `regel`-Datensatz (`quelle=stichwort`), Chip erscheint sofort.
- [OK] Stichwort entfernen (×): setzt `aktiv=0` in der Regel (kein Löschen), Chip verschwindet, per API verifiziert.
- [OK] „+ Neue Kategorie": navigiert korrekt zur Erfassen-Seite (spec-konform: nur einfacher Seitenwechsel, kein eigenes Formular hier vorgesehen).
- [OK] Gruppen über Sparten hinweg: rendert fehlerfrei, alle Gruppen zeigen „0 Kat." / „€ 0,00" – dies liegt an leeren `kategorie_ids` in der Testdatenbank (`GET /api/globalgruppen` bestätigt per API), nicht an einem erkennbaren Frontend-Fehler. Aggregationslogik selbst nicht mit echten Daten verifizierbar (siehe Abschnitt 3).
- [OK] Gelernte Merkregeln: Leerzustand „Keine gelernten Merkregeln." korrekt (keine Testdaten für `quelle=gelernt` vorhanden).
- [Befund QA1-05, niedrig, unsicher] Einmaliger, nicht zuverlässig reproduzierbarer JS-Fehler in der Konsole während der Rename-/Stichwort-Tests, siehe Befundliste.

### Handy-Ansicht (375 px)
- [Eingeschränkt geprüft] `resize_window(preset: mobile)` hat in dieser Session `window.innerWidth` nicht zuverlässig auf 375 px gesetzt (gemessen wurden 746–748 px trotz korrekt gesetztem `<meta name="viewport" content="width=device-width,initial-scale=1">` in `static-neu/index.html`). Das wirkt wie eine Emulations-Eigenheit des Test-Werkzeugs, nicht wie ein Layoutfehler der App – wird hier gemäß Auftrag vermerkt statt als Befund gewertet. Visuell (Screenshot) zeigten Übersicht und Kategorien dennoch ein sauberes, schmales Layout mit sichtbarer Bottom-Navigation (Start/Buchungen/+/Belege/Import) und TEST-INSTANZ-Banner; die Kategorientabelle wirkte auf der berichteten (zu breiten) Viewport-Größe an den Rändern abgeschnitten (Sparten-Reiter, Summe-Spalten, Aktionen) – ob das bei echten 375 px ebenfalls der Fall ist (mit horizontalem Scroll-Container) oder nicht, konnte wegen der Emulations-Unsicherheit **nicht zuverlässig verifiziert werden**. Empfehlung: mit echtem Gerät oder stabilerem Emulator erneut prüfen, insbesondere die Kategorientabelle auf horizontale Scrollbarkeit.
- [OK, soweit prüfbar] Kein Konsolenfehler durch die Mobil-Ansicht selbst ausgelöst.

## 2. Befunde

**QA1-01 — Sparten-Wechsel wird nicht in der URL abgebildet (mittel)**
Seite: Sparte (`static-neu/pages/sparte.js`), betrifft auch den Einstieg von der Übersicht (`static-neu/pages/uebersicht.js`).
Schritte: Übersicht → auf eine Sparten-Kachel klicken → URL bleibt `#/sparte` (keine ID) → im Sidebar/Auswahlbildschirm eine andere Sparte anklicken → URL bleibt weiterhin `#/sparte` → Browser-Zurück-Taste drücken.
Erwartet (P30/P32-Vorgabe „Zustand in der URL (Hash)", „Hash-Routen … Zurück-Taste des Browsers" laut Testauftrag): jede gewählte Sparte sollte im Hash erkennbar sein bzw. die Zurück-Taste sollte zwischen zuvor besuchten Sparten navigieren können.
Tatsächlich: `location.hash` bleibt bei jedem Sparten-Wechsel unverändert auf `#/sparte` (Code: `waehleSparte()`/`goSparte()` setzen `location.hash='#/sparte'` und lösen bei bereits identischem Hash-Wert manuell ein `hashchange`-Event aus, statt einen neuen Verlaufseintrag zu erzeugen). Browser-Zurück sprang in meinem Test direkt von der zuletzt angezeigten Sparte zur vorherigen Route (Übersicht) und übersprang alle zwischenzeitlich besuchten Sparten. Ein direkter Deep-Link `#/sparte/2` lädt zwar beim ersten Aufruf korrekt die richtige Sparte, die URL wird danach aber sofort intern auf `#/sparte` normalisiert (`syncSparteAusHash()`), sodass die Adresse nicht mehr teilbar/bookmarkbar ist.
Konsole/Log: keine Fehler, rein funktionales Verhalten.
Datei: `static-neu/pages/sparte.js` (Zeilen ~52–74, `syncSparteAusHash`, `waehleSparte`), `static-neu/pages/uebersicht.js` (`goSparte`, Zeile ~156).

**QA1-02 — Drilldown-Dialog zeigt immer „Saldo € 0,00" (kritisch — falsche Zahl)**
Seite: Übersicht und Sparte (jeder Drilldown, der Buchungslisten anzeigt).
Schritte: Übersicht → Hinweis „Größte Buchung: …" → „Buchungen zeigen" klicken (oder beliebiger anderer Drilldown mit Buchungsliste).
Erwartet: Fußzeile zeigt den tatsächlichen Saldo der angezeigten Buchungen (hier: −€ 258,04 für eine einzelne Ausgabe).
Tatsächlich: Fußzeile zeigt „Saldo € 0,00", unabhängig vom tatsächlichen Betrag.
Ursache (Code-Analyse): `static-neu/pages/uebersicht.js:136` und `static-neu/pages/sparte.js:270` lesen `summe.saldo_cent`; die Antwort von `GET /api/buchungen` (`app/routers/buchungen.py`, Zeile 262–264) liefert im `summen`-Objekt jedoch nur `einnahmen_cent`, `ausgaben_cent`, `anzahl` – kein `saldo_cent`. Der Fallback `summe.saldo_cent || 0` greift daher immer. Zum Vergleich: der Hilfsbaustein `app/rechenbasis.py` (Zeile 144–146) berechnet für andere Endpunkte `saldo_cent = einnahmen_cent - ausgaben_cent` korrekt – dieses Muster fehlt in `buchungen.py`.
Beleg (API-Antwort): `curl http://127.0.0.1:8051/api/buchungen?bereich_id=1&sparte_id=1` → `"summen":{"einnahmen_cent":0,"ausgaben_cent":25804,"anzahl":1}` (kein `saldo_cent`).
Betroffene Dateien: `app/routers/buchungen.py`, `static-neu/pages/uebersicht.js` (Zeile 136), `static-neu/pages/sparte.js` (Zeile 270).

**QA1-03 — Duplikat-Kategorienamen innerhalb derselben Sparte werden ohne Warnung akzeptiert (mittel)**
Seite: Kategorien.
Schritte: Sparte „Vermietung Haus Münster" → Kategorie „Umbau" → „umbenennen" → Namen zu „Versicherung" ändern (bereits vorhandener Name in derselben Sparte, Kategorie-ID 43) → Enter.
Erwartet: Validierungsfehler/Ablehnung, da zwei gleichnamige Kategorien in derselben Sparte Verwirrung stiften (z. B. in Dropdown-Filtern nicht unterscheidbar).
Tatsächlich: `PATCH /api/kategorien/42` wurde mit 200 OK angenommen, Toast „„Versicherung" gespeichert." erschien. `GET /api/kategorien?bereich_id=1&sparte_id=1&nur_aktive=false` zeigt danach zwei Einträge mit `"name":"Versicherung"` (id 42 und 43).
Betroffene Dateien: `app/routers/stammdaten.py` (PATCH-Endpoint ohne Duplikatprüfung), `static-neu/pages/kategorien.js` (`startRename`, Zeilen 163–195, keine clientseitige Duplikatprüfung).
Hinweis: Testdatenbank wurde durch diesen Test dauerhaft verändert (Kategorie 42 heißt jetzt „Versicherung" statt „Umbau") – unkritisch, da Wegwerf-DB.

**QA1-04 — Leerer Kategoriename wird stillschweigend verworfen, ohne Rückmeldung (niedrig)**
Seite: Kategorien.
Schritte: Kategorie → „umbenennen" → Textfeld leeren → Enter.
Erwartet: entweder eine Fehlermeldung/Toast, oder zumindest ein erkennbarer Hinweis, warum nichts gespeichert wurde.
Tatsächlich: Kein PATCH-Aufruf, Name bleibt in der Datenbank unverändert (korrekt), aber es erscheint kein Toast und keine Fehlermeldung – aus Nutzersicht scheint der Vorgang wirkungslos zu verpuffen, ohne erkennbaren Grund.
Datei: `static-neu/pages/kategorien.js`, Zeile 176 (`if (!neu || neu === k.name) { renderTable(); return; }` – kein `toast(...)`-Aufruf im Leer-Fall).

**QA1-05 — Vereinzelter, nicht zuverlässig reproduzierbarer JS-Fehler in der Kategorien-Seite (niedrig, unsicher)**
Seite: Kategorien.
Während der Rename-/Stichwort-/Stilllegen-Tests erschien wiederholt in der Browser-Konsole:
`TypeError: Cannot read properties of null (reading 'replaceWith')` in `pages/kategorien.js:141` (Aufrufstelle: `if (k) startRename(btn.closest('tr'), k);`, tatsächlicher Fehler vermutlich in `startRename()` selbst, Zeile ~168: `span.replaceWith(input)`, wenn `span` (`tr.querySelector('.kname')`) `null` ist – z. B. wenn „umbenennen" auf eine Zeile geklickt wird, die sich gerade bereits im Bearbeiten-Zustand befindet oder gerade neu gerendert wird).
Ich konnte diesen Fehler nicht sauber isoliert reproduzieren (er blieb über mehrere Seitenwechsel und `location.reload()` hinweg in der Konsolen-Historie sichtbar, was auf eine einmalige Ursache aus einem meiner eigenen Testschritte hindeutet, vermutlich ein Doppel-Klick-/Race-Fall zwischen Blur-Event und erneutem Klick auf „umbenennen"). Empfehlung an das Entwicklerteam: `startRename()` defensiv machen (`if (!span) return;`) und prüfen, ob durch schnelle Doppel-Interaktion (Klick während Blur-Speichervorgang) eine Race-Bedingung entstehen kann.

**QA1-06 — Fehlendes Favicon (niedrig, kosmetisch)**
`static-neu/` liefert kein `favicon.ico`, jeder Seitenaufruf erzeugt einen 404-Eintrag im Serverlog (`qa-8051.log`, durchgehend `GET /favicon.ico … 404 Not Found`). Rein kosmetisch, keine Funktionsstörung.

## 3. Nicht geprüft / Einschränkungen

- **Mehrjahres-Vergleich (Sparte-Matrix, Jahres-Chips):** Testdatenbank enthält Buchungen nur für 2026, `GET /api/jahre` liefert dadurch nur `[2026]`. Das Abwählen von Jahren, „mindestens ein Jahr muss aktiv bleiben" und der erneute Server-Aufruf bei Jahreswechsel konnten dadurch nicht mit echten Mehrjahresdaten geprüft werden – nur der Einzeljahr-Fall ist bestätigt funktionsfähig.
- **Eigene Kennzahlen (Sparte-Seite):** `GET /api/kennzahlen` liefert für alle getesteten Sparten `[]` (keine Kennzahlen in der Testdatenbank angelegt). Nur der Leerzustand wurde geprüft, nicht die Darstellung echter Kennzahl-Werte/Formeln.
- **Kreditkachel, Belege-Hinweis auf der Übersicht:** laut Code (`uebersicht.js`) keine feste UI-Sektion dafür vorgesehen, nur dynamische `hinweise`-Einträge vom Server möglich; Testdaten enthalten keinen Kredit (`#/kredit` zeigt „Kein Kredit erfasst.") und lösten keinen entsprechenden Hinweis aus – daher nicht testbar in dieser Instanz.
- **Handy-Ansicht (375 px):** `resize_window(preset: mobile)` hat in dieser Browser-Session `window.innerWidth` nicht zuverlässig auf 375 px gesetzt (gemessen 746–748 px trotz korrektem `<meta viewport>`-Tag in `index.html`). Layoutprüfung auf echten 375 px daher nur eingeschränkt über Screenshots möglich, siehe Abschnitt 1. Insbesondere die horizontale Bedienbarkeit der Kategorientabelle unter echten 375 px sollte erneut geprüft werden.
- **Gruppen über Sparten hinweg (Aggregation):** alle Testgruppen haben leere `kategorie_ids` (`GET /api/globalgruppen` bestätigt), daher konnte die im P33-Auftrag beschriebene Summenbildung aus der bereichsweiten Jahresmatrix nicht mit echten Werten verifiziert werden – nur der (korrekte) Leerzustand „0 Kat./€0,00".
- **Gelernte Merkregeln:** Testdatenbank enthält keine Regeln mit `quelle=gelernt`, daher wurde nur der Leerzustand geprüft, nicht Anzeige/„abschalten" einer echten gelernten Regel.
- **Passwort ändern, Abmelden:** Links/Knopf vorhanden und erreichbar, aber nicht ausgelöst, um die laufende Testsession nicht zu unterbrechen.
- **Auswertungsgruppen „+ Gruppe anlegen":** Dialog öffnet korrekt (Titel „Auswertungsgruppe anlegen"), das tatsächliche Anlegen einer neuen Gruppe wurde nicht bis zum Absenden durchgetestet (um die Testdatenbank nicht weiter zu verändern als nötig).
- Es wurden ausschließlich Bereich Haupt und Verein mit den vorgegebenen Testdaten geprüft; keine Prüfung mit leeren Bereichen ganz ohne Sparten/Buchungen.

## 4. Gesamturteil

Gerüst, Übersicht und Kategorien-Seite sind im Kern solide und funktionieren mit der Testdatenbank durchgehend ohne Abstürze oder Konsolenfehler bei normaler Nutzung; die Bereichstrennung Haupt/Verein (ZINA-Ausschluss) funktioniert sauber. Zwei Befunde sollten vor Abnahme behoben werden: die durchgängig falsche „Saldo € 0,00"-Anzeige in allen Drilldown-Dialogen (QA1-02) sowie die fehlende Duplikatprüfung beim Umbenennen von Kategorien (QA1-03); die URL-Navigation zwischen Sparten (QA1-01) ist funktional nicht blockierend, weicht aber spürbar vom in P30 zugesagten Hash-basierten Zustand ab und sollte nachgezogen werden.
