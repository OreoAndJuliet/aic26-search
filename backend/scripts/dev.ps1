# AIC 2026 backend - default dev commands with optional -Expand overrides
#
# Quick:
#   .\scripts\dev.ps1
#   .\scripts\dev.ps1 serve
#   .\scripts\dev.ps1 test
#   .\scripts\dev.ps1 index
#
# Expanded (extra flags + shows command before run):
#   .\scripts\dev.ps1 serve -Expand -Port 8080
#   .\scripts\dev.ps1 mock -Expand -SampleFraction 0.3
#   .\scripts\dev.ps1 submit -Expand -Queries data/my.csv -SkipCsv
#
# Raw passthrough:
#   .\scripts\dev.ps1 exec python -m scripts.eval_competition --groundtruth ...

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet(
        "help", "serve", "test", "test-guide", "test-http", "requirement-report",
        "index", "validate", "selfcheck", "mock", "submit", "bench", "eval",
        "ingest", "sync-milvus", "check-milvus", "probe-kis", "docker",
        "backup", "backup-milvus", "restore-milvus", "exec"
    )]
    [string]$Command = "help",

    [switch]$Expand,
    [switch]$DryRun,

    # test-guide -Expand
    [switch]$IncludeHttp,
    [switch]$IncludeClients,
    [switch]$IncludeInfra,
    [switch]$QuickTestGuide,

    # serve -Expand
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8000,
    [switch]$NoReload,

    # test -Expand
    [string]$TestPath = "tests/",
    [switch]$VerboseTests,

    # mock / submit / eval -Expand
    [string]$Queries = "",
    [string]$Groundtruth = "",
    [double]$SampleFraction = 0.5,
    [double]$BudgetHours = 3,
    [string]$OutputDir = "",
    [switch]$SkipCsv,
    [switch]$SkipSubmissionJson,
    [int]$TopK = 20,
    [string]$QueryText = "a person walking in a room",

    # bench -Expand
    [ValidateSet("inprocess", "http")]
    [string]$BenchMode = "inprocess",
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [int]$Repeats = 10,

    # sync-milvus / check-milvus -Expand
    [switch]$RecreateMilvus,
    [int]$MilvusBatchSize = 512,
    [string]$MilvusUri = "",
    [string]$MilvusCollection = "",

    # docker -Expand
    [ValidateSet("up", "down", "logs", "backend", "milvus", "redis", "all")]
    [string]$DockerAction = "up",
    [switch]$DockerBuild,

    # backup / restore -Expand
    [string]$BackupDestination = $(Join-Path $env:USERPROFILE "backups\aic_project"),
    [string]$BackupDir = $(Join-Path $env:TEMP "aic_milvus_backup"),
    [string]$ArchiveName = "",
    [string]$ArchivePath = "",
    [string]$VolumeName = "aic_milvus_data",
    [switch]$IncludeStatic,
    [switch]$IncludeVenv,
    [switch]$ForceRestore,
    [switch]$SkipChecksum,
    [switch]$NoChecksum,
    [int]$KeepBackups = 7,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExecArgs
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $ProjectRoot

function Write-DevLine {
    param([string]$Text = "", [string]$Color = "Gray")
    Write-Host $Text -ForegroundColor $Color
}

function Write-DevBanner {
    Write-Host ""
    Write-Host "  +--------------------------------------------------------------+" -ForegroundColor Cyan
    Write-Host "  |  AIC 2026 Backend - dev.ps1                                  |" -ForegroundColor Cyan
    Write-Host "  |  Project: $ProjectRoot" -ForegroundColor Cyan
    Write-Host "  +--------------------------------------------------------------+" -ForegroundColor Cyan
    Write-Host ""
}

function Write-DevSection {
    param([string]$Title)
    Write-Host "  $Title" -ForegroundColor Yellow
    Write-Host ("  " + ("-" * 62)) -ForegroundColor DarkGray
}

function Import-DevEnv {
    $envPath = Join-Path $ProjectRoot ".env"
    if (-not (Test-Path $envPath)) {
        return
    }
    Get-Content $envPath -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $key, $value = $line.Split("=", 2)
            $key = $key.Trim()
            $value = $value.Trim().Trim('"').Trim("'")
            [System.Environment]::SetEnvironmentVariable($key, $value, "Process")
        }
    }
}

function Get-PythonExe {
    $venvPython = Join-Path $ProjectRoot "venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }
    return "python"
}

function Invoke-DevCommand {
    param(
        [string[]]$CommandParts,
        [string]$Label = "run"
    )

    if (-not $CommandParts -or $CommandParts.Count -eq 0) {
        throw "Empty command."
    }

    $display = ($CommandParts -join " ")
    Write-Host ""
    Write-DevSection "> $Label"
    if ($Expand) {
        Write-DevLine "  mode     expanded" "DarkCyan"
    } else {
        Write-DevLine "  mode     default" "DarkGreen"
    }
    Write-DevLine "  command  $display" "White"
    if ($DryRun) {
        Write-DevLine "  (dry-run - not executed)" "DarkYellow"
        return
    }
    Write-Host ""
    $exe = $CommandParts[0]
    $argList = @()
    if ($CommandParts.Count -gt 1) {
        $argList = $CommandParts[1..($CommandParts.Count - 1)]
    }
    & $exe @argList
    if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) {
        throw "Command failed with exit code $LASTEXITCODE"
    }
}

function Show-DevHelp {
    Write-DevBanner

    Write-DevSection "QUICK - defaults (no -Expand)"
    @(
        @{ Name = "serve";             Desc = "API server (uvicorn --reload :8000)" },
        @{ Name = "test";              Desc = "pytest tests/" },
        @{ Name = "test-guide";        Desc = "run TEST_GUIDE suite (scripts/run_test_guide.ps1)" },
        @{ Name = "test-http";         Desc = "HTTP smoke checks via scripts/test_guide_http.py" },
        @{ Name = "requirement-report"; Desc = "print AIC 2026 requirement gaps from New folder docs" },
        @{ Name = "index";             Desc = "build_index.py + validate_dataset" },
        @{ Name = "validate";          Desc = "validate_dataset only" },
        @{ Name = "selfcheck";         Desc = "CLIP / index self-check" },
        @{ Name = "mock";              Desc = "mock_competition (example CSVs, 50% sample)" },
        @{ Name = "submit";            Desc = "build_submission (example queries + groundtruth)" },
        @{ Name = "bench";             Desc = "benchmark_latency (in-process)" },
        @{ Name = "eval";              Desc = "eval_competition against provided groundtruth" },
        @{ Name = "ingest";            Desc = "extract zip inbox -> static/" },
        @{ Name = "sync-milvus";       Desc = "FAISS -> Milvus sync" },
        @{ Name = "check-milvus";      Desc = "Milvus health + collection validation" },
        @{ Name = "probe-kis";         Desc = "probe a single KIS query" },
        @{ Name = "docker";            Desc = "docker compose up --build" },
        @{ Name = "backup";            Desc = "robocopy backup (skip static/venv)" },
        @{ Name = "backup-milvus";     Desc = "backup Milvus Docker volume" },
        @{ Name = "restore-milvus";    Desc = "restore Milvus Docker volume" },
        @{ Name = "exec";              Desc = "raw passthrough after 'exec'" }
    ) | ForEach-Object {
        Write-DevLine ("  {0,-18} {1}" -f $_.Name, $_.Desc) "Green"
    }

    Write-Host ""
    Write-DevSection "EXPANDED - add -Expand for extra options"
    @(
        "serve          -Expand [-HostName] [-Port] [-NoReload]",
        "test           -Expand [-TestPath] [-VerboseTests]",
        "test-guide     -Expand [-IncludeHttp] [-IncludeClients] [-IncludeInfra] [-QuickTestGuide]",
        "test-http      -Expand [-BaseUrl]",
        "requirement-report -Expand",
        "mock           -Expand [-Queries] [-Groundtruth] [-SampleFraction] [-BudgetHours] [-OutputDir]",
        "submit         -Expand [-Queries] [-Groundtruth] [-SkipCsv] [-OutputDir]",
        "bench          -Expand [-BenchMode inprocess|http] [-BaseUrl] [-TopK] [-Repeats]",
        "eval           -Expand [-Queries] [-Groundtruth] [-TopK]",
        "sync-milvus    -Expand [-RecreateMilvus] [-MilvusBatchSize]",
        "check-milvus   -Expand [-MilvusUri] [-MilvusCollection]",
        "probe-kis      -Expand [-QueryText] [-TopK]",
        "docker         -Expand [-DockerAction up|down|logs|backend|milvus|redis|all] [-DockerBuild]",
        "backup         -Expand [-BackupDestination] [-IncludeStatic] [-IncludeVenv]",
        "backup-milvus  -Expand [-BackupDir] [-ArchiveName] [-VolumeName] [-KeepBackups] [-NoChecksum]",
        "restore-milvus -Expand [-ArchivePath] [-VolumeName] [-ForceRestore] [-SkipChecksum]",
        "            add -DryRun to preview any command without running"
    ) | ForEach-Object {
        Write-DevLine "  $_" "DarkCyan"
    }

    Write-Host ""
    Write-DevSection "EXAMPLES"
    @(
        ".\scripts\dev.ps1 serve",
        ".\scripts\dev.ps1 serve -Expand -Port 8080 -NoReload",
        ".\scripts\dev.ps1 test-guide -Expand -IncludeHttp -IncludeInfra",
        ".\scripts\dev.ps1 test-http -Expand -BaseUrl http://127.0.0.1:8000",
        ".\scripts\dev.ps1 requirement-report",
        ".\scripts\dev.ps1 mock -Expand -SampleFraction 0.3",
        ".\scripts\dev.ps1 submit -Expand -Queries data\queries.example.csv",
        ".\scripts\dev.ps1 bench -Expand -BenchMode http -BaseUrl http://127.0.0.1:8000",
        ".\scripts\dev.ps1 check-milvus",
        ".\scripts\dev.ps1 backup-milvus -Expand -BackupDir C:\tmp -KeepBackups 5",
        ".\scripts\dev.ps1 restore-milvus -Expand -ArchivePath C:\tmp\milvus_backup_....tgz -ForceRestore",
        ".\scripts\dev.ps1 exec python -m scripts.eval_competition --groundtruth data\groundtruth.example.csv",
        ".\scripts\dev.ps1 index -DryRun"
    ) | ForEach-Object {
        Write-DevLine "  $_" "Gray"
    }

    Write-Host ""
    Write-DevLine "  Docs: CODE_INPUTS.md | DEVELOPER_GUIDE.md | TEST_GUIDE.txt | PROJECT_RECHECK_2026.txt" "DarkGray"
    Write-Host ""
}

function Get-DefaultCsv {
    param([string]$Override, [string]$FallbackRelative)
    if ($Override) {
        return (Resolve-Path $Override).Path
    }
    return (Join-Path $ProjectRoot $FallbackRelative)
}

Import-DevEnv
$python = Get-PythonExe

switch ($Command) {
    "help" {
        Show-DevHelp
    }

    "serve" {
        if ($Expand) {
            $useHost = $HostName
            $usePort = $Port
            $useReload = -not $NoReload
        } else {
            $useHost = "127.0.0.1"
            $usePort = 8000
            $useReload = $true
        }
        $uvicornArgs = @("-m", "uvicorn", "main:app", "--host", $useHost, "--port", "$usePort")
        if ($useReload) {
            $uvicornArgs += "--reload"
        }
        Invoke-DevCommand -CommandParts (@($python) + $uvicornArgs) -Label "serve API"
    }

    "test" {
        if ($Expand -and $VerboseTests) {
            $pytestArgs = @("-m", "pytest", $TestPath, "-v")
        } elseif ($Expand) {
            $pytestArgs = @("-m", "pytest", $TestPath, "-q")
        } else {
            $pytestArgs = @("-m", "pytest", "tests/", "-q")
        }
        Invoke-DevCommand -CommandParts (@($python) + $pytestArgs) -Label "pytest"
    }

    "test-guide" {
        $guideScript = Join-Path $ProjectRoot "scripts\run_test_guide.ps1"
        $guideArgs = @("-File", $guideScript)
        if ($QuickTestGuide) { $guideArgs += "-Quick" }
        if ($Expand) {
            if ($IncludeHttp) { $guideArgs += "-IncludeHttp" }
            if ($IncludeClients) { $guideArgs += "-IncludeClients" }
            if ($IncludeInfra) { $guideArgs += "-IncludeInfra" }
        }
        if ($DryRun) { $guideArgs += "-DryRun" }
        if ($Queries) { $guideArgs += @("-Queries", $Queries) }
        if ($Groundtruth) { $guideArgs += @("-Groundtruth", $Groundtruth) }
        if ($BaseUrl -and $BaseUrl -ne "http://127.0.0.1:8000") {
            $guideArgs += @("-BaseUrl", $BaseUrl)
        }
        
        # Use cross-platform PowerShell detection
        $psCommand = if (Get-Command Get-PowerShellCommand -ErrorAction SilentlyContinue) {
            Get-PowerShellCommand
        } else {
            "powershell"
        }
        Invoke-DevCommand -CommandParts (@($psCommand) + $guideArgs) -Label "TEST_GUIDE runner"
    }

    "test-http" {
        $httpArgs = @("-m", "scripts.test_guide_http")
        if ($BaseUrl -and $BaseUrl -ne "") {
            $httpArgs += @("--base-url", $BaseUrl)
        }
        Invoke-DevCommand -CommandParts (@($python) + $httpArgs) -Label "HTTP smoke checks"
    }

    "requirement-report" {
        $reqArgs = @("-m", "scripts.test_guide_http", "--requirement-report")
        Invoke-DevCommand -CommandParts (@($python) + $reqArgs) -Label "AIC 2026 requirement report"
    }

    "index" {
        Invoke-DevCommand -CommandParts @($python, "build_index.py") -Label "build FAISS index"
        Invoke-DevCommand -CommandParts @($python, "-m", "scripts.validate_dataset") -Label "validate dataset"
    }

    "validate" {
        Invoke-DevCommand -CommandParts @($python, "-m", "scripts.validate_dataset") -Label "validate dataset"
    }

    "selfcheck" {
        Invoke-DevCommand -CommandParts @($python, "-m", "scripts.selfcheck") -Label "KIS self-check"
    }

    "mock" {
        if ($Expand) {
            $queriesPath = Get-DefaultCsv -Override $Queries -FallbackRelative "data\queries.example.csv"
            $groundtruthPath = Get-DefaultCsv -Override $Groundtruth -FallbackRelative "data\groundtruth.example.csv"
            $useSample = $SampleFraction
            $useBudget = $BudgetHours
        } else {
            $queriesPath = Join-Path $ProjectRoot "data\queries.example.csv"
            $groundtruthPath = Join-Path $ProjectRoot "data\groundtruth.example.csv"
            $useSample = 0.5
            $useBudget = 3
        }
        $mockArgs = @(
            "-m", "scripts.mock_competition",
            "--queries", $queriesPath,
            "--groundtruth", $groundtruthPath,
            "--sample-fraction", "$useSample",
            "--budget-hours", "$useBudget"
        )
        if ($Expand -and $OutputDir) {
            $mockArgs += @("--output-dir", (Resolve-Path $OutputDir).Path)
        }
        if ($Expand -and $SkipSubmissionJson) {
            $mockArgs += "--skip-submission-json"
        }
        Invoke-DevCommand -CommandParts (@($python) + $mockArgs) -Label "mock competition"
    }

    "submit" {
        if ($Expand) {
            $queriesPath = Get-DefaultCsv -Override $Queries -FallbackRelative "data\queries.example.csv"
            $groundtruthPath = Get-DefaultCsv -Override $Groundtruth -FallbackRelative "data\groundtruth.example.csv"
        } else {
            $queriesPath = Join-Path $ProjectRoot "data\queries.example.csv"
            $groundtruthPath = Join-Path $ProjectRoot "data\groundtruth.example.csv"
        }
        $submitArgs = @(
            "-m", "scripts.build_submission",
            "--queries", $queriesPath,
            "--groundtruth", $groundtruthPath
        )
        if ($Expand -and $SkipCsv) {
            $submitArgs += "--skip-csv"
        }
        if ($Expand -and $OutputDir) {
            $submitArgs += @("--output-csv-dir", (Resolve-Path $OutputDir).Path)
        }
        Invoke-DevCommand -CommandParts (@($python) + $submitArgs) -Label "build submission"
    }

    "bench" {
        if ($Expand) {
            $useMode = $BenchMode
            $useTopK = $TopK
            $useRepeats = $Repeats
            $useBaseUrl = $BaseUrl
        } else {
            $useMode = "inprocess"
            $useTopK = 20
            $useRepeats = 10
            $useBaseUrl = "http://127.0.0.1:8000"
        }
        $benchArgs = @(
            "-m", "scripts.benchmark_latency",
            "--mode", $useMode,
            "--top-k", "$useTopK",
            "--repeats", "$useRepeats"
        )
        if ($useMode -eq "http") {
            $benchArgs += @("--base-url", $useBaseUrl)
        }
        Invoke-DevCommand -CommandParts (@($python) + $benchArgs) -Label "latency benchmark"
    }

    "eval" {
        if ($Expand) {
            $evalQueries = if ($Queries) { $Queries } elseif (Test-Path (Join-Path $ProjectRoot "data\queries.example.csv")) { Join-Path $ProjectRoot "data\queries.example.csv" } else { "" }
            $evalGroundtruth = if ($Groundtruth) { $Groundtruth } elseif (Test-Path (Join-Path $ProjectRoot "data\groundtruth.example.csv")) { Join-Path $ProjectRoot "data\groundtruth.example.csv" } else { "" }
        } else {
            $evalQueries = Join-Path $ProjectRoot "data\queries.example.csv"
            $evalGroundtruth = Join-Path $ProjectRoot "data\groundtruth.example.csv"
        }
        $evalArgs = @("-m", "scripts.eval_competition")
        if ($evalQueries) { $evalArgs += @("--queries", $evalQueries) }
        if ($evalGroundtruth) { $evalArgs += @("--groundtruth", $evalGroundtruth) }
        if ($TopK -gt 0) { $evalArgs += @("--top-k", "$TopK") }
        Invoke-DevCommand -CommandParts (@($python) + $evalArgs) -Label "competition evaluation"
    }

    "ingest" {
        Invoke-DevCommand -CommandParts @($python, "-m", "scripts.ingest_zips") -Label "zip ingest"
    }

    "sync-milvus" {
        if ($Expand) {
            $useBatch = $MilvusBatchSize
            $useRecreate = $RecreateMilvus
        } else {
            $useBatch = 512
            $useRecreate = $false
        }
        $milvusArgs = @("-m", "scripts.sync_milvus", "--batch-size", "$useBatch")
        if ($useRecreate) {
            $milvusArgs += "--recreate"
        }
        Invoke-DevCommand -CommandParts (@($python) + $milvusArgs) -Label "sync Milvus"
    }

    "check-milvus" {
        if ($MilvusUri) { $env:MILVUS_URI = $MilvusUri }
        if ($MilvusCollection) { $env:MILVUS_COLLECTION = $MilvusCollection }
        Invoke-DevCommand -CommandParts (@($python) + @("-m", "scripts.check_milvus")) -Label "Milvus health check"
    }

    "probe-kis" {
        $probeArgs = @("-m", "scripts.probe_kis", $QueryText, "$TopK")
        Invoke-DevCommand -CommandParts (@($python) + $probeArgs) -Label "probe KIS query"
    }

    "docker" {
        if (-not $Expand) {
            $DockerAction = "up"
            $DockerBuild = $true
        }
        switch ($DockerAction) {
            "up" {
                $composeArgs = @("compose", "up")
                if ($DockerBuild) {
                    $composeArgs += "--build"
                }
                $composeArgs += "-d"
                Invoke-DevCommand -CommandParts (@("docker") + $composeArgs) -Label "docker compose up"
            }
            "down" {
                Invoke-DevCommand -CommandParts @("docker", "compose", "down") -Label "docker compose down"
            }
            "logs" {
                Invoke-DevCommand -CommandParts @("docker", "compose", "logs", "-f", "backend") -Label "docker logs"
            }
            "backend" {
                Invoke-DevCommand -CommandParts @("docker", "compose", "up", "-d", "backend") -Label "docker backend only"
            }
            "redis" {
                Invoke-DevCommand -CommandParts @("docker", "compose", "up", "-d", "redis") -Label "docker redis only"
            }
            "milvus" {
                Invoke-DevCommand -CommandParts @("docker", "compose", "up", "-d", "milvus") -Label "docker milvus only"
            }
            "all" {
                Invoke-DevCommand -CommandParts @("docker", "compose", "up", "-d") -Label "docker compose up all services"
            }
        }
    }

    "backup" {
        if (-not $Expand) {
            $BackupDestination = Join-Path $env:USERPROFILE "backups\aic_project"
            $IncludeStatic = $false
            $IncludeVenv = $false
        }
        $backupScript = Join-Path $ProjectRoot "scripts\backup_robo.ps1"
        $backupArgs = @(
            "-File", $backupScript,
            "-Source", $ProjectRoot,
            "-DestinationRoot", $BackupDestination
        )
        if ($IncludeStatic) { $backupArgs += "-IncludeStatic" }
        if ($IncludeVenv) { $backupArgs += "-IncludeVenv" }
        
        # Use cross-platform PowerShell detection
        $psCommand = if (Get-Command Get-PowerShellCommand -ErrorAction SilentlyContinue) {
            Get-PowerShellCommand
        } else {
            "powershell"
        }
        Invoke-DevCommand -CommandParts (@($psCommand) + $backupArgs) -Label "robocopy backup"
    }

    "backup-milvus" {
        $milvusBackupScript = Join-Path $ProjectRoot "scripts\backup_milvus.ps1"
        $milvusBackupArgs = @("-File", $milvusBackupScript)
        $targetDir = if ($BackupDir) { $BackupDir } else { $BackupDestination }
        if ($targetDir) { $milvusBackupArgs += @("-BackupDir", $targetDir) }
        if ($ArchiveName) { $milvusBackupArgs += @("-ArchiveName", $ArchiveName) }
        if ($VolumeName) { $milvusBackupArgs += @("-VolumeName", $VolumeName) }
        if ($KeepBackups -gt 0) { $milvusBackupArgs += @("-Keep", "$KeepBackups") }
        if ($NoChecksum) { $milvusBackupArgs += "-NoChecksum" }
        
        # Use cross-platform PowerShell detection
        $psCommand = if (Get-Command Get-PowerShellCommand -ErrorAction SilentlyContinue) {
            Get-PowerShellCommand
        } else {
            "powershell"
        }
        Invoke-DevCommand -CommandParts (@($psCommand) + $milvusBackupArgs) -Label "Milvus volume backup"
    }

    "restore-milvus" {
        if (-not $ArchivePath) {
            $tempPath = Join-Path $env:TEMP "milvus_backup_....tgz"
            throw "ArchivePath is required for restore-milvus. Example: .\scripts\dev.ps1 restore-milvus -Expand -ArchivePath $tempPath -ForceRestore"
        }
        $restoreArgs = @(
            "-File", (Join-Path $ProjectRoot "scripts\restore_milvus.ps1"),
            "-ArchivePath", $ArchivePath
        )
        if ($VolumeName) { $restoreArgs += @("-VolumeName", $VolumeName) }
        if ($ForceRestore) { $restoreArgs += "-Force" }
        if ($SkipChecksum) { $restoreArgs += "-SkipChecksum" }
        
        # Use cross-platform PowerShell detection
        $psCommand = if (Get-Command Get-PowerShellCommand -ErrorAction SilentlyContinue) {
            Get-PowerShellCommand
        } else {
            "powershell"
        }
        Invoke-DevCommand -CommandParts (@($psCommand) + $restoreArgs) -Label "Milvus restore"
    }

    "exec" {
        if (-not $ExecArgs -or $ExecArgs.Count -eq 0) {
            throw 'Usage: .\scripts\dev.ps1 exec [command...]   Example: exec python -m scripts.selfcheck'
        }
        $exe = $ExecArgs[0]
        $rest = @()
        if ($ExecArgs.Count -gt 1) {
            $rest = $ExecArgs[1..($ExecArgs.Count - 1)]
        }
        if ($exe -eq "python") {
            $exe = $python
        }
        Invoke-DevCommand -CommandParts (@($exe) + $rest) -Label "exec"
    }
}
