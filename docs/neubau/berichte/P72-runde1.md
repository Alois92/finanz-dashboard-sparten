# P72 – Betriebsseite, Runde 1

Branch `pkt/p72-betriebsseite`, Basis `76ae6ac` (neubau). Worktree `C:\Users\lblet\dev\wt-p72`.

## Gebaut

**Backend**
- `app/routers/betrieb.py`: neu `GET /uebersicht` und `POST /sicherung`.
  - `baue_sicherung_und_schema_status(schema, schreibgeschuetzt)` – der Schema-/Sicherungsteil, der vorher direkt in `app/main.py::betrieb_status()` stand, ist hierher ausgelagert (P72-Auftrag, vom Nutzer bestätigt). `main.py::betrieb_status()` beschafft `con`/`migrationsstatus(con)` weiterhin selbst (über `main.get_connection`/`main.migrationsstatus`) und ruft dann nur noch die Hilfsfunktion – dadurch bleiben die Tests, die `main.get_connection`/`main.migrationsstatus` patchen (`tests/test_backup.py::test_betriebsstatus_enthaelt_nur_oeffentliche_sicherungsfelder`), unverändert grün, die Antwort von `/api/betrieb/status` ist bytegleich.
  - `GET /uebersicht` bündelt zusätzlich: Ollama (`modell`, `url`, `erreichbar` – wiederverwendet `beleg_auswertung.auswertung_status()`, kein zweiter Ollama-Aufruf), `ki_vorschlag_aktiv` (`ki_vorschlag.ist_aktiv()`), `frontend` (normalisiert aus `FINANZ_FRONTEND`, wie `main.py::frontend_verzeichnis()`), `instanz` (`FINANZ_INSTANZ`), `auswertungswarteschlange` (Zähler offen/laeuft/fehler aus `beleg_auswertung`, auf den Bereich beschränkt).
  - `POST /sicherung`: `backup.sicherungs_lock.locked()` → 409; sonst `await asyncio.to_thread(backup.sichere_datenbank)`, Ergebnisobjekt zurück. Kein eigener 503-Pfad – das übernimmt die bereits vorhandene `schreibschutz_middleware` in `app/main.py`, die vor jeder POST/PUT/PATCH/DELETE-Route (außer `/api/auth/`) greift, wenn `app.state.schreibgeschuetzt` gesetzt ist.
- `app/main.py`: `betrieb_status()` verkürzt (ruft die neue Hilfsfunktion), ungenutzter Import `from . import backup` entfernt (nur `backup_schleife` wird noch gebraucht).
- `tests/test_bereiche.py`: `/api/betrieb/sicherung` zur Ausnahmeliste in `test_fachliche_endpoints_haben_zentrale_dependency` ergänzt (wie `/api/betrieb/status` eine anwendungsweite Betriebsaktion, nicht bereichsgebunden).

**Frontend**
- `static-neu/pages/betrieb.js` + `betrieb.css` (Muster `pages/export.js`/`export.css`): fünf Kacheln – Datenbank, Sicherung (mit „Jetzt sichern“-Knopf, Spinner-Zustand, Toast bei 409/503/sonstigem Fehler, Kachel-Neuladen nach Abschluss), Foto-Auswertung, KI-Vorschlag, Instanz. Farbcodierung (`--ein`/`--aus`) wiederverwendet die bestehenden Design-Tokens statt neuer Farben.
- `static-neu/app.js`: `routes`-Map um `betrieb:['Betrieb','betrieb']` ergänzt (letzter Sidebar-Eintrag, automatisch über `drawSidebar()`).

**Tests**
- `tests/test_p72_betrieb.py` (8 Tests): Übersicht enthält alle Felder, keine Geheimnisse (Ganzstring-Suche nach `auth.json`/`finanz_session`/`session_secret`/`passwort_hash`/`cookie` in der kleingeschriebenen Serialisierung), Ollama-Erreichbarkeit gemockt (an/aus, `urllib.request.urlopen` in `app.routers.beleg_auswertung` gepatcht), `schreibgeschuetzt` wird durchgereicht, Sicherung liefert Ergebnis, 409 bei gehaltenem `sicherungs_lock`, 503 über die echte ASGI-App/Middleware (kein Router-eigener Pfad), `node --check` für `betrieb.js` und `app.js`.

## Tests – Ergebnis

Gesamtsuite im Worktree: `...\.venv\Scripts\python.exe -m unittest discover -s tests`, `FINANZ_DB=%TEMP%\p72-suite.db` (vorher gelöscht). **569 Tests, OK (1 skipped)**. Vollständige Ausgabe: `docs/neubau/berichte/P72-tests.txt`. Die im Log sichtbaren Tracebacks (`UnidentifiedImageError`, „KI-Kategorievorschlag fehlgeschlagen“, „invalid pdf header“) sind erwartetes Verhalten bereits bestehender Tests, die absichtlich fehlerhafte Eingaben/gemockte Fehlerfälle prüfen – keine neuen Fehler.

Live-Prüfung: Wegwerfinstanz auf Port 8084 (`FINANZ_DB` im `%TEMP%`, `FINANZ_INSTANZ=test`, `FINANZ_TEST_AUTH_BYPASS=1`, `FINANZ_FRONTEND=neu`), danach beendet (Prozess über den Port ermittelt und beendet, DB-Datei gelöscht):
- `GET /api/health` → 200
- `GET /api/betrieb/uebersicht` → alle erwarteten Felder, plausible Werte
- `GET /api/betrieb/status` → unverändert zum bisherigen Schema (Bytegleichheit visuell bestätigt)
- `POST /api/betrieb/sicherung` → `{"datenbank":"ok","belege":"ok","zweitziel":"nicht_konfiguriert"}`
- `GET /neu/pages/betrieb.js` und `.../betrieb.css` → 200 (ausgeliefert)
- Kein Browser verfügbar (belegt) – die eigentliche Seite (Kacheln, Knopf-Interaktion, Sidebar-Eintrag) wurde daher **nicht visuell**, sondern nur über `node --check`, Routen-Registrierung im Code und die Backend-Antworten geprüft.

Hinweis: Bei der Live-Prüfung meldete `ollama.erreichbar: true`, weil auf diesem Rechner tatsächlich ein Ollama-Dienst unter `127.0.0.1:11434` lief – das ist derselbe leichte `GET /api/tags`-Erreichbarkeitscheck, den `beleg_auswertung.auswertung_status()` ohnehin schon produktiv macht, keine Bildauswertung. Die automatisierte Testsuite ruft Ollama nicht auf (gemockt).

## Abweichungen vom Auftrag (mit Begründung)

1. **Bottom-Nav**: Der Auftrag nannte „Sidebar und Bottom-Nav, siehe wie Export registriert ist“. Tatsächlich ist Export gar nicht in der Bottom-Nav (`#mobile-nav` in `static-neu/index.html`) enthalten – dort liegen nur fünf feste Einträge (Start/Buchungen/Erfassen/Belege/Import). Betrieb wurde deshalb nur in die Sidebar aufgenommen, wie es Export vormacht; die Bottom-Nav wurde nicht angetastet (Auftrag hat das nach Rückfrage bestätigt).
2. **Mobile Erreichbarkeit der Sidebar – geprüft, nicht behoben**: Bei Viewports ≤760px gilt in `static-neu/style.css` `.side{display:none}` **ohne** Menü-Umschalter (Hamburger o. ä.). Die komplette Sidebar-Navigation ist auf dem Handy damit für **keine** ihrer Routen erreichbar – das betrifft nicht nur die neue Betriebsseite, sondern ebenso die bereits bestehenden Sidebar-only-Routen Sparte, Konten, Kredit, Kategorien und Export. Das ist eine vorbestehende Lücke des Gerüsts, keine P72-Regression. Ein Fix (z. B. ein Menü-Knopf, der `.side` als Overlay einblendet) würde alle genannten Routen betreffen und ist damit ein eigenes, über P72 hinausgehendes Paket – hier bewusst nicht mitgemacht, um den Scope nicht zu sprengen. **Empfehlung**: eigenes kleines Paket „Mobiles Sidebar-Menü“ auflegen.
3. **409-Check ist kein echter Mutex**: `sicherungs_lock.locked()` wird vor dem Start geprüft, dann `sichere_datenbank()` in einem Thread gestartet, der den Lock selbst erneut nimmt. Zwischen Prüfung und Threadstart liegt ein (sehr kleines) Race-Fenster – zwei nahezu gleichzeitige Klicks könnten beide 200 statt der zweite 409 bekommen. Für eine manuell ausgelöste Admin-Aktion (kein hochfrequentierter Pfad) als akzeptables Restrisiko bewertet und vom Auftrag so bestätigt.
4. **Ollama-URL nicht als Geheimnis behandelt**: `ollama.url` (z. B. `http://127.0.0.1:11434`) wird in `/uebersicht` ausgegeben. Das ist keine Zugangsdaten-URL (kein Token, kein externer Dienst), sondern dieselbe URL, die auch `GET /api/auswertung/status` (bestehender Endpunkt) schon zurückgibt – bewusst keine neue Einschränkung eingeführt.
5. **`version`-Feld weggelassen**: Kein Git-Commit/Versionsstand ist im Code bereits exponiert (geprüft); laut Auftrag in diesem Fall zulässig, weglassen statt selbst eine neue Quelle dafür einzuführen.

## Offen / nicht geprüft

- **Kein echter Browsertest** der neuen Seite (Kacheln, Knopf-Klick, Spinner, Toast) – Browser war für diese Sitzung belegt. Empfehlung: vor Merge einmal `/neu#/betrieb` im Browser gegen eine Testinstanz öffnen und den „Jetzt sichern“-Knopf klicken.
- **Mobiles Sidebar-Menü** (Punkt 2 oben) bleibt offen, betrifft mehrere bestehende Routen, nicht nur P72.
- Kein Lint/Typecheck-Lauf für JS über `node --check` hinaus (kein Linter im Projekt vorhanden, wie bei den anderen `pages/*.js`).
- Kein Push, kein Merge nach `neubau` – nur lokale Commits im Worktree, wie beauftragt.

## Commits

Siehe Rückmeldung im Chat für die Hashes dieser Runde (Backend, Frontend, Doku – ggf. mehrere Commits).
