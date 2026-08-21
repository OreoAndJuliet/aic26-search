# =============================================================================
#  AIC 2026 - All-in-One CLI (KIS / VQA / TRAKE) via API
# =============================================================================
[CmdletBinding()]
param (
    [string]$Mode = "",
    [string]$Query = "",
    [string]$Question = "",
    [string[]]$Events = @(),
    [int]$TopK = 100,
    [switch]$Help
)

$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

if ($Help -or $Mode -eq "") {
    Write-Host "Usage: .\search.bat <kis|vqa|trake> `"query text`" [options]"
    Write-Host "Example: .\search.bat kis `"xe buýt`""
    exit 0
}

$modeUpper = $Mode.ToUpper()
if ($modeUpper -notin @("KIS", "VQA", "TRAKE")) {
    Write-Host "Invalid mode. Use kis, vqa, or trake." -ForegroundColor Red
    exit 1
}

$bodyObj = @{
    type = $modeUpper
    text = $Query
    top_k = $TopK
}
if ($Question) {
    $bodyObj["question"] = $Question
}

$bodyJson = $bodyObj | ConvertTo-Json -Depth 5

try {
    $response = Invoke-RestMethod -Uri "http://localhost:8000/api/search" -Method Post -Body $bodyJson -ContentType "application/json"
} catch {
    Write-Host "API Request Failed. Make sure start.bat is running the server on port 8000!" -ForegroundColor Red
    exit 1
}

$results = @($response.results)
if ($results.Count -eq 0) {
    Write-Host "No matching results found." -ForegroundColor Red
    exit 0
}

$topHit = $results[0]
$vid = $topHit.video_id
$kf = $topHit.keyframe_id
$fid = $topHit.frame_id
$kfStr = "{0:D3}" -f [int]$kf

$ansStr = "null"
if ($topHit.answer) {
    $ansStr = "`"$($topHit.answer)`""
}

$qStr = "null"
if ($Question) {
    $qStr = "`"$Question`""
}

Write-Host "4.1. Static Files"
Write-Host "Ảnh: http://localhost:8000/static/keyframes/$vid/$kfStr.jpg"
Write-Host "Video: http://localhost:8000/static/videos/$vid.mp4"
Write-Host ""

Write-Host "4.2. API /search"
Write-Host "Endpoint: POST /api/v1/search"
Write-Host "Request:"
Write-Host "{"
Write-Host "  `"type`": `"$modeUpper`","
Write-Host "  `"text`": `"$Query`","
Write-Host "  `"question`": $qStr,"
Write-Host "  `"top_k`": $TopK"
Write-Host "}"
Write-Host "Response:"
Write-Host "{"
Write-Host "  `"status`": `"success`","
Write-Host "  `"results`": ["
Write-Host "    {"
Write-Host "      `"video_id`": `"$vid`","
Write-Host "      `"frame_id`": $fid,"
Write-Host "      `"thumbnail_url`": `"$($topHit.thumbnail_url)`","
Write-Host "      `"answer`": $ansStr"
Write-Host "    }"
Write-Host "  ]"
Write-Host "}"
Write-Host ""

Write-Host "4.3. Xuất File"
Write-Host "- Không header. Format: <video_id>, <frame_id>, `"<answer>`""

$csvStr = ""
if ($modeUpper -eq "KIS") {
    $csvStr = "$vid,$fid"
} elseif ($modeUpper -eq "VQA") {
    $csvStr = "$vid,$fid,$($topHit.answer)"
} elseif ($modeUpper -eq "TRAKE") {
    $csvStr = $response.submission_line
}
Write-Host $csvStr
exit 0
