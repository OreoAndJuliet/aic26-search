#Requires -Version 5.1
<#
.SYNOPSIS
    AIC 2026 - Global Installer
.DESCRIPTION
    Installs both Backend (Python) and Frontend (Node.js/npm) dependencies automatically.
#>

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "   AIC 2026 - FULL SYSTEM INSTALLER      " -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

$baseDir = $PSScriptRoot

# 1. Install Backend
Write-Host "`n[1/2] Installing Backend Dependencies..." -ForegroundColor Yellow
$backendDir = Join-Path $baseDir "backend"
if (Test-Path (Join-Path $backendDir "install.ps1")) {
    Set-Location $backendDir
    & .\install.ps1 -Force
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Backend installation failed!"
        exit 1
    }
} else {
    Write-Warning "Backend install.ps1 not found. Skipping backend installation."
}

# 2. Install Frontend
Write-Host "`n[2/2] Installing Frontend Dependencies..." -ForegroundColor Yellow
$frontendDir = Join-Path $baseDir "frontend"
if (Test-Path (Join-Path $frontendDir "package.json")) {
    Set-Location $frontendDir
    # Check if npm is installed
    if (Get-Command "npm" -ErrorAction SilentlyContinue) {
        npm install
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Frontend installation (npm install) failed!"
            exit 1
        }
    } else {
        Write-Warning "Node.js/npm is not installed. Please install Node.js to run the frontend."
    }
} else {
    Write-Warning "Frontend directory or package.json not found. Skipping frontend installation."
}

Write-Host "`n=========================================" -ForegroundColor Green
Write-Host "   INSTALLATION COMPLETED SUCCESSFULLY   " -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green
Write-Host "To start the system:"
Write-Host "  Backend: cd backend; .\start.ps1"
Write-Host "  Frontend: cd frontend; npm run dev"
