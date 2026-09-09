# P10 – Bereiche, Runde 1

Umsetzung auf `pkt/p10-bereiche`, Ausgangspunkt identisch mit `neubau` (`f03663fddbaa0cd1c19950e6c29db7e78cc83fce`). Keine Commits, kein Push. Grundlage sind die vollständige Auftragskarte und insbesondere Architekturabschnitte 2 und 8.

## Umsetzung

Die sechs vorgegebenen Tabellen tragen `bereich_id`; Kategorien und Buchungen erben ihren Bereich über die Sparte, Bankumsätze über das Konto und Fotoaufträge über den Beleg. `bereich_dep` prüft zentral den Query-Parameter mit Standard 1 gegen aktive Bereiche. Fremde oder unbekannte Kennungen ergeben 404, bevor geschrieben wird. Bei Stapelübernahmen werden sämtliche Umsatz-IDs vor dem ersten Commit geprüft. Erhaltene Beleg-/Kontenverweise sowie gekoppelte Löschfolgen werden ebenfalls geprüft.

Regellisten, Lernen und Vorschläge sind bereichsgebunden. Der Resolver schließt auch bereits vorhandene widersprüchliche Zielverweise aus, ohne die Daten zu bereinigen. Foto-Uploads speichern den Bereich am Beleg; die Hintergrundauswertung übernimmt diesen gespeicherten Bereich und prüft die Belegsparte. Das bestehende Frontend ergänzt in `api()` zentral `bereich_id=1`.

Es wurden keine neuen Tabellen außer `bereich`, Abhängigkeiten, Loginmodelle, Oberflächen oder Konten-/Bewegungsfunktionen eingeführt. Ein eigener Auslagen-Endpunkt existiert im Ausgangsstand nicht; vorhandene Buchungs- und Umbuchungspfade dürfen keine Bereichsgrenze überschreiten. Es wurden keine P11-Endpunkte ergänzt.

## Migration und allgemeiner Runner

`003_bereiche.sql` legt die Bereiche 1/2 und die vorgeschriebenen Spalten/Indizes an. Bestehende Vereinssparten wechseln nach Bereich 2; Konten, Belege und Regeln folgen ihren vorgegebenen Spartenverweisen. Die erste Sparte/Kategorie einer Gruppe ist deterministisch die mit der kleinsten ID. Nur die in der Karte ausdrücklich verlangten fremden Gruppenzuordnungen werden entfernt; ihre Anzahl wird je Zuordnungstabelle nach erfolgreichem Commit geloggt.

SQLite unterstützt kein `ADD COLUMN IF NOT EXISTS` und lehnt auf befüllten Tabellen `ADD COLUMN … REFERENCES` mit nichtleerer Vorgabe bei aktivierter FK-Prüfung ab. Der Runner verarbeitet deshalb SQL-Migrationen allgemein anweisungsweise, erkennt vollständige SQLite-Anweisungen einschließlich Triggern und überspringt bereits vorhandene `ADD COLUMN`-Spalten. Für die Migrationstransaktion wird die FK-Automatik vorübergehend ausgesetzt, vor dem Commit mit `foreign_key_check` geprüft und anschließend der ursprüngliche Modus wiederhergestellt. Bei Fehlern rollen Schema, Daten und Versionsmarkierung zurück. Es gibt keine Fallunterscheidung für einzelne Versionen oder fachliche Tabellen im Runner.

Tests vergleichen alle Tabellenspalten, Fremdschlüssel und Indizes von Neuanlage und Nachzug. Auch ein erzwungener erneuter Lauf von 003 auf bereits erweitertem Schema ist geprüft. Die normale Wiederholung des Runners wendet keine Migration mehr an.

## Geänderte und neue Dateien

| Datei | Änderung |
|---|---|
| `app/bereiche.py` (neu) | Enthält Bereichstyp, zentrale Dependency, sämtliche Kennungsprüfungen und `sparten_ids`. |
| `app/migrate.py` | Führt SQL-Migrationen allgemein idempotent, transaktional und mit nachgelagerter FK-Prüfung und Protokollierung aus. |
| `db/migrations/003_bereiche.sql` (neu) | Ergänzt Bereiche, Zuordnungen und Indizes sowie die protokollierte Entfernung fremder Gruppenzuordnungen. |
| `db/schema.sql` | Definiert für neue Datenbanken dasselbe Bereichsschema einschließlich Vorgabebereichen und Indizes. |
| `db/seed.sql` | Ordnet die Vereinssparte Bereich 2 zu und hält die vorgegebenen Gruppen innerhalb ihres Bereichs. |
| `app/routers/stammdaten.py` | Filtert Sparten und Kategorien, prüft Kategorieverweise und liefert `/api/bereiche`. |
| `app/routers/buchungen.py` | Trennt Listen, Suche und Lernen und prüft Referenzen beim Anlegen, Bearbeiten, Umbuchen und Löschen. |
| `app/routers/gruppen.py` | Trennt Gruppenlisten und schreibt ausschließlich bereichskonforme Kategorien-/Spartenzuordnungen. |
| `app/routers/dashboard.py` | Verwendet den Bereich in allen Summen, Jahresvergleichen und Monatsreihen. |
| `app/routers/export.py` | Begrenzt XLSX und HTML-Jahresbericht einschließlich Gesamtsummen auf den Bereich. |
| `app/routers/belege.py` | Trennt Upload-Dubletten und Listen und prüft Downloads, Löschungen und Buchungsverknüpfungen. |
| `app/routers/beleg_auswertung.py` | Prüft Belege und Fotoaufträge und begrenzt die Auftragsliste auf deren Bereich. |
| `app/routers/import_bank.py` | Trennt Konten, Umsätze und Regeln und prüft Import, Verbuchen und gesamte Übernahmestapel vor Schreibbeginn. |
| `app/routers/import_excel.py` | Prüft die Zielsparte vor Vorschau oder Einspielen des Kassabuchs. |
| `app/routers/schnellerfassung.py` | Beschränkt Namensabgleich und Regelvorschläge auf den gewählten Bereich. |
| `app/regeln.py` | Erwartet den Bereich explizit und filtert aktive Regeln einschließlich ihrer Zielverweise. |
| `app/auswertung.py` | Liest den gespeicherten Belegbereich und reicht ihn an die Kategorie-/Regelzuordnung weiter. |
| `app/auth.py` | Ergänzt ausschließlich die Bereichsdependency an den Auth-Endpunkten; Middleware, Passwort- und Sitzungsprüfung bleiben unverändert. |
| `app/main.py` | Ergänzt die zentrale Dependency auch an Health, Schemadiagnose und Betriebsstatus. |
| `static-studio/app.js` | Setzt in der zentralen API-Hilfsfunktion den Query-Parameter `bereich_id=1`. |
| `tests/test_bereiche.py` (neu) | Prüft Bereichsgrenzen über die echte ASGI-Anwendung, echtes Schema/Seed, Exporte, Fotoverarbeitung und den Rollback-Startzustand. |
| `tests/test_bereiche_import.py` (neu) | Prüft Bank-/Excel-Grenzen, Regellernen und vorab vollständig geprüfte Übernahmestapel. |
| `tests/test_bereiche_migration.py` (neu) | Prüft Nachzug, Gruppenbereinigung, Wiederholung, Strukturgleichheit und allgemeine SQL-Runner-Transaktionen. |
| `tests/test_migrate.py` | Erwartet Schema-Version 3 und verwendet durchgehend `TemporaryDirectory()` statt manuell verwalteter Temp-Verzeichnisse. |
| `tests/test_regeln.py` | Prüft den neuen 404-Vertrag für unbekannte Stapel-IDs und behält die positive Übernahme-/Überspringen-Prüfung bei. |
| `tests/test_set_auth_password.py` | Puffert ausschließlich die CLI-Testausgabe, damit zufällige Einmalcodes nicht im Testprotokoll erscheinen. |
| `docs/neubau/berichte/P10-plan.md` (neu) | Hält Umsetzungsschritte und Hausregeln fest. |
| `docs/neubau/berichte/P10-runde1.md` (neu) | Dokumentiert Änderungen, Endpunkte, Verifikation und verbleibende Einschränkungen. |

## Endpunkte und Bereichsprüfung

Alle 56 registrierten Endpunkte besitzen `bereich_id` über dieselbe Dependency; dies wird zusätzlich am tatsächlichen FastAPI-Abhängigkeitsbaum geprüft. In der folgenden Tabelle ist diese Prüfung immer eingeschlossen. Auth- und Betriebsinformationen bleiben anwendungsweit, weil weder ein zweiter Login noch bereichsweise Sicherungen Teil von P10 sind; sie liefern keine fachlichen Buchungslisten.

| Methode | Endpoint | Art der Bereichsprüfung |
|---|---|---|
| POST | `/api/auth/login` | Aktiver Bereich; bestehende anwendungsweite Auth-, Passwort-, Sitzungs- und Recovery-Prüfung unverändert. |
| POST | `/api/auth/logout` | Aktiver Bereich; bestehende anwendungsweite Auth-, Passwort-, Sitzungs- und Recovery-Prüfung unverändert. |
| GET | `/api/auth/state` | Aktiver Bereich; bestehende anwendungsweite Auth-, Passwort-, Sitzungs- und Recovery-Prüfung unverändert. |
| POST | `/api/auth/initial-password` | Aktiver Bereich; bestehende anwendungsweite Auth-, Passwort-, Sitzungs- und Recovery-Prüfung unverändert. |
| POST | `/api/auth/change-password` | Aktiver Bereich; bestehende anwendungsweite Auth-, Passwort-, Sitzungs- und Recovery-Prüfung unverändert. |
| POST | `/api/auth/recover` | Aktiver Bereich; bestehende anwendungsweite Auth-, Passwort-, Sitzungs- und Recovery-Prüfung unverändert. |
| GET | `/api/export/xlsx` | Bereichsfilter in Buchungs-, Monats- und Kategorieblättern einschließlich Summen; optionale Sparte prüfen. |
| GET | `/export/bericht` | Bereichseigene Sparten und Summen; optionale Sparte zentral prüfen. |
| GET | `/api/sparten` | SQL-Filter sparte.bereich_id; nur aktive Sparten. |
| GET | `/api/kategorien` | SQL-Filter über die Sparte; optionalen Spartenfilter zentral prüfen. |
| POST | `/api/kategorien` | Zielsparte und optionale übergeordnete Kategorie zentral prüfen. |
| GET | `/api/bereiche` | Aktiver angefragter Bereich; liefert ausschließlich aktive Bereiche mit id/name/kuerzel/typ. |
| POST | `/api/buchungen` | Sparte, alle Zeilenkategorien und optionales Bankkonto prüfen; Regellernen mit Bereich. |
| GET | `/api/buchungen` | SQL-Filter über Sparte; Sparten-/Kategorie-/Gruppenfilter prüfen; angehängte Belege ebenfalls filtern. |
| GET | `/api/buchungen/suche` | Bereichsfilter vor Text-/Notiz-/Kontaktsuche und Limit; angehängte Belege ebenfalls filtern. |
| POST | `/api/umbuchungen` | Beide Sparten vor dem ersten Schreiben zentral prüfen. |
| PUT | `/api/buchungen/{buchung_id}` | Bestehende Buchung, erhaltene Konten-/Umsatz-/Belegverweise, Zielsparte und alle Kategorien prüfen. |
| DELETE | `/api/buchungen/{buchung_id}` | Buchung und sämtliche gekoppelten Buchungen sowie deren Konten-/Umsatz-/Belegverweise vor dem Löschen prüfen. |
| GET | `/api/dashboard` | Bereichsfilter über Sparte in sämtlichen Summen/Unterauswertungen; optionale Sparte und Globalgruppe prüfen. |
| GET | `/api/jahresvergleich` | Bereichsfilter über Sparte in sämtlichen Summen/Unterauswertungen; optionale Sparte und Globalgruppe prüfen. |
| GET | `/api/verlauf` | Bereichsfilter über Sparte in sämtlichen Summen/Unterauswertungen; optionale Sparte und Globalgruppe prüfen. |
| GET | `/api/globalgruppen` | SQL-Filter globale_kategoriegruppe.bereich_id. |
| POST | `/api/globalgruppen` | Jede Kategorie prüfen; Bereich explizit an der neuen Gruppe speichern. |
| PUT | `/api/globalgruppen/{gruppe_id}` | Bestehende Gruppe und jede neue Kategoriezuordnung prüfen. |
| DELETE | `/api/globalgruppen/{gruppe_id}` | Bestehende Gruppe vor dem Löschen prüfen. |
| GET | `/api/auswertungsgruppen` | SQL-Filter auswertungsgruppe.bereich_id. |
| POST | `/api/auswertungsgruppen` | Alle Mitgliedssparten prüfen; Bereich explizit an der neuen Gruppe speichern. |
| PUT | `/api/auswertungsgruppen/{gruppe_id}` | Bestehende Gruppe und alle neuen Mitgliedssparten prüfen. |
| DELETE | `/api/auswertungsgruppen/{gruppe_id}` | Bestehende Auswertungsgruppe vor dem Löschen prüfen. |
| POST | `/api/parse` | Namensabgleich nur mit Sparten/Kategorien des Bereichs; Resolver erhält den Bereich explizit. |
| POST | `/api/parse-mehrere` | Namensabgleich nur mit Sparten/Kategorien des Bereichs; Resolver erhält den Bereich explizit. |
| POST | `/api/belege` | Optionale Sparte prüfen; Dublettenprüfung nur im Bereich; Bereich am Beleg speichern. |
| GET | `/api/belege` | SQL-Filter beleg.bereich_id; optionale Sparte prüfen. |
| GET | `/api/belege/{beleg_id}/datei` | Beleg zentral prüfen, bevor Dateipfad gelesen oder Datei ausgeliefert wird. |
| DELETE | `/api/belege/{beleg_id}` | Beleg und betroffene verknüpfte Buchungen vor DB-/Dateilöschung prüfen. |
| POST | `/api/buchungen/{buchung_id}/belege` | Buchung und Beleg zentral prüfen, bevor Verknüpfung oder Status geändert werden. |
| DELETE | `/api/buchungen/{buchung_id}/belege/{beleg_id}` | Buchung und Beleg zentral prüfen, bevor Verknüpfung oder Status geändert werden. |
| GET | `/api/buchungen/{buchung_id}/belege` | Buchung zentral prüfen; verknüpfte Belege zusätzlich nach Bereich filtern. |
| POST | `/api/belege/{beleg_id}/auswerten` | Beleg zentral prüfen; Auftrag und Deduplizierung erben den geprüften Belegbereich. |
| GET | `/api/beleg-auswertungen` | SQL-Filter über beleg.bereich_id, vor Statusfilter und Limit. |
| POST | `/api/beleg-auswertungen/{auswertung_id}/status` | Auftrag zentral über seinen Belegbereich prüfen. |
| GET | `/api/auswertung/status` | Aktiver Bereich; technischer Modellserverstatus ohne fachliche Datensätze. |
| GET | `/api/bankkonten` | SQL-Filter bankkonto.bereich_id; nur aktive Konten. |
| POST | `/api/bankkonten` | Optionale Sparte prüfen; Bereich auch bei Konten ohne Sparte explizit speichern. |
| POST | `/api/import/csv` | Zielkonto vor dem Einlesen/Schreiben prüfen; Import und Umsätze erben dessen Bereich. |
| GET | `/api/regeln` | SQL-Filter regel.bereich_id. |
| PATCH | `/api/regeln/{regel_id}` | Regel vor Aktivierung/Deaktivierung oder Löschung zentral prüfen. |
| DELETE | `/api/regeln/{regel_id}` | Regel vor Aktivierung/Deaktivierung oder Löschung zentral prüfen. |
| GET | `/api/bankumsaetze` | SQL-Filter über bankkonto.bereich_id; optionales Konto prüfen; nur bereichskonforme Regelvorschläge. |
| POST | `/api/bankumsaetze/vorschlaege-uebernehmen` | Alle angeforderten Umsatz-IDs vor dem ersten Commit prüfen; Regeln und delegiertes Verbuchen erhalten den Bereich. |
| POST | `/api/bankumsaetze/{umsatz_id}/verbuchen` | Umsatz über Konto sowie Zielsparte/Kategorie prüfen; Regel-Upsert ausschließlich im Bereich. |
| PATCH | `/api/bankumsaetze/{umsatz_id}` | Umsatz zentral über Konto prüfen, bevor der Status geändert wird. |
| POST | `/api/import/excel` | Zielsparte vor Vorschau und Einspielen prüfen; Kategorien/Buchungen bleiben unter dieser Sparte. |
| GET | `/api/health` | Aktiver Bereich; technische Erreichbarkeit, keine fachlichen Datensätze. |
| GET | `/api/schema` | Aktiver Bereich und bestehende Auth; anwendungsweiter Schema-/Schreibschutzstatus. |
| GET | `/api/betrieb/status` | Aktiver Bereich und bestehende Auth; anwendungsweiter Sicherungs- und Schemastatus. |

## Testumgebung

Alle Testdatenbanken und Belegdateien liegen außerhalb des Repos. Die Tests verwenden `tempfile.TemporaryDirectory()` und das echte Anwendungsschema. Der abschließende Prozess erhält `FINANZ_DB=<externes TemporaryDirectory>/suite.db`; ausgeführt wird unverändert `python -m unittest discover -s tests`. `PYTHONDONTWRITEBYTECODE=1` vermeidet zusätzlich Bytecode-Schreibzugriffe.

Die Windows-Sandbox verweigert Zugriffe auf die von Python 3.12 mit Modus `0700` angelegten Temp-Verzeichnisse. Ein isolierter Vergleich mit `os.mkdir` bestätigte, dass Verzeichnisse mit geerbter TEMP-ACL zugänglich sind. Ausschließlich für diese Testprozesse liegt außerhalb des Repos ein `sitecustomize.py` auf `PYTHONPATH`, das `tempfile` beim Erstellen seiner Verzeichnisse die vorhandene TEMP-ACL erben lässt (`0777` statt der speziellen Windows-`0700`-ACL). `TemporaryDirectory`, Cleanup, Datenbankzugriffe und der vorhandene Auth-Testbypass bleiben unverändert; es gibt dazu keine Änderung im Produktcode oder in Repo-Testfixtures.

## Vollständige Ausgabe der abschließenden Testsuite

Ergebnis: **159 Tests in 213,243 Sekunden, OK (skipped=1), Exitcode 0**. Der übersprungene Test prüft POSIX-Dateirechte und ist auf Windows nicht anwendbar.

```text
............C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 37400 is still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 34908 is still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 38152 is still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 36216 is still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 36296 is still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 23168 is still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 25620 is still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 38588 is still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 19256 is still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 37080 is still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 34848 is still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 32688 is still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 36588 is still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 38396 is still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 26716 is still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 38304 is still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 37252 is still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 23208 is still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 8320 is still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 14000 is still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 30332 is still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.s...................DB-Sicherung fehlgeschlagen (Betrieb laeuft weiter)
Traceback (most recent call last):
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\app\backup.py", line 262, in sichere_datenbank
    quelle.backup(kopie)
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\tests\test_backup.py", line 231, in backup
    raise sqlite3.OperationalError("simulierter Abbruch")
sqlite3.OperationalError: simulierter Abbruch
......DB-Sicherung auf Zweitziel fehlgeschlagen, Erstkopie bleibt gueltig (\\kein-host-xyz-existiert\share\backup)
Traceback (most recent call last):
  File "C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\pathlib.py", line 1311, in mkdir
    os.mkdir(self, mode)
PermissionError: [WinError 5] Zugriff verweigert: '\\\\kein-host-xyz-existiert\\share\\backup'

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\app\backup.py", line 292, in _sichere_auf_zweitziel
    BACKUP_ZIEL2.mkdir(parents=True, exist_ok=True)
  File "C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\pathlib.py", line 1320, in mkdir
    if not exist_ok or not self.is_dir():
                           ^^^^^^^^^^^^^
  File "C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\pathlib.py", line 875, in is_dir
    return S_ISDIR(self.stat().st_mode)
                   ^^^^^^^^^^^
  File "C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\pathlib.py", line 840, in stat
    return os.stat(self, follow_symlinks=follow_symlinks)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
PermissionError: [WinError 5] Zugriff verweigert: '\\\\kein-host-xyz-existiert\\share\\backup'
...Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\app\auswertung.py", line 106, in _lade_bild_base64
    from PIL import Image, ImageOps
ModuleNotFoundError: No module named 'PIL'
..Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\app\auswertung.py", line 106, in _lade_bild_base64
    from PIL import Image, ImageOps
ModuleNotFoundError: No module named 'PIL'
.Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\app\auswertung.py", line 106, in _lade_bild_base64
    from PIL import Image, ImageOps
ModuleNotFoundError: No module named 'PIL'
.Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\app\auswertung.py", line 106, in _lade_bild_base64
    from PIL import Image, ImageOps
ModuleNotFoundError: No module named 'PIL'
.Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\app\auswertung.py", line 106, in _lade_bild_base64
    from PIL import Image, ImageOps
ModuleNotFoundError: No module named 'PIL'
..Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\app\auswertung.py", line 106, in _lade_bild_base64
    from PIL import Image, ImageOps
ModuleNotFoundError: No module named 'PIL'
.Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\app\auswertung.py", line 106, in _lade_bild_base64
    from PIL import Image, ImageOps
ModuleNotFoundError: No module named 'PIL'
...................................................................................Keine bestehende Auth-Datei unter C:\Users\lblet\AppData\Local\Temp\tmpzw7js9ju\auth.json gefunden. Ohne bestehendes Passwort kann kein Recovery-Code erzeugt werden.
......
----------------------------------------------------------------------
Ran 159 tests in 213.243s

OK (skipped=1)
```

## Doppelter Nachzug auf einer Bestandskopie

Die bereits vor dieser Umsetzung vorhandene lokale temporäre Datenbank wurde über eine schreibgeschützte SQLite-Verbindung kopiert. Beide Nachzüge liefen hintereinander über `app.migrate.anwenden` auf derselben Kopie in einem externen `TemporaryDirectory`. Vor dem ersten Lauf wurde eine SQLite-Sicherung erstellt; beim zweiten Lauf hätte ein Sicherungsaufruf den Nachweis fehlschlagen lassen. Zusätzlich wurden Schema-/Datendump, `total_changes`, Fremdschlüssel und der unveränderte Hash der Originaldatei geprüft.

```text
Quelle: bereits vorhandene lokale temporaere Bestandsdatenbank, nur lesend geoeffnet.
Arbeitskopie: TemporaryDirectory ausserhalb des Repos.
Vorher: {'aktuell': 1, 'anstehend': [(2, 'import_batch_erkennung'), (3, 'bereiche')], 'basis': False}
Bestand: 6 Sparten; 0 Buchungen
DB-Sicherung vor Schema-Nachzug: <externes TemporaryDirectory>/sicherung-vor-nachzug.db
Migration 3: Entfernte fremde Zuordnungen auswertungsgruppe_sparte: 1
Migration 3: Entfernte fremde Zuordnungen kategorie_globalgruppe: 0
Lauf 1 angewendet: [2, 3]
Nach Lauf 1: {'aktuell': 3, 'anstehend': [], 'basis': False}
Lauf 2 angewendet: []
Nach Lauf 2: {'aktuell': 3, 'anstehend': [], 'basis': False}
Lauf 2 Daten-/Schema-Dump identisch: True
Lauf 2 zusaetzliche Zeilenaenderungen: 0
Fremdschluesselfehler: []
Original unveraendert: True
```

## Review und offene Punkte

- Der unabhängige Review fand einen Fehlerfall beim Rollback von 003: Die fehlende Bereichstabelle verursachte SQL-Fehler auch an Auth-/Diagnose-Endpunkten. Dies ist zentral mit HTTP 503 behoben und mit einer vollständig aufgebauten Vor-P10-Datenbank, tatsächlich scheiternder Migration und `lifespan` getestet; der Nachreview meldet keine blockierenden Befunde.
- Fehlt das Bereichsschema nach einem fehlgeschlagenen Nachzug, bleiben entsprechend der Pflicht zur zentralen Bereichsprüfung auch Login, Health und Schemadiagnose mit einem allgemeinen Nachzug-Hinweis auf HTTP 503 gesperrt, bis das Schema repariert ist. Es wird kein ungeprüfter Ersatzbereich freigegeben.
- Die verfügbare Bestandsdatenbank enthält sechs Sparten und keine Buchungen; eine Produktionsdatenbank ist hier nicht konfiguriert. Die Nachzugsprobe belegt daher Schema-/Gruppennachzug und Idempotenz auf einem tatsächlichen Bestand, keinen produktiven Summenvergleich. Die API-Tests verwenden getrennte synthetische Buchungen beider Bereiche; der Migrationstest enthält Vereinssparte, Vereinskonto, Belege, Regeln und gemischte Gruppen.
- Ein vorhandener POSIX-Dateirechtetest wird auf Windows planmäßig übersprungen. Die Ausgabe enthält außerdem erwartete Fehlersimulationen der Sicherungstests und Warnungen des vorhandenen Bild-Fallbacks, da Pillow in dieser Python-Umgebung nicht installiert ist; es wurde keine Abhängigkeit ergänzt oder installiert.
- Das vorhandene Test-Cleanup mit `taskkill` erhält in dieser Sandbox „Zugriff verweigert“ und hinterlässt `ResourceWarning`-Meldungen. Die in den Laufprotokollen eindeutig identifizierten eigenen Testserver wurden anschließend mit `Stop-Process` beendet (21 im Abschlusslauf; Nachkontrolle: 0 noch laufend); Produktcode und Auth werden hierfür nicht verändert.

Keine offenen fachlichen Implementierungspunkte. Keine Datenbereinigung außerhalb der ausdrücklich verlangten Gruppenzuordnungen, keine echten fachlichen Namen oder Geheimnisse in neuen Fixtures oder im Bericht.
