# Einrichtung des Finanz-Dashboards auf diesem PC.
# Ausfuehren aus dem Projektordner:  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
#
# Schritte: Python finden -> venv anlegen -> Abhaengigkeiten installieren ->
#           instance\db_location.txt auf die NAS-Datei zeigen lassen.

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)   # Projekt-Wurzel (Skript liegt in scripts\)
Write-Host "== Finanz-Dashboard Einrichtung ==" -ForegroundColor Cyan
Write-Host "Ordner: $(Get-Location)"

# --- 1) Python finden (echte Installation, nicht den Windows-Store-Platzhalter) ---
$py = $null
foreach ($cand in @("py", "python")) {
    if (Get-Command $cand -ErrorAction SilentlyContinue) {
        try { & $cand --version *> $null; if ($LASTEXITCODE -eq 0) { $py = $cand; break } } catch {}
    }
}
$known = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
if (-not $py -and (Test-Path $known)) { $py = $known }
if (-not $py) {
    Write-Host "Python nicht gefunden." -ForegroundColor Yellow
    Write-Host "Bitte installieren und Skript erneut ausfuehren:"
    Write-Host "  winget install Python.Python.3.12 --scope user"
    exit 1
}
Write-Host "Python: $py"

# --- 2) venv anlegen ---
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Lege virtuelle Umgebung (.venv) an ..."
    & $py -m venv .venv
} else {
    Write-Host "venv existiert bereits."
}

# --- 3) Abhaengigkeiten ---
Write-Host "Installiere Abhaengigkeiten ..."
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt

# --- 4) DB-Speicherort ---
$cfg = "instance\db_location.txt"
if (Test-Path $cfg) {
    Write-Host "DB-Speicherort bereits gesetzt: $(Get-Content $cfg -Raw)"
} else {
    New-Item -ItemType Directory -Force -Path "instance" | Out-Null
    $default = "\\192.168.1.119\Daten\Hohenegg\IT. und IP-Adressen Hohenegg\home assistant und Codex\Finanz Dashboard Lois\Finanzdaten\finanz.db"
    Write-Host ""
    Write-Host "Wo liegt die gemeinsame Datenbank (finanz.db) auf dem NAS?"
    Write-Host "Standard (von jedem PC per UNC erreichbar):"
    Write-Host "  $default"
    $path = Read-Host "Pfad [Enter = Standard]"
    if ([string]::IsNullOrWhiteSpace($path)) { $path = $default }
    $full = Join-Path (Get-Location) "instance\db_location.txt"
    [System.IO.File]::WriteAllText($full, $path, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "Gespeichert in $cfg :" -ForegroundColor Green
    Write-Host "  $path"
}

Write-Host ""
Write-Host "Fertig. Starten mit Doppelklick auf  start.cmd" -ForegroundColor Green
