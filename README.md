# Finanz-Dashboard Sparten

Lokales, klickbares Finanz-Dashboard mit getrennten Sparten und flexibler
Auswertung. Konzept siehe [Projektkonzept](Projektkonzept_Finanz_Dashboard_Sparten_2026.md).

**Status:** Das Abschlusspaket ist umgesetzt. Das Studio deckt Stammdaten,
Buchungen, Importe, Auswertungen, Suche, Export und automatische Sicherungen ab.

## Technik

- **Backend:** Python + FastAPI (`app/`)
- **Datenbank:** SQLite (`db/schema.sql`, `db/seed.sql`)
- **Frontend:** statisches HTML/JS ohne Build-Schritt (`static-studio/`, erreichbar unter `/` und `/studio`)

Alle Geldbetraege werden als Ganzzahl in **Cent** gespeichert. Die Datenbank
wird beim ersten Start automatisch aus Schema + Seed erzeugt.

## Umgesetzte Funktionen

- Buchungen mit Split-Aufteilung, Umbuchungen und Belegverknüpfung
- Dashboard mit Zeitraum-, Sparten- und globalen Kategoriegruppen-Filtern
- Pflege von Auswertungsgruppen und globalen Kategoriegruppen
- interaktive Verlaufs- und Kategorie-Diagramme mit Buchungs-Drill-down
- Bank-CSV-Import mit Dublettenschutz, lernenden Regelvorschlägen und Sammelübernahme
- Excel-Migration und Volltextsuche über Buchungstext, Notiz und Kontakt
- XLSX-Export mit drei Tabellenblättern und druckbarer Jahresbericht
- validierte SQLite-Sicherung über Temporärdatei und atomaren Austausch

### Wo liegt die Datenbank? (pro Rechner konfigurierbar)

Der Speicherort wird in dieser Reihenfolge bestimmt:

1. Umgebungsvariable `FINANZ_DB` (voller Pfad zur `.db`-Datei)
2. Datei `instance/db_location.txt` (eine Zeile mit dem Pfad; liegt lokal, **nicht** in Git)
3. Fallback: eine **temporaere** DB im Temp-Ordner - nur zum Testen, **keine dauerhaften Daten**

So bleibt ein Arbeits-/Entwicklungsrechner bewusst datenfrei. Am produktiven
Rechner (z. B. Heim-PC) den echten, privaten Speicherort setzen, z. B.:

```powershell
# Variante A: Config-Datei anlegen
"D:\Privat\Finanzen\finanz.db" | Out-File -Encoding utf8 instance\db_location.txt

# Variante B: Umgebungsvariable
$env:FINANZ_DB = "D:\Privat\Finanzen\finanz.db"
```

Die DB nutzt bewusst **kein WAL**, damit der Speicherort auch auf einem
Netzlaufwerk (SMB/NAS) zuverlaessig funktioniert.

## Einrichten (einmalig, je PC)

```powershell
# Repo holen
git clone https://github.com/Alois92/finanz-dashboard-sparten.git
cd finanz-dashboard-sparten

# virtuelle Umgebung + Abhaengigkeiten
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Starten

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
Dann im Browser: <http://127.0.0.1:8000>


## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts\test_gruppen_integration.py
.\.venv\Scripts\python.exe scripts\test_drilldown_api.py
.\.venv\Scripts\python.exe scripts\test_export_integration.py
node scripts\test_drilldown_charts.mjs
node --check static-studio\app.js
node --check static-studio\charts.js
```


Die Tests verwenden Wegwerf-Datenbanken und verändern keine produktiven Buchungsdaten.
## Wichtig zu den Daten

Die Buchungsdatenbank, Belege, Bank-CSVs und Backups werden **absichtlich nie**
nach GitHub synchronisiert (siehe `.gitignore` und Konzept Abschnitt 18).
Git synchronisiert nur Programm und Konzept – **nicht** den Datenbestand.
GitHub ist daher **kein Backup** der Buchungen; dafuer den lokalen
Backup-Weg (NAS/offline) nutzen.

## Optionale Zukunftsthemen

- Kontostand-Abgleich und Budgetplanung
- Mehrbenutzer- oder Cloud-Betrieb
- weiterführende Steuer- und Behördenexporte
- serverseitig erzeugte PDF-Dateien zusätzlich zum druckbaren Browser-Bericht
