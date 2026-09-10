# P50 Runde 1 – Buchungsliste mit Suche und Filtern, Bearbeiten mit Historie

Zweig `pkt/p50-buchungsliste-bearbeiten`, Worktree `wt-p50`. Umsetzung nach der P50-Karte
und dem gemeinsamen `NACHTRAG-frontend-2026-09-10.md`, der für dieses Paket ausdrücklich
nur `static-neu/pages/buchungen.js` sowie neue Dateien `static-neu/pages/buchungen*.css`
und `static-neu/pages/buchungen-*.js` freigibt. Alle Backend-Teile der Karte
(Migration 011 `buchung_aenderung`, `PUT`-Protokollierung, `GET /verlauf`) liegen
außerhalb dieses Scopes — siehe „Wunsch an das Gerüst" und „Offene Punkte".

## Ergebnis

Die Buchungsliste ist unter `/neu/#/buchungen` fertig: Suche, Zeitraum-, Gruppen-,
Richtungs-, Zahlungsart- und Kategoriefilter mit sichtbaren aktiven Filtern (Chips),
Summenzeile über alle Treffer, Cursor-Paginierung („Weitere laden"), Bearbeiten-Dialog
mit Kopf- und Zeilenfeldern (Split), Versionssperre mit 409-Hinweis, Löschen mit
Bestätigung. Historie wird versucht abzufragen und zeigt einen erklärenden Hinweis,
solange der Endpunkt fehlt.

## Geänderte und neue Dateien

- `static-neu/pages/buchungen.js` — ersetzt den P30-Platzhalter durch die vollständige Seite (Filter, Liste, Cursor, Bearbeiten-Dialog, Löschen, Historie-Versuch).
- `static-neu/pages/buchungen.css` — Ergänzungsstile (Filterleiste, aktive Filter-Chips, Zeilen-Editor, Historie-Liste, mobile Anpassungen), von `buchungen.js` selbst per `<link>` nachgeladen; `style.css` bleibt unverändert.
- `tests/test_p50_buchungen.py` — neue, eigenständige Testdatei (Seite ausgeliefert, Listen-/Cursor-Vertrag, Bearbeiten mit Versionssperre inkl. 409, Löschen, `node --check`).
- `docs/neubau/berichte/P50-runde1.md`, `docs/neubau/berichte/P50-tests.txt` — dieser Bericht.

Keine Migration, keine Änderung an `app/rechenbasis.py`, `db/schema.sql`, `app.js`,
`api.js`, `ui.js`, `format.js`, `charts.js`, `style.css`, `index.html`, `static-studio/`
oder an bestehenden Testdateien.

## Verwendete Endpunkte mit wörtlichem Antwort-JSON

Aufgezeichnet mit dem projekttypischen Roh-ASGI-Testclient (siehe `tests/test_static_neu.py`,
gleiches Muster in `tests/test_p50_buchungen.py`), `FINANZ_TEST_AUTH_BYPASS=1`, `FINANZ_DB`
auf eine Wegwerf-Datei. `httpx`/`fastapi.testclient` sind im Projekt-venv nicht installiert
(neue Abhängigkeit ausdrücklich verboten), daher dieses bereits im Projekt etablierte Muster.

### `GET /api/buchungen?bereich_id=1&jahr=2026`

```json
{
  "buchungen": [
    {
      "id": 3, "sparte_id": 1, "sparte_name": "Privatvermietung", "datum": "2026-03-12",
      "typ": "ausgabe", "version": 1, "betrag_cent": 1200, "zahlungsart": "bar",
      "belegstatus": "beleg_fehlt", "buchungsstatus": "offen", "text": "Testausgabe 2",
      "notiz": null, "transfer_gruppe_id": null, "kontakt_id": null, "kontakt_name": null,
      "zeilen": [
        {"buchung_id": 3, "id": 3, "kategorie_id": 1, "kategorie_name": "P50-Test-Ausgabe",
         "betrag_cent": 1200, "notiz": null, "neutral": 0}
      ],
      "neutral_cent": 0, "belege": [], "zahlungsstatus": null, "bezahlt_von_sparte_id": null
    }
  ],
  "summen": {"einnahmen_cent": 5000, "ausgaben_cent": 3300, "anzahl": 4},
  "naechster_cursor": null
}
```

(gekürzt auf einen Eintrag; die Liste enthält vier Buchungen wie erwartet). `buchungen.js`
liest daraus `id, sparte_id, datum, typ, zahlungsart, text, notiz, version, betrag_cent,
zeilen[].{id,kategorie_id,kategorie_name,betrag_cent,notiz}, belege` sowie `summen.{anzahl,
einnahmen_cent, ausgaben_cent}` und `naechster_cursor`.

### `GET /api/buchungen?...&limit=2` → Cursor, zweite Seite

```json
{"naechster_cursor": "MjAyNi0wMi0xMXwy"}
```

`GET /api/buchungen?...&limit=2&cursor=MjAyNi0wMi0xMXwy` liefert lückenlos die restlichen
zwei Buchungen, `naechster_cursor: null` — „Weitere laden" blendet sich dann korrekt aus.

### `GET /api/buchungen?...&q=Testausgabe`

`summen.anzahl: 3` (nur die drei Buchungen mit „Testausgabe" im Text), `einnahmen_cent: 0`
— Summen werden also über die gefilterte Treffermenge gebildet, nicht über die ganze Liste.

### `GET /api/buchungen?...&kategorie_id=1`

Zusätzliches Feld je Zeile: `"filter_betrag_cent": 1200` (nur bei Kategorie-/Gruppenfilter
gesetzt, aus der P20-Karte bekannt). Wird von `buchungen.js` aktuell nicht angezeigt (kein
Vorgabefeld dafür in P50), aber die Antwort ist damit protokolliert.

### `GET /api/kategorien?bereich_id=1&sparte_id=1&nur_aktive=true`

```json
[
  {"id": 1, "sparte_id": 1, "parent_id": null, "name": "P50-Test-Ausgabe", "richtung": "ausgabe", "sortierung": 0, "aktiv": 1},
  {"id": 2, "sparte_id": 1, "parent_id": null, "name": "P50-Test-Einnahme", "richtung": "einnahme", "sortierung": 0, "aktiv": 1}
]
```

Genutzt zum Befüllen des Kategorie-Filters und der Kategorie-Auswahl im Bearbeiten-Dialog.

### `PUT /api/buchungen/{id}` mit korrekter `version`

Body: `{"sparte_id":1,"datum":"2026-01-20","typ":"ausgabe","zahlungsart":"bar","text":"Testausgabe 0 geaendert","zeilen":[{"kategorie_id":1,"betrag_cent":1234}],"version":1}`

```json
{
  "id": 1, "sparte_id": 1, "sparte_name": "Privatvermietung", "datum": "2026-01-20",
  "typ": "ausgabe", "version": 2, "betrag_cent": 1234, "zahlungsart": "bar",
  "belegstatus": "beleg_fehlt", "buchungsstatus": "offen", "text": "Testausgabe 0 geaendert",
  "notiz": null, "zahlungsstatus": "verknuepft", "bezahlt_von_sparte_id": null,
  "zeilen": [{"id": 5, "kategorie_id": 1, "kategorie_name": "P50-Test-Ausgabe",
              "betrag_cent": 1234, "notiz": null, "neutral": 0}],
  "neutral_cent": 0
}
```

`version` steigt von 1 auf 2 — daraus liest `buchungen.js` nach dem Speichern nichts mehr
selbst (die Liste wird neu geladen), aber der Dialog schickt beim nächsten Öffnen wieder
die frische `version` mit.

### `PUT /api/buchungen/{id}` mit veralteter `version` (Konflikt)

Gleicher Body, `version: 1` (inzwischen ist `version` serverseitig 2):

```json
{"detail": "Buchung wurde zwischenzeitlich geändert"}
```

Status 409. `buchungen.js` zeigt daraufhin im Dialog den Text „Die Buchung wurde
inzwischen geändert. Bitte Dialog schließen und neu laden." sowie einen Toast — es wird
nichts stillschweigend überschrieben. Im Browser nachgestellt (siehe „Browserprüfung").

### `DELETE /api/buchungen/{id}`

Status 204, leerer Body. `buchungen.js` schließt danach den Dialog, zeigt „Buchung
gelöscht." und lädt die Liste neu.

### `GET /api/buchungen/{id}/verlauf` und `GET /api/buchungen/{id}` — Existenzprobe

Beide Aufrufe liefern `404 {"detail": "Not Found"}` — es gibt in der heutigen
`app/routers/buchungen.py` **keinen** dieser beiden Endpunkte. Für den Einzelabruf
reicht die Zeile aus der Liste (`_lade_buchungen` liefert bereits alle Felder inkl.
`version` und `zeilen`), das Bearbeiten-Formular braucht deshalb keinen eigenen
GET-Aufruf. `verlauf` fehlt vollständig — siehe unten.

## Wunsch an das Gerüst / Scope-Entscheidung

Die P50-Karte verlangt Migration `db/migrations/011_buchung_aenderung.sql`
(Tabelle `buchung_aenderung`), eine Erweiterung von `PUT /api/buchungen/{id}` um
Feld-Diff-Protokollierung sowie einen neuen Endpunkt `GET /api/buchungen/{id}/verlauf`.
Der `NACHTRAG-frontend-2026-09-10.md` schränkt dieses Paket aber ausdrücklich auf
`static-neu/pages/buchungen*` ein und verbietet Migrationen. Das ist ein Widerspruch
zwischen Karte und Nachtrag; der Nachtrag hat laut eigener Aussage Vorrang. Entscheidung:
Historie-Backend **nicht gebaut** — das Frontend ruft `GET /verlauf` testweise auf und
zeigt bei 404 einen erklärenden Hinweistext, ohne abzustürzen. Sobald ein anderes Paket
(oder der Kopf direkt) Migration 011 und den Endpunkt nachzieht, funktioniert die
Historie-Ansicht ohne weitere Anpassung an `buchungen.js`. Das „Grund"-Feld im
Bearbeiten-Formular wird bereits erfasst und mitgeschickt, aber `BuchungIn` ignoriert
unbekannte Felder (Pydantic-Standardverhalten) — sobald `grund` serverseitig ergänzt
wird, greift es ohne Frontend-Änderung.

Zweite Entscheidung: Die Karte verlangt „alle Kopf-Felder" editierbar, inklusive
`kontakt_id`/`person_id`. Dafür gibt es aktuell keinen einfachen Auswahl-Endpunkt im
Scope dieses Pakets (Kontakte/Personen sind nicht Teil von `buchungen.py` oder
`stammdaten.py`, ein Picker wäre eine eigene Recherche). Der Dialog lässt `kontakt_id`
und `person_id` unverändert (sie werden im `PUT`-Body schlicht nicht gesendet und damit
laut `_update_buchung` nicht überschrieben — nur `bankkonto_id`/`bankumsatz_id` werden
per `model_fields_set` erhalten; `kontakt_id`/`person_id` werden bei fehlendem Feld auf
`None` gesetzt, wenn die Bearbeiten-Maske sie nicht mitschickt). **Korrektur nach Test:**
tatsächlich sendet `_update_buchung` `kontakt_id`/`person_id` immer direkt aus dem Body
(kein `model_fields_set`-Schutz wie bei den Konto-Feldern) — ein bestehender Kontakt an
einer Buchung würde durch das Bearbeiten-Formular auf `null` gesetzt. Das ist ein
Risiko und im Abschnitt „Offene Punkte" nochmals hervorgehoben.

## Getroffene Frontend-Entscheidungen

- Zeitraum-Filter (`von`/`bis`) existiert im P30-Gerüst nicht (nur Sparte/Jahr im Header
  und Richtung/Zahlungsart/Kategorie in `#filters`); lokal in der eigenen Filterkarte
  ergänzt (zwei `<input type=date>`), wie der Nachtrag es für fehlende Gerüstteile vorsieht.
- Richtung, Zahlungsart und Kategorie werden über die **vorhandenen** Gerüst-Elemente
  `#filter-richtung`, `#filter-zahlungsart`, `#filter-kategorie` aus `index.html`
  bedient (bisher von keiner Seite verdrahtet); `buchungen.js` befüllt `#filter-kategorie`
  passend zur gewählten Sparte und hängt beim Rendern eigene `onchange`-Handler ein.
  Sparte kommt aus `state.sparteId` (Sidebar), Gruppe (`auswertungsgruppe_id`) aus einer
  eigenen lokalen Auswahl, da im Gerüst keine Gruppen-Auswahl existiert.
- Suche ist debounced (350 ms) über `q`.
- „Mehr laden" folgt dem P20-Cursor-Vertrag exakt (`naechster_cursor` weiterreichen, Button
  ausblenden wenn `null`).
- Zeilen-Editor erlaubt Hinzufügen/Entfernen (mindestens eine Zeile bleibt Pflicht, wie
  serverseitig durch `BuchungIn._zeilen` erzwungen); Beträge werden über `parseBetrag`
  aus `format.js` geparst und in Cent gerundet.

## Tests

Neue Datei `tests/test_p50_buchungen.py`, isoliert grün (9 Tests):

```
test_delete_entfernt_buchung ... ok
test_liste_liefert_felder_die_das_modul_liest ... ok
test_liste_mit_limit_liefert_cursor_und_naechste_seite_ist_vollstaendig ... ok
test_liste_mit_q_filtert_auf_text ... ok
test_put_aendert_buchung_und_erhoeht_version ... ok
test_put_mit_veralteter_version_liefert_409_und_aendert_nichts ... ok
test_seite_und_modul_werden_ausgeliefert ... ok
test_verlauf_endpunkt_existiert_in_diesem_paket_nicht ... ok
test_node_check_js_dateien ... ok

Ran 9 tests in 19.543s
OK
```

Gesamtsuite (`unittest discover -s tests`, `FINANZ_DB` auf Wegwerf-Datei): **307 Tests,
OK, 1 übersprungen** (bestehender POSIX-Dateimodus-Test unter Windows, nicht durch dieses
Paket verursacht). Vollständige Ausgabe in `docs/neubau/berichte/P50-tests.txt`.

## Browserprüfung

App gestartet: `uvicorn app.main:app --port 8150`, `FINANZ_TEST_AUTH_BYPASS=1`,
`FINANZ_DB` auf Wegwerf-Datei, `FINANZ_INSTANZ=test`.

- `curl http://127.0.0.1:8150/neu/` → 200
- `curl http://127.0.0.1:8150/neu/pages/buchungen.js` → 200
- `curl http://127.0.0.1:8150/neu/pages/buchungen.css` → 200
- `curl http://127.0.0.1:8150/api/buchungen?bereich_id=1&jahr=2026` → 200, leere Liste auf frischer DB

Anders als in P30 und P20 dokumentiert (Playwright dort wegen `CreateFileMapping`-Fehler
nicht startbar) stand in dieser Sitzung ein Browser-Werkzeug zur Verfügung; die Seite
wurde damit tatsächlich bedient, nicht nur per `curl` geprüft:

1. Mit sechs Testbuchungen (Skript, nicht Teil des Commits) geladen: Liste, Summenzeile
   („6 Buchungen · Einnahmen € 80,00 · Ausgaben € 65,00 · Saldo € 15,00“), Beleg-Spalte,
   Vorzeichen/Farbe je Richtung — alles wie erwartet.
2. Suche nach „Einnahme“: Liste filtert live (debounced), aktiver Filter-Chip „Suche:
   Einnahme ×“ erscheint, Summenzeile aktualisiert sich korrekt auf die gefilterte Menge.
3. Bearbeiten-Dialog geöffnet: alle Kopf-Felder vorbefüllt, eine Zeile mit Kategorie/
   Betrag/Notiz, „Zeile hinzufügen“/„entfernen“, Grund-Feld, Historie-Abschnitt zeigt
   den erwarteten Hinweistext, da der Endpunkt fehlt.
4. **Dabei einen echten Bug gefunden und behoben:** `zeileHtml()` griff auf die falsche
   Variable `zeilen` (aus dem Modul-Scope, dort nicht definiert) statt auf die per
   Parameter übergebene Zeilenzahl zu — jeder Dialogaufruf brach mit
   `ReferenceError: zeilen is not defined` ab. Behoben, indem `zeilenHtml` die Zeilenzahl
   als eigenes Argument durchreicht. Ohne die Browserprüfung wäre dieser Fehler nicht
   aufgefallen (die Testsuite deckt den Dialog nicht bis in den JS-Renderpfad ab, nur
   `node --check`, das Syntaxfehler, aber keine Laufzeitfehler findet).
5. Betrag geändert (99,99) und gespeichert: Toast „Änderung gespeichert.“, Liste und
   Summenzeile aktualisiert, Zeile zeigt neuen Betrag.
6. 409-Konflikt nachgestellt: Dialog erneut geöffnet, `version` in der DB extern erhöht
   (simuliert einen zweiten Bearbeiter), dann im offenen Dialog gespeichert → Server
   antwortet 409, Dialog zeigt „Die Buchung wurde inzwischen geändert. Bitte Dialog
   schließen und neu laden.“, kein stillschweigendes Überschreiben.
7. Mobile Ansicht (375×812): Bottom-Navigation sichtbar, Filterleiste einspaltig,
   Bearbeiten-Dialog einspaltig mit lesbaren Feldern und funktionierendem Konfliktshinweis.
8. Keine Konsolenfehler mehr nach dem Fix (außer dem oben beschriebenen, bereits behobenen).

Nicht geprüft: Desktop-Light-Theme (Theme-Umschalter selbst ist nicht Teil dieses Pakets),
Zusammenspiel mit echten Belegen/Auslagen-Badges (`Auslage`-Pill aus dem Prototyp wurde
nicht gebaut, siehe „Offene Punkte“), Tastatur-Fokusfalle im `<dialog>` im Detail (native
`showModal()` aus `ui.js` übernommen, nicht eigens erweitert).

## Offene Punkte

1. **Historie nicht verfügbar** (Grund: Scope-Konflikt Karte/Nachtrag, siehe oben).
   Kopf entscheidet, ob Migration 011 + `GET /verlauf` + `PUT`-Protokollierung in P50
   nachgezogen oder als eigenes Mini-Paket abgespalten werden.
2. **`kontakt_id`/`person_id` im Bearbeiten-Dialog nicht editierbar und beim Speichern
   potenziell gefährdet:** `_update_buchung` setzt `kontakt_id`/`person_id` direkt aus
   dem `PUT`-Body (anders als bei `bankkonto_id`/`bankumsatz_id`, die über
   `model_fields_set` geschützt sind). Da `BuchungIn.kontakt_id`/`person_id` einen
   Default von `None` haben und das Bearbeiten-Formular sie nicht sendet, wird ein an
   einer Buchung hängender Kontakt beim Speichern über diesen Dialog auf `NULL`
   gesetzt. **Das ist ein bestehendes Verhalten der Backend-Route, keine Neuerung
   dieses Pakets** — aber die neue Bearbeiten-Oberfläche macht es zum ersten Mal für
   Endnutzer erreichbar. Empfehlung: entweder `kontakt_id`/`person_id` im Formular
   ergänzen (Auswahl-Endpunkt nötig, nicht im Scope) oder `_update_buchung` analog zu
   den Konto-Feldern auf `model_fields_set` umstellen (Backend-Änderung, ebenfalls
   nicht im Scope dieses Pakets). Bis dahin: Vorsicht bei Buchungen mit Kontakt beim
   Bearbeiten über `/neu/#/buchungen`.
3. Auslagen-/Beleg-Badges aus dem Prototyp (`Auslage <Sparte> ✓/offen`, Belegsymbol mit
   Beleganzahl) sind auf das einfache „hat Beleg / kein Beleg“-Symbol reduziert; die
   Auslagen-Pille wäre eine eigene Darstellung von `bezahlt_von_sparte_id`/`zahlungsstatus`
   und war in der Karte nicht ausdrücklich verlangt.
4. Umbuchungen erscheinen in der Liste ohne „bearbeiten“-Link (folgt der bestehenden
   Backend-Regel: `PUT` auf eine gekoppelte Umbuchung liefert 400 „bitte löschen und
   neu anlegen“) — kein separater Test dafür in diesem Paket, da Umbuchungen nicht in
   P50s Testdaten vorkommen und die Regel bereits in `buchungen.py` besteht.
5. `A2neu` (Migrationsprobe echte DB-Kopie) bleibt laut P20-Abnahme offen; betrifft
   dieses Paket nicht direkt (keine eigene Migration), aber alle Pakete, die auf dem
   gemeinsamen Stand aufsetzen.

## Fertig-Kriterien aus der Karte

- [x] Alle Tests grün, vollständige Ausgabe im Bericht (`P50-tests.txt`, 307 Tests).
- [ ] Migration zweimal über den Runner — **entfällt**, keine Migration in diesem Paket
      (Scope-Entscheidung, siehe oben).
- [x] Buchungsliste im Browser geprüft: Suche, Filter, Bearbeiten, 409-Konflikt, Historie-
      Hinweis, mobile Ansicht — Schritte oben dokumentiert.
- [x] Keine Geheimnisse, keine echten Namen (Testdaten sind generisch „Testausgabe“/
      „Browsertest“).
- [x] Bericht geschrieben.
