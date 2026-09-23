<#
  移除小客的開機自動啟動（不會刪任何租戶資料）
    powershell -ExecutionPolicy Bypass -File windows\uninstall_autostart.ps1
#>
$TaskName = "XiaokeLineBot"
$Server = Join-Path (Split-Path -Parent $PSScriptRoot) "server.py"
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
  Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
  Write-Host "[ OK ] 已移除排程 $TaskName"
} else {
  Write-Host "沒有找到排程 $TaskName，不用移除"
}
# 手動開的也收掉；Stop-ScheduledTask 殺不到子程序 cloudflared
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
  Where-Object { $_.CommandLine -and $_.CommandLine.Contains($Server) } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host "已停止 PID $($_.ProcessId)" }
# 只收小客開的那個 cloudflared（指向本機 8788），不動你其他的通道
Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" |
  Where-Object { $_.CommandLine -match "localhost:8788" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
