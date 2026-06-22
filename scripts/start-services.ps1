<#
.SYNOPSIS
    Start all 3 Mockingbird backend services for local development.

.DESCRIPTION
    Starts auth-service (:3001), project-service (:8001), ingestion-service (:8003)
    in separate terminals, waits for each /health endpoint, then exits.
    The portal (Vite :3000) must be started separately: cd portal && npm run dev

.PARAMETER SkipAuthService
    Skip starting auth-service (useful if it's already running).
#>
param(
    [switch]$SkipAuthService
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

function Wait-ForHealth {
    param([string]$url, [string]$name, [int]$timeoutSec = 30)
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
if (-not $SkipAuthService) {
    Write-Host "`n[1/3] Starting auth-service on :3001" -ForegroundColor Cyan
    $authDir = Join-Path $root "services\auth-service"
    $envFile  = Join-Path $authDir ".env.local"
    if (-not (Test-Path $envFile)) {
        Write-Host "  ERROR: $envFile not found. Run: echo 'JWT_SECRET=...' > $envFile" -ForegroundColor Red
        exit 1
    }
    # Load JWT_SECRET from .env.local
    $jwtSecret = (Get-Content $envFile | Where-Object { $_ -match "^JWT_SECRET=" }) -replace "^JWT_SECRET=", ""
    $authProc = Start-Process -FilePath "powershell.exe" `
        -ArgumentList "-NoExit", "-Command", "cd '$authDir'; `$env:JWT_SECRET='$jwtSecret'; npm run dev" `
        -PassThru -WindowStyle Normal
    Write-Host "  auth-service PID: $($authProc.Id)"
}

# ── project-service ───────────────────────────────────────────────────────────
Write-Host "`n[2/3] Starting project-service on :8001" -ForegroundColor Cyan
$projDir = Join-Path $root "services\project-service"
$projProc = Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c", "cd /d `"$projDir`" && set jwt_secret=$jwtSecret && set `"database_url=sqlite:///./mockingbird.db`" && set `"local_storage_path=./uploads`" && .\venv\Scripts\activate && uvicorn project_service.main:app --reload --port 8001 --log-level info > uvicorn.log 2>&1" `
    -PassThru -WindowStyle Hidden -WorkingDirectory $projDir
Write-Host "  project-service PID: $($projProc.Id)"

# ── ingestion-service ─────────────────────────────────────────────────────────
# Share project-service DB so both services can see the same projects and stubs.
Write-Host "`n[3/3] Starting ingestion-service on :8003" -ForegroundColor Cyan
$ingDir = Join-Path $root "services\ingestion-service"
$sharedDbPath = (Join-Path $projDir "mockingbird.db").Replace('\', '/')
$sharedDbUrl = "sqlite:///$sharedDbPath"
$sharedUploads = (Join-Path $projDir "uploads").Replace('\', '/')
$ingProc = Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c", "cd /d `"$ingDir`" && set jwt_secret=$jwtSecret && set `"database_url=$sharedDbUrl`" && set `"local_storage_path=./uploads`" && .\venv\Scripts\activate && uvicorn ingestion_service.main:app --reload --port 8003 --log-level info > uvicorn.log 2>&1" `
    -PassThru -WindowStyle Hidden -WorkingDirectory $ingDir
Write-Host "  ingestion-service PID: $($ingProc.Id)"

# ── wait for health ────────────────────────────────────────────────────────────
Write-Host "`nWaiting for all services to be healthy..." -ForegroundColor Cyan
Start-Sleep -Seconds 4  # give Node/Python time to start

$ok = $true
if (-not $SkipAuthService) {
    $ok = $ok -and (Wait-ForHealth "http://localhost:3001/health" "auth-service")
}
$ok = $ok -and (Wait-ForHealth "http://localhost:8001/health" "project-service")
$ok = $ok -and (Wait-ForHealth "http://localhost:8003/health" "ingestion-service")

if ($ok) {
    Write-Host "`nAll services running. Portal: cd portal && npm run dev" -ForegroundColor Green
    # Print PIDs so the caller can kill them
    $pidFile = Join-Path $root ".service-pids"
    "$($authProc?.Id),$($projProc.Id),$($ingProc.Id)" | Set-Content $pidFile
    Write-Host "PIDs saved to .service-pids for stop-services.ps1"
} else {
    Write-Host "`nOne or more services failed to start. Check the terminal windows." -ForegroundColor Red
    exit 1
}
