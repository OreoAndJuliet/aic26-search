# Complete End-to-End Deployment Script
# This script handles everything from checking Docker to running tests

param(
    [string]$Source = $PSScriptRoot,
    [string]$DestinationRoot = (Join-Path $env:USERPROFILE "backups\aic_deployment"),
    [switch]$SkipCopy,
    [switch]$SkipTests,
    [switch]$MockMode
)

$ErrorActionPreference = "Stop"

function Write-Info($m){ Write-Host "[INFO] $m" -ForegroundColor Cyan }
function Write-Warn($m){ Write-Host "[WARN] $m" -ForegroundColor Yellow }
function Write-Err($m){ Write-Host "[ERROR] $m" -ForegroundColor Red }
function Write-Success($m){ Write-Host "[SUCCESS] $m" -ForegroundColor Green }

# Step 1: Copy project using robocopy
if (-not $SkipCopy) {
    Write-Info "=== Step 1: Copying Project Files ==="
    
    $stamp = Get-Date -Format "yyyy-MM-dd_HHmm"
    $destination = Join-Path $DestinationRoot $stamp
    New-Item -ItemType Directory -Force -Path $destination | Out-Null
    
    Write-Info "Copying from $Source to $destination"
    Write-Info "This may take several minutes..."
    
    # Use robocopy with include venv and static for full copy
    $robocopyArgs = @(
        $Source,
        $destination,
        "/E",
        "/Z",
        "/FFT",
        "/R:3",
        "/W:5",
        "/NP",
        "/NDL",
        "/NFL",
        "/LOG:$destination\robocopy.log"
    )
    
    & robocopy @robocopyArgs
    $exitCode = $LASTEXITCODE
    
    if ($exitCode -ge 8) {
        Write-Err "Robocopy failed with exit code $exitCode"
        throw "Copy operation failed"
    }
    
    Write-Success "Project copied successfully to $destination"
    $projectPath = $destination
} else {
    Write-Info "Skipping copy step"
    # Use the most recent backup folder
    $backups = Get-ChildItem -Path $DestinationRoot | Where-Object { $_.PsIsContainer } | Sort-Object LastWriteTime -Descending
    if ($backups.Count -eq 0) {
        throw "No backup folders found in $DestinationRoot"
    }
    $projectPath = $backups[0].FullName
    Write-Info "Using existing backup: $projectPath"
}

Write-Info "Project location: $projectPath"

# Step 2: Set up Python virtual environment
Write-Info "=== Step 2: Setting Up Python Environment ==="
$venvPath = Join-Path $projectPath ".venv"
$pythonPath = Join-Path $venvPath "Scripts\python.exe"

# Check if venv is valid by checking for python.exe
$venvValid = Test-Path $pythonPath

if ((-not (Test-Path $venvPath)) -or (-not $venvValid)) {
    Write-Info "Creating Python virtual environment..."
    if (Test-Path $venvPath) {
        Remove-Item -Path $venvPath -Recurse -Force
    }
    python -m venv $venvPath
    Write-Success "Virtual environment created"
} else {
    Write-Info "Virtual environment already exists and is valid"
}

# Activate venv and install dependencies
Write-Info "Installing Python dependencies..."
& $pythonPath -m pip install --upgrade pip
$depInstallResult = & $pythonPath -m pip install -r (Join-Path $projectPath "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    Write-Warn "Dependency installation had issues, but continuing..."
    Write-Info "Output: $depInstallResult"
} else {
    Write-Success "Dependencies installed"
}

# Step 3: Configure environment
Write-Info "=== Step 3: Configuring Environment ==="

# Copy .env.example to .env
$envExample = Join-Path $projectPath ".env.example"
$envFile = Join-Path $projectPath ".env"

if (-not (Test-Path $envFile)) {
    Copy-Item $envExample $envFile
    Write-Info "Created .env from .env.example"
    
    # Keep hybrid mode for Docker deployment
    Write-Info "Configuring for hybrid retrieval mode (Docker + Milvus)"
    
    # If mock mode requested, override the setting
    if ($MockMode) {
        (Get-Content $envFile) -replace "AI_PROVIDER_MODE=real", "AI_PROVIDER_MODE=mock" | Set-Content $envFile
        Write-Info "Set AI_PROVIDER_MODE=mock for testing"
    }
} else {
    Write-Info ".env file already exists, skipping configuration"
}

# Step 4: Start Docker Desktop if needed
Write-Info "=== Step 4: Starting Docker Desktop ==="

$dockerStarted = $false
$maxDockerAttempts = 3
$dockerAttempt = 0

while ($dockerAttempt -lt $maxDockerAttempts) {
    $dockerAttempt++
    Write-Info "Docker check attempt $dockerAttempt/$maxDockerAttempts"
    
    try {
        docker version 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Docker is running"
            $dockerStarted = $true
            break
        }
    } catch {
        Write-Warn "Docker not available, attempting to start..."
    }
    
    # Try to start Docker Desktop - check common installation paths
    $dockerDesktopPaths = @(
        "C:\Program Files\Docker\Docker\Docker Desktop.exe",
        "C:\Program Files\Docker\Docker\Docker Desktop",
        "${env:LOCALAPPDATA}\Docker\Docker Desktop\Docker Desktop.exe"
    )
    
    $dockerDesktopPath = $null
    foreach ($path in $dockerDesktopPaths) {
        if (Test-Path $path) {
            $dockerDesktopPath = $path
            break
        }
    }
    
    if ($dockerDesktopPath) {
        Write-Info "Starting Docker Desktop from: $dockerDesktopPath"
        Start-Process -FilePath $dockerDesktopPath
        Write-Info "Waiting for Docker Desktop to start (60 seconds)..."
        Start-Sleep -Seconds 60
    } else {
        Write-Err "Docker Desktop not found at $dockerDesktopPath"
        throw "Please install Docker Desktop to proceed with this setup"
    }
}

if (-not $dockerStarted) {
    throw "Failed to start Docker Desktop after $maxDockerAttempts attempts. Please start it manually."
}

# Step 5: Initialize Milvus
Write-Info "=== Step 5: Initializing Milvus ==="

Write-Info "Starting Docker Compose for Milvus..."
Set-Location $projectPath
docker-compose up -d milvus

Write-Info "Waiting for Milvus to start (60 seconds)..."
Start-Sleep -Seconds 60

Write-Info "Initializing Milvus collection..."
& $pythonPath -m scripts.init_milvus

Write-Info "Syncing data to Milvus..."
& $pythonPath -m scripts.sync_milvus --batch-size 512

Write-Success "Milvus initialized and synced"

# Step 6: Start backend
Write-Info "=== Step 6: Starting Backend ==="

Write-Info "Building and starting Docker Compose backend..."
docker-compose up --build -d backend

Write-Info "Waiting for backend to start (30 seconds)..."
Start-Sleep -Seconds 30

# Check if backend is running
try {
    Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -Method Get -TimeoutSec 10 | Out-Null
    Write-Success "Backend is running and healthy"
} catch {
    Write-Err "Backend health check failed"
    Write-Info "Check Docker logs: docker-compose logs backend"
    throw "Backend did not start properly"
}

# Step 7: Run tests
if (-not $SkipTests) {
    Write-Info "=== Step 7: Running Tests ==="
    
    $testScripts = @(
        "tests\test_kis_quick.ps1",
        "tests\test_trake_quick.ps1"
    )
    
    if (-not $MockMode) {
        $testScripts += "tests\test_vqa_quick.ps1"
    } else {
        Write-Info "Skipping VQA test (mock mode enabled)"
    }
    
    foreach ($testScript in $testScripts) {
        $testPath = Join-Path $projectPath $testScript
        if (Test-Path $testPath) {
            Write-Info "Running test: $testScript"
            Set-Location $projectPath
            & $testPath
        } else {
            Write-Warn "Test script not found: $testPath"
        }
    }
    
    Write-Success "All tests completed"
} else {
    Write-Info "Skipping tests"
}

Write-Info "=== Complete Deployment and Testing Finished ==="
Write-Info "Project location: $projectPath"
Write-Info "Backend: http://127.0.0.1:8000"
Write-Info "API Docs: http://127.0.0.1:8000/docs"
Write-Info ""
Write-Info "To run additional tests manually:"
Write-Host "  cd $projectPath"
Write-Host "  .\tests\test_kis_evaluation.ps1"
Write-Host "  .\tests\test_trake_evaluation.ps1"