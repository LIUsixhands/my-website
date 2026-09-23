<#
  小客 Windows 開機自動啟動（工作排程器）

  用法（在 xiaoke 資料夾裡開 PowerShell）：
    powershell -ExecutionPolicy Bypass -File windows\install_autostart.ps1            # 登入 Windows 後自動跑（不需系統管理員）
    powershell -ExecutionPolicy Bypass -File windows\install_autostart.ps1 -AtStartup # 開機就跑、不用登入（需「以系統管理員身分執行」）
    加上 -NoSleep 會順便把「插電時不睡眠」打開

  為什麼用工作排程器：它是 Windows 內建的，當掉會自動重開（每分鐘一次、最多 999 次），
  不用裝任何第三方工具。Mac 版用的 launchd 在 Windows 對應的就是它。
#>
param(
  [switch]$AtStartup,
  [switch]$NoSleep
)
$ErrorActionPreference = "Stop"
$TaskName = "XiaokeLineBot"
$Root = Split-Path -Parent $PSScriptRoot
$Server = Join-Path $Root "server.py"

if ($Root -match "OneDrive") {
  Write-Host "[FAIL] 小客放在 OneDrive 同步資料夾：$Root" -ForegroundColor Red
  Write-Host "       同步中的檔案會被鎖住，服務看起來活著卻什麼都不做。請把整個資料夾搬到 C:\xiaoke 再執行。"
  exit 1
}
if (-not (Test-Path $Server)) { throw "找不到 $Server" }

# 找 pythonw.exe（無視窗版 Python，開機跑不會跳黑視窗）
$py = $null
foreach ($cmd in @("py", "python")) {
  $c = Get-Command $cmd -ErrorAction SilentlyContinue
  if ($c -and $c.Source -notmatch "WindowsApps") {
    $exe = & $cmd -c "import sys; print(sys.executable)" 2>$null
    if ($LASTEXITCODE -eq 0 -and $exe) { $py = $exe.Trim(); break }
  }
}
if (-not $py) {
  Write-Host "[FAIL] 找不到 Python。請到 https://www.python.org/downloads/ 安裝，安裝時勾選「Add python.exe to PATH」。" -ForegroundColor Red
  Write-Host "       （Microsoft Store 那個假 python 不算，它在排程裡跑不起來）"
  exit 1
}
$pyw = Join-Path (Split-Path -Parent $py) "pythonw.exe"
if (-not (Test-Path $pyw)) { $pyw = $py }
Write-Host "[ OK ] Python：$pyw"

# 先體檢，缺金鑰也照樣裝，但要讓人看到
& $py $Server --check
Write-Host ""

$action = New-ScheduledTaskAction -Execute $pyw -Argument "`"$Server`"" -WorkingDirectory $Root
$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
  -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
  -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
$user = "$env:USERDOMAIN\$env:USERNAME"

if ($AtStartup) {
  $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
  if (-not $isAdmin) {
    Write-Host "[FAIL] -AtStartup 要用「以系統管理員身分執行」的 PowerShell。" -ForegroundColor Red
    exit 1
  }
  # S4U：不用登入、不存密碼；Windows Update 半夜重開機也會自己起來
  $trigger = New-ScheduledTaskTrigger -AtStartup
  $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType S4U -RunLevel Limited
  $mode = "開機就啟動（不用登入）"
} else {
  $trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
  $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
  $mode = "登入 Windows 後啟動"
}

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
  -Principal $principal -Description "小客 LINE 自動客服（$Root）" -Force | Out-Null
Write-Host "[ OK ] 已建立排程 $TaskName：$mode，當掉每分鐘自動重開"

if ($NoSleep) {
  powercfg /change standby-timeout-ac 0
  powercfg /change hibernate-timeout-ac 0
  Write-Host "[ OK ] 插電時不睡眠、不休眠（螢幕可以照樣關）"
}

Start-ScheduledTask -TaskName $TaskName
Write-Host "啟動中，最多等 90 秒看健康狀態…"
# 最多等 90 秒：通道要先拿到網址，LINE 也要等新網址的 DNS 生效才收得下 webhook
$h = $null
for ($i = 0; $i -lt 18; $i++) {
  Start-Sleep -Seconds 5
  try { $h = Invoke-RestMethod -Uri "http://localhost:8788/health" -TimeoutSec 5 } catch { continue }
  $pending = @($h.tenants.PSObject.Properties | Where-Object { $_.Value.webhook -in @("未註冊", "註冊中…") })
  if ($h.public_url -and $pending.Count -eq 0) { break }
}
if (-not $h) {
  Write-Host "[FAIL] 連不到 http://localhost:8788/health，請看 $Root\logs\xiaoke.log" -ForegroundColor Red
  exit 1
}
Write-Host "[ OK ] 小客活著。對外網址：$($h.public_url)" -ForegroundColor Green
foreach ($p in $h.tenants.PSObject.Properties) {
  Write-Host "       $($p.Name)：模式 $($p.Value.mode)、webhook $($p.Value.webhook)"
}
if (-not $h.public_url) { Write-Host "[WARN] 還沒拿到對外網址，再等一下或看 logs\xiaoke.log" -ForegroundColor Yellow }
