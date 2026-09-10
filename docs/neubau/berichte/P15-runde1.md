# P15 – Kategorien, Regeln, Kennzahlen – Runde 1

Stand: 9. September 2026  
Worktree: `C:\Users\lblet\dev\wt-p15`  
Branch: `pkt/p15-kategorien-regeln`

## Ergebnis

P15 ist im vorgegebenen Schnitt umgesetzt: bestehende Router wurden gezielt erweitert, und für eigene Kennzahlen gibt es den neuen Router `app/routers/kennzahlen.py`. Konten-, Bewegungs- und Transferstrukturen wurden nicht angelegt. Es gab keinen Commit und keinen Push.

## Geänderte und neue Dateien

- `db/migrations/008_regeln_kennzahlen.sql` ist eine idempotente Migration für Regelherkunft/-freigabe/-kontext sowie `kennzahl` und `kennzahl_term` einschließlich Indizes.
- `db/schema.sql` bildet den Endstand der Migration für neue Datenbanken ab.
- `app/routers/stammdaten.py` ergänzt `PATCH /api/kategorien/{id}` und den Parameter `nur_aktive`, wobei IDs und Historie erhalten bleiben.
- `app/regeln.py` ergänzt Bereich-, Konto- und Spartenkontext, Betragsgrenzen, Herkunft/Freigabe im Ergebnis, stillgelegte Zielkategorien und Konflikterkennung.
- `app/routers/import_bank.py` ergänzt Regel-CRUD/-Filter/-Vorschau und lässt nur freigegebene gelernte Regeln beim CSV-Import automatisch verbuchen.
- `app/routers/buchungen.py` lernt nur aus einfachen manuell erfassten Buchungen, speichert Herkunft und Quellbuchung und reaktiviert deaktivierte Regeln nicht.
- `app/routers/schnellerfassung.py` verwendet den Bereich-/Spartenkontext und übernimmt Konflikttreffer nicht automatisch.
- `app/auswertung.py` verwendet die neue Regelauflösung mit fester Belegsparte.
- `app/bereiche.py` enthält die Bereichsprüfung für Kennzahlen.
- `app/kennzahlen.py` berechnet Einnahmen, Ausgaben und Netto je Term in Cent und ermittelt Monate mit Daten.
- `app/routers/kennzahlen.py` stellt den bereichsgeprüften Kennzahlen-CRUD sowie Jahreswert und Monatsdurchschnitt bereit.
- `app/main.py` bindet den Kennzahlen-Router unter `/api` ein.
- `tests/test_p15_kern.py` prüft Kategorie-PATCH/Liste, Regelkonflikt und Herkunft, Kennzahlrechnung und doppelten Nachzug auf Wegwerf-Datenbanken.
- `tests/test_regeln.py` erwartet die erweiterten Regelmetadaten, ohne den bestehenden Verhaltenstest abzuschwächen.
- `docs/superpowers/plans/2026-09-09-p15-kategorien-regeln-kennzahlen.md` hält den Umsetzungsschnitt ohne Commit fest.

## Neue und erweiterte Endpunkte

| Endpoint | Bereichsprüfung |
|---|---|
| `PATCH /api/kategorien/{id}` | `bereich_dep`; Kategorie-ID über `pruefe_kategorie` |
| `GET /api/kategorien?sparte_id=&nur_aktive=false` | `bereich_dep`; Sparte über `pruefe_sparte` |
| `GET /api/regeln?bereich_id=&quelle=&sparte_id=` | `bereich_dep`; optionale Sparte über `pruefe_sparte`; SQL filtert `regel.bereich_id` |
| `POST /api/regeln` | `bereich_dep`; Zielkategorie, Ziel-/Eingabesparte und Konto über die vorhandenen Prüfer |
| `PATCH /api/regeln/{id}` | `bereich_dep`; Regel über `pruefe_regel`, referenzierte IDs über die vorhandenen Prüfer |
| `POST /api/regeln/vorschau` | `bereich_dep`; Zielkategorie und optionales Konto werden geprüft; nur offene Umsätze desselben Bereichs |
| `GET /api/kennzahlen?sparte_id=&jahr=` | `bereich_dep`; Sparte und Kennzahl-/Kategoriebezug werden bereichsgebunden gelesen |
| `POST /api/kennzahlen` | `bereich_dep`; Sparte und jede Kategorie über `pruefe_sparte`/`pruefe_kategorie` |
| `PUT /api/kennzahlen/{id}` | `bereich_dep`; Kennzahl über `pruefe_kennzahl`, neue Terme über `pruefe_kategorie` |
| `DELETE /api/kennzahlen/{id}` | `bereich_dep`; Kennzahl über `pruefe_kennzahl` |

Bereichsdependency wurde nicht an Auth-, Health-, Schema- oder Betriebsendpunkte angelegt.

## Testausgabe

Interpreter: `C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Scripts\python.exe`  
Arbeitsverzeichnis: `C:\Users\lblet\dev\wt-p15`

Gezielter P15-Lauf:

```text
test_category_list_includes_inactive_and_patch_preserves_id ... ok
test_metric_value_uses_terms_and_months_with_data ... ok
test_migration_008_is_idempotent ... ok
test_rule_resolution_returns_origin_and_conflict ... ok

----------------------------------------------------------------------
Ran 4 tests in 3.671s

OK
```

Zusatzprüfungen:

```text
python -m compileall -q app tests       -> erfolgreich, keine Ausgabe
git diff --check                         -> erfolgreich, keine Whitespace-Fehler
OpenAPI-Pfade: ['/api/kennzahlen', '/api/kennzahlen/{kennzahl_id}']
             ['/api/regeln', '/api/regeln/{regel_id}', '/api/regeln/vorschau']
```

Angeforderter Gesamtlauf:

```text
python -m unittest discover -s tests -v
setUpClass (test_auth.AuthIntegrationTest) ... ERROR
test_abgelaufene_api_session_fuehrt_zur_loginseite ... ok
test_studio_bietet_logout_ueber_post_an ... ok
test_ersteinrichtung_gibt_code_einmal_aus ...
```

Der Lauf wurde nach wiederholter fehlender Ausgabe beendet, nachdem die Auth-/Migrationsläufe vor den fachlichen Assertions mit folgendem Fehlerbild reproduzierbar feststanden:

```text
sqlite3.OperationalError: unable to open database file
PermissionError: [WinError 5] Zugriff verweigert: C:\Users\lblet\AppData\Local\Temp\finanz-migrate-... 
```

Der Fehler entsteht beim Anlegen/Öffnen von Python-`TemporaryDirectory()`-Unterordnern in bestehenden Tests; die gleiche Anwendung kann eine Wegwerf-SQLite-Datei direkt unter `C:\Users\lblet\AppData\Local\Temp` öffnen. Der P15-Test verwendet deshalb weiterhin `TemporaryDirectory()` als Fixture und eine eindeutig benannte Wegwerfdatei im freigegebenen Temp-Verzeichnis.

## Nachweis des doppelten Nachzugs

Die Bestandsprobe wurde als Wegwerf-Datenbank unter `C:\Users\lblet\AppData\Local\Temp\p15-bestand-check-2.db` aus `db/schema.sql` und `db/seed.sql` initialisiert. Danach wurde Version 8 für die Nachzugsprobe als ausstehend markiert und der allgemeine Runner zweimal aufgerufen:

```text
first [8]
second []
status {'aktuell': 8, 'anstehend': [], 'basis': False}
```

Damit hat der erste Lauf Migration 008 angewendet; der zweite Lauf hat nichts angewendet. Die Testprobe deckt zusätzlich ab, dass der zweite Aufruf leer bleibt.

## Getroffene Annahmen

- `jahr` ist für den Kennzahlen-GET verpflichtend; ohne Jahr antwortet der Endpoint mit 400.
- Der laufende Monat wird beim aktuellen Jahr bis zum Serverdatum in `Europe/Vienna` begrenzt; bei abgeschlossenen Jahren zählen alle vorhandenen Monate.
- Ein geteilter Buchungskopf mit mehr als einer Kategorie erzeugt keine Lernregel; eine einfache Buchung darf eine gelernte Regel erzeugen.
- Das bestehende manuelle Übernehmen eines Vorschlags bleibt eine ausdrückliche Benutzeraktion; nur der automatische CSV-Import ist auf `quelle='gelernt'` und `auto_verbuchen=1` beschränkt.
- Gleich gute Regelkandidaten werden bei gleicher Priorität und gleicher normalisierter Bedingungslänge als Konflikt behandelt.
- Die bestehende Vorschlagsantwort behält ihre bisherigen Felder; Herkunft und Freigabe bleiben intern für die automatische Importentscheidung und sind in der Regelverwaltung sichtbar.

## Offene Punkte

- Der vollständige Repository-Testlauf konnte in dieser Umgebung nicht erfolgreich abgeschlossen werden, weil bestehende Tests ihre SQLite-/Auth-Testdateien in Python-`TemporaryDirectory()`-Unterordnern nicht öffnen können (`WinError 5`). Der P15-spezifische Lauf ist grün; eine Änderung am allgemeinen Runner oder an Auth zur Umgehung wäre außerhalb des Arbeitspakets und würde die vorgegebenen Grenzen verletzen.
- Der geplante Bericht enthält keinen Frontend-Teil, weil Frontend ausdrücklich Nicht-Ziel von P15 ist.

Die tatsächlich zuletzt verwendete Bestandsprobe liegt unter `C:\Users\lblet\AppData\Local\Temp\p15-bestand.db`; der frühere Zwischenlauf unter `p15-bestand-check-2.db` ist für den Nachweis nicht maßgeblich.
