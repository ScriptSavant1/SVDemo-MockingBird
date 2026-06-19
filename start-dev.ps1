# Mockingbird local development launcher
# Run this once from the repo root. It opens 4 windows automatically.
#
# Usage:
#   .\start-dev.ps1
#
# To stop everything: close the 4 windows (or Ctrl+C in each).

$root = $PSScriptRoot

function Start-Service($title, $commands) {
    $joined = $commands -join "; "
    # -ExecutionPolicy Bypass lets the spawned window run .ps1 scripts (venv activation)
    Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $joined `
        -WorkingDirectory $root
}

Write-Host "Starting Mockingbird local dev stack..." -ForegroundColor Cyan
Write-Host ""

# 1. auth-service (Node.js + SQLite — no PostgreSQL needed)
Start-Service "auth-service" @(
    "Set-Location '$root\services\auth-service'",
    "Write-Host '[auth-service] Starting on http://localhost:3001' -ForegroundColor Green",
    "npm run dev"
)

# 2. project-service (Python + SQLite)
Start-Service "project-service" @(
    "Set-Location '$root\services\project-service'",
    "`$env:DATABASE_URL = 'sqlite:///./mockingbird.db'",
    "Write-Host '[project-service] Starting on http://localhost:8001' -ForegroundColor Green",
    ".\venv\Scripts\python.exe -m uvicorn project_service.main:app --host 0.0.0.0 --port 8001 --reload"
)

# 3. ingestion-service (Python + SQLite + local file storage — no S3 needed)
Start-Service "ingestion-service" @(
    "Set-Location '$root\services\ingestion-service'",
    "`$env:DATABASE_URL = 'sqlite:///./ingestion.db'",
    "`$env:LOCAL_STORAGE_PATH = '.\uploads'",
    "`$env:JWT_SECRET = 'local-dev-secret'",
    "Write-Host '[ingestion-service] Starting on http://localhost:8003' -ForegroundColor Green",
    ".\venv\Scripts\python.exe -m uvicorn ingestion_service.main:app --host 0.0.0.0 --port 8003 --reload"
)

# 4. portal (React + Vite)
Start-Service "portal" @(
    "Set-Location '$root\portal'",
    "Write-Host '[portal] Starting on http://localhost:3000' -ForegroundColor Green",
    "npm run dev"
)

Write-Host "Four windows opened. Services will be ready in about 10 seconds." -ForegroundColor Cyan
Write-Host ""
Write-Host "Then open: http://localhost:3000" -ForegroundColor Yellow
Write-Host ""
Write-Host "First time only - create the admin account (run in a new terminal):" -ForegroundColor Yellow
Write-Host ""
Write-Host "  See docs\LOCAL_DEVELOPMENT.md for the setup curl command." -ForegroundColor White
