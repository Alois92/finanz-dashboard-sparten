# P40: Erfassen-Fluss mit Auto-Kategorie und Auslagen erfassen

Meilenstein M4. Branch `pkt/p40-erfassen-fluss` von `neubau` (nach P12, P15, P30).

## 1. Ziel

Die Erfassen-Seite aus dem Gerüst (P30) bekommt echten Inhalt: ein Satz reicht, Bar ist die Vorgabe-Zahlungsart, Sparte und Kategorie werden aus dem Text vorgeschlagen, Details lassen sich aufklappen, und eine privat bezahlte Ausgabe für eine andere Sparte wird über „Bezahlt von" als Auslage markiert. Ein Doppel-Tap erzeugt nie zwei Buchungen.

## 2. Kontext

Lies `docs/neubau/ARCHITEKTUR.md` Abschnitt 3, 4, 5, 7 und 11, dann `docs/neubau/pakete/P12-auslagen-ausgleich.md` (`bezahlt_von_sparte_id`, `client_request_id`, `version`), `docs/neubau/pakete/P15-kategorien-regeln-kennzahlen.md` (Regel-Herkunft, Stichwörter sind nur Vorschläge), `docs/neubau/pakete/P30-frontend-geruest.md` (Router, Zustand, `api.js`, `ui.js`, `format.js`), `app/routers/schnellerfassung.py` (bestehender regelbasierter Parser unter `POST /api/parse` — wird wiederverwendet, nicht ersetzt), `app/routers/buchungen.py` (`POST`/`PUT /api/buchungen`), `docs/neubau/prototyp/prototyp.html` Abschnitt „Erfassen" (Zeilen ~571–656, Klasse `.quick`, `.form`, `.photo`, `.recent`) für Wortlaut und Verhalten. Fachliche Vorgabe des Nutzers: Bar ist die Vorgabe beim Erfassen; eine privat bezahlte Ausgabe bleibt bei der Sparte, der die Kosten gehören, und erzeugt eine Forderung des Zahlers; Stichwörter sind Vorschläge, keine automatische Verbuchung.

## 3. Schnittstellen

Kein neuer Endpoint. Genutzt werden ausschließlich vorhandene: `POST /api/parse` (Schnelltext → Vorschlag inkl. `sparte_id`/`kategorie_id`/`typ`/`betrag_cent`/`text`), `POST /api/kategorien` (neue Kategorie inline), `POST /api/buchungen` (Feld `zahlungsart` Standard `'bar'`, `bezahlt_von_sparte_id` optional, `client_request_id` aus `api.js`), `GET /api/buchungen?sparte_id=&limit=7` (Zuletzt erfasst), `GET /api/sparten`, `GET /api/kategorien?sparte_id=`.

`static-neu/pages/erfassen.js` (ersetzt den P30-Platzhalter):

- Karte „Erfassen": Textfeld, Enter speichert direkt, wenn Sparte, Kategorie und Betrag erkannt sind (kein Zwischenschritt nötig); Debounce 300 ms auf `POST /api/parse`; Vorschlagszeile mit bis zu drei Kategorie-Treffern, Pfeiltasten ↑↓ wechseln die Auswahl (wie im Prototyp). Zeigt die Regel-Herkunft, falls der Vorschlag aus einer Regel stammt (`„gelernt"`/`„Stichwort"`), damit klar bleibt: ein Stichwort ist ein Vorschlag, keine automatische Verbuchung.
- „Details anpassen ▾" klappt das Formular auf: Sparte (aus `localStorage state.quickSparte` gemerkt, sonst zuletzt verwendete), Datum (Standard heute), Richtung, Zahlungsart (Select mit Vorgabe `'bar'`), Kategorie (+ „Neue"-Dialog → `POST /api/kategorien`), Betrag (`parseBetrag` aus `format.js`), „Bezahlt von" (Select, nur sichtbar bei Richtung „Ausgabe"; Optionen = aktive Sparten mit `typ='privat'` des aktuellen Bereichs, ungleich der gewählten Sparte; Hinweistext wörtlich aus dem Prototyp: „Privat bezahlt für eine andere Sparte? Dann steht es unter „Offene Auslagen" und kommt per Ausgleich zurück. Die Kosten bleiben bei der Sparte.").
- Speichern-Button wird sofort nach Klick deaktiviert, bis die Antwort da ist (Doppel-Tap-Schutz zusätzlich zur serverseitigen `client_request_id`-Deduplizierung aus P12); bei 409 wegen unterschiedlicher Nutzdaten unter demselben Schlüssel: Toast „Wird gerade anders gespeichert — Seite neu laden."; bei 422 (z. B. `bezahlt_von_sparte_id` bei Einnahme) den `detail`-Text aus der Antwort als Toast zeigen.
- Karte „Zuletzt erfasst": letzte 7 Buchungen der gewählten Sparte, inkl. Auslage-Kennzeichen (`auslage.zahler_sparte_id`/`ausgeglichen` aus der P20-Buchungsliste, sobald das Feld dort vorhanden ist — bis dahin ohne Kennzeichen, kein Fehler).
- Karte „Rechnung fotografieren": In diesem Paket nur ein Platzhalter-Knopf, der bei Klick den Hinweis „Kommt mit der Foto-Übernahme" zeigt (gleiches Muster wie die P30-Platzhalterseiten), damit P43 den Knopf später mit echtem Verhalten füllen kann, ohne das Erfassen-Formular anzufassen.
- Mobil (< 760 px): identisches Verhalten, kompaktes Layout wie im Prototyp beschrieben; die Bottom-Navigation mit dem Plus in der Mitte (aus P30) führt hierher und ist der Handy-Startpunkt.

Kompatibilitäts-Check in `app/routers/schnellerfassung.py`: prüfen, ob der Aufruf von `finde_regel(...)` noch die alte Positions-Signatur `(con, text, bereich_id)` nutzt. Hat P15 die Signatur auf `finde_regel(con, text, *, sparte_id=None, konto_id=None, bereich_id=1)` umgestellt, hier auf Keyword-Argumente nachziehen (reiner Zweizeiler, kein Verhaltenswechsel — die Parser-Logik selbst bleibt unverändert).

## 4. Nicht-Ziele

Kein Foto-Upload und keine Foto-Auswertung (P43). Keine Ausgleich-Logik oder Konten-Verwaltung (P41). Kein neuer Server-Endpoint. Keine Änderung an der Erkennungslogik von `POST /api/parse` selbst oder an `app/regeln.py`.

## 5. Schritte

1. `pages/erfassen.js` Grundgerüst mit Zustand (`state.quickSparte`, `state.manualKat`) analog Prototyp.
2. Schnelltext-Fluss mit Debounce, Vorschlagszeile, Tastatursteuerung, Direkt-Speichern.
3. Detailformular inkl. „Bezahlt von" und „+ Neue Kategorie".
4. Speichern inkl. `client_request_id`, Doppel-Tap-Schutz, Fehlerbehandlung 409/422.
5. „Zuletzt erfasst", Foto-Platzhalter, Kompatibilitäts-Check in `schnellerfassung.py`.
6. Tests, Browserprüfung, Bericht.

## 6. Tests

Testinterpreter `C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Scripts\python.exe`, `FINANZ_DB` auf eine Wegwerf-Datenbank unter `C:\Users\lblet\AppData\Local\Temp` (nie die echte Datenbank), Tests über `tempfile.TemporaryDirectory()`, schreiben nie in den Arbeitsbaum.

- `node --check static-neu/pages/erfassen.js` (und jede weitere geänderte `static-neu`-Datei).
- Backend-Regression in `tests/test_schnellerfassung.py` bzw. `tests/test_buchungen.py`: `POST /api/buchungen` ohne `zahlungsart` → `'bar'`; `POST /api/parse` liefert weiterhin 200 und respektiert `bereich_id`.
- Browserprüfung (Playwright, falls in der Sandbox verfügbar, sonst ausdrücklich vermerken statt stillschweigend auszulassen): Text eingeben → Vorschlag erscheint, Enter speichert, Buchung erscheint in „Zuletzt erfasst"; Detailformular zeigt „Bezahlt von" nur bei Richtung „Ausgabe"; doppeltes schnelles Klicken auf Speichern erzeugt über das Netzwerk-Log nur eine Buchung; Konsole ohne Fehler; 375 px zeigt das kompakte Layout.

## 7. Fertig heißt

- [ ] Tests grün, vollständige Ausgabe im Bericht.
- [ ] Bereichsdependency nur an fachlichen Endpunkten (hier: keine neuen Endpunkte, daher nichts zu prüfen außer der bestehenden Nutzung).
- [ ] Playwright-Ergebnis im Bericht oder ausdrücklicher Grund, warum nicht möglich.
- [ ] Kein toter Code, keine neue Abhängigkeit, keine externen Netzaufrufe im Frontend.
- [ ] Keine Geheimnisse, keine echten Namen im Code.
- [ ] Bericht geschrieben.

## 8. Modell und Aufwand

Modell: `gpt-5.6-luna`, Aufwand medium.

## 9. Bericht zurück

Geänderte und neue Dateien mit je einem Satz. Testausgabe. Was im Browser geprüft wurde oder nicht geprüft werden konnte, mit Grund. Offene Punkte. Keine Commits, kein Push.
