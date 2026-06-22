<#
.SYNOPSIS
    (Re)start all Mockingbird backend services for local development.

.DESCRIPTION
    Always kills existing processes on :3001 / :8001 / :8003 first,
    then starts auth-service, project-service and ingestion-service fresh.
    Waits for each /health endpoint before exiting.

.PARAMETER SkipAuthService
    Do not restart auth-service.
#>

param([switch]$SkipAuthService)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

# ── helpers ───────────────────────────────────────────────────────────────────

function Stop-ServiceOnPort([int]$Port, [string]$Name) {
    $conns = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if (-not $conns) { return }

    $ownerPids = $conns |
        Select-Object -ExpandProperty OwningProcess -Unique |
        Where-Object { $_ -gt 0 }
    if (-not $ownerPids) { return }

    Write-Host "  Stopping $Name (port $Port, PIDs: $($ownerPids -join ', '))..." -ForegroundColor DarkYellow

    foreach ($p in $ownerPids) {
        # uvicorn --reload spawns a child worker; kill children first on Windows
        try {
            $children = Get-WmiObject Win32_Process -Filter "ParentProcessId=$p" -ErrorAction SilentlyContinue
            foreach ($child in $children) {
                Stop-Process -Id $child.ProcessId -Force -ErrorAction SilentlyContinue
            }
        } catch { }
        Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
    }

    # Wait up to 6 s for port to be released
    $deadline = (Get-Date).AddSeconds(6)
    while ((Get-Date) -lt $deadline) {
        if (-not (Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Milliseconds 400
    }
}

function Wait-ForHealth([string]$Url, [string]$Name, [int]$TimeoutSec = 60) {
    Write-Host "  Waiting for $Name ..." -ForegroundColor Yellow
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        # curl.exe avoids PS 5.1 system proxy routing localhost through the proxy
        $status = & curl.exe -s -o "$env:TEMP\mb_health.txt" -w "%{http_code}" --max-time 2 $Url 2>$null
        if ($status -eq "200") { Write-Host "  $Name UP" -ForegroundColor Green; return $true }
        Start-Sleep -Seconds 1
    }
    Write-Host "  ERROR: $Name did not start within ${TimeoutSec}s" -ForegroundColor Red
    return $false
}

function Start-PSService([string]$Cmd) {
    return Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $Cmd -PassThru
}

# ── read JWT secret ────────────────────────────────────────────────────────────

$authDir  = Join-Path $root "services\auth-service"
$envFile  = Join-Path $authDir ".env.local"
if (-not (Test-Path $envFile)) { Write-Host "ERROR: $envFile not found." -ForegroundColor Red; exit 1 }
$jwtSecret = (Get-Content $envFile | Where-Object { $_ -match "^JWT_SECRET=" }) -replace "^JWT_SECRET=", ""

# ── auth-service (:3001) ──────────────────────────────────────────────────────

$authProc = $null
Write-Host "`n[1/3] auth-service :3001" -ForegroundColor Cyan

if ($SkipAuthService) {
    Write-Host "  Skipped (-SkipAuthService)" -ForegroundColor DarkGray
} else {
    Stop-ServiceOnPort 3001 "auth-service"
    $authProc = Start-PSService "cd '$authDir'; `$env:JWT_SECRET='$jwtSecret'; npm run dev"
    Write-Host "  Started PID $($authProc.Id)"
}

# ── project-service (:8001) ───────────────────────────────────────────────────

$projDir = Join-Path $root "services\project-service"
Write-Host "`n[2/3] project-service :8001" -ForegroundColor Cyan
Stop-ServiceOnPort 8001 "project-service"

$projCmd = @"
cd '$projDir'
`$env:jwt_secret='$jwtSecret'
`$env:database_url='sqlite:///./mockingbird.db'
`$env:local_storage_path='./uploads'
.\venv\Scripts\activate
uvicorn project_service.main:app --reload --port 8001 --log-level info
"@

$projProc = Start-PSService $projCmd
Write-Host "  Started PID $($projProc.Id)"

# ── ingestion-service (:8003) ─────────────────────────────────────────────────

$ingDir      = Join-Path $root "services\ingestion-service"
$sharedDbUrl = "sqlite:///" + (Join-Path $projDir "mockingbird.db").Replace("\", "/")
Write-Host "`n[3/3] ingestion-service :8003" -ForegroundColor Cyan
Stop-ServiceOnPort 8003 "ingestion-service"

$ingCmd = @"
cd '$ingDir'
`$env:jwt_secret='$jwtSecret'
`$env:database_url='$sharedDbUrl'
`$env:local_storage_path='./uploads'
.\venv\Scripts\activate
uvicorn ingestion_service.main:app --reload --port 8003 --log-level info
"@

$ingProc = Start-PSService $ingCmd
Write-Host "  Started PID $($ingProc.Id)"

# ── health checks ──────────────────────────────────────────────────────────────

Write-Host "`nWaiting for services to be healthy..." -ForegroundColor Cyan
Start-Sleep -Seconds 5

$ok = $true
if (-not $SkipAuthService) { $ok = $ok -and (Wait-ForHealth "http://localhost:3001/health" "auth-service" 60) }
$ok = $ok -and (Wait-ForHealth "http://localhost:8001/health" "project-service"   30)
$ok = $ok -and (Wait-ForHealth "http://localhost:8003/health" "ingestion-service" 30)

if ($ok) {
    Write-Host "`nAll services running.  Start portal:  cd portal && npm run dev" -ForegroundColor Green
    $authId = if ($authProc) { $authProc.Id } else { "" }
    "$authId,$($projProc.Id),$($ingProc.Id)" | Set-Content (Join-Path $root ".service-pids")
} else {
    Write-Host "`nOne or more services failed to start." -ForegroundColor Red
    exit 1
}
