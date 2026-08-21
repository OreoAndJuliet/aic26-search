<#
.SYNOPSIS
    AIC 2026 Comprehensive Workspace & Database Backup Utility.
.DESCRIPTION
    Creates a timestamped backup archive containing all source code, encyclopedic databases,
    OCR indexes, landmarks, traffic signs, brand catalogs, test suites, and documentation.
.PARAMETER Destination
    Target directory for backup archives. Default is D:\ (parent directory) or current root.
.PARAMETER IncludeFullData
    If specified, also includes FAISS vector binary indexes (faiss_index.bin) and metadata.
.EXAMPLE
    .\backup.ps1
    .\backup.ps1 -IncludeFullData
#>
param(
    [string]$Destination = "..",
    [switch]$IncludeFullData,
    [string]$Tag = ""
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$suffix = if ($Tag) { "_$Tag" } else { "" }
$backupFileName = "AIC2026_Backup_$timestamp$suffix.zip"

$destDir = [System.IO.Path]::GetFullPath((Join-Path $root $Destination))
if (-not (Test-Path $destDir)) {
    New-Item -ItemType Directory -Path $destDir -Force | Out-Null
}
$outZipPath = Join-Path $destDir $backupFileName

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  AIC 2026 - Comprehensive Workspace & Database Backup    " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  Source Directory : $root" -ForegroundColor Gray
Write-Host "  Backup Archive   : $outZipPath" -ForegroundColor White
Write-Host ""

# 1. Clean temporary files before backup
Write-Host "  [1/4] Cleaning temporary cache files..." -ForegroundColor Gray
Get-ChildItem -Path $root -Recurse -Filter "__pycache__" -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $root -Recurse -Filter "*.pyc" -File -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $root -Recurse -Filter ".pytest_cache" -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# 2. Stage backup files
Write-Host "  [2/4] Staging source code, scripts & databases..." -ForegroundColor Gray
$stagingTemp = Join-Path $env:TEMP ("aic_backup_staging_" + [System.Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $stagingTemp -Force | Out-Null

try {
    # Core directories
    $copyDirs = @("app", "scripts", "tests")
    foreach ($d in $copyDirs) {
        $src = Join-Path $root $d
        if (Test-Path $src) {
            Copy-Item -Path $src -Destination (Join-Path $stagingTemp $d) -Recurse -Force
            Write-Host "    + Directory: $d" -ForegroundColor Green
        }
    }

    # Data directory (Crucial: Database files)
    $dataStaging = Join-Path $stagingTemp "data"
    New-Item -ItemType Directory -Path $dataStaging -Force | Out-Null

    $dbFiles = @(
        "vietnam_landmarks.json",
        "traffic_signs_vietnam.json",
        "brands_and_retail.json",
        "vehicles_and_transport.json",
        "ocr_database.csv",
        "ocr_database.txt",
        "metadata.json",
        "open_world_codabench_benchmark.json",
        "mock_contest_ground_truth.json"
    )
    foreach ($f in $dbFiles) {
        $fPath = Join-Path (Join-Path $root "data") $f
        if (Test-Path $fPath) {
            Copy-Item -Path $fPath -Destination (Join-Path $dataStaging $f) -Force
            Write-Host "    + Database: data\$f" -ForegroundColor Cyan
        }
    }

    # If full data requested, copy vector index & maps
    if ($IncludeFullData) {
        $fullDataItems = @("faiss_index.bin", "map_keyframes", "media_info", "gazetteers")
        foreach ($item in $fullDataItems) {
            $src = Join-Path (Join-Path $root "data") $item
            if (Test-Path $src) {
                Copy-Item -Path $src -Destination (Join-Path $dataStaging $item) -Recurse -Force
                Write-Host "    + Full Data: data\$item" -ForegroundColor DarkCyan
            }
        }
    }

    # Root scripts and configs
    $rootFiles = @(
        "main.py",
        "build_index.py",
        "requirements.txt",
        "pytest.ini",
        ".env",
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
        "README.md",
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
            Write-Host "    + File: $rf" -ForegroundColor Green
        }
    }

    # 3. Create ZIP Archive
    Write-Host "  [3/4] Compressing backup archive..." -ForegroundColor Gray
    Compress-Archive -Path "$stagingTemp\*" -DestinationPath $outZipPath -Force

    # 4. Verification & Summary
    $sizeMB = [math]::Round((Get-Item $outZipPath).Length / 1MB, 2)
    Write-Host "  [4/4] Verification successful!" -ForegroundColor Green
    Write-Host ""
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host "  BACKUP COMPLETED SUCCESSFULLY                           " -ForegroundColor Green
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host "  Location : $outZipPath" -ForegroundColor White
    Write-Host "  Size     : $sizeMB MB" -ForegroundColor White
    Write-Host "  Databases Included:" -ForegroundColor Yellow
    foreach ($f in $dbFiles) {
        Write-Host "    - data\$f" -ForegroundColor Gray
    }
    Write-Host ""
} finally {
    if (Test-Path $stagingTemp) {
        Remove-Item -Path $stagingTemp -Recurse -Force -ErrorAction SilentlyContinue
    }
}
