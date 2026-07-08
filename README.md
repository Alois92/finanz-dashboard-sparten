# Finanz-Dashboard Sparten

Lokales, klickbares Finanz-Dashboard mit getrennten Sparten und flexibler
Auswertung. Konzept siehe [Projektkonzept](Projektkonzept_Finanz_Dashboard_Sparten_2026.md).

**Status:** Erster Meilenstein (MVP-Minimalkern) – Stammdaten, Kategorien und
manuelle Buchungserfassung mit Split, Umbuchungen und einem Dashboard.

## Technik

- **Backend:** Python + FastAPI (`app/`)
- **Datenbank:** SQLite (`db/schema.sql`, `db/seed.sql`)
- **Frontend:** statisches HTML/JS ohne Build-Schritt (`static/`)

Alle Geldbetraege werden als Ganzzahl in **Cent** gespeichert. Die Datenbank
liegt lokal unter `%LOCALAPPDATA%\finanz-dashboard\finanz.db` (nicht im Repo,
nicht in Git) und wird beim ersten Start automatisch aus Schema + Seed erzeugt.

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

## Wichtig zu den Daten

Die Buchungsdatenbank, Belege, Bank-CSVs und Backups werden **absichtlich nie**
nach GitHub synchronisiert (siehe `.gitignore` und Konzept Abschnitt 18).
Git synchronisiert nur Programm und Konzept – **nicht** den Datenbestand.
GitHub ist daher **kein Backup** der Buchungen; dafuer den lokalen
Backup-Weg (NAS/offline) nutzen.

## Naechste Schritte (laut Konzept 13.2)

1. Bank-CSV-Import mit Dublettenschutz und Kontostand-Abgleich
2. Belege hochladen und verknuepfen
3. Auswertungsgruppen und globale Kategoriegruppen in der Oberflaeche
4. Interaktive Diagramme mit Drill-down
5. Regelvorschlaege
6. PDF-/XLSX-Exportpakete
