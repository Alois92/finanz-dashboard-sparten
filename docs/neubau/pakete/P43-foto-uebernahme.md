# P43: Foto-Übernahme in eine Buchung

Meilenstein M4. Branch `pkt/p43-foto-uebernahme` von `neubau` (nach P12, P30; kleiner Eingriff in `pages/erfassen.js` aus P40).

## 1. Ziel

Ein fotografierter Beleg wird lokal von Ollama ausgewertet (nie mit Cloud-KI). Der Nutzer sieht das Ergebnis, korrigiert bei Bedarf Sparte, Kategorie, Beträge und Datum je Position und übernimmt es mit einem Klick als Buchung — bei mehreren Positionen als eine Buchung mit mehreren Buchungszeilen (Split) — inklusive verknüpftem Beleg.

## 2. Kontext

Lies `docs/neubau/ARCHITEKTUR.md` Abschnitt 4, 7 und 11, dann die bereits produktiv laufenden Module vollständig, aber **ohne sie zu ändern**: `app/auswertung.py` (`_auswerten`, `_parse_ergebnis`, `_brutto_abgleich`, `_kategorie_fuer_position`, Hintergrundschleife, `OLLAMA_MODEL`/`OLLAMA_URL`), `app/routers/beleg_auswertung.py` (Auftrag anlegen/auflisten/Status setzen), `app/routers/belege.py` (Upload, Download, Verknüpfung `buchung_beleg`). Dann `docs/neubau/pakete/P12-auslagen-ausgleich.md` (`bezahlt_von_sparte_id`, `client_request_id`), `docs/neubau/pakete/P30-frontend-geruest.md`, `docs/neubau/pakete/P40-erfassen-fluss.md` (Platzhalter-Knopf „Rechnung fotografieren", der hier mit Verhalten gefüllt wird), `app/routers/buchungen.py` (`create_buchung`, insbesondere ob die Erstell-Logik als wiederverwendbare Funktion vorliegt oder nur im Endpoint steckt). Vorlage für Wortlaut: `docs/neubau/prototyp/prototyp.html`, Abschnitte „Rechnung fotografieren" (Zeilen ~613–620) und „Belege" (Zeilen ~698–704, `renderBelege` Zeilen ~1755–1759). Fachliche Vorgabe des Nutzers: Rechnungsfotos werden ausschließlich lokal mit Ollama ausgewertet, unter keinen Umständen mit Cloud-KI.

## 3. Schnittstellen

Ein neuer Endpoint in `app/routers/beleg_auswertung.py`:

```
POST /api/beleg-auswertungen/{id}/uebernehmen
  {sparte_id, datum?, bezahlt_von_sparte_id?, zahlungsart? (Standard 'bar'),
   positionen: [{text, betrag_cent, kategorie_id, typ? (Standard 'ausgabe')}],
   client_request_id?}
  → 201 {buchung_id, version}
```

Regeln:
- `pruefe_auswertung` und `pruefe_sparte`; der Auftrag muss `status='fertig'` haben, sonst 409 „Auswertung ist noch nicht fertig oder bereits abgeschlossen".
- `positionen` darf nicht leer sein; jede `kategorie_id` muss zur gewählten `sparte_id` gehören (dieselbe Prüfung wie `POST /api/buchungen`).
- Erzeugt **eine** Buchung mit einer Buchungszeile je Position — dieselbe Prüf- und Einfüge-Logik wie `POST /api/buchungen` nutzen, nicht duplizieren: liegt sie in `create_buchung` als reiner Endpoint-Body, eine kleine Hilfsfunktion `erstelle_buchung(con, bereich, sparte_id, datum, typ, zahlungsart, bezahlt_von_sparte_id, positionen, client_request_id) -> dict` in `app/routers/buchungen.py` herausziehen und von beiden Stellen aufrufen lassen; Verhalten von `POST /api/buchungen` darf sich dabei nicht ändern (Regressionstests aus P11/P12/P20 bleiben grün).
- Nach dem Anlegen: `buchung_beleg(buchung_id, beleg_id)` einfügen (Beleg-ID aus `beleg_auswertung.beleg_id`), `belegstatus` der Buchung entsprechend setzen (wie in `app/routers/belege.py::_aktualisiere_belegstatus`), `beleg_auswertung.status='verbucht'` setzen.
- `client_request_id` verhält sich wie bei `POST /api/buchungen` (gleicher Schlüssel/gleiche Daten → 200 dieselbe Buchung, andere Daten → 409).

`static-neu/pages/belege.js` (ersetzt den P30-Platzhalter), drei Karten plus ein Verweis:

1. **Rechnung fotografieren**: Datei-Input mit `capture="environment"` fürs Handy plus normaler Dateiauswahl. Auswahl löst `POST /api/belege` (multipart, `sparte_id` = aktuell gewählte Sparte) und danach `POST /api/belege/{id}/auswerten` aus. Zeigt „wird ausgewertet, das dauert ein paar Minuten, die App darf zu sein" (Wortlaut aus dem Prototyp) mit Polling auf `GET /api/beleg-auswertungen?status=laeuft` alle 4 Sekunden, Obergrenze 3 Minuten, danach Hinweis „dauert ungewöhnlich lange — bitte später erneut prüfen" statt endlosem Warten. Ist `GET /api/auswertung/status` nicht erreichbar oder `modell_vorhanden=false`, erscheint statt des Uploads der Hinweis „Foto-Auswertung gerade nicht erreichbar" (kein stiller Fehlschlag).
2. **Belege zur Prüfung** (`GET /api/beleg-auswertungen?status=fertig`): je Auftrag eine Kachel mit Händler, Datum, Gesamtbetrag aus `ergebnis`. Klick öffnet den Prüf-Dialog: Sparte-Pflichtfeld (das Modell kennt keine Sparten, deshalb kein Vorschlag), je Position editierbares Textfeld und Betrag, Kategorie-Dropdown — sobald eine Sparte gewählt ist, die Kategorien dieser Sparte laden (`GET /api/kategorien?sparte_id=`) und lokal per Namensabgleich vorbefüllen (leichte, im Client gehaltene Variante von `_match_name`, kein neuer Endpoint nötig, weil `_kategorie_fuer_position` serverseitig ohnehin nur mit fester Sparte arbeitet, die der Client zum Auswertungszeitpunkt noch nicht kennt). `ergebnis.hinweis` (z. B. Netto/Brutto-Angleichung) wird unverändert angezeigt. „Bezahlt von" wie in P40 nur bei Richtung „Ausgabe". „Übernehmen" → `POST .../uebernehmen`; Erfolg zeigt Toast und entfernt die Kachel aus der Liste. „Verwerfen" → `POST /api/beleg-auswertungen/{id}/status {status:'verworfen'}`.
3. **Belege** (`GET /api/belege`): Kachel-Ansicht wie im Prototyp (Dateiname, Datum, Sparte); Klick öffnet die Datei über `GET /api/belege/{id}/datei` in neuem Tab.
4. Verweis aus `pages/erfassen.js` (P40): der dortige Platzhalter-Knopf „Rechnung fotografieren" ruft denselben Upload-Fluss wie Punkt 1 auf; nach dem Hochladen bleibt der Nutzer auf der Erfassen-Seite (die Auswertung dauert Minuten und blockiert die Erfassung nicht — „die App darf zu sein").

## 4. Nicht-Ziele

Keine Änderung an `app/auswertung.py` (Modell, Prompt, Netto/Brutto-Abgleich, Hintergrundschleife, Timeouts bleiben unverändert). Unter keinen Umständen eine Cloud-KI-Anbindung. Kein PDF-Vorschaubild, nur ein Icon. Keine Änderung an `POST /api/belege` oder der Belegablage.

## 5. Schritte

1. Endpoint `POST /api/beleg-auswertungen/{id}/uebernehmen`, ggf. `erstelle_buchung`-Hilfsfunktion aus `buchungen.py` herausgezogen.
2. `pages/belege.js`: Upload mit Polling, Nicht-erreichbar-Hinweis.
3. Prüf-Dialog mit Positions-Bearbeitung, Kategorie-Vorbefüllung, Übernehmen/Verwerfen.
4. „Belege"-Kachelliste.
5. Verweis aus `pages/erfassen.js` (P40) verdrahten.
6. Tests, Gesamtlauf, Browserprüfung, Bericht.

## 6. Tests

Testinterpreter `C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Scripts\python.exe`, `FINANZ_DB` auf eine Wegwerf-Datenbank unter `C:\Users\lblet\AppData\Local\Temp` (nie die echte Datenbank), Tests über `tempfile.TemporaryDirectory()`, schreiben nie in den Arbeitsbaum. `bereich_dep` bleibt an `/api/belege*`, `/api/beleg-auswertungen*` — niemals an `/api/auth/*`, `/api/health`, `/api/schema`, `/api/betrieb/status`.

`tests/test_beleg_auswertung.py` erweitern (Auftrag direkt mit `status='fertig'` und festem `ergebnis_json` in die Wegwerf-DB schreiben statt Ollama aufzurufen, damit die Tests offline laufen):
- `.../uebernehmen` mit zwei Positionen → eine Buchung mit zwei Buchungszeilen, Summe der Zeilen = Summe der `betrag_cent`, Beleg über `buchung_beleg` verknüpft, `beleg_auswertung.status='verbucht'`.
- Aufruf ohne `status='fertig'` (z. B. `'laeuft'`) → 409.
- `sparte_id` aus anderem Bereich → 404.
- `client_request_id` doppelt mit gleichen Daten → 200 dieselbe `buchung_id`; mit anderen Daten → 409.
- `bezahlt_von_sparte_id` gesetzt → erzeugt eine Auslage (P12) genauso wie eine normal über `POST /api/buchungen` erfasste Ausgabe (gleicher Kassa-/Auslage-Effekt).
- Regressionslauf: bestehende Tests zu `POST /api/buchungen` bleiben grün, falls `create_buchung` zur gemeinsamen Hilfsfunktion umgebaut wurde.

`node --check static-neu/pages/belege.js` und `static-neu/pages/erfassen.js`.

Browserprüfung (Playwright, falls verfügbar, sonst ausdrücklich vermerken statt stillschweigend auszulassen): Foto einer Testrechnung hochladen; läuft in der Sandbox kein Ollama, den Auftrag stattdessen per Testskript direkt auf `status='fertig'` setzen und das ausdrücklich im Bericht vermerken. Prüf-Dialog öffnen, Positionen zeigen, Sparte wählen → Kategorien laden, Übernehmen → Buchung erscheint in `GET /api/buchungen`, Beleg-Kachel erscheint unter „Belege"; Konsole ohne Fehler.

## 7. Fertig heißt

- [ ] Alle Tests grün, vollständige Ausgabe im Bericht.
- [ ] Playwright-Ergebnis im Bericht oder ausdrücklicher Grund, warum nicht möglich.
- [ ] Kein Aufruf einer Cloud-KI im Code, keine neue externe Abhängigkeit.
- [ ] Kein toter Code, keine Abschwächung von Validierung.
- [ ] Keine Geheimnisse, keine echten Namen im Code.
- [ ] Bericht geschrieben.

## 8. Modell und Aufwand

Modell: `gpt-5.6-luna`, Aufwand medium.

## 9. Bericht zurück

Geänderte und neue Dateien mit je einem Satz. Vollständige Testausgabe. Was im Browser geprüft wurde oder nicht geprüft werden konnte, mit Grund. Offene Punkte mit Grund. Keine Commits, kein Push.
