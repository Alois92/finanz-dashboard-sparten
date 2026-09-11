# QA-fix-B — Behebung der QA-3/QA-4-Befunde (Konten, Belege, Foto-Auswertung)

Worktree `C:\Users\lblet\dev\wt-qa-b`, Branch `fix/qa-konten-belege`, Basis neubau 67a4011.
Grundlage: `docs/neubau/berichte/QA-3-konten-kassa-kredit-bankimport.md` und
`docs/neubau/berichte/QA-4-belege-foto-export-betrieb-login.md` (aus dem Hauptklon
`C:\Users\lblet\dev\finanz-dashboard-sparten` gelesen, dort nicht verändert).
Verifiziert über Unit-Tests (ASGI-Aufruf wie `tests/test_bereiche.py`) und `node --check`,
kein Browser verwendet (laut Auftrag belegt). Ollama nicht aufgerufen.

## Behoben

### QA3-02 (hoch) — Verbuchen-Formular wählte falsche Sparte vor
- **Ursache:** `static-neu/pages/bankimport.js` `formularHtml()` fiel ohne Regel-Vorschlag
  immer auf `state.sparten[0]?.id` zurück, unabhängig vom Bankkonto des Umsatzes.
- **Fix:** Vorbelegung mit `bankkonto.sparte_id` (Feld existiert bereits in `db/schema.sql`
  Zeile 131, "leer = gemischt genutzt"). Ist die Sparte des Kontos leer (gemischt genutztes
  Konto), bleibt das Sparte-Select ohne Vorauswahl (deaktivierte Platzhalter-Option) und
  ist `required` — Speichern ist erst nach aktiver Wahl möglich, nie eine geratene Sparte.
- **Test:** Kein JS-Testharness im Projekt vorhanden (nur `node --check`); Logik per
  Code-Review verifiziert, `node --check static-neu/pages/bankimport.js` grün.
- **Commit:** 399c526

### QA4-05 (mittel) — Wiederholungs-Eintrag `beleg_uebernahme` wurde nie committet
- **Ursache:** `app/routers/beleg_auswertung.py::auswertung_uebernehmen` rief nach
  `erstelle_buchung(...)` (committet selbst über `with con: ... BEGIN IMMEDIATE`) noch
  `speichere_antwort(con, 'beleg_uebernahme', ...)` auf, aber ohne folgenden `con.commit()`.
  `db_dep` committet beim Verbindungsschluss nicht selbst — der Eintrag ging verloren.
- **Fix:** `con.commit()` nach `speichere_antwort(...)` ergänzt.
- **Test:** `tests/test_qa4_05_commit.py` (neu) — verzichtet bewusst auf die geteilte
  Testverbindung der bestehenden P43/P50b-Tests (dort fällt der Bug wegen der geteilten
  Connection nicht auf) und lässt `db_dep()` wie im echten Betrieb pro Request neu
  verbinden. Verifiziert: Test schlägt ohne den Fix fehl (`request_wiederholung`-Zeile
  fehlt, zweiter Aufruf liefert 409), mit Fix grün.
- **Commit:** b29f7e2

### Foto-Auswertung deterministisch (Kopf-Auftrag zu QA4-01…04)
- **Ursache:** `app/auswertung.py::_auswerten` schickte keine `options` an Ollama; der
  Modellvergleich beim Umstieg auf das Gewinnermodell lief mit `temperature=0` und lieferte
  spürbar bessere Datumswerte.
- **Fix:** `body["options"] = {"temperature": OLLAMA_TEMPERATUR}`, Standard `0`, per
  `FINANZ_OLLAMA_TEMPERATUR` überschreibbar.
- **Test:** `tests/test_beleg_auswertung.py` — zwei neue Tests (`_ollama_aufruf` gemockt,
  gesendeter Body geprüft: Standard 0, per ENV überschreibbar).
- **Commit:** 0f72354
- **Hinweis:** Behebt nicht die Modell-Schwächen selbst (Datum/Betrag teils falsch, siehe
  QA4-01…04) — das ist ein Modellverhalten, kein Code-Fehler, außerhalb des Auftrags.

### QA3-03 (mittel) — Horizontaler Seiten-Überlauf durch `.card-head`
- **Ursache:** `.card-head{display:flex;justify-content:space-between;...}` in
  `static-neu/style.css` ohne `flex-wrap`; lange Hinweistexte (z. B. im
  Bankimport-Kartenkopf) hatten keinen Umbruchpunkt und drückten die Karte über den
  Viewport.
- **Fix:** `.card-head{flex-wrap:wrap}`, `.card-head>*{min-width:0;overflow-wrap:break-word}`,
  zusätzlich `.card{min-width:0}` (Grid-Item-Absicherung). `.card-head` ist eine geteilte
  Gerüst-Klasse (P30) — die zentrale Änderung behebt das Problem auf allen Seiten mit
  langen Kopftexten, nicht nur im Bankimport, wie im Auftrag gefordert.
- **Test:** Kein Browser verfügbar für Live-Verifikation (laut Auftrag belegt); Fix ist
  eine Standard-CSS-Absicherung (min-width:0 + flex-wrap gegen die bekannte
  Flexbox-Overflow-Falle). Nicht live nachgemessen — siehe „Nicht geprüft" unten.
- **Commit:** 4112515

### QA3-06 (niedrig) — „Jahr bestätigen"-Dialog blieb nach Speichern offen
- **Fix:** `static-neu/pages/kredit.js` schließt den Dialog jetzt nach erfolgreichem
  `PUT /api/kredite/{id}/jahre/{jahr}` (`document.querySelector('#drill').close()`) und
  lädt die Liste neu; Abweichungen gehen nicht verloren, der Toast nennt sie.
- **Test:** `node --check` grün; kein Browser für Live-Klicktest verfügbar.
- **Commit:** f8d1a26

### QA3-07 (niedrig) — `#/sparte/<id>/kredit` führte zur Sparten-Übersicht
- **Ursache:** `currentRoute()` in `static-neu/app.js` wertete nur das erste
  Hash-Segment aus (`raw.split('/')[0]`).
- **Fix:** Erkennt jetzt das Muster `sparte/<id>/<seite>`, setzt den globalen
  Sparten-Filter (`state.filter.sparteId`, so steuert die App Sparten-Auswahl
  grundsätzlich, nicht über URL-Segmente) und löst zur eigentlichen Seite auf.
- **Test:** `node --check` grün; kein Browser für Live-Navigationstest verfügbar.
- **Commit:** c6c44dc

### QA3-01 (niedrig) — Doppelte Währungsangabe
- **Fix:** `static-neu/pages/konten.js` hängt den Währungscode nur noch an, wenn das
  Konto NICHT auf EUR lautet (`fmtEur` formatiert ohnehin immer als €).
- **Commit:** 2598439 (zusammen mit QA3-05)

### QA3-05 (niedrig) — „Offene Abgleiche"-Hinweis auch auf Kassakonten
- **Fix:** Hinweis wird nur noch für Konten mit `art in ('bank','karte')` berechnet/gezeigt.
- **Commit:** 2598439

### QA3-04 (mittel) — Konto bearbeiten/deaktivieren fehlte im Frontend
- **Geprüft:** `PATCH /api/konten/{id}` existiert bereits und unterstützt
  `name/iban/bank/sparte_id/aktiv` vollständig (`app/routers/konten.py`).
- **Fix:** Neuer „Bearbeiten"-Dialog je Konto (`openBearbeitenDialog`, über den
  bestehenden `drill()`-Mechanismus wie die übrigen Konto-Dialoge): Name, Sparte,
  IBAN, Bank, Aktiv-Checkbox. Art/Währung bewusst nicht editierbar (serverseitig
  gesperrt, sobald das Konto Bewegungen hat — 409). Inaktive Konten zeigen eine
  „inaktiv"-Badge und sind abgedunkelt.
- **Test:** `tests/test_p41_konten.py` — neuer Test verifiziert PATCH-Wirkung direkt
  gegen die API (Name/IBAN/Bank/aktiv=0 ändern sich, erscheinen so in der Liste) sowie
  Quelltextprüfung, dass `konten.js` den Dialog/Endpunkt tatsächlich verwendet.
- **Commit:** fade5f3

## Nicht behoben / offen

### QA4-06 (niedrig) — kein manueller Sicherungs-Trigger, keine Betriebsseite
Laut Auftrag NICHT bauen, nur als Entscheidung für den Kopf vermerken:

- `app/routers/betrieb.py` bietet nur die beiden GET-Endpunkte `status` und
  `migrationsprotokoll`; ein POST-Trigger für eine manuelle Sicherung existiert nicht.
- Es gibt keine „Betrieb"-Seite im neuen Frontend (`static-neu/`), kein Menüpunkt,
  keine Route in `app.js`.
- **Offene Entscheidung für den Kopf:** Soll ein manueller Sicherungs-Trigger
  (`POST /api/betrieb/sicherung` o. ä.) plus eine minimale Betriebsseite (Status,
  Migrationsprotokoll, Sicherung-Knopf) als eigenes Baustein-Ticket aufgenommen werden,
  oder bleibt die Sicherung bewusst ausschließlich ein Hintergrund-Job
  (`app/backup.py`) ohne Nutzer-Interaktion? Betrifft auch QA4-Nachtrag zum
  Login-Instanz-Neustart (8056) — unabhängig von diesem Auftrag.

## Nicht live verifiziert (kein Browser verfügbar)

Alle Frontend-Änderungen (QA3-02, QA3-03, QA3-06, QA3-07, QA3-01, QA3-05, QA3-04) wurden
ausschließlich über `node --check` (Syntax) und, wo die zugrunde liegende API betroffen
ist, über Backend-Unit-Tests verifiziert — nicht per echtem Klick-/Rendertest im Browser,
da dieser laut Auftrag belegt war. Insbesondere:
- QA3-03 (Overflow-Fix): kein Live-Breitenmessung bei 1024/375 px.
- QA3-06/QA3-07 (Dialog-Schließen, Routing): kein Live-Klicktest.
- QA3-04 (Bearbeiten-Dialog): Formularverhalten/Styling nicht optisch geprüft, nur
  API-Wirkung und Quelltext.

Empfehlung: vor Freigabe einen kurzen Browser-Rauchtest dieser Seiten nachziehen, sobald
ein Browser-Werkzeug wieder frei ist.

## Gesamtsuite

`FINANZ_DB=%TEMP%\qa-b-suite.db` (vorher gelöscht),
`<venv-python> -m unittest discover -s tests`, Ausgabe in `QA-fix-B-tests.txt`.

**Ergebnis: `Ran 459 tests ... OK (skipped=1)`, Exit-Code 0.** Die im Log sichtbaren
Tracebacks (`FileExistsError`, `sqlite3.DatabaseError`, `PIL.UnidentifiedImageError`,
"Keine bestehende Auth-Datei gefunden") sind erwartete Fehlerpfad-Tests (bewusst
provozierte Fehler, von den jeweiligen Tests abgefangen/erwartet), keine Fehlschläge —
kein `FAIL`/`ERROR` in der Zusammenfassung.
