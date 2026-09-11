# P60b, P31b, P32b – drei kleine Schulden aus SCHULDEN.md

Datum: 11. September 2026. Umsetzung: Claude Sonnet 5. Zweig `pkt/p60b-p31b-kleinkram`, Worktree `wt-p60b`, abgezweigt von `neubau` (Stand `cab766b`). Keine Migration, keine Datei aus dem Bereich von P50b/P51 (`app/routers/buchungen.py`, `db/`, `pages/buchungen.js`, `beleg_auswertung.py`) angefasst.

## P60b — `GET /export/bericht` ohne `jahr` bei `profil_id`; Ausschluss-Dialog seitenweise

### Backend

`app/routers/export.py`, Funktion `jahresbericht`: `jahr` ist jetzt `str | None = None` statt Pflichtparameter. Ohne `profil_id` bleibt `jahr` weiterhin Pflicht (400 „jahr muss vierstellig sein“, wie vorher); mit `profil_id` wird `jahr` gar nicht mehr geprüft, weil dieser Zweig das Jahr ohnehin aus dem geladenen Profil nimmt (`_profil_bericht`/`_preview` lesen `profil['jahr']`). Der Hinweis aus der Aufgabenstellung „oder aus `von`/`bis`“ trifft auf diesen Endpunkt nicht zu – er kennt keine `von`/`bis`-Parameter, nur `jahr`, `sparte_id`, `profil_id`.

### Frontend

`static-neu/pages/export.js`, Funktion `ladeBuchungszeilen`: holt die Buchungen für den Ausschluss-Dialog jetzt in einer `do/while`-Schleife über `GET /api/buchungen` mit `cursor`/`naechster_cursor` (Muster aus `pages/buchungen.js`, nur lesend verwendet, diese Datei selbst wurde nicht angefasst). Seitenlimit von 1000 auf 100 gesenkt (deckt sich mit dem Limit, das `pages/buchungen.js` selbst verwendet) – bei mehr als 100 Buchungen im Zeitraum werden jetzt mehrere Seiten geholt, bis `naechster_cursor` leer ist, statt nach der ersten Seite abzubrechen. Der Hinweistext „Liste ist auf 1000 Zeilen begrenzt“ und das Feld `ctx.zeilenAbgeschnitten` sind entfallen, weil die Liste jetzt vollständig ist.

### Konflikt mit `tests/test_p60_export.py` (wichtig, bitte lesen)

`tests/test_p60_export.py::test_jahresbericht_mit_profil_id_braucht_weiterhin_jahr_parameter` dokumentierte ausdrücklich die alte Lücke und erwartet `422` (fehlender Pflichtparameter) für `GET /export/bericht?profil_id=…` ohne `jahr`. Nach dem Fix liefert derselbe Aufruf `200`. Der Auftrag verbietet ausdrücklich, `tests/test_p60_export.py` zu ändern – ich habe diese Datei **nicht angefasst**, wodurch dieser eine Test jetzt fehlschlägt (`422 != 200`). Das ist kein Seiteneffekt, sondern die zwangsläufige Folge des beauftragten Fixes: der alte Test prüfte exakt das gemeldete Fehlverhalten. Bitte entscheiden, ob der alte Test gelöscht/anpasst werden soll oder ob der Fix zurückgenommen werden soll – ich habe bewusst nicht eigenmächtig in die fremde Testdatei eingegriffen.

Neue Tests in `tests/test_p60b_export.py`: `GET /export/bericht` mit `profil_id` ohne `jahr` → 200; mit `profil_id` und `jahr` weiterhin 200; ohne `profil_id` und ohne/mit ungültigem `jahr` weiterhin 400. Textprüfung, dass `export.js` die Cursor-Schleife (`naechster_cursor`, `while (cursor)`) enthält und weder `limit: 1000` noch den alten Begrenzungstext „1000 Zeilen“. Eigener Beleg, dass `GET /api/buchungen` bei kleinem Limit über mehrere Seiten läuft (Cursor-Muster, dem `export.js` jetzt folgt). `node --check` für `export.js`.

## P31b — Hinweistexte ohne rohe Cent

`app/rechenbasis.py`, Funktion `hinweise()`: neue Hilfsfunktion `_euro_text(cent)` (gleiches Format wie `format.js`/`fmtEur`, z. B. „50,99 €“). Der `add()`-Helfer bekommt einen neuen optionalen Parameter `wert_cent`; jeder Hinweis trägt jetzt zusätzlich das Feld `wert_cent` (Zahl oder `None`, wenn der Hinweis keinen Geldbetrag meint). Die beiden Hinweise mit rohen Cent im Text sind korrigiert:

- `groesste_buchung`: „Größte Buchung: 5099 Cent.“ → „Größte Buchung: 50,99 €.“, `wert_cent=5099`.
- `auslagen_offen`: „Offene Auslagen: 12345 Cent.“ → „Offene Auslagen: 123,45 €.“, `wert_cent=12345`.

Die übrigen vier Hinweisarten (`kostenanstieg`, `kategorie_anteil`, `einnahme_fehlt`, `bankumsaetze_offen`) enthielten keine rohen Cent (Prozent, Monatsangabe, Anzahl) und bleiben unverändert; ihr `wert_cent` ist `None`. Das bestehende Ausblenden-Feld `wert` (Vergleichsbasis für `hinweis_aus.bis_wert`) ist unverändert geblieben, damit `hinweis_aus` und bestehende Tests (`tests/test_rechenbasis.py`) weiter funktionieren.

`static-neu/pages/uebersicht.js` musste **nicht** geändert werden: es zeigt schon `h.text` unverändert an (Zeile 171), wie in der Entscheidung aus der Aufgabenstellung vorgesehen.

Neue Tests in `tests/test_p31b_hinweise.py`: `groesste_buchung` und `auslagen_offen` liefern `wert_cent` als Zahl und `text` ohne „Cent“ mit Euro-Format; ein nicht-monetärer Hinweis (`kategorie_anteil`) bleibt mit `wert_cent=None`; Ausblenden über `wert` funktioniert weiterhin (Regressionstest zum bestehenden Verhalten aus `test_rechenbasis.py`).

## P32b — Gruppen-Hash gewinnt auch bei gewählter Sparte

`static-neu/pages/sparte.js`: neuer Modulzustand `gruppenZustand = {suffix: null}` merkt sich den zuletzt betretenen Gruppen-Hash-Suffix, um zwischen „Gruppe gerade betreten“ und „Nutzer wählt jetzt aktiv im Kopf eine Sparte, während die Gruppe schon offen ist“ zu unterscheiden – beide Fälle sehen an `state.sparteId` allein gleich aus.

`render()`: `gruppeId` wird jetzt unabhängig von `state.sparteId` aus dem Hash gelesen (vorher: `!state.sparteId ? parseGruppeId(suffix) : null`, das war der Fehler). Beim ersten Betreten eines Gruppen-Hashs mit noch gesetzter Sparte räumt die Seite `state.sparteId`, `state.filter.sparteId` und `localStorage('neu-sparte')` und löst wie `waehleSparte()` ein `hashchange` aus, damit Kopf-Select und Sidebar synchron „Alle Sparten“ zeigen. Wählt der Nutzer danach im Kopf aktiv eine Sparte, während derselbe Gruppen-Hash noch aktiv ist, entfernt die Seite beim nächsten Render das Gruppen-Suffix (`location.hash = '#/sparte'`) und zeigt die gewählte Einzelsparte.

Nur `static-neu/pages/sparte.js` geändert, `tests/test_static_neu_sparte.py` nicht angefasst. Neue Tests in `tests/test_p32b_gruppe.py`, Textprüfung analog zu den bestehenden statischen Tests (kein Browser/DOM in den Unit-Tests): die alte fehlerhafte Bedingung ist entfernt, `gruppenZustand` existiert, das Räumen beim Betreten und das Entfernen des Suffix bei aktiver Kopf-Wahl sind im Quelltext nachweisbar, `node --check`.

## Tests

Gesamtsuite (`FINANZ_DB=%TEMP%\p60b-test.db`, `python -m unittest discover -s tests`, kein Auth-Bypass):

```
Ran 413 tests in 182.7s
FAILED (failures=1, skipped=1)
```

413 = 397 (Bestand) + 16 eigene Tests (7 in `test_p60b_export.py`, 4 in `test_p31b_hinweise.py`, 5 in `test_p32b_gruppe.py`). 1 skipped wie erwartet (node-Umgebung o. ä., unverändert zum Bestand). Der einzige Fehlschlag ist der oben beschriebene, erwartete Konflikt in `tests/test_p60_export.py` (dokumentiert die jetzt behobene alte Lücke) – keine anderen Regressionen.

`node --check` für alle drei geänderten/neuen JS-Dateien: `static-neu/pages/export.js`, `static-neu/pages/sparte.js` – beide fehlerfrei.

## Browserprüfung

Testinstanz: `FINANZ_DB=%TEMP%\p60b-app.db`, `FINANZ_INSTANZ=test`, `FINANZ_AUTH_FILE=%TEMP%\p60b-auth.json`, `FINANZ_TEST_AUTH_BYPASS=1`, `python -m uvicorn app.main:app --port 8039`. Testdaten per API: eine Kategorie „P60b-Testkategorie“ in Sparte „Privatvermietung“, 210 Buchungsversuche für 2026 (167 tatsächlich in Sparte 1 gelandet, Rest der 210 in der Vorschau kommt aus vorhandenen Seed-Daten anderer Sparten), Exportprofil „Steuer“ automatisch angelegt.

| Prüfung | Ergebnis |
|---|---|
| Export-Bericht mit Profil ohne Jahr | `GET /export/bericht?bereich_id=1&profil_id=1` → 200 (vorher 422); mit zusätzlichem `jahr` weiterhin 200; ohne `profil_id` und ohne `jahr` weiterhin 400 |
| Ausschluss-Dialog, Cursor-Schleife | Netzwerk-Log zeigt zwei `GET /api/buchungen`-Aufrufe (erste Seite ohne Cursor, zweite mit `cursor=MjAyNi0wMi0xOHw3NA%3D%3D`); Dialog zeigt alle 167 Zeilen (`document.querySelectorAll('#ex-dlg-body tr').length === 167`), Seitenlimit dafür auf 100 gesenkt |
| Übersicht-Hinweise ohne „Cent“ | Hinweis „Größte Buchung: 12,10 €.“ statt „… Cent.“ |
| Gruppen-Hash mit gewählter Sparte | Kopf-Select auf „Privatvermietung“ gesetzt, dann direkt `#/sparte/gruppe-3` aufgerufen: Seite zeigt „Hof gesamt · Auswertungsgruppe“, Kopf-Select springt auf „Alle Sparten“, keine Sparte in der Sidebar aktiv (per DOM-Abfrage geprüft). Danach im Kopf „Zimmervermietung Hof“ gewählt: Hash sofort von `#/sparte/gruppe-3` auf `#/sparte` bereinigt, Seite zeigt die Einzelsparte |
| Konsole | keine Fehler in beiden Durchläufen (Export-Dialog, Sparte/Gruppe) |

Server danach beendet (Prozesse auf Port 8039 gekillt), Test-DB/Auth-Dateien im Temp-Verzeichnis gelöscht.

## Offene Punkte

1. **Konflikt in `tests/test_p60_export.py`** (siehe oben, Abschnitt P60b) – bewusst ungelöst, da die Aufgabenstellung diese Datei ausdrücklich sperrt. Die Gesamtsuite zeigt deshalb 1 Fehlschlag statt „grün“.
2. Das Seitenlimit in `ladeBuchungszeilen` (100) ist eine Annahme meinerseits, keine Vorgabe aus der Karte – bei Bedarf leicht anpassbar.
3. Keine Migration, keine neue Abhängigkeit, keine Geheimnisse.
