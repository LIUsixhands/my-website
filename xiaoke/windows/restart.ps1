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
Write-Host "重啟中，最多等 90 秒…"
# 最多等 90 秒：通道要先拿到網址，LINE 也要等新網址的 DNS 生效才收得下 webhook
$h = $null
for ($i = 0; $i -lt 18; $i++) {
  Start-Sleep -Seconds 5
  try { $h = Invoke-RestMethod -Uri "http://localhost:8788/health" -TimeoutSec 5 } catch { continue }
  $pending = @($h.tenants.PSObject.Properties | Where-Object { $_.Value.webhook -in @("未註冊", "註冊中…") })
  if ($h.public_url -and $pending.Count -eq 0) { break }
}
if (-not $h) {
  Write-Host "[FAIL] 重啟後連不到 health，請看 logs\xiaoke.log"
  exit 1
}
Write-Host "[ OK ] 已重啟。對外網址：$($h.public_url)"
foreach ($p in $h.tenants.PSObject.Properties) {
  Write-Host "       $($p.Name)：webhook $($p.Value.webhook)"
}
