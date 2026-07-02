@echo off
title Khukra Launcher
cd /d "%~dp0"

echo Starting Khukra (API :8010 + UI :3020)...
echo Leave the two server windows open while using the app.
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup.ps1" -Dev

if errorlevel 1 (
    echo.
    echo Launch failed. Check errors above.
    pause
)
