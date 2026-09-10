# P52 Runde 1 – Kredit-Oberfläche

Zweig `pkt/p52-kredit-oberflaeche`, Worktree `wt-p52`. Umsetzung nach der P52-Karte
(`docs/neubau/pakete/P52-kredit-oberflaeche.md`) und dem gemeinsamen
`NACHTRAG-frontend-2026-09-10.md`. Die Karte erlaubt für dieses Paket ausdrücklich
genau eine Zeile in `static-neu/app.js` (Route `kredit` nach `konten`) sowie neue
Dateien `static-neu/pages/kredit.js` und `static-neu/pages/kredit.css`; sonst nichts
in `app.js`, nichts in `index.html` (keine Mobil-Navigation für Kredit verlangt),
kein Backend (`app/routers/kredite.py`, `app/kredite.py` unangetastet), keine Migration.

## Ergebnis

Die Kredit-Oberfläche ist unter `/neu/#/kredit` fertig: Kredit-Liste je gewählter
Sparte (oder aller Sparten), Leerzustand mit Inline-Anlegen-Formular, Jahresübersicht
als Pillen (geschätzt/bestätigt, Zins, Restschuld), „Jahr bestätigen"-Dialog mit
Beleg-Auswahl und persistenter Abweichungs-Warnliste, Ratentabelle mit getrennten
Zins-/Tilgungsspalten, „Rate erfassen"-Formular (Betrag vorbelegt mit Monatsrate),
sowie „Bestehende Buchungen zuordnen" mit Mehrfachauswahl. Alle Abläufe wurden im
Browser gegen eine Wegwerf-DB durchgespielt (siehe „Browserprüfung").

## Geänderte und neue Dateien

- `static-neu/app.js` — genau eine Zeile ergänzt: `kredit:['Kredit','kredit']` in der `routes`-Konstante, direkt nach `konten` (Navigation und Seiten-Laden entstehen dadurch automatisch aus dem bestehenden Mechanismus, sonst keine Änderung).
- `static-neu/pages/kredit.js` — neue Seite: Kredit-Liste/Anlegen, Jahresübersicht mit Bestätigen-Dialog, Ratentabelle, Rate erfassen, Zuordnen bestehender Buchungen.
- `static-neu/pages/kredit.css` — neue, von `kredit.js` selbst per `<link>` nachgeladene Stile (Kredit-Karten, Jahr-Pillen, Detailbereich); `style.css` bleibt unverändert.
- `tests/test_p52_kredit.py` — neue, eigenständige Testdatei (Seite/Modul/CSS ausgeliefert, Route in `app.js`, Vertragstests für Anlegen, Jahr bestätigen mit Abweichung, Ratenliste mit Zins/Tilgung, Zuordnen).
- `docs/neubau/berichte/P52-runde1.md`, `docs/neubau/berichte/P52-tests.txt` — dieser Bericht.

Keine Migration, keine Änderung an `app/routers/kredite.py`, `app/kredite.py`,
`api.js`, `ui.js`, `format.js`, `charts.js`, `style.css`, `index.html`,
`static-studio/` oder an bestehenden Testdateien.

## Verwendete Endpunkte mit wörtlichem Antwort-JSON

Aufgezeichnet mit dem projekttypischen Roh-ASGI-Testclient (gleiches Muster wie in
`tests/test_p50_buchungen.py`) sowie ergänzend per `curl` gegen die im Browserlauf
gestartete App, `FINANZ_TEST_AUTH_BYPASS=1`, `FINANZ_DB` auf eine Wegwerf-Datei.

### `POST /api/kredite`

Body: `{"sparte_id":1,"konto_id":1,"name":"Testkredit Hof","monatsrate_cent":50000,"beginn":"2025-01-01","zinssatz":0.035,"kategorie_zins_id":1,"kategorie_rate_id":2}`

```json
{"id":1,"name":"Testkredit Hof","sparte_id":1,"monatsrate_cent":50000,"beginn":"2025-01-01","jahre":[]}
```

Wichtiger Befund: **die Antwort enthält weder `kategorie_zins_id` noch
`kategorie_rate_id`** (siehe `_listeintrag` in `app/routers/kredite.py`). `kredit.js`
kann diese Felder deshalb nicht direkt aus dem Kredit-Objekt lesen — siehe „Wunsch an
das Gerüst" unten, dort auch die gewählte Umgehung.

### `GET /api/kredite`

```json
[
  {
    "id": 1, "name": "Testkredit Hof", "sparte_id": 1, "monatsrate_cent": 50000,
    "beginn": "2025-01-01",
    "jahre": [
      {"jahr": 2025, "zins_cent": 110000, "restschuld_cent": 4450000, "status": "bestaetigt"},
      {"jahr": 2026, "zins_cent": 109992, "restschuld_cent": null, "status": "geschaetzt"}
    ]
  },
  {"id": 2, "name": "ZVH Kredit", "sparte_id": 2, "monatsrate_cent": 30000, "beginn": "2026-09-10", "jahre": []}
]
```

`kredit.js` filtert diese Liste clientseitig nach `state.sparteId` (leer = alle
Sparten) und baut daraus die Jahres-Pillen (`jahre[].{jahr,zins_cent,restschuld_cent,
status}`, ergänzt um das laufende Jahr, falls es fehlt).

### `POST /api/kredite/{id}/raten`

Body: `{"datum":"2026-10-05"}` (Betrag weggelassen → Server nimmt `monatsrate_cent`)

```json
{"id":14,"kredit_id":1,"datum":"2026-10-05","betrag_cent":50000,"zins_cent":9166,"tilgung_cent":40834,"status":"geschaetzt","hinweis":null}
```

### `GET /api/kredite/{id}/raten?jahr=2025` (Ausschnitt)

```json
[
  {"id": 1, "kredit_id": 1, "datum": "2025-01-05", "betrag_cent": 50000, "zins_cent": 10000, "tilgung_cent": 40000, "status": "bestaetigt"},
  {"id": 2, "kredit_id": 1, "datum": "2025-02-05", "betrag_cent": 50000, "zins_cent": 10000, "tilgung_cent": 40000, "status": "bestaetigt"}
]
```

`kredit.js` zeigt daraus die Ratentabelle mit den Spalten Datum, Rate, Zins,
Tilgung, Status.

### `PUT /api/kredite/{id}/jahre/{jahr}` mit 11 statt 12 Raten (Abweichung)

Body: `{"zins_cent":110000,"restschuld_cent":4500000}`

```json
{"raten":11,"verteilt_cent":110000,"abweichungen":["11 Raten im Jahr 2025 statt 12"]}
```

`kredit.js` zeigt `abweichungen` als dauerhaft sichtbare Warnliste im „Jahr
bestätigen"-Dialog (Dialog bleibt nach dem Speichern offen, Formular wird deaktiviert,
Warnung verschwindet erst beim manuellen Schließen) und zusätzlich als Toast „Jahr
bestätigt, mit Abweichung." Im Browser nachgestellt, siehe „Browserprüfung".

### `POST /api/kredite/{id}/raten/zuordnen`

Body: `{"buchung_ids":[12]}`

```json
{"raten": 1, "buchung_ids": [12]}
```

### `GET /api/buchungen?...&von=<kredit.beginn>&bis=<heute>&sparte_id=<sparte>`

Liste wie aus P50 bekannt (`buchungen[].{id,datum,typ,betrag_cent,kredit_id,zeilen[].
{kategorie_id,neutral},...}`, `summen`, `naechster_cursor`). `kredit.js` nutzt daraus
nur `kredit_id`, `typ`, `zeilen[].{kategorie_id,neutral}` — siehe „Wunsch an das
Gerüst" zur Herleitung der Ratekategorie.

### `GET /api/belege?sparte_id=<sparte>`

```json
[{"id": 1, "dateiname": "beispiel.pdf", "sparte_id": 1, "belegdatum": null, "betrag_erkannt_cent": null, "sha256_hash": "…"}]
```

Für die optionale Beleg-Auswahl im „Jahr bestätigen"-Dialog genutzt (bestehender
Endpunkt aus `app/routers/belege.py`, kein Upload gebaut, siehe „Wunsch an das
Gerüst").

## Wunsch an das Gerüst / Scope-Entscheidungen

1. **`GET /api/kredite` liefert `kategorie_zins_id`/`kategorie_rate_id` nicht mit**
   (`_listeintrag` in `app/routers/kredite.py` gibt nur `id, name, sparte_id,
   monatsrate_cent, beginn, jahre` zurück). Für „Bestehende Buchungen zuordnen"
   braucht die Seite aber genau diese Kategorie, um passende Buchungen zu finden.
   Da dieses Paket den Router laut Karte nicht ändern darf, leitet `kredit.js` die
   Kategorie stattdessen aus einer bereits zugeordneten Rate desselben Kredits ab
   (aus der ohnehin geladenen `/api/buchungen`-Antwort: `buchungszeile` mit
   `neutral=1` der ersten Buchung mit `kredit_id === k.id`). **Hat ein Kredit noch
   keine einzige Rate** (weder erfasst noch zugeordnet), bleibt die Kategorie
   unbekannt und die Zuordnen-Liste bleibt in diesem Fall leer, auch wenn passende
   Buchungen existieren — ein echter, im Bericht offen benannter Randfall.
   Empfehlung: `_listeintrag` um `kategorie_zins_id`/`kategorie_rate_id` ergänzen
   (kleine, rückwärtskompatible Backend-Änderung außerhalb dieses Scopes).
2. **`GET /api/buchungen` setzt ohne `von`/`bis`/`jahr` automatisch das aktuelle
   Stichtagsjahr** (`app/rechenbasis.py`, `auswertungsfilter`). Für „Bestehende
   Buchungen zuordnen" würden dadurch unzugeordnete Raten aus Vorjahren
   stillschweigend fehlen. `kredit.js` umgeht das, indem es explizit `von: k.beginn,
   bis: <heute>` mitschickt. Kein Backend-Wunsch, nur hier dokumentiert, weil es beim
   Testen tatsächlich zu einer leeren Liste geführt hat, bevor die Ursache gefunden war.
3. **Beleg-Hochladen** wurde nicht gebaut: die Karte sieht im „Jahr
   bestätigen"-Dialog nur das *Verknüpfen* eines *bereits hochgeladenen* Belegs vor
   („optional einen bereits hochgeladenen Beleg verknüpfen"). Der Dialog bietet daher
   eine Auswahl aus `GET /api/belege?sparte_id=` an; ein Upload-Button wurde nicht
   ergänzt, da die Karte ihn an dieser Stelle nicht verlangt und der bestehende
   Upload-Endpunkt (`POST /api/belege`, `app/routers/belege.py`) eher zur
   Beleg-Erfassung (P43) gehört.

## Getroffene Frontend-Entscheidungen

- Ohne gewählte Sparte (`state.sparteId === ''`, „Alle Sparten") zeigt die Seite die
  Kredite aller Sparten des Bereichs, statt eine Sparte zu erzwingen — die Karte
  verlangt „Liste der Kredite der aktuell gewählten Sparte", lässt den Fall „keine
  Sparte gewählt" aber offen; das Anlegen-Formular hat trotzdem immer ein
  Sparten-Feld.
- Jede Kredit-Karte ist ein Akkordeon: Klick auf den Kopf oder eine Jahres-Pille
  öffnet den Detailbereich (Ratentabelle, Zuordnen) für das gewählte Jahr; nur ein
  Kredit ist gleichzeitig geöffnet, um die Seite bei vielen Krediten übersichtlich zu
  halten (im Prototyp nicht exakt vorgegeben).
- „Jahr bestätigen" schließt den Dialog nach dem Speichern **nicht** automatisch,
  sondern deaktiviert das Formular und zeigt Ergebnis/Abweichungen dauerhaft an
  (analog zum bestehenden Anker-Dialog aus `konten.js`) — Abweichungen dürfen laut
  Karte nicht verschluckt werden, ein Auto-Close hätte sie sofort wieder verdeckt.
- Beträge folgen dem Vorbild aus `konten.js`/`buchungen.js`: `parseBetrag`/`fmtEur`
  aus `format.js`, keine eigene Rundung.

## Tests

Neue Datei `tests/test_p52_kredit.py`, isoliert grün (6 Tests):

```
test_jahr_bestaetigen_mit_11_statt_12_raten_zeigt_abweichung ... ok
test_kredit_anlegen_liefert_felder_die_die_seite_liest ... ok
test_ratenliste_liefert_zins_und_tilgung_getrennt ... ok
test_route_ist_in_app_js_registriert ... ok
test_seite_und_modul_werden_ausgeliefert ... ok
test_zuordnen_verknuepft_bestehende_buchung_mit_dem_kredit ... ok

Ran 6 tests in 16.211s

OK
```

`node --check static-neu/pages/kredit.js` und `node --check static-neu/app.js`:
beide fehlerfrei.

Gesamtsuite (`unittest discover -s tests`, `FINANZ_DB` auf Wegwerf-Datei, ohne
`FINANZ_TEST_AUTH_BYPASS`): **376 Tests, OK, 1 übersprungen** (835,5 s). Die Karte
erwartet „367 + eigene Tests, 1 skipped" (= 373); der aktuelle Stand von `neubau` in
diesem Worktree enthält bereits einige Tests aus anderen, zwischenzeitlich gemergten
Paketen, daher 376 statt 373 — alle grün, keiner davon durch P52 verursacht. Während
des Laufs geloggte `PIL.UnidentifiedImageError`-Tracebacks stammen aus bestehenden
Beleg-Miniaturbild-Tests (`app/auswertung.py`, Fallback-Pfad „Bild-Verkleinerung
fehlgeschlagen - sende Original") und sind vorbestehendes, von diesem Paket
unverändertes Verhalten, kein Fehlschlag. Vollständige Ausgabe in
`docs/neubau/berichte/P52-tests.txt`.

## Browserprüfung

App gestartet: `uvicorn app.main:app --port 8036`, `FINANZ_DB=%TEMP%\p52-app.db`,
`FINANZ_INSTANZ=test`, `FINANZ_AUTH_FILE=%TEMP%\p52-auth.json`,
`FINANZ_TEST_AUTH_BYPASS=1` (laut `app/auth.py` nur für DBs unter dem Temp-Ordner
erlaubt). Playwright-Tools standen in dieser Sitzung zur Verfügung und wurden für
eine echte Bedienung genutzt (nicht nur `curl`):

1. Testdaten per API angelegt: Bankkonto „Testbank" (Sparte 1), zwei Kategorien
   („Kreditzinsen", „Kredittilgung"), Kredit „Testkredit Hof" (Monatsrate € 500,
   Zinssatz 3,5 %, Beginn 1.1.2025), elf Raten für 2025 (bewusst nur 11 statt 12,
   um die Abweichung zu provozieren).
2. `/neu/#/kredit` geladen: Kredit-Karte erscheint mit Monatsrate/Beginn/Zinssatz,
   Jahres-Pillen 2026 (geschätzt) und 2025 (zunächst noch nicht bestätigt).
3. Jahr 2025 bestätigt (Zins € 1.100, Restschuld € 45.000): Ratentabelle zeigt elf
   Zeilen mit Zins € 100,00 / Tilgung € 400,00 je Rate (110000 Cent gleichmäßig auf
   elf Raten verteilt), Pille zeigt danach „bestätigt · Zins € 1.100,00 · Rest
   € 45.000,00".
4. Jahr 2025 erneut bestätigt (Zins € 1.100, Restschuld € 44.500): Dialog zeigt nach
   dem Speichern dauerhaft „11 Rate(n), € 1.100,00 Zins verteilt." und die Warnung
   „11 Raten im Jahr 2025 statt 12" — Formular wird deaktiviert, Dialog bleibt offen,
   Toast „Jahr bestätigt, mit Abweichung."
5. Über die API eine zwölfte, bislang nicht zugeordnete Ausgabe-Buchung mit der
   Kategorie „Kredittilgung" angelegt („Nachgetragene Kreditrate", € 500,
   5.12.2025). Nach Neuladen erscheint sie unter „Bestehende Buchungen zuordnen";
   ausgewählt und „Zuordnen" geklickt → Toast „1 Buchung(en) zugeordnet.", die
   Ratentabelle zeigt die Buchung danach als zwölfte Zeile (Zins € 0,00, Tilgung
   € 500,00, bestätigt), die Zuordnen-Liste ist leer.
6. „Rate erfassen" für das laufende Jahr 2026 geöffnet: Datum und Betrag (€ 500,00)
   vorbelegt, gespeichert → Toast „Rate erfasst.", Jahres-Pille zeigt danach
   „geschätzt · Zins € 1.099,92", Ratentabelle zeigt die neue Zeile mit geschätztem
   Zins-/Tilgungsanteil (€ 91,66 / € 408,34).
7. Leerzustand geprüft: Sparte „Zimmervermietung Hof" (ohne Kredit) gewählt → Karte
   zeigt „Kein Kredit erfasst." mit dem Inline-Anlegen-Formular; zwei neue
   Kategorien angelegt, Formular ausgefüllt und „Kredit anlegen" geklickt → Toast
   „Kredit angelegt.", Liste zeigt danach die neue Kredit-Karte mit Jahres-Pille
   2026 (geschätzt).
8. Mobile Ansicht (375×812): Sidebar wird durch die Bottom-Navigation ersetzt
   (Kredit hat dort laut Karte keinen eigenen Eintrag), Kredit-Karten, Jahres-Kopf
   und Tabellen brechen einspaltig um, `.table-wrap` sorgt für horizontales Scrollen
   der Ratentabelle statt Layout-Bruch.
9. Konsole: keine Fehler außer dem erwarteten `favicon.ico`-404 (kein Favicon im
   Projekt, betrifft alle Seiten gleichermaßen, nicht Teil dieses Pakets).

**Dabei einen echten Bug gefunden und behoben** (siehe „Wunsch an das Gerüst" Punkt 1
und 2): Beide Probleme (fehlende Kategorie-Felder in `/api/kredite`, implizites
Jahresfenster in `/api/buchungen`) wurden erst im Browserlauf sichtbar — „Bestehende
Buchungen zuordnen" zeigte zunächst trotz passender, existierender Buchung „Keine
passenden Buchungen …" an. Beide Ursachen wurden identifiziert und im Frontend ohne
Backend-Änderung umgangen (siehe Code-Kommentare in `kredit.js` bei
`ladeZuordnenKandidaten`).

## Offene Punkte

1. **Kategorie-Herleitung für „Zuordnen" schlägt fehl, solange ein Kredit noch keine
   einzige Rate hat** (siehe „Wunsch an das Gerüst" Punkt 1). Betrifft nur den
   Moment direkt nach dem Anlegen eines Kredits, bevor die erste Rate erfasst oder
   zugeordnet wurde; danach funktioniert die Herleitung zuverlässig. Kopf entscheidet,
   ob `_listeintrag` um die beiden Kategorie-Felder ergänzt wird.
2. Kein Upload für Belege direkt aus dem „Jahr bestätigen"-Dialog (siehe „Wunsch an
   das Gerüst" Punkt 3) — nur Verknüpfung bereits vorhandener Belege, wie von der
   Karte verlangt.
3. Die Seite erzwingt keine Sparten-Auswahl; bei „Alle Sparten" werden alle Kredite
   des Bereichs in einer Liste gezeigt (Entscheidung, siehe oben) statt eines
   Hinweises „bitte Sparte wählen".
4. Kein automatischer Refresh der Jahres-Pillen anderer, nicht geöffneter Kredit-
   Karten nach einer Aktion an einem Kredit — jede Aktion lädt aber die komplette
   Kreditliste neu (`reload()`), betrifft also nur die (ohnehin aus derselben
   Antwort gebauten) Pillen, kein Datenrisiko.
5. Kein Node-basierter DOM-Test für `kredit.js` (Projektkonvention: `node --check`
   für Syntax, echte Interaktion über Playwright/Browser) — die Interaktion wurde
   ausschließlich im Browserlauf geprüft, wie in P50 vorgemacht.

## Fertig-Kriterien aus der Karte

- [x] Syntaxprüfung (`node --check`) grün, eigene Tests grün (6/6), Ausgabe im Bericht.
- [x] Gesamtsuite grün — 376 Tests, OK, 1 übersprungen (siehe oben).
- [x] Kredit anlegen, Jahr bestätigen (inkl. Abweichung), Rate erfassen, Zuordnen
      einmal im Browser gegen eine Wegwerf-Datenbank mit einem P14-Kredit-Seed
      durchgespielt — Schritte oben dokumentiert.
- [x] Keine Geheimnisse, keine echten Namen, keine neuen Abhängigkeiten, kein
      Build-Schritt.
- [x] Bericht geschrieben.
