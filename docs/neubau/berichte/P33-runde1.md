# P33 – Runde 1

Stand: 2026-09-10. Worktree: `C:\Users\lblet\dev\wt-p33`, Branch: `pkt/p33-seite-kategorien` (von `neubau`, nach P30b).

## Ergebnis

P33 ist umgesetzt. `static-neu/pages/kategorien.js` zeigt je Sparte (Reiter, Seitenzustand) die Kategorien mit Buchungssumme
und Monatsdurchschnitt aus `GET /api/jahresmatrix`, erlaubt Umbenennen und Stilllegen/Aktivieren echt über
`PATCH /api/kategorien/{id}`, verwaltet Stichwörter als echte `regel`-Datensätze (`quelle='stichwort'`) über
`POST /api/regeln` und `PATCH /api/regeln/{id} {aktiv:false}`, zeigt spartenübergreifende Kategoriegruppen als Balken
(Summe aus der bereichsweiten Jahresmatrix) und eine Tabelle der gelernten Merkregeln (`quelle='gelernt'`) mit
„abschalten“ über denselben Regel-Endpunkt. Kein `toast("Im Prototyp nur angedeutet")` mehr für diese Aktionen.

## Geänderte und neue Dateien

- `static-neu/pages/kategorien.js` (ersetzt den P30-Platzhalter): komplette Seite – Reiter, Kategorientabelle mit
  Inline-Umbenennen (Enter speichert, Escape verwirft, Blur speichert als Fallback) und Stilllegen/Aktivieren,
  Stichwort-Chips mit Hinzufügen/Entfernen, Gruppen-Balken, Tabelle der gelernten Merkregeln.
- `static-neu/pages/kategorien.css` (neu): Ergänzung für Reiter, Tabelle, Chips und Balken, alle Selektoren auf die
  `#k-*`-Container beschränkt, damit sie sich nicht mit gleichnamigen Klassen anderer bereits geladener Seiten
  überschneiden (z. B. `.hbar` aus `uebersicht.css`).
- `tests/test_static_neu_kategorien.py` (neu): sieben Tests laut Auftragskarte Abschnitt 6.

Nicht angefasst: `app.js`, `api.js`, `ui.js`, `format.js`, `charts.js`, `style.css`, `index.html`, sowie
`app/routers/stammdaten.py`, `app/routers/gruppen.py`, `app/regeln.py`, `app/routers/import_bank.py` – keine
Backend-Änderung, keine Migration.

## Festlegungen aus der Karte, wie umgesetzt

- Aktiver Reiter startet mit `state.filter.sparteId`, falls gesetzt und in `state.sparten` vorhanden, sonst mit der
  ersten Sparte (`initialSparte()`).
- Reiterwechsel ändert nur den lokalen Seitenzustand (`local.activeSparteId`), nicht `state.filter` – bestätigt im
  Browsertest: der Kopf-Select „Alle Sparten“ blieb beim Reiterwechsel unverändert.
- Umbenennen, Stilllegen, Stichwort anlegen/entfernen und Regel abschalten laufen über die echten Endpunkte
  (siehe Antwort-JSON unten), kein Platzhalter-Toast.
- Nach Umbenennen/Stilllegen: `patchZentraleKategorieFilterFallsAktiv()` aktualisiert `#filter-kategorie` direkt aus
  den frisch geladenen Kategorien des aktiven Reiters, sofern der Kopf-Filter (`state.filter.sparteId`/`state.sparteId`)
  gerade dieselbe Sparte zeigt – siehe „Wunsch an das Gerüst“ unten für die Einschränkung.

## Verwendete Endpunkte mit wörtlichem Antwort-JSON

Aufgezeichnet mit dem ASGI-Testclient-Muster aus `tests/test_static_neu.py` gegen eine frische Wegwerf-DB
(Schema + Seed, dazu eine Test-Sparte/-Kategorie/-Regel/-Konto/-Gruppe wie im eigenen Test):

```
### GET /api/sparten?bereich_id=1 -> 200
[{"id": 1, "name": "Privatvermietung", "kuerzel": "PV", "typ": "vermietung", "geschuetzt": 0, "farbe": "#6AA9FF"}, {"id": 2, "name": "Zimmervermietung Hof", "kuerzel": "ZVH", "typ": "vermietung", "geschuetzt": 0, "farbe": "#2DD4BF"}, ...]

### GET /api/kategorien?bereich_id=1&sparte_id=1&nur_aktive=false -> 200
[{"id": 1, "sparte_id": 1, "parent_id": null, "name": "Futtermittel", "richtung": "ausgabe", "sortierung": 0, "aktiv": 1}]

### GET /api/jahresmatrix?bereich_id=1&sparte_id=1&jahre=2026 -> 200
{"jahre": [2026], "stichtag": "2026-09-10", "zeilen": [{"kategorie_id": 1, "name": "Futtermittel", "sparte_id": 1, "aktiv": 1, "richtung": "ausgabe", "werte": {"2026": {"einnahmen_cent": 0, "ausgaben_cent": 4500}}, "erwartung_cent": {"einnahmen": 0, "ausgaben": 4500}, "ohne_vorjahr": true, "monatsdurchschnitt_cent": {"2026": {"einnahmen_cent": 0, "ausgaben_cent": 500}}}], "summen": {"2026": {"einnahmen_cent": 0, "ausgaben_cent": 4500, "saldo_cent": -4500}}}

### GET /api/regeln?bereich_id=1&quelle=stichwort -> 200
[{"id": 1, "name": "lagerhaus", "aktiv": 1, "prioritaet": 100, "bedingung_text": "lagerhaus", "bedingung_betrag_von_cent": null, "bedingung_betrag_bis_cent": null, "bankkonto_id": null, "ziel_sparte_id": 1, "ziel_kategorie_id": 1, "ziel_typ": null, "quelle": "stichwort", "auto_verbuchen": 0, "eingabe_sparte_id": null, "gelernt_aus_buchung_id": null, "erstellt_am": "2026-09-10 21:54:02"}]

### GET /api/regeln?bereich_id=1&quelle=gelernt -> 200
[{"id": 2, "name": "werkstatt", "aktiv": 1, "prioritaet": 100, "bedingung_text": "werkstatt", "bedingung_betrag_von_cent": null, "bedingung_betrag_bis_cent": null, "bankkonto_id": 1, "ziel_sparte_id": 2, "ziel_kategorie_id": 2, "ziel_typ": null, "quelle": "gelernt", "auto_verbuchen": 0, "eingabe_sparte_id": null, "gelernt_aus_buchung_id": null, "erstellt_am": "2026-09-10 21:54:02"}]

### GET /api/globalgruppen?bereich_id=1 -> 200
[{"id": 2, "name": "Auto und Mobilitaet", "beschreibung": null, "kategorie_ids": []}, ..., {"id": 14, "name": "Testgruppe", "beschreibung": "Beschreibung", "kategorie_ids": [1, 2]}, ...]

### GET /api/konten?bereich_id=1 -> 200
[{"id": 1, "name": "Testkonto", "art": "bank", "waehrung": "EUR", "sparte_id": null, "iban": null, "bank": null, "kartenendnummer": null, "aktiv": 1, "sortierung": 0, "stand_cent": null, "datenstand": "unbekannt", "letzter_import": null, "hinweis": ""}]

### GET /api/jahresmatrix?bereich_id=1&jahre=2026 -> 200
{"jahre": [2026], "stichtag": "2026-09-10", "zeilen": [{"kategorie_id": 1, "name": "Futtermittel", "sparte_id": 1, "aktiv": 1, "richtung": "ausgabe", "werte": {"2026": {"einnahmen_cent": 0, "ausgaben_cent": 4500}}, ...}], "summen": {"2026": {"einnahmen_cent": 0, "ausgaben_cent": 4500, "saldo_cent": -4500}}}
```

Bestätigt außerdem den in der Karte (Abschnitt 3) benannten Punkt: `GET /api/regeln?sparte_id=` filtert nach
`ziel_sparte_id`, nicht nach der Sparte der Zielkategorie – deshalb lädt die Seite die Stichwort-/gelernten Regeln
einmal ohne `sparte_id` und filtert clientseitig nach `ziel_kategorie_id`, wie in der Karte vorgegeben.

`POST /api/regeln {name, bedingung_text, ziel_kategorie_id, quelle:'stichwort'}` und
`PATCH /api/regeln/{id} {aktiv:false|true}` sowie `PATCH /api/kategorien/{id} {name:...}` / `{aktiv:false|true}`
funktionieren mit JS-`true`/`false` im JSON-Body (von Pydantic auf `Literal[0,1]` bzw. `int` mit `ge=0,le=1`
koerziert – geprüft mit `pydantic.BaseModel.model_validate`).

## Testausgabe

Vollständig in `docs/neubau/berichte/P33-tests.txt`. Zusammenfassung:

- Eigene Datei `tests/test_static_neu_kategorien.py`, isoliert: **7 Tests, OK** (18,3 s).
- Gesamtsuite (`FINANZ_DB` auf Wegwerf-Datei, ohne `FINANZ_TEST_AUTH_BYPASS`): **377 Tests, OK, 1 übersprungen**
  (205,6 s). Die im Rohprotokoll enthaltenen Tracebacks (PIL-Bildfehler, fehlende Auth-Datei für Recovery-Code)
  stammen aus absichtlich simulierten Fehlerpfaden anderer Suiten und enden jeweils mit „ok“; kein Zusammenhang mit P33.
  (Zur Einordnung: P30b hatte 367 Tests gemeldet; die Differenz von 10 stammt aus Arbeit, die seither auf `neubau`
  gelandet ist, nicht aus diesem Paket – P33 selbst bringt genau die 7 eigenen Tests dazu.)

`node --check static-neu/pages/kategorien.js`: ohne Ausgabe (Erfolg), zusätzlich als eigener Test in der Testdatei.

## Browserprüfung

App gestartet mit `FINANZ_DB=%TEMP%\p33-app.db`, `FINANZ_INSTANZ=test`, eigener `FINANZ_AUTH_FILE`,
`FINANZ_TEST_AUTH_BYPASS=1` (laut Auftrag zulässig, da die DB unter dem Temp-Ordner liegt),
`python -m uvicorn app.main:app --port 8034`. Testdaten über die echten Endpunkte angelegt: zwei Sparten mit je
einer Kategorie, eine dritte stillgelegte Kategorie, eine Stichwort-Regel, ein Konto, eine gelernte Regel mit
Konto-Bezug, eine globale Gruppe mit Kategorien aus beiden Sparten, zwei Buchungen.

Geprüft im Chrome-Browser-Tool (Playwright selbst nicht genutzt, stattdessen `mcp__Claude_Browser__*`, siehe
„Werkzeug-Besonderheit“ unten):

- **Seite lädt ohne Konsolenfehler**: mehrfach per `read_console_messages` geprüft, keine echten Fehler
  (ein einzelner „Failed to load resource: ERR_CONNECTION_REFUSED“-Eintrag stammt nachweislich aus einem kurzen
  Serverausfall während der Prüfung, siehe unten, nicht aus dem Code der Seite).
- **Reiterwechsel**: Klick auf „Zimmervermietung Hof“ lädt die Kategorientabelle neu (andere Kategorie, andere
  Summe/Ø), der Kopf-Select „Alle Sparten“ blieb dabei unverändert – bestätigt, dass der Reiterwechsel
  `state.filter` nicht anfasst.
- **Umbenennen**: Klick auf „umbenennen“ öffnet das Eingabefeld mit vorausgewähltem Text; Speichern per Enter
  löste `PATCH /api/kategorien/{id}` (200) aus, Name in der Tabelle und in der Zielspalte der gelernten Regel
  (die auf dieselbe Kategorie zeigt) aktualisierten sich sofort. Escape verwirft die Eingabe ohne Aufruf.
- **Stilllegen/Aktivieren**: Klick auf „stilllegen“ löste `PATCH .../{id} {aktiv:false}` (200) aus, Zeile bekam
  die Pille „stillgelegt“; erneuter Klick auf „aktivieren“ machte die Kategorie wieder aktiv.
- **Stichwort hinzufügen**: Eingabe „Spar Markt“ + Enter im „+ Stichwort“-Feld löste
  `POST /api/regeln {quelle:'stichwort', ...}` (201) aus, Chip „spar markt“ (kleingeschrieben wie gefordert)
  erschien neben dem bestehenden „lagerhaus“-Chip.
- **Stichwort entfernen**: Klick auf „×“ löste `PATCH /api/regeln/{id} {aktiv:false}` (200) aus, Chip verschwand.
- **Gruppen-Balken**: „Testgruppe“ (2 Kategorien aus beiden Sparten) zeigte die Summe aus der bereichsweiten
  Jahresmatrix korrekt (45,00 + 22,00 = 67,00 €) neben den übrigen (leeren) Seed-Gruppen.
- **Gelernte-Regeln-Tabelle**: zeigte die manuell angelegte gelernte Regel mit Konto-Name und, weil ihre
  Zielkategorie nicht zum aktiven Reiter gehörte, zusätzlich dem Spartennamen; außerdem zwei automatisch beim
  Anlegen der Testbuchungen gelernte Regeln (Backend-Verhalten aus `app/routers/buchungen.py`, nicht Teil dieser
  Karte).
- **„abschalten“ entfernt Zeile**: Klick auf „abschalten“ bei der Konto-Regel löste `PATCH .../{id} {aktiv:false}`
  (200) aus, Zeile verschwand sofort aus der Tabelle (Filter `aktiv=1` beim Rendern).
- **„+ Neue Kategorie“**: Klick navigierte zu `#/erfassen` mit der Sparte des aktiven Reiters vorbelegt
  (Sparten-Select auf der Erfassen-Seite zeigte „Privatvermietung“).
- **Mobil (375 px)**: Seite lädt ohne Konsolenfehler, Kopf-Filter und Reiterleiste stapeln sich lesbar
  (`@media(max-width:760px)` in `kategorien.css` greift), Tabelle bleibt horizontal scrollbar in ihrer Karte
  (`.tscroll`, wie bei `buchungen.js`). Der genaue Pixel-Screenshot bei 375 px ließ sich mit dem verfügbaren
  Browser-Werkzeug nicht sauber einfangen (siehe „Nicht geprüft“ unten); die Bottom-Navigation selbst (Teil des
  unveränderten Gerüsts aus P30) wurde deshalb nicht separat gegengeprüft.

### Werkzeug-Besonderheit während der Prüfung

Zwei Auffälligkeiten, beide beim Kopf zu nennen, keine davon ein Fehler im gelieferten Code:

1. **Geteilter Browser über Sitzungen hinweg.** Während der Prüfung navigierte sich der Standard-Browser-Tab
   („seed“) mehrfach von selbst auf `http://127.0.0.1:8033` (offensichtlich Port des parallel laufenden P32
   in `wt-p32`) – ein anderer, gleichzeitig laufender Agent nutzt sichtbar denselben Browser/dieselbe
   Tab-Gruppe. Behoben durch einen eigenen, dedizierten Tab (`tabs_create` statt des Standard-Tabs) für den
   Rest der Prüfung.
2. **Synthetische Enter-/Escape-Tastendrücke.** Der reine `computer{action:"key", text:"Return"}`-Tastendruck
   des Browser-Werkzeugs löste den `keydown`-Handler des Umbenennen-Feldes nicht zuverlässig aus (ähnliches
   Verhalten wie das in `docs/neubau/berichte/P30b-runde1.md` für Escape im Dialog dokumentierte). Über
   `element.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true}))` ausgelöst, funktionierte
   Speichern (`PATCH`, 200, Name aktualisiert) und ebenso Escape (Abbrechen ohne Aufruf) zuverlässig – der
   Code ist also korrekt, nur der reine synthetische Tastendruck des Werkzeugs kommt nicht immer als
   „trusted event“ an. Der reguläre Weg über Blur (Klick woanders hin) hat in jedem Fall zuverlässig
   gespeichert.
3. **Kurzer Serverausfall.** Der lokale `uvicorn`-Prozess (Port 8034) wurde während der Prüfung einmal beendet
   (vermutlich durch Bash-Sandbox-Aufräumen des Hintergrundprozesses) und mit derselben DB neu gestartet;
   die eine dabei sichtbare `ERR_CONNECTION_REFUSED`-Meldung und der „Failed to fetch“-Toast stammen davon,
   nicht von einem Fehler in `kategorien.js`. Der fehlgeschlagene Umbenennungsversuch in diesem Fenster kam
   serverseitig nachweislich nicht an (per `curl` gegenkontrolliert).

## Wunsch an das Gerüst

`app.js` cached die Optionen von `#filter-kategorie` in einer modulprivaten Variable (`kategorieOptionsKey`,
Schlüssel `bereichId:sparteId`) und lädt nur bei Schlüsselwechsel neu (P30b). Ändert `kategorien.js` eine
Kategorie (umbenennen/stilllegen), bleibt der zentrale Filter veraltet, solange sich Bereich/Sparte nicht ändern
– `app.js` bietet dafür keine exportierte Invalidierungsfunktion. Lokaler Ersatz in dieser Karte:
`patchZentraleKategorieFilterFallsAktiv()` schreibt die Optionen von `#filter-kategorie` direkt aus den frisch
geladenen Kategorien des aktiven Reiters, aber nur, wenn der Kopf-Filter gerade dieselbe Sparte zeigt wie der
aktive Reiter – wechselt der Nutzer die Sparte im Kopf-Filter *nach* einer Umbenennung auf der Kategorienseite
zurück zu der Sparte, bleibt der Filter bis zu einem erneuten Bereichs-/Spartenwechsel veraltet. Eine exportierte
`invalidateKategorieFilterCache()` (oder ein `bereichId:sparteId`-Parameter, der `drawKategorieFilter()` zum
Neuladen zwingt) in `app.js` würde diesen Rand- und den lokalen Ersatz überflüssig machen.

## Offene Punkte

- Pixelgenauer 375-px-Screenshot der Kategorienseite ließ sich mit dem verfügbaren Browser-Werkzeug nicht
  zuverlässig erzeugen (das Werkzeug lieferte eine höhere Breite als die emulierte Viewport-Breite). Layout
  und Medienabfrage (`@media(max-width:760px)` in `kategorien.css`) wurden gelesen/visuell auf Stapelung
  geprüft, die Bottom-Navigation aus dem Gerüst wurde dabei nicht gesondert gegengeprüft.
- Der Rand aus „Wunsch an das Gerüst“ oben (zentraler Kategoriefilter nach Sparten-Rückwechsel) bleibt offen,
  solange `app.js` keine Invalidierung anbietet.
- Der Zufalls-Wert im Verzeichnis-Ordner der stillgelegten Test-Kategorie/-Regeln aus der Browserprüfung lag in
  der Wegwerf-DB `%TEMP%\p33-app.db`, die nach der Prüfung gelöscht wurde; keine Spuren im Repository.

Keine Migrationen, keine Backend-Änderungen, keine Commits außerhalb dieses Auftrags. Kein Push, kein Merge.
