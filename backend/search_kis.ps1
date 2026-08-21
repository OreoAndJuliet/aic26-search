[CmdletBinding()]
param (
    [Parameter(Mandatory = $false, Position = 0, HelpMessage = "Search query in Vietnamese or English")]
    [string]$baseQuery,

    [Parameter(HelpMessage = "Turn on every algorithmic and pipeline upgrade in 1 command")]
    [Alias("Max", "Turbo", "All")]
    [switch]$AllUpgrades,

    [Parameter(HelpMessage = "Hybrid LLM expansion: half Google Gemini + half OpenAI ChatGPT")]
    [switch]$Expand,

    [Parameter(HelpMessage = "Fast faithful template expansion (no LLM, compliance-friendly)")]
    [switch]$TemplateExpand,

    [Parameter(HelpMessage = "Show detailed command usage and exit")]
    [Alias("h")]
    [switch]$Help,

    [int]$topK = 100,
    [int]$topKPerQuery = 100,
    [int]$finalTopK = 100,
    [int]$expandCount = 6,
    [string]$apiBase = ""
)

# Set default API base from environment variable if not provided
if (-not $apiBase) {
    $apiBase = if ($env:BACKEND_HOST) { $env:BACKEND_HOST } else { "http://127.0.0.1:8000" }
}

if ($AllUpgrades) {
    Write-Host "[ALL UPGRADES ACTIVE] Multi-Concept Decomposition + Template Paraphrasing + Visual PRF + Temporal Shot Consensus + Crop Regional RoI + Object Rerank + OCR/MediaInfo + Temporal Smoothing + Diversification + Translation" -ForegroundColor Green
    $TemplateExpand = $true
    $topK         = [Math]::Max($topK,         100)
    $topKPerQuery  = [Math]::Max($topKPerQuery,  100)
    $finalTopK     = [Math]::Max($finalTopK,     100)

    # Load search_common.ps1 so Enable-AllUpgrades is available before the rest of the script runs.
    # (It will be dot-sourced again later, which is harmless — functions are idempotent.)
    . "$PSScriptRoot\search_common.ps1"
    Enable-AllUpgrades
}

function Show-SearchKisHelp {
    Write-Host ""
    Write-Host "Usage: .\search_kis.ps1 [query] [-AllUpgrades] [-Expand] [-TemplateExpand] [-Help] [-topK N] [-apiBase URL]" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Examples:" -ForegroundColor Yellow
    Write-Host "  .\search_kis.ps1 'a person walking in a room' -AllUpgrades" -ForegroundColor Green
    Write-Host "  .\search_kis.ps1 'người đi xe máy gần Chợ Bến Thành' -AllUpgrades -topK 100" -ForegroundColor Green
    Write-Host "  .\search_kis.ps1 'a person walking in a room' -Expand -topK 20" -ForegroundColor Gray
    Write-Host "  .\search_kis.ps1 'a person walking in a room' -TemplateExpand -apiBase http://127.0.0.1:8000" -ForegroundColor Gray
    Write-Host "  .\search_kis.ps1 -Help" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Options:" -ForegroundColor Yellow
    Write-Host "  -AllUpgrades    Turn on every algorithmic upgrade (Multi-Concept + PRF + Consensus + RoI) in 1 command" -ForegroundColor Green
    Write-Host "  -Expand         Use hybrid LLM paraphrase expansion for stronger recall" -ForegroundColor Gray
    Write-Host "  -TemplateExpand Use a faithful template-based expansion without external LLM calls" -ForegroundColor Gray
    Write-Host "  -topK N        Number of returned KIS hits (default: 100)" -ForegroundColor Gray
    Write-Host "  -apiBase URL   Backend URL (default: http://127.0.0.1:8000)" -ForegroundColor Gray
    Write-Host ""
}

if ($Help) {
    Show-SearchKisHelp
    exit 0
}

# Usage:
#   Compliance / fast (default):
#     .\search_kis.ps1 "a person walking in a room"
#   Best quality (4 paraphrases, fused KIS, top 100 frames):
#     .\search_kis.ps1 "a person walking in a room" -Expand
#   Faithful template fusion (no LLM):
#     .\search_kis.ps1 "a person walking in a room" -TemplateExpand

function Normalize-QueryList {
    param([object]$InputObject)

    if ($null -eq $InputObject) { return @() }
    if ($InputObject -is [string]) {
        $trimmed = $InputObject.Trim()
        if ([string]::IsNullOrWhiteSpace($trimmed)) { return @() }
        return @($trimmed)
    }

    return @(
        $InputObject |
            ForEach-Object { [string]$_ } |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    )
}

function Get-GeminiText {
    param([object]$Response)

    if ($null -eq $Response.candidates -or $Response.candidates.Count -eq 0) {
        $reason = $Response.promptFeedback.blockReason
        if ($reason) {
            throw "Gemini blocked the request: $reason"
        }
        throw "Gemini returned no candidates."
    }

    $text = (
        $Response.candidates[0].content.parts |
            Where-Object { $_.text } |
            Select-Object -First 1
    ).text

    if ([string]::IsNullOrWhiteSpace($text)) {
        throw "Gemini returned an empty response."
    }

    return $text.Trim()
}

function Parse-JsonQueryArray {
    param([string]$Text)

    $clean = $Text.Trim()
    $clean = $clean -replace '^\s*```(?:json)?\s*', ''
    $clean = $clean -replace '\s*```\s*$', ''
    $clean = $clean.Trim()

    $parsed = $clean | ConvertFrom-Json
    if ($parsed -is [PSCustomObject] -and $parsed.PSObject.Properties.Name -contains 'queries') {
        $parsed = $parsed.queries
    }
    return Normalize-QueryList -InputObject $parsed
}

function Get-ParaphraseExpansionPrompt {
    param(
        [string]$Query,
        [int]$Count
    )

    return @"
You generate ultra-faithful micro-paraphrases for video keyframe text search (CLIP-style).

Given one user query, output a JSON array of exactly $Count alternative English phrasings.

GOAL: Keep the same searchable words and facts. This is NOT general rewriting - only tiny surface variations.

STRICT RULES:
1. Keep every content noun and verb from the original query. Do NOT replace them with synonyms.
   - "person" must stay "person" or "people" - NEVER someone, somebody, individual, figure, or human.
   - "room" must stay "room" or "rooms" - NEVER indoor space, interior, indoors, or a specific room type.
   - "walking" must stay walk/walks/walking/walked - NEVER moving, traveling, or strolling.
2. Allowed changes ONLY:
   - articles/determiners: a/an/the
   - preposition swaps for the same meaning: in/inside/within
   - verb inflection from the SAME lemma: walk/walks/walking/walked
   - word order and grammar
3. Do NOT add, remove, infer, or substitute any word, object, place, color, clothing, gender, age, number, or emotion.
4. Do NOT introduce any new content word that is not already in the user query.
5. Keep each query short (4-12 words), visual, and searchable.
6. Output ONLY a JSON array of strings. No markdown, no explanation.

GOOD (for "a person walking in a room"):
["a person walks in a room", "a person walking inside a room", "the person walking in a room", "a person walking in the room"]

BAD:
["someone walking in a room", "an individual walking inside a room", "someone moving through an indoor space", "person walking around a bedroom"]
Reason: replaced person with someone/individual, changed verb, replaced room, or invented details.

User query: $Query
"@
}

function Get-QueryContentTokens {
    param([string]$Query)

    $stopWords = @(
        'a', 'an', 'the', 'in', 'on', 'at', 'of', 'to', 'for', 'with', 'by', 'from',
        'into', 'inside', 'within', 'through', 'around', 'and', 'or', 'is', 'are',
        'was', 'were', 'be', 'being', 'that', 'this', 'there', 'their', 'while'
    )

    return @(
        $Query.ToLowerInvariant() -replace '[^\w\s]', ' ' -split '\s+' |
            Where-Object { $_ -and ($stopWords -notcontains $_) }
    )
}

function Get-ParaphraseConceptRequirements {
    param([string]$Query)

    $inflectionMap = [ordered]@{
        walk  = @('walk', 'walks', 'walking', 'walked')
        run   = @('run', 'runs', 'running', 'ran')
        stand = @('stand', 'stands', 'standing', 'stood')
        sit   = @('sit', 'sits', 'sitting', 'sat')
        look  = @('look', 'looks', 'looking', 'looked')
        hold  = @('hold', 'holds', 'holding', 'held')
        carry = @('carry', 'carries', 'carrying', 'carried')
        wear  = @('wear', 'wears', 'wearing', 'wore', 'worn')
    }

    $pluralMap = [ordered]@{
        person = @('person', 'people')
        room   = @('room', 'rooms')
        man    = @('man', 'men')
        woman  = @('woman', 'women')
        child  = @('child', 'children')
    }

    $prepositionVariants = [ordered]@{
        in = @('in', 'inside', 'within')
    }

    $tokens = Get-QueryContentTokens -Query $Query
    $requirements = [System.Collections.Generic.List[object]]::new()
    $seenIds = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    $allowedWords = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)

    foreach ($entry in $prepositionVariants.GetEnumerator()) {
        foreach ($form in $entry.Value) {
            [void]$allowedWords.Add([string]$form)
        }
    }

    foreach ($token in $tokens) {
        $conceptId = $token
        $aliases = @($token)
        $matched = $false

        foreach ($entry in $inflectionMap.GetEnumerator()) {
            $key = [string]$entry.Key
            $forms = @($entry.Value)
            if ($token -eq $key -or ($forms -contains $token) -or ($token.StartsWith($key) -and $key.Length -ge 3)) {
                $conceptId = $key
                $aliases = $forms
                $matched = $true
                break
            }
        }

        if (-not $matched) {
            foreach ($entry in $pluralMap.GetEnumerator()) {
                $key = [string]$entry.Key
                $forms = @($entry.Value)
                if ($token -eq $key -or ($forms -contains $token)) {
                    $conceptId = $key
                    $aliases = $forms
                    $matched = $true
                    break
                }
            }
        }

        foreach ($alias in $aliases) {
            [void]$allowedWords.Add([string]$alias)
        }

        if (-not $seenIds.Add($conceptId)) { continue }

        [void]$requirements.Add([PSCustomObject]@{
                Id      = $conceptId
                Aliases = @($aliases | Select-Object -Unique)
                Strict  = -not $matched -or ($pluralMap.Contains($conceptId))
            })
    }

    return [PSCustomObject]@{
        Requirements = $requirements
        AllowedWords = $allowedWords
    }
}

function Select-FaithfulParaphrases {
    param(
        [string]$Query,
        [string[]]$Candidates,
        [int]$Count
    )

    if ($Count -le 0) { return @() }

    $accepted = [System.Collections.Generic.List[string]]::new()
    $seen = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)

    foreach ($candidate in $Candidates) {
        if ($accepted.Count -ge $Count) { break }
        if (-not (Test-FaithfulParaphrase -Original $Query -Paraphrase $candidate)) { continue }
        if (-not $seen.Add([string]$candidate)) { continue }
        [void]$accepted.Add([string]$candidate)
    }

    return @($accepted)
}

function Get-OpenAIExpansionModelName {
    if ($env:OPENAI_EXPANSION_MODEL) {
        return [string]$env:OPENAI_EXPANSION_MODEL
    }
    if ($env:OPENAI_TRANSLATION_MODEL) {
        return [string]$env:OPENAI_TRANSLATION_MODEL
    }
    return "gpt-4o-mini"
}

function Get-GeminiExpandedParaphrases {
    param(
        [string]$Query,
        [int]$Count
    )

    if ($Count -le 0) { return @() }

    $apiKey = $env:GEMINI_API_KEY
    if (-not $apiKey) { throw "GEMINI_API_KEY is missing in environment variables." }

    $model = Get-ExpansionModelName
    $geminiApiBase = if ($env:GEMINI_API_BASE) { $env:GEMINI_API_BASE } else { "https://generativelanguage.googleapis.com" }
    $url = "${geminiApiBase}/v1beta/models/${model}:generateContent?key=$apiKey"
    $requestCount = [Math]::Min([Math]::Max($Count * 3, $Count + 3), 16)
    $prompt = Get-ParaphraseExpansionPrompt -Query $Query -Count $requestCount

    $genPayload = @{
        contents = @(
            @{
                parts = @(
                    @{ text = $prompt }
                )
            }
        )
        generationConfig = @{
            temperature      = 0.2
            responseMimeType = "application/json"
        }
    } | ConvertTo-Json -Depth 8 -Compress

    try {
        $genResp = Invoke-RestMethod -Method Post -Uri $url -ContentType "application/json" -Body $genPayload
    }
    catch {
        $detail = $_.Exception.Message
        if ($_.Exception.Response) {
            $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
            $detail = $reader.ReadToEnd()
        }
        throw "Gemini generateContent failed: $detail"
    }
    $textOut = Get-GeminiText -Response $genResp
    $generated = Parse-JsonQueryArray -Text $textOut
    return @(
        Select-FaithfulParaphrases -Query $Query -Candidates $generated -Count $Count
    )
}

function Get-OpenAIExpandedParaphrases {
    param(
        [string]$Query,
        [int]$Count
    )

    if ($Count -le 0) { return @() }

    $apiKey = $env:OPENAI_API_KEY
    if (-not $apiKey) { throw "OPENAI_API_KEY is missing in environment variables." }

    $model = Get-OpenAIExpansionModelName
    $requestCount = [Math]::Min([Math]::Max($Count * 3, $Count + 3), 16)
    $prompt = Get-ParaphraseExpansionPrompt -Query $Query -Count $requestCount
    $headers = @{
        Authorization = "Bearer $apiKey"
        ContentType   = "application/json"
    }
    $payload = @{
        model       = $model
        temperature = 0.2
        messages    = @(
            @{
                role    = "user"
                content = $prompt
            }
        )
    } | ConvertTo-Json -Depth 6

    $openaiApiBase = if ($env:OPENAI_API_BASE) { $env:OPENAI_API_BASE } else { "https://api.openai.com" }
    $response = Invoke-RestMethod `
        -Method Post `
        -Uri "${openaiApiBase}/v1/chat/completions" `
        -Headers $headers `
        -Body $payload

    $textOut = $response.choices[0].message.content
    if ([string]::IsNullOrWhiteSpace($textOut)) {
        throw "OpenAI returned an empty paraphrase response."
    }

    $generated = Parse-JsonQueryArray -Text $textOut
    return @(
        Select-FaithfulParaphrases -Query $Query -Candidates $generated -Count $Count
    )
}

function Get-HybridExpandedQueries {
    param(
        [string]$Query,
        [int]$TotalCount
    )

    $googleCount = [int][Math]::Floor($TotalCount / 2)
    $openaiCount = $TotalCount - $googleCount

    Write-Host "Generating paraphrases: Google (Gemini)=$googleCount, OpenAI (ChatGPT)=$openaiCount"

    $googleParaphrases = @()
    $openaiParaphrases = @()
    $googleFailed = $false
    $openaiFailed = $false

    try {
        $googleParaphrases = @(Get-GeminiExpandedParaphrases -Query $Query -Count $googleCount)
        Write-Host "  Google returned $($googleParaphrases.Count) paraphrase(s)"
    }
    catch {
        $googleFailed = $true
        Write-Warning "Google (Gemini) paraphrase expansion failed: $_"
    }

    try {
        $openaiParaphrases = @(Get-OpenAIExpandedParaphrases -Query $Query -Count $openaiCount)
        Write-Host "  OpenAI returned $($openaiParaphrases.Count) paraphrase(s)"
    }
    catch {
        $openaiFailed = $true
        Write-Warning "OpenAI (ChatGPT) paraphrase expansion failed: $_"
    }

    if ($openaiFailed -and -not $googleFailed) {
        $fillCount = [Math]::Max($openaiCount, $TotalCount - $googleParaphrases.Count)
        Write-Warning "Falling back to Gemini-only for $fillCount additional paraphrase(s)."
        try {
            $extraGoogle = @(Get-GeminiExpandedParaphrases -Query $Query -Count $fillCount)
            Write-Host "  Google fallback returned $($extraGoogle.Count) paraphrase(s)"
            $googleParaphrases = @($googleParaphrases + $extraGoogle)
        }
        catch {
            Write-Warning "Gemini fallback expansion failed: $_"
        }
    }

    if ($googleFailed -and -not $openaiFailed) {
        $fillCount = [Math]::Max($googleCount, $TotalCount - $openaiParaphrases.Count)
        Write-Warning "Falling back to OpenAI-only for $fillCount additional paraphrase(s)."
        try {
            $extraOpenai = @(Get-OpenAIExpandedParaphrases -Query $Query -Count $fillCount)
            Write-Host "  OpenAI fallback returned $($extraOpenai.Count) paraphrase(s)"
            $openaiParaphrases = @($openaiParaphrases + $extraOpenai)
        }
        catch {
            Write-Warning "OpenAI fallback expansion failed: $_"
        }
    }

    if ($googleFailed -and $openaiFailed) {
        Write-Warning "Both providers failed on the first attempt. Retrying with Gemini-only..."
        try {
            $googleParaphrases = @(Get-GeminiExpandedParaphrases -Query $Query -Count $TotalCount)
            Write-Host "  Google retry returned $($googleParaphrases.Count) paraphrase(s)"
            $googleFailed = $false
        }
        catch {
            Write-Warning "Gemini retry failed: $_"
        }
    }

    if ($googleParaphrases.Count -eq 0 -and $openaiParaphrases.Count -eq 0) {
        throw "Neither provider returned valid paraphrases."
    }

    $entries = [System.Collections.Generic.List[object]]::new()
    $seen = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)

    function Add-ExpansionEntry {
        param(
            [string]$Text,
            [string]$Provider
        )

        $normalized = [string]$Text
        if ([string]::IsNullOrWhiteSpace($normalized)) { return }
        if (-not $seen.Add($normalized)) { return }

        [void]$entries.Add([PSCustomObject]@{
                Text     = $normalized
                Provider = $Provider
            })
    }

    Add-ExpansionEntry -Text $Query -Provider "original"

    foreach ($q in $googleParaphrases) {
        Add-ExpansionEntry -Text $q -Provider "google"
    }
    foreach ($q in $openaiParaphrases) {
        Add-ExpansionEntry -Text $q -Provider "openai"
    }

    if ($entries.Count -le 1) {
        throw "Hybrid expansion produced no usable paraphrases."
    }

    if ($openaiFailed -or $googleFailed) {
        Write-Host "Expansion fallback active: continuing with available provider paraphrases."
    }

    return $entries
}

function Get-ResultLink {
    param(
        [object]$Result,
        [string]$ApiBase
    )

    if ($Result.image_url) {
        return $Result.image_url
    }
    if ($Result.url) {
        return $Result.url
    }
    if ($Result.image_path) {
        if ($Result.image_path -like "http*") { return $Result.image_path }
        return "$ApiBase/$($Result.image_path.TrimStart('/'))"
    }

    return "$ApiBase/static/keyframes/$($Result.video_id)/$($Result.keyframe_id.ToString('000')).jpg"
}

function Invoke-KisSearch {
    param(
        [string]$Query,
        [int]$TopK,
        [string]$SearchUri,
        [string]$ApiBase,
        [string]$ExpansionProvider = "original"
    )

    $jsonBody = @{
        query_text = [string]$Query
        top_k      = $TopK
    } | ConvertTo-Json

    $bytes = [System.Text.Encoding]::UTF8.GetBytes($jsonBody)

    $res = Invoke-RestMethod `
        -Uri $SearchUri `
        -Method Post `
        -ContentType "application/json; charset=utf-8" `
        -Body $bytes

    if ($null -eq $res.results) {
        throw "Response did not include a results array."
    }

    foreach ($r in $res.results) {
        $r | Add-Member -NotePropertyName source_query -NotePropertyValue $Query -Force
        $r | Add-Member -NotePropertyName expansion_provider -NotePropertyValue $ExpansionProvider -Force
        $r | Add-Member -NotePropertyName link -NotePropertyValue (Get-ResultLink -Result $r -ApiBase $ApiBase) -Force
    }

    return $res.results
}

function Test-FaithfulParaphrase {
    param(
        [string]$Original,
        [string]$Paraphrase
    )

    if ([string]::IsNullOrWhiteSpace($Paraphrase)) { return $false }

    $origLower = $Original.ToLowerInvariant()
    $paraLower = $Paraphrase.ToLowerInvariant()
    $paraWords = @($paraLower -replace '[^\w\s]', ' ' -split '\s+' | Where-Object { $_ })

    $stopWords = @(
        'a', 'an', 'the', 'in', 'on', 'at', 'of', 'to', 'for', 'with', 'by', 'from',
        'into', 'inside', 'within', 'through', 'around', 'and', 'or', 'is', 'are',
        'was', 'were', 'be', 'being', 'that', 'this', 'there', 'their', 'while'
    )

    $specificTerms = @(
        'bedroom', 'kitchen', 'bathroom', 'living room', 'dining room', 'office',
        'hallway', 'corridor', 'garage', 'classroom', 'restaurant', 'cafe',
        'hospital', 'street', 'road', 'park', 'beach', 'forest', 'garden',
        'balcony', 'elevator', 'staircase', 'basement', 'attic', 'warehouse',
        'supermarket', 'shop', 'store', 'airport', 'station', 'car', 'bicycle',
        'motorcycle', 'dog', 'cat', 'baby', 'child', 'elderly', 'woman', 'man'
    )

    $bannedSubstitutions = @(
        'someone', 'somebody', 'individual', 'figure', 'human',
        'indoor space', 'indoor', 'interior', 'indoors', 'inside a building', 'building interior',
        'moving', 'move', 'moves', 'travel', 'travels', 'traveling', 'stroll', 'strolling', 'stepping'
    )

    foreach ($term in $specificTerms) {
        if ($paraLower.Contains($term) -and -not $origLower.Contains($term)) {
            return $false
        }
    }

    foreach ($term in $bannedSubstitutions) {
        if ($paraLower.Contains($term) -and -not $origLower.Contains($term)) {
            return $false
        }
    }

    $conceptData = Get-ParaphraseConceptRequirements -Query $Original
    $requirements = $conceptData.Requirements
    $allowedWords = $conceptData.AllowedWords

    foreach ($req in $requirements) {
        $matched = $false
        foreach ($alias in $req.Aliases) {
            if ($paraWords -contains $alias) {
                $matched = $true
                break
            }
        }
        if (-not $matched) { return $false }
    }

    foreach ($word in $paraWords) {
        if ($stopWords -contains $word) { continue }
        if (-not $allowedWords.Contains($word)) {
            return $false
        }
    }

    if ($origLower -match '\bperson\b' -and $paraWords -notcontains 'person' -and $paraWords -notcontains 'people') {
        return $false
    }

    if ($origLower -match '\broom\b' -and $paraWords -notcontains 'room' -and $paraWords -notcontains 'rooms') {
        return $false
    }

    if ($origLower -match '\bwalk' -and -not ($paraWords | Where-Object { $_ -like 'walk*' })) {
        return $false
    }

    return $true
}

function Get-ExpansionModelName {
    if ($env:GEMINI_EXPANSION_MODEL) {
        return [string]$env:GEMINI_EXPANSION_MODEL
    }
    if ($env:GEMINI_MODEL) {
        return [string]$env:GEMINI_MODEL
    }
    return "gemini-flash-latest"
}

function Get-TemplateExpandedQueries {
    param(
        [string]$Query
    )

    $templates = if ($env:KIS_QUERY_TEMPLATES) {
        $env:KIS_QUERY_TEMPLATES
    } else {
        "{query}|a photo of {query}|an image of {query}|a video frame of {query}"
    }

    $entries = [System.Collections.Generic.List[object]]::new()
    $seen = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)

    foreach ($template in ($templates -split '\|')) {
        $template = $template.Trim()
        if ([string]::IsNullOrWhiteSpace($template)) { continue }

        $expanded = $template.Replace('{query}', $Query).Trim()
        if ([string]::IsNullOrWhiteSpace($expanded)) { continue }
        if (-not $seen.Add($expanded)) { continue }

        [void]$entries.Add([PSCustomObject]@{
                Text     = $expanded
                Provider = "template"
            })
    }

    if ($entries.Count -eq 0) {
        throw "No valid templates found in KIS_QUERY_TEMPLATES."
    }

    return $entries
}

function Get-ResultRScore {
    param([object]$Result)

    if ($null -eq $Result) { return 0.0 }
    
    # Check for r_score in the result object
    if ($Result.PSObject.Properties.Name -contains 'r_score') {
        $rScore = $Result.r_score
        if ($rScore -ne $null -and $rScore -ne "") {
            return [double]$rScore
        }
    }
    
    # Check for raw_cosine_score
    if ($Result.PSObject.Properties.Name -contains 'raw_cosine_score') {
        $rawCosine = $Result.raw_cosine_score
        if ($rawCosine -ne $null -and $rawCosine -ne "") {
            return ([double]$rawCosine + 1.0) / 2.0
        }
    }
    
    # Fall back to score
    if ($Result.PSObject.Properties.Name -contains 'score') {
        $score = $Result.score
        if ($score -ne $null -and $score -ne "") {
            return [double]$score
        }
    }
    
    return 0.0
}

function Get-RScoreReport {
    param(
        [object[]]$Results,
        [int[]]$KValues = @(1, 5, 20, 50, 100)
    )

    $rScores = @(
        $Results |
            ForEach-Object { Get-ResultRScore -Result $_ }
    )

    $topK = [ordered]@{}
    foreach ($k in $KValues) {
        $bucket = @($rScores | Select-Object -First $k)
        if ($bucket.Count -eq 0) {
            $topK[[string]$k] = 0.0
            continue
        }
        $topK[[string]$k] = ($bucket | Measure-Object -Average).Average
    }

    $final = if ($topK.Count -gt 0) {
        ($topK.Values | Measure-Object -Average).Average
    } else {
        0.0
    }

    return [PSCustomObject]@{
        KValues      = $KValues
        TopKRScores  = $topK
        FinalRScore  = $final
        ResultCount  = $Results.Count
    }
}

function Write-RScoreReport {
    param(
        [object[]]$Results
    )

    if ($Results.Count -eq 0) { return }

    $report = Get-RScoreReport -Results $Results
    Write-Host ""
    Write-Host "R-Score report (0..1):"
    foreach ($entry in $report.TopKRScores.GetEnumerator()) {
        Write-Host ("  Top-{0} R-Score = {1:F4}" -f $entry.Key, [double]$entry.Value)
    }
    Write-Host ("  Final R-Score = average(Top-k) = {0:F4}" -f [double]$report.FinalRScore)
}

function Invoke-FusedKisSearch {
    param(
        [System.Collections.Generic.List[object]]$QueryEntries,
        [string]$ModeLabel,
        [int]$TopKPerQuery,
        [int]$FinalTopK,
        [string]$SearchUri,
        [string]$ApiBase
    )

    if (-not [string]::IsNullOrWhiteSpace($ModeLabel)) {
        Write-Host $ModeLabel
        Write-Host ""
    }

    Write-Host "Expanded queries ($($QueryEntries.Count)):"
    foreach ($entry in $QueryEntries) {
        Write-Host "  [$($entry.Provider)] $($entry.Text)"
    }
    Write-Host ""

    $merged = @{}
    $failedQueries = [System.Collections.Generic.List[string]]::new()

    foreach ($entry in $QueryEntries) {
        try {
            $results = Invoke-KisSearch `
                -Query $entry.Text `
                -TopK $TopKPerQuery `
                -SearchUri $SearchUri `
                -ApiBase $ApiBase `
                -ExpansionProvider $entry.Provider
            $hitWeight = if ($entry.Provider -eq 'original') { 2 } else { 1 }
            foreach ($r in $results) {
                $key = "$($r.video_id)|$($r.frame_id)"
                if (-not $merged.ContainsKey($key)) {
                    $merged[$key] = [PSCustomObject]@{
                        Result = $r
                        Hits   = $hitWeight
                        Score  = [double]$r.score
                    }
                    continue
                }

                $merged[$key].Hits += $hitWeight
                if ([double]$r.score -gt $merged[$key].Score) {
                    $merged[$key].Score = [double]$r.score
                    $merged[$key].Result = $r
                }
            }
        }
        catch {
            [void]$failedQueries.Add("$($entry.Provider): $($entry.Text)")
            Write-Warning "Failed to fetch results for sub-query [$($entry.Provider)]: '$($entry.Text)'. Error: $_"
        }
    }

    if ($merged.Count -eq 0) {
        if ($failedQueries.Count -eq $QueryEntries.Count) {
            throw "All KIS sub-queries failed. Check that the backend is running at $ApiBase."
        }
        throw "No results returned from KIS search."
    }

    if ($failedQueries.Count -gt 0) {
        Write-Warning "$($failedQueries.Count) of $($QueryEntries.Count) sub-queries failed."
    }

    # Calculate r_score for each result and sort by r_score descending
    $final = $merged.Values | ForEach-Object {
        $rScore = Get-ResultRScore -Result $_.Result
        $_ | Add-Member -NotePropertyName RScore -NotePropertyValue $rScore -Force
        $_
    } | Sort-Object -Property @{ Expression = 'RScore'; Descending = $true } |
        Select-Object -First $FinalTopK
    
    $rank = 1
    $final = $final | ForEach-Object {
        $result = $_.Result
        $result | Add-Member -NotePropertyName final_rank -NotePropertyValue $rank -Force
        $result | Add-Member -NotePropertyName query_hits -NotePropertyValue $_.Hits -Force
        $rank++
        $result
    }

    Write-Host "Top $($final.Count) fused results:"
    $final | Select-Object `
        final_rank,
        @{Name='r_score'; Expression={ "{0:F4}" -f (Get-ResultRScore -Result $_) }},
        @{Name='cosine'; Expression={
                if ($_.PSObject.Properties.Name -contains 'raw_cosine_score') {
                    "{0:F4}" -f [double]$_.raw_cosine_score
                } else {
                    "{0:F4}" -f ([double](Get-ResultRScore -Result $_) * 2.0 - 1.0)
                }
            }},
        query_hits,
        video_id,
        frame_id,
        keyframe_id,
        @{Name='time(s)'; Expression={ "{0:F1}" -f [double]$_.timestamp }},
        link,
        expansion_provider,
        source_query | Format-Table -AutoSize

    Write-RScoreReport -Results @($final)
}

# Expand PowerShell buffer width to prevent column wrapping
try {
    if ($Host.UI.RawUI.BufferSize.Width -lt 200) {
        $Host.UI.RawUI.BufferSize = New-Object System.Management.Automation.Host.Size(220, $Host.UI.RawUI.BufferSize.Height)
    }
} catch {
    # Ignore if host environment doesn't allow resizing buffer
}

# ===== Auto-load .env file =====
$envPath = Join-Path $PSScriptRoot ".env"
if (Test-Path $envPath) {
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

if ($Expand -and $TemplateExpand) {
    throw "Use only one expansion mode: -Expand (LLM) or -TemplateExpand (templates)."
}

# Prompt if query is empty
if ([string]::IsNullOrWhiteSpace($baseQuery)) {
    $baseQuery = Read-Host "Enter search query"
}

if ([string]::IsNullOrWhiteSpace($baseQuery)) {
    Write-Error "Search query cannot be empty."
    exit 1
}

$searchUri = "$apiBase/api/v1/search/kis"

if ($Expand) {
    if (-not $PSBoundParameters.ContainsKey('expandCount')) {
        $expandCount = 4
    }
    if (-not $PSBoundParameters.ContainsKey('topKPerQuery')) {
        $topKPerQuery = 100
    }
    if (-not $PSBoundParameters.ContainsKey('finalTopK')) {
        $finalTopK = 100
    }

    $googleModel = Get-ExpansionModelName
    $openaiModel = Get-OpenAIExpansionModelName
    Write-Host "Mode: hybrid LLM expansion (Google + OpenAI)"
    Write-Host "Google model: $googleModel"
    Write-Host "OpenAI model: $openaiModel"
    Write-Host "Total paraphrases: $expandCount (half per provider)"
    Write-Host ""

    try {
        $queryEntries = Get-HybridExpandedQueries -Query $baseQuery -TotalCount $expandCount
    }
    catch {
        throw "Hybrid paraphrase expansion failed: $_"
    }

    Invoke-FusedKisSearch `
        -QueryEntries $queryEntries `
        -ModeLabel "" `
        -TopKPerQuery $topKPerQuery `
        -FinalTopK $finalTopK `
        -SearchUri $searchUri `
        -ApiBase $apiBase
}
elseif ($TemplateExpand) {
    if (-not $PSBoundParameters.ContainsKey('topKPerQuery')) {
        $topKPerQuery = 100
    }
    if (-not $PSBoundParameters.ContainsKey('finalTopK')) {
        $finalTopK = 100
    }

    $queryEntries = Get-TemplateExpandedQueries -Query $baseQuery

    Invoke-FusedKisSearch `
        -QueryEntries $queryEntries `
        -ModeLabel "Mode: template expansion (fast, no LLM)" `
        -TopKPerQuery $topKPerQuery `
        -FinalTopK $finalTopK `
        -SearchUri $searchUri `
        -ApiBase $apiBase
}
else {
    Write-Host "Mode: direct search (compliance / fast)"
    Write-Host "Backend: CLIP ViT-B/32 + google_gtx translation for Vietnamese queries"
    Write-Host ""

    try {
        $results = Invoke-KisSearch -Query $baseQuery -TopK $topK -SearchUri $searchUri -ApiBase $apiBase
    }
    catch {
        throw "KIS search failed. Check that the backend is running at $apiBase. Error: $_"
    }

    if ($results.Count -eq 0) {
        throw "No results returned from KIS search."
    }

    # Sort results by r_score descending and re-rank
    $sortedResults = $results | ForEach-Object {
        $rScore = Get-ResultRScore -Result $_
        $_ | Add-Member -NotePropertyName RScore -NotePropertyValue $rScore -Force
        $_
    } | Sort-Object -Property @{ Expression = 'RScore'; Descending = $true }
    
    $rank = 1
    $sortedResults = $sortedResults | ForEach-Object {
        $_.rank = $rank
        $rank++
        $_
    }

    Write-Host "Top $($sortedResults.Count) results:"
    $sortedResults | Select-Object `
        rank,
        @{Name='r_score'; Expression={ "{0:F4}" -f (Get-ResultRScore -Result $_) }},
        @{Name='cosine'; Expression={
                if ($_.PSObject.Properties.Name -contains 'raw_cosine_score') {
                    "{0:F4}" -f [double]$_.raw_cosine_score
                } else {
                    "{0:F4}" -f ([double](Get-ResultRScore -Result $_) * 2.0 - 1.0)
                }
            }},
        video_id,
        frame_id,
        keyframe_id,
        @{Name='time(s)'; Expression={ "{0:F1}" -f [double]$_.timestamp }},
        link | Format-Table -AutoSize

    Write-RScoreReport -Results @($sortedResults)
}
