@echo off
title AIC 2026 - All-In-One Data Ingest & Indexer
color 0b
echo =================================================================
echo        AIC 2026 SEARCH - 1-CLICK DATA INSTALLER
echo =================================================================
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_data.ps1"
pause
