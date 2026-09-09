# P41: Konten und Kassen verwalten, offene Auslagen, Ausgleich-Dialog

Meilenstein M4. Branch `pkt/p41-konten-ausgleich` von `neubau` (nach P11, P12, P13, P30).

## 1. Ziel

Der Nutzer verwaltet im neuen Frontend alle Konten und Kassen (anlegen, Anfangsstand setzen, Kassa zählen und Differenz buchen), sieht auf einen Blick, wer wem wieviel an privat bezahlten Auslagen schuldet, und bucht einen Ausgleich — ganz oder teilweise, bar oder per Überweisung — mitsamt Rücknahme.

## 2. Kontext

Lies `docs/neubau/ARCHITEKTUR.md` Abschnitt 3 und 5, dann `docs/neubau/pakete/P11-konten-bewegungen.md`, `P12-auslagen-ausgleich.md`, `P13-saldoanker-kassa.md` (Endpoints und Regeln, die dieses Paket ausschließlich konsumiert, nicht ändert), `docs/neubau/pakete/P30-frontend-geruest.md` (`api.js`, `ui.js` — insbesondere `toast`, `drill`, `sheet` —, Router, Zustand). Vorlage für Text und Verhalten: `docs/neubau/prototyp/prototyp.html`, Abschnitt „Offene Auslagen" (Zeilen ~936–1024, Funktionen `renderAuslagen`, Ausgleich-Dialog, `settle`) und die Kassa-Kachel (Zeilen ~1025–1063). Im Prototyp liegen diese Karten auf der Übersichts-/Sparten-Seite; die hat in M4 noch keinen Inhalt (kommt in einem eigenen, hier nicht beauftragten Paket außerhalb M4). Deshalb ziehen „Offene Auslagen" und der Ausgleich-Dialog in diesem Paket auf die Konten-Seite (`#/konten`), weil sie inhaltlich zu Kassenständen gehören und dort ein Zuhause haben, bis die Übersichtsseite gefüllt wird. Fachliche Vorgaben des Nutzers: Ausgleich jederzeit, Teilbeträge erlaubt, meist bar; negative Kassa warnt, sperrt nicht; Kreditkarte ist ein eigenes Konto, ihr Ausgleich ist eine Umbuchung, keine Ausgabe.

## 3. Schnittstellen

Kein neuer Endpoint. Genutzt werden ausschließlich vorhandene: `GET/POST /api/konten`, `PATCH /api/konten/{id}`, `GET /api/konten/{id}/bewegungen`, `GET /api/konten/{id}/stand`, `POST/GET/DELETE /api/konten/{id}/anker`, `POST /api/konten/{id}/zaehlung` und `.../zaehlung/{id}/buchen`, `GET /api/kassazaehlungen`, `GET /api/auslagen`, `POST /api/ausgleiche`, `DELETE /api/ausgleiche/{id}`, `GET /api/ausgleiche`.

`static-neu/pages/konten.js` (ersetzt den P30-Platzhalter), drei Karten:

1. **Konten**: Liste nach Art gruppiert (Bank, Karte, Kassa, Depot/Wallet nur falls vorhanden). Je Zeile: Name, Art, Stand (`fmtEur`), Datenstand-Badge `aktuell`/`veraltet`/`unbekannt` mit dem `hinweis`-Text aus der Antwort als Titel-Attribut. Bei `art='kassa'` zusätzlich zwei Knöpfe: „Anfangsstand ändern" (Dialog → `POST .../anker`, zeigt bei vorhandenem älteren Anker die zurückgegebene Differenz ungeschönt, nicht still korrigiert) und „Kassa gezählt, Differenz buchen" (Dialog: gezählter Betrag → `POST .../zaehlung`; ist die Differenz ≠ 0, zweiter Schritt „Kategorie wählen" mit „Kassadifferenz" vorausgewählt → `POST .../zaehlung/{id}/buchen`, danach Stand-Anzeige aktualisieren). „+ Konto anlegen" öffnet einen Dialog mit Art-Auswahl (bei `art='kassa'` ist die Sparte Pflicht; 422 aus dem Server wird als Feldfehler angezeigt, keine eigene Client-Validierung, die die Serverprüfung verdoppelt). Bei `art='karte'` steht unter dem Kontoeintrag statisch der Hinweis „Der Ausgleich der Karte ist eine Umbuchung, keine Ausgabe" (reiner Text, keine neue Logik — die Umbuchung selbst existiert bereits über `/api/umbuchungen`/`/api/transfers` aus P11).
2. **Offene Auslagen**: `GET /api/auslagen` gruppiert nach Zahler/Ziel-Sparte, Darstellung wie im Prototyp („X hat für Y ausgelegt", Anzahl Buchungen, ältestes Datum, Summe). Klick auf „Buchungen" öffnet den Drilldown aus `ui.js` (`drill`) mit den zugehörigen `auslagen[].auslagen`-Zeilen. „Ausgleich buchen" öffnet den Ausgleich-Dialog vorbefüllt mit dieser Zahler/Ziel-Kombination.
3. **Ausgleich-Dialog** (über `ui.js`-Dialog/Sheet): Checkboxen je offener Auslage, FIFO-sortiert nach Datum, alle vorangehakt; Zahlungsart-Select mit Vorgabe `bar` (laut Nutzer meist bar); Datum (Standard heute, `max` heute); Betrag in € vorbefüllt mit der Summe der angehakten Auslagen, editierbar für Teilbeträge (`parseBetrag`); bei Zahlungsart `bank` zusätzlich Quell- und Zielkonto-Pflichtfelder. Absenden → `POST /api/ausgleiche` mit `client_request_id`. Enthält die Antwort `warnungen`, wird der Text unverändert übernommen (z. B. „Kassa Hof hat nur 8.744,69 €, danach negativ") und unterhalb des Formulars angezeigt — der Ausgleich ist zu diesem Zeitpunkt bereits gebucht (201), es ist kein zweiter Klick nötig: negative Kassa warnt, sperrt nicht.
4. **Ausgleichs-Historie**: `GET /api/ausgleiche` als Liste unterhalb der Auslagen-Karte, je Zeile „zurücknehmen" → `DELETE /api/ausgleiche/{id}` nach Bestätigung über einen kleinen `ui.js`-Dialog (kein natives `confirm()`, damit es zum Rest der App passt).

## 4. Nicht-Ziele

Keine allgemeine Bewegungs-Liste mit Cursor-Scrollen über die einfache Anzeige aus `GET /api/konten/{id}/bewegungen` hinaus. Kein Anlegen freier Transfers/Umbuchungen über die in P11 vorhandenen Wege hinaus. Keine Änderung an P11-, P12- oder P13-Endpoints. Keine Inhalte für die Übersichts- oder Sparten-Seite.

## 5. Schritte

1. Karte „Konten" mit Liste und Anlegen-Dialog.
2. Anker- und Kassazählungs-Dialoge.
3. Karte „Offene Auslagen" mit Drilldown.
4. Ausgleich-Dialog inkl. Warnung (nicht blockierend) und Historie mit Rücknahme.
5. Tests, Browserprüfung, Bericht.

## 6. Tests

Testinterpreter `C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Scripts\python.exe`, `FINANZ_DB` auf eine Wegwerf-Datenbank unter `C:\Users\lblet\AppData\Local\Temp` (nie die echte Datenbank), Tests über `tempfile.TemporaryDirectory()`, schreiben nie in den Arbeitsbaum.

- `node --check static-neu/pages/konten.js`.
- Kein neuer Server-Endpoint, daher kein neuer Python-Testfall nötig; stattdessen vor der Browserprüfung jeden verwendeten Endpoint einmal gegen die laufende Test-Instanz mit `curl` (oder gleichwertig) durchspielen und die Antworten im Bericht zeigen, damit die Anbindung nachvollziehbar ist.
- Browserprüfung (Playwright, falls verfügbar, sonst ausdrücklich vermerken): Konto anlegen (inkl. 422 bei Kassa ohne Sparte), Anker setzen (Differenz-Antwort sichtbar, nicht still korrigiert), Kassa zählen und Differenz buchen (Stand ändert sich sichtbar), Auslage anzeigen und Drilldown öffnen, Teilausgleich bar buchen (Warnung bei niedriger Kassa sichtbar, Buchung geht trotzdem durch), Ausgleich zurücknehmen (Stand wieder wie vorher), Konsole ohne Fehler.

## 7. Fertig heißt

- [ ] Tests grün bzw. Endpoint-Durchspielung vollständig dokumentiert.
- [ ] Playwright-Ergebnis im Bericht oder ausdrücklicher Grund, warum nicht möglich.
- [ ] Kein toter Code, keine neue Abhängigkeit, keine externen Netzaufrufe im Frontend.
- [ ] Keine Geheimnisse, keine echten Namen im Code.
- [ ] Bericht geschrieben.

## 8. Modell und Aufwand

Modell: `gpt-5.6-luna`, Aufwand medium.

## 9. Bericht zurück

Geänderte und neue Dateien mit je einem Satz. Testausgabe und Endpoint-Durchspielung. Was im Browser geprüft wurde oder nicht geprüft werden konnte, mit Grund. Offene Punkte. Keine Commits, kein Push.
