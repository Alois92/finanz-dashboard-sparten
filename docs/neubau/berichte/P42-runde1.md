# P42 – Runde 1

Stand: 10. September 2026. Arbeitsverzeichnis `C:\Users\lblet\dev\wt-p42`,
Zweig `pkt/p42-bankimport-zuordnung`.

## Zusammenfassung

Backend fuer P42 war bereits vollstaendig vorhanden: `app/routers/import_bank.py`
enthaelt `import_csv`, `list_bankumsaetze`, `verbuche_umsatz`,
`uebernehme_vorschlaege`, `setze_umsatzstatus` unveraendert seit P11/P15, und
die vier Abgleich-Endpunkte aus F-N4 (`GET .../kandidaten`, `POST .../zuordnen`,
`POST .../zuordnung-loesen`, `GET /api/konten/{id}/offene-abgleiche`) sind
bereits in `app/abgleich.py` und den vorhandenen Routern verdrahtet (siehe
`docs/neubau/berichte/N4-runde1.md`). Der urspruengliche Vertrag der Karte
(`POST /api/bankumsaetze/{id}/abgleichen`, `abgleich_vorschlaege` in der
CSV-Antwort) existiert **nicht** im heutigen Code und wurde wie im Nachtrag
vorgegeben durch den N4-Vertrag ersetzt. Damit war fuer dieses Paket **keine
Backend-Aenderung noetig** – die Konfliktregel des Nachtrags ("nur
`static-neu/pages/bankimport.js` sowie neue `bankimport*.css`/`bankimport-*.js`")
wurde eingehalten, es gab schlicht keinen Grund, davon abzuweichen.

Gebaut wurde die vollstaendige Bankimport-Seite: Konten-Uebersicht (lesend),
CSV-Upload mit Pruefbericht, eine "Zusammenfuehren?"-Liste auf Basis von
`GET /api/konten/{id}/offene-abgleiche` + `GET .../kandidaten` (ersetzt den
veralteten `abgleich_vorschlaege`-Ansatz der Karte), und die Umsaetze-Tabelle
mit allen vier Zustaenden (automatisch/Vorschlag/offen/verbucht/ignoriert)
inkl. Sammeluebernahme.

## Geaenderte und neue Dateien

- `static-neu/pages/bankimport.js` (ersetzt) – vollstaendiges Seitenmodul: Konten-Karte, Upload mit Pruefbericht und Zusammenfuehren-Liste, Umsaetze-Tabelle mit Formular, Kandidaten-Dialog, Sammeluebernahme.
- `static-neu/pages/bankimport.css` (neu) – Kontokarten, Statusbadges, Drop-Zone, Zusammenfuehren-Zeilen, Formular- und Kandidaten-Styles, eigene Mobil-Anpassung.
- `tests/test_p42_bankimport.py` (neu) – 8 Tests gegen die echte ASGI-Anwendung: statische Auslieferung, `node --check`, Konten-/Kategorien-Felder, CSV-Upload mit Fixture, Verbuchen/Ignorieren, N4-Abgleich (Kandidaten/Zuordnen/Loesen), Sammeluebernahme.
- `docs/neubau/berichte/P42-record.py` (neu, Arbeitsdatei wie `N4-testlauf.py`) – zeichnet die woertlichen Antworten unten auf; kein Teil der Testsuite.
- `docs/neubau/berichte/P42-record-output.md` (neu, Arbeitsdatei) – Rohausgabe des obigen Skripts.
- `docs/neubau/berichte/P42-runde1.md`, `docs/neubau/berichte/P42-tests.txt` (dieser Bericht).

Keine neuen `.csv`-Testfixtures: die Tests verwenden die bereits vorhandene
`tests/fixtures/george_2025_auszug.csv`.

Nicht angefasst: `app/routers/import_bank.py`, `app/abgleich.py`, `app/regeln.py`,
`app/rechenbasis.py`, `db/schema.sql`, `app.js`, `api.js`, `ui.js`, `format.js`,
`charts.js`, `style.css`, `index.html`, `static-studio/`, bestehende Testdateien.
Keine Migration.

## Entwurfsentscheidungen (kein Backend-Zugriff moeglich)

1. **"Zusammenfuehren?"-Liste beim Upload:** Der urspruengliche Kartenvertrag
   wollte `abgleich_vorschlaege` direkt in der Antwort von `POST /api/import/csv`.
   Dieses Feld existiert nicht mehr. Stattdessen ruft die Seite nach jedem
   erfolgreichen Upload `GET /api/konten/{id}/offene-abgleiche` fuer das
   hochgeladene Konto ab und laedt fuer jeden offenen Umsatz mit Kandidaten
   zusaetzlich `GET .../kandidaten`. Das zeigt alle offenen Zusammenfuehr-Kandidaten
   des Kontos, nicht nur die aus dem letzten Batch – im Ergebnis identisch
   fuer den Nutzer (alles, was zusammengefuehrt werden kann, wird angezeigt),
   aber technisch nicht auf den gerade importierten Batch beschraenkt.
2. **Status "Umbuchung" fuer verbuchte Umsaetze nicht unterscheidbar:**
   `GET /api/bankumsaetze` liefert fuer `importstatus='verbucht'` weder den
   `typ` der zugehoerigen Buchung noch die Regel-Herkunft (`vorschlag` wird
   laut Router-Code nur fuer `importstatus='offen'` befuellt). Die Karte wollte
   verbuchte Umbuchungen als eigenen Badge "Umbuchung" zeigen und automatisch
   verbuchte Umsaetze an `regel_id`-Herkunft erkennen. Beides ist mit den
   vorhandenen Feldern nicht moeglich, ohne fuer jede Zeile zusaetzlich die
   Buchungsliste zu laden (nicht vorgesehen, da `GET /api/buchungen` nicht nach
   `bankumsatz_id` filterbar ist). Entscheidung: alle `verbucht`-Umsaetze
   bekommen einheitlich den Badge "verbucht"; die Aktion "oeffnen" zeigt die
   verfuegbaren Umsatzfelder (Datum, Text, Betrag) und verweist auf die
   Buchungsliste fuer Details. Siehe "Wunsch an das Geruest".
3. **"Zuordnung loesen" bei per `/verbuchen` erzeugten Buchungen liefert 409:**
   laut `N4-runde1.md` hat eine ueber `/verbuchen` neu erzeugte Buchung keine
   manuelle Ruecknahmereferenz; der Loesen-Endpunkt lehnt sie mit 409 ab. Die
   Seite bietet den Knopf trotzdem bei jedem `verbucht`-Umsatz an (da nicht
   unterscheidbar, ob er per `/verbuchen` oder per `/zuordnen` entstand) und
   zeigt einen 409 wie jeden anderen Serverfehler als Toast – kein stilles
   Scheitern, aber ein Knopf, der in einem Teil der Faelle einen erwarteten
   Fehler produziert.
4. **"wieder oeffnen" fuer ignorierte Umsaetze:** von der Karte nicht verlangt,
   aber ohne diese Aktion waere Ignorieren eine Einbahnstrasse. Nutzt den
   vorhandenen `PATCH /api/bankumsaetze/{id}` mit `importstatus:'offen'`
   (laut Endpunkt-Doku ausdruecklich erlaubt), kein neuer Endpunkt noetig.
5. **Sparten- und Kategorienamen:** `state.sparten` aus dem globalen Zustand
   (von `app.js` bereits geladen) wird wiederverwendet; Kategorien werden
   einmalig bereichsweit über `GET /api/kategorien?nur_aktive=true` geladen
   und im Formular clientseitig nach `sparte_id` gefiltert.

## Verwendete Endpunkte mit woertlichem Antwort-JSON

Aufgezeichnet mit `docs/neubau/berichte/P42-record.py` (ASGI-Requesthelfer wie
`tests/test_bereiche.py`, da `httpx`/`TestClient` im Projekt-venv fehlt – siehe
"Wunsch an das Geruest" Punkt 3) auf einer Wegwerf-Datenbank.

### GET /api/konten

```json
[{"id": 1, "name": "Testbank", "art": "bank", "waehrung": "EUR", "sparte_id": 1, "iban": null, "bank": null, "kartenendnummer": null, "aktiv": 1, "sortierung": 0, "stand_cent": null, "datenstand": "unbekannt", "letzter_import": null}]
```

### POST /api/import/csv (erster Import)

```json
{"batch_id": 1, "neu": 2, "dubletten": 0, "gesamt": 2, "saldo_ok": null, "saldo_hinweis": "Keine Saldospalte vorhanden.", "erkannt": {"kodierung": "utf-8", "trennzeichen": ";", "spalten": {"datum": 0, "betrag": 1, "text": 2, "gegenpartei": 3, "iban": null, "waehrung": null, "saldo": null}, "zeilen_gesamt": 2, "zeilen_ungueltig": []}}
```

### POST /api/import/csv (Dublette, gleiche Datei erneut)

```json
{"batch_id": 2, "neu": 0, "dubletten": 2, "gesamt": 2, "saldo_ok": null, "saldo_hinweis": "Keine Saldospalte vorhanden.", "erkannt": {"kodierung": "utf-8", "trennzeichen": ";", "spalten": {"datum": 0, "betrag": 1, "text": 2, "gegenpartei": 3, "iban": null, "waehrung": null, "saldo": null}, "zeilen_gesamt": 2, "zeilen_ungueltig": []}}
```

### GET /api/bankumsaetze?bankkonto_id=1 (beide offen, kein Vorschlag)

```json
[{"id": 2, "bankkonto_id": 1, "import_batch_id": 1, "datum": "2026-03-02", "valuta": null, "betrag_cent": 25000, "saldo_nachher_cent": null, "text": "Gehalt Maerz", "gegenpartei": "Arbeitgeber GmbH", "iban_gegenpartei": null, "importstatus": "offen", "vorschlag": null}, {"id": 1, "bankkonto_id": 1, "import_batch_id": 1, "datum": "2026-03-01", "valuta": null, "betrag_cent": -12345, "saldo_nachher_cent": null, "text": "Einkauf Supermarkt", "gegenpartei": "Handelskette AG", "iban_gegenpartei": null, "importstatus": "offen", "vorschlag": null}]
```

### POST /api/bankumsaetze/1/verbuchen

```json
{"buchung_id": 1, "typ": "ausgabe", "betrag_cent": 12345, "regel_angelegt": true}
```

### PATCH /api/bankumsaetze/2 ({"importstatus":"ignoriert"})

```json
{"id": 2, "importstatus": "ignoriert"}
```

### GET /api/bankumsaetze?bankkonto_id=1 (nach Verbuchen/Ignorieren – kein "vorschlag"-Feld mehr bei nicht-offenen Umsaetzen)

```json
[{"id": 3, "bankkonto_id": 1, "import_batch_id": 3, "datum": "2026-04-03", "valuta": null, "betrag_cent": -500, "saldo_nachher_cent": null, "text": "Bereits erfasste Zahlung", "gegenpartei": null, "iban_gegenpartei": null, "importstatus": "offen", "vorschlag": null}, {"id": 2, "bankkonto_id": 1, "import_batch_id": 1, "datum": "2026-03-02", "valuta": null, "betrag_cent": 25000, "saldo_nachher_cent": null, "text": "Gehalt Maerz", "gegenpartei": "Arbeitgeber GmbH", "iban_gegenpartei": null, "importstatus": "ignoriert"}, {"id": 1, "bankkonto_id": 1, "import_batch_id": 1, "datum": "2026-03-01", "valuta": null, "betrag_cent": -12345, "saldo_nachher_cent": null, "text": "Einkauf Supermarkt", "gegenpartei": "Handelskette AG", "iban_gegenpartei": null, "importstatus": "verbucht"}]
```

### GET /api/bankumsaetze/3/kandidaten

```json
{"kandidaten": [{"buchung_id": 2, "datum": "2026-04-02", "betrag_cent": -500, "text": "Manuell erfasst", "abstand_tage": 1}]}
```

### GET /api/konten/1/offene-abgleiche

```json
{"konto_id": 1, "manuelle_anzahl": 1, "manuelle_bewegungen": [{"bewegung_id": 3, "datum": "2026-04-02", "betrag_cent": -500, "text": "Manuell erfasst"}], "umsaetze_anzahl": 1, "offene_umsaetze": [{"bankumsatz_id": 3, "datum": "2026-04-03", "betrag_cent": -500, "text": "Bereits erfasste Zahlung", "kandidaten_anzahl": 1}]}
```

### POST /api/bankumsaetze/3/zuordnen ({"buchung_id":2})

```json
{"bankumsatz_id": 3, "buchung_id": 2, "importstatus": "verbucht"}
```

### POST /api/bankumsaetze/3/zuordnung-loesen

```json
{"bankumsatz_id": 3, "buchung_id": null, "importstatus": "offen"}
```

Weitere im Modul verwendete, unveraenderte Endpunkte ohne eigenen Aufzeichnungslauf
hier: `GET /api/kategorien?nur_aktive=true` (Felder `id,sparte_id,parent_id,name,
richtung,sortierung,aktiv`, siehe `app/routers/stammdaten.py`),
`POST /api/bankumsaetze/vorschlaege-uebernehmen` (Antwort `{"verbucht":n,
"uebersprungen":n}`, siehe Test `test_sammeluebernahme_von_regelvorschlaegen`).

## Tests

Vollstaendige Ausgabe in `docs/neubau/berichte/P42-tests.txt`.

- `tests/test_p42_bankimport.py` isoliert: **8 Tests, OK** (`FINANZ_DB` auf
  Wegwerf-Datei unter `%TEMP%`, `discover -s tests -p test_p42_bankimport.py`).
- Gesamtsuite `discover -s tests` (`FINANZ_DB` auf eine neue Wegwerf-Datei
  unter `%TEMP%`): **306 Tests, OK (skipped=1)**, Laufzeit 8 m 45 s, Exitcode 0.
  Davon sind 8 die neuen P42-Tests, 298 bereits bestehende Tests dieses
  Arbeitsbaums (dieser Worktree teilt den Stand `neubau` nach P11/P15/P30/N4;
  parallele Pakete wie P31/P40/P41/P50/P60 laufen in eigenen Worktrees und sind
  hier nicht enthalten). Die im Rohlog sichtbaren Tracebacks (`Sicherung vor
  Nachzug ist nicht intakt`, `Bild-Verkleinerung fehlgeschlagen`, `Keine
  bestehende Auth-Datei ...`) sind erwartete Ausgaben bestehender
  Negativtests (Backup-, Bild- und Recovery-Fehlerpfade), keine Fehlschlaege –
  die Suite endet mit `OK (skipped=1)`. Der eine Skip ist der bekannte
  `test_store_setzt_dateimodus_0600` (POSIX-Dateirechte, unter Windows nicht
  anwendbar, siehe `N4-runde1.md`).
- `node --check static-neu/pages/bankimport.js`: **bestanden** (auch als
  Testfall `test_node_check_js_dateien` in der Suite, ueberspringt sich selbst
  falls `node` fehlt).

## App gestartet und per curl geprueft

`uvicorn app.main:app --port 8142` mit `FINANZ_TEST_AUTH_BYPASS=1` und
`FINANZ_DB` auf eine Wegwerf-Datei unter `%TEMP%`:

```
GET /neu/                         -> 200
GET /neu/pages/bankimport.js      -> 200
GET /neu/pages/bankimport.css     -> 200
GET /api/schema                   -> {"aktuell":14,"anstehend":[],"schreibgeschuetzt":false,"fehler":null,"instanz":"prod"}
```

Server danach beendet (Prozess auf Port 8142 gestoppt, `curl` bestaetigt
`000`/nicht erreichbar).

## Im Browser geprueft / nicht geprueft

Playwright bzw. ein interaktiver Browser standen in dieser Sandbox nicht zur
Verfuegung (kein MCP-Browserzugriff auf `localhost`-Server dieses Worktrees in
der aktuellen Session). Stattdessen wurde die App unter Port 8142 gestartet
und die Startseite sowie das Modul per `curl` gegen echte HTTP-Antworten
geprueft (siehe unten). Die interaktiven Ablaeufe (Datei per Drag&Drop hochladen,
Formular ausfuellen und speichern, "Zusammenfuehren" klicken, Konsole auf
Fehler pruefen) konnten **nicht** im echten Browser nachvollzogen werden; sie
sind stattdessen durch `tests/test_p42_bankimport.py` gegen die echten
Endpunkte abgedeckt, die das Modul aufruft (gleiche Anfragen, gleiche
Antwortformen wie im Browser), aber ohne DOM-Ereignisse (Klick, Formular-Submit)
selbst auszuloesen.

## Wunsch an das Geruest

1. `GET /api/bankumsaetze` liefert fuer `importstatus='verbucht'` weder `typ`
   noch die Regel-Herkunft der Buchung. Ohne das kann die Seite "automatisch
   verbucht" (Regelherkunft `gelernt`+`auto_verbuchen=1`) nicht von "manuell
   verbucht" und "Umbuchung" nicht vom normalen Fall unterscheiden, wie es die
   Karte in Abschnitt 3 beschreibt. Ein optionales `buchung_typ`-Feld (oder ein
   Join gegen `buchung.typ` bei `importstatus='verbucht'`) wuerde das loesen.
2. `GET /api/buchungen` filtert nicht nach `bankumsatz_id`; ohne das kann eine
   Seite zu einem verbuchten Umsatz nicht guenstig die zugehoerige Buchung fuer
   eine Detailansicht nachladen.
3. Im Projekt-`.venv` fehlt `httpx`, wodurch `fastapi.testclient.TestClient`
   (wie in der Aufgabenstellung verlangt) nicht nutzbar ist. Alle bestehenden
   Testdateien (inkl. `test_bereiche.py`, `test_abgleich.py`) umgehen das mit
   einem handgeschriebenen ASGI-Requesthelfer. Dieser Bericht und
   `tests/test_p42_bankimport.py` folgen demselben Muster. Ein `httpx`-Eintrag
   in den Dev-Dependencies wuerde kuenftigen Paketen die vorgeschriebene
   Testclient-Aufzeichnung ohne Umweg ermoeglichen (waere eine neue Abhaengigkeit
   – hier nur als Vorschlag, nicht installiert).

## Offene Punkte

- Kein echter Browsertest moeglich (siehe oben); die visuelle Handy-Ansicht
  (Karten stapeln, Tabellen scrollen horizontal) ist nur durch die CSS-Regeln
  selbst und die bestehenden `@media(max-width:760px)`-Konventionen aus
  `style.css` abgesichert, nicht durch einen Sichttest.
- Status "Umbuchung" fuer verbuchte Umsaetze wird nicht separat angezeigt
  (siehe Entwurfsentscheidung 2 / Wunsch an das Geruest 1) – Grund: fehlendes
  Feld in der vorhandenen API, keine Backend-Aenderung im Scope dieses Pakets.
- "Zuordnung loesen" kann bei per `/verbuchen` entstandenen Buchungen 409
  liefern (siehe Entwurfsentscheidung 3) – das ist die vom Backend
  dokumentierte, gewollte Grenze (siehe `N4-runde1.md`), keine offene
  Baustelle dieses Pakets.
- `docs/neubau/berichte/P42-record.py` und `P42-record-output.md` sind
  Arbeitsdateien (wie `N4-testlauf.py`), keine Testdatei im eigentlichen Sinn;
  bleiben zur Nachvollziehbarkeit der Aufzeichnung im Bericht liegen.

## Fertig heisst

- [x] Alle Tests gruen, vollstaendige Ausgabe in `docs/neubau/berichte/P42-tests.txt`
  (isoliert 8/8, Gesamtsuite 306 Tests OK, skipped=1).
- [x] Keine neue Migration – `db/schema.sql` unveraendert (Backend insgesamt
  nicht angefasst).
- [x] Kein Playwright-Ergebnis, Grund oben genannt.
- [x] Kein toter Code, keine neue Abhaengigkeit, keine Abschwaechung von Validierung.
- [x] Keine Geheimnisse, keine echten Namen im Code (Testdaten sind synthetisch).
- [x] Bericht geschrieben.
