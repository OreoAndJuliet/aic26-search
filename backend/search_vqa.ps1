[CmdletBinding()]
param (
    [Parameter(Mandatory = $false, Position = 0, HelpMessage = "Event/context text in Vietnamese or English")]
    [string]$ContextText,

    [Parameter(Mandatory = $false, Position = 1, HelpMessage = "Question about the retrieved frame")]
    [string]$Question,

    [Parameter(HelpMessage = "Turn on every algorithmic and pipeline upgrade in 1 command")]
    [Alias("Max", "Turbo", "All")]
    [switch]$AllUpgrades,

    [Parameter(HelpMessage = "Show detailed command usage and exit")]
    [Alias("h")]
    [switch]$Help,

    [int]$topK = 5,
    [string]$apiBase = ""
)

# Set default API base from environment variable if not provided
if (-not $apiBase) {
    $apiBase = if ($env:BACKEND_HOST) { $env:BACKEND_HOST } else { "http://127.0.0.1:8000" }
}

if ($AllUpgrades) {
    Write-Host "[ALL UPGRADES ACTIVE] Faster R-CNN Scale-Aware Counting + Spatial VQA Attention + Temporal VQA Context + Multi-Concept KIS + Visual PRF + Temporal Consensus + OCR/MediaInfo + Temporal Smoothing + Diversification + Translation" -ForegroundColor Green
    $topK = [Math]::Max($topK, 10)

    # Load search_common.ps1 so Enable-AllUpgrades is available before the rest of the script runs.
    # (It will be dot-sourced again later via the line below, which is harmless — functions are idempotent.)
    . "$PSScriptRoot\search_common.ps1"
    Enable-AllUpgrades
}

function Show-SearchVqaHelp {
    Write-Host ""
    Write-Host "Usage: .\search_vqa.ps1 [contextText] [question] [-AllUpgrades] [-Help] [-topK N] [-apiBase URL]" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Examples:" -ForegroundColor Yellow
    Write-Host "  .\search_vqa.ps1 'a person walking in a room' 'How many people are visible?' -AllUpgrades" -ForegroundColor Green
    Write-Host "  .\search_vqa.ps1 'người trong phòng' 'Người đó mặc áo màu gì?' -AllUpgrades" -ForegroundColor Green
    Write-Host "  .\search_vqa.ps1 -Help" -ForegroundColor Gray
    Write-Host "  .\search_vqa.ps1 'một người đang đi trong phòng' 'Có bao nhiêu người?' -topK 10" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Options:" -ForegroundColor Yellow
    Write-Host "  -AllUpgrades    Turn on every upgrade (Scale-Aware R-CNN + Spatial/Temporal VQA + Multi-Concept KIS + PRF + Consensus + OCR/MediaInfo + Smoothing + Diversification) in 1 command" -ForegroundColor Green
    Write-Host "  -topK N        Number of candidate frames to inspect (default: 5)" -ForegroundColor Gray
    Write-Host "  -apiBase URL   Backend URL (default: http://127.0.0.1:8000)" -ForegroundColor Gray
    Write-Host ""
}

if ($Help) {
    Show-SearchVqaHelp
    exit 0
}

# Usage:
#   .\search_vqa.ps1 "a person walking in a room" "How many people are visible?"
#   .\search_vqa.ps1
#     (script will prompt for context + question)

. "$PSScriptRoot\search_common.ps1"
Initialize-SearchClient

if ([string]::IsNullOrWhiteSpace($ContextText)) {
    $ContextText = Read-Host "Enter event/context text"
}

if ([string]::IsNullOrWhiteSpace($Question)) {
    $Question = Read-Host "Enter VQA question"
}

if ([string]::IsNullOrWhiteSpace($ContextText)) {
    Write-Error "Context text cannot be empty."
    exit 1
}

if ([string]::IsNullOrWhiteSpace($Question)) {
    Write-Error "Question cannot be empty."
    exit 1
}

Write-Host "Mode: VQA (KIS top-$topK + answer)"
Write-Host "Context: $ContextText"
Write-Host "Question: $Question"
Write-Host ""

try {
    $response = Invoke-SearchApi -ApiBase $apiBase -Body @{
        type     = "VQA"
        text     = $ContextText
        question = $Question
        top_k    = $topK
    }
}
catch {
    throw "VQA search failed. Check that the backend is running at $apiBase. Error: $_"
}

if ($null -eq $response.results -or $response.results.Count -eq 0) {
    throw "No VQA results returned."
}

$results = Add-SearchResultLinks -Results @($response.results) -ApiBase $apiBase

Write-Host "Translated context: $($response.translated_text)"
if ($response.translation_applied) {
    Write-Host "Translation applied: yes"
}
Write-Host ""
Write-Host "Top $($results.Count) VQA result(s):"

$results | Select-Object `
    rank,
    @{Name='r_score'; Expression={ if ($_.PSObject.Properties.Name -contains 'r_score') { "{0:F4}" -f [double]$_.r_score } else { "N/A" } }},
    answer,
    @{Name='confidence'; Expression={ if ($_.PSObject.Properties.Name -contains 'confidence') { "{0:P0}" -f [double]$_.confidence } else { "N/A" } }},
    source,
    video_id,
    frame_id,
    keyframe_id,
    @{Name='time(s)'; Expression={ "{0:F1}" -f [double]$_.timestamp } },
    link | Format-Table -AutoSize

Write-SearchTiming -Response $response

$best = $results | Select-Object -First 1
Write-Host ""
Write-Host "Selected Answer: $($best.answer)" -ForegroundColor Green
if ($best.PSObject.Properties.Name -contains 'source') {
    Write-Host "Decision Source: $($best.source)" -ForegroundColor Cyan
}
if ($best.PSObject.Properties.Name -contains 'rationale' -and $best.rationale) {
    Write-Host "Consensus Judge Rationale: $($best.rationale)" -ForegroundColor DarkYellow
}
Write-Host "Target Frame: $($best.video_id), frame_id=$($best.frame_id)"
Write-Host "Thumbnail URL: $($best.link)"

if ($best.PSObject.Properties.Name -contains 'alternative_answers' -and $best.alternative_answers.Count -gt 0) {
    Write-Host ""
    Write-Host "Speculative Candidate Answers Pool ('Pick the 1 you like'):" -ForegroundColor Yellow
    $idx = 1
    foreach ($alt in $best.alternative_answers) {
        $confPct = "{0:P0}" -f [double]$alt.confidence
        Write-Host "  [$idx] $($alt.text) - Source: $($alt.source) (Confidence: $confPct) | $($alt.rationale)" -ForegroundColor DarkCyan
        $idx++
    }
}

