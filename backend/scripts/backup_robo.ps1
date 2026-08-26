<#
.SYNOPSIS
    Robocopy & Zip High-Speed Backup Script for AIC 2026 Project.

.DESCRIPTION
    Creates clean, verified snapshots or compressed zip archives of the AIC 2026 backend,
    including algorithms, indices, metadata, gazetteers, and configurations while excluding
    heavy transient artifacts (.venv, __pycache__, .git).

.PARAMETER Source
    Source directory to backup. Default: Repository root.

.PARAMETER DestinationRoot
    Target directory where backups will be stored. Default: $env:USERPROFILE\backups\aic_project

.PARAMETER IncludeStatic
    If specified, includes raw keyframe images and videos in static/.

.PARAMETER IncludeVenv
    If specified, includes the .venv Python virtual environment.

.PARAMETER AsZip
    If specified, creates a compressed .zip archive instead of a folder snapshot.

.PARAMETER Keep
    Number of recent backups to retain. Older backups will be automatically purged. Default: 5.

.PARAMETER NoChecksum
    If specified, skips SHA256 integrity checksum generation.
#>

[CmdletBinding()]
param (
    [string]$Source = (Resolve-Path "$PSScriptRoot\..").ProviderPath,
    [string]$DestinationRoot = (Join-Path $env:USERPROFILE "backups\aic_project"),
    [switch]$IncludeStatic,
    [switch]$IncludeVenv,
    [switch]$IncludeFeatures,
    [switch]$IncludeObjects,
    [switch]$AsZip,
    [int]$Keep = 5,
    [switch]$NoChecksum
)

$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Write-Info($msg) { Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Write-Success($msg) { Write-Host "[SUCCESS] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Err($msg) { Write-Host "[ERROR] $msg" -ForegroundColor Red }

try {
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    if (-not (Test-Path $DestinationRoot)) {
        New-Item -ItemType Directory -Path $DestinationRoot -Force | Out-Null
    }
    $resolvedDest = (Resolve-Path $DestinationRoot).ProviderPath

    Write-Info "================================================================="
    Write-Info "            AIC 2026 BACKUP ENGINE (ROBOCOPY & ZIP)              "
    Write-Info "================================================================="
    Write-Info "Source:      $Source"
    Write-Info "Destination: $resolvedDest"
    Write-Info "Timestamp:   $timestamp"

    $targetFolder = Join-Path $resolvedDest "aic_snapshot_$timestamp"

    # Exclude directories
    $excludeDirs = @(".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".idea", ".vscode", "scratch", ".system_generated", "keyframes", "videos", "media", "backups", "New folder")
    if (-not $IncludeVenv) {
        $excludeDirs += ".venv"
    }
    if (-not $IncludeStatic) {
        $excludeDirs += "static"
    }
    # Features are now always included intact by default
    # if (-not $IncludeFeatures) {
    #     $excludeDirs += "features"
    # }
    if (-not $IncludeObjects) {
        $excludeDirs += "objects"
    }

    $excludeFiles = @("*.pyc", "*.pyo", "*.pyd", "*.tmp", "*.log", "check_milvus.*")

    Write-Info "Running multi-threaded Robocopy snapshot (MT:8)..."

    $roboArgs = @(
        $Source,
        $targetFolder,
        "/E",
        "/MT:8",
        "/R:1",
        "/W:1",
        "/NP",
        "/NDL",
        "/NFL"
    )

    if ($excludeDirs.Count -gt 0) {
        $roboArgs += "/XD"
        $roboArgs += $excludeDirs
    }

    if ($excludeFiles.Count -gt 0) {
        $roboArgs += "/XF"
        $roboArgs += $excludeFiles
    }

    $process = Start-Process -FilePath "robocopy.exe" -ArgumentList $roboArgs -Wait -NoNewWindow -PassThru
    # Robocopy exit codes 0-7 indicate success/copy completed
    if ($process.ExitCode -ge 8) {
        throw "Robocopy failed with exit code $($process.ExitCode)"
    }

    Write-Success "Robocopy snapshot completed successfully: $targetFolder"

    # Compress to ZIP if requested
    if ($AsZip) {
        $zipFile = Join-Path $resolvedDest "aic_backup_$timestamp.zip"
        Write-Info "Compressing snapshot into ZIP archive: $zipFile..."
        Compress-Archive -Path "$targetFolder\*" -DestinationPath $zipFile -CompressionLevel Optimal -Force
        Remove-Item -Path $targetFolder -Recurse -Force
        Write-Success "Compressed archive created: $zipFile"
        $finalTarget = $zipFile
    } else {
        $finalTarget = $targetFolder
    }

    # Generate SHA256 Checksum
    if (-not $NoChecksum) {
        Write-Info "Generating SHA256 integrity checksum..."
        if ($AsZip) {
            $hash = (Get-FileHash -Path $finalTarget -Algorithm SHA256).Hash
            $hashFile = "$finalTarget.sha256"
            "$hash  $(Split-Path $finalTarget -Leaf)" | Out-File -FilePath $hashFile -Encoding ASCII
            Write-Success "Checksum written to: $hashFile"
        } else {
            $manifest = @{}
            $allFiles = Get-ChildItem -Path $finalTarget -Recurse -File
            foreach ($f in $allFiles) {
                $rel = $f.FullName.Substring($finalTarget.Length).TrimStart([char[]]@('\', '/'))
                $manifest[$rel] = (Get-FileHash -Path $f.FullName -Algorithm SHA256).Hash
            }
            $manifestJson = Join-Path $finalTarget "backup_manifest.json"
            $manifest | ConvertTo-Json -Depth 3 | Out-File -FilePath $manifestJson -Encoding UTF8
            Write-Success "Manifest written to: $manifestJson ($($allFiles.Count) files indexed)"
        }
    }

    # Retention Policy
    if ($Keep -gt 0) {
        Write-Info "Applying retention policy (keeping $Keep most recent backups)..."
        if ($AsZip) {
            $oldZips = Get-ChildItem -Path $resolvedDest -Filter "aic_backup_*.zip" | Sort-Object LastWriteTime -Descending
            if ($oldZips.Count -gt $Keep) {
                $toDelete = $oldZips | Select-Object -Skip $Keep
                foreach ($item in $toDelete) {
                    Write-Info "Removing old archive: $($item.Name)"
                    Remove-Item -Path $item.FullName -Force -ErrorAction SilentlyContinue
                    Remove-Item -Path "$($item.FullName).sha256" -Force -ErrorAction SilentlyContinue
                }
            }
        } else {
            $oldFolders = Get-ChildItem -Path $resolvedDest -Filter "aic_snapshot_*" | Where-Object { $_.PSIsContainer } | Sort-Object LastWriteTime -Descending
            if ($oldFolders.Count -gt $Keep) {
                $toDelete = $oldFolders | Select-Object -Skip $Keep
                foreach ($item in $toDelete) {
                    Write-Info "Removing old snapshot folder: $($item.Name)"
                    Remove-Item -Path $item.FullName -Recurse -Force -ErrorAction SilentlyContinue
                }
            }
        }
    }

    Write-Info "================================================================="
    Write-Success "Backup Operation Completed Successfully!"
    Write-Info "Target: $finalTarget"
    Write-Info "================================================================="
    exit 0

} catch {
    Write-Err "Backup Operation Failed: $_"
    exit 1
}
