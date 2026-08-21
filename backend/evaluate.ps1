# =============================================================================
#  AIC 2026 - Official Mock Contest Evaluation Harness Runner
# =============================================================================
param (
    [ValidateSet("all", "kis", "vqa", "trake")]
    [string]$Suite = "all",

    [int]$TopK = 10,

    [float]$ToleranceSeconds = 30.0,

    [string]$BaseUrl = "http://localhost:8000",

    [switch]$ExportZip,

    [string]$OutputFile = "data\evaluation_results.json"
)

$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

$pythonExe = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
}

$scriptPath = Join-Path $PSScriptRoot "scripts\run_mock_contest.py"

if ($ExportZip) {
    & $pythonExe -u $scriptPath --suite $Suite --topk $TopK --tolerance $ToleranceSeconds --base-url $BaseUrl --output-json $OutputFile --export-zip
} else {
    & $pythonExe -u $scriptPath --suite $Suite --topk $TopK --tolerance $ToleranceSeconds --base-url $BaseUrl --output-json $OutputFile
}
