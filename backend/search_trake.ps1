[CmdletBinding()]
param (
    [Parameter(Mandatory = $false, Position = 0, ValueFromRemainingArguments = $true, HelpMessage = "Ordered event descriptions")]
    [string[]]$Events,

    [Parameter(HelpMessage = "Pipe-separated event list, e.g. 'enters room|sits down|leaves'")]
    [string]$EventList,

    [Parameter(HelpMessage = "Turn on every algorithmic and pipeline upgrade in 1 command")]
    [Alias("Max", "Turbo", "All")]
    [switch]$AllUpgrades,

    [Parameter(HelpMessage = "Show detailed command usage and exit")]
    [Alias("h")]
    [switch]$Help,

    [int]$topKPerEvent = 100,
    [string]$apiBase = ""
)

# Set default API base from environment variable if not provided
if (-not $apiBase) {
    $apiBase = if ($env:BACKEND_HOST) { $env:BACKEND_HOST } else { "http://127.0.0.1:8000" }
}

if ($AllUpgrades) {
    Write-Host "[ALL UPGRADES ACTIVE] Vectorized DTW Event Alignment + Gaussian Spacing Decay + Monotonic Temporal Filtering + Multi-Concept KIS + Visual PRF + Temporal Consensus + OCR/MediaInfo + Temporal Smoothing + Diversification + Translation" -ForegroundColor Green
    $topKPerEvent = [Math]::Max($topKPerEvent, 100)

    # Load search_common.ps1 so Enable-AllUpgrades is available before the rest of the script runs.
    # (It will be dot-sourced again later via the line below, which is harmless — functions are idempotent.)
    . "$PSScriptRoot\search_common.ps1"
    Enable-AllUpgrades
}

function Show-SearchTrakeHelp {
    Write-Host ""
    Write-Host "Usage: .\search_trake.ps1 [event1 event2 ...] [-EventList 'a|b|c'] [-AllUpgrades] [-Help] [-topKPerEvent N] [-apiBase URL]" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Examples:" -ForegroundColor Yellow
    Write-Host "  .\search_trake.ps1 'a person enters a room' 'the person sits down' 'the person leaves' -AllUpgrades" -ForegroundColor Green
    Write-Host "  .\search_trake.ps1 -EventList 'enters room|sits down|leaves' -AllUpgrades" -ForegroundColor Green
    Write-Host "  .\search_trake.ps1 -Help" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Options:" -ForegroundColor Yellow
    Write-Host "  -AllUpgrades         Turn on every upgrade (Vectorized DTW + Gaussian decay) in 1 command" -ForegroundColor Green
    Write-Host "  -EventList 'a|b|c'   Pipe-separated event sequence" -ForegroundColor Gray
    Write-Host "  -topKPerEvent N      Top-K candidates per event (default: 100)" -ForegroundColor Gray
    Write-Host "  -apiBase URL         Backend URL (default: http://127.0.0.1:8000)" -ForegroundColor Gray
    Write-Host ""
}

if ($Help) {
    Show-SearchTrakeHelp
    exit 0
}

# Usage:
#   .\search_trake.ps1 "a person enters a room" "the person sits down" "the person leaves"
#   .\search_trake.ps1 -EventList "enters room|sits down|leaves"
#   .\search_trake.ps1
#     (script will prompt for events one by one)

. "$PSScriptRoot\search_common.ps1"
Initialize-SearchClient

function Read-InteractiveEvents {
    $collected = [System.Collections.Generic.List[string]]::new()
    $index = 1

    while ($true) {
        $line = Read-Host "Event $index (empty line to finish)"
        if ([string]::IsNullOrWhiteSpace($line)) {
            break
        }
        [void]$collected.Add($line.Trim())
        $index++
    }

    return @($collected)
}

$normalizedEvents = @(
    $Events |
        ForEach-Object { [string]$_ } |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
)

if (-not [string]::IsNullOrWhiteSpace($EventList)) {
    $normalizedEvents += @(
        $EventList -split '\|' |
            ForEach-Object { $_.Trim() } |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    )
}

if ($normalizedEvents.Count -eq 0) {
    Write-Host "Enter ordered TRAKE events."
    $normalizedEvents = Read-InteractiveEvents
}

if ($normalizedEvents.Count -eq 0) {
    Write-Error "At least one event description is required."
    exit 1
}

Write-Host "Mode: TRAKE (multi-event KIS + temporal alignment)"
Write-Host "Events: $($normalizedEvents.Count)"
for ($i = 0; $i -lt $normalizedEvents.Count; $i++) {
    Write-Host ("  E{0}: {1}" -f ($i + 1), $normalizedEvents[$i])
}
Write-Host "Top-K per event: $topKPerEvent"
Write-Host ""

try {
    $response = Invoke-SearchApi -ApiBase $apiBase -Body @{
        type            = "TRAKE"
        events          = $normalizedEvents
        top_k_per_event = $topKPerEvent
    }
}
catch {
    throw "TRAKE search failed. Check that the backend is running at $apiBase. Error: $_"
}

if ($null -eq $response.results -or $response.results.Count -eq 0) {
    throw "No temporally aligned TRAKE results returned."
}

$results = Add-SearchResultLinks -Results @($response.results) -ApiBase $apiBase

Write-Host "Translated events:"
foreach ($item in $response.translated_events) {
    Write-Host "  - $item"
}
if ($response.translation_applied) {
    Write-Host "Translation applied: yes"
}

if ($response.trake) {
    Write-Host ""
    Write-Host "Alignment:"
    Write-Host "  video_id       = $($response.trake.video_id)"
    Write-Host "  event_frames   = $($response.trake.event_frames -join ', ')"
    Write-Host "  alignment_score= $($response.trake.alignment_score)"
    Write-Host "  dtw_score      = $($response.trake.dtw_score)"
}

Write-Host ""
Write-Host "Aligned sequence:"
$results | Select-Object `
    rank,
    event_index,
    event_text,
    @{Name='r_score'; Expression={ if ($_.PSObject.Properties.Name -contains 'r_score') { "{0:F4}" -f [double]$_.r_score } else { "N/A" } }},
    video_id,
    frame_id,
    keyframe_id,
    @{Name='time(s)'; Expression={ "{0:F1}" -f [double]$_.timestamp } },
    link | Format-Table -AutoSize

Write-SearchTiming -Response $response

Write-Host ""
Write-Host "Submission-style frames:"
Write-Host ("  {0}, {1}" -f $response.trake.video_id, ($response.trake.event_frames -join ", "))

