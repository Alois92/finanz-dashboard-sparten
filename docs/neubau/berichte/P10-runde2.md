# P10 - Ruecklaeufer, Runde 2

Bearbeitet am 9. September 2026 auf `pkt/p10-bereiche`, aufbauend auf den uncommitted Aenderungen aus Runde 1; keine Commits und kein Push.

## Befunde und Aenderungen

Befund 1: Die Bereichsdependency ist von den sechs Auth-Endpunkten sowie `/api/health`, `/api/schema` und `/api/betrieb/status` entfernt. Alle fachlichen Endpunkte und die Bereichstrennung bleiben unveraendert. Der Dependency-Test begruendet die neun Ausnahmen mit dem anwendungsweiten Zugang und der Diagnose nach fehlgeschlagenem Nachzug (P00).

Der Regressionstest erzeugt die Struktur vor P10, laesst Migration 003 tatsaechlich scheitern und prueft nach dem Rollback ohne Tabelle `bereich`: falsches Passwort ergibt 401, korrektes Passwort 204, Health 200, Schema/Betriebsstatus 200; fachliche Zugriffe bleiben kontrolliert gesperrt. Die Login- und Health-Pruefungen laufen ohne Auth-Bypass. Ein weiterer Test prueft Login mit `bereich_id=99` (401 bzw. 204) und den unveraenderten 404-Vertrag fuer `/api/buchungen?bereich_id=99`.

Befund 2: Bereits vorhandene ADD-COLUMN-Spalten erzeugen einen INFO-Eintrag mit Migration, Tabelle und Spalte. Ein allgemeiner Test mit Migration 777 und einer abweichend definierten vorhandenen Spalte prueft die Protokollierung, die unveraenderte Bestandsspalte, die Ausfuehrung der naechsten SQL-Anweisung und die Wiederholbarkeit. Der Runner bekommt keine fachliche Sonderbehandlung.

## In Runde 2 geaenderte Dateien

| Datei | Aenderung |
|---|---|
| `app/auth.py` | Entfernt ausschliesslich die Bereichsdependency und deren Import von den sechs Auth-Endpunkten. |
| `app/main.py` | Entfernt ausschliesslich die Bereichsdependency und deren Import von Health, Schema und Betriebsstatus. |
| `app/migrate.py` | Protokolliert jedes uebersprungene ADD COLUMN auf INFO mit Version, Tabelle und Spalte. |
| `tests/test_bereiche.py` | Begrenzt die Dependency-Pflicht mit begruendeten Ausnahmen auf fachliche Endpunkte und prueft Login/Diagnose bei fehlendem Schema sowie unbekannte Bereichskennungen. |
| `tests/test_bereiche_migration.py` | Ergaenzt den Regressionstest fuer protokollierte bereits vorhandene Spalten im allgemeinen SQL-Runner. |
| `docs/neubau/berichte/P10-runde2.md` | Dokumentiert diese Korrekturen, Testausgaben und verbleibende Einschraenkungen. |

## Verifikation

Vor der Produktkorrektur schlugen die neuen Pruefungen gezielt fehl: Dependency an allen neun Ausnahmen, Login 503 bei fehlendem Schema, Login 404 bei Bereich 99 und fehlender INFO-Eintrag. Nach der Korrektur: 14 Bereichstests und 6 Migrationstests erfolgreich. Ein Fehler im neuen Test zur zweiten Anwendung (Verzeichnis-Patch bereits verlassen) wurde korrigiert und der Migrationstest erneut erfolgreich ausgefuehrt.

`git diff --check` meldet keine Whitespace-Fehler; Git weist lediglich auf bestehende LF/CRLF-Konvertierungen in anderen P10-Dateien hin.

### Gesamte Testsuite und Testumgebung

Befehl in beiden Versuchen: `python -m unittest discover -s tests`, Python 3.12.10; FINANZ_DB jeweils vor dem Prozessstart gesetzt.

Der unveraenderte Lauf verwendete `FINANZ_DB=C:\Users\lblet\AppData\Local\Temp\finanz-p10-runde2-a841b80710c04b81b1e6404ac523a663\suite-normal.db`. Er blieb nach den ersten Fehlermarkierungen mehrere Minuten ohne weiteren Fortschritt und wurde beendet; es gibt dafuer keinen erfolgreichen Testabschluss. Vollstaendige bis dahin ausgegebene Ausgabe:

```text
EE..
```

Bereits die isolierte Vorpruefung belegte das Umgebungsproblem: `tempfile.TemporaryDirectory()` erzeugt hier mit Modus 0700 ein Verzeichnis, in dem anschliessend `sqlite3.connect` mit `unable to open database file` und Cleanup mit `PermissionError: [WinError 5] Zugriff verweigert` scheitern. Ein normales Verzeichnis mit geerbten Windows-Rechten ist nutzbar. Deshalb wurde ausschliesslich ausserhalb des Repos eine `sitecustomize.py` fuer den ergaenzenden Testlauf angelegt, die die Verzeichnisanlage innerhalb von `tempfile` mit geerbten Rechten ausfuehrt; weder Repo-Dateien noch Produkt-Auth oder Validierung werden dadurch geaendert. Keine Abhaengigkeiten installiert.

Exakter Inhalt der externen Umgebungshilfe:

```python
# Windows sandbox test harness: inherit directory ACLs for temporary test data only.
import os
import tempfile
import types
_original_os = tempfile._os

def _temp_mkdir(path, mode=0o777, *, dir_fd=None):
    return _original_os.mkdir(path, 0o777, dir_fd=dir_fd)

tempfile._os = types.SimpleNamespace(**{**vars(os), "mkdir": _temp_mkdir})

```

Ergaenzender Gesamtlauf: `PYTHONPATH=C:\Users\lblet\AppData\Local\Temp\finanz-p10-runde2-a841b80710c04b81b1e6404ac523a663`, `FINANZ_DB=C:\Users\lblet\AppData\Local\Temp\finanz-p10-runde2-a841b80710c04b81b1e6404ac523a663\suite-assisted-direct.db`, `PYTHONIOENCODING=utf-8`. Ausgabe via PowerShell `2>&1 | Out-File -Encoding utf8` aufgezeichnet; die erste PowerShell-NativeCommandError-Einrahmung stammt von der stderr-Umleitung und ist unten unveraendert enthalten. Python-Exitcode: **0**. Ergebnis: **161 Tests in 238.694s, OK (skipped=1)**.

### Vollstaendige Ausgabe des abgeschlossenen Gesamtlaufs

```text
python : ............C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: 
subprocess 35220 is still running
In Zeile:6 Zeichen:1
+ python -m unittest discover -s tests 2>&1 | Out-File -LiteralPath (Jo ...
+ ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (............C:\...s still running:String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
 
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 22176 is 
still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 21252 is 
still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 18532 is 
still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 29748 is 
still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 35780 is 
still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 25728 is 
still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 18204 is 
still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 35692 is 
still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 32032 is 
still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 22908 is 
still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 35424 is 
still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 36536 is 
still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 32512 is 
still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 35408 is 
still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 1528 is 
still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 37192 is 
still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 35228 is 
still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 36660 is 
still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 7324 is 
still running
  _warn("subprocess %s is still running" % self.pid,
ResourceWarning: Enable tracemalloc to get the object allocation traceback
.C:\Users\lblet\AppData\Local\Programs\Python\Python312\Lib\subprocess.py:1127: ResourceWarning: subprocess 26100 is 
still running
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
.....................................................................................Keine bestehende Auth-Datei unter 
C:\Users\lblet\AppData\Local\Temp\tmpxe42oz5q\auth.json gefunden. Ohne bestehendes Passwort kann kein Recovery-Code 
erzeugt werden.
......
----------------------------------------------------------------------
Ran 161 tests in 238.694s

OK (skipped=1)

```

## Offene Punkte mit Grund

- Kein offener Implementierungspunkt zu den beiden Befunden; Bereichstrennung, Auth-Logik, Validierung und Abhaengigkeiten wurden nicht erweitert oder abgeschwaecht.
- Der Gesamtlauf ohne Umgebungshilfe ist in dieser Windows-Sandbox nicht erfolgreich verifiziert: temporaere Verzeichnisse mit Modus 0700 sind nicht nutzbar, der Versuch blieb haengen und wurde beendet; fuer eine Abnahme ohne diese Umgebungseinschraenkung ist der unveraenderte Befehl nochmals in einer normalen Umgebung auszufuehren.
- Ein vorhandener POSIX-Dateirechtetest wird auf Windows planmaessig uebersprungen; erwartete Sicherungs-Fehlersimulationen und der bestehende Bild-Fallback wegen fehlendem Pillow bleiben in der Ausgabe sichtbar.
- Das bestehende Testserver-Cleanup beendet in dieser Sandbox nicht alle Prozesse; die 21 im Protokoll eindeutig identifizierten eigenen Testserver wurden anschliessend mit Stop-Process beendet, Nachkontrolle: 0 davon noch laufend. Bereits vor dieser Runde laufende Prozesse blieben unberuehrt.

Keine Commits, kein Push. Die Aussagen aus Runde 1, Auth und Diagnose muessten bei fehlendem Bereichsschema 503 liefern, sind durch diese Runde korrigiert; der historische Bericht bleibt unveraendert.
