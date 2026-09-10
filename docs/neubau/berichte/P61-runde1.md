# P61 – Runde 1, 10. September 2026

P61 ist implementiert und auf synthetischen Offline-Kopien geprüft.
Eine echte Produktionskopie wurde gemäß Nachtrag nicht verwendet; diese
fachliche Abnahme bleibt beim Kopf. Der vollständige Testlauf ist wegen der
unten beschriebenen Sandbox-Prozessgrenze nicht als grün abgenommen.

Vorgabe: [Paketkarte](../pakete/P61-migrationsprobe.md), mit Vorrang für den
[Nachtrag](../pakete/P61-nachtrag-2026-09-10.md).
Arbeitsverzeichnis `C:\Users\lblet\dev\wt-p61-migrationsprobe`, Zweig
`pkt/p61-migrationsprobe`. Keine Commits und kein Push.

## Neue Dateien

- `scripts/migrationsprobe.py`: reine Summen-/Vergleichsfunktionen, geschützter
  Kopierlauf, vorhandener Migrationsrunner und JSON-/CLI-Bericht.
- `tests/test_migrationsprobe.py`: Tests mit P10-Fixture, echtem Rückbau auf
  Version 0 und ausschließlich synthetischen TemporaryDirectory-Datenbanken.
- `docs/neubau/berichte/P61-runde1.md`: Umsetzung, Nachweise und offene Punkte.
- [P61-tests.txt](P61-tests.txt): vollständige aufgezeichnete Ausgabe der
  Abschlussprüfungen einschließlich des abgebrochenen Gesamtlaufs.
- [P61-proben.txt](P61-proben.txt): vollständige lesbare Ausgabe aller vier
  Abnahmeproben mit Migrationslog und Migrationsprotokoll.
- [P61-p10-lauf1.json](P61-p10-lauf1.json) und
  [P61-p10-lauf2.json](P61-p10-lauf2.json): vollständige Berichte der beiden
  frischen P10-Kopien.
- [P61-v0-lauf1.json](P61-v0-lauf1.json) und
  [P61-v0-lauf2.json](P61-v0-lauf2.json): vollständige Berichte der beiden
  frischen Version-0-Kopien.

Bestehende Anwendung, Schema, Fixture und Migrationen wurden nicht verändert.
Keine neuen Abhängigkeiten, keine neue Migration.

## Umsetzung und fachliche Entscheidungen

`lauf(quelle_db, arbeitsordner)` verwendet `shutil.copy2` und öffnet
ausschließlich `kopie.db` und `sicherung.db` mit SQLite. Die Quelle wird nur
binär gelesen. Kein Import von `app.db` oder `app.backup`: deren globale
Pfad-/Sicherungsauflösung könnte eine Betriebsdatenbank auswählen.
Die tatsächlich verfügbare API ist `migrate.anwenden(con, sicherung,
sicherung_pflicht=True)`; das argumentlose Callable nutzt `con.backup` und
prüft die Integrität der Sicherung. Vorhandene Artefakte werden abgewiesen.
Fehlende/unlesbare Quellen führen zum Fehler, nicht zu einer leeren SQLite-DB.

Der konfigurierte FINANZ_DB-Pfad ist als Quelle und als Schreibziel gesperrt;
der dokumentierte Produktivpfad und UNC-Quellen sind als Quelle gesperrt.
Eine Quelle mit nichtleerem WAL/Journal wird
abgewiesen, weil die vorgeschriebene einzelne Dateikopie sonst keinen
konsistenten Snapshot garantiert. Für die spätere echte Probe ist eine
abgeschlossene Offline-Sicherung erforderlich. Ein beliebiger Dateiname
beweist nicht, dass es sich um eine Kopie handelt; die Herkunft muss der
spätere Bediener sicherstellen. In dieser Runde wurden nur die unten
beschriebenen synthetischen Quellen angelegt und benutzt.

Die alte Rechnung summiert Buchungszeilen direkt, schließt nur Umbuchungen
aus und ignoriert neutral/Stornos/Zahlungsbewegungen. Die neue Rechnung
nutzt `v_einnahmen_ausgaben`, mit Neutral-/Transferausschluss. Ganze Centwerte
bleiben Integer, auch jenseits der exakten Float-Darstellung; fehlende
Sparte/Jahr-Kombinationen zählen im Vergleich als null.

Buchung und Buchungszeile besitzen in Schema 14 keine `storniert_am`-Spalte.
Stornos an Bewegung/Transfer betreffen die Zahlung und dürfen nicht Kosten
entfernen. Das ist durch einen Test mit stornierten und mehrfach verknüpften
Bewegungen abgesichert. Für mitgebrachte Kostenstorno-Spalten an Buchung oder
Zeile berücksichtigt die neue Rechnung `storniert_am IS NULL`; ein eigener
Test belegt deren Abweichung zur alten Rechnung. Keine Schemaerweiterung
durch das Probeskript und keine erfundene Stornologik in den Migrationen.

Der Bereichsbericht enthält vorher/nachher/erwartet je Sparte und Buchungsjahr,
auch reine Umbuchungsjahre; leere Sparten erscheinen mit Jahr `null`.
ZINA wird über Kürzel oder Namen erkannt und erwartet Bereich 2, andere
Sparten Bereich 1. Bei Version 0 bedeutet `vorher: null`, dass die Spalte
noch nicht existierte; ihre erstmalige korrekte Zuordnung ist kein Fehler.
Eine bereits vorhandene falsche oder veränderte Zuordnung fällt auf.

Ungeklärte Umbuchungen werden anhand der Objektkennungen aus Migration 012
und der Transfernotizen zusammengeführt; derselbe Fall wird nicht doppelt
gezählt. Zusätzlich werden die Zahlen aus dem P11-Log ausgewertet und separat
ausgewiesen. Der Gesamtwert unterschreitet weder Bestand/Protokoll noch Log.
Historische Protokollhinweise werden nicht als erledigt unterstellt.
Unbekannte Zahlungen und ungeklärte Barbuchungen bleiben sichtbar.

`erfolgreich` verlangt gleiche Summen, korrekte Bereiche, gleiche Anzahl
Buchungen/Zeilen, leere Fremdschlüsselprüfung, Integrität `ok`, leeren zweiten
Runner-Aufruf, keine anstehenden Migrationen und gleiche Quellprüfsummen.
Die ausdrücklich zu meldenden ungeklärten Altfälle machen einen ansonsten
gleichen Nachzug nicht automatisch fehlerhaft.

CLI: `python -m scripts.migrationsprobe <offline-kopie.db> --arbeitsordner <ordner>`.
Ohne Arbeitsordner bleibt ein separat angelegter `p61-bericht-*.json` im
Temp-Verzeichnis erhalten; der temporäre Arbeitsordner samt Kopie und
Sicherung wird entfernt. Der Berichtspfad wird ausgegeben. Exitcode 0 heißt
Prüfungen bestanden, 1 fachliche/strukturelle Abweichung, 2 Lauf fehlgeschlagen.
Nach einem technischen Fehler mit explizitem Arbeitsordner bleiben die
erzeugten Artefakte zur Diagnose bestehen; für einen neuen Lauf ist ein
frischer Ordner zu verwenden.

## Vier vollständige Proben

Basis ist unverändert `tests/fixtures/schema_p10.sql`; das Datenmuster stammt
aus `scripts/p11_nachzug_probe.py`. `db/seed.sql` wird für die Probe nicht
eingespielt: zwei synthetische Sparten und Konten reichen aus. Die zweite
Sparte trägt allein für die fachliche Bereichsprüfung das Kürzel ZINA.
Der Version-0-Stand entfernt zusätzlich zur `schema_version`-Tabelle die
Bereichsspalten/-indizes/-tabelle und die P01-Importbatch-Nachrüstungen.
Es ist damit nicht bloß ein aktuelles Schema mit fehlender Versionsnummer.

Je Quelle: zwei Jahre, neun Buchungen, 18 Splitzeilen, drei Bankumsätze,
zwei Barbuchungen, ein bekanntes und ein unklares Umbuchungspaar sowie eine
Kartenbuchung ohne Umsatz. Alle Quellen und Arbeitskopien lagen unter TEMP;
die erfolgreich abgeschlossenen Abnahmeverzeichnisse wurden anschließend
durch `TemporaryDirectory` gelöscht. Nur Berichte wurden in den Arbeitsbaum
kopiert.

| Prüfung | P10 Lauf 1/2 | Version 0 Lauf 1/2 |
| --- | --- | --- |
| Angewendete Migrationen | 4–14 | 1–14, Basis 0 angelegt |
| Zielversion / anstehend | 14 / leer | 14 / leer |
| Summenvergleich | gleich, keine Abweichungen | gleich, keine Abweichungen |
| Buchungen vorher/nachher | 9 / 9 | 9 / 9 |
| Zeilen vorher/nachher | 18 / 18 | 18 / 18 |
| Bereiche | 1 → 1, ZINA 2 → 2 | fehlend → 1, ZINA fehlend → 2 |
| `foreign_key_check` | `[]` | `[]` |
| `integrity_check` | `["ok"]` | `["ok"]` |
| Zweiter `anwenden`-Aufruf | `[]` | `[]` |
| Ungeklärte Transfers | 1 | 1 |
| Zahlung unbekannt | 1 | 1 |
| Ungeklärte Barbuchungen im Log | 0 | 0 |
| Migrationsprotokoll | 2 Einträge | 2 Einträge |
| P11-Nachzug | 2 Kassen, 7 Bewegungen, 2 Transfers | identisch |

Die folgenden Summen gelten **vorher und nachher in allen vier Läufen**, in Cent:

| Sparte | Jahr | Einnahmen | Ausgaben |
| --- | --- | ---: | ---: |
| 1 | 2025 | 200 | 100 |
| 1 | 2026 | 0 | 90 |
| 2 | 2026 | 80 | 0 |

Das Migrationsprotokoll enthält jeweils `umbuchung_ungeklaert` für
`umbuchungsgruppe:probe-offen` und `zahlung_ungeklaert` für `buchung:9`, beide
mit Version 4. Der vollständige Inhalt einschließlich Hinweistext und
Zeitpunkt steht in jedem JSON und in P61-proben.txt.

Alle fachlichen Berichtsfelder der Wiederholung wurden per Assertion auf
Identität geprüft. Nur der absolute Sicherungspfad im Log und der technische
Protokollzeitpunkt wurden dafür ausgenommen. Diese Werte bleiben in den
unveränderten Originalberichten enthalten.

### SHA256-Nachweis der unveränderten Quellen

P10, vor Lauf 1, nach Lauf 1 und nach Lauf 2 identisch:

```text
5fcb720c4e4af9c6694046df9aed01698bbc6e1249e7142da57bd0904a53260f
```

Version 0, vor Lauf 1, nach Lauf 1 und nach Lauf 2 identisch:

```text
1e6237515712a9404ee1e07a61e99caef37d0a6cd362794ed7bda2df6025ca74
```

Die Tests prüfen zusätzlich, dass sich die migrierte Kopie gegenüber der
Quelle tatsächlich geändert hat und die Sicherung noch den Altstand trägt.

## Tests und Sandbox-Befund

Vorgeschriebener Interpreter:
`C:\Users\lblet\dev\finanz-dashboard-sparten\.venv\Scripts\python.exe`.
Vor jedem Lauf wurde FINANZ_DB auf einen neuen GUID-Dateinamen unter TEMP
gesetzt; für App-Tests auch FINANZ_AUTH_FILE auf eine Wegwerfdatei. Die
Migrationsprobe selbst verwendet diese FINANZ_DB-Datei nicht.

Die ersten Tests wurden vor dem Skript angelegt. Nach Behebung des unten
beschriebenen Umgebungsproblems schlugen sie erwartungsgemäß am noch fehlenden
Modulimport fehl; nach Implementierung bestanden alle zwölf P61-Tests.

Der erste unveränderte Aufruf scheiterte bereits bei `TemporaryDirectory`:
Python 3.12 legt Windows-Verzeichnisse mit Modus 0700 an, deren ACL in dieser
Sandbox anschließenden Zugriff verhindert (`unable to open database file`,
`WinError 5` beim Aufräumen). Eine isolierte Diagnose zeigte: `os.mkdir`
mit 0700 scheitert beim anschließenden Schreiben, mit 0755 gelingt es.
Die nachfolgenden Prüfläufe verwenden daher eine temporäre `sitecustomize.py`
über PYTHONPATH, ausschließlich für neu erzeugte Verzeichnisse unter TEMP:

```python
import os
from pathlib import Path
_original_mkdir = os.mkdir
_temp_root = Path(os.environ['TEMP']).resolve()
def _mkdir(path, mode=0o777, *, dir_fd=None):
    if mode == 0o700 and Path(path).resolve().is_relative_to(_temp_root):
        mode = 0o755
    return _original_mkdir(path, mode, dir_fd=dir_fd)
os.mkdir = _mkdir
```

Keine Änderung an Produktcode, Standardbibliothek auf Platte oder bestehenden
Verzeichnisrechten. Die Tests benutzen weiterhin `TemporaryDirectory` und
laufen niemals mit Datenbanken im Arbeitsbaum. Die Anpassung gilt auch für
die von den CLI-Tests gestarteten Python-Prozesse.

Der angeforderte Gesamtlauf `-m unittest discover -s tests` wurde gestartet.
Er blieb mit `ResourceWarning: subprocess ... is still running` bei der
Auth-Prozessbereinigung ohne Abschluss. Das dort verwendete Windows-
`taskkill /T /F` meldet in der Sandbox „Zugriff verweigert“. Der hängende
Runner und seine zugeordneten Python-Prozesse wurden gezielt beendet.
Die vollständige bis dahin ausgegebene Ausgabe steht in P61-tests.txt;
es gibt für diesen Lauf ausdrücklich kein erfolgreiches Endergebnis.

Zusätzlich wurde die gesamte übrige Suite ausgeführt, unter Auslassung genau
der 30 Tests aus `test_auth` und `test_auth_lifecycle`; Auth-Unit-, Store- und
Frontendtests bleiben enthalten. Die ausgelassenen IDs stehen vollständig
im Testprotokoll. Ergebnis: **244 Tests in 78,648 Sekunden, `OK (skipped=1)`,
Exitcode 0**. Der einzige reguläre Skip betrifft
`test_store_setzt_dateimodus_0600` mit Grund `POSIX-Dateirechte` unter Windows.
Erwartete Fehlerlogs aus bestehenden Negativtests sind vollständig erhalten.

Danach wurde der FINANZ_DB-Schutz um alle Schreibziele ergänzt: Ein neuer
Regressionstest schlug vorher für Kopie, Sicherung und JSON-Ziel fehl und
bestand nach der Korrektur. Der abschließende isolierte Lauf
`-m unittest discover -s tests -p test_migrationsprobe.py -v` ergab
**13 Tests in 6,065 Sekunden, `OK`, Exitcode 0**. Diese letzte Änderung ist
durch die gesamte P61-Suite geprüft; die 244er-Restsuite stammt vom Stand
unmittelbar davor. Beide vollständigen Ausgaben stehen in P61-tests.txt.

`git diff --check` und die zusätzliche Whitespace-/Syntax-/JSON-Prüfung der
neuen Dateien waren fehlerfrei; alle vier Probenberichte wurden gegen die
Abnahmekriterien und die dokumentierten Quellprüfsummen geprüft.

Eine unabhängige statische Codeprüfung meldete keine blockierenden Befunde.

## Fertig heißt / offene Punkte

- [ ] **Alle Tests grün:** Gesamtsuite durch Auth-/Prozessbereinigung in dieser
  Sandbox nicht vollständig nachgewiesen; vollständiger Wiederholungslauf
  außerhalb dieser Prozessgrenze bleibt offen. P61 isoliert ist grün.
- [x] **Zwei vollständige identische Proben:** für beide Altstände jeweils
  zweimal; vier JSON-Berichte und lesbare Gesamtausgabe oben verlinkt.
- [x] **Quelle unverändert:** SHA256 vor/nach jedem Lauf identisch, oben und
  in allen vier JSON-Berichten dokumentiert.
- [x] **Keine Geheimnisse/echten Namen/neuen Abhängigkeiten:** nur synthetische
  Probeobjekte, Standardbibliothek und vorhandenes `app.migrate`.
- [x] **Bericht geschrieben:** dieser Bericht und vollständige Testausgabe.

Weitere offene Abnahme: Die echte Kopie aus CT 101 wurde absichtlich nicht
verwendet. Laut verbindlichem Nachtrag fährt der Kopf diese Probe; diese
Runde ersetzt die fachliche Abnahme der Schuld A2neu auf echten Daten nicht.
Keine Bereinigung alter Kategorien, keine neue Migration, keine Änderung
an P11, kein Commit und kein Push.
