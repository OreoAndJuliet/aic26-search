# =============================================================================
#  AIC 2026 - Smart Server & CLI Launcher (AutoDetect, AutoTune, Search, Server)
# =============================================================================
[CmdletBinding(PositionalBinding = $true)]
param (
    [switch]$Benchmark,
    [switch]$Test,
    [switch]$AutoTune,
    [switch]$Tune,
    [switch]$ForceReindex,
    [string]$Mode = "presets",
    [string]$Suite = "kis",
    [string]$Dataset = "data\mock_contest_ground_truth.json",
    [int]$TopK = 100,
    [float]$ToleranceSeconds = 30.0,
    [string]$Kis = "",
    [string]$Vqa = "",
    [string]$Trake = "",
    [Alias("query_text", "search_query")]
    [string]$Query = "",
    [Alias("q", "vqa_question")]
    [string]$Question = "",
    [string]$Events = "",
    [int]$Port = 8000,
    [string]$HostIP = "0.0.0.0",
    [Alias("h")]
    [switch]$Help
)

$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

# Parse raw args in case double-dash syntax or unbound args were passed
for ($i = 0; $i -lt $args.Count; $i++) {
    $arg = $args[$i]
    switch -Regex ($arg) {
        "^--?autotune$|^--?tune$" { $AutoTune = $true }
        "^--?benchmark$" { $Benchmark = $true }
        "^--?test$" { $Test = $true }
        "^--?force-?reindex$" { $ForceReindex = $true }
        "^--?apply$" { $Apply = $true }
        "^--?kis$" {
            $Kis = $true
            if ($i + 1 -lt $args.Count -and -not $args[$i + 1].StartsWith("-")) {
                $Query = $args[$i + 1]
                $i++
            }
        }
        "^--?vqa$" {
            $Vqa = $true
            if ($i + 1 -lt $args.Count -and -not $args[$i + 1].StartsWith("-")) {
                $Query = $args[$i + 1]
                $i++
            }
        }
        "^--?trake$" {
            $Trake = $true
            if ($i + 1 -lt $args.Count -and -not $args[$i + 1].StartsWith("-")) {
                $Query = $args[$i + 1]
                $i++
            }
        }
        "^--?mode$" {
            if ($i + 1 -lt $args.Count) { $Mode = $args[$i + 1]; $i++ }
        }
        "^--?suite$" {
            if ($i + 1 -lt $args.Count) { $Suite = $args[$i + 1]; $i++ }
        }
        "^--?dataset$" {
            if ($i + 1 -lt $args.Count) { $Dataset = $args[$i + 1]; $i++ }
        }
        "^--?topk$|^--?top-?k$" {
            if ($i + 1 -lt $args.Count) { $TopK = [int]$args[$i + 1]; $i++ }
        }
        "^--?tolerance$" {
            if ($i + 1 -lt $args.Count) { $ToleranceSeconds = [float]$args[$i + 1]; $i++ }
        }
        "^--?port$" {
            if ($i + 1 -lt $args.Count) { $Port = [int]$args[$i + 1]; $i++ }
        }
        "^--?host$|^--?hostip$" {
            if ($i + 1 -lt $args.Count) { $HostIP = $args[$i + 1]; $i++ }
        }
        "^--?question$|^-q$" {
            if ($i + 1 -lt $args.Count) { $Question = $args[$i + 1]; $i++ }
        }
        "^--?events$" {
            if ($i + 1 -lt $args.Count) { $Events = $args[$i + 1]; $i++ }
        }
        "^--?help$|^-h$" { $Help = $true }
    }
}

$pythonExe = Join-Path "$PSScriptRoot" ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
}

if ($Help) {
    Write-Host "=================================================================" -ForegroundColor Cyan
    Write-Host "         AIC 2026 BACKEND SERVER & CLI LAUNCHER                  " -ForegroundColor Cyan
    Write-Host "=================================================================" -ForegroundColor Cyan
    Write-Host "Usage:"
    Write-Host "  .\start.bat                       Start FastAPI server on port 8000"
    Write-Host "  .\start.bat -AutoTune [-Apply]    Run hyperparameter auto-tuner"
    Write-Host "  .\start.bat -Test                 Run automated test suite (44 tests)"
    Write-Host "  .\start.bat -Benchmark            Run Codabench benchmark on real data"
    Write-Host "  .\start.bat -Kis <query>          Run direct KIS search"
    Write-Host "  .\start.bat -Vqa <query> -q <txt> Run direct VQA search"
    Write-Host "  .\start.bat -Trake <events>       Run direct TRAKE search"
    Write-Host "  .\start.bat -Port <port>          Start server on custom port"
    Write-Host "=================================================================" -ForegroundColor Cyan
    exit 0
}

# --- Standalone CLI Modes ---
if ($Benchmark) {
    Write-Host ">>> Running AIC 2026 Open-World Codabench Benchmark on Real Data..." -ForegroundColor Cyan
    & $pythonExe (Join-Path "$PSScriptRoot" "scripts\run_open_world_benchmark.py")
    exit $LASTEXITCODE
}

if ($Test) {
    Write-Host ">>> Running Complete Automated Test Suite (44 Tests)..." -ForegroundColor Cyan
    $pytestExe = Join-Path "$PSScriptRoot" ".venv\Scripts\pytest.exe"
    if (Test-Path $pytestExe) {
        & $pytestExe (Join-Path "$PSScriptRoot" "tests\test_all_features.py") (Join-Path "$PSScriptRoot" "tests\test_speculative_consensus.py") -v
    } else {
        & $pythonExe -m pytest (Join-Path "$PSScriptRoot" "tests\test_all_features.py") (Join-Path "$PSScriptRoot" "tests\test_speculative_consensus.py") -v
    }
    exit $LASTEXITCODE
}

if ($AutoTune -or $Tune) {
    Write-Host ">>> Running AIC 2026 Retrieval Hyperparameter Auto-Tuner..." -ForegroundColor Cyan
    $scriptPath = Join-Path "$PSScriptRoot" "scripts\tune_hyperparameters.py"
    $tuneArgs = @("-u", $scriptPath, "--mode", $Mode, "--suite", $Suite, "--dataset", $Dataset, "--topk", "$TopK", "--tolerance", "$ToleranceSeconds", "--apply")
    & $pythonExe @tuneArgs
    exit $LASTEXITCODE
}

if ($Kis -or $Vqa -or $Trake) {
    $searchMode = if ($Kis) { "KIS" } elseif ($Vqa) { "VQA" } else { "TRAKE" }
    $actualQuery = $Query
    if (-not $actualQuery -and $Kis -and $Kis -ne "True") { $actualQuery = $Kis }
    if (-not $actualQuery -and $Vqa -and $Vqa -ne "True") { $actualQuery = $Vqa }
    if (-not $actualQuery -and $Trake -and $Trake -ne "True") { $actualQuery = $Trake }
    if (-not $actualQuery -and $args.Count -gt 0) { $actualQuery = ($args -join " ") }

    Write-Host ">>> Running Direct In-Process $searchMode Search for: '$actualQuery'..." -ForegroundColor Cyan
    $directScript = Join-Path "$PSScriptRoot" "scripts\run_direct_search.py"
    $searchArgs = @($directScript, "--mode", $searchMode, "--query", $actualQuery, "--top-k", "$TopK")
    if ($Question) {
        $searchArgs += @("--question", $Question)
    }
    if ($Events) {
        $searchArgs += @("--events", $Events)
    }
    & $pythonExe @searchArgs
    exit $LASTEXITCODE
}

# --- Default Server Launcher Mode --------------------------------------------
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "         AIC 2026 BACKEND SMART SERVER LAUNCHER                  " -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

Write-Host "[1/5] Checking Port $Port status..." -ForegroundColor Yellow
try {
    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($connections) {
        foreach ($conn in $connections) {
            $pidToKill = $conn.OwningProcess
            if ($pidToKill -gt 0) {
                Write-Host "      Freeing stale process (PID: $pidToKill) on port $Port..." -ForegroundColor Yellow
                Stop-Process -Id $pidToKill -Force -ErrorAction SilentlyContinue
            }
        }
        Start-Sleep -Milliseconds 500
        Write-Host "      Port $Port is now completely free." -ForegroundColor Green
    } else {
        Write-Host "      Port $Port is ready." -ForegroundColor Green
    }
} catch {
    Write-Host "      Port check completed." -ForegroundColor Gray
}

Write-Host "[2/5] Checking Docker Milvus Vector Store (Port 19530)..." -ForegroundColor Yellow
$milvusPortActive = $false
try {
    $tcpClient = New-Object System.Net.Sockets.TcpClient
    $connect = $tcpClient.BeginConnect("127.0.0.1", 19530, $null, $null)
    $success = $connect.AsyncWaitHandle.WaitOne(500, $false)
    if ($success -and $tcpClient.Connected) {
        $milvusPortActive = $true
        $tcpClient.EndConnect($connect)
        Write-Host "      Milvus Standalone is ACTIVE on port 19530 (HNSW Hybrid Mode ready)." -ForegroundColor Green
    }
    $tcpClient.Close()
} catch {}

if (-not $milvusPortActive) {
    Write-Host "      Milvus not detected on port 19530." -ForegroundColor Yellow
    $dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
    if ($dockerCmd) {
        Write-Host "      Attempting to launch Milvus via Docker Compose..." -ForegroundColor Yellow
        & docker compose up -d milvus 2>$null
        Start-Sleep -Seconds 1
    } else {
        Write-Host "      Docker not running. FAISS in-memory C++ engine will handle 100% of queries seamlessly." -ForegroundColor Cyan
    }
}

Write-Host "[3/5] Checking dataset integrity & new feature batches..." -ForegroundColor Yellow
$featuresDir = Join-Path "$PSScriptRoot" "data\features"
$faissIndex = Join-Path "$PSScriptRoot" "data\faiss_index.bin"

$newDataDetected = $false

if (Test-Path $featuresDir) {
    $latestFeature = Get-ChildItem -Path $featuresDir -Filter "*.npy" -Recurse -File | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    
    if (-not (Test-Path $faissIndex)) {
        $newDataDetected = $true
        Write-Host "      [ALERT] faiss_index.bin is missing. Vector index needs to be built!" -ForegroundColor Magenta
    } elseif ($latestFeature) {
        $indexTime = (Get-Item $faissIndex).LastWriteTime
        if ($latestFeature.LastWriteTime -gt $indexTime) {
            $newDataDetected = $true
            Write-Host "      [ALERT] New feature file detected ($($latestFeature.Name)) newer than faiss_index.bin!" -ForegroundColor Magenta
        }
    }
}

if ($ForceReindex -or $newDataDetected) {
    Write-Host "      Building FAISS Vector Index (build_index.py)..." -ForegroundColor Yellow
    & $pythonExe (Join-Path "$PSScriptRoot" "build_index.py")
}

Write-Host "[4/5] Auto-detecting Hardware Accelerator (CPU/GPU)..." -ForegroundColor Yellow
$gpuCheck = & $pythonExe -c "import torch; print('GPU_ACTIVE') if torch.cuda.is_available() else print('CPU_ONLY')"
if ($gpuCheck -match "GPU_ACTIVE") {
    Write-Host "      CUDA GPU detected! Heavy spatial AI algorithms will be ENABLED." -ForegroundColor Green
} else {
    Write-Host "      CPU only detected. Heavy spatial AI algorithms will be DISABLED for speed." -ForegroundColor Cyan
}

Write-Host "[5/5] Starting FastAPI High-Throughput Server on http://${HostIP}:${Port}..." -ForegroundColor Green
Write-Host "=================================================================" -ForegroundColor Cyan

$uvicornCmd = Join-Path "$PSScriptRoot" ".venv\Scripts\uvicorn.exe"
if (-not (Test-Path $uvicornCmd)) {
    & $pythonExe -m uvicorn main:app --host $HostIP --port $Port
} else {
    & $uvicornCmd main:app --host $HostIP --port $Port
}
