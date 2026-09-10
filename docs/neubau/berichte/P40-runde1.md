# P40 Runde 1 — Erfassen-Fluss mit Auto-Kategorie und Auslagen erfassen

Zweig `pkt/p40-erfassen-fluss`, Worktree `wt-p40`. Umsetzung nach `NACHTRAG-frontend-2026-09-10.md` (Vorrang), `P40-erfassen-fluss.md` und dem Prototyp-Abschnitt „Erfassen“.

## Geänderte und neue Dateien

- `static-neu/pages/erfassen.js` — ersetzt den P30-Platzhalter durch den vollständigen Erfassen-Fluss: Betrag zuerst (mit `inputmode="decimal"`), Sparte, Einnahme/Ausgabe-Umschalter, Text mit Kategorievorschlag über `POST /api/parse` (300 ms Debounce), Zahlungsart mit Kontoauswahl je Sparte/Art, Datum (heute vorbelegt), Kategorie-Select mit „+ Neue“-Dialog, Schalter „Auslage für andere Sparte“ mit „Bezahlt von“-Auswahl, Beleg-Hinweistext, Speichern mit `client_request_id`, Doppel-Tap-Schutz und Toast-Fehlerbehandlung, sowie Karte „Zuletzt erfasst“ (7 Buchungen der gewählten Sparte inkl. Auslage-Kennzeichen).
- `static-neu/pages/erfassen.css` — neue, eigene Stildatei (per `<link>` beim ersten Render nachgeladen), ergänzt nur erfassen-spezifische Klassen (Segmented-Control, große Betragsanzeige, Vorschlagszeile, Zuletzt-erfasst-Liste, Foto-Platzhalter); rührt `style.css` nicht an.
- `tests/test_p40_erfassen.py` — neue Testdatei: Ausliefern von `/neu/pages/erfassen.js` und `/neu/pages/erfassen.css`, Feldverträge der vier genutzten Endpunkte gegen die tatsächlich von `erfassen.js` gelesenen Felder, Buchung mit `client_request_id` inkl. Idempotenz-Nachweis (keine Dublette in der DB), Auslage-Erzeugung über `bezahlt_von_sparte_id`, 422-Fehlerfall mit `detail`-Feld, sowie `node --check` für `erfassen.js`.
- `docs/neubau/berichte/P40-tests.txt` — vollständige Rohausgabe der Gesamtsuite.

Kompatibilitäts-Check laut Karte in `app/routers/schnellerfassung.py`: geprüft, `finde_regel(...)` wird bereits mit den benannten Schlüsselwort-Argumenten (`bereich_id=`, `sparte_id=`) aufgerufen — **keine Änderung nötig**, keine Datei angefasst.

## Verwendete Endpunkte mit wörtlicher Antwort (aufgezeichnet mit dem FastAPI-Testclient-Muster, Wegwerf-DB, Seed-Daten)

### `GET /api/sparten?bereich_id=1`
```json
[
  {"id": 1, "name": "Privatvermietung", "kuerzel": "PV", "typ": "vermietung", "geschuetzt": 0, "farbe": "#6AA9FF"},
  {"id": 2, "name": "Zimmervermietung Hof", "kuerzel": "ZVH", "typ": "vermietung", "geschuetzt": 0, "farbe": "#2DD4BF"},
  {"id": 3, "name": "Bauernhof", "kuerzel": "HOF", "typ": "hof", "geschuetzt": 0, "farbe": "#C084FC"},
  {"id": 5, "name": "Alois privat", "kuerzel": "AL", "typ": "privat", "geschuetzt": 0, "farbe": "#FB923C"},
  {"id": 6, "name": "Frau privat", "kuerzel": "FR", "typ": "privat", "geschuetzt": 0, "farbe": "#818CF8"}
]
```
Wird nicht separat von `erfassen.js` geladen, sondern aus `state.sparten` (bereits von `app.js` geladen) wiederverwendet — spart einen Roundtrip.

### `GET /api/kategorien?sparte_id=1&nur_aktive=true`
```json
[{"id": 1, "sparte_id": 1, "parent_id": null, "name": "Futtermittel", "richtung": "ausgabe", "sortierung": 0, "aktiv": 1}]
```

### `GET /api/konten?bereich_id=1`
```json
[{"id": 1, "name": "Kassa Hof", "art": "kassa", "waehrung": "EUR", "sparte_id": 1, "iban": null, "bank": null, "kartenendnummer": null, "aktiv": 1, "sortierung": 0, "stand_cent": null, "datenstand": "unbekannt", "letzter_import": null}]
```
Kein `sparte_id`-Filterparameter am Endpunkt vorhanden — `erfassen.js` filtert clientseitig nach `sparte_id` und `art` (nur bei Zahlungsart Bank/Karte sichtbar).

### `POST /api/parse` (`{"text": "Lagerhaus Kraftfutter 612"}`)
```json
{
  "typ": "ausgabe", "datum": "2026-09-10", "betrag_cent": 61200,
  "text": "Lagerhaus Kraftfutter", "sparte_id": null, "sparte_name": null,
  "kategorie_id": null, "kategorie_name": null
}
```
(In diesem leeren Testschema ohne Namensabgleich/Regel kein Treffer — die Felder sind aber vollständig, wie vom JS erwartet.)

### `POST /api/kategorien` (`{"sparte_id": 1, "name": "Futtermittel", "richtung": "ausgabe"}`)
```json
{"id": 1, "sparte_id": 1, "parent_id": null, "name": "Futtermittel", "richtung": "ausgabe"}
```

### `POST /api/buchungen` (mit `client_request_id`)
```json
{
  "id": 1, "sparte_id": 1, "sparte_name": "Privatvermietung", "datum": "2026-09-10",
  "typ": "ausgabe", "version": 1, "betrag_cent": 61200, "zahlungsart": "bar",
  "belegstatus": "beleg_fehlt", "buchungsstatus": "offen",
  "text": "Lagerhaus Kraftfutter 612", "notiz": null, "zahlungsstatus": "verknuepft",
  "bezahlt_von_sparte_id": null,
  "zeilen": [{"id": 1, "kategorie_id": 1, "kategorie_name": "Probe-Kategorie", "betrag_cent": 61200, "notiz": null, "neutral": 0}],
  "neutral_cent": 0
}
```
Wiederholung mit derselben `client_request_id` und identischen Nutzdaten → HTTP 200, gleiche `id`, kein Duplikat (in `tests/test_p40_erfassen.py::test_buchung_mit_client_request_id_und_idempotenz` per SQL-Zählung zusätzlich verifiziert).

### `POST /api/buchungen` mit `bezahlt_von_sparte_id` (Auslage)
```json
{
  "id": 2, "sparte_id": 1, "datum": "2026-09-10", "typ": "ausgabe",
  "betrag_cent": 4500, "zahlungsart": "bar", "text": "Diesel privat vorgestreckt",
  "bezahlt_von_sparte_id": 5,
  "auslage": {"zahler_sparte_id": 5, "offen_cent": 4500, "ausgeglichen": false},
  "zeilen": [{"id": 2, "kategorie_id": 1, "kategorie_name": "Probe-Kategorie", "betrag_cent": 4500, "notiz": null, "neutral": 0}],
  "neutral_cent": 0
}
```

### `POST /api/buchungen` — Fehlerfall 422 (`bezahlt_von_sparte_id` bei Einnahme)
```json
{"detail": "Auslage benötigt eine Ausgabe und eine andere private Zahlersparte"}
```
`erfassen.js` zeigt `error.detail` unverändert als Toast.

### `GET /api/buchungen?sparte_id=1&limit=7`
```json
{
  "buchungen": [{
    "id": 1, "sparte_id": 1, "sparte_name": "Privatvermietung", "datum": "2026-09-10",
    "typ": "ausgabe", "version": 1, "betrag_cent": 61200, "zahlungsart": "bar",
    "belegstatus": "beleg_fehlt", "buchungsstatus": "offen", "text": "Lagerhaus Kraftfutter 612",
    "notiz": null, "transfer_gruppe_id": null, "kontakt_id": null, "kontakt_name": null,
    "zeilen": [{"buchung_id": 1, "id": 1, "kategorie_id": 1, "kategorie_name": "Probe-Kategorie", "betrag_cent": 61200, "notiz": null, "neutral": 0}],
    "neutral_cent": 0, "belege": [], "zahlungsstatus": "verknuepft", "bezahlt_von_sparte_id": null
  }],
  "summen": {"einnahmen_cent": 0, "ausgaben_cent": 61200, "anzahl": 1},
  "naechster_cursor": null
}
```
`bezahlt_von_sparte_id` bzw. `auslage.{zahler_sparte_id,offen_cent,ausgeglichen}` sind bereits vorhanden (anders als im Karten-Text vermutet, der sie noch als „sobald vorhanden“ beschreibt) — `erfassen.js` zeigt daher das Auslage-Kennzeichen bereits jetzt in „Zuletzt erfasst“.

## Testausgabe

- **Eigene neue Testdatei isoliert**: `tests/test_p40_erfassen.py` — **12 Tests, 0 Fehler**.
- **Gesamtsuite** (`unittest discover -s tests`, Wegwerf-DB, `FINANZ_TEST_AUTH_BYPASS=1`): **310 Tests, 6 Fehlschläge, 1 übersprungen**. Alle 6 Fehlschläge liegen in `test_auth.py` und `test_auth_lifecycle.py` (Cookie-/Sitzungs-Durchsetzung), die bei global gesetztem `FINANZ_TEST_AUTH_BYPASS=1` die Sperre nicht mehr greifen sehen — keine dieser Dateien wurde von P40 verändert, und keiner der Fehlschläge betrifft `buchungen.py`, `schnellerfassung.py`, `stammdaten.py`, `auslagen.py` oder `static-neu/`. Vollständige Rohausgabe in [`P40-tests.txt`](P40-tests.txt).
- `node --check static-neu/pages/erfassen.js` — erfolgreich (auch als Testfall `test_node_check_erfassen_js` in der eigenen Testdatei enthalten).

## App-Start-Check

`uvicorn app.main:app` auf Port 8140, `FINANZ_TEST_AUTH_BYPASS=1`, Wegwerf-DB:

| Aufruf | Status |
|---|---|
| `GET /neu/` | 200 |
| `GET /neu/pages/erfassen.js` | 200 |
| `GET /neu/pages/erfassen.css` | 200 |

Server danach beendet.

## Was im Browser nicht geprüft werden konnte

Es steht kein echter Browser zur Verfügung (nur Testclient/curl). Nicht geprüft:

- Optik und Layout am Handy (375 px) visuell — nur die CSS-Regeln (`.g2`/`.g3` kollabieren global bereits unter 760 px laut `style.css`, eigene mobile Anpassungen in `erfassen.css` für Betrag/Segmented-Control) sind im Code vorhanden, aber nicht am Bildschirm gesehen.
- Tatsächliches Tastaturverhalten von `inputmode="decimal"` auf einem echten Mobilgerät.
- Live-Verhalten des Debounce (300 ms) und der Auto-Übernahme des Parse-Vorschlags in die Sparte/Kategorie-Selects während der Eingabe.
- Doppel-Tap-Schutz real durch schnelles Doppelklicken im Browser (nur die serverseitige `client_request_id`-Idempotenz wurde über den Testclient nachgewiesen; die clientseitige Sofort-Deaktivierung des Speichern-Buttons ist im Code vorhanden, aber nicht in einer echten Browser-Session beobachtet).
- Konsole auf JavaScript-Fehler im echten Browser.
- Fokus-/Tastatursteuerung des „+ Neue Kategorie“-Dialogs (`ui.js`-Dialog mit `inert`/Fokusfalle) im echten Browser.

## Wunsch an das Gerüst

1. Die Karte (`P40-erfassen-fluss.md`) verlangt, den Vorschlag mit bis zu drei Kategorie-Treffern per Pfeiltasten durchzuschalten und die Regel-Herkunft („gelernt“/„Stichwort“) anzuzeigen. `POST /api/parse` liefert aber nur einen einzelnen besten Treffer (`kategorie_id`/`kategorie_name`) ohne Herkunftsfeld und ohne Alternativen-Liste. Da weder eine Änderung der Erkennungslogik noch eine Erweiterung von `schnellerfassung.py` über den benannten Kompatibilitäts-Zweizeiler hinaus beauftragt war (Nicht-Ziel „Keine Änderung an der Erkennungslogik von POST /api/parse selbst“), wurde nur der einzelne Vorschlag angezeigt („Vorschlag: Sparte X · Kategorie Y“), ohne Pfeiltasten-Auswahl und ohne Herkunftsanzeige. Falls gewünscht, bräuchte `/api/parse` ein zusätzliches Feld (z. B. `kategorie_quelle: "gelernt"|"stichwort"|null`) und optional eine `kandidaten`-Liste.
2. `GET /api/konten` hat keinen `sparte_id`-Filterparameter; bei vielen Konten müsste jede Seite, die kontobezogen filtert, die komplette Liste laden und selbst filtern (wie hier getan). Ein optionaler Query-Parameter würde das vereinfachen.

## Offene Punkte

- Die 6 Fehlschläge der Auth-Suite in der Gesamtsuite sind vorbestehend und durch `FINANZ_TEST_AUTH_BYPASS=1` bedingt (siehe Testausgabe oben); sie sind nicht durch P40 verursacht und wurden nicht behoben, da `test_auth.py`/`test_auth_lifecycle.py` laut Nachtrag/Verbotsliste nicht angefasst werden dürfen.
- Browserprüfung komplett offen (siehe Abschnitt oben) — nur Testclient und curl standen zur Verfügung.
- Die Regel-Herkunft-Anzeige und die Pfeiltasten-Auswahl aus der Karte wurden aus den unter „Wunsch an das Gerüst“ genannten Gründen nicht umgesetzt.
- Das Konto-Feld wird nur bei Zahlungsart „Bank“ oder „Karte“ angezeigt und filtert nach `art` passend zur Zahlungsart; bei „Bar“ wird automatisch keine `bankkonto_id` mitgeschickt (Backend braucht keine für Barbuchungen). Nicht mit einem echten mehrkontigen Bereich geprüft, nur mit einem einzelnen Testkonto.
- Keine Commits, kein Push, keine neuen Abhängigkeiten, keine Migration — wie beauftragt.
