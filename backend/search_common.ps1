function Initialize-SearchClient {
    param(
        [int]$BufferWidth = 220
    )

    try {
        if ($Host.UI.RawUI.BufferSize.Width -lt $BufferWidth) {
            $Host.UI.RawUI.BufferSize = New-Object System.Management.Automation.Host.Size(
                $BufferWidth,
                $Host.UI.RawUI.BufferSize.Height
            )
        }
    }
    catch {
        # Ignore hosts that cannot resize the buffer.
    }

    $envPath = Join-Path $PSScriptRoot ".env"
    if (-not (Test-Path $envPath)) {
        return
    }

    Get-Content $envPath -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $key, $value = $line.Split("=", 2)
            $key = $key.Trim()
            $value = $value.Trim().Trim('"').Trim("'")
            [System.Environment]::SetEnvironmentVariable($key, $value, 'Process')
        }
    }
}

function Get-SearchResultLink {
    param(
        [object]$Result,
        [string]$ApiBase
    )

    if ($Result.thumbnail_url) {
        if ($Result.thumbnail_url -like "http*") {
            return $Result.thumbnail_url
        }
        return "$ApiBase$($Result.thumbnail_url)"
    }
    if ($Result.image_url) {
        return $Result.image_url
    }
    if ($Result.url) {
        return $Result.url
    }
    if ($Result.image_path) {
        if ($Result.image_path -like "http*") {
            return $Result.image_path
        }
        return "$ApiBase/$($Result.image_path.TrimStart('/'))"
    }

    $staticPath = if ($env:STATIC_PATH) { $env:STATIC_PATH } else { "/keyframes" }
    return "$ApiBase$staticPath/$($Result.video_id)/$($Result.frame_id).jpg"
}

function Add-SearchResultLinks {
    param(
        [object[]]$Results,
        [string]$ApiBase
    )

    foreach ($result in $Results) {
        $result | Add-Member -NotePropertyName link -NotePropertyValue (
            Get-SearchResultLink -Result $result -ApiBase $ApiBase
        ) -Force
    }

    return $Results
}

function Invoke-SearchApi {
    param(
        [hashtable]$Body,
        [string]$ApiBase
    )

    $searchEndpoint = if ($env:SEARCH_API_ENDPOINT) { $env:SEARCH_API_ENDPOINT } else { "/api/v1/search" }
    $searchUri = "$ApiBase$searchEndpoint"
    $jsonBody = $Body | ConvertTo-Json -Depth 6
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($jsonBody)

    return Invoke-RestMethod `
        -Uri $searchUri `
        -Method Post `
        -ContentType "application/json; charset=utf-8" `
        -Body $bytes
}

function Write-SearchTiming {
    param([object]$Response)

    Write-Host ""
    Write-Host "Timing (ms):"
    Write-Host ("  translation = {0}" -f $Response.translation_time_ms)
    Write-Host ("  retrieval   = {0}" -f $Response.retrieval_time_ms)
    if ($Response.embedding_time_ms -gt 0) {
        Write-Host ("  embedding   = {0}" -f $Response.embedding_time_ms)
        Write-Host ("  faiss       = {0}" -f $Response.faiss_time_ms)
        Write-Host ("  metadata    = {0}" -f $Response.metadata_time_ms)
    }
    if ($Response.vlm_time_ms -gt 0) {
        Write-Host ("  vlm         = {0}" -f $Response.vlm_time_ms)
    }
    Write-Host ("  total       = {0}" -f $Response.total_time_ms)
}

function Get-ResultRScore {
    param([object]$Result)

    if ($null -eq $Result) { return 0.0 }
    
    # Check for r_score in the result object
    if ($Result.PSObject.Properties.Name -contains 'r_score') {
        $rScore = $Result.r_score
        if ($null -ne $rScore -and $rScore -ne "") {
            $scoreValue = [double]$rScore
            # Ensure score is in 0-1 range
            if ($scoreValue -lt 0) { return 0.0 }
            if ($scoreValue -gt 1) { return 1.0 }
            return $scoreValue
        }
    }
    
    # Check for raw_cosine_score (convert from [-1,1] to [0,1])
    if ($Result.PSObject.Properties.Name -contains 'raw_cosine_score') {
        $rawCosine = $Result.raw_cosine_score
        if ($null -ne $rawCosine -and $rawCosine -ne "") {
            $cosineValue = [double]$rawCosine
            # Clamp cosine to [-1,1] range first
            if ($cosineValue -lt -1) { $cosineValue = -1 }
            if ($cosineValue -gt 1) { $cosineValue = 1 }
            # Convert to [0,1] range
            return ($cosineValue + 1.0) / 2.0
        }
    }
    
    # Fall back to score
    if ($Result.PSObject.Properties.Name -contains 'score') {
        $score = $Result.score
        if ($null -ne $score -and $score -ne "") {
            $scoreValue = [double]$score
            # If score is already in 0-1 range, use it directly
            if ($scoreValue -ge 0 -and $scoreValue -le 1) {
                return $scoreValue
            }
            # If score appears to be in [-1,1] range, convert to [0,1]
            if ($scoreValue -ge -1 -and $scoreValue -le 1) {
                return ($scoreValue + 1.0) / 2.0
            }
            # Otherwise clamp to [0,1] range
            if ($scoreValue -lt 0) { return 0.0 }
            if ($scoreValue -gt 1) { return 1.0 }
            return $scoreValue
        }
    }
    
    return 0.0
}

function Enable-AllUpgrades {
    <#
    .SYNOPSIS
        Enable every algorithmic upgrade across KIS, VQA, and TRAKE in 1 call.
    .DESCRIPTION
        Sets all P0/P1/P2/P3 upgrade environment variables for the current process.
        Called automatically when -AllUpgrades is passed to any search_*.ps1 script.
    #>

    # Multi-Concept Semantic Decomposition
    [System.Environment]::SetEnvironmentVariable("MULTI_CONCEPT_DECOMPOSITION_ENABLED", "true", 'Process')
    [System.Environment]::SetEnvironmentVariable("MULTI_CONCEPT_WEIGHT_GLOBAL",         "0.40", 'Process')
    [System.Environment]::SetEnvironmentVariable("MULTI_CONCEPT_WEIGHT_ENTITY",         "0.25", 'Process')
    [System.Environment]::SetEnvironmentVariable("MULTI_CONCEPT_WEIGHT_ATTRIBUTE",      "0.15", 'Process')
    [System.Environment]::SetEnvironmentVariable("MULTI_CONCEPT_WEIGHT_ACTION",         "0.10", 'Process')
    [System.Environment]::SetEnvironmentVariable("MULTI_CONCEPT_WEIGHT_SCENE",          "0.10", 'Process')

    # Query Expansion (template mode — no LLM needed)
    [System.Environment]::SetEnvironmentVariable("QUERY_EXPANSION_ENABLED",          "true",    'Process')
    [System.Environment]::SetEnvironmentVariable("QUERY_EXPANSION_MODE",             "template", 'Process')
    [System.Environment]::SetEnvironmentVariable("QUERY_EXPANSION_NUM_VARIATIONS",   "3",        'Process')
    [System.Environment]::SetEnvironmentVariable("QUERY_EXPANSION_ORIGINAL_WEIGHT",  "0.6",      'Process')
    [System.Environment]::SetEnvironmentVariable("QUERY_EXPANSION_EXPANDED_WEIGHT",  "0.4",      'Process')

    # Deep Candidate Pool
    [System.Environment]::SetEnvironmentVariable("KIS_CANDIDATE_POOL_SIZE", "1000", 'Process')

    # Crop-Level CLIP Regional RoI
    [System.Environment]::SetEnvironmentVariable("KIS_CROP_ALIGNMENT_ENABLED", "true", 'Process')
    [System.Environment]::SetEnvironmentVariable("KIS_CROP_ALIGNMENT_TOPK",    "15",   'Process')
    [System.Environment]::SetEnvironmentVariable("KIS_CROP_ALIGNMENT_WEIGHT",  "0.12", 'Process')

    # Object Co-Occurrence Rerank (Faster R-CNN)
    [System.Environment]::SetEnvironmentVariable("KIS_OBJECT_RERANK_ENABLED", "true", 'Process')
    [System.Environment]::SetEnvironmentVariable("KIS_OBJECT_RERANK_WEIGHT",  "0.10", 'Process')

    # Inverted OCR + BM25 MediaInfo
    [System.Environment]::SetEnvironmentVariable("KIS_MEDIA_INFO_ENRICH_ENABLED",  "true", 'Process')
    [System.Environment]::SetEnvironmentVariable("KIS_MEDIA_INFO_RERANK_ENABLED",  "true", 'Process')
    [System.Environment]::SetEnvironmentVariable("KIS_MEDIA_INFO_RERANK_WEIGHT",   "0.10", 'Process')

    # Visual PRF (Rocchio Expansion)
    [System.Environment]::SetEnvironmentVariable("VISUAL_PRF_ENABLED",     "true", 'Process')
    [System.Environment]::SetEnvironmentVariable("VISUAL_PRF_TOPK",        "3",    'Process')
    [System.Environment]::SetEnvironmentVariable("VISUAL_PRF_WEIGHT",      "0.12", 'Process')
    [System.Environment]::SetEnvironmentVariable("VISUAL_PRF_BLEND_ALPHA", "0.20", 'Process')

    # Temporal Shot Consensus Graph
    [System.Environment]::SetEnvironmentVariable("TEMPORAL_CONSENSUS_ENABLED",          "true", 'Process')
    [System.Environment]::SetEnvironmentVariable("TEMPORAL_CONSENSUS_WINDOW_SECONDS",   "15.0", 'Process')
    [System.Environment]::SetEnvironmentVariable("TEMPORAL_CONSENSUS_BOOST_WEIGHT",     "0.15", 'Process')
    [System.Environment]::SetEnvironmentVariable("TEMPORAL_CONSENSUS_ISOLATED_PENALTY", "0.00", 'Process')

    # EMA Temporal Smoothing
    [System.Environment]::SetEnvironmentVariable("TEMPORAL_SMOOTHING_ENABLED",        "true", 'Process')
    [System.Environment]::SetEnvironmentVariable("TEMPORAL_SMOOTHING_WINDOW_SECONDS", "6.0",  'Process')
    [System.Environment]::SetEnvironmentVariable("TEMPORAL_SMOOTHING_SIGMA",          "3.0",  'Process')
    [System.Environment]::SetEnvironmentVariable("TEMPORAL_SMOOTHING_WEIGHT",         "0.15", 'Process')

    # Intra-Video Soft Diversification
    [System.Environment]::SetEnvironmentVariable("DIVERSIFICATION_ENABLED",        "true",         'Process')
    [System.Environment]::SetEnvironmentVariable("DIVERSIFICATION_MIN_GAP_SECONDS","3.5",          'Process')
    [System.Environment]::SetEnvironmentVariable("DIVERSIFICATION_MAX_PER_VIDEO",  "6",            'Process')
    [System.Environment]::SetEnvironmentVariable("DIVERSIFICATION_MODE",           "soft_penalty", 'Process')
    [System.Environment]::SetEnvironmentVariable("DIVERSIFICATION_PENALTY_WEIGHT", "0.05",         'Process')

    # VQA-specific
    [System.Environment]::SetEnvironmentVariable("VQA_COUNTING_STRATEGY",        "scale_aware", 'Process')
    [System.Environment]::SetEnvironmentVariable("SPATIAL_VQA_ATTENTION_ENABLED","true",        'Process')
    [System.Environment]::SetEnvironmentVariable("TEMPORAL_VQA_CONTEXT_ENABLED", "true",        'Process')

    # Hybrid Metadata Rerank + Translation + Cache Warmup
    [System.Environment]::SetEnvironmentVariable("HYBRID_METADATA_RERANK_ENABLED", "true",                   'Process')
    [System.Environment]::SetEnvironmentVariable("HYBRID_METADATA_RERANK_WEIGHT",  "0.12",                   'Process')
    [System.Environment]::SetEnvironmentVariable("TRANSLATION_ENABLED",            "true",                   'Process')
    [System.Environment]::SetEnvironmentVariable("TRANSLATION_PROVIDER",           "google_gtx",             'Process')
    [System.Environment]::SetEnvironmentVariable("CLIP_WARMUP_ENABLED",            "true",                   'Process')
    [System.Environment]::SetEnvironmentVariable("CLIP_WARMUP_QUERY",              "a person walking in a room", 'Process')
}
