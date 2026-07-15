@echo off
title Finanz-Dashboard (auch am Handy erreichbar - Fenster offen lassen)
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Noch nicht eingerichtet. Bitte zuerst einmalig ausfuehren:
  echo    powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
  echo.
  pause
  exit /b 1
)

echo Starte Finanz-Dashboard fuer Zugriff aus dem Heimnetz/Tailscale ...
echo Am Handy oeffnen:  http://^<IP-dieses-PCs^>:8000
echo (IP anzeigen mit:  ipconfig ^| findstr IPv4)
echo Windows fragt beim ersten Mal nach Firewall-Freigabe - "Zulassen" waehlen.
echo Zum Beenden dieses Fenster schliessen.
echo.

start "" cmd /c "timeout /t 2 >nul & start """" http://127.0.0.1:8000"

rem 0.0.0.0 = erreichbar fuer andere Geraete im (Tailscale-)Netz
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
