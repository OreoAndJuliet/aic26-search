<#
.SYNOPSIS
    Packages the project into a self-installing ZIP for distribution.
.DESCRIPTION
    Creates AIC2026_Backend_<version>.zip that clients can extract and
    run setup.bat to install everything automatically.
    
    What gets included:
      - app/            (all backend source code, algorithms, services)
      - scripts/        (helper scripts and evaluation benchmarks)
      - tests/          (full automated test suite)
      - data/           (databases: landmarks, traffic signs, brands, vehicles, OCR database, metadata.json)
      - main.py, build_index.py, requirements.txt, pytest.ini
      - .env.example    (client copies this to .env and adds their API key)
      - setup.ps1       (applies tqdm hotfix + env setup, called by install.ps1)
      - install.ps1     (full one-shot installer)
      - setup.bat       (double-click entry point for clients)
      - start.bat       (start the server, supports --reset flag)
      - backup.ps1      (workspace and database backup script)
      - search.ps1      (unified CLI search tool)
      - GUIDE.md        (documentation)
      - PROJECT_INFRASTRUCTURE_MAP.md (infrastructure map)
    
    What gets excluded:
      - .venv/          (clients build their own)
      - static/         (keyframes - too large, clients bring their own data)
      - submission/     (local output)
      - error_log.txt   (local debug file)
      - __pycache__/
      - *.zip           (previous packages)
.EXAMPLE
    .\package_for_release.ps1
    .\package_for_release.ps1 -Version "2.1.0"
#>
param(
    [string]$Version = (Get-Date -Format "yyyyMMdd")
)

$ErrorActionPreference = 'Stop'
$root    = $PSScriptRoot
$distName = "AIC2026_Backend_$Version.zip"
$outPath  = Join-Path $root $distName

# Remove old package if exists
if (Test-Path $outPath) {
    Remove-Item $outPath -Force
    Write-Host "  Removed old: $distName" -ForegroundColor Gray
}

Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  AIC 2026 Backend - Packaging for Release  " -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  Output : $outPath" -ForegroundColor Gray
Write-Host ""

# Clean __pycache__ before packaging
Write-Host "  Cleaning temporary cache files..." -ForegroundColor Gray
Get-ChildItem -Path $root -Recurse -Filter "__pycache__" -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $root -Recurse -Filter "*.pyc" -File -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $root -Recurse -Filter ".pytest_cache" -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# Stage items
$stagingTemp = Join-Path $env:TEMP ("aic_release_staging_" + [System.Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $stagingTemp -Force | Out-Null

try {
    # 1. Directories to include
    $includeDirs = @("app", "scripts", "tests")
    foreach ($d in $includeDirs) {
        $src = Join-Path $root $d
        if (Test-Path $src) {
            Copy-Item -Path $src -Destination (Join-Path $stagingTemp $d) -Recurse -Force
            Write-Host "  + $d/" -ForegroundColor Green
        }
    }

    # 2. Database files in data/
    $dataStaging = Join-Path $stagingTemp "data"
    New-Item -ItemType Directory -Path $dataStaging -Force | Out-Null

    $dbFiles = @(
        "vietnam_landmarks.json",
        "traffic_signs_vietnam.json",
        "brands_and_retail.json",
        "vehicles_and_transport.json",
        "ocr_database.csv",
        "ocr_database.txt",
        "metadata.json"
    )
    foreach ($f in $dbFiles) {
        $fPath = Join-Path (Join-Path $root "data") $f
        if (Test-Path $fPath) {
            Copy-Item -Path $fPath -Destination (Join-Path $dataStaging $f) -Force
            Write-Host "  + data/$f" -ForegroundColor Cyan
        }
    }

    # 3. Root files to include
    $rootFiles = @(
        "main.py",
        "build_index.py",
        "requirements.txt",
        "pytest.ini",
        ".env.example",
        "setup.ps1",
        "install.ps1",
        "setup.bat",
        "start.bat",
        "start.ps1",
        "tune.ps1",
        "evaluate.ps1",
        "ingest.ps1",
        "test.ps1",
        "backup.ps1",
        "package_for_release.ps1",
        "search.ps1",
        "search_common.ps1",
        "search_kis.ps1",
        "search_vqa.ps1",
        "search_trake.ps1",
        "GUIDE.md",
        "PROJECT_INFRASTRUCTURE_MAP.md",
        "AIC2026_REQUIREMENTS_ANALYSIS.md",
        "docker-compose.yml",
        "Dockerfile"
    )
    foreach ($rf in $rootFiles) {
        $src = Join-Path $root $rf
        if (Test-Path $src) {
            Copy-Item -Path $src -Destination (Join-Path $stagingTemp $rf) -Force
            Write-Host "  + $rf" -ForegroundColor Green
        }
    }

    # Create the ZIP
    Write-Host ""
    Write-Host "  Compressing..." -ForegroundColor Cyan
    Compress-Archive -Path "$stagingTemp\*" -DestinationPath $outPath -Force

    # Report
    $sizeMB = [math]::Round((Get-Item $outPath).Length / 1MB, 2)
    Write-Host ""
    Write-Host "=============================================" -ForegroundColor Green
    Write-Host "  Done! Package created:" -ForegroundColor Green
    Write-Host "  $outPath ($sizeMB MB)" -ForegroundColor White
    Write-Host "=============================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Client instructions:" -ForegroundColor Yellow
    Write-Host "   1. Extract the ZIP anywhere" -ForegroundColor Gray
    Write-Host "   2. Copy .env.example to .env and add your GEMINI_API_KEY" -ForegroundColor Gray
    Write-Host "   3. Place your keyframes in static\keyframes\" -ForegroundColor Gray
    Write-Host "   4. Double-click setup.bat (or run .\install.ps1)" -ForegroundColor Gray
    Write-Host "   5. Double-click start.bat to launch the server" -ForegroundColor Gray
    Write-Host ""
} finally {
    if (Test-Path $stagingTemp) {
        Remove-Item -Path $stagingTemp -Recurse -Force -ErrorAction SilentlyContinue
    }
}
