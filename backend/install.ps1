#Requires -Version 5.1
<#
.SYNOPSIS
    AIC 2026 Backend — one-shot project installer.

.DESCRIPTION
    Sets up the AIC 2026 Backend (Python FastAPI + FAISS + optional Milvus via Docker):
      • Validates Python >= 3.10
      • Creates and populates a local .venv
      • Installs pip dependencies from requirements.txt
      • Bootstraps .env from .env.example
      • Creates required data / static / submission directories
      • Optionally starts the Milvus Docker stack
      • Optionally builds the FAISS index from pre-computed feature files
    Run with -Force to skip interactive prompts.

.PARAMETER PythonExe
    Path or name of the Python executable to use. Defaults to 'python'.

.PARAMETER WithDocker
    Switch. Start the Milvus Docker Compose stack after setup.

.PARAMETER WithMilvus
    Switch. Alias for -WithDocker; also sets VECTOR_BACKEND=hybrid in .env.

.PARAMETER Force
    Switch. Skip all interactive confirmation prompts.

.PARAMETER SkipIndex
    Switch. Do not attempt to build the FAISS index (build_index.py).

.EXAMPLE
    .\install.ps1
    .\install.ps1 -WithMilvus -Force
    .\install.ps1 -PythonExe "C:\Python312\python.exe" -SkipIndex
#>

[CmdletBinding()]
param(
    [string]  $PythonExe  = 'python',
    [switch]  $WithDocker,
    [switch]  $WithMilvus,
    [switch]  $Force,
    [switch]  $SkipIndex
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# --- Constants ----------------------------------------------------------------
$TOTAL_STEPS = 8
$ROOT        = $PSScriptRoot          # Project root (where this script lives)
$VENV_DIR    = Join-Path $ROOT '.venv'
$VENV_PY     = Join-Path $VENV_DIR 'Scripts\python.exe'
$VENV_PIP    = Join-Path $VENV_DIR 'Scripts\pip.exe'

# --- Colour helpers -----------------------------------------------------------

function Write-Step {
    param([int]$Num, [string]$Message)
    Write-Host "`n  [$Num/$TOTAL_STEPS] $Message" -ForegroundColor Cyan
}

function Write-Ok   { param([string]$Message) Write-Host "  +  $Message" -ForegroundColor Green  }
function Write-Warn { param([string]$Message) Write-Host "  !  $Message" -ForegroundColor Yellow }
function Write-Err  { param([string]$Message) Write-Host "  x  $Message" -ForegroundColor Red    }
function Write-Info { param([string]$Message) Write-Host "     $Message" -ForegroundColor Gray   }

# --- Banner -------------------------------------------------------------------
Write-Host ''
Write-Host '================================================================' -ForegroundColor Magenta
Write-Host '         AIC 2026 Backend -- Project Installer                 ' -ForegroundColor Magenta
Write-Host '================================================================' -ForegroundColor Magenta
Write-Host ''
Write-Info "Project root : $ROOT"
Write-Info "Python exe   : $PythonExe"
Write-Info "WithDocker   : $($WithDocker -or $WithMilvus)"
Write-Info "WithMilvus   : $WithMilvus"
Write-Info "Force        : $Force"
Write-Info "SkipIndex    : $SkipIndex"

# Treat -WithMilvus as implying -WithDocker
if ($WithMilvus) { $WithDocker = $true }

# --- Optional confirmation ----------------------------------------------------
if (-not $Force) {
    Write-Host ''
    $answer = Read-Host '  Proceed with installation? [Y/n]'
    if ($answer -match '^[Nn]') {
        Write-Warn 'Installation cancelled by user.'
        exit 0
    }
}

# =============================================================================
# STEP 1 -- Check Python version
# =============================================================================
try {
    Write-Step 1 'Checking Python version (>= 3.10 required)'

    $rawVersion = & $PythonExe --version 2>&1
    Write-Info "Detected: $rawVersion"

    if ($rawVersion -match 'Python\s+(\d+)\.(\d+)') {
        [int]$major = $Matches[1]
        [int]$minor = $Matches[2]
    } else {
        throw "Could not parse Python version string: $rawVersion"
    }

    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
        Write-Err "Python 3.10+ is required. Found: $major.$minor"
        exit 1
    }

    Write-Ok "Python $major.$minor -- OK"
}
catch {
    Write-Err "Step 1 failed: $_"
    exit 1
}

# =============================================================================
# STEP 2 -- Create virtual environment
# =============================================================================
try {
    Write-Step 2 'Creating virtual environment (.venv)'

    if (Test-Path $VENV_PY) {
        Write-Ok '.venv already exists -- skipping creation'
    } else {
        Write-Info "Running: $PythonExe -m venv `"$VENV_DIR`""
        & $PythonExe -m venv $VENV_DIR
        if ($LASTEXITCODE -ne 0) { throw "venv creation exited with code $LASTEXITCODE" }
        Write-Ok "Virtual environment created at $VENV_DIR"
    }
}
catch {
    Write-Err "Step 2 failed: $_"
    exit 1
}

# =============================================================================
# STEP 3 -- Install Python dependencies
# =============================================================================
try {
    Write-Step 3 'Installing Python dependencies'

    Write-Info 'Upgrading pip, setuptools, wheel...'
    & $VENV_PY -m pip install --upgrade pip setuptools wheel --quiet
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade exited with code $LASTEXITCODE" }
    Write-Ok 'pip, setuptools, wheel upgraded'

    $reqFile = Join-Path $ROOT 'requirements.txt'
    if (-not (Test-Path $reqFile)) {
        Write-Warn "requirements.txt not found at $reqFile -- skipping package install"
    } else {
        Write-Info 'Installing requirements.txt (this may take a while)...'
        & $VENV_PY -m pip install -r $reqFile
        if ($LASTEXITCODE -ne 0) { throw "pip install exited with code $LASTEXITCODE" }
        Write-Ok 'All packages installed successfully'
    }

    # ── Hotfix: tqdm Windows Errno 22 ────────────────────────────────────────
    Write-Info 'Applying tqdm Windows hotfix (OSError Errno 22)...'
    $tqdmStd = Join-Path $VENV_DIR 'Lib\site-packages\tqdm\std.py'
    if (Test-Path $tqdmStd) {
        $content = Get-Content $tqdmStd -Raw
        $oldSnippet = @'
        if fp in (sys.stderr, sys.stdout):
            getattr(sys.stderr, 'flush', lambda: None)()
            getattr(sys.stdout, 'flush', lambda: None)()
'@
        $newSnippet = @'
        if fp in (sys.stderr, sys.stdout):
            try:
                getattr(sys.stderr, 'flush', lambda: None)()
                getattr(sys.stdout, 'flush', lambda: None)()
            except OSError:
                pass
'@
        if ($content -match [regex]::Escape($oldSnippet.Trim())) {
            $content = $content.Replace($oldSnippet, $newSnippet)
            Set-Content $tqdmStd -Value $content -NoNewline
            Write-Ok 'tqdm hotfix applied successfully'
        } elseif ($content -match 'except OSError') {
            Write-Ok 'tqdm hotfix already applied'
        } else {
            Write-Warn 'tqdm hotfix: target snippet not found in std.py'
        }
    } else {
        Write-Warn "tqdm hotfix: std.py not found at $tqdmStd"
    }
}
catch {
    Write-Err "Step 3 failed: $_"
    exit 1
}

# =============================================================================
# STEP 4 -- Bootstrap .env
# =============================================================================
try {
    Write-Step 4 'Bootstrapping .env configuration'

    $envFile    = Join-Path $ROOT '.env'
    $envExample = Join-Path $ROOT '.env.example'

    if (Test-Path $envFile) {
        Write-Ok '.env already exists -- skipping (your settings are preserved)'
    } else {
        if (Test-Path $envExample) {
            Copy-Item -Path $envExample -Destination $envFile
            Write-Ok '.env created from .env.example -- edit it to add your API keys'
        } else {
            Write-Warn '.env.example not found; creating an empty .env placeholder'
            New-Item -ItemType File -Path $envFile -Force | Out-Null
            Write-Ok 'Empty .env created'
        }
    }
}
catch {
    Write-Err "Step 4 failed: $_"
    exit 1
}

# =============================================================================
# STEP 5 -- Create required directories
# =============================================================================
try {
    Write-Step 5 'Creating required project directories'

    $requiredDirs = @(
        'data\inbox',
        'data\features',
        'data\map_keyframes',
        'static\keyframes',
        'static\videos',
        'submission'
    )

    foreach ($relDir in $requiredDirs) {
        $absDir = Join-Path $ROOT $relDir
        if (Test-Path $absDir) {
            Write-Info "  (exists) $relDir"
        } else {
            New-Item -ItemType Directory -Path $absDir -Force | Out-Null
            Write-Ok "  Created  $relDir"
        }
    }
}
catch {
    Write-Err "Step 5 failed: $_"
    exit 1
}

# =============================================================================
# STEP 6 -- Optional: Start Milvus via Docker Compose
# =============================================================================
try {
    if (-not $WithDocker) {
        Write-Step 6 'Docker / Milvus stack (skipped -- use -WithDocker or -WithMilvus)'
        Write-Info 'Pass -WithDocker or -WithMilvus to enable this step'
    } else {
        Write-Step 6 'Docker / Milvus stack'

        $dockerCmd = Get-Command 'docker' -ErrorAction SilentlyContinue
        if (-not $dockerCmd) {
            Write-Warn "'docker' command not found in PATH -- Milvus stack will NOT be started."
            Write-Info  'Install Docker Desktop from https://www.docker.com/products/docker-desktop'
        } else {
            Write-Info "Docker found: $($dockerCmd.Source)"
            Write-Info 'Running: docker compose up -d milvus'

            Push-Location $ROOT
            try {
                docker compose up -d milvus
                if ($LASTEXITCODE -ne 0) { throw "docker compose exited with code $LASTEXITCODE" }
            } finally {
                Pop-Location
            }

            Write-Info 'Waiting 5 seconds for Milvus to initialise...'
            Start-Sleep -Seconds 5
            Write-Ok  'Milvus container started'
            Write-Info 'Milvus gRPC : localhost:19530'
            Write-Info 'Milvus HTTP : http://localhost:9091'

            # If -WithMilvus, patch .env to set VECTOR_BACKEND=hybrid
            if ($WithMilvus) {
                $envFile = Join-Path $ROOT '.env'
                if (Test-Path $envFile) {
                    $envContent = Get-Content $envFile -Raw
                    if ($envContent -match '(?m)^VECTOR_BACKEND=') {
                        $envContent = $envContent -replace '(?m)^VECTOR_BACKEND=.*', 'VECTOR_BACKEND=hybrid'
                    } else {
                        $envContent = $envContent.TrimEnd() + "`nVECTOR_BACKEND=hybrid`n"
                    }
                    Set-Content -Path $envFile -Value $envContent -NoNewline
                    Write-Ok '.env updated: VECTOR_BACKEND=hybrid'
                } else {
                    Write-Warn '.env not found; could not set VECTOR_BACKEND=hybrid'
                }
            }
        }
    }
}
catch {
    Write-Err "Step 6 failed: $_"
    Write-Warn 'Continuing despite Docker error...'
}

# =============================================================================
# STEP 7 -- Build FAISS index
# =============================================================================
try {
    if ($SkipIndex) {
        Write-Step 7 'Build FAISS index (skipped -- -SkipIndex flag set)'
        Write-Info 'Index build step skipped by -SkipIndex flag'
    } else {
        Write-Step 7 'Build FAISS index'

        $indexFile   = Join-Path $ROOT 'data\faiss_index.bin'
        $featuresDir = Join-Path $ROOT 'data\features'

        if (Test-Path $indexFile) {
            Write-Ok 'data\faiss_index.bin already exists -- index build skipped'
        } else {
            $npyFiles = @(Get-ChildItem -Path $featuresDir -Filter '*.npy' -Recurse -ErrorAction SilentlyContinue)

            if ($npyFiles.Count -eq 0) {
                Write-Warn 'No .npy feature files found in data\features\'
                Write-Info 'Add your feature files, then run:'
                Write-Info '  .\.venv\Scripts\python.exe build_index.py'
            } else {
                Write-Info "Found $($npyFiles.Count) .npy feature file(s) -- building FAISS index..."
                $buildScript = Join-Path $ROOT 'build_index.py'

                if (-not (Test-Path $buildScript)) {
                    Write-Warn "build_index.py not found at $buildScript -- skipping index build"
                } else {
                    & $VENV_PY $buildScript
                    if ($LASTEXITCODE -ne 0) { throw "build_index.py exited with code $LASTEXITCODE" }
                    Write-Ok 'FAISS index built successfully'
                }
            }
        }
    }
}
catch {
    Write-Err "Step 7 failed: $_"
    Write-Warn 'Continuing despite index build error...'
}

# =============================================================================
# STEP 8 -- Final summary
# =============================================================================
Write-Step 8 'Installation complete!'

Write-Host ''
Write-Host '================================================================' -ForegroundColor Magenta
Write-Host '                        NEXT STEPS                             ' -ForegroundColor Magenta
Write-Host '================================================================' -ForegroundColor Magenta
Write-Host '  Activate venv  :  .\.venv\Scripts\Activate.ps1              ' -ForegroundColor White
Write-Host '  Start backend  :  uvicorn main:app --reload                  ' -ForegroundColor White
Write-Host '  With Docker    :  docker compose up                          ' -ForegroundColor White
Write-Host '  Search         :  .\search.ps1 -Mode KIS "your query"       ' -ForegroundColor White
Write-Host '  Ingest data    :  .\ingest.ps1 -ZipDir C:\path\to\zips      ' -ForegroundColor White
Write-Host '  Config         :  Edit .env -- add GEMINI_API_KEY, etc.     ' -ForegroundColor White
Write-Host '================================================================' -ForegroundColor Magenta
Write-Host ''
Write-Ok  'All done. Happy hacking at AIC 2026!'
Write-Host ''
