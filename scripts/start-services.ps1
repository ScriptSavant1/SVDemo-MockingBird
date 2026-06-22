<#
.SYNOPSIS
    Start all 3 Mockingbird backend services for local development.

.DESCRIPTION
    Starts auth-service (:3001), project-service (:8001), ingestion-service (:8003)
    in separate terminals, waits for each /health endpoint, then exits.
    If a port is already bound the existing process is kept and we just confirm /health.
    The portal (Vite :3000) must be started separately: cd portal && npm run dev

.PARAMETER SkipAuthService
    Skip starting auth-service (useful if it's already running).
#>
param(
    [switch]$SkipAuthService
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

function Is-PortBound([int]$port) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    return $null -ne $conn
}

function Wait-ForHealth {
    param([string]$url, [string]$name, [int]$timeoutSec = 60)
    $deadline = (Get-Date).AddSeconds($timeoutSec)
    Write-Host "  Waiting for $name at $url ..." -ForegroundColor Yellow
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
            if ($r.StatusCode -eq 200) {
                Write-Host "  $name is UP" -ForegroundColor Green
                return $true
            }
        } catch { }
        Start-Sleep -Seconds 1
    }
    Write-Host "  ERROR: $name did not start within ${timeoutSec}s" -ForegroundColor Red
    return $false
}

# ── auth-service ──────────────────────────────────────────────────────────────
$authDir  = Join-Path $root "services\auth-service"
$envFile  = Join-Path $authDir ".env.local"
if (-not (Test-Path $envFile)) {
    Write-Host "ERROR: $envFile not found." -ForegroundColor Red
    exit 1
}
$jwtSecret = (Get-Content $envFile | Where-Object { $_ -match "^JWT_SECRET=" }) -replace "^JWT_SECRET=", ""

$authProc = $null
if (-not $SkipAuthService) {
    Write-Host "`n[1/3] auth-service on :3001" -ForegroundColor Cyan
    if (Is-PortBound 3001) {
        Write-Host "  Port 3001 already bound — skipping start, will confirm health" -ForegroundColor DarkYellow
    } else {
        # tsc compile + node takes ~40s on first run; timeout is 60s
        $authProc = Start-Process -FilePath "powershell.exe" `
            -ArgumentList "-NoExit", "-Command", "cd '$authDir'; `$env:JWT_SECRET='$jwtSecret'; npm run dev" `
            -PassThru -WindowStyle Normal
        Write-Host "  auth-service PID: $($authProc.Id)"
    }
}

# ── project-service ───────────────────────────────────────────────────────────
Write-Host "`n[2/3] project-service on :8001" -ForegroundColor Cyan
$projDir = Join-Path $root "services\project-service"
$projProc = $null
if (Is-PortBound 8001) {
    Write-Host "  Port 8001 already bound — skipping start" -ForegroundColor DarkYellow
} else {
    $projProc = Start-Process -FilePath "cmd.exe" `
        -ArgumentList "/c", "cd /d `"$projDir`" && set jwt_secret=$jwtSecret && set `"database_url=sqlite:///./mockingbird.db`" && set `"local_storage_path=./uploads`" && .\venv\Scripts\activate && uvicorn project_service.main:app --reload --port 8001 --log-level info > uvicorn.log 2>&1" `
        -PassThru -WindowStyle Hidden -WorkingDirectory $projDir
    Write-Host "  project-service PID: $($projProc.Id)"
}

# ── ingestion-service ─────────────────────────────────────────────────────────
Write-Host "`n[3/3] ingestion-service on :8003" -ForegroundColor Cyan
$ingDir      = Join-Path $root "services\ingestion-service"
$sharedDbPath = (Join-Path $projDir "mockingbird.db").Replace('\', '/')
$sharedDbUrl  = "sqlite:///$sharedDbPath"
$ingProc = $null
if (Is-PortBound 8003) {
    Write-Host "  Port 8003 already bound — skipping start" -ForegroundColor DarkYellow
} else {
    $ingProc = Start-Process -FilePath "cmd.exe" `
        -ArgumentList "/c", "cd /d `"$ingDir`" && set jwt_secret=$jwtSecret && set `"database_url=$sharedDbUrl`" && set `"local_storage_path=./uploads`" && .\venv\Scripts\activate && uvicorn ingestion_service.main:app --reload --port 8003 --log-level info > uvicorn.log 2>&1" `
        -PassThru -WindowStyle Hidden -WorkingDirectory $ingDir
    Write-Host "  ingestion-service PID: $($ingProc.Id)"
}

# ── wait for health ────────────────────────────────────────────────────────────
Write-Host "`nWaiting for all services to be healthy..." -ForegroundColor Cyan
Start-Sleep -Seconds 5  # let Node/Python start before polling

$ok = $true
if (-not $SkipAuthService) {
    $ok = $ok -and (Wait-ForHealth "http://localhost:3001/health" "auth-service" 60)
}
$ok = $ok -and (Wait-ForHealth "http://localhost:8001/health" "project-service" 30)
$ok = $ok -and (Wait-ForHealth "http://localhost:8003/health" "ingestion-service" 30)

if ($ok) {
    Write-Host "`nAll services running. Start portal: cd portal && npm run dev" -ForegroundColor Green
    # Save PIDs for stop-services.ps1
    $pidFile = Join-Path $root ".service-pids"
    "$($authProc?.Id),$($projProc?.Id),$($ingProc?.Id)" | Set-Content $pidFile
    Write-Host "PIDs saved to .service-pids"
} else {
    Write-Host "`nOne or more services failed to start. Check uvicorn.log in each service directory." -ForegroundColor Red
    exit 1
}
