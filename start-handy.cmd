@echo off
title Hohenegg Finanzstudio

echo Oeffne das private Hohenegg Finanzstudio ...
echo.
echo Voraussetzung:
echo   Tailscale muss auf diesem Geraet verbunden sein.
echo.
echo Adresse:
echo   https://finanz.tailb1b087.ts.net
echo.

start "" "https://finanz.tailb1b087.ts.net"

echo Falls sich die Seite nicht oeffnet, zuerst Tailscale einschalten.
timeout /t 8 >nul
