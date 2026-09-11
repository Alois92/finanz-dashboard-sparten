# P70: KI-Kategorievorschlag als Rückfallebene

Nach M6 (Nutzerwunsch 11.09.2026). Modell: Claude Sonnet als Subagent. Branch `pkt/p70-ki-vorschlag` von `neubau` (Stand 67a4011 oder neuer). Worktree `C:\Users\lblet\dev\wt-p70`.

## 1. Ziel

Findet der bestehende Vorschlagsweg (Namensabgleich, Stichwort-/Merkregeln) keine Kategorie, fragt die App auf Wunsch das lokale Sprachmodell (Ollama, Textaufruf ohne Bild) nach einer Kategorie aus der Liste der Sparte. Der Vorschlag ist immer nur ein Vorschlag, klar als „KI“ gekennzeichnet, wird nie automatisch verbucht und wird erst durch die Bestätigung des Nutzers wirksam. Bestätigt der Nutzer, entsteht daraus wie bisher eine Merkregel (bestehender Weg `_lerne_regel` bzw. `regel_merken`), sodass das Modell beim nächsten gleichen Text nicht mehr gebraucht wird.

## 2. Kontext (lesen, bevor du schreibst)

- `app/regeln.py` (`finde_regel`, `aktive_regeln`), `app/routers/schnellerfassung.py` (`_parse_einzeltext`, Rückgabefelder), `app/routers/import_bank.py` (`_vorschlag_fuer_umsatz`, `_regel_haystack`, `zuordnen`-Endpunkt mit `regel_merken`), `app/routers/buchungen.py` (`_lerne_regel`).
- `app/auswertung.py`: `_ollama_aufruf`, `_denkmodus_abschalten`, `OLLAMA_URL`, `OLLAMA_MODEL`, `_parse_ergebnis` als Muster für defensives JSON-Parsen. Den Ollama-Aufruf **wiederverwenden**, nicht duplizieren.
- Frontend `static-neu/pages/erfassen.js` (`parseText`, `zeigeVorschlag`, `M.manuellKategorie`), `static-neu/pages/bankimport.js` (`oeffneFormular`, `formularHtml`, Vorschlagsanzeige), `static-neu/ui.js` (`toast`, `drill`), `static-neu/api.js`.
- `docs/neubau/ARCHITEKTUR.md` Abschnitt 4 und `docs/neubau/SCHULDEN.md` (P40b: `/api/parse` liefert nur einen Treffer ohne Herkunft — bei dieser Gelegenheit das Feld `quelle` in der Parse-Antwort einführen, siehe 3.).

Entscheidungen des Kopfs:
- **Kein** Aufruf des Modells innerhalb von `POST /api/parse` (läuft beim Tippen, das Modell braucht auf der CPU von CT 101 mehrere Sekunden). Eigener Endpunkt, den das Frontend nur dann ruft, wenn der normale Weg leer bleibt.
- **Keine** Migration, keine Speicherung des KI-Vorschlags. Er lebt nur in der Antwort; dauerhaft wird nur die vom Nutzer bestätigte Merkregel.
- Bankimport: Vorschlag je Umsatz **auf Anforderung** im Zuordnen-Dialog (kein Sammellauf beim Import).
- Abschaltbar über `FINANZ_KI_VORSCHLAG=0` (Standard an). Zeitsperre eigener Wert `FINANZ_OLLAMA_TEXT_TIMEOUT` (Standard 60 s), weil Textaufrufe viel schneller sind als Fotos.

## 3. Schnittstellen

Neues Modul `app/ki_vorschlag.py`:

```python
def kategorie_vorschlag(con, *, text: str, bereich_id: int, sparte_id: int | None,
                        typ: str | None, betrag_cent: int | None) -> dict | None
```
- Baut die Kandidatenliste: aktive Kategorien der Sparte (bei `sparte_id=None` alle aktiven Kategorien aller aktiven Sparten des Bereichs, dann darf das Modell auch die Sparte wählen); Filter nach `richtung` passend zu `typ` (`einnahme`/`ausgabe`/`beides`), wenn `typ` bekannt.
- Prompt (deutsch, kurz): Buchungstext, Betrag, Richtung, nummerierte Liste `id: Sparte / Kategorie`; Antwort **ausschließlich** JSON `{"kategorie_id": int | null, "sicherheit": "hoch"|"mittel"|"niedrig", "begruendung": string}`; bei Unsicherheit `null`.
- Aufruf über `auswertung._ollama_aufruf(OLLAMA_URL + "/api/chat", body)` mit `stream: false`, `format: "json"`, `options.temperature: 0`, `think: False` falls `_denkmodus_abschalten(modell)`. Kein `images`-Feld.
- Validierung: `kategorie_id` muss in der Kandidatenliste sein, sonst `None`. Rückgabe `{"sparte_id", "sparte_name", "kategorie_id", "kategorie_name", "sicherheit", "begruendung", "quelle": "ki", "modell": OLLAMA_MODEL}`.
- Fehler (Ollama nicht erreichbar, Timeout, kaputtes JSON): `None` zurück und `log.warning`, nie eine Exception zum Aufrufer. Bei `FINANZ_KI_VORSCHLAG=0` sofort `None`.

Endpunkt in `app/routers/schnellerfassung.py`:

```
POST /api/kategorie-vorschlag/ki   {text: str, sparte_id?: int, typ?: str, betrag_cent?: int}
  → 200 {"vorschlag": {...} | null, "grund": "kein_modell"|"abgeschaltet"|"unsicher"|null}
  → 422 bei leerem Text (< 3 Zeichen)
```
`bereich_id` wie überall als Query-Parameter über `BereichDep`. `sparte_id` mit `pruefe_sparte` prüfen.

`POST /api/parse` und `/parse-mehrere`: Antwort erhält zusätzlich `"quelle": "name" | "regel" | null` (woher die Kategorie kam) und `"regel_name"` bei Regeltreffern. Bestehende Felder unverändert (bestehende Tests müssen weiter laufen).

Bankimport, `GET /api/bankumsaetze`: unverändert. Der Zuordnen-Dialog ruft bei fehlendem Vorschlag den neuen Endpunkt mit `text = Haystack des Umsatzes` (Frontend baut ihn aus Verwendungszweck, Auftraggeber/Empfänger; wenn nötig neues Feld `haystack` in der Umsatz-Antwort ergänzen, ohne andere Felder zu ändern), `typ` aus dem Vorzeichen, `betrag_cent`.

Frontend:
- `erfassen.js`: Wenn `parseText` keine `kategorie_id` liefert und der Text seit 1,5 s unverändert ist (eigener Timer, nicht der Parse-Timer), einmal den KI-Endpunkt rufen. Anzeige unter dem bestehenden Vorschlag: `KI-Vorschlag: <Sparte> · <Kategorie> (Sicherheit) [übernehmen]`. Übernahme **nur per Klick** (setzt Sparte/Kategorie in den Selects, respektiert `M.manuellKategorie`). Während des Aufrufs Hinweis „KI fragt …“, bei `null` kein Text (kein Rauschen). Pro Text nur ein Aufruf (Merker des zuletzt gefragten Texts).
- `bankimport.js`: Im Zuordnen-Dialog ohne Regelvorschlag ein Knopf „KI-Vorschlag holen“; Ergebnis füllt Sparte/Kategorie vor und setzt das Häkchen `regel_merken` **nicht** automatisch (der Nutzer entscheidet). Kennzeichnung im Dialog „Vorschlag der KI (Modell …)“.
- Kein neuer Aufruf, wenn `FINANZ_KI_VORSCHLAG` aus ist: der Endpunkt liefert `grund: "abgeschaltet"`, das Frontend zeigt dann nichts an.

## 4. Nicht-Ziele

Keine Speicherung, keine Migration, kein automatisches Verbuchen, kein Sammellauf über alle offenen Umsätze, keine Änderung an `finde_regel`, keine neuen Abhängigkeiten.

## 5. Tests (Pflicht, `FINANZ_DB` immer auf Wegwerf-Datei unter `%TEMP%`, kein `FINANZ_TEST_AUTH_BYPASS` in der Suite)

`tests/test_p70_ki_vorschlag.py`, Ollama immer über `patch.object(auswertung, "_ollama_aufruf", ...)` gemockt (nie das echte Modell in Tests):
1. Kandidatenliste: nur aktive Kategorien der Sparte, Richtungsfilter bei `typ`.
2. Gültige Antwort → Vorschlag mit Namen; ID außerhalb der Liste → `None`; kaputtes JSON → `None`; `URLError` → `None` ohne Exception.
3. `FINANZ_KI_VORSCHLAG=0` → `None`, kein Ollama-Aufruf (Mock nicht aufgerufen).
4. Endpunkt: 200 mit Vorschlag, 200 mit `null` + `grund`, 422 bei leerem Text, 404/400 bei fremder Sparte (Bereichsprüfung).
5. `/api/parse` liefert `quelle` (`name`, `regel`, `null`) – bestehende Tests unverändert grün.
6. `node --check` für beide geänderten JS-Dateien.

Gesamtsuite am Ende: `C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Scripts\python.exe -m unittest discover -s tests` im Worktree mit `FINANZ_DB=%TEMP%\p70-suite.db` (Datei vorher löschen), Ergebnis in `docs/neubau/berichte/P70-tests.txt`.

## 6. Abgabe

Commit(s) im Worktree auf `pkt/p70-ki-vorschlag`, **kein Push, kein Merge**. Bericht `docs/neubau/berichte/P70-runde1.md`: was gebaut, Prompt im Wortlaut, Testergebnis, offene Punkte, Entscheidungen, die von dieser Karte abweichen (mit Begründung). Keine Änderungen außerhalb des Worktrees, nichts unter `Z:\`, kein Zugriff auf Ports 8051–8056.
