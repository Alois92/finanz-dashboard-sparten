# P30b – Runde 1

Stand: 2026-09-10. Worktree: `C:\Users\lblet\dev\wt-p30b`, Branch: `pkt/p30b-geruest-luecken` (von `neubau`, nach P30).

## Ergebnis

P30b ist umgesetzt. Die in `docs/neubau/SCHULDEN.md` benannten Gerüst-Lücken sind geschlossen: `state.filter` als zentrales Filterobjekt, `#year-select` mit `onchange`, `#sparte-select` (Kopf und Sidebar) mit Re-Render der aktiven Seite, `#filter-kategorie` befüllt und verdrahtet, sowie ein wiederverwendbarer Mehrschritt-Dialog (`wizard()`) in `ui.js`. Die sechs bestehenden Seiten funktionieren weiter; dort, wo sie die Lücke bisher lokal kompensiert hatten und jetzt doppelt reagiert hätten, wurde die lokale Kompensation entfernt.

## Geänderte Dateien

- `static-neu/app.js`: `state.filter = {jahr, sparteId, kategorieId}` (persistent über `neu-jahr`/`neu-sparte`/`neu-kategorie` in `localStorage`, analog zum bestehenden `neu-sparte`). Neue zentrale Funktion `setFilter(patch)` aktualisiert `state.filter` **und** die bestehenden Alias-Felder `state.sparteId`/`state.year` (die sechs Seiten aus P31 ff. lesen diese direkt; ein harter Umbau auf ausschließlich `state.filter` hätte alle sechs Seiten angefasst, was außerhalb des Auftragsscopes lag) und rendert die aktive Seite neu. `#year-select` und `#sparte-select` (Kopfzeile) rufen jetzt `setFilter` bei `onchange`. Die Sidebar-Sparten-Buttons rufen ebenfalls `setFilter` statt nur `drawSidebar()`. Neue Funktion `drawKategorieFilter()` befüllt `#filter-kategorie` aus `GET /api/kategorien` (mit `sparte_id`, falls eine Sparte gewählt ist; ohne Sparte alle Kategorien des Bereichs) und cached das Ergebnis über einen Schlüssel `bereichId:sparteId`, damit nicht bei jeder Seitennavigation ein Zusatzaufruf entsteht. `loadData()` gleicht `state.year` gegen `state.jahre` ab (wie bisher schon für `state.sparteId` gegen `state.sparten`) und hält `state.filter` synchron.
- `static-neu/ui.js`: neue exportierte Funktion `wizard({title, steps, onFinish})`. Nutzt den bestehenden `<dialog id="drill">`-Mechanismus (kein neues DOM-Element). Jeder Schritt hat `render(ctx)` (HTML), optional `validate(ctx)` (darf async sein, z. B. API-Aufruf; wirft bei Fehlern eine `Error` mit lesbarer `message`, die im Dialog angezeigt wird) und optional `lockBack: true` (blendet „Zurück“ für alle folgenden Schritte aus, für Schritte mit bereits ausgelöster Server-Wirkung). `validate()` kann `ctx.finishNow` setzen, um sofort zu `onFinish` zu springen, auch wenn noch Schritte übrig wären. Buttons „Zurück“/„Weiter“/„Abschließen“ (letzter Schritt). Escape schließt über den nativen `<dialog>`-Mechanismus (browserseitig, unabhängig von unserem Code).
- `static-neu/style.css`: `.wizard-nav` (Button-Leiste) und `.field-error` (bisher nur in `konten.css` definiert) global ergänzt, damit `wizard()` auch ohne seitenspezifisches CSS korrekt aussieht.
- `static-neu/pages/konten.js`: `openZaehlungDialog`/`zaehlungSchritt2` (das einzige echte, seitenlokal gebaute Mehrschritt-Formular im Bestand – Kassa zählen → bei Differenz Kategorie wählen und buchen) auf `wizard()` umgestellt und dadurch von zwei Funktionen auf eine verkürzt. Fachliche Logik (Zählung anlegen, bei Differenz 0 sofort abschließen, sonst passende Kategorien laden und die Buchung auslösen) ist unverändert, nur die Dialog-Mechanik kommt jetzt aus dem Gerüst.
- `static-neu/pages/uebersicht.js`: lokale Kompensation für `#year-select`, `#sparte-select`, `#filter-kategorie` (bisher: `bindOnce` + manuelles `hashchange`-Event) entfernt, weil `app.js` das jetzt zentral übernimmt und die Seite sonst doppelt neu gezeichnet hätte. `#filter-richtung`/`#filter-zahlungsart` bleiben lokal gebunden (kein Teil des zentralen Filterobjekts). `resetFilters()` und `goSparte()` setzen zusätzlich `state.filter.sparteId`/`state.filter.kategorieId`, sonst würde `app.js` beim nächsten Render die alten Werte wiederherstellen.
- `static-neu/pages/export.js`: `bindeGlobaleFilter()` (eigene `change`-Listener auf `#year-select`/`#sparte-select`/Sidebar-Sparten-Buttons, die die Seite erneut gerendert haben) entfernt – `app.js` löst das Re-Render jetzt zentral aus, die Seite hätte sich sonst zweimal neu aufgebaut.
- `static-neu/pages/buchungen.js`: eigene Befüllung von `#filter-kategorie` (`ladeKategorienFuerFilter`) und der zugehörige `onchange`-Handler entfernt – `app.js` befüllt die Auswahl jetzt zentral und ein Wechsel löst dort bereits ein volles Re-Render dieser Seite aus. Der „Filter zurücksetzen“-Knopf setzt zusätzlich `state.filter.kategorieId` zurück und räumt `localStorage['neu-kategorie']`.
- `tests/test_static_neu.py`: fünf neue Tests, die (wie die bestehenden Tests dieser Datei) den Inhalt der ausgelieferten JS-Dateien auf die neuen Exporte/Bindungen prüfen: `state.filter`/`neu-jahr`/`neu-kategorie` in `app.js`, `setFilter`/`#year-select`-Verdrahtung, `drawKategorieFilter`, `export function wizard` in `ui.js` (inkl. „Zurück“/„Abschließen“), und dass `konten.js` `wizard(` statt eines lokalen Zwei-Schritt-Dialogs nutzt.

## Was aus welcher Seite hochgezogen wurde

- **Jahr-/Sparten-/Kategoriewechsel mit Re-Render**: das Muster stammt aus `uebersicht.js` (P31), die dafür extra `bindOnce()` + ein manuell ausgelöstes `hashchange`-Event gebaut hatte, weil das Gerüst es nicht konnte. Das ist jetzt echter Gerüst-Code in `app.js` (`setFilter`); `uebersicht.js` nutzt nur noch die Alias-Felder, ohne eigene Verdrahtung für Jahr/Sparte/Kategorie.
- **`#filter-kategorie`-Befüllung**: `buchungen.js` (P50) hatte dafür schon eine eigene `ladeKategorienFuerFilter()`; die Logik (Kategorien nach Sparte laden, vorherigen Wert nur behalten, wenn noch gültig) ist als Vorbild in `drawKategorieFilter()` in `app.js` eingeflossen.
- **Mehrschritt-Dialog**: `bankimport.js` und `export.js` (wie im Auftrag als Kandidaten genannt) haben mehrere Dialoge, aber keinen echten Mehrschritt-Ablauf mit Zurück/Weiter – nur Einzelschritt-`drill()`-Formulare bzw. einen Ablehnen/Bestätigen-Dialog (`export.js`, „Belege fehlen“). Der einzige echte, lokal gebaute Zwei-Schritt-Ablauf war `konten.js`s Kassa-Zählung (`openZaehlungDialog` → bedingt `zaehlungSchritt2`). Diese Logik wurde in den neuen `wizard()` in `ui.js` gezogen; `konten.js` ruft jetzt nur noch `wizard({...})` auf.

## Absichtlich unverändert gelassen

- `#filter-richtung`/`#filter-zahlungsart` sind laut Auftrag nicht Teil der Gerüst-Lücke (nur Jahr/Sparte/Kategorie) und bleiben seitenlokal in `uebersicht.js`/`buchungen.js` gebunden.
- `erfassen.js`, `bankimport.js`, `konten.js` (außer der Zählung) haben eigene, seiteninterne Selects (z. B. Sparte im Erfassen-Formular), die nichts mit `#sparte-select`/`#year-select` im Kopf zu tun haben – unangetastet.
- `placeholder.js`, `belege.js`, `kategorien.js`, `sparte.js` sind reine Platzhalter ohne Filterbezug – unangetastet.

## Node-Syntaxprüfung

`node --check` für alle geänderten Dateien sowie zur Kontrolle für sämtliche `static-neu/*.js` und `static-neu/pages/*.js` – durchgehend ohne Ausgabe (Erfolg).

## Testausgabe

Befehl:

```
set FINANZ_DB=%TEMP%\p30b-test.db
C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Scripts\python.exe -m unittest discover -s tests
```

```
----------------------------------------------------------------------
Ran 367 tests in 175.252s

OK (skipped=1)
```

Die im Rohprotokoll enthaltenen Tracebacks (Backup-ACL-Simulation, PIL-Bildverkleinerung auf Test-Fixtures ohne echtes Bildformat, Recovery-Code ohne bestehende Auth-Datei) stammen aus absichtlich simulierten Fehlerpfaden anderer Test-Suiten und enden jeweils mit `ok`; sie stehen in keinem Zusammenhang mit P30b.

Die fünf neuen `test_static_neu.py`-Tests (`test_app_js_hat_zentrales_filterobjekt`, `test_app_js_verdrahtet_year_und_sparte_select_mit_setfilter`, `test_app_js_befuellt_filter_kategorie`, `test_ui_js_hat_wizard_export`, `test_konten_js_nutzt_wizard_statt_lokalem_zwei_schritt_dialog`) sind darin enthalten und liefen isoliert ebenfalls grün (8/8 in `tests.test_static_neu`).

## Browserprüfung

App gestartet mit `FINANZ_DB=%TEMP%\p30b-app.db`, eigener `FINANZ_AUTH_FILE`, `FINANZ_INSTANZ=test`, `python -m uvicorn app.main:app --port 8031`. Login über echtes Passwort (Auth-Datei mit `app.auth.hash_password`/`AuthConfigStore` wie `scripts/set_auth_password.py` vorbereitet, da `getpass` unter Windows nicht aus einer Pipe liest). `FINANZ_TEST_AUTH_BYPASS` wurde zu keinem Zeitpunkt gesetzt.

Geprüft unter `http://127.0.0.1:8031/neu/` (Chromium, Desktop 1440×900 und Mobil 375×812):

- **Jahr-Wechsel**: `#year-select` besitzt jetzt einen `onchange`, der `state.filter.jahr`/`state.year` setzt, in `localStorage['neu-jahr']` speichert und die aktive Seite neu rendert.
- **Sparten-Wechsel**: sowohl Kopf-Select `#sparte-select` als auch die Sidebar-Sparten-Buttons setzen die Sparte zentral und lösen ein Re-Render aus (vorher: nur `drawSidebar()`, die Seite blieb auf dem alten Filter stehen). Sichtbar an „Sparten · gefiltert“ mit nur der gewählten Sparte, „Filter aktiv: … zurücksetzen“-Zeile, aktiver Sidebar-Eintrag, `GET /api/kategorien?sparte_id=…` im Netzwerk-Log nach dem Wechsel.
- **Kategorie-Filter**: `#filter-kategorie` wird aus `GET /api/kategorien` befüllt (mit angelegter Testkategorie sichtbar geprüft), Auswahl setzt `state.filter.kategorieId`, speichert `localStorage['neu-kategorie']` und rendert neu; auf der Buchungen-Seite bleibt die Auswahl über die Navigation hinweg erhalten (Filterchip „Kategorie: … ×“).
- **Persistenz über Reload**: Sparte, Jahr und Kategorie bleiben nach einem vollständigen Seiten-Reload erhalten (`localStorage`).
- **`wizard()` in `konten.js`**: Kassa-Konto angelegt, Anfangsstand gesetzt, „Kassa gezählt, Differenz buchen“ geöffnet.
  - Schritt 1 (Datum/Betrag) → „Weiter“ zeigt bei ungültigem Betrag und bei Server-Fehlern (getestet: Zählung ohne Anker → 422 „Kassenstand ist ohne Anker unbekannt“) den Fehler im Dialog, ohne den Dialog zu schließen.
  - Mit Differenz (€ 50,00 gezählt, gerechnet € 0,00) → Schritt 2 zeigt Differenz, vorausgewählte Kategorie „Kassadifferenz“ (Namensvorauswahl funktioniert), kein „Zurück“-Button (lockBack korrekt aktiv), leere Kategorieauswahl wird mit „Keine Kategorie ausgewählt.“ abgelehnt, gültige Auswahl → „Abschließen“ bucht, schließt den Dialog und zeigt in „Zuletzt erfasst“ (Erfassen-Seite) die gebuchte Kassadifferenz (+ € 50,00).
  - Ohne Differenz (0,00 gezählt gegen 0,00 Anker) → `ctx.finishNow` überspringt Schritt 2 korrekt, Toast „Kassa gezählt: keine Differenz.“, Dialog schließt sofort.
- **Mobil (375 px)**: Start auf „Erfassen“ mit Bottom-Navigation, Kopf-Filter (Sparte/Jahr/Mehr Filter) vorhanden und funktionsfähig, „Zuletzt erfasst“ zeigt die per Wizard gebuchte Kassadifferenz.
- **TEST-INSTANZ-Banner**: sichtbar.
- **Browser-Konsole**: keine Fehler außer dem einen erwarteten 422 aus dem absichtlichen Ohne-Anker-Test oben (Resource-Load-Fehler, korrekt im Dialog abgefangen).

**Nicht automatisiert verifiziert**: Escape schließt den Dialog nativ über `<dialog>.showModal()` (Standard-Browserverhalten, unabhängig von unserem Code) – die synthetischen `Escape`-Tastendrücke des Browser-Tools haben den nativen Cancel-Mechanismus in dieser Sitzung nicht ausgelöst (vermutlich weil sie nicht als „trusted event“ gewertet werden); das „×“-Schließen (`#drill-close`, unverändert aus P30) wurde stattdessen wiederholt erfolgreich getestet. Empfehlung: einmal manuell im echten Browser bestätigen.

## Offene Punkte

- Escape-Verhalten des Dialogs wurde nicht automatisiert verifiziert (siehe oben) – beruht auf nativer `<dialog>`-Funktionalität, die durch P30b nicht verändert wurde.
- Die in `konten.js` verbliebene Test-Kassa/-Kategorie aus der Browserprüfung liegt in der Wegwerf-Datenbank `%TEMP%\p30b-app.db`, die nach der Prüfung gelöscht wurde; keine Spuren im Repository.
- `state.sparteId`/`state.year` bleiben als Alias-Felder neben `state.filter` bestehen (bewusste Entscheidung, siehe oben), damit die sechs bestehenden Seiten nicht angefasst werden mussten. P32/P33 können wählen, ob sie `state.filter.*` oder die Alias-Felder lesen – beide sind immer synchron.
- `buchungen.js` liest `#filter-kategorie`/`#filter-richtung`/`#filter-zahlungsart` weiterhin direkt aus dem DOM statt aus `state.filter`, weil ein vollständiger Wechsel dieser Seite auf `state.filter` außerhalb des beauftragten Scopes („nur dort anpassen, wo doppelt reagiert würde“) gelegen hätte; funktional unverändert, da `app.js` die Selects bereits korrekt befüllt/synchron hält.

Keine Migrationen, keine Backend-Änderungen, keine Commits außerhalb dieses Auftrags.
