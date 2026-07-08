@echo off
title Finanz-Dashboard  (Server laeuft - dieses Fenster offen lassen)
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Noch nicht eingerichtet.
  echo Bitte zuerst einmalig ausfuehren:
  echo    powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
  echo.
  pause
  exit /b 1
)

echo Starte Finanz-Dashboard ... Browser oeffnet sich gleich.
echo Zum Beenden dieses Fenster schliessen.
echo.

rem Browser nach kurzer Wartezeit oeffnen (Server braucht ~1-2 Sekunden)
start "" cmd /c "timeout /t 2 >nul & start """" http://127.0.0.1:8000"

rem Server starten (blockiert - haelt dieses Fenster offen)
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
