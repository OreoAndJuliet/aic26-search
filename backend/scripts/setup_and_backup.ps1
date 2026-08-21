<#
.SYNOPSIS
    Professional automated setup and deployment script for AIC 2026 backend project.

.DESCRIPTION
    This script provides a complete end-to-end solution for:
    - Git repository cloning and setup
    - Environment validation and dependency installation
    - Docker container orchestration (Milvus + backend)
    - Database initialization and data indexing
    - Backup and recovery operations
    
    The script includes comprehensive error handling, rollback capabilities,
    progress tracking, and system validation to ensure reliable deployment.

.PARAMETER GitUrl
    Git repository URL to clone. If not specified, uses existing RepoRoot.

.PARAMETER RepoRoot
    Local path where the repository exists or will be cloned.
    Default: Parent directory of the scripts folder.

.PARAMETER DestinationRoot
    Backup destination directory for archives and snapshots.
    Default: D:\backups\project25

.PARAMETER Branch
    Git branch to clone. Default: main

.PARAMETER IncludeStatic
    Include static assets (keyframes/videos) in backup.

.PARAMETER IncludeVenv
    Include Python virtual environment in backup.

.PARAMETER Keep
    Number of backups to retain. Default: $script:totalSteps

.PARAMETER SkipMilvus
    Skip Milvus initialization and backup steps.

.PARAMETER SkipDocker
    Skip Docker operations entirely.

.PARAMETER NoInstall
    Skip Python package installation.

.PARAMETER NoBuild
    Skip FAISS index building.

.PARAMETER NoBackup
    Skip backup operations.

.PARAMETER SkipValidation
    Skip dataset validation (use if index already exists).

.PARAMETER MilvusWaitSeconds
    Maximum time to wait for Milvus health check. Default: 120

.PARAMETER Force
    Force operations without confirmation prompts.

.EXAMPLE
    # Clone from git and run complete setup
    .\scripts\setup_and_backup.ps1 -GitUrl "https://github.com/user/project25.git" -RepoRoot "D:\project25"

.EXAMPLE
    # Run setup on existing repository
    .\scripts\setup_and_backup.ps1 -RepoRoot "D:\project25"

.EXAMPLE
    # Quick setup without backups
    .\scripts\setup_and_backup.ps1 -RepoRoot "D:\project25" -NoBackup

.EXAMPLE
    # Development setup with Docker only
    .\scripts\setup_and_backup.ps1 -RepoRoot "D:\project25" -SkipMilvus -NoBackup

.NOTES
    Requirements:
    - PowerShell 5.1 or higher
    - Git (if cloning from repository)
    - Python 3.10+
    - Docker Desktop with Docker Compose
    - Sufficient disk space (20GB+ recommended)
    - Administrator privileges for some operations

    Author: Professional DevOps Script
    Version: 2.0.0
#>

[CmdletBinding()]
param(
    [string]$GitUrl,
    [string]$RepoRoot = (Resolve-Path "$PSScriptRoot\.." -ErrorAction SilentlyContinue).Path,
    [string]$DestinationRoot = (Join-Path $env:USERPROFILE "backups\aic_project"),
    [string]$Branch = "main",
    [switch]$IncludeStatic,
    [switch]$IncludeVenv,
    [int]$Keep = 5,
    [switch]$SkipMilvus,
    [switch]$SkipDocker,
    [switch]$NoInstall,
    [switch]$NoBuild,
    [switch]$NoBackup,
    [switch]$SkipValidation,
    [int]$MilvusWaitSeconds = 120,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
# $ProgressPreference = 'SilentlyContinue'  # Commented out to show progress bars

# Enhanced logging functions
function Write-Info($m){ 
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] [INFO] $m" -ForegroundColor Cyan 
    if ($VerbosePreference -eq 'Continue') { Add-Content -Path "$scriptDir\setup.log" -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [INFO] $m" -ErrorAction SilentlyContinue }
}

function Write-Warn($m){ 
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] [WARN] $m" -ForegroundColor Yellow 
    if ($VerbosePreference -eq 'Continue') { Add-Content -Path "$scriptDir\setup.log" -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [WARN] $m" -ErrorAction SilentlyContinue }
}

function Write-Err($m){ 
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] [ERROR] $m" -ForegroundColor Red 
    Add-Content -Path "$scriptDir\setup.log" -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [ERROR] $m" -ErrorAction SilentlyContinue
}

function Write-Success($m){ 
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] [SUCCESS] $m" -ForegroundColor Green 
    if ($VerbosePreference -eq 'Continue') { Add-Content -Path "$scriptDir\setup.log" -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [SUCCESS] $m" -ErrorAction SilentlyContinue }
}

function Write-Step($step, $total, $message){
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] [STEP $step/$total] $message" -ForegroundColor Magenta
    if ($VerbosePreference -eq 'Continue') { Add-Content -Path "$scriptDir\setup.log" -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [STEP $step/$total] $message" -ErrorAction SilentlyContinue }
}

function Show-Progress($activity, $status, $percent){
    if ($null -eq $percent) { $percent = 0 }
    Write-Progress -Activity $activity -Status $status -PercentComplete $percent
}

# Global variables for rollback
$script:rollbackActions = @()
# Total number of logical steps in this script — update if new steps are added
$script:totalSteps = 13
$script:currentStep = 0

function Add-RollbackAction($action){
    $script:rollbackActions += $action
}

function Invoke-Rollback(){
    if ($script:rollbackActions.Count -eq 0) { return }
    
    Write-Warn "Initiating rollback due to failure..."
    for ($i = $script:rollbackActions.Count - 1; $i -ge 0; $i--) {
        try {
            Write-Info "Executing rollback action: $($script:rollbackActions[$i].Description)"
            & $script:rollbackActions[$i].Action
        } catch {
            Write-Err "Rollback action failed: $_"
        }
    }
    Write-Err "Rollback completed. System may be in inconsistent state."
}

# Initialize log file
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$logFile = Join-Path $scriptDir "setup_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
"=== Setup Script Started $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Out-File -FilePath $logFile -Encoding UTF8

Write-Info "=== AIC 2026 Backend Setup Script v2.0 ==="
Write-Info "Log file: $logFile"
Write-Info "Configuration:"
Write-Info "  RepoRoot: $RepoRoot"
Write-Info "  DestinationRoot: $DestinationRoot"
Write-Info "  GitUrl: $(if ($GitUrl) { $GitUrl } else { 'Not specified (using existing)' })"
Write-Info "  Branch: $Branch"
Write-Info "  SkipDocker: $SkipDocker"
Write-Info "  SkipMilvus: $SkipMilvus"
Write-Info "  NoInstall: $NoInstall"
Write-Info "  NoBuild: $NoBuild"
Write-Info "  NoBackup: $NoBackup"
Write-Info "  SkipValidation: $SkipValidation"

# Resolve script paths
$backupRobo = Join-Path $scriptDir "backup_robo.ps1"
$backupMilvus = Join-Path $scriptDir "backup_milvus.ps1"
$restoreMilvus = Join-Path $scriptDir "restore_milvus.ps1"

try {
    # ============================================================================
    # STEP 1: Pre-flight System Checks
    # ============================================================================
    $script:currentStep = 1
    Write-Step $script:currentStep $script:totalSteps "Running pre-flight system checks"

    function Test-Command($command){
        try {
            $null = Get-Command $command -ErrorAction Stop
            return $true
        } catch {
            return $false
        }
    }

    $systemChecks = @{
        'Git' = Test-Command 'git'
        'Python' = Test-Command 'python'
        'Docker' = Test-Command 'docker'
        'PowerShell' = $PSVersionTable.PSVersion.Major -ge 5
    }

    $allChecksPassed = $true
    foreach ($check in $systemChecks.GetEnumerator()) {
        if ($check.Value) {
            Write-Info "  CHECK PASSED: $($check.Key) available"
        } else {
            Write-Warn "  CHECK FAILED: $($check.Key) not found"
            if ($check.Key -eq 'Git' -and $GitUrl) {
                Write-Err "Git is required when cloning from repository"
                $allChecksPassed = $false
            }
            if ($check.Key -eq 'Python') {
                Write-Err "Python is required for this project"
                $allChecksPassed = $false
            }
            if ($check.Key -eq 'Docker' -and -not $SkipDocker) {
                Write-Warn "Docker not found - will skip Docker operations"
                $SkipDocker = $true
            }
        }
    }

    if (-not $allChecksPassed) {
        throw "Required system checks failed. Please install missing dependencies."
    }

    # Check disk space
    $systemDrive = $env:SystemDrive
    $drive = Get-PSDrive -Name $systemDrive.Replace(':','')
    $freeSpaceGB = [math]::Round($drive.Free / 1GB, 2)
    Write-Info "  Available disk space: ${freeSpaceGB}GB"
    if ($freeSpaceGB -lt 20) {
        Write-Warn "Low disk space warning: Less than 20GB available"
    }

    Write-Success "Pre-flight checks completed"

        # One-time setup marker: if present and not forcing, stop early to avoid repeating heavy operations
        $setupMarker = Join-Path $RepoRoot '.setup_complete'
        if ((Test-Path $setupMarker) -and (-not $Force)) {
            Write-Info "Setup has already been completed (marker found at $setupMarker). Use -Force to re-run or remove the marker to run again."
            exit 0
        }

        # ============================================================================
        # STEP 2: Git Clone or Repository Validation
        # ============================================================================
        $script:currentStep = 2
        Write-Step $script:currentStep $script:totalSteps "Repository setup"

    if ($GitUrl) {
        if (Test-Path $RepoRoot) {
            if ($Force) {
                Write-Warn "Removing existing repository directory: $RepoRoot"
                Remove-Item -Path $RepoRoot -Recurse -Force
            } else {
                throw "Repository directory already exists: $RepoRoot. Use -Force to overwrite."
            }
        }

        Write-Info "Cloning repository from $GitUrl to $RepoRoot"
        $parentDir = Split-Path $RepoRoot -Parent
        if (-not (Test-Path $parentDir)) {
            New-Item -ItemType Directory -Path $parentDir -Force | Out-Null
        }

        $cloneArgs = @('clone', $GitUrl, $RepoRoot)
        if ($Branch -ne 'main') {
            $cloneArgs += '--branch', $Branch
        }

        & git @cloneArgs
        if ($LASTEXITCODE -ne 0) {
            throw "Git clone failed with exit code $LASTEXITCODE"
        }

        Add-RollbackAction @{
            Description = "Remove cloned repository"
            Action = { Remove-Item -Path $RepoRoot -Recurse -Force -ErrorAction SilentlyContinue }
        }

        Write-Success "Repository cloned successfully"
    } else {
        if (-not (Test-Path $RepoRoot)) {
            throw "Repository not found at $RepoRoot. Specify -GitUrl to clone or provide valid path."
        }
        Write-Info "Using existing repository at $RepoRoot"
    }

    # ============================================================================
    # STEP 3: Python Environment Setup
    # ============================================================================
    $script:currentStep = 3
    Write-Step $script:currentStep $script:totalSteps "Python environment setup"

    function Find-Python() {
        $cands = @('python','python3','python3.10','python3.11','python3.12')
        foreach ($c in $cands) {
            try { 
                $ver = & $c -c "import sys; print(str(sys.version_info.major) + '.' + str(sys.version_info.minor))"
                if ($LASTEXITCODE -eq 0) { 
                    $version = [version]$ver
                    if ($version -ge [version]"3.10") {
                        return $c
                    }
                } 
            } catch { }
        }
        return $null
    }

    $pythonCmd = Find-Python
    if (-not $pythonCmd) { 
        throw "Python 3.10+ not found on PATH. Please install Python 3.10 or higher." 
    }
    Write-Info "Using Python command: $pythonCmd"

    # Create virtual environment
    $venvPath = Join-Path $RepoRoot ".venv"
    $venvPython = Join-Path $venvPath "Scripts\python.exe"
    
    if (-not (Test-Path $venvPython)) {
        Write-Info "Creating virtualenv at $venvPath"
        & $pythonCmd -m venv $venvPath
        if ($LASTEXITCODE -ne 0) { 
            throw "Failed to create venv with exit code $LASTEXITCODE" 
        }

        Add-RollbackAction @{
            Description = "Remove virtual environment"
            Action = { Remove-Item -Path $venvPath -Recurse -Force -ErrorAction SilentlyContinue }
        }

        Write-Success "Virtualenv created"
    } else {
        Write-Info "Virtualenv already exists at $venvPath"
    }

    # Install dependencies
    function Invoke-PipInstall($venvPythonPath, $requirementsFile) {
        $maxAttempts = 3
        $tempDir = Join-Path $RepoRoot '.venv\pip_tmp'
        if (-not (Test-Path $tempDir)) { New-Item -ItemType Directory -Path $tempDir -Force | Out-Null }
        $env:PIP_NO_CACHE_DIR = '1'
        $env:TEMP = $tempDir
        $env:TMP = $tempDir

        for ($i = 1; $i -le $maxAttempts; $i++) {
            Write-Info "Pip install attempt $i/$maxAttempts"
            Show-Progress -Activity "Installing Python packages" -Status "Upgrading pip (attempt $i)" -PercentComplete 10
            & $venvPythonPath -m pip install --upgrade pip setuptools wheel --no-cache-dir
            if ($LASTEXITCODE -ne 0) {
                Write-Warn "pip upgrade returned exit code $LASTEXITCODE"
                if ($i -lt $maxAttempts) { Start-Sleep -Seconds 2; continue } else { throw "Failed to upgrade pip after $maxAttempts attempts" }
            }

            Show-Progress -Activity "Installing Python packages" -Status "Installing requirements (attempt $i)" -PercentComplete 30
            & $venvPythonPath -m pip install --no-cache-dir -r $requirementsFile
            if ($LASTEXITCODE -eq 0) {
                Write-Success "Pip install succeeded"
                return
            } else {
                Write-Warn "pip install returned exit code $LASTEXITCODE"
                if ($i -lt $maxAttempts) { Start-Sleep -Seconds 2; continue } else { throw "Failed to install requirements after $maxAttempts attempts" }
            }
        }
    }

    if (-not $NoInstall) {
        Write-Info "Upgrading pip and installing requirements"
        Show-Progress -Activity "Installing Python packages" -Status "Upgrading pip" -PercentComplete 10

        $requirementsPath = Join-Path $RepoRoot 'requirements.txt'
        if (-not (Test-Path $requirementsPath)) {
            throw "requirements.txt not found at $requirementsPath"
        }

        try {
            Invoke-PipInstall -venvPythonPath $venvPython -requirementsFile $requirementsPath
        } catch {
            throw "Failed to install requirements: $_"
        }

        Show-Progress -Activity "Installing Python packages" -Status "Completed" -PercentComplete 100
        Write-Success "Python dependencies installed"
    } else {
        Write-Warn "Skipping pip install as requested (-NoInstall)"
    }

    # ============================================================================
    # STEP 4: Environment Configuration Validation
    # ============================================================================
    $script:currentStep = 4
    Write-Step $script:currentStep $script:totalSteps "Environment configuration validation"

    $envExampleFile = Join-Path $RepoRoot '.env.example'
    $envFile = Join-Path $RepoRoot '.env'

    if (-not (Test-Path $envFile)) {
        if (Test-Path $envExampleFile) {
            Write-Info "Creating .env from .env.example"
            Copy-Item -Path $envExampleFile -Destination $envFile
            Write-Warn "Please review and configure $envFile with your API keys and settings"
        } else {
            Write-Warn "No .env.example found. Creating basic .env file"
            $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
            $envContent = @"
# AIC 2026 Backend Configuration
# Generated by setup script on $timestamp

# Database Configuration
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_COLLECTION=aic_vectors

# API Keys (configure these)
# GEMINI_API_KEY=your_gemini_api_key
# OPENAI_API_KEY=your_openai_api_key

# Model Configuration
TEXT_ENCODER_PROVIDER=sentence_transformers
CLIP_MODEL_NAME=sentence-transformers/clip-ViT-B-32
TRANSLATION_PROVIDER=google_gtx
CACHE_BACKEND=memory

# Performance
LATENCY_SLA_MS=1000
CLIP_WARMUP_ENABLED=true
"@
            $envContent | Out-File -FilePath $envFile -Encoding UTF8
        }
    } else {
        Write-Info "Environment file already exists at $envFile"
    }

    Write-Success "Environment configuration validated"

    # ============================================================================
    # STEP 5: Docker Setup and Initialization
    # ============================================================================
    $script:currentStep = 5
    Write-Step $script:currentStep $script:totalSteps "Docker setup and initialization"

    if (-not $SkipDocker) {
        # Check for docker-compose.yml
        $dockerComposePath = Join-Path $RepoRoot 'docker-compose.yml'
        if (-not (Test-Path $dockerComposePath)) {
            Write-Warn "docker-compose.yml not found. Skipping Docker operations."
            $SkipDocker = $true
        } else {
            Write-Info "Found docker-compose.yml"

            # Detect and restore from backup if available
            $packDir = Join-Path $RepoRoot 'pack'
            $milvusArchive = $null

            if (Test-Path $packDir) {
                # Check for dataset zip
                $datasetZip = Get-ChildItem -Path $packDir -Filter 'dataset_*.zip' -File -ErrorAction SilentlyContinue | 
                              Sort-Object LastWriteTime -Descending | Select-Object -First 1
                if ($datasetZip) {
                    Write-Info "Found dataset archive: $($datasetZip.FullName)"
                    $dataDir = Join-Path $RepoRoot 'data'
                    if ((-not (Test-Path $dataDir)) -or $Force) {
                        Write-Info "Extracting dataset into $dataDir"
                        Expand-Archive -Path $datasetZip.FullName -DestinationPath $dataDir -Force
                        Write-Success "Dataset extracted"
                    } else {
                        Write-Info "Data folder already exists; skip extraction (use -Force to overwrite)"
                    }
                }

                # Check for milvus snapshot
                $milvusArchive = Get-ChildItem -Path $packDir -Filter 'milvus_*.tgz' -File -ErrorAction SilentlyContinue | 
                                 Sort-Object LastWriteTime -Descending | Select-Object -First 1
            }

            # Also check DestinationRoot for milvus archive
            if (-not $milvusArchive) {
                if (Test-Path $DestinationRoot) {
                    $milvusArchive = Get-ChildItem -Path $DestinationRoot -Filter 'milvus_*.tgz' -File -ErrorAction SilentlyContinue | 
                                     Sort-Object LastWriteTime -Descending | Select-Object -First 1
                }
            }

            if ($milvusArchive -and -not $SkipMilvus) {
                Write-Info "Found Milvus snapshot: $($milvusArchive.FullName)"
                if (Test-Path $restoreMilvus) {
                    Write-Info "Restoring Milvus from snapshot"
                    & powershell -NoProfile -ExecutionPolicy Bypass -File $restoreMilvus -ArchivePath $milvusArchive.FullName -Force
                    if ($LASTEXITCODE -ne 0) { 
                        Write-Warn "Milvus restore returned $LASTEXITCODE; proceeding with fresh setup"
                    } else {
                        Write-Success "Milvus restored from snapshot"
                    }
                } else {
                    Write-Warn "restore_milvus.ps1 not found; cannot auto-restore Milvus"
                }
            }

            # Start Docker Compose
            Write-Info "Starting Docker Compose (detached)"
            Push-Location $RepoRoot
            try {
                Show-Progress -Activity "Docker operations" -Status "Starting containers" -PercentComplete 20
                
                & docker compose up -d
                if ($LASTEXITCODE -ne 0) { 
                    throw "docker compose up failed with exit code $LASTEXITCODE" 
                }

                Add-RollbackAction @{
                    Description = "Stop Docker containers"
                    Action = { 
                        Push-Location $RepoRoot
                        docker compose down
                        Pop-Location
                    }
                }

                Show-Progress -Activity "Docker operations" -Status "Containers started" -PercentComplete 100
                Write-Success "Docker Compose started successfully"
            } finally { 
                Pop-Location 
            }
        }
    } else {
        Write-Info "Skipping Docker operations as requested"
    }

    # ============================================================================
    # STEP 6: Milvus Server Health Check
    # ============================================================================
    $script:currentStep = 6
    Write-Step $script:currentStep $script:totalSteps "Milvus server connectivity check"

    if (-not $SkipMilvus -and -not $SkipDocker) {
        Write-Info "Checking Milvus server connectivity (timeout ${MilvusWaitSeconds}s)"
        $checkScript = Join-Path $scriptDir 'check_milvus_simple.py'
        
        if (Test-Path $checkScript) {
            $deadline = (Get-Date).AddSeconds($MilvusWaitSeconds)
            $ok = $false
            $attempt = 0
            $start = Get-Date

            while ((Get-Date) -lt $deadline) {
                $attempt++
                $elapsed = [math]::Round(((Get-Date) - $start).TotalSeconds, 0)
                if ($MilvusWaitSeconds -gt 0) { $percentComplete = [int](([double]$elapsed / [double]$MilvusWaitSeconds * 100)) } else { $percentComplete = 0 }
                if ($percentComplete -lt 0) { $percentComplete = 0 } elseif ($percentComplete -gt 100) { $percentComplete = 100 }
                Show-Progress -Activity "Milvus connectivity check" -Status "Attempt $attempt" -PercentComplete $percentComplete
                
                try {
                    Push-Location $RepoRoot
                    $env:PYTHONPATH = $RepoRoot
                    $healthOutput = & $venvPython $checkScript
                    if ($LASTEXITCODE -eq 0) { 
                        Write-Info $healthOutput
                        $ok = $true 
                        break 
                    }
                } catch { }
                finally { Pop-Location }
                
                Start-Sleep -Seconds 3
            }

            if ($ok) {
                Write-Success "Milvus server is running and accessible"
            } else {
                Write-Warn "Milvus server health check did not succeed within timeout. Proceeding anyway."
            }
        } else {
            Write-Warn "check_milvus_simple.py not found, skipping Milvus connectivity check"
        }
    } else {
        Write-Info "Skipping Milvus health check"
    }

    # ============================================================================
    # STEP 7: Data Preparation and Validation
    # ============================================================================
    $script:currentStep = 7
    Write-Step $script:currentStep $script:totalSteps "Data preparation and validation"

    # Ensure data directory exists
    $dataDir = Join-Path $RepoRoot 'data'
    if (-not (Test-Path $dataDir)) {
        Write-Info "Creating data directory: $dataDir"
        New-Item -ItemType Directory -Path $dataDir -Force | Out-Null
    }

    # Extract zip files from processed directory if they exist
    $processedDir = Join-Path $dataDir 'inbox\processed'
    $zipFiles = Get-ChildItem -Path $processedDir -Filter '*.zip' -ErrorAction SilentlyContinue
    
    if ($zipFiles) {
        Write-Info "Found $($zipFiles.Count) zip files in processed directory"
        Write-Info "Moving zips back to inbox for extraction..."
        
        $inboxDir = Join-Path $dataDir 'inbox'
        foreach ($zipFile in $zipFiles) {
            $destination = Join-Path $inboxDir $zipFile.Name
            if (Test-Path $destination) {
                Remove-Item $destination -Force
            }
            Move-Item -Path $zipFile.FullName -Destination $destination -Force
            Write-Info "  Moved $($zipFile.Name) to inbox"
        }
        
        # Run zip extraction script
        $extractScript = Join-Path $scriptDir 'extract_zips.py'
        if (Test-Path $extractScript) {
            Write-Info "Extracting keyframes and videos from zip files..."
            Push-Location $RepoRoot
            try {
                & $venvPython $extractScript
                if ($LASTEXITCODE -ne 0) {
                    Write-Warn "Zip extraction returned exit code $LASTEXITCODE"
                } else {
                    Write-Success "Zip extraction completed successfully"
                }
            } finally {
                Pop-Location
            }
        } else {
            Write-Warn "extract_zips.py not found, skipping zip extraction"
        }
    } else {
        Write-Info "No zip files found in processed directory"
    }

    # Skip dataset validation if we already have the index
    $indexPath = Join-Path $RepoRoot 'data\faiss_index.bin'
    $metadataPath = Join-Path $RepoRoot 'data\metadata.json'
    
    if ((Test-Path $indexPath) -and (Test-Path $metadataPath)) {
        Write-Info "FAISS index and metadata already exist, skipping dataset validation"
        Write-Success "Using existing data files"
    } else {
        # Validate dataset if script exists
        $validateScript = Join-Path $RepoRoot 'scripts\validate_dataset.py'
        if (Test-Path $validateScript) {
            Write-Info "Running dataset validation"
            Push-Location $RepoRoot
            try {
                & $venvPython -m scripts.validate_dataset
                if ($LASTEXITCODE -ne 0) {
                    Write-Warn "Dataset validation returned exit code $LASTEXITCODE"
                } else {
                    Write-Success "Dataset validation passed"
                }
            } finally {
                Pop-Location
            }
        } else {
            Write-Warn "Dataset validation script not found, skipping"
        }
    }

    # ============================================================================
    # STEP 8: Build FAISS Index
    # ============================================================================
    $script:currentStep = 8
    Write-Step $script:currentStep $script:totalSteps "Building FAISS index"

    if (-not $NoBuild) {
        $buildIndexPath = Join-Path $RepoRoot 'data\faiss_index.bin'
        $metadataPath = Join-Path $RepoRoot 'data\metadata.json'
        
        # Skip build if index and metadata already exist
        if ((Test-Path $buildIndexPath) -and (Test-Path $metadataPath)) {
            Write-Info "FAISS index and metadata already exist, skipping build step"
            Write-Success "Using existing FAISS index"
        } else {
            $buildIndexPath = Join-Path $RepoRoot 'build_index.py'
            if (Test-Path $buildIndexPath) {
                Write-Info "Building FAISS index via build_index.py"
                Push-Location $RepoRoot
                try {
                    Show-Progress -Activity "Building index" -Status "Processing vectors" -PercentComplete 10
                    & $venvPython $buildIndexPath
                    if ($LASTEXITCODE -ne 0) {
                        throw "build_index.py failed with exit code $LASTEXITCODE"
                    }
                    Show-Progress -Activity "Building index" -Status "Completed" -PercentComplete 100
                    Write-Success "FAISS index built successfully"
                } finally {
                    Pop-Location
                }
            } else {
                Write-Warn "build_index.py not found, skipping index build"
            }
        }
    } else {
        Write-Info "Skipping FAISS index build as requested (-NoBuild)"
    }

    # ============================================================================
    # STEP 9: Initialize and Sync Vectors to Milvus
    # ============================================================================
    $script:currentStep = 9
    Write-Step $script:currentStep $script:totalSteps "Initialize and sync vectors to Milvus"

    if (-not $SkipMilvus -and -not $SkipDocker) {
        $indexPath = Join-Path $RepoRoot 'data\faiss_index.bin'
        $metadataPath = Join-Path $RepoRoot 'data\metadata.json'
        $collection = if ($env:MILVUS_COLLECTION) { $env:MILVUS_COLLECTION } else { "aic_keyframes" }

        # Check if we have the required files
        if (-not (Test-Path $indexPath)) {
            Write-Warn "FAISS index not found at $indexPath, skipping Milvus operations"
        } elseif (-not (Test-Path $metadataPath)) {
            Write-Warn "Metadata not found at $metadataPath, skipping Milvus operations"
        } else {
            Write-Info "Found FAISS index and metadata, proceeding with Milvus setup"
            
            # Initialize Milvus collection using separate scripts
            Write-Info "Initializing Milvus collection '$collection'"
            $initScript = Join-Path $scriptDir 'init_milvus.py'
            
            if (Test-Path $initScript) {
                Push-Location $RepoRoot
                try {
                    $env:PYTHONPATH = $RepoRoot
                    & $venvPython $initScript --collection $collection
                    if ($LASTEXITCODE -ne 0) {
                        Write-Warn "Milvus initialization returned exit code $LASTEXITCODE"
                    } else {
                        Write-Success "Milvus collection initialized successfully"
                    }
                } finally {
                    Pop-Location
                }
            } else {
                Write-Warn "init_milvus.py not found, skipping collection initialization"
            }
            
            # Sync vectors to Milvus
            Write-Info "Syncing FAISS vectors to Milvus"
            $syncScript = Join-Path $scriptDir 'sync_milvus.py'
            
            if (Test-Path $syncScript) {
                Push-Location $RepoRoot
                try {
                    Show-Progress -Activity "Syncing vectors to Milvus" -Status "Processing vectors" -PercentComplete 10
                    $env:PYTHONPATH = $RepoRoot
                    & $venvPython $syncScript --index $indexPath --metadata $metadataPath --collection $collection
                    Show-Progress -Activity "Syncing vectors to Milvus" -Status "Completed" -PercentComplete 100
                    
                    if ($LASTEXITCODE -ne 0) {
                        Write-Warn "Milvus sync returned exit code $LASTEXITCODE"
                    } else {
                        Write-Success "Vectors synced to Milvus successfully"
                    }
                } finally {
                    Pop-Location
                }
            } else {
                Write-Warn "sync_milvus.py not found, skipping vector sync"
            }
        }
    } else {
        Write-Info "Skipping Milvus initialization and vector sync"
    }

    # ============================================================================
    # STEP 10: Verify Milvus Collection
    # ============================================================================
    $script:currentStep = 10
    Write-Step $script:currentStep $script:totalSteps "Verify Milvus collection and data"

    if (-not $SkipMilvus -and -not $SkipDocker) {
        $collection = if ($env:MILVUS_COLLECTION) { $env:MILVUS_COLLECTION } else { "aic_keyframes" }
        
        # Verify collection was created and has data
        $checkScript = Join-Path $scriptDir 'check_milvus.py'
        
        if (Test-Path $checkScript) {
            Write-Info "Verifying Milvus collection '$collection'"
            Push-Location $RepoRoot
            try {
                $env:PYTHONPATH = $RepoRoot
                $checkOutput = & $venvPython $checkScript --output json
                Write-Info $checkOutput
                
                if ($LASTEXITCODE -eq 0) {
                    Write-Success "Milvus collection verification passed"
                } else {
                    Write-Warn "Milvus collection verification failed, but setup will continue"
                }
            } finally {
                Pop-Location
            }
        } else {
            Write-Warn "check_milvus.py not found, skipping collection verification"
        }
    } else {
        Write-Info "Skipping Milvus collection verification"
    }

    # ============================================================================
    # STEP 11: Application Startup Test
    # ============================================================================
    $script:currentStep = 11
    Write-Step $script:currentStep $script:totalSteps "Application startup validation"

    if (-not $SkipDocker) {
        Write-Info "Testing application health endpoint"
        $maxAttempts = 30
        $attempt = 0
        $appHealthy = $false

        while ($attempt -lt $maxAttempts -and -not $appHealthy) {
            $attempt++
            try {
                $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
                if ($response.StatusCode -eq 200) {
                    $appHealthy = $true
                    Write-Success "Application health check passed"
                }
            } catch {
                Write-Info "Health check attempt $attempt failed (expected during startup)"
                Start-Sleep -Seconds 2
            }
        }

        if (-not $appHealthy) {
            Write-Warn "Application health check did not succeed within expected time"
        }
    } else {
        Write-Info "Skipping application health check"
    }

    # ============================================================================
    # STEP 12: Backup Operations
    # ============================================================================
    $script:currentStep = 12
    Write-Step $script:currentStep $script:totalSteps "Backup operations"

    if (-not $NoBackup) {
        # Ensure DestinationRoot exists
        if (-not (Test-Path $DestinationRoot)) { 
            New-Item -ItemType Directory -Path $DestinationRoot -Force | Out-Null 
        }

        # Milvus backup
        if (-not $SkipMilvus -and -not $SkipDocker -and (Test-Path $backupMilvus)) {
            Write-Info "Creating Milvus Docker-volume snapshot"
            & powershell -NoProfile -ExecutionPolicy Bypass -File $backupMilvus -BackupDir $DestinationRoot -VolumeName 'project25_milvus_data' -Keep $Keep
            if ($LASTEXITCODE -ne 0) { 
                Write-Warn "backup_milvus.ps1 reported non-zero exit ($LASTEXITCODE)" 
            } else {
                Write-Success "Milvus backup completed"
            }
        } elseif (-not $SkipMilvus) {
            Write-Warn "Milvus backup script not found at $backupMilvus; skipping Milvus snapshot"
        }

        # Repository backup
        Write-Info "Running Robocopy backup (host files)"
        $robocopyArgs = @(
            "-Source", $RepoRoot,
            "-DestinationRoot", $DestinationRoot,
            "-Keep", $Keep
        )
        if ($IncludeStatic) { $robocopyArgs += "-IncludeStatic" }
        if ($IncludeVenv) { $robocopyArgs += "-IncludeVenv" }

        & powershell -NoProfile -ExecutionPolicy Bypass -File $backupRobo @robocopyArgs
        if ($LASTEXITCODE -ne 0) { 
            Write-Warn "backup_robo.ps1 reported non-zero exit ($LASTEXITCODE)" 
        } else {
            Write-Success "Repository backup completed"
        }
    } else {
        Write-Info "Skipping backup operations as requested (-NoBackup)"
    }

    # ============================================================================
    # STEP 13: Final Validation and Summary
    # ============================================================================
    $script:currentStep = 13
    Write-Step $script:currentStep $script:totalSteps "Final validation and summary"

    Write-Success "=== Setup completed successfully ==="
    Write-Info "Summary:"
    Write-Info "  Repository: $RepoRoot"
    Write-Info "  Python venv: $venvPath"
    Write-Info "  Backup location: $DestinationRoot"
    
    if (-not $SkipDocker) {
        Write-Info "  Docker containers: Running"
        Write-Info "  Application: http://localhost:8000"
        Write-Info "  API docs: http://localhost:8000/docs"
    }

    Write-Info "Next steps:"
    Write-Info "  1. Review and configure .env file with your API keys"
    Write-Info "  2. Test the application: .\scripts\dev.ps1 serve"
    Write-Info "  3. Run tests: .\scripts\dev.ps1 test"
    Write-Info "  4. For monitoring, check the log file: $logFile"

    # Create a marker to indicate setup completed successfully (prevents accidental reruns)
    try {
        $setupMarker = Join-Path $RepoRoot '.setup_complete'
        $markerContent = "Setup completed on $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')`nRepository: $RepoRoot"
        $markerContent | Out-File -FilePath $setupMarker -Encoding UTF8 -Force
        Write-Info "Created setup marker: $setupMarker"
    } catch {
        Write-Warn "Failed to create setup marker file: $_"
    }

    exit 0

} catch {
    Write-Err "Setup failed: $_"
    Write-Err "Error details: $($_.ScriptStackTrace)"
    
    # Attempt rollback
    Invoke-Rollback
    
    exit 1
}
