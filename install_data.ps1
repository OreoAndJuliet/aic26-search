<#
.SYNOPSIS
    AIC 2026 - Bộ cài đặt dữ liệu tự động 1-Click (All-in-One Data Installer).
.DESCRIPTION
    Tự động quét các file .zip trong backend/data/inbox (hoặc đường dẫn chỉ định),
    giải nén đúng vào vị trí (Keyframes, Features, Maps, Metadata, OCR) và tự động
    chạy build_index.py để tái tạo Vector Index cho hệ thống tìm kiếm.
.EXAMPLE
    .\install_data.ps1
    .\install_data.ps1 -SourceDir "D:\AIC_Downloads"
#>

[CmdletBinding()]
param(
    [string]$SourceDir = "",
    [switch]$SkipIndex,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8


# Xác định đường dẫn gốc
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$BackendDir = Join-Path $ScriptDir "backend"

if (-not (Test-Path $BackendDir)) {
    Write-Host "[LỖI] Không tìm thấy thư mục backend! Hãy chạy script từ thư mục gốc của project." -ForegroundColor Red
    exit 1
}

$InboxDir = if ($SourceDir -and (Test-Path $SourceDir)) { $SourceDir } else { Join-Path $BackendDir "data\inbox" }
$KeyframesDir = Join-Path $BackendDir "static\keyframes"
$FeaturesDir = Join-Path $BackendDir "data\features"
$MapDir = Join-Path $BackendDir "data\map_keyframes"
$MediaInfoDir = Join-Path $BackendDir "data\media_info"
$OcrDir = Join-Path $BackendDir "data\ocr"

# Tạo các thư mục đích nếu chưa có
@($InboxDir, $KeyframesDir, $FeaturesDir, $MapDir, $MediaInfoDir, $OcrDir) | ForEach-Object {
    if (-not (Test-Path $_)) { New-Item -ItemType Directory -Path $_ -Force | Out-Null }
}

Write-Host "`n=================================================================" -ForegroundColor Cyan
Write-Host "   AIC 2026 SEARCH - BỘ CÀI ĐẶT DỮ LIỆU TỰ ĐỘNG (1-CLICK INGEST)  " -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " Thư mục quét Zip: $InboxDir" -ForegroundColor Gray
Write-Host " Thư mục Keyframes: $KeyframesDir" -ForegroundColor Gray
Write-Host " Thư mục Features:  $FeaturesDir" -ForegroundColor Gray
Write-Host " Thư mục Maps:      $MapDir" -ForegroundColor Gray
Write-Host "-----------------------------------------------------------------" -ForegroundColor Gray

# 1. Tìm kiếm tất cả file Zip
$zipFiles = Get-ChildItem -Path $InboxDir -Filter "*.zip" -File

if ($zipFiles.Count -eq 0) {
    Write-Host "[CẢNH BÁO] Không tìm thấy file .zip nào trong: $InboxDir" -ForegroundColor Yellow
    Write-Host "-> Hãy copy các file Zip (Keyframes_L*.zip, clip-features-*.zip, map-keyframes-*.zip) vào thư mục này rồi chạy lại script!" -ForegroundColor White
} else {
    Write-Host "Tìm thấy $($zipFiles.Count) file .zip cần xử lý:`n" -ForegroundColor Green
    
    Add-Type -AssemblyName System.IO.Compression.FileSystem

    foreach ($zip in $zipFiles) {
        $name = $zip.Name.ToLower()
        $targetDir = ""
        $typeLabel = ""

        if ($name -match "keyframe") {
            $targetDir = $KeyframesDir
            $typeLabel = "Keyframes (Ảnh hiển thị)"
        } elseif ($name -match "feature|clip|vector") {
            $targetDir = $FeaturesDir
            $typeLabel = "Features (Vector AI)"
        } elseif ($name -match "map") {
            $targetDir = $MapDir
            $typeLabel = "Map Keyframes (CSV ánh xạ)"
        } elseif ($name -match "media|info|metadata") {
            $targetDir = $MediaInfoDir
            $typeLabel = "Media Metadata"
        } elseif ($name -match "ocr") {
            $targetDir = $OcrDir
            $typeLabel = "OCR Text"
        } else {
            $targetDir = Join-Path $BackendDir "data\other"
            $typeLabel = "Dữ liệu bổ trợ"
        }

        Write-Host " [ĐANG GIẢI NÉN] " -NoNewline -ForegroundColor Yellow
        Write-Host "$($zip.Name) " -NoNewline -ForegroundColor White
        Write-Host "-> $typeLabel" -ForegroundColor Cyan

        try {
            [System.IO.Compression.ZipFile]::ExtractToDirectory($zip.FullName, $targetDir, $true)
            Write-Host "   -> Thành công!" -ForegroundColor Green
        } catch {
            Write-Host "   -> Lỗi giải nén: $($_.Exception.Message)" -ForegroundColor Red
        }
    }

    # Dọn dẹp cấu trúc thư mục lồng nhau nếu zip tạo thêm 1 cấp thư mục
    # Ví dụ static/keyframes/Keyframes_L22/L22_V001 -> static/keyframes/L22_V001
    $nestedKeyframeDirs = Get-ChildItem -Path $KeyframesDir -Directory | Where-Object { $_.Name -match "^keyframes_l\d+" -or $_.Name -match "^keyframes" }
    foreach ($nested in $nestedKeyframeDirs) {
        Get-ChildItem -Path $nested.FullName -Directory | ForEach-Object {
            $dest = Join-Path $KeyframesDir $_.Name
            if (-not (Test-Path $dest)) {
                Move-Item -Path $_.FullName -Destination $KeyframesDir -Force
            } else {
                Copy-Item -Path "$($_.FullName)\*" -Destination $dest -Recurse -Force
                Remove-Item -Path $_.FullName -Recurse -Force
            }
        }
        if ((Get-ChildItem -Path $nested.FullName).Count -eq 0) {
            Remove-Item -Path $nested.FullName -Force
        }
    }
}

# 2. Chạy Rebuild FAISS Vector Index
if (-not $SkipIndex) {
    Write-Host "`n-----------------------------------------------------------------" -ForegroundColor Gray
    Write-Host " [BƯỚC TIẾP THEO] Tái tạo FAISS Vector Index (build_index.py)..." -ForegroundColor Yellow
    
    $pythonExe = Join-Path $BackendDir ".venv\Scripts\python.exe"
    if (-not (Test-Path $pythonExe)) {
        $pythonExe = "python"
    }

    $buildScript = Join-Path $BackendDir "build_index.py"
    if (Test-Path $buildScript) {
        Push-Location $BackendDir
        try {
            & $pythonExe $buildScript
            Write-Host "`n [HOÀN TẤT] Dữ liệu đã được nạp và Index thành công!" -ForegroundColor Green
        } catch {
            Write-Host "`n [LỖI] Không thể chạy build_index.py: $($_.Exception.Message)" -ForegroundColor Red
        } finally {
            Pop-Location
        }
    } else {
        Write-Host "[CẢNH BÁO] Không tìm thấy backend/build_index.py" -ForegroundColor Yellow
    }
}

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " BẠN ĐÃ SẴN SÀNG! Khởi động hệ thống bằng lệnh: .\start.bat" -ForegroundColor Cyan
Write-Host "=================================================================`n" -ForegroundColor Cyan
