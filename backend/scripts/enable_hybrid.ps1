<#
Automate enabling Milvus hybrid retrieval end-to-end.

Usage (from project root):
  .\scripts\enable_hybrid.ps1

Options (PowerShell parameters):
  -RecreateMilvus    : Recreate Milvus collection during sync (pass through to dev.ps1 sync-milvus)
  -MilvusBatchSize   : Batch size for sync-milvus (default 512)
  -StartServer       : Start the backend server after enabling hybrid
  -ServerPort        : Port for server (default 8000)
  -NoReload          : Pass -NoReload to dev.ps1 serve to disable autoreload

Notes:
- This script uses .\scripts\dev.ps1 to start docker/milvus and to run the sync command.
- It will run the check_milvus.py script to validate the collection before toggling VECTOR_BACKEND in .env.
- It creates a backup of .env as .env.bak.<timestamp> before editing.
- Run inside PowerShell with appropriate permissions and ensure Docker is running if you intend to start Milvus.
#>

[CmdletBinding()]
param(
    [switch]$RecreateMilvus,
    [int]$MilvusBatchSize = 512,
    [switch]$StartServer,
    [int]$ServerPort = 8000,
    [switch]$NoReload
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $ProjectRoot

function Write-Info($msg) { Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Write-Err($msg) { Write-Host "[ERROR] $msg" -ForegroundColor Red }
function Write-Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }

# helper to run dev.ps1 subcommands
function Invoke-DevPs1([string[]]$args, [string]$label = "dev") {
    # Prefer pwsh if available; fallback to powershell.exe
    $shell = 'pwsh'
    if (-not (Get-Command $shell -ErrorAction SilentlyContinue)) { $shell = 'powershell.exe' }
    $cmdArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', "& '$ProjectRoot\\scripts\\dev.ps1' $($args -join ' ')")
    Write-Info ("Running dev.ps1 {0}: {1}" -f $label, ($args -join ' '))
    $proc = Start-Process -FilePath $shell -ArgumentList $cmdArgs -NoNewWindow -Wait -PassThru
    if ($proc.ExitCode -ne 0) { throw ("dev.ps1 {0} failed with exit code {1}" -f $label, $proc.ExitCode) }
}

# 1. Start Milvus via docker
Write-Info "Starting Milvus via Docker (dev.ps1 docker -Expand -DockerAction milvus)"
try {
    $dockerArgs = @('docker', '-Expand', '-DockerAction', 'milvus')
    if ($true) { $dockerArgs += '-DockerBuild' }
    Invoke-DevPs1 -args $dockerArgs -label 'docker/milvus'
} catch {
    Write-Err "Failed to start Milvus via dev.ps1 docker: $_"
    throw
}

# 2. Sync Milvus (FAISS -> Milvus)
try {
    Write-Info "Syncing FAISS index to Milvus (dev.ps1 sync-milvus)"
    $syncArgs = @('sync-milvus', '-Expand', '-MilvusBatchSize', $MilvusBatchSize)
    if ($RecreateMilvus) { $syncArgs += '-RecreateMilvus' }
    Invoke-DevPs1 -args $syncArgs -label 'sync-milvus'
} catch {
    Write-Err "Failed to sync Milvus: $_"
    throw
}

# 3. Run check_milvus.py to validate
Write-Info "Running scripts/check_milvus.py to validate Milvus collection"
$pythonExe = (Join-Path $ProjectRoot 'venv\Scripts\python.exe')
if (-not (Test-Path $pythonExe)) { $pythonExe = 'python' }
$checkCmd = @($pythonExe, 'scripts/check_milvus.py')
$proc = Start-Process -FilePath $checkCmd[0] -ArgumentList $checkCmd[1..($checkCmd.Length-1)] -NoNewWindow -Wait -PassThru -RedirectStandardOutput "$(Join-Path $ProjectRoot 'scripts\check_milvus.out.json')" -RedirectStandardError "$(Join-Path $ProjectRoot 'scripts\check_milvus.err.log')"
$outFile = Join-Path $ProjectRoot 'scripts\check_milvus.out.json'
if ($proc.ExitCode -ne 0) {
    Write-Err "Milvus health-check failed (exit $($proc.ExitCode)). See $outFile and scripts\check_milvus.err.log for details."
    Get-Content $outFile -ErrorAction SilentlyContinue | Write-Host
    throw "Milvus health check failed"
}
Write-Info "Milvus health-check passed. Output:"
Get-Content $outFile -Raw | Write-Host

# 4. Backup .env and update VECTOR_BACKEND to hybrid
$envPath = Join-Path $ProjectRoot '.env'
if (-not (Test-Path $envPath)) {
    Write-Warn ".env not found in project root. Creating from .env.example"
    Copy-Item -Path (Join-Path $ProjectRoot '.env.example') -Destination $envPath -Force
}
$bak = Join-Path $ProjectRoot ('.env.bak.' + (Get-Date -Format 'yyyyMMddHHmmss'))
Copy-Item $envPath $bak -Force
Write-Info ".env backed up to $bak"

# Read and update
$content = Get-Content $envPath -Raw
if ($content -match '^(?m)\s*VECTOR_BACKEND\s*=\s*') {
    $content = [regex]::Replace($content, '^(?m)\s*VECTOR_BACKEND\s*=\s*.*$', "VECTOR_BACKEND=hybrid")
} else {
    $content += "`nVECTOR_BACKEND=hybrid`n"
}
Set-Content -Path $envPath -Value $content -Encoding UTF8
Write-Info ".env updated with VECTOR_BACKEND=hybrid"

# 5. Optionally start the server
if ($StartServer) {
    Write-Info "Starting backend server via dev.ps1 serve"
    $serveArgs = @('serve', '-Expand', '-Port', $ServerPort)
    if ($NoReload) { $serveArgs += '-NoReload' }
    # Start in a new window so this script can finish
    $psExe = 'pwsh'
    if (-not (Get-Command $psExe -ErrorAction SilentlyContinue)) { $psExe = 'powershell.exe' }
    # Build argument list explicitly to avoid format-string brace issues
    $commandString = "& '$ProjectRoot\scripts\dev.ps1' $($serveArgs -join ' '); if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }"
    $argsList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', $commandString)
    Write-Info "Launching serve in a new PowerShell process"
    Start-Process -FilePath $psExe -ArgumentList $argsList
    Write-Info "Server start command launched (background)."
}

Write-Info "Hybrid enablement completed successfully. Verify by running a sample KIS query or viewing /health endpoint."
