@echo off
echo ===================================================
echo     AIC 2026 Backend - Quick Setup
echo ===================================================
echo.
echo This will run the installation script.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
echo.
pause
