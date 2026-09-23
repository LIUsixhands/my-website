<#
  重啟小客（改了 config.json 的金鑰、新增租戶後用）；知識庫改檔不用重啟
    powershell -ExecutionPolicy Bypass -File windows\restart.ps1
#>
$TaskName = "XiaokeLineBot"
$Server = Join-Path (Split-Path -Parent $PSScriptRoot) "server.py"
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
  Where-Object { $_.CommandLine -and $_.CommandLine.Contains($Server) } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
# 只收小客開的那個 cloudflared（指向本機 8788），不動你其他的通道
Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" |
  Where-Object { $_.CommandLine -match "localhost:8788" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Start-Sleep -Seconds 2
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 15
try {
  $h = Invoke-RestMethod -Uri "http://localhost:8788/health" -TimeoutSec 5
  Write-Host "[ OK ] 已重啟。對外網址：$($h.public_url)"
} catch {
  Write-Host "[FAIL] 重啟後連不到 health，請看 logs\xiaoke.log"
}
