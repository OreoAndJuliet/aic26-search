# Cross-Platform Compatibility Utilities
# Provides platform-agnostic functions for file operations and command execution

$ErrorActionPreference = "Stop"

function Get-Platform {
    $isWindows = [System.Environment]::OSVersion.Platform -eq "Win32NT"
    if ($isWindows) {
        return "Windows"
    }
    return "Unix"
}

function Get-CopyCommand {
    $platform = Get-Platform
    if ($platform -eq "Windows") {
        return @{
            Command = "robocopy"
            ArgsTemplate = {
                param($source, $destination, $options)
                @($source, $destination) + $options
            }
        }
    } else {
        # Unix-like systems use rsync
        return @{
            Command = "rsync"
            ArgsTemplate = {
                param($source, $destination, $options)
                @("-av", "--progress", $source, $destination)
            }
        }
    }
}

function Get-PowerShellCommand {
    # Cross-platform PowerShell detection
    $pwshAvailable = Get-Command "pwsh" -ErrorAction SilentlyContinue
    if ($pwshAvailable) {
        return "pwsh"
    }
    
    # Fallback to Windows PowerShell
    $powershellAvailable = Get-Command "powershell" -ErrorAction SilentlyContinue
    if ($powershellAvailable) {
        return "powershell"
    }
    
    throw "Neither pwsh nor powershell found in PATH"
}

function Invoke-CrossPlatformCopy {
    param(
        [string]$Source,
        [string]$Destination,
        [string[]]$Options = @(),
        [switch]$DryRun
    )
    
    $platform = Get-Platform
    $copyTool = Get-CopyCommand
    
    if ($platform -eq "Windows") {
        # Robocopy-specific options
        $robocopyOptions = @("/E", "/Z", "/FFT", "/R:3", "/W:5", "/NP", "/NDL", "/NFL")
        if ($DryRun) {
            $robocopyOptions += "/L"
        }
        $robocopyOptions += $Options
        
        $logFile = Join-Path $Destination "copy.log"
        $robocopyOptions += "/LOG:$logFile"
        
        Write-Host "Using robocopy to copy from $Source to $Destination"
        & robocopy $Source $Destination @robocopyOptions
        
        # Robocopy returns various exit codes for different conditions
        # 0 = No files were copied
        # 1 = Files were copied successfully
        # 2 = Some files were skipped
        # 4+ = Errors occurred
        if ($LASTEXITCODE -ge 8) {
            throw "Robocopy failed with exit code $LASTEXITCODE"
        }
    } else {
        # Unix rsync
        $rsyncOptions = @("-av", "--progress")
        if ($DryRun) {
            $rsyncOptions += "--dry-run"
        }
        $rsyncOptions += $Options
        
        Write-Host "Using rsync to copy from $Source to $Destination"
        & rsync @rsyncOptions $Source $Destination
        
        if ($LASTEXITCODE -ne 0) {
            throw "Rsync failed with exit code $LASTEXITCODE"
        }
    }
}

function Get-TempDirectory {
    # Cross-platform temp directory
    if ($IsWindows -or $null -eq $IsWindows) {
        return $env:TEMP
    } else {
        return "/tmp"
    }
}

function Join-PathSafe {
    param(
        [string[]]$PathParts
    )
    
    # Use PowerShell's Join-Path which is cross-platform
    return Join-Path @PathParts
}

Export-ModuleMember -Function Get-Platform, Get-CopyCommand, Get-PowerShellCommand, Invoke-CrossPlatformCopy, Get-TempDirectory, Join-PathSafe