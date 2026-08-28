Write-Host "Starting backend server..."
$serverJob = Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "-m uvicorn main:app --host 0.0.0.0 --port 8000" -NoNewWindow -PassThru

Write-Host "Waiting for port 8000 to become active..."
$isReady = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 2
    try {
        $tcpClient = New-Object System.Net.Sockets.TcpClient
        $connect = $tcpClient.BeginConnect("127.0.0.1", 8000, $null, $null)
        $success = $connect.AsyncWaitHandle.WaitOne(500, $false)
        if ($success -and $tcpClient.Connected) {
            $isReady = $true
            $tcpClient.Close()
            break
        }
    } catch {}
}

if (-not $isReady) {
    Write-Host "Failed to start server within timeout."
    Stop-Process -Id $serverJob.Id -Force
    exit 1
}

Write-Host "Server is up! Waiting 20 more seconds for models to warm up..."
Start-Sleep -Seconds 20

Write-Host "Running solve_exam_p2.py..."
& ".\.venv\Scripts\python.exe" scripts\solve_exam_p2.py

Write-Host "Stopping backend server..."
Stop-Process -Id $serverJob.Id -Force
Write-Host "Done!"
