param(
    [string]$PythonExe = "python",
    [switch]$Backup,
    [switch]$CreateVenv = $true,
    [switch]$InstallDeps = $true
)

$ErrorActionPreference = "Stop"

function Write-Info($m){ Write-Host "[INFO] $m" -ForegroundColor Cyan }
function Write-Warn($m){ Write-Host "[WARN] $m" -ForegroundColor Yellow }
function Write-Err($m){ Write-Host "[ERROR] $m" -ForegroundColor Red }

Write-Info "Starting setup.ps1"
$root = (Get-Location).Path
Write-Info "Repository root: $root"

if ($Backup) {
    if (-not (Test-Path (Join-Path $root 'scripts\backup_robo.ps1'))) {
        Write-Warn "Backup script not found at scripts\backup_robo.ps1, skipping backup."
    } else {
        Write-Info "Running backup_robo.ps1 (this may take a while)..."
        try {
            & "$root\scripts\backup_robo.ps1" -Source $root -DestinationRoot (Join-Path $env:USERPROFILE "backups\project")
        } catch {
            Write-Warn "Backup script failed: $_"
        }
    }
}

# Create virtual environment
$venvPath = Join-Path $root '.venv'
if ($CreateVenv) {
    if (-not (Test-Path $venvPath)) {
        Write-Info "Creating virtual environment in $venvPath"
        & $PythonExe -m venv $venvPath
        if ($LASTEXITCODE -ne 0) { Write-Err "Failed to create virtualenv (exit $LASTEXITCODE)"; exit $LASTEXITCODE }
    } else {
        Write-Info "Virtual environment already exists at $venvPath"
    }
} else {
    Write-Info "Skipping venv creation as requested."
}

# Determine pip/python paths to use
$pythonExePath = if (Test-Path (Join-Path $venvPath 'Scripts\python.exe')) { Join-Path $venvPath 'Scripts\python.exe' } else { $PythonExe }
$pipPath = if (Test-Path (Join-Path $venvPath 'Scripts\pip.exe')) { Join-Path $venvPath 'Scripts\pip.exe' } else { "$PythonExe -m pip" }

Write-Info "Using python: $pythonExePath"

# Upgrade pip
try {
    Write-Info "Upgrading pip and setuptools"
    & $pythonExePath -m pip install --upgrade pip setuptools wheel | Out-Null
} catch {
    Write-Warn "Failed to upgrade pip: $_"
}

if ($InstallDeps) {
    # Install requirements if present
    $reqFiles = @('requirements.txt','requirements-dev.txt','dev-requirements.txt')
    $found = $false
    foreach ($f in $reqFiles) {
        $p = Join-Path $root $f
        if (Test-Path $p) {
            Write-Info "Installing packages from $f"
            & $pythonExePath -m pip install -r $p
            $found = $true
        }
    }
    if (-not $found) {
        Write-Info "No requirements.txt found. Attempting editable install of package if setup.py or pyproject.toml exists."
        if ((Test-Path (Join-Path $root 'pyproject.toml')) -or (Test-Path (Join-Path $root 'setup.py'))) {
            & $pythonExePath -m pip install -e $root
        } else {
            Write-Warn "No obvious install target found; skipping dependency install."
        }
    }
} else {
    Write-Info "Skipping dependency installation as requested."
}

# ── Hotfix: tqdm Windows Errno 22 ────────────────────────────────────────────
# When sentence-transformers runs inside uvicorn on Windows, tqdm's status_printer
# unconditionally calls sys.stderr.flush() even when disabled=True.
# This crashes with OSError: [Errno 22] Invalid argument and silently breaks VQA.
# We patch the one problematic line to be wrapped in try/except OSError.
Write-Info "Applying tqdm Windows hotfix (OSError Errno 22)..."
$tqdmStd = Join-Path $venvPath "Lib\site-packages\tqdm\std.py"
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
        Write-Info "tqdm hotfix applied successfully."
    } elseif ($content -match "except OSError") {
        Write-Info "tqdm hotfix already applied, skipping."
    } else {
        Write-Warn "tqdm hotfix: could not find target snippet in std.py - tqdm version may have changed."
    }
} else {
    Write-Warn "tqdm hotfix: std.py not found at $tqdmStd - skipping."
}
# ─────────────────────────────────────────────────────────────────────────────

# Create .env from template if available
$envCandidates = @('.env.example', '.env.sample', '.env.template')
$createdEnv = $false
foreach ($c in $envCandidates) {
    $cTrim = $c.Trim()
    $src = Join-Path $root $cTrim
    $dst = Join-Path $root '.env'
    if ((Test-Path $src) -and (-not (Test-Path $dst))) {
        Copy-Item -Path $src -Destination $dst
        Write-Info "Created .env from $cTrim"
        $createdEnv = $true
        break
    }
}
if (-not $createdEnv) {
    if (-not (Test-Path (Join-Path $root '.env'))) {
        Write-Warn "No .env template found. You may need to create .env with configuration values (API keys, VECTOR_BACKEND, etc.)."
    } else {
        Write-Info ".env already exists."
    }
}

Write-Info "Setup complete. Next steps:\n - Activate the venv: .\.venv\Scripts\Activate.ps1\n - Run .\test.ps1 to run tests and evaluation harness."
