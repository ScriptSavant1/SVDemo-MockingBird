<#
.SYNOPSIS
    Start all Mockingbird backend services for local development.

.DESCRIPTION
    Starts:
      - auth-service (:3001)
      - project-service (:8001)
      - ingestion-service (:8003)

    Waits for each /health endpoint.

.PARAMETER SkipAuthService
    Skip starting auth-service.
#>

param(
    [switch]$SkipAuthService
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot

function Is-PortBound {
    param([int]$Port)

    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return ($null -ne $conn)
}

function Wait-ForHealth {
    param(
        [string]$Url,
        [string]$Name,
        [int]$TimeoutSec = 60
    )

    Write-Host "Waiting for $Name ..." -ForegroundColor Yellow

    $deadline = (Get-Date).AddSeconds($TimeoutSec)

    while ((Get-Date) -lt $deadline) {
        # curl.exe bypasses PowerShell 5.1 proxy configuration issues for localhost
        $status = & curl.exe -s -o "$env:TEMP\health_check.txt" -w "%{http_code}" --max-time 2 $Url 2>$null
        if ($status -eq "200") {
            Write-Host "$Name is UP" -ForegroundColor Green
            return $true
        }
        Start-Sleep -Seconds 1
    }

    Write-Host "$Name failed to start." -ForegroundColor Red
    return $false
}

# ====================================================
# Read JWT secret
# ====================================================

$authDir = Join-Path $root "services\auth-service"
$envFile = Join-Path $authDir ".env.local"

if (!(Test-Path $envFile)) {
    Write-Host ".env.local not found." -ForegroundColor Red
    exit 1
}

$jwtSecret = (
    Get-Content $envFile |
    Where-Object { $_ -match "^JWT_SECRET=" }
) -replace "^JWT_SECRET=", ""

# ====================================================
# auth-service
# ====================================================

$authProc = $null

if (-not $SkipAuthService) {

    Write-Host "`n[1/3] auth-service (:3001)" -ForegroundColor Cyan

    if (Is-PortBound 3001) {
        Write-Host "Port 3001 already in use. Skipping start."
    }
    else {

        $authProc = Start-Process powershell.exe `
            -ArgumentList @(
                "-NoExit",
                "-Command",
                "cd '$authDir'; `$env:JWT_SECRET='$jwtSecret'; npm run dev"
            ) `
            -PassThru

        Write-Host "auth-service PID: $($authProc.Id)"
    }
}

# ====================================================
# project-service
# ====================================================

$projDir = Join-Path $root "services\project-service"
$projProc = $null

Write-Host "`n[2/3] project-service (:8001)" -ForegroundColor Cyan

if (Is-PortBound 8001) {

    Write-Host "Port 8001 already in use. Skipping start."

}
else {

    $projectCommand = @"
cd '$projDir'
`$env:jwt_secret='$jwtSecret'
`$env:database_url='sqlite:///./mockingbird.db'
`$env:local_storage_path='./uploads'
.\venv\Scripts\activate
uvicorn project_service.main:app --reload --port 8001 --log-level info
"@

    $projProc = Start-Process powershell.exe `
        -ArgumentList @(
            "-NoExit",
            "-Command",
            $projectCommand
        ) `
        -PassThru

    Write-Host "project-service PID: $($projProc.Id)"
}

# ====================================================
# ingestion-service
# ====================================================

$ingDir = Join-Path $root "services\ingestion-service"

$sharedDbPath = (Join-Path $projDir "mockingbird.db").Replace("\", "/")
$sharedDbUrl = "sqlite:///$sharedDbPath"

$ingProc = $null

Write-Host "`n[3/3] ingestion-service (:8003)" -ForegroundColor Cyan

if (Is-PortBound 8003) {

    Write-Host "Port 8003 already in use. Skipping start."

}
else {

    $ingestionCommand = @"
cd '$ingDir'
`$env:jwt_secret='$jwtSecret'
`$env:database_url='$sharedDbUrl'
`$env:local_storage_path='./uploads'
.\venv\Scripts\activate
uvicorn ingestion_service.main:app --reload --port 8003 --log-level info
"@

    $ingProc = Start-Process powershell.exe `
        -ArgumentList @(
            "-NoExit",
            "-Command",
            $ingestionCommand
        ) `
        -PassThru

    Write-Host "ingestion-service PID: $($ingProc.Id)"
}

# ====================================================
# Health checks
# ====================================================

Write-Host "`nWaiting for services..." -ForegroundColor Cyan

Start-Sleep -Seconds 5

$ok = $true

if (-not $SkipAuthService) {
    $ok = $ok -and (Wait-ForHealth "http://localhost:3001/health" "auth-service" 60)
}

$ok = $ok -and (Wait-ForHealth "http://localhost:8001/health" "project-service" 60)
$ok = $ok -and (Wait-ForHealth "http://localhost:8003/health" "ingestion-service" 60)

if ($ok) {

    Write-Host ""
    Write-Host "All services are running." -ForegroundColor Green
    Write-Host "Start portal separately:"
    Write-Host "cd portal"
    Write-Host "npm run dev"

    $pidFile = Join-Path $root ".service-pids"

    $authPid = ""
    $projPid = ""
    $ingPid = ""

    if ($authProc) { $authPid = $authProc.Id }
    if ($projProc) { $projPid = $projProc.Id }
    if ($ingProc) { $ingPid = $ingProc.Id }

    "$authPid,$projPid,$ingPid" | Set-Content $pidFile
}
else {

    Write-Host ""
    Write-Host "One or more services failed to start." -ForegroundColor Red
    exit 1
}