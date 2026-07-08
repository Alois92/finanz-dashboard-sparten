# Einrichtung auf einem weiteren PC (z. B. Heim-PC)

Der Klon bringt das **Programm** — deine **Buchungen liegen NICHT in Git**, sondern
in der Datei `finanz.db` auf dem NAS. Beide PCs zeigen auf **dieselbe** NAS-Datei.

## Einmalig einrichten

```powershell
# 1) Repo holen
git clone https://github.com/Alois92/finanz-dashboard-sparten.git
cd finanz-dashboard-sparten

# 2) Einrichten (Python-venv, Abhaengigkeiten, DB-Pfad)
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
#   Falls Python fehlt:  winget install Python.Python.3.12 --scope user
```

Das Setup-Skript fragt nach dem Pfad zur `finanz.db` auf dem NAS und schreibt ihn
nach `instance\db_location.txt`. Standard (von jedem PC erreichbar):
`\\192.168.1.119\Daten\...\Finanz Dashboard Lois\Finanzdaten\finanz.db`

## Starten

Doppelklick auf **`start.cmd`** → Server startet, Browser oeffnet
`http://127.0.0.1:8000`. Fenster offen lassen, solange du arbeitest.

## Taeglicher Ablauf (Code synchron halten)

```powershell
git pull                              # vor Arbeitsbeginn: neuesten Programmstand holen
# ... arbeiten ...
git add -A
git commit -m "kurze Beschreibung"    # Code-Aenderungen sichern
git push                              # auf GitHub hochladen
```

## Wichtig

- **GitHub ist kein Backup deiner Buchungen** — nur des Programms.
  Sichere die NAS-Datei `finanz.db` separat (NAS-Snapshot / Offline-Kopie).
- **Nur ein PC gleichzeitig schreiben.** SQLite auf dem Netzlaufwerk ist fuer
  Einzelnutzer ausgelegt; nacheinander ist ok, gleichzeitiges Buchen kann die DB
  beschaedigen.
