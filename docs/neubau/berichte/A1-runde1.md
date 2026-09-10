# A1 – frische Sicherung vor Schema-Nachzug

## Auftrag und Umsetzungsplan

Arbeitsverzeichnis: `C:\Users\lblet\dev\wt-a1`, Branch
`fix/a1-sicherung-vor-nachzug`. Keine Commits, kein Push, keine Änderungen
in anderen Worktrees oder unter `docs/superpowers/`.

1. Fehlerpfad in `app/backup.py`, `app/db.py` und dem CLI in `app/migrate.py`
   prüfen; bestehende Callback- und Fehlerverträge erhalten.
2. Regressionstests zuerst ergänzen: aktuelle Daten trotz alter Tageskopie,
   aufeinanderfolgende Nachzüge einschließlich Namenskollision, getrennte
   Rotation, Sicherungsfehler und Wegwerf-Datenbank.
3. `sichere_datenbank` um einen optionalen Vor-Nachzug-Modus erweitern.
   SQLite-Backup-API, Integritätsprüfung und atomare Veröffentlichung verwenden.
   Basisname: `finanz-JJJJ-MM-TT-HHMM-vor-nachzug-v<zielversion>.db`;
   bei Kollision fortlaufend `-2`, `-3`, … ergänzen. Tageskopien behalten
   ihren bisherigen Vertrag. Die zehn zuletzt geschriebenen
   Nachzugssicherungen separat aufbewahren.
4. App- und CLI-Nachzug mit der höchsten anstehenden Zielversion anbinden.
   Fehlgeschlagene Pflichtsicherung liefert weiterhin `MigrationsFehler`;
   ephemere Datenbanken werden nicht gesichert.
5. Betriebsdokumentation aktualisieren, unabhängige Prüfung durchführen,
   gezielte Tests und gesamte unittest-Suite mit dem vorgegebenen Interpreter
   und einer isolierten temporären `FINANZ_DB` ausführen. Vollständige
   Testausgaben unten aufnehmen.

Die konkrete Nutzeranweisung bestimmt Namensschema und Aufbewahrung; die
ältere Formulierung in `SCHULDEN.md` wird dadurch präzisiert. Entwurfs- und
Planungsschritte erfolgen ohne Rückfragen entsprechend dem Auftrag.

## Umsetzung und Sicherheitsnachweis

Der verletzte Vertrag lag zwischen dem Nachzugsrunner und seiner Sicherung:
`db.init_db()` und der CLI-Pfad aus `migrate._main()` riefen beide den
idempotenten Tageskopienmodus auf. Eine gültige Kopie vom Morgen wurde damit
als Sicherung des aktuellen Standes akzeptiert. Ein angreifergesteuerter
Eingabewert ist für diesen Datenverlust nicht erforderlich.

`backup.sichere_datenbank(vor_nachzug_version=...)` erzeugt jetzt im
gemeinsamen Sicherungs-Lock eine frische SQLite-Kopie. Der Zielname wird
exklusiv reserviert, die Kopie zunächst temporär geschrieben, mit
`PRAGMA integrity_check` geprüft und anschließend atomar veröffentlicht.
Fehler liefern `None`; temporäre Dateien und fehlgeschlagene Reservierungen
werden bereinigt. Namenskollisionen werden fortlaufend aufgelöst, auch wenn
die erste Datei durch die Rotation bereits entfernt wurde.

Die separate Rotation berücksichtigt nur Nachzugssicherungen. Maßgeblich
ist der Dateiänderungszeitpunkt; bei gleichen Zeitstempeln werden Datum,
Zielversion und laufende Nummer numerisch berücksichtigt. Die Tagesrotation
behält unverändert 30 Tageskopien einschließlich ihrer zugehörigen Belege
und Manifeste. Nachzugssicherungen unterliegen keiner Altersgrenze.

Beide produktiven Aufrufer übergeben die höchste anstehende Zielversion.
Der bestehende parameterlose Callback-Vertrag von `migrate.anwenden()`
bleibt erhalten. Zusätzlich liefert der CLI-Sicherungsadapter bei einem
Fehler korrekt `None` statt `Path("")`; dadurch wird die bestehende
Pflichtprüfung auch dort wirksam. Der App-Start fängt `MigrationsFehler`
weiterhin ab und aktiviert den Schreibschutz. Ohne anstehende Migrationen
wird der Callback nicht ausgeführt; bei einer ephemeren Datenbank erfolgt
keine Sicherung.

Die unabhängige Untersuchung hat beide Aufrufer geprüft. Die unabhängige
Kandidatenprüfung fand die alphabetische Sortierung laufender Zusätze bei
identischen Zeitstempeln. Dieser Befund wurde durch einen fehlschlagenden
Test bestätigt und durch numerische Sortierung behoben.

## Begründung der erlaubten Teständerung

In `tests/test_migrate.py` wurde ausschließlich
`test_alte_datenbank_erhaelt_basis_version_und_einmalige_sicherung`
geändert. Seine bisherigen beiden Erwartungen verlangten eine Tageskopie
und schrieben damit A1 fest. Jetzt verlangt er genau eine eigene
Vor-Nachzug-Datei für Zielversion 9 und keine Tageskopie. Beim zweiten
Start ohne anstehende Migration muss genau dieselbe Dateiliste bestehen
bleiben. Die Prüfungen zu Basisversion und angewendeten Migrationen bleiben
erhalten. Ein AST-Vergleich mit `HEAD` bestätigt, dass kein anderer
bestehender Test geändert oder entfernt wurde.

Zehn neue Tests in `tests/test_backup_nachzug.py` prüfen:

- Morgenkopie bleibt unverändert; Vor-Nachzug-Kopie enthält die später
  gebuchten Testdaten und noch keine Änderungen der folgenden Migrationen.
- Zwei Nachzüge derselben Zielversion in derselben Minute überschreiben
  keine Datei und enthalten jeweils den aktuellen Stand.
- Tagesrotation entfernt alte Tageskopien und lässt Nachzugssicherungen
  stehen; nach einem weiteren Nachzug bleiben separat die letzten zehn.
- Ein nicht beschreibbares Sicherungsziel stoppt die Pflichtmigration.
- Eine Wegwerf-Datenbank überspringt die Sicherung auch bei unbrauchbarem Ziel.
- Ein echter Sicherungsfehler führt über den App-Lebenszyklus zum Schreibschutz.
- Eine ungültige Kopie stoppt die Migration und hinterlässt keine Tempdateien.
- Zwölf echte Sicherungen behalten die zehn jüngsten Datenstände.
- Gleiche Datei-Zeitstempel werden anhand numerischer Zusätze richtig sortiert.
- Der CLI-Nachzug sichert frisch und bricht bei einer fehlenden Pflichtkopie ab.

Alle neuen Tests verwenden `tempfile.TemporaryDirectory()`.

## Testumgebung

Interpreter: `C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Scripts\python.exe`.
Arbeitsverzeichnis bei allen Läufen: `C:\Users\lblet\dev\wt-a1`.
Der Teststarter setzt `FINANZ_DB` auf eine eigene Wegwerf-Datei unter
`C:\Users\lblet\AppData\Local\Temp\finanz-a1-suite-*\wegwerf.db` und
deaktiviert für den Testlauf das optionale Sicherungszweitziel.

Der erste direkte Versuch scheiterte vor den Testhandlungen an Windows-ACLs:
Python 3.12 erzeugt bei `TemporaryDirectory()` mit Modus `0700` eine neue
DACL, die in dieser Sandbox den ausführenden Prozess aussperrt
(`PermissionError: [WinError 5]`). Ein Schreibtest mit geerbten ACLs war
erfolgreich. Der unten vollständig dokumentierte Teststarter lässt deshalb
ausschließlich neue temporäre Testordner die ACL des Temp-Verzeichnisses
erben. Er verändert weder Tests noch Produktivcode, Authentifizierung,
Validierung, Assertions oder Testauswahl. Es wurden keine Abhängigkeiten
installiert.

Der folgende Gesamtlauf blieb bei `test_kredit.KreditApiTest` hängen:
Dieser bestehende Test übergibt `TemporaryDirectory()` ausdrücklich
`dir="C:\\Users\\lblet\\dev"`, außerhalb des zulässigen Schreibbereichs.
Der Teststarter leitet genau diesen temporären Basispfad nach
`tempfile.gettempdir()` um. Der Kredit-Test wurde nicht verändert.
Die anschließende gezielte Kredit-Prüfung bestand mit **5 Tests, OK**.
Danach wurde die gesamte Suite erneut gestartet.

Ein früherer Gesamtlauf wurde nach weiteren Codekorrekturen beendet und
mit dem endgültigen Stand neu gestartet. Dabei wurden ausschließlich die
identifizierten Prozesse des eigenen A1-Teststarters und seine verwaisten
Uvicorn-Nachkommen beendet; andere
Worktrees und deren Testläufe wurden nicht verändert. Die langsamen
Integrationstests machten bis zum genannten Kredit-Test weiter Fortschritt.
Die WMI-Prozessabfrage per `Get-CimInstance` war in der Sandbox nicht erlaubt.
Die Bereinigung erfolgte deshalb über die Windows-Prozessliste und Prüfung
von Prozessabstammung sowie Uvicorn-Kommandozeile; andere Prozesse wurden
nicht beendet.

## Prüfstände

- Regression vor Implementierung: sechs Tests, vier erwartete Fehlschläge
  (frische App-/CLI-Sicherung, separate Rotation, aufeinanderfolgende Dateien).
- Zusätzlicher Belastungstest: zwölf Sicherungen deckten die Wiederverwendung
  eines schon wegrotierten Basisnamens auf; fortlaufende Nummerierung korrigiert.
- Review-Regression bei gleichen Zeitstempeln: ein erwarteter Fehlschlag,
  anschließend behoben.
- Abschließende fokussierte Prüfung: **34 Tests, OK**.
- Syntaxprüfung der fünf betroffenen Python-Dateien: bestanden.
- `git diff --check`: bestanden; Git weist lediglich auf die konfigurierte
  spätere LF/CRLF-Konvertierung hin.
- Abschließende Gesamtsuite: **210 Tests in 211,753 Sekunden, OK (skipped=1), Exitcode 0**. 209 bestanden; der bereits vorhandene POSIX-Dateirechtetest wird unter Windows plattformbedingt übersprungen.

## Abgrenzung

Es wurden keine produktiven Finanzdaten gelesen oder verändert. Die
Sicherungsszenarien wurden mit echten SQLite-Dateien und synthetischen
Testdaten reproduziert. Tagesmanifest, Belegsicherung, Zweitziel und
bestehende Ad-hoc-Nachrüstungen in `db.init_db()` wurden nicht umgebaut;
der neue Modus schützt den versionierten Schema-Nachzug. Die aktuelle
Nutzeranweisung verlangt eine separate Datenbankkopie, keine Erweiterung
des Tagesmanifests. Andere Schuldenbefunde bleiben außerhalb von A1.


## Ergebnis

**fixed** – A1 ist behoben. Die reproduzierte Morgen-/Abend-Konstellation
liefert eine eigene aktuelle Vor-Nachzug-Kopie; die Morgenkopie bleibt
unverändert. Tageskopien, Belege, Authentifizierung und Validierung bestehen
ihre vorhandenen Tests. Die Suite mit 210 Tests wurde vollständig beendet:
209 bestanden und ein bereits vorhandener Plattform-Skip für
`test_store_setzt_dateimodus_0600` (`POSIX-Dateirechte`). Dieser POSIX-Test
ist unter dem vorgegebenen Windows-Interpreter nicht anwendbar; sein
Skip wurde weder hinzugefügt noch verändert. Keine weiteren Prüfungen
wurden ausgelassen.

Basis-Commit: `501f6ca7026b8f45ebd8abe924d3fee49fdb07a3`.
Geändert: `app/backup.py`, `app/db.py`, `app/migrate.py`,
`tests/test_migrate.py`, `docs/BETRIEB-UND-ARCHITEKTUR.md`.
Neu: `tests/test_backup_nachzug.py` und dieser Bericht.
Keine Commits, kein Push, keine Änderungen in anderen Worktrees.

## Reproduktion der Testläufe

Den folgenden ausschließlich für diese Windows-Sandbox benötigten Starter
bei Bedarf als `outputs/a1_testlauf.py` im Worktree speichern. Er lädt die
gesamte Suite über `unittest.defaultTestLoader.discover("tests", "test*.py")`;
der Starter fügt keine Filterung oder Überspringung von Tests hinzu.

```python
"""Isolierter A1-Testlauf; Windows-Sandbox-ACLs fuer temporaere Ordner erben."""
import os
import pathlib
import sys
import tempfile
import unittest

# Python 3.12 erstellt mode=0o700 auf Windows mit einer neuen DACL, die den
# Sandbox-SID aussperrt. Nur temporaere Testordner erben stattdessen die ACL
# des bereits zugelassenen Temp-Verzeichnisses. Kein Produktivcode-Patch.
_mkdir = os.mkdir


def _temp_mkdir(path, mode=0o777, *, dir_fd=None):
    if mode == 0o700 and pathlib.Path(path).resolve().is_relative_to(
        pathlib.Path(tempfile.gettempdir()).resolve()
    ):
        mode = 0o777
    return _mkdir(path, mode, dir_fd=dir_fd)


os.mkdir = _temp_mkdir
_mkdtemp = tempfile.mkdtemp


def _test_mkdtemp(suffix=None, prefix=None, dir=None):
    # Ein vorhandener Kredit-Test nennt den Entwicklerordner explizit.
    # Seine Wegwerf-Dateien gehoeren in dieser Sandbox in den Temp-Ordner.
    if dir is not None and pathlib.Path(dir) == pathlib.Path(r"C:\Users\lblet\dev"):
        dir = tempfile.gettempdir()
    return _mkdtemp(suffix=suffix, prefix=prefix, dir=dir)


tempfile.mkdtemp = _test_mkdtemp
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory(
    prefix="finanz-a1-suite-", dir=r"C:\Users\lblet\AppData\Local\Temp"
) as tmp:
    os.environ["FINANZ_DB"] = str(pathlib.Path(tmp) / "wegwerf.db")
    os.environ["FINANZ_BACKUP_ZIEL2"] = ""
    suite = unittest.TestSuite(
        unittest.defaultTestLoader.discover("tests", pattern=pattern)
        for pattern in (sys.argv[1:] or ["test*.py"])
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(not result.wasSuccessful())
```

Ausgeführte Testbefehle (Arbeitsverzeichnis jeweils dieser Worktree):

```powershell
& C:/Users/lblet/dev/finanz-dashboard-sparten/.venv/Scripts/python.exe outputs/a1_testlauf.py test_backup_nachzug.py
& C:/Users/lblet/dev/finanz-dashboard-sparten/.venv/Scripts/python.exe outputs/a1_testlauf.py 'test_backup*.py' test_migrate.py
& C:/Users/lblet/dev/finanz-dashboard-sparten/.venv/Scripts/python.exe outputs/a1_testlauf.py test_kredit.py
& C:/Users/lblet/dev/finanz-dashboard-sparten/.venv/Scripts/python.exe outputs/a1_testlauf.py
git diff --check
```

Die Logdateien wurden über `subprocess.Popen` bzw. `subprocess.run` mit
`stdout=log, stderr=subprocess.STDOUT` vollständig erfasst. Die beim
Fehlertest absichtlich erzeugten Sicherungs-Tracebacks gehören zur
erwarteten Fehlerprüfung, nicht zu fehlgeschlagenen Tests.

## Vollständige Testausgaben

Die folgenden Ausgaben enthalten auch die roten Entwicklungsstände und
die beiden ausdrücklich abgebrochenen Gesamtläufe. Maßgeblich für die
Freigabe ist der letzte, vollständige Gesamtlauf mit 210 Tests und Exitcode 0.
Die erste rote Ausgabe enthält zusätzlich PowerShells Darstellung von
stderr als `NativeCommandError`.

### Regression vor Implementierung

```text
python.exe : test_cli_sichert_frisch_und_bricht_bei_sicherungsfehler_ab 
(test_backup_nachzug.NachzugSicherungTest.test_cli_sichert_frisch_und_bricht_bei_sicherungsfehler_ab) ... FAIL
In Zeile:2 Zeichen:32
+ ... NG='utf-8'; & C:/Users/lblet/dev/finanz-dashboard-sparten/.venv/Scrip ...
+                 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (test_cli_sicher...er_ab) ... FAIL:String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
 
test_nachzug_sichert_aktuellen_stand_trotz_tageskopie 
(test_backup_nachzug.NachzugSicherungTest.test_nachzug_sichert_aktuellen_stand_trotz_tageskopie) ... FAIL
test_rotation_behaelt_zehn_nachzuege_unabhaengig_von_tageskopien 
(test_backup_nachzug.NachzugSicherungTest.test_rotation_behaelt_zehn_nachzuege_unabhaengig_von_tageskopien) ... FAIL
test_schreibfehler_stoppt_pflichtnachzug 
(test_backup_nachzug.NachzugSicherungTest.test_schreibfehler_stoppt_pflichtnachzug) ... DB-Sicherung fehlgeschlagen 
(Betrieb laeuft weiter)
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\backup.py", line 257, in sichere_datenbank
    ziel_ordner.mkdir(parents=True, exist_ok=True)
  File "C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\pathlib.py", line 1311, in mkdir
    os.mkdir(self, mode)
  File "C:\Users\lblet\dev\wt-a1\outputs\a1_testlauf.py", line 19, in _temp_mkdir
    return _mkdir(path, mode, dir_fd=dir_fd)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
FileExistsError: [WinError 183] Eine Datei kann nicht erstellt werden, wenn sie bereits vorhanden ist: 
'C:\\Users\\lblet\\AppData\\Local\\Temp\\finanz-a1-10qncy00\\backup'
ok
test_wegwerf_datenbank_ueberspringt_sicherung 
(test_backup_nachzug.NachzugSicherungTest.test_wegwerf_datenbank_ueberspringt_sicherung) ... ok
test_zwei_nachzuege_in_derselben_minute_ueberschreiben_nichts 
(test_backup_nachzug.NachzugSicherungTest.test_zwei_nachzuege_in_derselben_minute_ueberschreiben_nichts) ... FAIL

======================================================================
FAIL: test_cli_sichert_frisch_und_bricht_bei_sicherungsfehler_ab 
(test_backup_nachzug.NachzugSicherungTest.test_cli_sichert_frisch_und_bricht_bei_sicherungsfehler_ab)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\tests\test_backup_nachzug.py", line 139, in 
test_cli_sichert_frisch_und_bricht_bei_sicherungsfehler_ab
    self.assertEqual(1, len(sicherungen))
AssertionError: 1 != 0

======================================================================
FAIL: test_nachzug_sichert_aktuellen_stand_trotz_tageskopie 
(test_backup_nachzug.NachzugSicherungTest.test_nachzug_sichert_aktuellen_stand_trotz_tageskopie)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\tests\test_backup_nachzug.py", line 65, in 
test_nachzug_sichert_aktuellen_stand_trotz_tageskopie
    self.assertEqual(1, len(sicherungen))
AssertionError: 1 != 0

======================================================================
FAIL: test_rotation_behaelt_zehn_nachzuege_unabhaengig_von_tageskopien 
(test_backup_nachzug.NachzugSicherungTest.test_rotation_behaelt_zehn_nachzuege_unabhaengig_von_tageskopien)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\tests\test_backup_nachzug.py", line 114, in 
test_rotation_behaelt_zehn_nachzuege_unabhaengig_von_tageskopien
    self.assertEqual(10, len(aktuelle))
AssertionError: 10 != 12

======================================================================
FAIL: test_zwei_nachzuege_in_derselben_minute_ueberschreiben_nichts 
(test_backup_nachzug.NachzugSicherungTest.test_zwei_nachzuege_in_derselben_minute_ueberschreiben_nichts)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\tests\test_backup_nachzug.py", line 80, in 
test_zwei_nachzuege_in_derselben_minute_ueberschreiben_nichts
    self.assertEqual(1, len(erste))
AssertionError: 1 != 0

----------------------------------------------------------------------
Ran 6 tests in 2.605s

FAILED (failures=4)
Angewendet: [1]
```

### Zwischenstand mit aufgedeckter Namenswiederverwendung

```text
test_belege_manifest_und_pruefsummen_werden_gesichert (test_backup.BackupTest.test_belege_manifest_und_pruefsummen_werden_gesichert) ... ok
test_belegsicherung_ohne_db_kopie_schreibt_db_null (test_backup.BackupTest.test_belegsicherung_ohne_db_kopie_schreibt_db_null) ... ok
test_beschaedigte_tagesdatei_wird_durch_gueltige_sicherung_ersetzt (test_backup.BackupTest.test_beschaedigte_tagesdatei_wird_durch_gueltige_sicherung_ersetzt) ... ok
test_betriebsstatus_enthaelt_nur_oeffentliche_sicherungsfelder (test_backup.BackupTest.test_betriebsstatus_enthaelt_nur_oeffentliche_sicherungsfelder) ... ok
test_fehlender_beleg_steht_im_manifest_und_db_sicherung_bleibt_erfolgreich (test_backup.BackupTest.test_fehlender_beleg_steht_im_manifest_und_db_sicherung_bleibt_erfolgreich) ... ok
test_fehlgeschlagene_sicherung_hinterlaesst_keine_tagesdatei (test_backup.BackupTest.test_fehlgeschlagene_sicherung_hinterlaesst_keine_tagesdatei) ... DB-Sicherung fehlgeschlagen (Betrieb laeuft weiter)
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\backup.py", line 334, in sichere_datenbank
    quelle.backup(kopie)
  File "C:\Users\lblet\dev\wt-a1\tests\test_backup.py", line 231, in backup
    raise sqlite3.OperationalError("simulierter Abbruch")
sqlite3.OperationalError: simulierter Abbruch
ok
test_geloeschte_belegkopie_wird_beim_zweiten_lauf_erneuert (test_backup.BackupTest.test_geloeschte_belegkopie_wird_beim_zweiten_lauf_erneuert) ... ok
test_identische_originalnamen_in_verschiedenen_sparten_bleiben_getrennt (test_backup.BackupTest.test_identische_originalnamen_in_verschiedenen_sparten_bleiben_getrennt) ... ok
test_ohne_zweitziel_bleibt_alles_wie_bisher (test_backup.BackupTest.test_ohne_zweitziel_bleibt_alles_wie_bisher) ... ok
test_pruefe_sicherung_erkennt_manipulierte_belegkopie (test_backup.BackupTest.test_pruefe_sicherung_erkennt_manipulierte_belegkopie) ... ok
test_rotation_entfernt_db_belegordner_und_manifest_gemeinsam (test_backup.BackupTest.test_rotation_entfernt_db_belegordner_und_manifest_gemeinsam) ... ok
test_unerreichbares_zweitziel_laesst_erstkopie_gueltig (test_backup.BackupTest.test_unerreichbares_zweitziel_laesst_erstkopie_gueltig) ... DB-Sicherung auf Zweitziel fehlgeschlagen, Erstkopie bleibt gueltig (\\kein-host-xyz-existiert\share\backup)
Traceback (most recent call last):
  File "C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\pathlib.py", line 1311, in mkdir
    os.mkdir(self, mode)
  File "C:\Users\lblet\dev\wt-a1\outputs\a1_testlauf.py", line 19, in _temp_mkdir
    return _mkdir(path, mode, dir_fd=dir_fd)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
PermissionError: [WinError 5] Zugriff verweigert: '\\\\kein-host-xyz-existiert\\share\\backup'

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\backup.py", line 364, in _sichere_auf_zweitziel
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
ok
test_zweiter_lauf_am_selben_tag_ist_idempotent (test_backup.BackupTest.test_zweiter_lauf_am_selben_tag_ist_idempotent) ... ok
test_zweitziel_erhaelt_eine_gueltige_zweitkopie (test_backup.BackupTest.test_zweitziel_erhaelt_eine_gueltige_zweitkopie) ... ok
test_cli_sichert_frisch_und_bricht_bei_sicherungsfehler_ab (test_backup_nachzug.NachzugSicherungTest.test_cli_sichert_frisch_und_bricht_bei_sicherungsfehler_ab) ... ok
test_nachzug_sichert_aktuellen_stand_trotz_tageskopie (test_backup_nachzug.NachzugSicherungTest.test_nachzug_sichert_aktuellen_stand_trotz_tageskopie) ... ok
test_rotation_behaelt_zehn_nachzuege_unabhaengig_von_tageskopien (test_backup_nachzug.NachzugSicherungTest.test_rotation_behaelt_zehn_nachzuege_unabhaengig_von_tageskopien) ... ok
test_schreibfehler_stoppt_pflichtnachzug (test_backup_nachzug.NachzugSicherungTest.test_schreibfehler_stoppt_pflichtnachzug) ... DB-Sicherung vor Schema-Nachzug fehlgeschlagen
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\backup.py", line 241, in _sichere_vor_nachzug
    ziel_ordner.mkdir(parents=True, exist_ok=True)
  File "C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\pathlib.py", line 1311, in mkdir
    os.mkdir(self, mode)
  File "C:\Users\lblet\dev\wt-a1\outputs\a1_testlauf.py", line 19, in _temp_mkdir
    return _mkdir(path, mode, dir_fd=dir_fd)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
FileExistsError: [WinError 183] Eine Datei kann nicht erstellt werden, wenn sie bereits vorhanden ist: 'C:\\Users\\lblet\\AppData\\Local\\Temp\\finanz-a1-se06wsi_\\backup'
ok
test_sicherungsfehler_startet_app_schreibgeschuetzt (test_backup_nachzug.NachzugSicherungTest.test_sicherungsfehler_startet_app_schreibgeschuetzt) ... DB-Sicherung vor Schema-Nachzug fehlgeschlagen
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\backup.py", line 241, in _sichere_vor_nachzug
    ziel_ordner.mkdir(parents=True, exist_ok=True)
  File "C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\pathlib.py", line 1311, in mkdir
    os.mkdir(self, mode)
  File "C:\Users\lblet\dev\wt-a1\outputs\a1_testlauf.py", line 19, in _temp_mkdir
    return _mkdir(path, mode, dir_fd=dir_fd)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
FileExistsError: [WinError 183] Eine Datei kann nicht erstellt werden, wenn sie bereits vorhanden ist: 'C:\\Users\\lblet\\AppData\\Local\\Temp\\finanz-a1-5h_zykf5\\backup'
ok
test_ungueltige_kopie_stoppt_nachzug_und_entfernt_tempdateien (test_backup_nachzug.NachzugSicherungTest.test_ungueltige_kopie_stoppt_nachzug_und_entfernt_tempdateien) ... DB-Sicherung vor Schema-Nachzug fehlgeschlagen
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\backup.py", line 266, in _sichere_vor_nachzug
    raise sqlite3.DatabaseError("Sicherung vor Nachzug ist nicht intakt")
sqlite3.DatabaseError: Sicherung vor Nachzug ist nicht intakt
ok
test_wegwerf_datenbank_ueberspringt_sicherung (test_backup_nachzug.NachzugSicherungTest.test_wegwerf_datenbank_ueberspringt_sicherung) ... ok
test_zwei_nachzuege_in_derselben_minute_ueberschreiben_nichts (test_backup_nachzug.NachzugSicherungTest.test_zwei_nachzuege_in_derselben_minute_ueberschreiben_nichts) ... ok
test_zwoelf_frische_sicherungen_behalten_die_letzten_zehn (test_backup_nachzug.NachzugSicherungTest.test_zwoelf_frische_sicherungen_behalten_die_letzten_zehn) ... FAIL
test_alte_datenbank_erhaelt_basis_version_und_einmalige_sicherung (test_migrate.MigrationTest.test_alte_datenbank_erhaelt_basis_version_und_einmalige_sicherung) ... ok
test_fehlende_sicherung_ist_bei_wegwerf_datenbank_erlaubt (test_migrate.MigrationTest.test_fehlende_sicherung_ist_bei_wegwerf_datenbank_erlaubt) ... ok
test_fehlerhafte_migration_rollt_zurueck_und_sperrt_version (test_migrate.MigrationTest.test_fehlerhafte_migration_rollt_zurueck_und_sperrt_version) ... ok
test_fehlgeschlagene_pflichtsicherung_stoppt_nachzug (test_migrate.MigrationTest.test_fehlgeschlagene_pflichtsicherung_stoppt_nachzug) ... ok
test_migrationsfehler_startet_app_schreibgeschuetzt (test_migrate.MigrationTest.test_migrationsfehler_startet_app_schreibgeschuetzt) ... ok
test_neue_datenbank_ist_auf_version_9_ohne_anstehende_migrationen (test_migrate.MigrationTest.test_neue_datenbank_ist_auf_version_9_ohne_anstehende_migrationen) ... ok
test_neue_und_alte_datenbank_haben_gleiche_tabellenliste (test_migrate.MigrationTest.test_neue_und_alte_datenbank_haben_gleiche_tabellenliste) ... ok
test_schema_endpoint_liefert_erwartete_felder (test_migrate.MigrationTest.test_schema_endpoint_liefert_erwartete_felder) ... ok
test_schreibschutz_blockiert_auth_login_nicht (test_migrate.MigrationTest.test_schreibschutz_blockiert_auth_login_nicht) ... ok
test_schreibschutz_blockiert_post_aber_nicht_get (test_migrate.MigrationTest.test_schreibschutz_blockiert_post_aber_nicht_get) ... ok

======================================================================
FAIL: test_zwoelf_frische_sicherungen_behalten_die_letzten_zehn (test_backup_nachzug.NachzugSicherungTest.test_zwoelf_frische_sicherungen_behalten_die_letzten_zehn)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\tests\test_backup_nachzug.py", line 166, in test_zwoelf_frische_sicherungen_behalten_die_letzten_zehn
    self.assertEqual(12, len(set(pfade)))
AssertionError: 12 != 11

----------------------------------------------------------------------
Ran 33 tests in 10.366s

FAILED (failures=1)
Angewendet: [1]
```

### Review-Regression mit gleichen Zeitstempeln

```text
test_cli_sichert_frisch_und_bricht_bei_sicherungsfehler_ab (test_backup_nachzug.NachzugSicherungTest.test_cli_sichert_frisch_und_bricht_bei_sicherungsfehler_ab) ... ok
test_nachzug_sichert_aktuellen_stand_trotz_tageskopie (test_backup_nachzug.NachzugSicherungTest.test_nachzug_sichert_aktuellen_stand_trotz_tageskopie) ... ok
test_rotation_behaelt_zehn_nachzuege_unabhaengig_von_tageskopien (test_backup_nachzug.NachzugSicherungTest.test_rotation_behaelt_zehn_nachzuege_unabhaengig_von_tageskopien) ... ok
test_rotation_ordnet_gleiche_zeitstempel_nach_laufender_nummer (test_backup_nachzug.NachzugSicherungTest.test_rotation_ordnet_gleiche_zeitstempel_nach_laufender_nummer) ... FAIL
test_schreibfehler_stoppt_pflichtnachzug (test_backup_nachzug.NachzugSicherungTest.test_schreibfehler_stoppt_pflichtnachzug) ... DB-Sicherung vor Schema-Nachzug fehlgeschlagen
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\backup.py", line 241, in _sichere_vor_nachzug
    ziel_ordner.mkdir(parents=True, exist_ok=True)
  File "C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\pathlib.py", line 1311, in mkdir
    os.mkdir(self, mode)
  File "C:\Users\lblet\dev\wt-a1\outputs\a1_testlauf.py", line 19, in _temp_mkdir
    return _mkdir(path, mode, dir_fd=dir_fd)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
FileExistsError: [WinError 183] Eine Datei kann nicht erstellt werden, wenn sie bereits vorhanden ist: 'C:\\Users\\lblet\\AppData\\Local\\Temp\\finanz-a1-4z2xopb4\\backup'
ok
test_sicherungsfehler_startet_app_schreibgeschuetzt (test_backup_nachzug.NachzugSicherungTest.test_sicherungsfehler_startet_app_schreibgeschuetzt) ... DB-Sicherung vor Schema-Nachzug fehlgeschlagen
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\backup.py", line 241, in _sichere_vor_nachzug
    ziel_ordner.mkdir(parents=True, exist_ok=True)
  File "C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\pathlib.py", line 1311, in mkdir
    os.mkdir(self, mode)
  File "C:\Users\lblet\dev\wt-a1\outputs\a1_testlauf.py", line 19, in _temp_mkdir
    return _mkdir(path, mode, dir_fd=dir_fd)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
FileExistsError: [WinError 183] Eine Datei kann nicht erstellt werden, wenn sie bereits vorhanden ist: 'C:\\Users\\lblet\\AppData\\Local\\Temp\\finanz-a1-i_trw9ek\\backup'
ok
test_ungueltige_kopie_stoppt_nachzug_und_entfernt_tempdateien (test_backup_nachzug.NachzugSicherungTest.test_ungueltige_kopie_stoppt_nachzug_und_entfernt_tempdateien) ... DB-Sicherung vor Schema-Nachzug fehlgeschlagen
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\backup.py", line 272, in _sichere_vor_nachzug
    raise sqlite3.DatabaseError("Sicherung vor Nachzug ist nicht intakt")
sqlite3.DatabaseError: Sicherung vor Nachzug ist nicht intakt
ok
test_wegwerf_datenbank_ueberspringt_sicherung (test_backup_nachzug.NachzugSicherungTest.test_wegwerf_datenbank_ueberspringt_sicherung) ... ok
test_zwei_nachzuege_in_derselben_minute_ueberschreiben_nichts (test_backup_nachzug.NachzugSicherungTest.test_zwei_nachzuege_in_derselben_minute_ueberschreiben_nichts) ... ok
test_zwoelf_frische_sicherungen_behalten_die_letzten_zehn (test_backup_nachzug.NachzugSicherungTest.test_zwoelf_frische_sicherungen_behalten_die_letzten_zehn) ... ok

======================================================================
FAIL: test_rotation_ordnet_gleiche_zeitstempel_nach_laufender_nummer (test_backup_nachzug.NachzugSicherungTest.test_rotation_ordnet_gleiche_zeitstempel_nach_laufender_nummer)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\tests\test_backup_nachzug.py", line 181, in test_rotation_ordnet_gleiche_zeitstempel_nach_laufender_nummer
    self.assertEqual(set(pfade[1:]), set(self.ordner.glob("*.db")))
AssertionError: Items in the first set but not the second:
WindowsPath('C:/Users/lblet/AppData/Local/Temp/finanz-a1-v7dj_peh/backup/finanz-2026-09-10-1830-vor-nachzug-v1-10.db')
Items in the second set but not the first:
WindowsPath('C:/Users/lblet/AppData/Local/Temp/finanz-a1-v7dj_peh/backup/finanz-2026-09-10-1830-vor-nachzug-v1.db')

----------------------------------------------------------------------
Ran 10 tests in 5.933s

FAILED (failures=1)
Angewendet: [1]
```

### Abschließende fokussierte Prüfung

```text
test_belege_manifest_und_pruefsummen_werden_gesichert (test_backup.BackupTest.test_belege_manifest_und_pruefsummen_werden_gesichert) ... ok
test_belegsicherung_ohne_db_kopie_schreibt_db_null (test_backup.BackupTest.test_belegsicherung_ohne_db_kopie_schreibt_db_null) ... ok
test_beschaedigte_tagesdatei_wird_durch_gueltige_sicherung_ersetzt (test_backup.BackupTest.test_beschaedigte_tagesdatei_wird_durch_gueltige_sicherung_ersetzt) ... ok
test_betriebsstatus_enthaelt_nur_oeffentliche_sicherungsfelder (test_backup.BackupTest.test_betriebsstatus_enthaelt_nur_oeffentliche_sicherungsfelder) ... ok
test_fehlender_beleg_steht_im_manifest_und_db_sicherung_bleibt_erfolgreich (test_backup.BackupTest.test_fehlender_beleg_steht_im_manifest_und_db_sicherung_bleibt_erfolgreich) ... ok
test_fehlgeschlagene_sicherung_hinterlaesst_keine_tagesdatei (test_backup.BackupTest.test_fehlgeschlagene_sicherung_hinterlaesst_keine_tagesdatei) ... DB-Sicherung fehlgeschlagen (Betrieb laeuft weiter)
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\backup.py", line 346, in sichere_datenbank
    quelle.backup(kopie)
  File "C:\Users\lblet\dev\wt-a1\tests\test_backup.py", line 231, in backup
    raise sqlite3.OperationalError("simulierter Abbruch")
sqlite3.OperationalError: simulierter Abbruch
ok
test_geloeschte_belegkopie_wird_beim_zweiten_lauf_erneuert (test_backup.BackupTest.test_geloeschte_belegkopie_wird_beim_zweiten_lauf_erneuert) ... ok
test_identische_originalnamen_in_verschiedenen_sparten_bleiben_getrennt (test_backup.BackupTest.test_identische_originalnamen_in_verschiedenen_sparten_bleiben_getrennt) ... ok
test_ohne_zweitziel_bleibt_alles_wie_bisher (test_backup.BackupTest.test_ohne_zweitziel_bleibt_alles_wie_bisher) ... ok
test_pruefe_sicherung_erkennt_manipulierte_belegkopie (test_backup.BackupTest.test_pruefe_sicherung_erkennt_manipulierte_belegkopie) ... ok
test_rotation_entfernt_db_belegordner_und_manifest_gemeinsam (test_backup.BackupTest.test_rotation_entfernt_db_belegordner_und_manifest_gemeinsam) ... ok
test_unerreichbares_zweitziel_laesst_erstkopie_gueltig (test_backup.BackupTest.test_unerreichbares_zweitziel_laesst_erstkopie_gueltig) ... DB-Sicherung auf Zweitziel fehlgeschlagen, Erstkopie bleibt gueltig (\\kein-host-xyz-existiert\share\backup)
Traceback (most recent call last):
  File "C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\pathlib.py", line 1311, in mkdir
    os.mkdir(self, mode)
  File "C:\Users\lblet\dev\wt-a1\outputs\a1_testlauf.py", line 19, in _temp_mkdir
    return _mkdir(path, mode, dir_fd=dir_fd)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
PermissionError: [WinError 5] Zugriff verweigert: '\\\\kein-host-xyz-existiert\\share\\backup'

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\backup.py", line 376, in _sichere_auf_zweitziel
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
ok
test_zweiter_lauf_am_selben_tag_ist_idempotent (test_backup.BackupTest.test_zweiter_lauf_am_selben_tag_ist_idempotent) ... ok
test_zweitziel_erhaelt_eine_gueltige_zweitkopie (test_backup.BackupTest.test_zweitziel_erhaelt_eine_gueltige_zweitkopie) ... ok
test_cli_sichert_frisch_und_bricht_bei_sicherungsfehler_ab (test_backup_nachzug.NachzugSicherungTest.test_cli_sichert_frisch_und_bricht_bei_sicherungsfehler_ab) ... ok
test_nachzug_sichert_aktuellen_stand_trotz_tageskopie (test_backup_nachzug.NachzugSicherungTest.test_nachzug_sichert_aktuellen_stand_trotz_tageskopie) ... ok
test_rotation_behaelt_zehn_nachzuege_unabhaengig_von_tageskopien (test_backup_nachzug.NachzugSicherungTest.test_rotation_behaelt_zehn_nachzuege_unabhaengig_von_tageskopien) ... ok
test_rotation_ordnet_gleiche_zeitstempel_nach_laufender_nummer (test_backup_nachzug.NachzugSicherungTest.test_rotation_ordnet_gleiche_zeitstempel_nach_laufender_nummer) ... ok
test_schreibfehler_stoppt_pflichtnachzug (test_backup_nachzug.NachzugSicherungTest.test_schreibfehler_stoppt_pflichtnachzug) ... DB-Sicherung vor Schema-Nachzug fehlgeschlagen
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\backup.py", line 242, in _sichere_vor_nachzug
    ziel_ordner.mkdir(parents=True, exist_ok=True)
  File "C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\pathlib.py", line 1311, in mkdir
    os.mkdir(self, mode)
  File "C:\Users\lblet\dev\wt-a1\outputs\a1_testlauf.py", line 19, in _temp_mkdir
    return _mkdir(path, mode, dir_fd=dir_fd)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
FileExistsError: [WinError 183] Eine Datei kann nicht erstellt werden, wenn sie bereits vorhanden ist: 'C:\\Users\\lblet\\AppData\\Local\\Temp\\finanz-a1-n1b3fkrp\\backup'
ok
test_sicherungsfehler_startet_app_schreibgeschuetzt (test_backup_nachzug.NachzugSicherungTest.test_sicherungsfehler_startet_app_schreibgeschuetzt) ... DB-Sicherung vor Schema-Nachzug fehlgeschlagen
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\backup.py", line 242, in _sichere_vor_nachzug
    ziel_ordner.mkdir(parents=True, exist_ok=True)
  File "C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\pathlib.py", line 1311, in mkdir
    os.mkdir(self, mode)
  File "C:\Users\lblet\dev\wt-a1\outputs\a1_testlauf.py", line 19, in _temp_mkdir
    return _mkdir(path, mode, dir_fd=dir_fd)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
FileExistsError: [WinError 183] Eine Datei kann nicht erstellt werden, wenn sie bereits vorhanden ist: 'C:\\Users\\lblet\\AppData\\Local\\Temp\\finanz-a1-b5lkk3tu\\backup'
ok
test_ungueltige_kopie_stoppt_nachzug_und_entfernt_tempdateien (test_backup_nachzug.NachzugSicherungTest.test_ungueltige_kopie_stoppt_nachzug_und_entfernt_tempdateien) ... DB-Sicherung vor Schema-Nachzug fehlgeschlagen
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\backup.py", line 273, in _sichere_vor_nachzug
    raise sqlite3.DatabaseError("Sicherung vor Nachzug ist nicht intakt")
sqlite3.DatabaseError: Sicherung vor Nachzug ist nicht intakt
ok
test_wegwerf_datenbank_ueberspringt_sicherung (test_backup_nachzug.NachzugSicherungTest.test_wegwerf_datenbank_ueberspringt_sicherung) ... ok
test_zwei_nachzuege_in_derselben_minute_ueberschreiben_nichts (test_backup_nachzug.NachzugSicherungTest.test_zwei_nachzuege_in_derselben_minute_ueberschreiben_nichts) ... ok
test_zwoelf_frische_sicherungen_behalten_die_letzten_zehn (test_backup_nachzug.NachzugSicherungTest.test_zwoelf_frische_sicherungen_behalten_die_letzten_zehn) ... ok
test_alte_datenbank_erhaelt_basis_version_und_einmalige_sicherung (test_migrate.MigrationTest.test_alte_datenbank_erhaelt_basis_version_und_einmalige_sicherung) ... ok
test_fehlende_sicherung_ist_bei_wegwerf_datenbank_erlaubt (test_migrate.MigrationTest.test_fehlende_sicherung_ist_bei_wegwerf_datenbank_erlaubt) ... ok
test_fehlerhafte_migration_rollt_zurueck_und_sperrt_version (test_migrate.MigrationTest.test_fehlerhafte_migration_rollt_zurueck_und_sperrt_version) ... ok
test_fehlgeschlagene_pflichtsicherung_stoppt_nachzug (test_migrate.MigrationTest.test_fehlgeschlagene_pflichtsicherung_stoppt_nachzug) ... ok
test_migrationsfehler_startet_app_schreibgeschuetzt (test_migrate.MigrationTest.test_migrationsfehler_startet_app_schreibgeschuetzt) ... ok
test_neue_datenbank_ist_auf_version_9_ohne_anstehende_migrationen (test_migrate.MigrationTest.test_neue_datenbank_ist_auf_version_9_ohne_anstehende_migrationen) ... ok
test_neue_und_alte_datenbank_haben_gleiche_tabellenliste (test_migrate.MigrationTest.test_neue_und_alte_datenbank_haben_gleiche_tabellenliste) ... ok
test_schema_endpoint_liefert_erwartete_felder (test_migrate.MigrationTest.test_schema_endpoint_liefert_erwartete_felder) ... ok
test_schreibschutz_blockiert_auth_login_nicht (test_migrate.MigrationTest.test_schreibschutz_blockiert_auth_login_nicht) ... ok
test_schreibschutz_blockiert_post_aber_nicht_get (test_migrate.MigrationTest.test_schreibschutz_blockiert_post_aber_nicht_get) ... ok

----------------------------------------------------------------------
Ran 34 tests in 12.290s

OK
Angewendet: [1]
```

### Erster Gesamtlauf, für endgültigen Code abgebrochen

```text
test_nachzug_zweimal_und_schema_identisch (test_auslagen.AuslagenMigrationTest.test_nachzug_zweimal_und_schema_identisch) ... ok
test_auslage_teilausgleich_ruecknahme_und_kosten (test_auslagen.AuslagenTest.test_auslage_teilausgleich_ruecknahme_und_kosten) ... ok
test_bereichsgrenzen_und_bankausgleich (test_auslagen.AuslagenTest.test_bereichsgrenzen_und_bankausgleich) ... ok
test_fehlgeschlagener_ausgleich_rollt_kassenanlage_zurueck (test_auslagen.AuslagenTest.test_fehlgeschlagener_ausgleich_rollt_kassenanlage_zurueck) ... ok
test_historie_replay_nach_aenderung_und_aufhebung (test_auslagen.AuslagenTest.test_historie_replay_nach_aenderung_und_aufhebung) ... ok
test_idempotenz_buchung_und_ausgleich (test_auslagen.AuslagenTest.test_idempotenz_buchung_und_ausgleich) ... ok
test_kassawarnung_zehn_euro_und_volle_tilgung (test_auslagen.AuslagenTest.test_kassawarnung_zehn_euro_und_volle_tilgung) ... ok
test_parallele_requests_serialisieren_offen_version_und_request_id (test_auslagen.AuslagenTest.test_parallele_requests_serialisieren_offen_version_und_request_id) ... ok
test_replay_nach_kategoriestilllegung_und_unbenutzter_auslage (test_auslagen.AuslagenTest.test_replay_nach_kategoriestilllegung_und_unbenutzter_auslage) ... ok
test_textkorrektur_bei_zulaessigem_rueckdatiertem_ausgleich (test_auslagen.AuslagenTest.test_textkorrektur_bei_zulaessigem_rueckdatiertem_ausgleich) ... ok
test_validierung_fifo_stichtag_und_warnung (test_auslagen.AuslagenTest.test_validierung_fifo_stichtag_und_warnung) ... ok
test_version_und_zuordnungssperre (test_auslagen.AuslagenTest.test_version_und_zuordnungssperre) ... ok
test_zeilen_ids_bleiben_stabil_und_fremde_werden_abgewiesen (test_auslagen.AuslagenTest.test_zeilen_ids_bleiben_stabil_und_fremde_werden_abgewiesen) ... ok
test_api_ist_ohne_anmeldung_gesperrt (test_auth.AuthIntegrationTest.test_api_ist_ohne_anmeldung_gesperrt) ... ok
test_browser_wird_auf_vorhandene_loginseite_umgeleitet (test_auth.AuthIntegrationTest.test_browser_wird_auf_vorhandene_loginseite_umgeleitet) ... ok
test_falsches_passwort_wird_abgewiesen (test_auth.AuthIntegrationTest.test_falsches_passwort_wird_abgewiesen) ... ok
test_freigegebenes_tailscale_geraet_erreicht_den_login (test_auth.AuthIntegrationTest.test_freigegebenes_tailscale_geraet_erreicht_den_login) ... ok
test_login_setzt_sicheres_cookie_und_oeffnet_api (test_auth.AuthIntegrationTest.test_login_setzt_sicheres_cookie_und_oeffnet_api) ... ok
test_logout_loescht_cookie (test_auth.AuthIntegrationTest.test_logout_loescht_cookie) ... ok
test_manipuliertes_cookie_wird_abgewiesen (test_auth.AuthIntegrationTest.test_manipuliertes_cookie_wird_abgewiesen) ... ok
test_nicht_freigegebenes_tailscale_geraet_wird_abgewiesen (test_auth.AuthIntegrationTest.test_nicht_freigegebenes_tailscale_geraet_wird_abgewiesen) ... ok
test_unbekannter_host_header_wird_abgewiesen (test_auth.AuthIntegrationTest.test_unbekannter_host_header_wird_abgewiesen) ... ok
test_abgelaufene_api_session_fuehrt_zur_loginseite (test_auth_expiry_frontend.AuthExpiryFrontendTest.test_abgelaufene_api_session_fuehrt_zur_loginseite) ... ok
test_studio_bietet_logout_ueber_post_an (test_auth_frontend.AuthFrontendTest.test_studio_bietet_logout_ueber_post_an) ... ok
test_ersteinrichtung_gibt_code_einmal_aus (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_ersteinrichtung_gibt_code_einmal_aus) ... ok
test_ersteinrichtung_kann_nicht_wiederholt_werden (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_ersteinrichtung_kann_nicht_wiederholt_werden) ... ok
test_ersteinrichtung_lehnt_json_array_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_ersteinrichtung_lehnt_json_array_ab) ... ok
test_ersteinrichtung_lehnt_malformedes_json_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_ersteinrichtung_lehnt_malformedes_json_ab) ... ok
test_ersteinrichtung_lehnt_ungueltige_eingaben_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_ersteinrichtung_lehnt_ungueltige_eingaben_ab) ... ok
test_ersteinrichtung_lehnt_ungueltiges_utf8_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_ersteinrichtung_lehnt_ungueltiges_utf8_ab) ... ok
test_login_lehnt_ungueltiges_utf8_neutral_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_login_lehnt_ungueltiges_utf8_neutral_ab) ... ok
test_passwortaenderung_lehnt_fehlerhafte_eingaben_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_passwortaenderung_lehnt_fehlerhafte_eingaben_ab) ... ok
test_passwortaenderung_lehnt_json_array_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_passwortaenderung_lehnt_json_array_ab) ... ok
test_passwortaenderung_lehnt_malformedes_json_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_passwortaenderung_lehnt_malformedes_json_ab) ... ok
test_passwortaenderung_lehnt_ungueltiges_utf8_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_passwortaenderung_lehnt_ungueltiges_utf8_ab) ... ok
test_passwortaenderung_widerruft_alte_sitzung (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_passwortaenderung_widerruft_alte_sitzung) ... ok
test_recovery_lehnt_fehlerhafte_eingaben_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_recovery_lehnt_fehlerhafte_eingaben_ab) ... ok
test_recovery_lehnt_json_array_neutral_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_recovery_lehnt_json_array_neutral_ab) ... ok
test_recovery_lehnt_malformedes_json_neutral_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_recovery_lehnt_malformedes_json_neutral_ab) ... ok
test_recovery_lehnt_ungueltiges_utf8_neutral_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_recovery_lehnt_ungueltiges_utf8_neutral_ab) ...
```

### Gesamtlauf, wegen festem Kredit-Temp-Pfad abgebrochen

```text
test_nachzug_zweimal_und_schema_identisch (test_auslagen.AuslagenMigrationTest.test_nachzug_zweimal_und_schema_identisch) ... ok
test_auslage_teilausgleich_ruecknahme_und_kosten (test_auslagen.AuslagenTest.test_auslage_teilausgleich_ruecknahme_und_kosten) ... ok
test_bereichsgrenzen_und_bankausgleich (test_auslagen.AuslagenTest.test_bereichsgrenzen_und_bankausgleich) ... ok
test_fehlgeschlagener_ausgleich_rollt_kassenanlage_zurueck (test_auslagen.AuslagenTest.test_fehlgeschlagener_ausgleich_rollt_kassenanlage_zurueck) ... ok
test_historie_replay_nach_aenderung_und_aufhebung (test_auslagen.AuslagenTest.test_historie_replay_nach_aenderung_und_aufhebung) ... ok
test_idempotenz_buchung_und_ausgleich (test_auslagen.AuslagenTest.test_idempotenz_buchung_und_ausgleich) ... ok
test_kassawarnung_zehn_euro_und_volle_tilgung (test_auslagen.AuslagenTest.test_kassawarnung_zehn_euro_und_volle_tilgung) ... ok
test_parallele_requests_serialisieren_offen_version_und_request_id (test_auslagen.AuslagenTest.test_parallele_requests_serialisieren_offen_version_und_request_id) ... ok
test_replay_nach_kategoriestilllegung_und_unbenutzter_auslage (test_auslagen.AuslagenTest.test_replay_nach_kategoriestilllegung_und_unbenutzter_auslage) ... ok
test_textkorrektur_bei_zulaessigem_rueckdatiertem_ausgleich (test_auslagen.AuslagenTest.test_textkorrektur_bei_zulaessigem_rueckdatiertem_ausgleich) ... ok
test_validierung_fifo_stichtag_und_warnung (test_auslagen.AuslagenTest.test_validierung_fifo_stichtag_und_warnung) ... ok
test_version_und_zuordnungssperre (test_auslagen.AuslagenTest.test_version_und_zuordnungssperre) ... ok
test_zeilen_ids_bleiben_stabil_und_fremde_werden_abgewiesen (test_auslagen.AuslagenTest.test_zeilen_ids_bleiben_stabil_und_fremde_werden_abgewiesen) ... ok
test_api_ist_ohne_anmeldung_gesperrt (test_auth.AuthIntegrationTest.test_api_ist_ohne_anmeldung_gesperrt) ... ok
test_browser_wird_auf_vorhandene_loginseite_umgeleitet (test_auth.AuthIntegrationTest.test_browser_wird_auf_vorhandene_loginseite_umgeleitet) ... ok
test_falsches_passwort_wird_abgewiesen (test_auth.AuthIntegrationTest.test_falsches_passwort_wird_abgewiesen) ... ok
test_freigegebenes_tailscale_geraet_erreicht_den_login (test_auth.AuthIntegrationTest.test_freigegebenes_tailscale_geraet_erreicht_den_login) ... ok
test_login_setzt_sicheres_cookie_und_oeffnet_api (test_auth.AuthIntegrationTest.test_login_setzt_sicheres_cookie_und_oeffnet_api) ... ok
test_logout_loescht_cookie (test_auth.AuthIntegrationTest.test_logout_loescht_cookie) ... ok
test_manipuliertes_cookie_wird_abgewiesen (test_auth.AuthIntegrationTest.test_manipuliertes_cookie_wird_abgewiesen) ... ok
test_nicht_freigegebenes_tailscale_geraet_wird_abgewiesen (test_auth.AuthIntegrationTest.test_nicht_freigegebenes_tailscale_geraet_wird_abgewiesen) ... ok
test_unbekannter_host_header_wird_abgewiesen (test_auth.AuthIntegrationTest.test_unbekannter_host_header_wird_abgewiesen) ... ok
test_abgelaufene_api_session_fuehrt_zur_loginseite (test_auth_expiry_frontend.AuthExpiryFrontendTest.test_abgelaufene_api_session_fuehrt_zur_loginseite) ... ok
test_studio_bietet_logout_ueber_post_an (test_auth_frontend.AuthFrontendTest.test_studio_bietet_logout_ueber_post_an) ... ok
test_ersteinrichtung_gibt_code_einmal_aus (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_ersteinrichtung_gibt_code_einmal_aus) ... ok
test_ersteinrichtung_kann_nicht_wiederholt_werden (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_ersteinrichtung_kann_nicht_wiederholt_werden) ... ok
test_ersteinrichtung_lehnt_json_array_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_ersteinrichtung_lehnt_json_array_ab) ... ok
test_ersteinrichtung_lehnt_malformedes_json_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_ersteinrichtung_lehnt_malformedes_json_ab) ... ok
test_ersteinrichtung_lehnt_ungueltige_eingaben_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_ersteinrichtung_lehnt_ungueltige_eingaben_ab) ... ok
test_ersteinrichtung_lehnt_ungueltiges_utf8_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_ersteinrichtung_lehnt_ungueltiges_utf8_ab) ... ok
test_login_lehnt_ungueltiges_utf8_neutral_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_login_lehnt_ungueltiges_utf8_neutral_ab) ... ok
test_passwortaenderung_lehnt_fehlerhafte_eingaben_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_passwortaenderung_lehnt_fehlerhafte_eingaben_ab) ... ok
test_passwortaenderung_lehnt_json_array_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_passwortaenderung_lehnt_json_array_ab) ... ok
test_passwortaenderung_lehnt_malformedes_json_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_passwortaenderung_lehnt_malformedes_json_ab) ... ok
test_passwortaenderung_lehnt_ungueltiges_utf8_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_passwortaenderung_lehnt_ungueltiges_utf8_ab) ... ok
test_passwortaenderung_widerruft_alte_sitzung (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_passwortaenderung_widerruft_alte_sitzung) ... ok
test_recovery_lehnt_fehlerhafte_eingaben_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_recovery_lehnt_fehlerhafte_eingaben_ab) ... ok
test_recovery_lehnt_json_array_neutral_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_recovery_lehnt_json_array_neutral_ab) ... ok
test_recovery_lehnt_malformedes_json_neutral_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_recovery_lehnt_malformedes_json_neutral_ab) ... ok
test_recovery_lehnt_ungueltiges_utf8_neutral_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_recovery_lehnt_ungueltiges_utf8_neutral_ab) ... ok
test_recovery_rotiert_code_und_lehnt_wiederverwendung_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_recovery_rotiert_code_und_lehnt_wiederverwendung_ab) ... ok
test_recovery_sperrt_nach_fuenf_ungueltigen_payloads (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_recovery_sperrt_nach_fuenf_ungueltigen_payloads) ... ok
test_setup_assets_sind_waehrend_ersteinrichtung_erreichbar (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_setup_assets_sind_waehrend_ersteinrichtung_erreichbar) ... ok
test_startpasswort_erlaubt_nur_ersteinrichtung (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_startpasswort_erlaubt_nur_ersteinrichtung) ... ok
test_wiederherstellungsseite_und_assets_sind_oeffentlich (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_wiederherstellungsseite_und_assets_sind_oeffentlich) ... ok
test_store_schreibt_atomar_und_laesst_keine_temporaere_datei (test_auth_store.AuthConfigStoreTest.test_store_schreibt_atomar_und_laesst_keine_temporaere_datei) ... ok
test_store_setzt_dateimodus_0600 (test_auth_store.AuthConfigStoreTest.test_store_setzt_dateimodus_0600) ... skipped 'POSIX-Dateirechte'
test_wiederherstellungscode_hat_mindestens_128_bit (test_auth_store.AuthConfigStoreTest.test_wiederherstellungscode_hat_mindestens_128_bit) ... ok
test_genau_sechs_zeichen_und_alle_zeichenarten_sind_erlaubt (test_auth_store.PasswordValidationTest.test_genau_sechs_zeichen_und_alle_zeichenarten_sind_erlaubt) ... ok
test_hashing_verwendet_die_flexible_passwortvalidierung (test_auth_store.PasswordValidationTest.test_hashing_verwendet_die_flexible_passwortvalidierung) ... ok
test_ungueltige_passwoerter_werden_abgewiesen (test_auth_store.PasswordValidationTest.test_ungueltige_passwoerter_werden_abgewiesen) ... ok
test_manipulierte_session_wird_abgewiesen (test_auth_unit.AuthUnitTest.test_manipulierte_session_wird_abgewiesen) ... ok
test_passwort_hash_enthaelt_keinen_klartext (test_auth_unit.AuthUnitTest.test_passwort_hash_enthaelt_keinen_klartext) ... ok
test_rate_limit_sperrt_nach_fuenf_fehlern (test_auth_unit.AuthUnitTest.test_rate_limit_sperrt_nach_fuenf_fehlern) ... ok
test_session_gilt_hoechstens_zwoelf_stunden (test_auth_unit.AuthUnitTest.test_session_gilt_hoechstens_zwoelf_stunden) ... ok
test_buchung_speichern_legt_regel_an (test_auto_kategorien.AutoKategorienTest.test_buchung_speichern_legt_regel_an) ... ok
test_ein_einzelnes_gemeinsames_wort_reicht_nicht_fuer_einen_treffer (test_auto_kategorien.AutoKategorienTest.test_ein_einzelnes_gemeinsames_wort_reicht_nicht_fuer_einen_treffer) ... ok
test_kurze_eingabe_trifft_lange_gelernte_regel_ueber_wort_tokens (test_auto_kategorien.AutoKategorienTest.test_kurze_eingabe_trifft_lange_gelernte_regel_ueber_wort_tokens) ... ok
test_namensabgleich_hat_vorrang_vor_regel (test_auto_kategorien.AutoKategorienTest.test_namensabgleich_hat_vorrang_vor_regel) ... ok
test_parse_ordnet_per_regel_zu_ohne_kategorienamen (test_auto_kategorien.AutoKategorienTest.test_parse_ordnet_per_regel_zu_ohne_kategorienamen) ... ok
test_umbuchung_lernt_nicht (test_auto_kategorien.AutoKategorienTest.test_umbuchung_lernt_nicht) ... ok
test_belege_manifest_und_pruefsummen_werden_gesichert (test_backup.BackupTest.test_belege_manifest_und_pruefsummen_werden_gesichert) ... ok
test_belegsicherung_ohne_db_kopie_schreibt_db_null (test_backup.BackupTest.test_belegsicherung_ohne_db_kopie_schreibt_db_null) ... ok
test_beschaedigte_tagesdatei_wird_durch_gueltige_sicherung_ersetzt (test_backup.BackupTest.test_beschaedigte_tagesdatei_wird_durch_gueltige_sicherung_ersetzt) ... ok
test_betriebsstatus_enthaelt_nur_oeffentliche_sicherungsfelder (test_backup.BackupTest.test_betriebsstatus_enthaelt_nur_oeffentliche_sicherungsfelder) ... ok
test_fehlender_beleg_steht_im_manifest_und_db_sicherung_bleibt_erfolgreich (test_backup.BackupTest.test_fehlender_beleg_steht_im_manifest_und_db_sicherung_bleibt_erfolgreich) ... ok
test_fehlgeschlagene_sicherung_hinterlaesst_keine_tagesdatei (test_backup.BackupTest.test_fehlgeschlagene_sicherung_hinterlaesst_keine_tagesdatei) ... DB-Sicherung fehlgeschlagen (Betrieb laeuft weiter)
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\backup.py", line 346, in sichere_datenbank
    quelle.backup(kopie)
  File "C:\Users\lblet\dev\wt-a1\tests\test_backup.py", line 231, in backup
    raise sqlite3.OperationalError("simulierter Abbruch")
sqlite3.OperationalError: simulierter Abbruch
ok
test_geloeschte_belegkopie_wird_beim_zweiten_lauf_erneuert (test_backup.BackupTest.test_geloeschte_belegkopie_wird_beim_zweiten_lauf_erneuert) ... ok
test_identische_originalnamen_in_verschiedenen_sparten_bleiben_getrennt (test_backup.BackupTest.test_identische_originalnamen_in_verschiedenen_sparten_bleiben_getrennt) ... ok
test_ohne_zweitziel_bleibt_alles_wie_bisher (test_backup.BackupTest.test_ohne_zweitziel_bleibt_alles_wie_bisher) ... ok
test_pruefe_sicherung_erkennt_manipulierte_belegkopie (test_backup.BackupTest.test_pruefe_sicherung_erkennt_manipulierte_belegkopie) ... ok
test_rotation_entfernt_db_belegordner_und_manifest_gemeinsam (test_backup.BackupTest.test_rotation_entfernt_db_belegordner_und_manifest_gemeinsam) ... ok
test_unerreichbares_zweitziel_laesst_erstkopie_gueltig (test_backup.BackupTest.test_unerreichbares_zweitziel_laesst_erstkopie_gueltig) ... DB-Sicherung auf Zweitziel fehlgeschlagen, Erstkopie bleibt gueltig (\\kein-host-xyz-existiert\share\backup)
Traceback (most recent call last):
  File "C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\pathlib.py", line 1311, in mkdir
    os.mkdir(self, mode)
  File "C:\Users\lblet\dev\wt-a1\outputs\a1_testlauf.py", line 19, in _temp_mkdir
    return _mkdir(path, mode, dir_fd=dir_fd)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
PermissionError: [WinError 5] Zugriff verweigert: '\\\\kein-host-xyz-existiert\\share\\backup'

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\backup.py", line 376, in _sichere_auf_zweitziel
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
ok
test_zweiter_lauf_am_selben_tag_ist_idempotent (test_backup.BackupTest.test_zweiter_lauf_am_selben_tag_ist_idempotent) ... ok
test_zweitziel_erhaelt_eine_gueltige_zweitkopie (test_backup.BackupTest.test_zweitziel_erhaelt_eine_gueltige_zweitkopie) ... ok
test_cli_sichert_frisch_und_bricht_bei_sicherungsfehler_ab (test_backup_nachzug.NachzugSicherungTest.test_cli_sichert_frisch_und_bricht_bei_sicherungsfehler_ab) ... ok
test_nachzug_sichert_aktuellen_stand_trotz_tageskopie (test_backup_nachzug.NachzugSicherungTest.test_nachzug_sichert_aktuellen_stand_trotz_tageskopie) ... ok
test_rotation_behaelt_zehn_nachzuege_unabhaengig_von_tageskopien (test_backup_nachzug.NachzugSicherungTest.test_rotation_behaelt_zehn_nachzuege_unabhaengig_von_tageskopien) ... ok
test_rotation_ordnet_gleiche_zeitstempel_nach_laufender_nummer (test_backup_nachzug.NachzugSicherungTest.test_rotation_ordnet_gleiche_zeitstempel_nach_laufender_nummer) ... ok
test_schreibfehler_stoppt_pflichtnachzug (test_backup_nachzug.NachzugSicherungTest.test_schreibfehler_stoppt_pflichtnachzug) ... DB-Sicherung vor Schema-Nachzug fehlgeschlagen
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\backup.py", line 242, in _sichere_vor_nachzug
    ziel_ordner.mkdir(parents=True, exist_ok=True)
  File "C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\pathlib.py", line 1311, in mkdir
    os.mkdir(self, mode)
  File "C:\Users\lblet\dev\wt-a1\outputs\a1_testlauf.py", line 19, in _temp_mkdir
    return _mkdir(path, mode, dir_fd=dir_fd)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
FileExistsError: [WinError 183] Eine Datei kann nicht erstellt werden, wenn sie bereits vorhanden ist: 'C:\\Users\\lblet\\AppData\\Local\\Temp\\finanz-a1-kb6z0crb\\backup'
ok
test_sicherungsfehler_startet_app_schreibgeschuetzt (test_backup_nachzug.NachzugSicherungTest.test_sicherungsfehler_startet_app_schreibgeschuetzt) ... DB-Sicherung vor Schema-Nachzug fehlgeschlagen
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\backup.py", line 242, in _sichere_vor_nachzug
    ziel_ordner.mkdir(parents=True, exist_ok=True)
  File "C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\pathlib.py", line 1311, in mkdir
    os.mkdir(self, mode)
  File "C:\Users\lblet\dev\wt-a1\outputs\a1_testlauf.py", line 19, in _temp_mkdir
    return _mkdir(path, mode, dir_fd=dir_fd)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
FileExistsError: [WinError 183] Eine Datei kann nicht erstellt werden, wenn sie bereits vorhanden ist: 'C:\\Users\\lblet\\AppData\\Local\\Temp\\finanz-a1-eaiuhzph\\backup'
ok
test_ungueltige_kopie_stoppt_nachzug_und_entfernt_tempdateien (test_backup_nachzug.NachzugSicherungTest.test_ungueltige_kopie_stoppt_nachzug_und_entfernt_tempdateien) ... DB-Sicherung vor Schema-Nachzug fehlgeschlagen
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\backup.py", line 273, in _sichere_vor_nachzug
    raise sqlite3.DatabaseError("Sicherung vor Nachzug ist nicht intakt")
sqlite3.DatabaseError: Sicherung vor Nachzug ist nicht intakt
ok
test_wegwerf_datenbank_ueberspringt_sicherung (test_backup_nachzug.NachzugSicherungTest.test_wegwerf_datenbank_ueberspringt_sicherung) ... ok
test_zwei_nachzuege_in_derselben_minute_ueberschreiben_nichts (test_backup_nachzug.NachzugSicherungTest.test_zwei_nachzuege_in_derselben_minute_ueberschreiben_nichts) ... ok
test_zwoelf_frische_sicherungen_behalten_die_letzten_zehn (test_backup_nachzug.NachzugSicherungTest.test_zwoelf_frische_sicherungen_behalten_die_letzten_zehn) ... ok
test_absurde_abweichung_nur_pruefhinweis (test_beleg_auswertung.BelegAuswertungTest.test_absurde_abweichung_nur_pruefhinweis) ... Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\auswertung.py", line 108, in _lade_bild_base64
    bild = Image.open(io.BytesIO(roh))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Lib\site-packages\PIL\Image.py", line 3532, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x00000252984FCCC0>
ok
test_auftrag_anlegen_und_dedupe (test_beleg_auswertung.BelegAuswertungTest.test_auftrag_anlegen_und_dedupe) ... ok
test_brutto_mit_mwst_je_position (test_beleg_auswertung.BelegAuswertungTest.test_brutto_mit_mwst_je_position) ... Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\auswertung.py", line 108, in _lade_bild_base64
    bild = Image.open(io.BytesIO(roh))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Lib\site-packages\PIL\Image.py", line 3532, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x00000252989CD8A0>
ok
test_brutto_proportional_ohne_mwst (test_beleg_auswertung.BelegAuswertungTest.test_brutto_proportional_ohne_mwst) ... Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\auswertung.py", line 108, in _lade_bild_base64
    bild = Image.open(io.BytesIO(roh))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Lib\site-packages\PIL\Image.py", line 3532, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x00000252989CDAD0>
ok
test_ollama_nicht_erreichbar_bleibt_offen (test_beleg_auswertung.BelegAuswertungTest.test_ollama_nicht_erreichbar_bleibt_offen) ... Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\auswertung.py", line 108, in _lade_bild_base64
    bild = Image.open(io.BytesIO(roh))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Lib\site-packages\PIL\Image.py", line 3532, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x0000025298965D00>
ok
test_rabatt_wird_mitskaliert (test_beleg_auswertung.BelegAuswertungTest.test_rabatt_wird_mitskaliert) ... Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\auswertung.py", line 108, in _lade_bild_base64
    bild = Image.open(io.BytesIO(roh))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Lib\site-packages\PIL\Image.py", line 3532, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x00000252989CDF30>
ok
test_status_endpoint_erlaubt_nur_verworfen_oder_verbucht (test_beleg_auswertung.BelegAuswertungTest.test_status_endpoint_erlaubt_nur_verworfen_oder_verbucht) ... ok
test_stimmige_bruttosumme_unveraendert (test_beleg_auswertung.BelegAuswertungTest.test_stimmige_bruttosumme_unveraendert) ... Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\auswertung.py", line 108, in _lade_bild_base64
    bild = Image.open(io.BytesIO(roh))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Lib\site-packages\PIL\Image.py", line 3532, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x00000252989CE160>
ok
test_verarbeitung_gemockt_setzt_fertig_und_mapped_kategorie (test_beleg_auswertung.BelegAuswertungTest.test_verarbeitung_gemockt_setzt_fertig_und_mapped_kategorie) ... Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\auswertung.py", line 108, in _lade_bild_base64
    bild = Image.open(io.BytesIO(roh))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Lib\site-packages\PIL\Image.py", line 3532, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x00000252989CE340>
ok
test_belege_und_verknuepfungen (test_bereiche.BereicheTest.test_belege_und_verknuepfungen) ... ok
test_buchungen_suche_und_schreiben (test_bereiche.BereicheTest.test_buchungen_suche_und_schreiben) ... ok
test_dashboard_jahre_und_verlauf (test_bereiche.BereicheTest.test_dashboard_jahre_und_verlauf) ... ok
test_export_xlsx_und_bericht (test_bereiche.BereicheTest.test_export_xlsx_und_bericht) ... ok
test_fachliche_endpoints_haben_zentrale_dependency (test_bereiche.BereicheTest.test_fachliche_endpoints_haben_zentrale_dependency) ... ok
test_fehlendes_bereichsschema_bleibt_kontrolliert_gesperrt (test_bereiche.BereicheTest.test_fehlendes_bereichsschema_bleibt_kontrolliert_gesperrt) ... ok
test_fotoauftraege_grenzen (test_bereiche.BereicheTest.test_fotoauftraege_grenzen) ... ok
test_fotoverarbeitung_uebergibt_belegbereich (test_bereiche.BereicheTest.test_fotoverarbeitung_uebergibt_belegbereich) ... ok
test_gruppen_sind_bereichsgebunden (test_bereiche.BereicheTest.test_gruppen_sind_bereichsgebunden) ... ok
test_kategorien_grenzen (test_bereiche.BereicheTest.test_kategorien_grenzen) ... ok
test_login_ignoriert_unbekannten_bereich_fachlicher_endpoint_nicht (test_bereiche.BereicheTest.test_login_ignoriert_unbekannten_bereich_fachlicher_endpoint_nicht) ... ok
test_regeln_und_namensabgleich_der_schnellerfassung (test_bereiche.BereicheTest.test_regeln_und_namensabgleich_der_schnellerfassung) ... ok
test_stammdaten_und_bereichsaufloesung (test_bereiche.BereicheTest.test_stammdaten_und_bereichsaufloesung) ... ok
test_upload_dubletten_nur_im_bereich (test_bereiche.BereicheTest.test_upload_dubletten_nur_im_bereich) ... ok
test_account_creation_and_import_reject_foreign_references (test_bereiche_import.BereicheImportTest.test_account_creation_and_import_reject_foreign_references) ... ok
test_batch_checks_all_ids_before_first_commit (test_bereiche_import.BereicheImportTest.test_batch_checks_all_ids_before_first_commit) ... ok
test_domain_two_rule_and_batch_mutations (test_bereiche_import.BereicheImportTest.test_domain_two_rule_and_batch_mutations) ... ok
test_foreign_and_inconsistent_rules_are_not_proposed (test_bereiche_import.BereicheImportTest.test_foreign_and_inconsistent_rules_are_not_proposed) ... ok
test_foreign_mutations_are_404_and_do_not_write (test_bereiche_import.BereicheImportTest.test_foreign_mutations_are_404_and_do_not_write) ... ok
test_lists_and_foreign_filters (test_bereiche_import.BereicheImportTest.test_lists_and_foreign_filters) ... ok
test_rule_learning_stays_in_domain (test_bereiche_import.BereicheImportTest.test_rule_learning_stays_in_domain) ... ok
test_current_schema_accepts_migration_and_seed_has_separate_domains (test_bereiche_migration.BereicheMigrationTest.test_current_schema_accepts_migration_and_seed_has_separate_domains) ... ok
test_migration_assigns_domains_and_removes_only_foreign_memberships (test_bereiche_migration.BereicheMigrationTest.test_migration_assigns_domains_and_removes_only_foreign_memberships) ... ok
test_schema_and_migration_have_identical_structure (test_bereiche_migration.BereicheMigrationTest.test_schema_and_migration_have_identical_structure) ... ok
test_sql_runner_logs_skipped_existing_column (test_bereiche_migration.BereicheMigrationTest.test_sql_runner_logs_skipped_existing_column) ... ok
test_sql_runner_preserves_trigger_and_string_semicolons (test_bereiche_migration.BereicheMigrationTest.test_sql_runner_preserves_trigger_and_string_semicolons) ... ok
test_sql_runner_rolls_back_fk_failure_and_restores_enforcement (test_bereiche_migration.BereicheMigrationTest.test_sql_runner_rolls_back_fk_failure_and_restores_enforcement) ... ok
test_liefert_hoechstens_200_neueste_buchungen (test_buchungen_suche.BuchungenSucheApiTest.test_liefert_hoechstens_200_neueste_buchungen) ... ok
test_sucht_case_insensitiv_in_text_notiz_und_kontakt (test_buchungen_suche.BuchungenSucheApiTest.test_sucht_case_insensitiv_in_text_notiz_und_kontakt) ... ok
test_alte_revision_wird_abgewiesen (test_export_profil.ExportProfilTests.test_alte_revision_wird_abgewiesen) ... ok
test_paket_enthaelt_excel_und_inhalt (test_export_profil.ExportProfilTests.test_paket_enthaelt_excel_und_inhalt) ... ok
test_vorschau_respektiert_kategorie_und_buchungsausschluss (test_export_profil.ExportProfilTests.test_vorschau_respektiert_kategorie_und_buchungsausschluss) ... ok
test_alter_fingerabdruck_verhindert_neuen_umsatz (test_import_bank.ImportBankApiTest.test_alter_fingerabdruck_verhindert_neuen_umsatz) ... ok
test_dublettenschutz_bei_wiederholtem_import (test_import_bank.ImportBankApiTest.test_dublettenschutz_bei_wiederholtem_import) ... ok
test_erfolgreicher_import_mehrerer_umsaetze (test_import_bank.ImportBankApiTest.test_erfolgreicher_import_mehrerer_umsaetze) ... ok
test_george_fixture_importiert_alle_zeilen_und_erkennt_spalten (test_import_bank.ImportBankApiTest.test_george_fixture_importiert_alle_zeilen_und_erkennt_spalten) ... ok
test_george_identische_zeilen_bleiben_zwei_und_reimport_ist_dubletten (test_import_bank.ImportBankApiTest.test_george_identische_zeilen_bleiben_zwei_und_reimport_ist_dubletten) ... ok
test_kaputte_csv_liefert_4xx_statt_500 (test_import_bank.ImportBankApiTest.test_kaputte_csv_liefert_4xx_statt_500) ... ok
test_semikolon_beispiel_prueft_und_speichert_saldo (test_import_bank.ImportBankApiTest.test_semikolon_beispiel_prueft_und_speichert_saldo) ... ok
test_verbuchen_erzeugt_buchung_und_lernt_regel (test_import_bank.ImportBankApiTest.test_verbuchen_erzeugt_buchung_und_lernt_regel) ... ok
test_erkennung_und_utf16 (test_import_bank.ParserTest.test_erkennung_und_utf16) ... ok
test_parse_betrag_cent (test_import_bank.ParserTest.test_parse_betrag_cent) ... ok
test_parse_datum (test_import_bank.ParserTest.test_parse_datum) ... ok
test_datei_ohne_kassabuch_layout_erzeugt_andere_warnung (test_import_excel.ImportExcelApiTest.test_datei_ohne_kassabuch_layout_erzeugt_andere_warnung)
Kein Blatt hat eine erkennbare Kopfzeile -> eigener Hinweistext. ... ok
test_dubletten_bei_wiederholtem_einspielen (test_import_excel.ImportExcelApiTest.test_dubletten_bei_wiederholtem_einspielen) ... ok
test_einspielen_legt_buchungen_an (test_import_excel.ImportExcelApiTest.test_einspielen_legt_buchungen_an) ... ok
test_leere_vorlage_erzeugt_warnung (test_import_excel.ImportExcelApiTest.test_leere_vorlage_erzeugt_warnung)
Aufgabe 1: eine Datei ohne jede Betragszeile darf nicht stillschweigend ... ok
test_pruefen_aendert_datenbank_nicht (test_import_excel.ImportExcelApiTest.test_pruefen_aendert_datenbank_nicht) ... ok
test_unbekannte_kategorien_werden_gemeldet (test_import_excel.ImportExcelApiTest.test_unbekannte_kategorien_werden_gemeldet) ... ok
test_bankomat_storno_und_cursor (test_konten_bewegungen.KontenApiTest.test_bankomat_storno_und_cursor) ... ok
test_bar_anlegen_aendern_loeschen (test_konten_bewegungen.KontenApiTest.test_bar_anlegen_aendern_loeschen) ... ok
test_csv_und_kassa_importverbot (test_konten_bewegungen.KontenApiTest.test_csv_und_kassa_importverbot) ... ok
test_geteilten_import_loeschen_und_transferimport_erhalten (test_konten_bewegungen.KontenApiTest.test_geteilten_import_loeschen_und_transferimport_erhalten) ... ok
test_import_verknuepfung_und_vorlaeufige_bewegung (test_konten_bewegungen.KontenApiTest.test_import_verknuepfung_und_vorlaeufige_bewegung) ... ok
test_kompatible_barumbuchung_und_storno (test_konten_bewegungen.KontenApiTest.test_kompatible_barumbuchung_und_storno) ... ok
test_konten_alias_validierung_und_bereich (test_konten_bewegungen.KontenApiTest.test_konten_alias_validierung_und_bereich) ... ok
test_notiz_kann_keinen_fremden_transfer_stornieren (test_konten_bewegungen.KontenApiTest.test_notiz_kann_keinen_fremden_transfer_stornieren) ... ok
test_put_prueft_erhaltenen_umsatz_und_oeffnet_abgeloesten (test_konten_bewegungen.KontenApiTest.test_put_prueft_erhaltenen_umsatz_und_oeffnet_abgeloesten) ... ok
test_unbekannte_zahlung_und_fremdes_konto (test_konten_bewegungen.KontenApiTest.test_unbekannte_zahlung_und_fremdes_konto) ... ok
test_bestandskopie_nachzug_und_schema_identisch (test_konten_bewegungen.KontenMigrationTest.test_bestandskopie_nachzug_und_schema_identisch) ... ok
test_bereich_und_referenzen_werden_geprueft (test_kredit.KreditApiTest.test_bereich_und_referenzen_werden_geprueft) ...
```

### Kredit-Tests mit passendem temporärem Basispfad

```text
test_bereich_und_referenzen_werden_geprueft (test_kredit.KreditApiTest.test_bereich_und_referenzen_werden_geprueft) ... ok
test_elf_raten_melden_abweichung_und_vorjahreszins_schaetzt (test_kredit.KreditApiTest.test_elf_raten_melden_abweichung_und_vorjahreszins_schaetzt) ... ok
test_jahreszins_wird_auf_raten_und_auswertung_verteilt (test_kredit.KreditApiTest.test_jahreszins_wird_auf_raten_und_auswertung_verteilt) ... ok
test_verteile_zins_erhaelt_jeden_cent (test_kredit.KreditLogikTest.test_verteile_zins_erhaelt_jeden_cent) ... ok
test_migration_007_zweimal_und_view (test_kredit.KreditMigrationTest.test_migration_007_zweimal_und_view) ... ok

----------------------------------------------------------------------
Ran 5 tests in 1.559s

OK
```

### Abschließender vollständiger Gesamtlauf – Exitcode 0

```text
test_nachzug_zweimal_und_schema_identisch (test_auslagen.AuslagenMigrationTest.test_nachzug_zweimal_und_schema_identisch) ... ok
test_auslage_teilausgleich_ruecknahme_und_kosten (test_auslagen.AuslagenTest.test_auslage_teilausgleich_ruecknahme_und_kosten) ... ok
test_bereichsgrenzen_und_bankausgleich (test_auslagen.AuslagenTest.test_bereichsgrenzen_und_bankausgleich) ... ok
test_fehlgeschlagener_ausgleich_rollt_kassenanlage_zurueck (test_auslagen.AuslagenTest.test_fehlgeschlagener_ausgleich_rollt_kassenanlage_zurueck) ... ok
test_historie_replay_nach_aenderung_und_aufhebung (test_auslagen.AuslagenTest.test_historie_replay_nach_aenderung_und_aufhebung) ... ok
test_idempotenz_buchung_und_ausgleich (test_auslagen.AuslagenTest.test_idempotenz_buchung_und_ausgleich) ... ok
test_kassawarnung_zehn_euro_und_volle_tilgung (test_auslagen.AuslagenTest.test_kassawarnung_zehn_euro_und_volle_tilgung) ... ok
test_parallele_requests_serialisieren_offen_version_und_request_id (test_auslagen.AuslagenTest.test_parallele_requests_serialisieren_offen_version_und_request_id) ... ok
test_replay_nach_kategoriestilllegung_und_unbenutzter_auslage (test_auslagen.AuslagenTest.test_replay_nach_kategoriestilllegung_und_unbenutzter_auslage) ... ok
test_textkorrektur_bei_zulaessigem_rueckdatiertem_ausgleich (test_auslagen.AuslagenTest.test_textkorrektur_bei_zulaessigem_rueckdatiertem_ausgleich) ... ok
test_validierung_fifo_stichtag_und_warnung (test_auslagen.AuslagenTest.test_validierung_fifo_stichtag_und_warnung) ... ok
test_version_und_zuordnungssperre (test_auslagen.AuslagenTest.test_version_und_zuordnungssperre) ... ok
test_zeilen_ids_bleiben_stabil_und_fremde_werden_abgewiesen (test_auslagen.AuslagenTest.test_zeilen_ids_bleiben_stabil_und_fremde_werden_abgewiesen) ... ok
test_api_ist_ohne_anmeldung_gesperrt (test_auth.AuthIntegrationTest.test_api_ist_ohne_anmeldung_gesperrt) ... ok
test_browser_wird_auf_vorhandene_loginseite_umgeleitet (test_auth.AuthIntegrationTest.test_browser_wird_auf_vorhandene_loginseite_umgeleitet) ... ok
test_falsches_passwort_wird_abgewiesen (test_auth.AuthIntegrationTest.test_falsches_passwort_wird_abgewiesen) ... ok
test_freigegebenes_tailscale_geraet_erreicht_den_login (test_auth.AuthIntegrationTest.test_freigegebenes_tailscale_geraet_erreicht_den_login) ... ok
test_login_setzt_sicheres_cookie_und_oeffnet_api (test_auth.AuthIntegrationTest.test_login_setzt_sicheres_cookie_und_oeffnet_api) ... ok
test_logout_loescht_cookie (test_auth.AuthIntegrationTest.test_logout_loescht_cookie) ... ok
test_manipuliertes_cookie_wird_abgewiesen (test_auth.AuthIntegrationTest.test_manipuliertes_cookie_wird_abgewiesen) ... ok
test_nicht_freigegebenes_tailscale_geraet_wird_abgewiesen (test_auth.AuthIntegrationTest.test_nicht_freigegebenes_tailscale_geraet_wird_abgewiesen) ... ok
test_unbekannter_host_header_wird_abgewiesen (test_auth.AuthIntegrationTest.test_unbekannter_host_header_wird_abgewiesen) ... ok
test_abgelaufene_api_session_fuehrt_zur_loginseite (test_auth_expiry_frontend.AuthExpiryFrontendTest.test_abgelaufene_api_session_fuehrt_zur_loginseite) ... ok
test_studio_bietet_logout_ueber_post_an (test_auth_frontend.AuthFrontendTest.test_studio_bietet_logout_ueber_post_an) ... ok
test_ersteinrichtung_gibt_code_einmal_aus (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_ersteinrichtung_gibt_code_einmal_aus) ... ok
test_ersteinrichtung_kann_nicht_wiederholt_werden (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_ersteinrichtung_kann_nicht_wiederholt_werden) ... ok
test_ersteinrichtung_lehnt_json_array_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_ersteinrichtung_lehnt_json_array_ab) ... ok
test_ersteinrichtung_lehnt_malformedes_json_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_ersteinrichtung_lehnt_malformedes_json_ab) ... ok
test_ersteinrichtung_lehnt_ungueltige_eingaben_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_ersteinrichtung_lehnt_ungueltige_eingaben_ab) ... ok
test_ersteinrichtung_lehnt_ungueltiges_utf8_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_ersteinrichtung_lehnt_ungueltiges_utf8_ab) ... ok
test_login_lehnt_ungueltiges_utf8_neutral_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_login_lehnt_ungueltiges_utf8_neutral_ab) ... ok
test_passwortaenderung_lehnt_fehlerhafte_eingaben_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_passwortaenderung_lehnt_fehlerhafte_eingaben_ab) ... ok
test_passwortaenderung_lehnt_json_array_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_passwortaenderung_lehnt_json_array_ab) ... ok
test_passwortaenderung_lehnt_malformedes_json_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_passwortaenderung_lehnt_malformedes_json_ab) ... ok
test_passwortaenderung_lehnt_ungueltiges_utf8_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_passwortaenderung_lehnt_ungueltiges_utf8_ab) ... ok
test_passwortaenderung_widerruft_alte_sitzung (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_passwortaenderung_widerruft_alte_sitzung) ... ok
test_recovery_lehnt_fehlerhafte_eingaben_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_recovery_lehnt_fehlerhafte_eingaben_ab) ... ok
test_recovery_lehnt_json_array_neutral_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_recovery_lehnt_json_array_neutral_ab) ... ok
test_recovery_lehnt_malformedes_json_neutral_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_recovery_lehnt_malformedes_json_neutral_ab) ... ok
test_recovery_lehnt_ungueltiges_utf8_neutral_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_recovery_lehnt_ungueltiges_utf8_neutral_ab) ... ok
test_recovery_rotiert_code_und_lehnt_wiederverwendung_ab (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_recovery_rotiert_code_und_lehnt_wiederverwendung_ab) ... ok
test_recovery_sperrt_nach_fuenf_ungueltigen_payloads (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_recovery_sperrt_nach_fuenf_ungueltigen_payloads) ... ok
test_setup_assets_sind_waehrend_ersteinrichtung_erreichbar (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_setup_assets_sind_waehrend_ersteinrichtung_erreichbar) ... ok
test_startpasswort_erlaubt_nur_ersteinrichtung (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_startpasswort_erlaubt_nur_ersteinrichtung) ... ok
test_wiederherstellungsseite_und_assets_sind_oeffentlich (test_auth_lifecycle.AuthLifecycleIntegrationTest.test_wiederherstellungsseite_und_assets_sind_oeffentlich) ... ok
test_store_schreibt_atomar_und_laesst_keine_temporaere_datei (test_auth_store.AuthConfigStoreTest.test_store_schreibt_atomar_und_laesst_keine_temporaere_datei) ... ok
test_store_setzt_dateimodus_0600 (test_auth_store.AuthConfigStoreTest.test_store_setzt_dateimodus_0600) ... skipped 'POSIX-Dateirechte'
test_wiederherstellungscode_hat_mindestens_128_bit (test_auth_store.AuthConfigStoreTest.test_wiederherstellungscode_hat_mindestens_128_bit) ... ok
test_genau_sechs_zeichen_und_alle_zeichenarten_sind_erlaubt (test_auth_store.PasswordValidationTest.test_genau_sechs_zeichen_und_alle_zeichenarten_sind_erlaubt) ... ok
test_hashing_verwendet_die_flexible_passwortvalidierung (test_auth_store.PasswordValidationTest.test_hashing_verwendet_die_flexible_passwortvalidierung) ... ok
test_ungueltige_passwoerter_werden_abgewiesen (test_auth_store.PasswordValidationTest.test_ungueltige_passwoerter_werden_abgewiesen) ... ok
test_manipulierte_session_wird_abgewiesen (test_auth_unit.AuthUnitTest.test_manipulierte_session_wird_abgewiesen) ... ok
test_passwort_hash_enthaelt_keinen_klartext (test_auth_unit.AuthUnitTest.test_passwort_hash_enthaelt_keinen_klartext) ... ok
test_rate_limit_sperrt_nach_fuenf_fehlern (test_auth_unit.AuthUnitTest.test_rate_limit_sperrt_nach_fuenf_fehlern) ... ok
test_session_gilt_hoechstens_zwoelf_stunden (test_auth_unit.AuthUnitTest.test_session_gilt_hoechstens_zwoelf_stunden) ... ok
test_buchung_speichern_legt_regel_an (test_auto_kategorien.AutoKategorienTest.test_buchung_speichern_legt_regel_an) ... ok
test_ein_einzelnes_gemeinsames_wort_reicht_nicht_fuer_einen_treffer (test_auto_kategorien.AutoKategorienTest.test_ein_einzelnes_gemeinsames_wort_reicht_nicht_fuer_einen_treffer) ... ok
test_kurze_eingabe_trifft_lange_gelernte_regel_ueber_wort_tokens (test_auto_kategorien.AutoKategorienTest.test_kurze_eingabe_trifft_lange_gelernte_regel_ueber_wort_tokens) ... ok
test_namensabgleich_hat_vorrang_vor_regel (test_auto_kategorien.AutoKategorienTest.test_namensabgleich_hat_vorrang_vor_regel) ... ok
test_parse_ordnet_per_regel_zu_ohne_kategorienamen (test_auto_kategorien.AutoKategorienTest.test_parse_ordnet_per_regel_zu_ohne_kategorienamen) ... ok
test_umbuchung_lernt_nicht (test_auto_kategorien.AutoKategorienTest.test_umbuchung_lernt_nicht) ... ok
test_belege_manifest_und_pruefsummen_werden_gesichert (test_backup.BackupTest.test_belege_manifest_und_pruefsummen_werden_gesichert) ... ok
test_belegsicherung_ohne_db_kopie_schreibt_db_null (test_backup.BackupTest.test_belegsicherung_ohne_db_kopie_schreibt_db_null) ... ok
test_beschaedigte_tagesdatei_wird_durch_gueltige_sicherung_ersetzt (test_backup.BackupTest.test_beschaedigte_tagesdatei_wird_durch_gueltige_sicherung_ersetzt) ... ok
test_betriebsstatus_enthaelt_nur_oeffentliche_sicherungsfelder (test_backup.BackupTest.test_betriebsstatus_enthaelt_nur_oeffentliche_sicherungsfelder) ... ok
test_fehlender_beleg_steht_im_manifest_und_db_sicherung_bleibt_erfolgreich (test_backup.BackupTest.test_fehlender_beleg_steht_im_manifest_und_db_sicherung_bleibt_erfolgreich) ... ok
test_fehlgeschlagene_sicherung_hinterlaesst_keine_tagesdatei (test_backup.BackupTest.test_fehlgeschlagene_sicherung_hinterlaesst_keine_tagesdatei) ... DB-Sicherung fehlgeschlagen (Betrieb laeuft weiter)
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\backup.py", line 346, in sichere_datenbank
    quelle.backup(kopie)
  File "C:\Users\lblet\dev\wt-a1\tests\test_backup.py", line 231, in backup
    raise sqlite3.OperationalError("simulierter Abbruch")
sqlite3.OperationalError: simulierter Abbruch
ok
test_geloeschte_belegkopie_wird_beim_zweiten_lauf_erneuert (test_backup.BackupTest.test_geloeschte_belegkopie_wird_beim_zweiten_lauf_erneuert) ... ok
test_identische_originalnamen_in_verschiedenen_sparten_bleiben_getrennt (test_backup.BackupTest.test_identische_originalnamen_in_verschiedenen_sparten_bleiben_getrennt) ... ok
test_ohne_zweitziel_bleibt_alles_wie_bisher (test_backup.BackupTest.test_ohne_zweitziel_bleibt_alles_wie_bisher) ... ok
test_pruefe_sicherung_erkennt_manipulierte_belegkopie (test_backup.BackupTest.test_pruefe_sicherung_erkennt_manipulierte_belegkopie) ... ok
test_rotation_entfernt_db_belegordner_und_manifest_gemeinsam (test_backup.BackupTest.test_rotation_entfernt_db_belegordner_und_manifest_gemeinsam) ... ok
test_unerreichbares_zweitziel_laesst_erstkopie_gueltig (test_backup.BackupTest.test_unerreichbares_zweitziel_laesst_erstkopie_gueltig) ... DB-Sicherung auf Zweitziel fehlgeschlagen, Erstkopie bleibt gueltig (\\kein-host-xyz-existiert\share\backup)
Traceback (most recent call last):
  File "C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\pathlib.py", line 1311, in mkdir
    os.mkdir(self, mode)
  File "C:\Users\lblet\dev\wt-a1\outputs\a1_testlauf.py", line 19, in _temp_mkdir
    return _mkdir(path, mode, dir_fd=dir_fd)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
PermissionError: [WinError 5] Zugriff verweigert: '\\\\kein-host-xyz-existiert\\share\\backup'

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\backup.py", line 376, in _sichere_auf_zweitziel
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
ok
test_zweiter_lauf_am_selben_tag_ist_idempotent (test_backup.BackupTest.test_zweiter_lauf_am_selben_tag_ist_idempotent) ... ok
test_zweitziel_erhaelt_eine_gueltige_zweitkopie (test_backup.BackupTest.test_zweitziel_erhaelt_eine_gueltige_zweitkopie) ... ok
test_cli_sichert_frisch_und_bricht_bei_sicherungsfehler_ab (test_backup_nachzug.NachzugSicherungTest.test_cli_sichert_frisch_und_bricht_bei_sicherungsfehler_ab) ... ok
test_nachzug_sichert_aktuellen_stand_trotz_tageskopie (test_backup_nachzug.NachzugSicherungTest.test_nachzug_sichert_aktuellen_stand_trotz_tageskopie) ... ok
test_rotation_behaelt_zehn_nachzuege_unabhaengig_von_tageskopien (test_backup_nachzug.NachzugSicherungTest.test_rotation_behaelt_zehn_nachzuege_unabhaengig_von_tageskopien) ... ok
test_rotation_ordnet_gleiche_zeitstempel_nach_laufender_nummer (test_backup_nachzug.NachzugSicherungTest.test_rotation_ordnet_gleiche_zeitstempel_nach_laufender_nummer) ... ok
test_schreibfehler_stoppt_pflichtnachzug (test_backup_nachzug.NachzugSicherungTest.test_schreibfehler_stoppt_pflichtnachzug) ... DB-Sicherung vor Schema-Nachzug fehlgeschlagen
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\backup.py", line 242, in _sichere_vor_nachzug
    ziel_ordner.mkdir(parents=True, exist_ok=True)
  File "C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\pathlib.py", line 1311, in mkdir
    os.mkdir(self, mode)
  File "C:\Users\lblet\dev\wt-a1\outputs\a1_testlauf.py", line 19, in _temp_mkdir
    return _mkdir(path, mode, dir_fd=dir_fd)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
FileExistsError: [WinError 183] Eine Datei kann nicht erstellt werden, wenn sie bereits vorhanden ist: 'C:\\Users\\lblet\\AppData\\Local\\Temp\\finanz-a1-fy4_g1dm\\backup'
ok
test_sicherungsfehler_startet_app_schreibgeschuetzt (test_backup_nachzug.NachzugSicherungTest.test_sicherungsfehler_startet_app_schreibgeschuetzt) ... DB-Sicherung vor Schema-Nachzug fehlgeschlagen
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\backup.py", line 242, in _sichere_vor_nachzug
    ziel_ordner.mkdir(parents=True, exist_ok=True)
  File "C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\pathlib.py", line 1311, in mkdir
    os.mkdir(self, mode)
  File "C:\Users\lblet\dev\wt-a1\outputs\a1_testlauf.py", line 19, in _temp_mkdir
    return _mkdir(path, mode, dir_fd=dir_fd)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
FileExistsError: [WinError 183] Eine Datei kann nicht erstellt werden, wenn sie bereits vorhanden ist: 'C:\\Users\\lblet\\AppData\\Local\\Temp\\finanz-a1-z2tug7d4\\backup'
ok
test_ungueltige_kopie_stoppt_nachzug_und_entfernt_tempdateien (test_backup_nachzug.NachzugSicherungTest.test_ungueltige_kopie_stoppt_nachzug_und_entfernt_tempdateien) ... DB-Sicherung vor Schema-Nachzug fehlgeschlagen
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\backup.py", line 273, in _sichere_vor_nachzug
    raise sqlite3.DatabaseError("Sicherung vor Nachzug ist nicht intakt")
sqlite3.DatabaseError: Sicherung vor Nachzug ist nicht intakt
ok
test_wegwerf_datenbank_ueberspringt_sicherung (test_backup_nachzug.NachzugSicherungTest.test_wegwerf_datenbank_ueberspringt_sicherung) ... ok
test_zwei_nachzuege_in_derselben_minute_ueberschreiben_nichts (test_backup_nachzug.NachzugSicherungTest.test_zwei_nachzuege_in_derselben_minute_ueberschreiben_nichts) ... ok
test_zwoelf_frische_sicherungen_behalten_die_letzten_zehn (test_backup_nachzug.NachzugSicherungTest.test_zwoelf_frische_sicherungen_behalten_die_letzten_zehn) ... ok
test_absurde_abweichung_nur_pruefhinweis (test_beleg_auswertung.BelegAuswertungTest.test_absurde_abweichung_nur_pruefhinweis) ... Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\auswertung.py", line 108, in _lade_bild_base64
    bild = Image.open(io.BytesIO(roh))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Lib\site-packages\PIL\Image.py", line 3532, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x000002A71A40CE00>
ok
test_auftrag_anlegen_und_dedupe (test_beleg_auswertung.BelegAuswertungTest.test_auftrag_anlegen_und_dedupe) ... ok
test_brutto_mit_mwst_je_position (test_beleg_auswertung.BelegAuswertungTest.test_brutto_mit_mwst_je_position) ... Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\auswertung.py", line 108, in _lade_bild_base64
    bild = Image.open(io.BytesIO(roh))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Lib\site-packages\PIL\Image.py", line 3532, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x000002A71A8E19E0>
ok
test_brutto_proportional_ohne_mwst (test_beleg_auswertung.BelegAuswertungTest.test_brutto_proportional_ohne_mwst) ... Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\auswertung.py", line 108, in _lade_bild_base64
    bild = Image.open(io.BytesIO(roh))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Lib\site-packages\PIL\Image.py", line 3532, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x000002A71A8E1C10>
ok
test_ollama_nicht_erreichbar_bleibt_offen (test_beleg_auswertung.BelegAuswertungTest.test_ollama_nicht_erreichbar_bleibt_offen) ... Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\auswertung.py", line 108, in _lade_bild_base64
    bild = Image.open(io.BytesIO(roh))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Lib\site-packages\PIL\Image.py", line 3532, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x000002A71A875E40>
ok
test_rabatt_wird_mitskaliert (test_beleg_auswertung.BelegAuswertungTest.test_rabatt_wird_mitskaliert) ... Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\auswertung.py", line 108, in _lade_bild_base64
    bild = Image.open(io.BytesIO(roh))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Lib\site-packages\PIL\Image.py", line 3532, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x000002A71A8E2070>
ok
test_status_endpoint_erlaubt_nur_verworfen_oder_verbucht (test_beleg_auswertung.BelegAuswertungTest.test_status_endpoint_erlaubt_nur_verworfen_oder_verbucht) ... ok
test_stimmige_bruttosumme_unveraendert (test_beleg_auswertung.BelegAuswertungTest.test_stimmige_bruttosumme_unveraendert) ... Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\auswertung.py", line 108, in _lade_bild_base64
    bild = Image.open(io.BytesIO(roh))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Lib\site-packages\PIL\Image.py", line 3532, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x000002A71A8E22A0>
ok
test_verarbeitung_gemockt_setzt_fertig_und_mapped_kategorie (test_beleg_auswertung.BelegAuswertungTest.test_verarbeitung_gemockt_setzt_fertig_und_mapped_kategorie) ... Bild-Verkleinerung fehlgeschlagen - sende Original
Traceback (most recent call last):
  File "C:\Users\lblet\dev\wt-a1\app\auswertung.py", line 108, in _lade_bild_base64
    bild = Image.open(io.BytesIO(roh))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Lib\site-packages\PIL\Image.py", line 3532, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x000002A71A8E2480>
ok
test_belege_und_verknuepfungen (test_bereiche.BereicheTest.test_belege_und_verknuepfungen) ... ok
test_buchungen_suche_und_schreiben (test_bereiche.BereicheTest.test_buchungen_suche_und_schreiben) ... ok
test_dashboard_jahre_und_verlauf (test_bereiche.BereicheTest.test_dashboard_jahre_und_verlauf) ... ok
test_export_xlsx_und_bericht (test_bereiche.BereicheTest.test_export_xlsx_und_bericht) ... ok
test_fachliche_endpoints_haben_zentrale_dependency (test_bereiche.BereicheTest.test_fachliche_endpoints_haben_zentrale_dependency) ... ok
test_fehlendes_bereichsschema_bleibt_kontrolliert_gesperrt (test_bereiche.BereicheTest.test_fehlendes_bereichsschema_bleibt_kontrolliert_gesperrt) ... ok
test_fotoauftraege_grenzen (test_bereiche.BereicheTest.test_fotoauftraege_grenzen) ... ok
test_fotoverarbeitung_uebergibt_belegbereich (test_bereiche.BereicheTest.test_fotoverarbeitung_uebergibt_belegbereich) ... ok
test_gruppen_sind_bereichsgebunden (test_bereiche.BereicheTest.test_gruppen_sind_bereichsgebunden) ... ok
test_kategorien_grenzen (test_bereiche.BereicheTest.test_kategorien_grenzen) ... ok
test_login_ignoriert_unbekannten_bereich_fachlicher_endpoint_nicht (test_bereiche.BereicheTest.test_login_ignoriert_unbekannten_bereich_fachlicher_endpoint_nicht) ... ok
test_regeln_und_namensabgleich_der_schnellerfassung (test_bereiche.BereicheTest.test_regeln_und_namensabgleich_der_schnellerfassung) ... ok
test_stammdaten_und_bereichsaufloesung (test_bereiche.BereicheTest.test_stammdaten_und_bereichsaufloesung) ... ok
test_upload_dubletten_nur_im_bereich (test_bereiche.BereicheTest.test_upload_dubletten_nur_im_bereich) ... ok
test_account_creation_and_import_reject_foreign_references (test_bereiche_import.BereicheImportTest.test_account_creation_and_import_reject_foreign_references) ... ok
test_batch_checks_all_ids_before_first_commit (test_bereiche_import.BereicheImportTest.test_batch_checks_all_ids_before_first_commit) ... ok
test_domain_two_rule_and_batch_mutations (test_bereiche_import.BereicheImportTest.test_domain_two_rule_and_batch_mutations) ... ok
test_foreign_and_inconsistent_rules_are_not_proposed (test_bereiche_import.BereicheImportTest.test_foreign_and_inconsistent_rules_are_not_proposed) ... ok
test_foreign_mutations_are_404_and_do_not_write (test_bereiche_import.BereicheImportTest.test_foreign_mutations_are_404_and_do_not_write) ... ok
test_lists_and_foreign_filters (test_bereiche_import.BereicheImportTest.test_lists_and_foreign_filters) ... ok
test_rule_learning_stays_in_domain (test_bereiche_import.BereicheImportTest.test_rule_learning_stays_in_domain) ... ok
test_current_schema_accepts_migration_and_seed_has_separate_domains (test_bereiche_migration.BereicheMigrationTest.test_current_schema_accepts_migration_and_seed_has_separate_domains) ... ok
test_migration_assigns_domains_and_removes_only_foreign_memberships (test_bereiche_migration.BereicheMigrationTest.test_migration_assigns_domains_and_removes_only_foreign_memberships) ... ok
test_schema_and_migration_have_identical_structure (test_bereiche_migration.BereicheMigrationTest.test_schema_and_migration_have_identical_structure) ... ok
test_sql_runner_logs_skipped_existing_column (test_bereiche_migration.BereicheMigrationTest.test_sql_runner_logs_skipped_existing_column) ... ok
test_sql_runner_preserves_trigger_and_string_semicolons (test_bereiche_migration.BereicheMigrationTest.test_sql_runner_preserves_trigger_and_string_semicolons) ... ok
test_sql_runner_rolls_back_fk_failure_and_restores_enforcement (test_bereiche_migration.BereicheMigrationTest.test_sql_runner_rolls_back_fk_failure_and_restores_enforcement) ... ok
test_liefert_hoechstens_200_neueste_buchungen (test_buchungen_suche.BuchungenSucheApiTest.test_liefert_hoechstens_200_neueste_buchungen) ... ok
test_sucht_case_insensitiv_in_text_notiz_und_kontakt (test_buchungen_suche.BuchungenSucheApiTest.test_sucht_case_insensitiv_in_text_notiz_und_kontakt) ... ok
test_alte_revision_wird_abgewiesen (test_export_profil.ExportProfilTests.test_alte_revision_wird_abgewiesen) ... ok
test_paket_enthaelt_excel_und_inhalt (test_export_profil.ExportProfilTests.test_paket_enthaelt_excel_und_inhalt) ... ok
test_vorschau_respektiert_kategorie_und_buchungsausschluss (test_export_profil.ExportProfilTests.test_vorschau_respektiert_kategorie_und_buchungsausschluss) ... ok
test_alter_fingerabdruck_verhindert_neuen_umsatz (test_import_bank.ImportBankApiTest.test_alter_fingerabdruck_verhindert_neuen_umsatz) ... ok
test_dublettenschutz_bei_wiederholtem_import (test_import_bank.ImportBankApiTest.test_dublettenschutz_bei_wiederholtem_import) ... ok
test_erfolgreicher_import_mehrerer_umsaetze (test_import_bank.ImportBankApiTest.test_erfolgreicher_import_mehrerer_umsaetze) ... ok
test_george_fixture_importiert_alle_zeilen_und_erkennt_spalten (test_import_bank.ImportBankApiTest.test_george_fixture_importiert_alle_zeilen_und_erkennt_spalten) ... ok
test_george_identische_zeilen_bleiben_zwei_und_reimport_ist_dubletten (test_import_bank.ImportBankApiTest.test_george_identische_zeilen_bleiben_zwei_und_reimport_ist_dubletten) ... ok
test_kaputte_csv_liefert_4xx_statt_500 (test_import_bank.ImportBankApiTest.test_kaputte_csv_liefert_4xx_statt_500) ... ok
test_semikolon_beispiel_prueft_und_speichert_saldo (test_import_bank.ImportBankApiTest.test_semikolon_beispiel_prueft_und_speichert_saldo) ... ok
test_verbuchen_erzeugt_buchung_und_lernt_regel (test_import_bank.ImportBankApiTest.test_verbuchen_erzeugt_buchung_und_lernt_regel) ... ok
test_erkennung_und_utf16 (test_import_bank.ParserTest.test_erkennung_und_utf16) ... ok
test_parse_betrag_cent (test_import_bank.ParserTest.test_parse_betrag_cent) ... ok
test_parse_datum (test_import_bank.ParserTest.test_parse_datum) ... ok
test_datei_ohne_kassabuch_layout_erzeugt_andere_warnung (test_import_excel.ImportExcelApiTest.test_datei_ohne_kassabuch_layout_erzeugt_andere_warnung)
Kein Blatt hat eine erkennbare Kopfzeile -> eigener Hinweistext. ... ok
test_dubletten_bei_wiederholtem_einspielen (test_import_excel.ImportExcelApiTest.test_dubletten_bei_wiederholtem_einspielen) ... ok
test_einspielen_legt_buchungen_an (test_import_excel.ImportExcelApiTest.test_einspielen_legt_buchungen_an) ... ok
test_leere_vorlage_erzeugt_warnung (test_import_excel.ImportExcelApiTest.test_leere_vorlage_erzeugt_warnung)
Aufgabe 1: eine Datei ohne jede Betragszeile darf nicht stillschweigend ... ok
test_pruefen_aendert_datenbank_nicht (test_import_excel.ImportExcelApiTest.test_pruefen_aendert_datenbank_nicht) ... ok
test_unbekannte_kategorien_werden_gemeldet (test_import_excel.ImportExcelApiTest.test_unbekannte_kategorien_werden_gemeldet) ... ok
test_bankomat_storno_und_cursor (test_konten_bewegungen.KontenApiTest.test_bankomat_storno_und_cursor) ... ok
test_bar_anlegen_aendern_loeschen (test_konten_bewegungen.KontenApiTest.test_bar_anlegen_aendern_loeschen) ... ok
test_csv_und_kassa_importverbot (test_konten_bewegungen.KontenApiTest.test_csv_und_kassa_importverbot) ... ok
test_geteilten_import_loeschen_und_transferimport_erhalten (test_konten_bewegungen.KontenApiTest.test_geteilten_import_loeschen_und_transferimport_erhalten) ... ok
test_import_verknuepfung_und_vorlaeufige_bewegung (test_konten_bewegungen.KontenApiTest.test_import_verknuepfung_und_vorlaeufige_bewegung) ... ok
test_kompatible_barumbuchung_und_storno (test_konten_bewegungen.KontenApiTest.test_kompatible_barumbuchung_und_storno) ... ok
test_konten_alias_validierung_und_bereich (test_konten_bewegungen.KontenApiTest.test_konten_alias_validierung_und_bereich) ... ok
test_notiz_kann_keinen_fremden_transfer_stornieren (test_konten_bewegungen.KontenApiTest.test_notiz_kann_keinen_fremden_transfer_stornieren) ... ok
test_put_prueft_erhaltenen_umsatz_und_oeffnet_abgeloesten (test_konten_bewegungen.KontenApiTest.test_put_prueft_erhaltenen_umsatz_und_oeffnet_abgeloesten) ... ok
test_unbekannte_zahlung_und_fremdes_konto (test_konten_bewegungen.KontenApiTest.test_unbekannte_zahlung_und_fremdes_konto) ... ok
test_bestandskopie_nachzug_und_schema_identisch (test_konten_bewegungen.KontenMigrationTest.test_bestandskopie_nachzug_und_schema_identisch) ... ok
test_bereich_und_referenzen_werden_geprueft (test_kredit.KreditApiTest.test_bereich_und_referenzen_werden_geprueft) ... ok
test_elf_raten_melden_abweichung_und_vorjahreszins_schaetzt (test_kredit.KreditApiTest.test_elf_raten_melden_abweichung_und_vorjahreszins_schaetzt) ... ok
test_jahreszins_wird_auf_raten_und_auswertung_verteilt (test_kredit.KreditApiTest.test_jahreszins_wird_auf_raten_und_auswertung_verteilt) ... ok
test_verteile_zins_erhaelt_jeden_cent (test_kredit.KreditLogikTest.test_verteile_zins_erhaelt_jeden_cent) ... ok
test_migration_007_zweimal_und_view (test_kredit.KreditMigrationTest.test_migration_007_zweimal_und_view) ... ok
test_alte_datenbank_erhaelt_basis_version_und_einmalige_sicherung (test_migrate.MigrationTest.test_alte_datenbank_erhaelt_basis_version_und_einmalige_sicherung) ... ok
test_fehlende_sicherung_ist_bei_wegwerf_datenbank_erlaubt (test_migrate.MigrationTest.test_fehlende_sicherung_ist_bei_wegwerf_datenbank_erlaubt) ... ok
test_fehlerhafte_migration_rollt_zurueck_und_sperrt_version (test_migrate.MigrationTest.test_fehlerhafte_migration_rollt_zurueck_und_sperrt_version) ... ok
test_fehlgeschlagene_pflichtsicherung_stoppt_nachzug (test_migrate.MigrationTest.test_fehlgeschlagene_pflichtsicherung_stoppt_nachzug) ... ok
test_migrationsfehler_startet_app_schreibgeschuetzt (test_migrate.MigrationTest.test_migrationsfehler_startet_app_schreibgeschuetzt) ... ok
test_neue_datenbank_ist_auf_version_9_ohne_anstehende_migrationen (test_migrate.MigrationTest.test_neue_datenbank_ist_auf_version_9_ohne_anstehende_migrationen) ... ok
test_neue_und_alte_datenbank_haben_gleiche_tabellenliste (test_migrate.MigrationTest.test_neue_und_alte_datenbank_haben_gleiche_tabellenliste) ... ok
test_schema_endpoint_liefert_erwartete_felder (test_migrate.MigrationTest.test_schema_endpoint_liefert_erwartete_felder) ... ok
test_schreibschutz_blockiert_auth_login_nicht (test_migrate.MigrationTest.test_schreibschutz_blockiert_auth_login_nicht) ... ok
test_schreibschutz_blockiert_post_aber_nicht_get (test_migrate.MigrationTest.test_schreibschutz_blockiert_post_aber_nicht_get) ... ok
test_aktuelles_passwort_ist_fuer_passwortmanager_gekennzeichnet (test_password_frontend.PasswordFrontendTest.test_aktuelles_passwort_ist_fuer_passwortmanager_gekennzeichnet) ... ok
test_desktop_navigation_verlinkt_passwortaenderung (test_password_frontend.PasswordFrontendTest.test_desktop_navigation_verlinkt_passwortaenderung) ... ok
test_erfolgsmeldung_ist_fokussierbar_und_fuehrt_zur_anmeldung (test_password_frontend.PasswordFrontendTest.test_erfolgsmeldung_ist_fokussierbar_und_fuehrt_zur_anmeldung) ... ok
test_kopiermeldung_bleibt_im_sichtbaren_recovery_panel (test_password_frontend.PasswordFrontendTest.test_kopiermeldung_bleibt_im_sichtbaren_recovery_panel) ... ok
test_login_verlinkt_passwort_vergessen (test_password_frontend.PasswordFrontendTest.test_login_verlinkt_passwort_vergessen) ... ok
test_mehr_menue_verlinkt_passwortaenderung (test_password_frontend.PasswordFrontendTest.test_mehr_menue_verlinkt_passwortaenderung) ... ok
test_netzwerkfehler_werden_verstaendlich_angezeigt (test_password_frontend.PasswordFrontendTest.test_netzwerkfehler_werden_verstaendlich_angezeigt) ... ok
test_passwortaenderung_sendet_altes_und_neues_passwort (test_password_frontend.PasswordFrontendTest.test_passwortaenderung_sendet_altes_und_neues_passwort) ... ok
test_passwortfelder_begrenzen_laenge_und_verwenden_neues_autocomplete (test_password_frontend.PasswordFrontendTest.test_passwortfelder_begrenzen_laenge_und_verwenden_neues_autocomplete) ... ok
test_recovery_code_kann_kopiert_werden (test_password_frontend.PasswordFrontendTest.test_recovery_code_kann_kopiert_werden) ... ok
test_recovery_code_wird_nur_in_einem_sicheren_bereich_angeboten (test_password_frontend.PasswordFrontendTest.test_recovery_code_wird_nur_in_einem_sicheren_bereich_angeboten) ... ok
test_setup_hat_zwei_passwortfelder_und_recovery_aktionen (test_password_frontend.PasswordFrontendTest.test_setup_hat_zwei_passwortfelder_und_recovery_aktionen) ... ok
test_setup_ruft_initial_password_mit_same_origin_credentials_auf (test_password_frontend.PasswordFrontendTest.test_setup_ruft_initial_password_mit_same_origin_credentials_auf) ... ok
test_weiter_zur_anmeldung_ist_vollwertige_aktion (test_password_frontend.PasswordFrontendTest.test_weiter_zur_anmeldung_ist_vollwertige_aktion) ... ok
test_wiederherstellung_setzt_neues_passwort_und_zeigt_fehler (test_password_frontend.PasswordFrontendTest.test_wiederherstellung_setzt_neues_passwort_und_zeigt_fehler) ... ok
test_windows_cleanup_ist_idempotent_und_beendet_den_gestarteten_baum (test_process_cleanup.ProcessCleanupTest.test_windows_cleanup_ist_idempotent_und_beendet_den_gestarteten_baum) ... ok
test_manuelles_verbuchen_lernt_regel_und_liefert_vollstaendigen_vorschlag (test_regeln.RegelvorschlagApiTest.test_manuelles_verbuchen_lernt_regel_und_liefert_vollstaendigen_vorschlag) ... ok
test_regelverwaltung_und_bulk_uebernahme (test_regeln.RegelvorschlagApiTest.test_regelverwaltung_und_bulk_uebernahme) ... ok
test_studio_bietet_bulk_uebernahme_und_regelverwaltung (test_regeln.RegelvorschlagApiTest.test_studio_bietet_bulk_uebernahme_und_regelverwaltung) ... ok
test_verbuchen_validiert_kategorierichtung_und_umbuchung (test_regeln.RegelvorschlagApiTest.test_verbuchen_validiert_kategorierichtung_und_umbuchung) ... ok
test_anker_und_bewegungen_rechnen (test_saldoanker.SaldoankerApiTest.test_anker_und_bewegungen_rechnen) ... ok
test_importalter_und_csv_importanker (test_saldoanker.SaldoankerApiTest.test_importalter_und_csv_importanker) ... ok
test_kassazaehlung_und_buchen (test_saldoanker.SaldoankerApiTest.test_kassazaehlung_und_buchen) ... ok
test_unbekannter_stand_ist_nicht_null (test_saldoanker.SaldoankerApiTest.test_unbekannter_stand_ist_nicht_null) ... ok
test_voranker_warnung_und_bereich (test_saldoanker.SaldoankerApiTest.test_voranker_warnung_und_bereich) ... ok
test_zaehlung_nur_kassa_und_liste (test_saldoanker.SaldoankerApiTest.test_zaehlung_nur_kassa_und_liste) ... ok
test_migration_006_idempotent (test_saldoanker.SaldoankerMigrationTest.test_migration_006_idempotent) ... ok
test_dezimalkomma_bleibt_beim_splitten_erhalten (test_schnellerfassung_mehrere.SammeltextErfassungTest.test_dezimalkomma_bleibt_beim_splitten_erhalten) ... ok
test_mehrere_positionen_durch_komma_getrennt (test_schnellerfassung_mehrere.SammeltextErfassungTest.test_mehrere_positionen_durch_komma_getrennt) ... ok
test_mehrzeiliger_text_wird_je_zeile_geparst (test_schnellerfassung_mehrere.SammeltextErfassungTest.test_mehrzeiliger_text_wird_je_zeile_geparst) ... ok
test_parse_verhaelt_sich_unveraendert (test_schnellerfassung_mehrere.SammeltextErfassungTest.test_parse_verhaelt_sich_unveraendert) ... ok
test_autostart_empfiehlt_keine_lan_freigabe (test_secure_launchers.SecureLauncherTest.test_autostart_empfiehlt_keine_lan_freigabe) ... ok
test_handy_launcher_oeffnet_nur_private_produktiv_url (test_secure_launchers.SecureLauncherTest.test_handy_launcher_oeffnet_nur_private_produktiv_url) ... ok
test_cli_akzeptiert_sechs_zeichen_und_schreibt_neues_format (test_set_auth_password.SetAuthPasswordTest.test_cli_akzeptiert_sechs_zeichen_und_schreibt_neues_format) ... ok
test_nur_recovery_code_laesst_passwort_unveraendert (test_set_auth_password.SetAuthPasswordTest.test_nur_recovery_code_laesst_passwort_unveraendert) ... ok
test_nur_recovery_code_ohne_bestehende_datei_scheitert_sauber (test_set_auth_password.SetAuthPasswordTest.test_nur_recovery_code_ohne_bestehende_datei_scheitert_sauber) ... Keine bestehende Auth-Datei unter C:\Users\lblet\AppData\Local\Temp\tmp6tqmualt\auth.json gefunden. Ohne bestehendes Passwort kann kein Recovery-Code erzeugt werden.
ok
test_suchfeld_nutzt_server_suche_mit_debounce_und_normale_leerliste (test_studio_suche.StudioSucheTest.test_suchfeld_nutzt_server_suche_mit_debounce_und_normale_leerliste) ... ok
test_betrag_0_oder_negativ_wird_abgelehnt (test_umbuchungen.UmbuchungenApiTest.test_betrag_0_oder_negativ_wird_abgelehnt) ... ok
test_gleiche_sparte_wird_abgelehnt (test_umbuchungen.UmbuchungenApiTest.test_gleiche_sparte_wird_abgelehnt) ... ok
test_umbuchung_erzeugt_zwei_gekoppelte_buchungen (test_umbuchungen.UmbuchungenApiTest.test_umbuchung_erzeugt_zwei_gekoppelte_buchungen) ... ok
test_umbuchung_ist_erfolgsneutral_im_dashboard (test_umbuchungen.UmbuchungenApiTest.test_umbuchung_ist_erfolgsneutral_im_dashboard) ... ok

----------------------------------------------------------------------
Ran 210 tests in 211.753s

OK (skipped=1)
Angewendet: [1]
```
