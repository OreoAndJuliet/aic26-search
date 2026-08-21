<#
Backup Milvus Docker volume to a compressed archive on the host.

Usage:
  pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\backup_milvus.ps1 -BackupDir $env:TEMP\milvus_backups -Keep 7

Parameters:
  -BackupDir   Directory on the host where backup archive will be written (default: temp directory)
  -ArchiveName Optional archive name (default: milvus_backup_<timestamp>.tgz)
  -VolumeName  Docker volume name to backup (default: aic_milvus_data)
  -Keep        Number of recent backups to keep (default: 7). Older archives will be removed.
  -NoChecksum  If set, skip generating a SHA256 checksum file for the archive.
#>

[CmdletBinding()]
param(
    [string]$BackupDir = $(Join-Path $env:TEMP "milvus_backups"),
    [string]$ArchiveName = $("milvus_backup_$(Get-Date -Format 'yyyyMMddHHmmss').tgz"),
    [string]$VolumeName = "aic_milvus_data",
    [int]$Keep = 7,
    [switch]$NoChecksum
)

$ErrorActionPreference = 'Stop'
function Write-Info($m){ Write-Host "[INFO] $m" -ForegroundColor Cyan }
function Write-Warn($m){ Write-Host "[WARN] $m" -ForegroundColor Yellow }
function Write-Err($m){ Write-Host "[ERROR] $m" -ForegroundColor Red }

try {
    $backupDirResolved = (Resolve-Path -Path $BackupDir -ErrorAction SilentlyContinue)
    if (-not $backupDirResolved) {
        Write-Info "Backup directory $BackupDir does not exist — creating."
        New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
        $backupDirResolved = Resolve-Path -Path $BackupDir
    }
    $backupDirPath = $backupDirResolved.ProviderPath
    $archivePath = Join-Path $backupDirPath $ArchiveName

    # Auto-detect active Docker volume if default was used
    if (-not $PSBoundParameters.ContainsKey('VolumeName')) {
        try {
            $dockerVolumes = @(docker volume ls -q 2>$null)
            $possibleVolumes = @("backup_milvus_data", "aic_milvus_data", "milvus_data", "project25_milvus_data")
            foreach ($v in $possibleVolumes) {
                if ($dockerVolumes -contains $v) {
                    $VolumeName = $v
                    Write-Info "Auto-detected active Milvus volume: '$VolumeName'"
                    break
                }
            }
        } catch {}
    }

    Write-Info "Backing up Docker volume '$VolumeName' to archive: $archivePath"

    # Run a short-lived container that tars the volume contents into the host-mounted backup dir
    $tarCmd = "tar czf /backup/$ArchiveName -C /data ."
    Write-Info "Running: docker run --rm -v ${VolumeName}:/data -v ${backupDirPath}:/backup alpine sh -c '$tarCmd'"

    & docker run --rm -v "${VolumeName}:/data" -v "${backupDirPath}:/backup" alpine sh -c $tarCmd
    if ($LASTEXITCODE -ne 0) { throw "docker run returned exit code $LASTEXITCODE" }

    Write-Info "Backup completed: $archivePath"
    $size = (Get-Item -Path $archivePath).Length
    Write-Host "Archive size: $size bytes"

    # Generate checksum unless disabled
    if (-not $NoChecksum) {
        Write-Info "Generating SHA256 checksum for archive"
        try {
            $hash = Get-FileHash -Path $archivePath -Algorithm SHA256
            $sumFile = "$archivePath.sha256"
            "$($hash.Hash)  $ArchiveName" | Out-File -FilePath $sumFile -Encoding ASCII
            Write-Info "Checksum written to: $sumFile"
        } catch {
            Write-Warn "Could not compute checksum: $_"
        }
    } else {
        Write-Warn "Skipping checksum generation (-NoChecksum set)"
    }

    # Retention: keep only the $Keep most recent backup archives
    if ($Keep -gt 0) {
        Write-Info "Applying retention policy: keep $Keep most recent backups in $backupDirPath"
        $pattern = 'milvus_backup_*.tgz'
        $archives = Get-ChildItem -Path $backupDirPath -Filter $pattern | Sort-Object LastWriteTime -Descending
        if ($archives.Count -gt $Keep) {
            $toDelete = $archives | Select-Object -Skip $Keep
            foreach ($a in $toDelete) {
                $delPath = $a.FullName
                Write-Info "Removing old archive: $delPath"
                try { Remove-Item -Path $delPath -Force -ErrorAction Stop } catch { Write-Warn "Failed to remove $($delPath): $_" }
                # remove checksum sibling if exists
                $sumSibling = "$delPath.sha256"
                if (Test-Path $sumSibling) { Remove-Item -Path $sumSibling -Force -ErrorAction SilentlyContinue }
            }
        } else {
            Write-Info "No old archives to remove (found $($archives.Count) archives)."
        }
    }

    Write-Info "Backup operation completed successfully."
    exit 0
} catch {
    Write-Err "Backup failed: $_"
    exit 1
}
