# First-time setup for Khukra (run from repo root via .\scripts\setup.ps1)
param(
    [switch]$SeedData,
    [switch]$Dev,
    [int]$Years = 5
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Start-KhukraDev {
    $ErrorActionPreference = "Continue"
    $apiPort = if ($env:KHUKRA_API_PORT) { $env:KHUKRA_API_PORT } elseif ($env:KHUKRA_LOGISTICS_API_PORT) { $env:KHUKRA_LOGISTICS_API_PORT } else { "8010" }
    $uiPort = if ($env:KHUKRA_UI_PORT) { $env:KHUKRA_UI_PORT } elseif ($env:KHUKRA_LOGISTICS_UI_PORT) { $env:KHUKRA_LOGISTICS_UI_PORT } else { "3020" }
    $env:KHUKRA_API_PORT = $apiPort
    $env:KHUKRA_API_URL = "http://127.0.0.1:$apiPort"
    $env:NEXT_PUBLIC_API_URL = $env:KHUKRA_API_URL
    @"
KHUKRA_API_URL=$($env:KHUKRA_API_URL)
NEXT_PUBLIC_API_URL=$($env:NEXT_PUBLIC_API_URL)
"@ | Set-Content -Encoding utf8 "$root\frontend\.env.local"

    $env:PYTHONPATH = "$root\src"
    if (-not (Test-Path .venv)) { python -m venv .venv }
    .\.venv\Scripts\python.exe -m pip install -e ".[dev]" -q

    Get-NetTCPConnection -LocalPort ([int]$apiPort) -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique |
        ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
    Get-NetTCPConnection -LocalPort ([int]$uiPort) -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique |
        ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 1

    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root'; `$env:PYTHONPATH='$root\src'; .venv\Scripts\python.exe -m uvicorn khukra.api.main:app --host 127.0.0.1 --port $apiPort"

    $healthUrl = "http://127.0.0.1:$apiPort/api/health"
    Write-Host "Waiting for API at $healthUrl ..."
    $apiReady = $false
    for ($i = 0; $i -lt 45; $i++) {
        try {
            $h = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2
            if ($h.status -eq "ok" -and $h.capabilities -contains "index-decomposition" -and $h.capabilities -contains "forecast-check") {
                $apiReady = $true
                break
            }
        } catch { }
        Start-Sleep -Seconds 1
    }
    if (-not $apiReady) {
        Write-Host "ERROR: API did not start with required routes. Check the API terminal window."
    } else {
        try {
            $status = Invoke-RestMethod -Uri "http://127.0.0.1:$apiPort/api/disruption/status" -TimeoutSec 5
            if ($status.covered_count -eq 0) {
                Write-Host "First run - ingesting demo signals (5y history)..."
                .\.venv\Scripts\khukra.exe refresh --years 5
                .\.venv\Scripts\khukra.exe refresh-news
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
}

if ($Dev) {
    Start-KhukraDev
    return
}

function Require-Command($name) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
        throw "Required command not found: $name"
    }
}

Write-Host "Khukra setup"
Write-Host "======================"

Require-Command python
Require-Command npm

$pyVersion = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
$pyMajor, $pyMinor = $pyVersion.Split(".") | ForEach-Object { [int]$_ }
if ($pyMajor -lt 3 -or ($pyMajor -eq 3 -and $pyMinor -lt 10)) {
    throw "Python 3.10+ required (found $pyVersion)"
}
Write-Host "Python $pyVersion"

if (-not (Test-Path .venv)) {
    Write-Host "Creating virtualenv..."
    python -m venv .venv
}

Write-Host "Installing Python package (editable + dev)..."
.\.venv\Scripts\python.exe -m pip install --upgrade pip -q
.\.venv\Scripts\python.exe -m pip install -e ".[dev]" -q

Write-Host "Installing frontend dependencies..."
Set-Location frontend
if (-not (Test-Path node_modules)) { npm install }
Set-Location $root

if (-not (Test-Path data)) {
    New-Item -ItemType Directory -Path data | Out-Null
}

if ($SeedData) {
    Write-Host "Seeding disruption signal cache (${Years}y history; may take 1-2 min)..."
    .\.venv\Scripts\khukra.exe refresh --years $Years
    Write-Host "Polling RSS news feeds..."
    .\.venv\Scripts\khukra.exe refresh-news
}

Write-Host ""
Write-Host "Setup complete."
Write-Host "  Run:  .\scripts\setup.ps1 -Dev"
Write-Host "  Test: .\scripts\smoke-test.ps1"
if (-not $SeedData) {
    Write-Host "  Optional seed data: .\scripts\setup.ps1 -SeedData"
}
