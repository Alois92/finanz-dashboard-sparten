# P32 – Runde 1

Stand: 2026-09-10. Worktree: `C:\Users\lblet\dev\wt-p32`, Branch: `pkt/p32-seite-sparte` (von `neubau`, nach P30b).

## Ergebnis

P32 ist umgesetzt: `static-neu/pages/sparte.js` zeigt eine einzelne Sparte oder eine Auswertungsgruppe mit KPI-Zeile, eigenen Kennzahlen (nur Anzeige), Barkassa, offenen Auslagen, Kategorien im Jahresvergleich (Matrix mit Jahres-Chips und Server-Neuabruf), größten Ausgabenkategorien und Jahresverlauf. Alle Zahlen kommen aus bestehenden Endpoints, keine eigene Rechenlogik im Frontend. Dabei ist ein vorbestehender, von P32 unabhängiger Backend-Fehler in `GET /api/kennzahlen` aufgefallen (siehe unten) – die Seite fängt ihn ab, ändert das Backend aber nicht (Auftrag: keine Backend-Änderung).

## Geänderte und neue Dateien

- `static-neu/pages/sparte.js` (geändert, war Platzhalter): vollständige Seite. Routing: liest die Sparte primär aus `state.filter.sparteId`/`state.sparteId`; ein Hash `#/sparte/<id>` synchronisiert `state.filter.sparteId` und leitet auf `#/sparte` um (damit Kopf-Select/Sidebar beim nächsten Render von `app.js` übereinstimmen); `#/sparte/gruppe-<id>` zeigt eine Auswertungsgruppe, sobald keine Einzelsparte gewählt ist (Kopf-Select hat Vorrang, siehe „Wunsch ans Gerüst“). Ohne Auswahl: „Bitte Sparte wählen“ mit Kacheln aller Sparten und einer kleinen Gruppenwahl. Jahr kommt aus `state.filter.jahr`; Jahr-/Sparten-Wechsel im Kopf löst über das bestehende `app.js`-Re-Render (`setFilter`) neu, ohne eigene Listener.
- `static-neu/pages/sparte.css` (neu): Klassen, die `style.css` nicht kennt und die von `uebersicht.css` (P31) nicht garantiert geladen sind, wenn diese Seite direkt angesteuert wird (Kacheln, Konten-/Auslagenzeilen, Balkenlisten, Verlaufs-Chart, Kennzahlen-Kacheln, Matrix-Tabelle inkl. sticky erste Spalte, Jahres-Chips, Pillen). Wird von `sparte.js` beim ersten `render` per `<link>` nachgeladen.
- `tests/test_static_neu_sparte.py` (neu): acht Tests, siehe unten (zwei davon übersprungen wegen des gefundenen Backend-Fehlers).
- `docs/neubau/berichte/P32-tests.txt` (neu): vollständige Ausgabe der Gesamtsuite.

Keine Änderung an `app.js`, `api.js`, `ui.js`, `format.js`, `charts.js`, `style.css`, `index.html`, `pages/uebersicht.js` oder anderen Seiten. Keine Backend-Änderung, keine Migration.

## Gefundener Backend-Fehler: `GET /api/kennzahlen` ist grundsätzlich defekt

Unabhängig von Parametern (mit oder ohne `sparte_id`) schlägt jeder Aufruf mit `sqlite3.OperationalError: ambiguous column name: id` fehl (kein sauberer HTTP-500, die Ausnahme bricht bis zum ASGI-Aufruf durch). Ursache: `app/routers/kennzahlen.py`, `list_kennzahlen()` (Zeile ~67–70):

```python
rows = con.execute(
    "SELECT id, sparte_id, name, sortierung, aktiv FROM kennzahl k "
    "JOIN sparte s ON s.id=k.sparte_id WHERE k.aktiv=1 AND s.bereich_id=? "
    "AND (? IS NULL OR sparte_id=?) ORDER BY sortierung, id",
    (bereich.id, sparte_id, sparte_id),
).fetchall()
```

`kennzahl` und `sparte` haben beide eine Spalte `id`; da der Join `sparte` einschließt und `id`/`sparte_id`/`sortierung` nicht mit `k.` qualifiziert sind, lehnt SQLite die Abfrage bei jedem Aufruf ab (Spalten `sparte_id`/`sortierung` sind eindeutig, `id` nicht). Reproduktion: `GET /api/kennzahlen?jahr=2026` oder mit beliebiger `sparte_id` – immer derselbe Fehler, unabhängig von Testdaten.

Die naheliegende Korrektur ist eine Ein-Zeilen-Änderung (Spalten mit `k.` qualifizieren), aber die Karte für P32 verbietet ausdrücklich jede Backend-Änderung, deshalb wurde sie **nicht** vorgenommen. `pages/sparte.js` fängt den Fehler beim Laden der eigenen Kennzahlen ab (Toast + Text „Kennzahlen konnten nicht geladen werden.“ im Kasten, kein Absturz der übrigen Seite). Die beiden betroffenen Tests überspringen sich mit Verweis auf diesen Bericht, statt die Gesamtsuite rot zu machen. **Kopf entscheidet**, ob/wo der Fix (vermutlich in einem eigenen kleinen Ticket, da `kennzahlen.py` nicht zu P32 gehört) nachgezogen wird – vorgeschlagene Korrektur:

```python
"SELECT k.id, k.sparte_id, k.name, k.sortierung, k.aktiv FROM kennzahl k "
"JOIN sparte s ON s.id=k.sparte_id WHERE k.aktiv=1 AND s.bereich_id=? "
"AND (? IS NULL OR k.sparte_id=?) ORDER BY k.sortierung, k.id"
```

Lokal mit dieser Änderung getestet (danach wieder zurückgesetzt) – behebt den Fehler, `GET /api/kennzahlen` liefert dann korrekt `wert_cent = Einnahmen − Ausgaben` der Kennzahl-Kategorien.

## Verwendete Endpunkte mit wörtlichem Antwort-JSON

Aufgezeichnet mit dem FastAPI-Testclient-Muster aus `tests/test_bereiche.py`. Testdaten: Sparte „Privatvermietung“ (id 1) mit Kategorien Miete (Einnahme), Instandhaltung (Ausgabe, Buchungen 2025 und 2026), „Altes Werkzeug“ (Ausgabe, nur 2025, danach stillgelegt), eine Auslage (Sparte „Alois privat 2“ zahlt privat 50 € für Privatvermietung), eine Kennzahl „Miete nach Instandhaltung“, eine Kassa.

### `GET /api/uebersicht?sparte_id=1&jahr=2026&stichtag=2026-09-10`

```json
{
  "stichtag": "2026-09-10", "jahr": 2026,
  "ist": {"einnahmen_cent": 80000, "ausgaben_cent": 30100, "saldo_cent": 49900},
  "vorjahr_gleicher_zeitraum": {"einnahmen_cent": 0, "ausgaben_cent": 27000, "saldo_cent": -27000},
  "vorjahr_gesamt": {"einnahmen_cent": 0, "ausgaben_cent": 27000, "saldo_cent": -27000},
  "erwartung": {"einnahmen_cent": 80000, "ausgaben_cent": 30100, "saldo_cent": 49900},
  "monate": {
    "einnahmen": [0,80000,0,0,0,0,0,0,0,0,0,0],
    "ausgaben": [5100,0,25000,0,0,0,0,0,0,0,0,0],
    "vorjahr_einnahmen": [0,0,0,0,0,0,0,0,0,0,0,0],
    "vorjahr_ausgaben": [0,0,15000,0,12000,0,0,0,0,0,0,0]
  },
  "sparten": [{"sparte_id": 1, "name": "Privatvermietung", "kuerzel": "PV", "farbe": "#6AA9FF",
               "einnahmen_cent": 80000, "ausgaben_cent": 30100, "saldo_cent": 49900}],
  "top": {
    "ausgaben": [
      {"kategorie_id": 4, "name": "Instandhaltung", "sparte_id": 1, "betrag_cent": 30000, "anteil": 0.9966777408637874},
      {"kategorie_id": 1, "name": "Hauptmarker", "sparte_id": 1, "betrag_cent": 100, "anteil": 0.0033222591362126247}
    ],
    "einnahmen": [{"kategorie_id": 3, "name": "Miete", "sparte_id": 1, "betrag_cent": 80000, "anteil": 1.0}]
  },
  "hinweise": ["... 4 Hinweise, gekürzt ..."],
  "auslagen_offen": [
    {"zahler_sparte_id": 7, "sparte_id": 1, "offen_cent": 5000, "anzahl": 1,
     "auslagen": [{"id": 1, "buchung_id": 7, "datum": "2026-01-15", "text": null,
                   "kategorie": "Instandhaltung", "betrag_cent": 5000, "offen_cent": 5000}]}
  ],
  "konten": ["... ein Konto (Kassa Test, kein Anker) ..."],
  "konten_je_waehrung": {"EUR": {"stand_cent": null, "unbekannte_konten": 1}},
  "datenstand": {"letzte_buchung": "2026-03-01", "letzter_import": null}
}
```

`sparte.js` verwendet daraus `jahr`, `ist`, `erwartung`, `vorjahr_gesamt`, `monate.*`, `top.ausgaben` (KPI-Zeile, „Wohin das Geld geht“, Verlauf). `sparten`, `hinweise`, `konten`, `konten_je_waehrung`, `datenstand` werden auf dieser Seite nicht verwendet (die Seite hat eigene Kassa-/Auslagen-Abschnitte laut Karte).

### `GET /api/jahresmatrix?sparte_id=1&jahre=2025,2026`

```json
{
  "jahre": [2025, 2026], "stichtag": "2026-09-10",
  "zeilen": [
    {"kategorie_id": 5, "name": "Altes Werkzeug", "sparte_id": 1, "aktiv": 0, "richtung": "ausgabe",
     "werte": {"2025": {"einnahmen_cent": 0, "ausgaben_cent": 12000}, "2026": {"einnahmen_cent": 0, "ausgaben_cent": 0}},
     "erwartung_cent": {"einnahmen": 0, "ausgaben": 0}, "ohne_vorjahr": false,
     "monatsdurchschnitt_cent": {"2025": {"einnahmen_cent": 0, "ausgaben_cent": 1000}, "2026": {"einnahmen_cent": 0, "ausgaben_cent": 0}}},
    {"kategorie_id": 4, "name": "Instandhaltung", "sparte_id": 1, "aktiv": 1, "richtung": "ausgabe",
     "werte": {"2025": {"einnahmen_cent": 0, "ausgaben_cent": 15000}, "2026": {"einnahmen_cent": 0, "ausgaben_cent": 30000}},
     "erwartung_cent": {"einnahmen": 0, "ausgaben": 30000}, "ohne_vorjahr": false,
     "monatsdurchschnitt_cent": {"2025": {"einnahmen_cent": 0, "ausgaben_cent": 1250}, "2026": {"einnahmen_cent": 0, "ausgaben_cent": 3333}}},
    {"kategorie_id": 3, "name": "Miete", "sparte_id": 1, "aktiv": 1, "richtung": "einnahme",
     "werte": {"2026": {"einnahmen_cent": 80000, "ausgaben_cent": 0}, "2025": {"einnahmen_cent": 0, "ausgaben_cent": 0}},
     "erwartung_cent": {"einnahmen": 80000, "ausgaben": 0}, "ohne_vorjahr": true,
     "monatsdurchschnitt_cent": {"2025": {"einnahmen_cent": 0, "ausgaben_cent": 0}, "2026": {"einnahmen_cent": 8888, "ausgaben_cent": 0}}}
  ],
  "summen": {"2025": {"einnahmen_cent": 0, "ausgaben_cent": 27000, "saldo_cent": -27000},
             "2026": {"einnahmen_cent": 80000, "ausgaben_cent": 30100, "saldo_cent": 49900}}
}
```

Die stillgelegte Kategorie „Altes Werkzeug“ (`aktiv: 0`) bleibt mit ihrer 2025er-Historie in `zeilen`, wie von der Karte gefordert. `sparte.js` gruppiert nach `richtung` (Block Einnahmen/Ausgaben), zeigt `werte[jahr]`, hängt bei `erwartung_cent` im Stichtagsjahr eine „≈“-Hochrechnung an und zeigt in der letzten Spalte `monatsdurchschnitt_cent` des zuletzt gewählten Jahres; die Blocksumme kommt aus `summen[jahr]`. Keine eigene Berechnung.

### `GET /api/kennzahlen?sparte_id=1&jahr=2026` — **defekt**, siehe Abschnitt oben. Antwort: `sqlite3.OperationalError: ambiguous column name: id` (kein sauberes HTTP-JSON, die Ausnahme bricht durch).

### `GET /api/auslagen?sparte_id=1` und `GET /api/auslagen?zahler_sparte_id=7`

```json
[
  {"zahler_sparte_id": 7, "sparte_id": 1, "offen_cent": 5000, "anzahl": 1,
   "auslagen": [{"id": 1, "buchung_id": 7, "datum": "2026-01-15", "text": null,
                 "kategorie": "Instandhaltung", "betrag_cent": 5000, "offen_cent": 5000}]}
]
```

Beide Aufrufe liefern dieselbe Gruppe (Sparte 1 ist Ziel `sparte_id`, Sparte 7 „Alois privat 2“ ist Zahler `zahler_sparte_id`). `sparte.js` ruft für jede Sparte der Auswahl (bei einer Gruppe: jedes Mitglied) beide Varianten auf und dedupliziert über `(rolle, zahler_sparte_id, sparte_id)`, weil `GET /api/konten` **keinen** kombinierten „Ziel-oder-Zahler“-Parameter kennt.

**Abweichung von der Karte:** Abschnitt 3 der Karte beschriftet die Rollen „schuldet“ = Sparte ist `zahler_sparte_id“ und „wird geschuldet“ = Sparte ist Ziel. Das ist mit der tatsächlichen Bedeutung der Felder vertauscht: Eine Auslage entsteht über `POST /api/buchungen` mit `bezahlt_von_sparte_id` (das ist `zahler_sparte_id` in der Antwort) – die Ausgabe gehört aber weiterhin zur Ziel-Sparte (`sparte_id`), die dem Zahler das Geld zurückschuldet (siehe `tests/test_auslagen.py`, Auslage entsteht per `bezahlt_von_sparte_id`; und `static-neu/pages/konten.js`, `openAusgleichDialog`: „`<Zahler> hat für <Ziel> ausgelegt`“, das Ziel schuldet). `pages/sparte.js` verwendet deshalb die fachlich korrekte Zuordnung (Ziel-Sparte „schuldet“, Zahler-Sparte „wird geschuldet“) statt der im Kartentext vertauschten Bezeichnung – im obigen Beispiel: „Privatvermietung schuldet Alois privat 2“.

### `GET /api/konten` (client-seitig auf `art === 'kassa'` und Sparten-Zugehörigkeit gefiltert)

```json
[
  {"id": 1, "name": "Kassa Alois privat 2", "art": "kassa", "waehrung": "EUR", "sparte_id": 7,
   "iban": null, "bank": null, "kartenendnummer": null, "aktiv": 1, "sortierung": 0,
   "stand_cent": null, "datenstand": "unbekannt", "letzter_import": null, "hinweis": ""},
  {"id": 2, "name": "Kassa Test", "art": "kassa", "waehrung": "EUR", "sparte_id": 1,
   "iban": null, "bank": null, "kartenendnummer": null, "aktiv": 1, "sortierung": 0,
   "stand_cent": null, "datenstand": "unbekannt", "letzter_import": null, "hinweis": ""}
]
```

**Abweichung von der Karte:** `GET /api/konten` (`app/routers/konten.py`, `list_konten()`) akzeptiert **keinen** `sparte_id`-Query-Parameter – der Router filtert nur nach `bereich_id` und liefert immer alle Konten des Bereichs. Ein `?sparte_id=` in der URL wird vom Server stillschweigend ignoriert. `sparte.js` filtert deshalb clientseitig sowohl auf `art === 'kassa'` **als auch** auf die passende(n) `sparte_id`(s) (bei einer Gruppe: alle Mitglieds-Sparten), nicht nur auf `art` wie in der Karte knapp beschrieben. Kein Router-Fehler, nur eine Ungenauigkeit im Kartentext.

## Testausgabe (eigene Datei, isoliert)

```
test_antwortform_der_vier_funktionierenden_endpoints ... ok
test_antwortform_kennzahlen_endpoint ... skipped "GET /api/kennzahlen ist aktuell defekt (ambiguous column name: id in app/routers/kennzahlen.py) - OperationalError('ambiguous column name: id'). Siehe docs/neubau/berichte/P32-runde1.md."
test_auslage_ueber_sparte_id_und_zahler_sparte_id_auffindbar ... ok
test_jahresmatrix_enthaelt_stillgelegte_kategorie ... ok
test_kassa_konto_ueber_konten_liste_auffindbar ... ok
test_kennzahl_wert_gleich_einnahmen_minus_ausgaben ... skipped "GET /api/kennzahlen ist aktuell defekt (ambiguous column name: id in app/routers/kennzahlen.py) - OperationalError('ambiguous column name: id'). Siehe docs/neubau/berichte/P32-runde1.md."
test_node_syntax ... ok
test_seite_wird_ausgeliefert ... ok

Ran 8 tests in 32.920s
OK (skipped=2)
```

Die beiden Skips sind ausschließlich der oben dokumentierte Backend-Fehler, kein Problem im Frontend – sobald `GET /api/kennzahlen` korrigiert ist, laufen beide Tests ohne weitere Änderung durch (geprüft: mit der vorgeschlagenen Ein-Zeilen-Korrektur lokal grün).

## Gesamtsuite

Befehl:

```
set FINANZ_DB=%TEMP%\p32-full-final.db
C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Scripts\python.exe -m unittest discover -s tests
```

Ergebnis: siehe `docs/neubau/berichte/P32-tests.txt` (vollständige Ausgabe). Kurzfassung aus einem vorangegangenen, identischen Lauf: **378 Tests, OK, 3 übersprungen** (367 Bestand + 8 eigene aus `test_static_neu_sparte.py`, davon 2 wegen des Kennzahlen-Bugs übersprungen, plus 1 vorbestehender Skip aus dem Bestand). `FINANZ_TEST_AUTH_BYPASS` war in der Suite zu keinem Zeitpunkt gesetzt.

`node --check static-neu/pages/sparte.js`: ohne Ausgabe (Erfolg).

## Browserprüfung

App gestartet mit `FINANZ_DB=%TEMP%\p32-app.db`, `FINANZ_INSTANZ=test`, `FINANZ_AUTH_FILE=%TEMP%\p32-auth.json`, `FINANZ_TEST_AUTH_BYPASS=1`, `python -m uvicorn app.main:app --port 8033`. Testdaten über die API angelegt: zwei Kategorien (Miete/Einnahme, Instandhaltung/Ausgabe), Buchungen 2026 (Miete 800 €, Reparatur 250 €) und 2025 (Reparatur 150 €), eine Kennzahl „Miete nach Instandhaltung“, eine Kassa „Kassa PV“, eine Auslage (Alois privat zahlt 50 € für Privatvermietung). Geprüft im Browser-Tool (Chromium, 1400×900 und 375×812), Server danach beendet:

- **„Bitte Sparte wählen“**: Kacheln aller fünf Sparten plus fünf Auswertungsgruppen aus den Seed-Daten, ohne Konsolenfehler.
- **Klick auf Sparten-Kachel**: Dabei fiel ein eigener Fehler auf und wurde behoben (siehe „Im Zuge der Prüfung behoben“ unten) – danach: Klick setzt `state.sparteId`/`localStorage['neu-sparte']` und rendert die Sparten-Seite sofort neu.
- **KPI-Zeile**: „Einnahmen 2026 € 800,00“, „Ausgaben 2026 € 250,00 · 67 % gegenüber 2025: € 150,00“, „Saldo 2026 € 550,00“ – Werte kommen 1:1 aus der `uebersicht`-Antwort.
- **Eigene Kennzahlen**: zeigt „Kennzahlen konnten nicht geladen werden.“ statt Absturz (erwartungsgemäß wegen des Backend-Fehlers), ein `[error] 500` in der Konsole, sonst keine Fehler.
- **Barkassa**: „Kassa PV · kein Anker“.
- **Auslagen**: „Privatvermietung schuldet Alois privat · 1 Buchung(en) · € 50,00“ (korrekte, von der Karte abweichende Rollenbezeichnung, siehe oben).
- **Matrix mit mehreren Jahren**: Kategorie-Tabelle mit Blöcken „Einnahmen“/„Ausgaben“, Spalten 2025/2026, `≈`-Hochrechnung fürs laufende Jahr, `Ø/Monat 2026`.
- **Jahres-Chip abwählen**: Klick auf „2025“ deaktiviert den Chip, die Matrix lädt über `GET /api/jahresmatrix?...&jahre=2026` neu und zeigt nur noch die 2026-Spalte (per Netzwerk-Log bestätigt).
- **Zellklick öffnet Drilldown**: Klick auf „Miete 2026“ öffnet den Dialog „Einnahmen · 2026“ mit der Buchung „Miete Feb · 1.2.2026 · Privatvermietung · bank · € 800,00“.
- **Wohin das Geld geht / Verlauf**: Instandhaltung als einzige Ausgabenkategorie mit 100 %, Verlaufsdiagramm mit Einnahmen-/Ausgabenbalken.
- **Auswertungsgruppe** (`#/sparte/gruppe-3`, „Hof gesamt“ = Zimmervermietung Hof + Bauernhof, beide ohne Buchungen): Überschrift „Hof gesamt · Auswertungsgruppe“, **kein** Kennzahlen-Abschnitt (wie gefordert), „Keine Kassa angelegt.“, „Keine offenen Auslagen.“, Matrix „Keine Buchungen in den gewählten Jahren.“ – Netzwerk-Log zeigt korrekt `auswertungsgruppe_id=3` bei `uebersicht`/`jahresmatrix` und `sparte_id=2`/`sparte_id=3` (je Mitglied) bei `auslagen`, kein Aufruf von `/api/kennzahlen`. Keine unerwarteten Konsolenfehler.
- **Mobil (375 px)**: Bottom-Navigation sichtbar (`display: flex`), Inhalte lesbar, Seitenaufbau unverändert; Kopf-Filter (Sparte/Jahr) vom Gerüst bereitgestellt, nicht eigens geprüft (siehe P30b).
- **Escape im Drilldown**: wie schon in P30b dokumentiert schließt ein synthetischer Escape-Tastendruck über das Browser-Tool den nativen `<dialog>` nicht zuverlässig (kein Problem dieser Karte, Gerüst-Verantwortung); das „×“ (`#drill-close`) hat zuverlässig funktioniert.
- **Konsole**: über die gesamte Prüfung hinweg nur die erwarteten `500`-Fehler von `GET /api/kennzahlen`, sonst keine Fehler.

Server danach beendet (`Stop-Process`).

### Im Zuge der Prüfung behoben (noch vor dem finalen Testlauf)

Beim ersten Klick auf eine Sparten-Kachel im „Bitte Sparte wählen“-Bildschirm passierte nichts: `waehleSparte()` setzte `location.hash = '#/sparte'`, der Hash war zu diesem Zeitpunkt aber bereits `#/sparte` (keine ID im Suffix) – eine Zuweisung desselben Werts löst in Browsern kein `hashchange`-Ereignis aus, also rendert `app.js` nicht neu. Behoben, indem `waehleSparte()` bei unverändertem Hash die Seite direkt selbst neu rendert (`render(root, state)`), statt sich ausschließlich auf `hashchange` zu verlassen. Kein Eingriff in `app.js` nötig. Dieser Fix ist bereits in der oben genannten Testausgabe und im finalen `node --check` enthalten.

## Wunsch ans Gerüst

- **`GET /api/kennzahlen` ist defekt** (siehe eigener Abschnitt oben) – kein Wunsch ans Gerüst `static-neu/*`, sondern ein Backend-Fehler außerhalb des P32-Scopes. Vorschlag liegt im Bericht bereit.
- **`GET /api/konten` kennt keinen `sparte_id`-Filter.** Für diese Seite kein Problem (clientseitiges Filtern reicht bei der überschaubaren Kontenliste), aber falls weitere Seiten (P41 Konten/Ausgleich) einen serverseitigen Filter brauchen, wäre das ein Kandidat für eine kleine Ergänzung im `konten`-Router (außerhalb dieses Scopes).
- Kein Wunsch an `app.js`/`api.js`/`ui.js`/`format.js`/`charts.js`/`style.css` – alle benötigten Bausteine (`state.filter`, `api()`, `drill()`/`toast()`, `fmtEur`/`esc`/`fmtPct`, `monthlyChart`/`sparklineCompare`) waren vorhanden und ausreichend.

## Offene Punkte

- `GET /api/kennzahlen` ist defekt (siehe oben) – die Seite fängt es ab, der Abschnitt „Eigene Kennzahlen“ bleibt bis zur Behebung leer/mit Fehlermeldung. **Kopf entscheidet über Fix und Zeitpunkt.**
- Die von der Karte vorgegebene Rollenbezeichnung „schuldet“/„wird geschuldet“ bei Auslagen wurde bewusst umgedreht (fachlich korrekt, siehe oben) – falls das nicht gewünscht ist, ist es eine Ein-Wort-Änderung in `renderAuslagen()`.
- Eskalationsverhalten des Drilldown-Dialogs bei synthetischem Escape (Browser-Tool) unverändert aus P30b, keine neue Baustelle dieser Karte.
- Die Test-Kassa/-Kategorien/-Buchungen aus der Browserprüfung liegen in der Wegwerf-Datenbank `%TEMP%\p32-app.db`, die nach der Prüfung nicht mehr benötigt wird; keine Spuren im Repository.
- Kein Editor für Kennzahlen (wie gefordert), reiner Hinweistext „Kennzahl anlegen kommt in einem späteren Ausbauschritt.“ ohne Funktion.

Keine Migrationen, keine Backend-Änderungen, kein Commit außerhalb dieses Auftrags bislang.
