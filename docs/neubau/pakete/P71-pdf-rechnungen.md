# P71: Rechnungen als Text-PDF auswerten

Nach M6 (Nutzerwunsch 11.09.2026). Modell: Claude Sonnet als Subagent. Branch `pkt/p71-pdf-rechnungen` von `neubau` (Stand 67a4011 oder neuer). Worktree `C:\Users\lblet\dev\wt-p71`.

## 1. Ziel

Eine per Mail erhaltene Rechnung als PDF wird über denselben Weg ausgewertet wie ein Foto: Beleg hochladen, Auswertung anfordern, Prüf-Dialog, Übernahme als Buchung. Bei PDFs mit Textebene wird der Text extrahiert und ohne Bilderkennung an das Sprachmodell geschickt (schneller und genauer als ein Foto). PDFs ohne Textebene (Scans) werden mit einer klaren Meldung abgewiesen, nicht stillschweigend leer ausgewertet.

## 2. Kontext (lesen, bevor du schreibst)

- `app/auswertung.py` vollständig: `PROMPT`, `ERLAUBTE_ENDUNGEN`, `_lade_bild_base64`, `_ollama_aufruf`, `_denkmodus_abschalten`, `_parse_ergebnis`, `_brutto_abgleich`, `_auswerten`, `_verarbeite_naechsten_auftrag` (Fehlerbehandlung: `ValueError` = endgültig fehlgeschlagen, `URLError/OSError` = Auftrag bleibt offen).
- `app/routers/belege.py` (`ERLAUBTE_ENDUNGEN` enthält bereits `pdf`), `app/routers/beleg_auswertung.py` (`auswerten_anfordern`, Statusfelder, Fehlermeldung an das Frontend).
- Frontend `static-neu/pages/belege.js` (`ladeBelegUndAuswerten`, Datei-Input `accept`, Statusanzeige, Prüf-Dialog), `docs/neubau/abnahme/P43.md`.
- Abhängigkeit: **`pypdf`** (rein Python, BSD-Lizenz, keine nativen Bibliotheken; vom Nutzer am 11.09.2026 freigegeben). Genaue Version pinnen: aktuelle stabile Version nehmen, in `requirements.txt` eintragen, im venv des Hauptklons installieren (`C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Scripts\python.exe -m pip install pypdf==<version>`), Version im Bericht nennen. `docs/BETRIEB-UND-ARCHITEKTUR.md` Abschnitt 11 (Umstellung): Punkt ergänzen, dass `pip install -r requirements.txt` im Container vor dem Start läuft.

Entscheidungen des Kopfs:
- Textextraktion nur aus der Textebene (`pypdf`), **kein** Rendern von PDF-Seiten zu Bildern (dafür fehlt eine Renderer-Bibliothek; Scans sollen als Foto hochgeladen werden).
- Obergrenzen: höchstens die ersten 5 Seiten, höchstens 12.000 Zeichen Text (danach abschneiden, Hinweis im Ergebnis `hinweis`), damit der Prompt auf der CPU beherrschbar bleibt.
- Mindestens 40 Zeichen sichtbarer Text (ohne Leerraum), sonst „PDF ohne Textebene“ → `ValueError` mit dieser Meldung, Auftrag endgültig fehlgeschlagen mit verständlichem Text für den Nutzer.
- Gleicher Prompt-Kern wie beim Foto (Positionen, Brutto, `gesamt_cent`), eingeleitet mit „Hier ist der Text einer Rechnung:“ statt „abgebildet“. Gleicher Parser, gleicher Brutto-Abgleich, gleiche Kategorievorschläge, gleiche Übernahme.

## 3. Schnittstellen

`app/auswertung.py`:
- `ERLAUBTE_ENDUNGEN` um `pdf` erweitern.
- Neu `PROMPT_TEXT` (aus einem gemeinsamen Kernstück mit `PROMPT` zusammengesetzt, kein zweiter, abweichender Wortlaut der Regeln).
- Neu `_pdf_text(pfad: pathlib.Path) -> str` (pypdf, Seiten-/Zeichenlimit, Leerraum normalisieren; wirft `ValueError("PDF ohne Textebene – bitte als Foto hochladen")` unter 40 Zeichen; kaputtes PDF ebenfalls `ValueError` mit klarer Meldung). Import von pypdf **innerhalb** der Funktion, mit verständlicher `ValueError`, falls das Paket fehlt.
- `_auswerten`: bei Endung `pdf` Body ohne `images`, `content = PROMPT_TEXT + "\n\n" + text`; sonst unverändert. Zeitsperre wie bisher.
- Ergebnis erhält `"quelle": "pdf_text" | "foto"`, damit das Frontend die Herkunft anzeigen kann.

`app/routers/beleg_auswertung.py`: Fehlermeldung des Auftrags (Feld für den Nutzer) muss den `ValueError`-Text durchreichen; prüfen, dass die Endungsprüfung dort (falls doppelt vorhanden) `pdf` zulässt.

Frontend `belege.js`: Auswertung für PDF-Belege anbieten (Knopf nicht mehr auf Bilder beschränkt), Statuszeile zeigt bei Fehlschlag den Meldungstext, Prüf-Dialog zeigt „aus PDF-Text“ bzw. „aus Foto“. Datei-Input `accept` bleibt.

## 4. Nicht-Ziele

Kein OCR, kein Seiten-Rendering, keine Migration, keine Änderung am Foto-Weg außer der gemeinsamen Prompt-Zerlegung, keine E-Mail-Anbindung.

## 5. Tests (Pflicht, `FINANZ_DB` immer auf Wegwerf-Datei unter `%TEMP%`, kein `FINANZ_TEST_AUTH_BYPASS` in der Suite)

`tests/test_p71_pdf.py`, Ollama immer über `patch.object(auswertung, "_ollama_aufruf", ...)` gemockt. Test-PDFs zur Laufzeit im Temp-Ordner erzeugen (mit pypdf `PdfWriter` und einer Textseite; für „ohne Textebene“ eine leere Seite), keine Binärdateien ins Repo.
1. `_pdf_text`: Text wird gelesen, Leerraum normalisiert, Seiten-/Zeichenlimit greift, leere Seite → `ValueError` mit „Textebene“, kaputte Datei → `ValueError`.
2. `_auswerten` mit PDF: Body hat kein `images`, `content` beginnt mit `PROMPT_TEXT`, Ergebnis `quelle == "pdf_text"`, Positionen/Kategorien wie beim Foto.
3. `_auswerten` mit JPG unverändert (`quelle == "foto"`), bestehende Tests `test_beleg_auswertung.py`/`test_p43_foto.py` grün.
4. Endpunkt `POST /api/belege/{id}/auswerten` akzeptiert PDF; Auftrag mit Scan-PDF endet in Status fehlgeschlagen mit der Meldung.
5. `node --check static-neu/pages/belege.js`.

Gesamtsuite am Ende: `C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Scripts\python.exe -m unittest discover -s tests` im Worktree mit `FINANZ_DB=%TEMP%\p71-suite.db` (Datei vorher löschen), Ergebnis in `docs/neubau/berichte/P71-tests.txt`.

## 6. Abgabe

Commit(s) im Worktree auf `pkt/p71-pdf-rechnungen`, **kein Push, kein Merge**. Bericht `docs/neubau/berichte/P71-runde1.md`: was gebaut, `pypdf`-Version, Prompt im Wortlaut, Testergebnis, offene Punkte, Abweichungen von dieser Karte mit Begründung. Keine Änderungen außerhalb des Worktrees (Ausnahme: `pip install` ins venv des Hauptklons), nichts unter `Z:\`, kein Zugriff auf Ports 8051–8056, Ollama nicht anhalten.
