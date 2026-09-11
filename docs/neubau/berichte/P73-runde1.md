# P73 – Mobil-Navigation und Handy-Fixes, Runde 1

Branch `pkt/p73-mobil-navigation`, Basis `7f31162` (neubau, enthält P72/Betriebsseite). Worktree `C:\Users\lblet\dev\wt-p73`. Interpreter: `C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Scripts\python.exe` (Hauptklon selbst nicht angefasst, dort lief die Testinstanz auf Port 8051 unberührt weiter).

## Gebaut

Siehe `docs/neubau/pakete/P73-mobil-navigation.md` für die vollständige Auflistung der Änderungen. Kurzfassung: sechster Bottom-Nav-Knopf „Mehr“ öffnet ein Sheet mit allen nicht in der Bottom-Nav enthaltenen Routen (dynamisch aus `routes` abgeleitet) plus Bereichswahl/Theme/Passwort/Abmelden (QA5-02); `min-width:0` auf den Grid-Items der Erfassen-Seite **und** `!important`-Override auf `.grid.g2-1` gegen einen Inline-`style` in `erfassen.js` (QA5-01, zweite Ursache erst beim Nachmessen gefunden); Mindest-Tap-Flächen für Bottom-Nav (44×48 px) und Listenaktionen (`.lnk`, `#k-table .act button`, `.btn` – 40 px, QA5-03); `dialog` bekommt `max-width:calc(100vw - 16px)` + scrollbaren Inhalt; Verlaufsschatten an `.tscroll`/`.table-wrap` (QA5-04).

## Prüfung

**Statisch (`tests/test_p73_mobil.py`, 10 Tests, ohne Browser)**: `node --check` für `app.js`; Markup-/CSS-Struktur wie im Auftrag verlangt. Alle grün, siehe Testlauf unten.

**Browser-Werkzeug**: Wie im Auftrag vorgesehen zuerst `mcp__playwright__browser_navigate` versucht — scheiterte wie beim QA-5-Bericht mit `Browser is already in use for …mcp-chrome-4b3d451, use --isolated`. Ausgewichen auf `mcp__Claude_Browser__*`, Messung über `document.documentElement.clientWidth`/`scrollWidth` (nicht `window.innerWidth`, siehe Begründung im QA-5-Bericht). Wegwerfinstanz auf Port 8085 (`FINANZ_DB` unter `%TEMP%\p73-instanz.db`, `FINANZ_INSTANZ=test`, `FINANZ_TEST_AUTH_BYPASS=1`), nach jeder Sitzung beendet und DB-Datei gelöscht.

**Wichtige Falle beim Messen**: Die Browser-Tab-`navigate()`-Aktion auf eine neue Hash-Route (`#/erfassen`) lädt `style.css` **nicht** neu (SPA, keine echte Navigation) – nach jeder CSS-Änderung musste `location.reload(true)` ausgeführt werden, sonst maß man versehentlich die vorherige Version. Das hat die erste Fassung des `.grid.g2-1`-Fixes fälschlich als wirkungslos erscheinen lassen; nach explizitem Reload war der Effekt sofort sichtbar.

### Messtabelle: `scrollWidth === clientWidth` je Seite/Breite

| Route | 320 px | 375 px | 390 px |
|---|---|---|---|
| uebersicht | 320=320 | 375=375 | 390=390 |
| sparte | 320=320 | 375=375 | 390=390 |
| erfassen | 320=320 | 375=375 | 390=390 |
| buchungen | 320=320 | 375=375 | 390=390 |
| konten | 320=320 | 375=375 | 390=390 |
| kredit | 320=320 | 375=375 | 390=390 |
| kategorien | 320=320 | 375=375 | 390=390 |
| belege | 320=320 | 375=375 | 390=390 |
| bankimport | 320=320 | 375=375 | 390=390 |
| export | 320=320 | 375=375 | 390=390 |
| betrieb | 320=320 | 375=375 | 390=390 |

Kein Overflow auf irgendeiner Seite bei irgendeiner der drei Breiten (vorher: Erfassen 112 px Overflow bei 375 px, 135 px bei 320 px). Erfassen-Formular füllt bei 375 px jetzt 317 px Breite (vorher 156 px, siehe Fallenhinweis oben).

### Mehr-Sheet (QA5-02)

| Prüfung | Ergebnis |
|---|---|
| Öffnet über `.mobile-nav [data-route="mehr"]` | Ja, `#sheet.hidden` wird `false` |
| Enthält genau die Routen außerhalb der Bottom-Nav | Ja: Sparte, Konten, Kredit, Kategorien, Export, Betrieb |
| Kein Seiten-Overflow bei geöffnetem Sheet, 375 px | `scrollWidth 375 = clientWidth 375` |
| Fokus beim Öffnen auf dem Sheet | Ja (`document.activeElement === sheet-node`) |
| Klick auf Routeneintrag | schließt Sheet und navigiert (`#/kategorien` bestätigt) |
| Escape | schließt Sheet (bestehender globaler Handler aus dem P30b-Gerüst) |
| Schließen-Knopf (`#sheet-close`) | schließt Sheet |
| Bereichs-Select im Sheet | befüllt mit „Haupt“/„Verein“ |
| Theme-Umschalter im Sheet | wechselt `dark`→`light`, schließt Sheet |
| Abmelden-Knopf | verkabelt (`POST /api/auth/logout` + Redirect, identischer Pfad wie Sidebar `#logout`); **nicht end-to-end ausgeführt**, um die laufende Testsitzung nicht durch Redirect/Session-Verlust zu unterbrechen — Code ist wortgleich zur bereits geprüften Sidebar-Logik in `drawSidebar()` |

### Tap-Ziele (QA5-03)

| Element | Höhe |
|---|---|
| Bottom-Nav-Knöpfe (5 normale) | 65×63 px |
| Bottom-Nav „＋“ (Plus) | 48×48 px |
| Bottom-Nav „Mehr“ | 65×63 px |
| `.lnk` (synthetisch, da Testinstanz ohne Buchungsdaten) | 40 px, `padding:10px 6px` bestätigt |
| `#k-table .act button` (synthetisch) | 40 px |

**Einschränkung**: Die Wegwerfinstanz hatte keine Buchungen/Kategorien (frische Test-DB ohne Seed-Buchungen), daher konnten „bearbeiten“/„stornieren“/„umbenennen“/„stilllegen“ nicht an echten Tabellenzeilen gemessen werden. Ersatzweise wurden synthetische Elemente mit den echten Klassen (`.lnk`, `#k-table .act button`) ins DOM eingehängt und `getComputedStyle`/`getBoundingClientRect` geprüft — das bestätigt die CSS-Regel wirkt (inkl. des `!important`-Kollisionsfalls mit `buchungen.css`/`kategorien.css`, siehe unten), ist aber kein Nachweis für exotisches Zusammenspiel mit dem echten Tabellen-Markup (z. B. Zeilenumbruch bei langen Kategorienamen). Empfehlung für die nächste Runde: Testinstanz mit einer echten Buchung/Kategorie aufsetzen (kurzer Zusatzschritt in `setUp`, wie in `tests/test_static_neu.py` vorgemacht) und dort real nachmessen.

### Dialog (`#drill`)

„Neue Kategorie“-Dialog auf der Erfassen-Seite (der im QA-5-Bericht als „sichtbar rechts abgeschnitten“ genannte Zusatzbefund): bei 375 px jetzt `left:18.75 / right:356.25` — vollständig im Viewport, vorher `right:412` (37 px außerhalb). Ursache war tatsächlich der native `<dialog>`-Zentrieralgorithmus auf Basis der überbreiten Seite (QA5-01) — mit dem behobenen Seiten-Overflow verschwindet auch dieses Symptom, wie im QA-5-Bericht vermutet.

### Konsole / Server-Log

Während der gesamten Sitzung keine `4xx`/`5xx` auf `/api/*` (Server-Log geprüft). Eine Browser-Konsolenmeldung `net::ERR_NO_BUFFER_SPACE` trat einmal auf — lokales Werkzeug-/Netzwerk-Transient, kein wiederholbarer App-Fehler, keine zugehörige fehlgeschlagene Anfrage in `read_network_requests`. Ein `ConnectionResetError`/`WinError 10054` im uvicorn-Log ist bekanntes Windows-Proactor-Rauschen bei Client-Disconnects (asyncio), keine Anwendungslogik betroffen.

## Gesamtsuite

`C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Scripts\python.exe -m unittest discover -s tests`, `FINANZ_DB=%TEMP%\p73-suite.db` (vorher gelöscht), ohne `FINANZ_TEST_AUTH_BYPASS`. **594 Tests, OK (1 skipped)**, 237 s. Vollständige Ausgabe: `docs/neubau/berichte/P73-tests.txt`. Die im Log sichtbaren Tracebacks (`UnidentifiedImageError`, „KI-Kategorievorschlag fehlgeschlagen“, „invalid pdf header“) sind erwartetes Verhalten bereits bestehender Tests mit absichtlich fehlerhaften/gemockten Eingaben – keine neuen Fehler.

## Abweichungen vom Auftrag (mit Begründung)

1. **`.grid.g2-1{grid-template-columns:1fr!important}` in `style.css`**: Der QA5-01-Bericht nannte nur das fehlende `min-width:0` als Ursache. Mit ausschließlich dieser Korrektur verschwand zwar der Seiten-Overflow, aber die Erfassen-Karte blieb auf ~156 px zusammengequetscht (siehe Messfalle oben) – Ursache war die Inline-`style`-Zweispaltigkeit von `.grid.g2-1` in `erfassen.js`, die schon `uebersicht.css`s eigene (nicht per `!important` abgesicherte) Mobil-Kollabierung dieser Klasse unwirksam macht. Zusätzlich ergänzt, nicht im Auftrag benannt, aber notwendig, um das eigentliche Ziel „Formular bei 375 px vollständig nutzbar“ zu erreichen.
2. **`.btn{min-height:40px}` statt eigener Klassen für Konten/Kredit/Belege**: Der Auftrag nennt „Konten, Kredit, Belege analog“, diese Seiten verwenden aber keine `.lnk`-Buttons, sondern durchgängig `.btn small` (wobei `.small` selbst keine eigene Regel hat, faktisch also `.btn`). Statt einzelne Selektoren pro Seite zu duplizieren, wurde die vorhandene gemeinsame `.btn`-Klasse im Media-Query auf 40 px angehoben – trifft automatisch alle drei Seiten, ohne die Desktop-Optik zu ändern.
3. **Tap-Ziele nicht an echten Tabellenzeilen gemessen** (siehe Einschränkung oben) – die Wegwerfinstanz hatte keine Buchungs-/Kategoriedaten und das Anlegen einer vollständigen Testbuchung (inkl. Kategorie) lag außerhalb des engen Scopes dieser Runde (Gefahr, den QA5-03-Fokus durch Fachlogik-Fehlersuche zu sprengen). Ersatzweise synthetisch mit den echten CSS-Klassen geprüft.
4. **Abmelden-Knopf im Sheet nicht end-to-end ausgeführt** (siehe Tabelle oben) – Code ist wortgleich zur bereits im Bestand laufenden Sidebar-Logik, ein echter Klick hätte die laufende Messsitzung durch Redirect beendet.

## Offen / nicht geprüft

- Echte Buchungs-/Kategorienzeilen-Tap-Ziele auf einer Instanz mit Testdaten (siehe Abweichung 3).
- Dialog „Zuordnen“ (Bankimport), „Beleg prüfen“, „Jahr bestätigen“ (Kredit) – wie schon im QA-5-Bericht nicht erreichbar, weil die Wegwerfinstanz keine passenden Testdaten hat (kein Bankkonto, keine offene Prüfung, kein Kredit). Diese Dialoge nutzen denselben `#drill`/`dialog`-Mechanismus und profitieren von der `max-width`/`max-height`-Korrektur, wurden aber nicht einzeln nachgemessen.
- Tastaturfokus-Verhalten bei eingeblendetem echten Mobil-Tastatur-Overlay (Desktop-Emulation hat keins).
- Kein Lint/Typecheck über `node --check` hinaus (kein Linter im Projekt, wie in den Vorgänger-Paketen).
- Kein Push, kein Merge nach `neubau` – nur lokale Commits im Worktree, wie beauftragt.

## Commits

Siehe Rückmeldung im Chat für die Hashes dieser Runde.
