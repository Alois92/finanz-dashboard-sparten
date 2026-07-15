# Richtet den automatischen Start des Finanz-Dashboards bei der Windows-
# Anmeldung ein (Aufgabenplanung). Einmalig als normaler Benutzer ausfuehren:
#   powershell -ExecutionPolicy Bypass -File scripts\autostart-einrichten.ps1
# Entfernen:
#   powershell -ExecutionPolicy Bypass -File scripts\autostart-einrichten.ps1 -Entfernen
param([switch]$Entfernen)

$name = "Finanz-Dashboard"
$projekt = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projekt ".venv\Scripts\python.exe"

if ($Entfernen) {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Autostart '$name' entfernt."
    exit 0
}

if (-not (Test-Path $python)) {
    Write-Host "Fehler: .venv fehlt. Zuerst scripts\setup.ps1 ausfuehren." -ForegroundColor Red
    exit 1
}

$aktion = New-ScheduledTaskAction -Execute $python `
    -Argument "-m uvicorn app.main:app --host 127.0.0.1 --port 8000" `
    -WorkingDirectory $projekt
$ausloeser = New-ScheduledTaskTrigger -AtLogOn
$einstellungen = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName $name -Action $aktion -Trigger $ausloeser `
    -Settings $einstellungen -Description "Startet das Finanz-Dashboard bei der Anmeldung" -Force | Out-Null

Write-Host "Autostart eingerichtet: '$name' startet das Dashboard bei jeder Anmeldung."
Write-Host "Hinweis: Fuer Handy-Zugriff im Skript '--host 127.0.0.1' durch '--host 0.0.0.0' ersetzen."
Start-ScheduledTask -TaskName $name
Write-Host "Dashboard gestartet: http://127.0.0.1:8000"
