# Start Khukra Logistics API + Next.js frontend (run from project root)
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$apiPort = if ($env:KHUKRA_LOGISTICS_API_PORT) { $env:KHUKRA_LOGISTICS_API_PORT } else { "8010" }
$uiPort = if ($env:KHUKRA_LOGISTICS_UI_PORT) { $env:KHUKRA_LOGISTICS_UI_PORT } else { "3020" }
$env:KHUKRA_LOGISTICS_API_PORT = $apiPort
$env:KHUKRA_LOGISTICS_API_URL = "http://127.0.0.1:$apiPort"
$env:NEXT_PUBLIC_API_URL = $env:KHUKRA_LOGISTICS_API_URL
@"
KHUKRA_LOGISTICS_API_URL=$($env:KHUKRA_LOGISTICS_API_URL)
NEXT_PUBLIC_API_URL=$($env:NEXT_PUBLIC_API_URL)
"@ | Set-Content -Encoding utf8 "$root\frontend\.env.local"

$env:PYTHONPATH = "$root\src"

if (-not (Test-Path .venv)) {
    Write-Host "No .venv found — running setup first..."
    & "$PSScriptRoot\setup.ps1"
}

if (-not (Test-Path .venv)) { python -m venv .venv }
.venv\Scripts\python.exe -m pip install -e ".[dev]" -q

Get-NetTCPConnection -LocalPort ([int]$apiPort) -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
Get-NetTCPConnection -LocalPort ([int]$uiPort) -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 1

Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root'; `$env:PYTHONPATH='$root\src'; .venv\Scripts\python.exe -m uvicorn khukra_logistics.api.main:app --host 127.0.0.1 --port $apiPort"

$healthUrl = "http://127.0.0.1:$apiPort/api/health"
Write-Host "Waiting for API at $healthUrl ..."
$apiReady = $false
for ($i = 0; $i -lt 45; $i++) {
    try {
        $h = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2
        if ($h.status -eq "ok" -and $h.capabilities -contains "explore" -and $h.capabilities -contains "news" -and $h.capabilities -contains "evaluate" -and $h.capabilities -contains "production-model") {
            $apiReady = $true
            break
        }
    } catch { }
    Start-Sleep -Seconds 1
}
if (-not $apiReady) {
    Write-Host "WARNING: API missing new routes (explore/panel). Reinstalling package and retrying..."
    .venv\Scripts\python.exe -m pip install -e ".[dev]" -q
    Get-NetTCPConnection -LocalPort ([int]$apiPort) -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique |
        ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 1
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root'; `$env:PYTHONPATH='$root\src'; .venv\Scripts\python.exe -m uvicorn khukra_logistics.api.main:app --host 127.0.0.1 --port $apiPort"
    for ($i = 0; $i -lt 30; $i++) {
        try {
            $h = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2
            if ($h.status -eq "ok" -and $h.capabilities -contains "explore" -and $h.capabilities -contains "news" -and $h.capabilities -contains "evaluate" -and $h.capabilities -contains "production-model") {
                $apiReady = $true
                break
            }
        } catch { }
        Start-Sleep -Seconds 1
    }
}
if (-not $apiReady) {
    Write-Host "ERROR: API did not start with required routes. Check the API terminal window."
} else {
    try {
        $status = Invoke-RestMethod -Uri "http://127.0.0.1:$apiPort/api/disruption/status" -TimeoutSec 5
        if ($status.covered_count -eq 0) {
            Write-Host "First run — ingesting demo signals (5y history)..."
            .\.venv\Scripts\khukra-logistics.exe refresh --years 5
            Write-Host "Polling RSS news..."
            .\.venv\Scripts\khukra-logistics.exe refresh-news
        }
    } catch {
        Write-Host "Could not auto-seed cache: $_"
    }
}

Set-Location "$root\frontend"
if (-not (Test-Path node_modules)) { npm install }
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\frontend'; npm run dev -- --hostname localhost --port $uiPort"

Write-Host "Waiting for UI at http://localhost:$uiPort ..."
for ($i = 0; $i -lt 45; $i++) {
    try {
        $ui = Invoke-WebRequest -Uri "http://localhost:$uiPort" -TimeoutSec 2 -UseBasicParsing
        if ($ui.StatusCode -eq 200) { break }
    } catch { }
    Start-Sleep -Seconds 1
}

Start-Process "http://localhost:$uiPort"
Write-Host "API: http://127.0.0.1:$apiPort/docs"
Write-Host "UI:  http://localhost:$uiPort"
