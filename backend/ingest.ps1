<#
.SYNOPSIS
    AIC Organizer Data Bundle Ingestion Script.

.DESCRIPTION
    Extracts AIC zip bundles (keyframes, videos, features, maps) into the correct
    project directories. Optionally rebuilds the FAISS index after ingestion.

.PARAMETER ZipDir
    Directory containing zip files to process. Default: 'data/inbox'.

.PARAMETER ZipFile
    Single zip file to process (alternative to -ZipDir).

.PARAMETER RebuildIndex
    After ingestion, run `python build_index.py`.

.PARAMETER DryRun
    Show what would be extracted without actually extracting anything.

.PARAMETER Force
    Overwrite existing files. Default: skip existing.

.PARAMETER Help
    Show this help message and exit.

.EXAMPLE
    .\ingest.ps1
    Process all zips in data\inbox\.

.EXAMPLE
    .\ingest.ps1 -ZipDir C:\Downloads\aic_bundles -DryRun
    Preview extraction of all zips in the given directory.

.EXAMPLE
    .\ingest.ps1 -ZipFile data\inbox\keyframes_L01.zip -Force
    Extract a single zip, overwriting existing files.

.EXAMPLE
    .\ingest.ps1 -RebuildIndex
    Process inbox zips then rebuild the FAISS index.
#>

[CmdletBinding()]
param(
    [string]  $ZipDir       = 'data/inbox',
    [string]  $ZipFile      = '',
    [switch]  $RebuildIndex,
    [switch]  $DryRun,
    [switch]  $Force,
    [Alias('h')]
    [switch]  $Help
)

# ── Assembly ──────────────────────────────────────────────────────────────────
Add-Type -AssemblyName System.IO.Compression.FileSystem

# ── Colour helpers ────────────────────────────────────────────────────────────
function Write-Step  { param([string]$Msg) Write-Host "`n==> $Msg"        -ForegroundColor Cyan   }
function Write-Ok    { param([string]$Msg) Write-Host "  [OK]  $Msg"      -ForegroundColor Green  }
function Write-Warn  { param([string]$Msg) Write-Host "  [WARN] $Msg"     -ForegroundColor Yellow }
function Write-Err   { param([string]$Msg) Write-Host "  [ERR]  $Msg"     -ForegroundColor Red    }
function Write-Info  { param([string]$Msg) Write-Host "  [INFO] $Msg"     -ForegroundColor Gray   }

# ── Help ──────────────────────────────────────────────────────────────────────
if ($Help) {
    Get-Help $MyInvocation.MyCommand.Path -Full
    exit 0
}

# ── Banner ────────────────────────────────────────────────────────────────────
Write-Host ''
Write-Host '╔══════════════════════════════════════════════════╗' -ForegroundColor Magenta
Write-Host '║      AIC Data Bundle Ingestion Script            ║' -ForegroundColor Magenta
Write-Host '╚══════════════════════════════════════════════════╝' -ForegroundColor Magenta
if ($DryRun) { Write-Warn 'DRY-RUN mode — no files will be written.' }

# ── Load .env ─────────────────────────────────────────────────────────────────
$envFile = Join-Path $PSScriptRoot '.env'
if (Test-Path $envFile) {
    Write-Info "Loading environment from $envFile"
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        # Skip blank lines and comment lines
        if ($line -and $line -notmatch '^\s*#') {
            $parts = $line -split '=', 2
            if ($parts.Count -eq 2) {
                $key   = $parts[0].Trim()
                $value = $parts[1].Trim().Trim('"').Trim("'")
                [System.Environment]::SetEnvironmentVariable($key, $value, 'Process')
            }
        }
    }
    Write-Ok '.env loaded.'
} else {
    Write-Info "No .env file found at $envFile — skipping."
}

# ── Resolve root paths ────────────────────────────────────────────────────────
$Root           = $PSScriptRoot
$KeyframeBase   = Join-Path $Root 'static\keyframes'
$VideoBase      = Join-Path $Root 'static\videos'
$FeatureBase    = Join-Path $Root 'data\features'
$MapBase        = Join-Path $Root 'data\map_keyframes'
$ProcessedDir   = Join-Path $Root 'data\inbox\processed'

foreach ($dir in @($KeyframeBase, $VideoBase, $FeatureBase, $MapBase, $ProcessedDir)) {
    if (-not (Test-Path $dir)) {
        if (-not $DryRun) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
            Write-Info "Created directory: $dir"
        } else {
            Write-Info "[DRY] Would create directory: $dir"
        }
    }
}

# ── Zip type detection ────────────────────────────────────────────────────────
# Returns @{ Type = 'KEYFRAMES'|'VIDEO'|'FEATURES'|'MAPS'|'UNKNOWN'; Dest = '<abs-path>' }
function Resolve-ZipType {
    param([string] $ZipPath)

    $name    = [System.IO.Path]::GetFileNameWithoutExtension($ZipPath).ToLower()
    $zipName = [System.IO.Path]::GetFileName($ZipPath)

    # 1. Detect by filename keywords
    if ($name -match 'map-keyframe|mapping') { return @{ Type = 'MAPS';      Dest = Join-Path $Root 'data\map_keyframes' } }
    if ($name -match 'keyframe|frame')       { return @{ Type = 'KEYFRAMES'; Dest = $KeyframeBase } }
    if ($name -match 'video')                { return @{ Type = 'VIDEO';     Dest = $VideoBase     } }
    if ($name -match 'feature|clip|npy')     { return @{ Type = 'FEATURES'; Dest = $FeatureBase   } }
    if ($name -match 'object')               { return @{ Type = 'OBJECTS';   Dest = Join-Path $Root 'data\objects' } }
    if ($name -match 'media-info')           { return @{ Type = 'MEDIAINFO'; Dest = Join-Path $Root 'data\media_info' } }

    # 2. Fall back: inspect the first 20 zip entries
    Write-Warn "Cannot determine type from filename '$zipName' — inspecting contents..."
    try {
        $archive = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
        $entries = @($archive.Entries | Select-Object -First 20)
        $archive.Dispose()

        $exts = $entries |
                ForEach-Object { [System.IO.Path]::GetExtension($_.FullName).ToLower() } |
                Sort-Object -Unique

        if ($exts -contains '.npy')                                                      { return @{ Type = 'FEATURES';  Dest = $FeatureBase  } }
        if ($exts -contains '.mp4' -or $exts -contains '.avi' -or $exts -contains '.mkv') { return @{ Type = 'VIDEO';    Dest = $VideoBase    } }
        if ($exts -contains '.jpg' -or $exts -contains '.jpeg' -or $exts -contains '.png') { return @{ Type = 'KEYFRAMES'; Dest = $KeyframeBase } }
        if ($exts -contains '.csv')                                                      { return @{ Type = 'MAPS';      Dest = $MapBase      } }
    } catch {
        Write-Warn "Could not inspect zip contents: $_"
    }

    return @{ Type = 'UNKNOWN'; Dest = $Root }
}

# ── Common prefix stripping ───────────────────────────────────────────────────
# Returns the common first-segment prefix shared by ALL entries, or '' if none.
function Get-CommonPrefix {
    param([System.IO.Compression.ZipArchiveEntry[]] $Entries)

    if ($Entries.Count -eq 0) { return '' }

    $firstSegments = @($Entries | ForEach-Object {
        $full = $_.FullName -replace '\\', '/'
        $idx  = $full.IndexOf('/')
        if ($idx -gt 0) { $full.Substring(0, $idx + 1) } else { '' }
    } | Sort-Object -Unique)

    if ($firstSegments.Count -eq 1 -and $firstSegments[0] -ne '') {
        return $firstSegments[0]   # e.g. "L01_V001/"
    }
    return ''
}

# ── Robust file extraction with retry on PermissionError ─────────────────────
function Invoke-ExtractEntry {
    param(
        [System.IO.Compression.ZipArchiveEntry] $Entry,
        [string] $DestPath,
        [switch] $SkipExisting
    )

    if ($SkipExisting -and (Test-Path $DestPath)) { return 'SKIPPED' }

    # Ensure destination directory exists
    $destDir = [System.IO.Path]::GetDirectoryName($DestPath)
    if (-not (Test-Path $destDir)) {
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
    }

    $maxAttempts = 3
    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        try {
            $stream = $Entry.Open()
            $fs     = [System.IO.File]::Open(
                $DestPath,
                [System.IO.FileMode]::Create,
                [System.IO.FileAccess]::Write,
                [System.IO.FileShare]::None
            )
            try   { $stream.CopyTo($fs) }
            finally { $fs.Dispose(); $stream.Dispose() }
            return 'OK'
        } catch [System.UnauthorizedAccessException] {
            if ($attempt -lt $maxAttempts) {
                Write-Warn "Permission error on '$DestPath' (attempt $attempt/$maxAttempts) — retrying in 1s..."
                Start-Sleep -Seconds 1
            } else {
                Write-Err "Permission error after $maxAttempts attempts: $DestPath"
                return 'ERROR'
            }
        } catch {
            Write-Err "Failed to extract '$DestPath': $_"
            return 'ERROR'
        }
    }
    return 'ERROR'
}

# ── Process a single zip file ─────────────────────────────────────────────────
function Invoke-ZipIngest {
    param([string] $ZipPath)

    $zipName  = [System.IO.Path]::GetFileName($ZipPath)
    $info     = Resolve-ZipType -ZipPath $ZipPath
    $zipType  = $info.Type
    $destBase = $info.Dest

    Write-Step "Processing: $zipName  (type: $zipType)"
    Write-Info "  Source : $ZipPath"
    Write-Info "  Dest   : $destBase"

    if ($zipType -eq 'UNKNOWN') {
        Write-Warn "Could not determine zip type for '$zipName' — extracting to project root."
    }

    # Open archive
    try {
        $archive = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
    } catch {
        Write-Err "Cannot open zip '$ZipPath': $_"
        return
    }

    $allEntries = @($archive.Entries)
    $prefix     = Get-CommonPrefix -Entries $allEntries

    if ($prefix) { Write-Info "Stripping common prefix: '$prefix'" }

    # Filter out directory-only entries (entries whose path ends with '/')
    $fileEntries = $allEntries | Where-Object {
        -not $_.FullName.EndsWith('/') -and -not $_.FullName.EndsWith('\')
    }
    $total = $fileEntries.Count
    Write-Info "  Entries : $($allEntries.Count) total, $total files"

    # ── DRY-RUN ───────────────────────────────────────────────────────────────
    if ($DryRun) {
        $preview = $fileEntries | Select-Object -First 20
        Write-Host "`n  [DRY] Would extract (showing first 20 of $total):" -ForegroundColor DarkCyan
        foreach ($e in $preview) {
            $rel = $e.FullName
            if ($prefix -and $rel.StartsWith($prefix)) { $rel = $rel.Substring($prefix.Length) }
            $dPath = Join-Path $destBase $rel
            Write-Host "        $dPath" -ForegroundColor DarkGray
        }
        if ($total -gt 20) {
            Write-Host "        ... and $($total - 20) more." -ForegroundColor DarkGray
        }
        $archive.Dispose()
        return
    }

    # ── EXTRACT ───────────────────────────────────────────────────────────────
    $countOk      = 0
    $countSkipped = 0
    $countErr     = 0
    $idx          = 0

    foreach ($entry in $fileEntries) {
        $idx++

        # Build destination path, stripping common prefix
        $rel = $entry.FullName -replace '\\', '/'
        if ($prefix -and $rel.StartsWith($prefix)) {
            $rel = $rel.Substring($prefix.Length)
        }
        $destPath = Join-Path $destBase ($rel -replace '/', '\')

        # In-place progress counter (overwrite same line)
        Write-Host "`r  Extracted $idx/$total files..." -NoNewline -ForegroundColor DarkCyan

        $result = Invoke-ExtractEntry `
            -Entry       $entry `
            -DestPath    $destPath `
            -SkipExisting:(-not $Force)

        switch ($result) {
            'OK'      { $countOk++      }
            'SKIPPED' { $countSkipped++ }
            'ERROR'   { $countErr++     }
        }
    }

    $archive.Dispose()

    # Clear progress line
    Write-Host "`r$(' ' * 60)`r" -NoNewline

    # Per-zip summary
    if ($countErr -gt 0) {
        Write-Warn "Done: $countOk extracted, $countSkipped skipped, $countErr errors  [$zipName]"
    } else {
        Write-Ok   "Done: $countOk extracted, $countSkipped skipped, $countErr errors  [$zipName]"
    }

    # Move processed zip to processed/ sub-directory
    $destZip = Join-Path $ProcessedDir $zipName
    try {
        Move-Item -Path $ZipPath -Destination $destZip -Force
        Write-Info "Moved to processed/: $zipName"
    } catch {
        Write-Warn "Could not move '$zipName' to processed/: $_"
    }
}

# ── Collect zip files ─────────────────────────────────────────────────────────
Write-Step 'Collecting zip files...'

$zipFiles = @()

if ($ZipFile) {
    # Single-file mode
    $absZip = if ([System.IO.Path]::IsPathRooted($ZipFile)) { $ZipFile } else { Join-Path $Root $ZipFile }
    if (-not (Test-Path $absZip)) {
        Write-Err "Zip file not found: $absZip"
        exit 1
    }
    $zipFiles = @($absZip)
    Write-Info "Single-file mode: $absZip"
} else {
    # Directory scan mode
    $absZipDir = if ([System.IO.Path]::IsPathRooted($ZipDir)) { $ZipDir } else { Join-Path $Root $ZipDir }
    if (-not (Test-Path $absZipDir)) {
        Write-Err "ZipDir not found: $absZipDir"
        exit 1
    }
    $zipFiles = @(
        Get-ChildItem -Path $absZipDir -Filter '*.zip' -File |
        Where-Object  { $_.FullName -notlike "*\processed\*" } |
        Select-Object -ExpandProperty FullName
    )
    Write-Info "Scanning   : $absZipDir"
    Write-Info "Found $($zipFiles.Count) zip file(s)."
}

if ($zipFiles.Count -eq 0) {
    Write-Warn 'No zip files found — nothing to do.'
    exit 0
}

# ── Process each zip ──────────────────────────────────────────────────────────
foreach ($zip in $zipFiles) {
    Invoke-ZipIngest -ZipPath $zip
}

# ── Post-ingestion inventory ──────────────────────────────────────────────────
Write-Step 'Post-ingestion inventory'

$kfDirs    = if (Test-Path $KeyframeBase) { @(Get-ChildItem -Path $KeyframeBase -Directory).Count }         else { 0 }
$vidFiles  = if (Test-Path $VideoBase)    { @(Get-ChildItem -Path $VideoBase    -File    ).Count }         else { 0 }
$featFiles = if (Test-Path $FeatureBase)  { @(Get-ChildItem -Path $FeatureBase  -File -Filter '*.npy').Count } else { 0 }
$mapFiles  = if (Test-Path $MapBase)      { @(Get-ChildItem -Path $MapBase      -File    ).Count }         else { 0 }

Write-Host ''
Write-Host '  ┌─────────────────────────────────────────┐' -ForegroundColor DarkCyan
Write-Host "  │  Keyframe dirs   : $($kfDirs.ToString().PadLeft(6))                │" -ForegroundColor DarkCyan
Write-Host "  │  Video files     : $($vidFiles.ToString().PadLeft(6))                │" -ForegroundColor DarkCyan
Write-Host "  │  Feature files   : $($featFiles.ToString().PadLeft(6))                │" -ForegroundColor DarkCyan
Write-Host "  │  Map files       : $($mapFiles.ToString().PadLeft(6))                │" -ForegroundColor DarkCyan
Write-Host '  └─────────────────────────────────────────┘' -ForegroundColor DarkCyan

# ── Optional FAISS index rebuild ──────────────────────────────────────────────
if ($RebuildIndex) {
    Write-Step 'Rebuilding FAISS index...'

    $venvPython  = Join-Path $Root '.venv\Scripts\python.exe'
    $buildScript = Join-Path $Root 'build_index.py'

    if (-not (Test-Path $venvPython)) {
        Write-Warn "Virtual-env Python not found at: $venvPython"
        Write-Warn 'Falling back to system python.'
        $pythonExe = 'python'
    } else {
        $pythonExe = $venvPython
        Write-Info "Using venv Python: $venvPython"
    }

    if (-not (Test-Path $buildScript)) {
        Write-Err "build_index.py not found at: $buildScript"
    } else {
        Write-Info "Running: $pythonExe build_index.py"
        try {
            $output = & $pythonExe $buildScript 2>&1
            $output | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
            if ($LASTEXITCODE -eq 0) {
                Write-Ok 'Index rebuild completed successfully.'
            } else {
                Write-Err "build_index.py exited with code $LASTEXITCODE."
            }
        } catch {
            Write-Err "Failed to run build_index.py: $_"
        }
    }
}

# ── Next-step hints ───────────────────────────────────────────────────────────
Write-Host ''
Write-Host '─────────────────────────────────────────────────────' -ForegroundColor DarkGray
Write-Host '  Next steps:' -ForegroundColor White
Write-Host '    Verify extractions : Get-ChildItem static\keyframes -Recurse | Measure-Object' -ForegroundColor Gray
Write-Host '    Rebuild FAISS index: .\ingest.ps1 -RebuildIndex' -ForegroundColor Gray
Write-Host '    Start search server: .\search.ps1' -ForegroundColor Gray
Write-Host '─────────────────────────────────────────────────────' -ForegroundColor DarkGray
Write-Host ''
