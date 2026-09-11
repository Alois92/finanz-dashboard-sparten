# P71-Bericht Runde 1 — Rechnungen als Text-PDF auswerten

Umsetzung: Claude Sonnet (Subagent), Worktree `wt-p71`, Branch `pkt/p71-pdf-rechnungen`,
Basis `neubau` Commit `67a4011`.

## Was gebaut wurde

- `app/auswertung.py`:
  - `ERLAUBTE_ENDUNGEN` um `pdf` erweitert.
  - Gemeinsamer Prompt-Kern `_PROMPT_KERN` (JSON-Format, Brutto-Regel, MwSt-Regel, Rabatt-Regel,
    Leerbeleg-Regel) ausgelagert; `PROMPT` (Foto) und neu `PROMPT_TEXT` (PDF-Text) setzen sich
    beide aus diesem Kern zusammen und unterscheiden sich nur in der Einleitung
    ("Analysiere den abgebildeten ..." bzw. "Hier ist der Text einer Rechnung: ...").
  - Neue Funktion `_pdf_text(pfad) -> (text, gekuerzt)`: liest mit `pypdf.PdfReader` höchstens
    die ersten `PDF_MAX_SEITEN` (5) Seiten, normalisiert Leerraum (`re.sub(r"\s+", " ", ...)`),
    schneidet nach `PDF_MAX_ZEICHEN` (12.000) ab. Wirft `ValueError`:
    - wenn `pypdf` nicht installiert ist (Import innerhalb der Funktion),
    - wenn die Datei nicht als PDF gelesen werden kann (kaputte Datei),
    - wenn weniger als `PDF_MIN_ZEICHEN` (40) sichtbarer Text übrig bleibt (Scan ohne Textebene) —
      Meldung „PDF ohne Textebene – bitte als Foto hochladen".
  - `_auswerten`: bei Endung `pdf` wird der Ollama-Body ohne `images` gebaut, `content =
    PROMPT_TEXT + "\n\n" + text`; bei Bildformaten unverändert (mit `images`). Zeitsperre/
    Denkmodus-Abschaltung wie bisher, unabhängig vom Zweig.
  - Ergebnis bekommt zusätzlich `"quelle": "pdf_text"` bzw. `"quelle": "foto"`. Wurde der
    PDF-Text gekürzt, wird das als `hinweis` ergänzt (an einen vorhandenen Brutto-Hinweis
    angehängt statt ihn zu überschreiben).
  - Fehlermeldung bei falscher Endung erweitert: „Nur JPG/PNG/WebP-Fotos oder PDF-Rechnungen
    können lokal ausgewertet werden".
- `app/routers/beleg_auswertung.py`: **keine Änderung nötig** — der Endpunkt
  `auswerten_anfordern` prüft die Dateiendung nicht selbst (das passiert erst in `_auswerten`
  im Hintergrund-Worker), und `_verarbeite_naechsten_auftrag` reicht `str(exc)` als `fehler`
  bereits unverändert durch. Geprüft, keine doppelte Endungsprüfung gefunden.
- `static-neu/pages/belege.js`:
  - Datei-Input akzeptiert PDF bereits seit P43 (`accept` enthält `.pdf`), der Upload-Pfad
    prüft die Endung nicht clientseitig — PDF-Belege liefen also schon vor diesem Paket durch
    Upload und Auswertungsanforderung. Keine Änderung nötig.
  - Neu: `openPruefDialog` zeigt in der Kopfzeile zusätzlich „aus PDF-Text" bzw. „aus Foto"
    (`ergebnis.quelle`).
  - Neu: `warteAufAuswertung` prüft nach Ende des Pollings zusätzlich
    `GET /api/beleg-auswertungen?status=fehler`; ist der Auftrag dort, zeigt die Statuszeile
    (`#blg-warte`) den Meldungstext aus `fehler` statt der pauschalen Erfolgsmeldung, zusätzlich
    als Toast.
- `docs/BETRIEB-UND-ARCHITEKTUR.md` Abschnitt 11.4 Punkt 2: expliziten Befehl
  `.venv/bin/pip install -r requirements.txt` vor dem Dienst-Umschalten ergänzt (vorher nur der
  Prosasatz „Abhängigkeiten im venv installieren" ohne konkreten Befehl).
- `requirements.txt`: `pypdf==6.18.1` ergänzt.

## pypdf-Version

`pypdf==6.18.1`, installiert in `C:\Users\lblet\dev\finanz-dashboard-sparten\.venv` (exakte
Version laut Auftrag, nicht „aktuelle stabile" wie ursprünglich in der Karte formuliert — siehe
Abweichungen).

## Prompt im Wortlaut

**PROMPT (Foto, unverändert im Ergebnis, jetzt aus `_PROMPT_KERN` zusammengesetzt):**

> Analysiere den abgebildeten Kassenbon oder die Rechnung. Antworte AUSSCHLIESSLICH mit einem
> JSON-Objekt in genau diesem Format, ohne weiteren Text davor oder danach:
> {"haendler": string oder null, "datum": "JJJJ-MM-TT" oder null, "positionen": [{"text": string,
> "betrag_cent": integer, "mwst_prozent": Zahl oder null}], "gesamt_cent": integer oder null}.
> Betraege sind ganze Zahlen in Cent (z. B. 5,50 EUR -> 550). betrag_cent ist der BRUTTO-Endpreis
> der Position inklusive MwSt, so wie er zu zahlen ist. Weist der Beleg Netto-Preise und MwSt
> getrennt aus, gib trotzdem den Brutto-Betrag an. mwst_prozent ist der MwSt-Satz der Position
> als Zahl (z. B. 10, 13, 20), falls auf dem Beleg ersichtlich, sonst null. gesamt_cent ist der
> zu zahlende Brutto-Gesamtbetrag. Rabatte und Abzuege werden als negative Betraege angegeben.
> Ist der Beleg unleserlich oder kein Kassenbon/keine Rechnung, liefere eine leere
> Positionsliste ("positionen": []).

**PROMPT_TEXT (neu, PDF-Text):**

> Hier ist der Text einer Rechnung: Antworte AUSSCHLIESSLICH mit einem JSON-Objekt in genau
> diesem Format, ohne weiteren Text davor oder danach: {"haendler": string oder null, "datum":
> "JJJJ-MM-TT" oder null, "positionen": [{"text": string, "betrag_cent": integer,
> "mwst_prozent": Zahl oder null}], "gesamt_cent": integer oder null}. Betraege sind ganze
> Zahlen in Cent (z. B. 5,50 EUR -> 550). betrag_cent ist der BRUTTO-Endpreis der Position
> inklusive MwSt, so wie er zu zahlen ist. Weist der Beleg Netto-Preise und MwSt getrennt aus,
> gib trotzdem den Brutto-Betrag an. mwst_prozent ist der MwSt-Satz der Position als Zahl (z. B.
> 10, 13, 20), falls auf dem Beleg ersichtlich, sonst null. gesamt_cent ist der zu zahlende
> Brutto-Gesamtbetrag. Rabatte und Abzuege werden als negative Betraege angegeben. Ist der Beleg
> unleserlich oder kein Kassenbon/keine Rechnung, liefere eine leere Positionsliste
> ("positionen": []).

Tatsächlicher `content` im Ollama-Aufruf: `PROMPT_TEXT + "\n\n" + <extrahierter PDF-Text>`.

## Tests

Neue Datei `tests/test_p71_pdf.py`, 7 Tests, deckt die Punkte 1–4 der Karte ab:

1. `_pdf_text`: Text wird gelesen und Leerraum normalisiert; Seiten-/Zeichenlimit greift
   (`PDF_MAX_SEITEN + 5` Seiten à 3.000 Zeichen → exakt `PDF_MAX_ZEICHEN` Zeichen, `gekuerzt=True`);
   leere Seite → `ValueError` mit „Textebene"; kaputte Datei → `ValueError`.
2. `_auswerten` mit PDF: Ollama-Body ohne `images`, `content` beginnt mit `PROMPT_TEXT`,
   Ergebnis `quelle == "pdf_text"`, Kategorie-Zuordnung wie beim Foto.
3. `_auswerten` mit JPG unverändert: `images` weiterhin vorhanden, `content == PROMPT`,
   `quelle == "foto"`.
4. Endpunkt-Ebene (`auswerten_anfordern` + `_verarbeite_naechsten_auftrag`, gleiches Muster wie
   `test_beleg_auswertung.py`): PDF wird als Auftrag angenommen (`status="offen"`), ein
   Scan-PDF ohne Textebene endet in `status="fehler"` mit der Meldung „... Textebene ...", ohne
   dass `_ollama_aufruf` überhaupt aufgerufen wird.

Test-PDFs werden zur Laufzeit im Temp-Ordner erzeugt (siehe Abweichungen), keine Binärdateien im
Repo. `FINANZ_DB` immer auf eine Wegwerf-Datei unter `%TEMP%` gesetzt, `FINANZ_TEST_AUTH_BYPASS`
nirgends in der Suite gesetzt (nur beim manuellen Live-Test auf Port 8072, außerhalb der Suite).
Ollama wird in allen automatisierten Tests über `patch.object(auswertung, "_ollama_aufruf", ...)`
gemockt.

`node --check static-neu/pages/belege.js` → ohne Ausgabe (Syntax OK).

Bestehende Tests `test_beleg_auswertung.py` und `test_p43_foto.py` weiterhin grün (einzeln
geprüft, siehe unten).

### Gesamtsuite

`FINANZ_DB=%TEMP%\p71-suite.db` (Datei vorher gelöscht),
`C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Scripts\python.exe -m unittest discover -s tests`
im Worktree.

**Ergebnis: 461 Tests, OK, 1 übersprungen.** Volle Ausgabe in `docs/neubau/berichte/P71-tests.txt`.

## Echttest (echtes Modell, ein Aufruf)

Eigene Wegwerf-Instanz auf Port 8072 (`FINANZ_DB` unter `%TEMP%`, `FINANZ_INSTANZ=test`,
`FINANZ_TEST_AUTH_BYPASS=1` nur dort), `FINANZ_OLLAMA_MODEL=qwen3.5:4b` gegen
`http://127.0.0.1:11434`. Selbst erzeugtes Text-PDF einer fiktiven Rechnung
(„Musterhandwerk GmbH", 3 Positionen, Gesamt 72,50 EUR) per `curl` hochgeladen und Auswertung
angefordert.

**Ergebnis nach ca. 26 s, ein einziger Ollama-Aufruf:**

```json
{
  "haendler": "Musterhandwerk GmbH",
  "datum": "2026-09-11",
  "positionen": [
    {"text": "Montage Steckdosen", "betrag_cent": 4500, "mwst_prozent": null},
    {"text": "Material Kabel", "betrag_cent": 1250, "mwst_prozent": null},
    {"text": "Anfahrt", "betrag_cent": 1500, "mwst_prozent": null}
  ],
  "gesamt_cent": 7250,
  "quelle": "pdf_text"
}
```

Händler, Datum (11.09.2026 → ISO korrekt), alle drei Beträge und der Gesamtbetrag stimmen exakt
mit der fiktiven Rechnung überein; `quelle: "pdf_text"` bestätigt den neuen Zweig. Kategorien
blieben `null`, weil in der frischen Wegwerf-DB keine Kategorien für die verwendete Sparte
angelegt waren (kein Befund, nur fehlende Testdaten). Instanz danach beendet (`kill`), keine
laufenden Prozesse mehr auf Port 8072.

## Abweichungen von der Karte (mit Begründung)

1. **pypdf-Version:** Die Karte sagt „aktuelle stabile Version nehmen"; der spätere Auftrag
   pinnt explizit `pypdf==6.18.1`. Diese exakte Version wurde installiert und eingetragen —
   spätere, konkretere Vorgabe hat Vorrang.
2. **Test-PDF-Erzeugung:** Die Karte schlägt vor, Test-PDFs „mit pypdf `PdfWriter` und einer
   Textseite" zu erzeugen. `pypdf.PdfWriter` bietet dafür keine High-Level-API (kein
   Text-Zeichnen wie bei reportlab/fpdf2). Die Testhilfsfunktion `_text_pdf` in
   `tests/test_p71_pdf.py` nutzt daher `PdfWriter.add_blank_page` und baut den
   Content-Stream (Helvetica-Font-Objekt + `BT ... Tj ET`-Operatoren) von Hand über
   `pypdf.generic`-Objekte und die (nicht-öffentliche) Methode `_add_object`. Damit bleibt es
   bei „nur pypdf, keine neue Test-Abhängigkeit", erzeugt aber tatsächlich extrahierbaren Text
   (verifiziert). Funktional entspricht das der Vorgabe, nur der Weg dorthin ist technisch
   anders als die Kurzbeschreibung in der Karte nahelegt.
3. **Frontend-Umfang kleiner als erwartet:** Die Karte nennt als Punkt „Knopf nicht mehr auf
   Bilder beschränkt". Der Datei-Input akzeptierte PDF bereits seit P43 (`accept` enthält
   `.pdf`), und der Upload-Code prüft die Endung clientseitig nicht. Es gab also nichts zu
   entsperren; nur die beiden tatsächlich fehlenden Anzeigen (`quelle`, Fehlermeldung im
   Prüf-Dialog/Statuszeile) wurden ergänzt.
4. **`app/routers/beleg_auswertung.py` unverändert:** Die Karte nennt „Fehlermeldung
   durchreichen, Endung zulassen" als Auftrag für diese Datei. Geprüft: `auswerten_anfordern`
   prüft die Endung nicht (das war schon vor P71 so, die Prüfung sitzt ausschließlich in
   `_auswerten`), und `_verarbeite_naechsten_auftrag` reicht `str(exc)` bereits unverändert als
   `fehler` durch. Es gab nichts zu ändern; keine Zeile in dieser Datei angefasst.

## Offene Punkte

- Kein Test für den Fall, dass `pypdf` zur Laufzeit fehlt (ImportError-Zweig in `_pdf_text`) —
  wäre nur über Mocking von `builtins.__import__` möglich und erschien angesichts der
  Geringfügigkeit nicht lohnend; der Codepfad ist trivial (drei Zeilen, direkt lesbar).
  Nicht getestet.
- Kamera-Aufnahme/echte Browser-Interaktion mit PDF-Auswahl wurde nicht geprüft (Browser war
  laut Auftrag belegt) — nur API-Ebene (`curl`) und `node --check`.
- Mehrseitige PDFs mit **echtem** Modellaufruf (>1 Seite, >5 Seiten) wurden nicht gegen das echte
  Modell getestet, nur gegen den Mock (Punkt 1 der Tests) — aus Sparsamkeit beim GPU-Zugriff
  (nur ein Echttest laut Auftrag).
- `docs/BETRIEB-UND-ARCHITEKTUR.md` Abschnitt 11 ist weiterhin „noch nicht ausgeführt" —
  der ergänzte `pip install -r requirements.txt`-Schritt ist nur dokumentiert, nicht auf CT 101
  ausgeführt (das war auch nicht Teil dieses Pakets).

## Nicht angefasst (wie gefordert)

Kein OCR, kein Seiten-Rendering, keine Migration, keine E-Mail-Anbindung, kein Eingriff in den
Foto-Weg außer der gemeinsamen Prompt-Zerlegung (Foto-Prompt-Wortlaut ist byte-identisch zum
vorherigen Stand). Keine Änderungen außerhalb des Worktrees außer `pip install` ins venv des
Hauptklons. Nichts unter `Z:\` angefasst. Ports 8051–8056 nicht verwendet (eigene Instanz auf
8072). Ollama lief durchgehend weiter, nicht angehalten.
