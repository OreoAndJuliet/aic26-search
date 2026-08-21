<#
Restore Milvus Docker volume from a previously created archive.

Usage:
  pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\restore_milvus.ps1 -ArchivePath C:\tmp\milvus_backup_20260814....tgz

Parameters:
  -ArchivePath  Full path to the backup archive (.tgz)
  -VolumeName   Docker volume name to restore into (default: project25_milvus_data)
  -Force        Skip interactive confirmation (use with care)
  -SkipChecksum Skip checksum verification (not recommended)
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string]$ArchivePath,
    [string]$VolumeName = "aic_milvus_data",
    [switch]$Force,
    [switch]$SkipChecksum
)

$ErrorActionPreference = 'Stop'
function Write-Info($m){ Write-Host "[INFO] $m" -ForegroundColor Cyan }
function Write-Warn($m){ Write-Host "[WARN] $m" -ForegroundColor Yellow }
function Write-Err($m){ Write-Host "[ERROR] $m" -ForegroundColor Red }

try {
    if (-not (Test-Path -Path $ArchivePath)) { throw "Archive not found: $ArchivePath" }
    $archiveFull = (Resolve-Path $ArchivePath).ProviderPath

    # Auto-detect active Docker volume if default was used
    if (-not $PSBoundParameters.ContainsKey('VolumeName')) {
        try {
            $dockerVolumes = @(docker volume ls -q 2>$null)
            $possibleVolumes = @("backup_milvus_data", "aic_milvus_data", "milvus_data", "project25_milvus_data")
            foreach ($v in $possibleVolumes) {
                if ($dockerVolumes -contains $v) {
                    $VolumeName = $v
                    Write-Info "Auto-detected target Milvus volume: '$VolumeName'"
                    break
                }
            }
        } catch {}
    }

    # Verify checksum if present
    $sumFile = "$archiveFull.sha256"
    if (-not $SkipChecksum -and (Test-Path -Path $sumFile)) {
        Write-Info "Verifying checksum using $sumFile"
        try {
            $expected = (Get-Content -Path $sumFile -Raw).Trim().Split()[0]
            $actual = (Get-FileHash -Path $archiveFull -Algorithm SHA256).Hash
            if ($expected -ne $actual) { throw "Checksum mismatch: expected $expected but got $actual" }
            Write-Info "Checksum OK"
        } catch {
            Write-Err "Checksum verification failed: $_"
            if (-not $Force) { exit 3 } else { Write-Warn "Continuing due to -Force" }
        }
    } elseif (-not (Test-Path -Path $sumFile)) {
        Write-Warn "No checksum file found next to archive. Use -SkipChecksum to bypass or generate checksum when creating backups."
    } else {
        Write-Warn "Skipping checksum verification (-SkipChecksum set)"
    }

    if (-not $Force) {
        Write-Warn "This will stop any running Milvus container, remove the Docker volume '$VolumeName' and restore its contents from the archive."
        $confirm = Read-Host "Type YES to continue"
        if ($confirm -ne 'YES') { Write-Err "Aborted by user."; exit 2 }
    }

    # Try to stop Milvus service (docker compose if available)
    Write-Info "Stopping Milvus container(s) if running"
    try {
        if (Get-Command 'docker' -ErrorAction SilentlyContinue) {
            # Prefer compose if project compose file is present
            if (Test-Path -Path "docker-compose.yml") {
                & docker compose stop milvus 2>$null
            } else {
                & docker stop project25-milvus-1 2>$null
            }
        }
    } catch {
        Write-Warn "Could not stop container cleanly: $_ — continuing"
    }

    # Remove volume if exists
    Write-Info "Removing existing Docker volume '$VolumeName' (if present)"
    try {
        & docker volume rm $VolumeName 2>$null
    } catch {
        Write-Warn "Could not remove volume (it may not exist or is in use). Attempting to clear contents instead."
        # attempt to delete contents inside volume
        try {
            & docker run --rm -v "${VolumeName}:/data" alpine sh -c "rm -rf /data/* || true"
        } catch {
            Write-Warn "Failed to clear volume contents: $_"
        }
    }

    # Ensure volume exists
    Write-Info "Creating Docker volume '$VolumeName'"
    & docker volume create $VolumeName | Out-Null

    # Extract archive into volume
    $archiveName = Split-Path $archiveFull -Leaf
    $archiveDir = Split-Path $archiveFull -Parent
    Write-Info "Restoring archive $archiveFull into volume $VolumeName"
    $untarCmd = "tar xzf /backup/$archiveName -C /data"
    & docker run --rm -v "${VolumeName}:/data" -v "${archiveDir}:/backup" alpine sh -c $untarCmd
    if ($LASTEXITCODE -ne 0) { throw "docker run returned exit code $LASTEXITCODE during restore" }

    Write-Info "Restore completed. Start Milvus with: docker compose up -d milvus (or .\scripts\dev.ps1 docker -Expand -DockerAction milvus)"
    exit 0
} catch {
    Write-Err "Restore failed: $_"
    exit 1
}
