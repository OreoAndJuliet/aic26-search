# =============================================================================
#  AIC 2026 - Retrieval Hyperparameter Auto-Tuner Runner
# =============================================================================
param (
    [ValidateSet("presets", "fast_grid", "full_grid")]
    [string]$Mode = "presets",

    [ValidateSet("all", "kis", "vqa", "trake")]
    [string]$Suite = "kis",

    [string]$Dataset = "data\mock_contest_ground_truth.json",

    [int]$TopK = 100,

    [float]$ToleranceSeconds = 30.0,

    [switch]$Apply
)

$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

$pythonExe = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
}

$scriptPath = Join-Path $PSScriptRoot "scripts\tune_hyperparameters.py"

if ($Apply) {
    & $pythonExe -u $scriptPath --mode $Mode --suite $Suite --dataset $Dataset --topk $TopK --tolerance $ToleranceSeconds --apply
} else {
    & $pythonExe -u $scriptPath --mode $Mode --suite $Suite --dataset $Dataset --topk $TopK --tolerance $ToleranceSeconds
}

