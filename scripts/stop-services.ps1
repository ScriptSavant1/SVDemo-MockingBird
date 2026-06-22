<#
.SYNOPSIS
    Stop all Mockingbird backend services started by start-services.ps1.
#>
$root = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $root ".service-pids"

if (Test-Path $pidFile) {
    $pids = (Get-Content $pidFile) -split ","
    foreach ($p in $pids) {
        if ($p -and $p -match "^\d+$") {
            try {
                Stop-Process -Id ([int]$p) -Force -ErrorAction Stop
                Write-Host "Stopped PID $p" -ForegroundColor Green
            } catch {
                Write-Host "PID $p not running (already stopped)" -ForegroundColor Yellow
            }
        }
    }
    Remove-Item $pidFile -Force
} else {
    Write-Host "No .service-pids file found — killing by port" -ForegroundColor Yellow
    foreach ($port in @(3001, 8001, 8003)) {
        $procs = netstat -ano | Select-String ":${port}\s" | ForEach-Object {
            ($_ -split "\s+")[-1]
        } | Sort-Object -Unique
        foreach ($p in $procs) {
            try { Stop-Process -Id ([int]$p) -Force -ErrorAction SilentlyContinue } catch { }
        }
    }
}
Write-Host "Services stopped." -ForegroundColor Cyan
