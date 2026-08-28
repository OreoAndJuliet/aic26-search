# Aggressively kill anything on port 8000
$conns = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if ($conns) {
    foreach ($c in $conns) {
        $pidToKill = $c.OwningProcess
        if ($pidToKill -gt 0) {
            Write-Host "Killing PID $pidToKill on port 8000..."
            Stop-Process -Id $pidToKill -Force -ErrorAction SilentlyContinue
        }
    }
    Start-Sleep -Seconds 3
}

Write-Host "Starting backend server with patched config..."
Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "-m uvicorn main:app --host 0.0.0.0 --port 8000" -NoNewWindow -PassThru

Write-Host "Waiting for port 8000..."
$isReady = $false
for ($i = 0; $i -lt 90; $i++) {
    Start-Sleep -Seconds 2
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $conn = $tcp.BeginConnect("127.0.0.1", 8000, $null, $null)
        $ok = $conn.AsyncWaitHandle.WaitOne(500, $false)
        if ($ok -and $tcp.Connected) { $isReady = $true; $tcp.Close(); break }
    } catch {}
}
if (-not $isReady) { Write-Host "Server failed to start"; exit 1 }

Write-Host "Server ready! Waiting 15s for model warmup..."
Start-Sleep -Seconds 15

Write-Host "Running improved solve_exam_p2.py..."
& ".\.venv\Scripts\python.exe" scripts\solve_exam_p2.py

Write-Host "Script complete!"
