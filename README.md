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

## Lokale Rechnungs-Auswertung (Ollama)

Rechnungen/Kassenbons lassen sich als Foto hochladen und lokal (kein
Cloud-Dienst) per [Ollama](https://ollama.com) mit einem Vision-Modell
auswerten: Haendler, Datum, Positionen und Kategorien-Vorschlag werden
automatisch erkannt und koennen anschliessend als Buchung uebernommen werden.

**Voraussetzung:** Ollama laeuft lokal (oder im Netzwerk erreichbar) mit einem
Vision-Modell, z. B.:

```powershell
ollama pull qwen2.5vl:7b
```

**ENV-Variablen** (optional, mit sinnvollen Defaults):

| Variable              | Default                    | Bedeutung                     |
|-----------------------|-----------------------------|--------------------------------|
| `FINANZ_OLLAMA_URL`   | `http://127.0.0.1:11434`   | Basis-URL des Ollama-Servers   |
| `FINANZ_OLLAMA_MODEL` | `qwen2.5vl:7b`              | zu verwendendes Vision-Modell  |

**Ablauf:**

1. Unter „Erfassen“ → „📷 Rechnung fotografieren“ Sparte waehlen, Foto
   aufnehmen/auswaehlen (JPG/PNG/WebP). Der Beleg wird sofort hochgeladen und
   ein Auswertungsauftrag angelegt (Status `offen`).
2. Ein Hintergrund-Task (`app/auswertung.py::auswertung_schleife`, startet mit
   dem Server) verarbeitet offene Auftraege alle ~15 Sekunden: laedt das Bild,
   ruft Ollama lokal auf (Timeout 10 Minuten) und speichert das erkannte
   Ergebnis (Status `fertig`) bzw. einen Fehlertext (Status `fehler`). Ist
   Ollama gerade nicht erreichbar, bleibt der Auftrag `offen` und wird spaeter
   automatisch erneut versucht (bis zu 5 Mal).
3. Unter „Erfassen“ → „Ausgewertete Rechnungen“ erscheinen offene, laufende,
   fertige und fehlerhafte Auftraege (Polling alle 20 s). Bei „fertig“:
   „Übernehmen“ fuellt das Buchungsformular (Sparte, Datum, Text, Positionen
   inkl. Kategorie-Vorschlag) - nach dem Speichern wird der bereits
   hochgeladene Beleg nur noch verknuepft (kein erneuter Upload) und der
   Auftrag auf `verbucht` gesetzt. „Verwerfen“ markiert den Auftrag als
   `verworfen`, ohne eine Buchung anzulegen.

Die Kategorien-Zuordnung je Position nutzt zuerst den Namensabgleich (nur
Kategorien der Beleg-Sparte), sonst gelernte Merkregeln (Feature „Merkregeln
ueberall“) - passend zur Beleg-Sparte.

## Optionale Zukunftsthemen

- Kontostand-Abgleich und Budgetplanung
- Mehrbenutzer- oder Cloud-Betrieb
- weiterführende Steuer- und Behördenexporte
- serverseitig erzeugte PDF-Dateien zusätzlich zum druckbaren Browser-Bericht
