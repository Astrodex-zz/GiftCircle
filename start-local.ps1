$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$env:DATABASE_URL = 'sqlite:///./local.db'
$env:PUBLIC_URL = 'http://127.0.0.1:8000'
$env:MAIL_MODE = 'log'
$env:PYTHONUTF8 = '1'
try {
    $health = Invoke-RestMethod 'http://127.0.0.1:8000/api/health' -TimeoutSec 2
    if ($health.ok -and $health.version -eq '1.0.0') { Write-Host 'GiftCircle is already running at http://127.0.0.1:8000'; exit 0 }
} catch {}
$server = Start-Process -FilePath "$PSScriptRoot/.venv/Scripts/python.exe" -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput "$PSScriptRoot/tools/server-out.log" -RedirectStandardError "$PSScriptRoot/tools/server-mail.log" -PassThru
$server.Id | Set-Content "$PSScriptRoot/tools/server.pid"
Write-Host 'GiftCircle starting at http://127.0.0.1:8000'
