# P70 – KI-Kategorievorschlag als Rückfallebene: Runde 1

Branch `pkt/p70-ki-vorschlag`, Worktree `C:\Users\lblet\dev\wt-p70`, Ausgangsstand `neubau` 67a4011.

## Was gebaut wurde

**Backend**

- `app/ki_vorschlag.py` (neu): `kategorie_vorschlag(con, *, text, bereich_id, sparte_id=None, typ=None, betrag_cent=None)`.
  - Kandidatenliste: aktive Kategorien der Sparte (oder aller aktiven Sparten des Bereichs, wenn `sparte_id=None`), gefiltert nach Richtung passend zu `typ`.
  - Prompt auf Deutsch, Text/Betrag/Richtung/nummerierte Kategorienliste, Antwortformat strikt JSON (`kategorie_id`, `sicherheit`, `begruendung`).
  - Ruft `auswertung._ollama_aufruf` / `auswertung._denkmodus_abschalten` / `auswertung.OLLAMA_URL` / `auswertung.OLLAMA_MODEL` wieder — keine Duplikation der Ollama-Anbindung.
  - Validiert `kategorie_id` gegen die Kandidatenliste; jeder Fehler (nicht erreichbar, Timeout, kaputtes JSON, ID außerhalb der Liste) liefert `None` + `log.warning`, nie eine Exception.
  - `ist_aktiv()` prüft `FINANZ_KI_VORSCHLAG` (Standard an) bei jedem Aufruf live (kein Caching), damit Tests per `patch.dict(os.environ, …)` zuverlässig greifen.
  - Eigene Zeitsperre `FINANZ_OLLAMA_TEXT_TIMEOUT` (Standard 60 s) — siehe Abweichung unten.
- `app/auswertung.py`: `_ollama_aufruf` bekommt einen optionalen `timeout`-Parameter (Default weiterhin `OLLAMA_TIMEOUT_SEKUNDEN`), damit `ki_vorschlag.py` die eigene, kürzere Zeitsperre nutzen kann, ohne die Funktion zu duplizieren oder den Foto-Weg zu beeinflussen.
- `app/routers/schnellerfassung.py`:
  - Neuer Endpunkt `POST /api/kategorie-vorschlag/ki` (`KiVorschlagIn`: `text`, `sparte_id?`, `typ?`, `betrag_cent?`). Prüft zuerst Textlänge (422 bei < 3 Zeichen) und `sparte_id` über `pruefe_sparte` (404 bei fremder Sparte), erst danach `FINANZ_KI_VORSCHLAG` bzw. der eigentliche Modellaufruf — ein ungültiges `sparte_id` löst also nie einen (langsamen) Ollama-Aufruf aus.
  - `_parse_einzeltext` (und damit `/api/parse`, `/api/parse-mehrere`) liefert zusätzlich `"quelle": "name" | "regel" | null` und `"regel_name"` (gesetzt bei Regeltreffern). Bestehende Felder unverändert.

**Frontend**

- `static-neu/pages/erfassen.js`: eigener Timer `M.kiTimer` (1,5 s, unabhängig vom 300-ms-Parse-Timer). Fragt die KI nur, wenn der reguläre Vorschlag (`M.letzterVorschlag`) keine `kategorie_id` liefert, der Text seit 1,5 s unverändert ist und noch nicht zu diesem Text gefragt wurde (`M.kiLetzterText`, Dedupe). Während des Aufrufs „KI fragt …“, bei `null` kein Text. Anzeige „KI-Vorschlag: Sparte · Kategorie (Sicherheit) [übernehmen]“ in eigener Box `#ef-ki-sugg`; Übernahme ausschließlich per Klick, respektiert danach `M.manuellKategorie`/`M.manuellSparte` wie der reguläre Weg.
- `static-neu/pages/bankimport.js`: Im Zuordnen-Dialog (`formularHtml`/`oeffneFormular`) erscheint der Knopf „KI-Vorschlag holen“ nur, wenn kein Regelvorschlag vorliegt (`!u.vorschlag`). Holt den Vorschlag on demand, füllt Sparte/Kategorie-Selects vor, setzt „Zuordnung als Regel merken“ **nicht** automatisch, zeigt „Vorschlag der KI (Modell …): Sparte · Kategorie (Sicherheit). Bitte prüfen.“ als Status-Text.
- Beide Dateien: `node --check` grün.

## Prompt im Wortlaut (Vorlage aus `app/ki_vorschlag.py`)

```
Ordne den folgenden Buchungstext genau EINER der aufgelisteten Kategorien
zu, oder keiner, wenn nichts eindeutig passt.
Buchungstext: {text!r}
Betrag: {betrag}
Richtung: {richtung}
Kategorien (id: Sparte / Kategorie):
{liste}
Antworte AUSSCHLIESSLICH mit einem JSON-Objekt in genau diesem Format,
ohne weiteren Text davor oder danach: {"kategorie_id": ganze Zahl aus der Liste oder null,
"sicherheit": "hoch" oder "mittel" oder "niedrig", "begruendung": string}.
Ist keine Kategorie eindeutig passend, liefere kategorie_id null.
```

`{text!r}` wird mit Python-`repr()` eingesetzt (in Anführungszeichen, escaped), `{betrag}` ist entweder `"12,34 EUR"` oder `"unbekannt"`, `{richtung}` eines von `Einnahme`/`Ausgabe`/`Umbuchung`/`unbekannt`, `{liste}` sind Zeilen `<id>: <Sparte> / <Kategorie>`. Body-weit: `format: "json"`, `options.temperature: 0`, `stream: false`, `think: false` falls `_denkmodus_abschalten(OLLAMA_MODEL)` (Qwen-3-Familie).

## Testergebnis

- `tests/test_p70_ki_vorschlag.py`: **20/20 grün** (Kandidatenliste inkl. Richtungsfilter, gültige/ungültige/kaputte Modellantworten, `URLError`, Abschaltbarkeit ohne Ollama-Aufruf, Endpunkt 200/422/404, `quelle`/`regel_name` in `/api/parse`). Ollama wird durchgehend über `patch.object(auswertung, "_ollama_aufruf", …)` gemockt — kein echter Modellaufruf.
- Gesamtsuite (`FINANZ_DB=%TEMP%\p70-suite.db`, Datei vorher gelöscht): **474 Tests, OK (1 skipped, unabhängig von P70)** in 461,999 s. Rohausgabe: `docs/neubau/berichte/P70-tests.txt`.
- `node --check static-neu/pages/erfassen.js` und `node --check static-neu/pages/bankimport.js`: beide grün.
- Kein Live-Test gegen Port 8071 durchgeführt (nicht nötig, da die Unit-/Endpunkttests den Endpunkt bereits per Direktaufruf mit echtem Schema/echter DB abdecken — siehe Abweichung unten).

## Abweichungen von der Karte (mit Begründung)

1. **`_ollama_aufruf` um optionalen `timeout`-Parameter erweitert** statt unverändert zu lassen. Die Karte verlangt sowohl Wiederverwendung von `auswertung._ollama_aufruf` als auch eine eigene, kürzere Zeitsperre `FINANZ_OLLAMA_TEXT_TIMEOUT` — die bestehende Funktion kannte aber nur die globale `OLLAMA_TIMEOUT_SEKUNDEN` (600 s, für Fotos gedacht). Minimal-invasive Lösung: ein optionaler `timeout`-Parameter mit Default = bisheriges Verhalten, damit der Foto-Weg unverändert bleibt und der Text-Weg trotzdem seine eigene Zeitsperre bekommt, ohne die HTTP-Logik zu duplizieren.
2. **Kein neues Feld `haystack` in `GET /api/bankumsaetze`.** Die Karte erlaubt das „wenn nötig“ — die Antwort enthält aber bereits `text` und `gegenpartei` je Umsatz, aus denen `bankimport.js` den Text für die KI-Anfrage clientseitig zusammensetzt (`${u.gegenpartei || ''} ${u.text || ''}`). Ein zusätzliches API-Feld war dafür nicht nötig; das hält die Änderung kleiner (Konfliktregel „kleinster logisch abgeschlossener Schritt“).
3. **`grund: "unsicher"` nicht erzeugt.** Die Karte nennt in der Endpunkt-Dokumentation drei mögliche Werte für `grund` (`kein_modell`, `abgeschaltet`, `unsicher`), aber die vorgegebene Signatur von `kategorie_vorschlag()` liefert laut Abschnitt 3 nur `dict | None` — es gibt in der Rückgabe keine Möglichkeit, zwischen „Modell technisch nicht erreichbar/kaputt“ und „Modell hat sich explizit gegen jede Kategorie entschieden“ zu unterscheiden, ohne die vorgegebene Signatur zu verändern. Der Endpunkt liefert deshalb für beide Fälle einheitlich `grund: "kein_modell"`. Sollte die Unterscheidung gewünscht sein, müsste `kategorie_vorschlag()` einen dritten Rückgabezustand bekommen (z. B. ein kleines Result-Objekt statt `dict | None`) — das wäre eine bewusste Rücksprache wert, da es die Karten-Signatur ändert.
4. **Kein Live-Test über Port 8071.** Die geforderten Endpunktfälle (200 mit Vorschlag, 200 mit `null`+`grund`, 422, 404) sind über Direktaufrufe der Router-Funktion mit echtem Schema/echter Test-DB abgedeckt (gleiches Muster wie `tests/test_schnellerfassung_mehrere.py` und `tests/test_beleg_auswertung.py`). Ein zusätzlicher Live-Server war dafür nicht nötig und hätte nur unnötig einen weiteren Prozess auf der Maschine belegt.

## Offene Punkte

- Kein manueller Smoke-Test in der laufenden App (Browser war laut Auftrag belegt) — nur Unit-/Endpunkttests über Direktaufruf. Ein kurzer Klicktest von „KI-Vorschlag holen“ (Bankimport) und der automatischen 1,5-s-KI-Anfrage (Erfassen) mit einem echten Ollama-Modell steht noch aus.
- `grund: "unsicher"` ist wie oben beschrieben nicht implementiert — falls das Frontend künftig zwischen „Modell weiß es nicht“ und „Modell nicht erreichbar“ unterscheiden soll, braucht es eine Rücksprache zur Signatur von `kategorie_vorschlag()`.
- Keine Migration/Persistenz nötig (wie in der Karte gefordert) — bestätigt: nichts wird gespeichert, außer über den bestehenden Weg `_lerne_regel`/`regel_merken`, wenn der Nutzer eine übernommene Zuordnung explizit als Regel merkt.

## Commit

Ein Commit im Worktree auf `pkt/p70-ki-vorschlag`, kein Push, kein Merge (Hash siehe Rückmeldung des Kopfs nach `git commit`).
