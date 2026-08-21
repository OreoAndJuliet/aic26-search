param(
    [string]$PythonExe = "python",
    [switch]$RunPytest,
    [switch]$RunEvalHarness,
    [int]$PytestTimeoutSeconds = 600,
    [int]$BackendPort = 8000,
    [switch]$SkipDocker
)

$ErrorActionPreference = "Stop"
function Write-Info($m){ Write-Host "[INFO] $m" -ForegroundColor Cyan }
function Write-Warn($m){ Write-Host "[WARN] $m" -ForegroundColor Yellow }
function Write-Err($m){ Write-Host "[ERROR] $m" -ForegroundColor Red }

$root = (Get-Location).Path
Write-Info "Running test.ps1 in $root"

# Prefer virtualenv python if present
$venvPython = Join-Path $root '.venv\Scripts\python.exe'
if (Test-Path $venvPython) { $python = $venvPython } else { $python = $PythonExe }
Write-Info "Using python: $python"

$exitCode = 0

# Start backend (docker-compose up or local uvicorn) so PS1 HTTP tests can run
$backendStartedByScript = $false
$backendProcess = $null
$composePath1 = Join-Path $root 'docker-compose.yml'
$composePath2 = Join-Path $root 'docker-compose.yaml'
$useDockerCompose = $false
if (-not $SkipDocker -and ((Test-Path $composePath1) -or (Test-Path $composePath2))) { $useDockerCompose = $true }

function Start-Backend() {
    param()
    if ($useDockerCompose) {
        Write-Info "Starting backend via docker compose"
        $composeFile = if (Test-Path $composePath1) { $composePath1 } else { $composePath2 }
        try {
            # prefer docker compose
            $useNew = $false
            try { & docker compose version > $null 2>&1; if ($LASTEXITCODE -eq 0) { $useNew = $true } } catch {}
            if ($useNew) { & docker compose -f $composeFile up -d --build } else { & docker-compose -f $composeFile up -d --build }
            Write-Info "Docker compose started backend"
            $script:backendStartedByScript = 'docker'
            return
        } catch {
            Write-Warn "docker compose failed to start backend: $_"
        }
    }
    Write-Info "Starting backend locally with uvicorn"
    try {
        $uvicornArgs = @('-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', "$BackendPort")
        $proc = Start-Process -FilePath $python -ArgumentList $uvicornArgs -WorkingDirectory $root -NoNewWindow -PassThru
        Start-Sleep -Seconds 1
        $script:backendProcess = $proc
        $script:backendStartedByScript = 'local'
        Write-Info "Started local backend (PID $($proc.Id))"
    } catch {
        Write-Err "Failed to start local backend: $_"
    }
}

function Stop-Backend() {
    if ($backendStartedByScript -eq 'docker') {
        Write-Info "Stopping docker compose backend"
        $composeFile = if (Test-Path $composePath1) { $composePath1 } else { $composePath2 }
        try { & docker compose -f $composeFile down -v } catch { & docker-compose -f $composeFile down -v }
    } elseif ($backendStartedByScript -eq 'local' -and $null -ne $backendProcess) {
        try {
            Write-Info "Stopping local backend PID $($backendProcess.Id)"
            Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue
        } catch { }
    } else {
        Write-Info "No backend started by script to stop"
    }
}

# Start backend and wait for health
Start-Backend
$healthy = $false
$maxAttempts = 60
$attempt = 0
while (-not $healthy -and $attempt -lt $maxAttempts) {
    try {
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/health" -Method Get -TimeoutSec 5
        if ($null -ne $resp) { $healthy = $true; break }
    } catch { }
    Start-Sleep -Seconds 1
    $attempt++
}
if (-not $healthy) { Write-Warn "Backend did not respond on /health after waiting. Continuing but HTTP tests may fail." }

if ($RunPytest) {
    Write-Info "Running pytest (this may take a while). Timeout: $PytestTimeoutSeconds sec"
    try {
        & $python -m pytest -q
        $exitCode = $LASTEXITCODE
        if ($exitCode -ne 0) { Write-Err "pytest failed with exit code $exitCode" }
    } catch {
        Write-Err "pytest invocation failed: $_"
        $exitCode = 3
    }
}

if ($RunEvalHarness) {
    # create small sample CSV in temp
    $tmp = [IO.Path]::GetTempPath()
    $csv = Join-Path $tmp 'eval_sample_ps.csv'
    Write-Info "Writing small eval dataset to $csv"
    $content = @(
        'query,video_id,gold_frame_id,question,gold_answer',
        'person walking,V1,100,What is visible?,person',
        'car driving,V1,200,What is visible?,car'
    ) -join "`n"
    $content | Out-File -FilePath $csv -Encoding utf8

    # Run eval harness in retrieval and vqa modes with hybrid-mock backend (safe, uses MockMilvusClient)
    $outCsv = Join-Path $tmp 'eval_results_ps.csv'

    # Ensure the repository root is on PYTHONPATH so scripts using "from app.*" can be run as scripts
    Write-Info "Ensuring PYTHONPATH includes repo root: $root"
    $env:PYTHONPATH = $root

    try {
        Write-Info "Running eval_harness retrieval mode"
        & $python "$root\scripts\eval_harness.py" --dataset $csv --mode retrieval --backend hybrid-mock --top-k 5
    } catch {
        Write-Warn "eval_harness retrieval failed: $_"
    }

    try {
        Write-Info "Running eval_harness vqa mode (detailed, output CSV)"
        & $python "$root\scripts\eval_harness.py" --dataset $csv --mode vqa --backend hybrid-mock --top-k 5 --detailed --output-csv $outCsv
        Write-Info "Eval harness detailed results written to: $outCsv"
    } catch {
        Write-Warn "eval_harness vqa failed: $_"
    }

    # Cleanup PYTHONPATH we set earlier to avoid polluting the environment
    try {
        Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    } catch {
        # ignore
    }

    # Run PowerShell integration tests in tests\*.ps1 to exercise HTTP endpoints and options
    $psTests = Get-ChildItem -Path (Join-Path $root 'tests') -Filter 'test_*.ps1' -File | Select-Object -ExpandProperty FullName
    foreach ($t in $psTests) {
        Write-Info "Running PS test: $t"
        try {
            & powershell -NoProfile -ExecutionPolicy Bypass -File $t
            Write-Info "PS test passed: $t"
        } catch {
            Write-Warn "PS test failed: $t - $_"
            $exitCode = 4
        }
    }
}

# Stop backend if started by this script
Stop-Backend

if ($exitCode -eq 0) { Write-Info "All tests finished (exit 0)" } else { Write-Err "Some tests failed (exit $exitCode)" }
exit $exitCode
