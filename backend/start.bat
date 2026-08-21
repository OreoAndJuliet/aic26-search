@echo off
setlocal enabledelayedexpansion
chcp 65001 > nul
powershell -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
if %errorlevel% neq 0 (
    echo Process ended with code %errorlevel%.
)
