# setup.ps1 -- Mockingbird one-time environment setup (Windows)
#
# Run this ONCE before the first start-dev.ps1.
# Safe to re-run: it skips steps that are already done.
#
# Usage:
#   cd C:\Workspace\Mockingbird
#   .\setup.ps1

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

function Step($msg) {
    Write-Host ""
    Write-Host "===> $msg" -ForegroundColor Cyan
}

function OK($msg) {
    Write-Host "  [OK] $msg" -ForegroundColor Green
}

function Warn($msg) {
    Write-Host "  [SKIP] $msg" -ForegroundColor Yellow
}

function Fail($msg) {
    Write-Host ""
    Write-Host "  [ERROR] $msg" -ForegroundColor Red
    Write-Host ""
    exit 1
}

function Require-Command($cmd, $installHint) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Fail "$cmd not found. $installHint"
    }
}

function Setup-Python-Service($label, $dir) {
    Step "Python service: $label"
    Push-Location (Join-Path $root $dir)

    if (Test-Path "venv") {
        Warn "venv already exists - skipping creation"
    } else {
        Write-Host "  Creating virtual environment..."
        python -m venv venv
        OK "venv created"
    }

    Write-Host "  Upgrading pip..."
    .\venv\Scripts\python.exe -m pip install --upgrade pip --quiet

    Write-Host "  Installing packages..."
    .\venv\Scripts\python.exe -m pip install -e ".[dev]" --quiet
    OK "packages installed"

    Write-Host "  Generating requirements.txt..."
    .\venv\Scripts\python.exe -m pip freeze | Out-File -Encoding utf8 requirements.txt
    OK "requirements.txt written"

    Pop-Location
}

function Setup-Node-Service($label, $dir) {
    Step "Node.js service: $label"
    Push-Location (Join-Path $root $dir)
    npm install --silent
    OK "npm packages installed"
    Pop-Location
}

# ---------------------------------------------------------------------------
# 1. Prerequisites
# ---------------------------------------------------------------------------

Step "Checking prerequisites"

Require-Command "python" "Install from https://www.python.org/downloads/ -- tick 'Add Python to PATH'"
Require-Command "node"   "Install from https://nodejs.org/ (choose LTS)"
Require-Command "git"    "Install from https://git-scm.com/download/win"

$pyver   = python --version 2>&1
$nodever = node --version 2>&1
OK "Python  : $pyver"
OK "Node.js : $nodever"

# ---------------------------------------------------------------------------
# 2. Allow PowerShell scripts (Activate.ps1 etc.)
# ---------------------------------------------------------------------------

Step "Setting PowerShell execution policy"
$effectivePolicy = Get-ExecutionPolicy
$allowedPolicies = @("Bypass", "Unrestricted", "RemoteSigned")
if ($allowedPolicies -contains $effectivePolicy) {
    OK "ExecutionPolicy is already '$effectivePolicy' -- no change needed"
} else {
    try {
        Set-ExecutionPolicy RemoteSigned -Scope CurrentUser -Force
        OK "ExecutionPolicy set to RemoteSigned"
    } catch {
        # Group Policy may override -- check if the effective policy still allows scripts
        $effective = Get-ExecutionPolicy
        if ($allowedPolicies -contains $effective) {
            OK "ExecutionPolicy is '$effective' (overridden by Group Policy but scripts can still run)"
        } else {
            Fail "ExecutionPolicy '$effective' blocks scripts. Ask your IT team to allow PowerShell scripts, or run: Set-ExecutionPolicy RemoteSigned -Scope Process"
        }
    }
}

# ---------------------------------------------------------------------------
# 3. parser-worker -- must install BEFORE ingestion-service
# ---------------------------------------------------------------------------

Setup-Python-Service "parser-worker" "services\parser-worker"

# ---------------------------------------------------------------------------
# 4. project-service
# ---------------------------------------------------------------------------

Setup-Python-Service "project-service" "services\project-service"

Step "Creating project-service SQLite database"
Push-Location (Join-Path $root "services\project-service")
$env:DATABASE_URL = "sqlite:///./mockingbird.db"
.\venv\Scripts\python.exe -m alembic upgrade head
OK "database tables created (mockingbird.db)"
Pop-Location

# ---------------------------------------------------------------------------
# 5. ingestion-service
#    parser-worker is a direct dependency so it must be installed into
#    this venv first, then the ingestion-service packages on top.
# ---------------------------------------------------------------------------

Step "Python service: ingestion-service"
Push-Location (Join-Path $root "services\ingestion-service")

if (Test-Path "venv") {
    Warn "venv already exists - skipping creation"
} else {
    Write-Host "  Creating virtual environment..."
    python -m venv venv
    OK "venv created"
}

Write-Host "  Upgrading pip..."
.\venv\Scripts\python.exe -m pip install --upgrade pip --quiet

Write-Host "  Installing parser-worker dependency first..."
.\venv\Scripts\python.exe -m pip install -e "..\parser-worker" --quiet
OK "parser-worker installed"

Write-Host "  Installing ingestion-service packages..."
.\venv\Scripts\python.exe -m pip install -e ".[dev]" --quiet
OK "packages installed"

Write-Host "  Generating requirements.txt..."
.\venv\Scripts\python.exe -m pip freeze | Out-File -Encoding utf8 requirements.txt
OK "requirements.txt written"

Pop-Location

# ---------------------------------------------------------------------------
# 6. auth-service (Node.js)
# ---------------------------------------------------------------------------

Setup-Node-Service "auth-service" "services\auth-service"

# ---------------------------------------------------------------------------
# 7. portal (Node.js)
# ---------------------------------------------------------------------------

Setup-Node-Service "portal" "portal"

# ---------------------------------------------------------------------------
# 8. Verify everything is in place
# ---------------------------------------------------------------------------

Step "Verifying setup"

$checks = @(
    @{ Label = "parser-worker venv";        Path = "services\parser-worker\venv" },
    @{ Label = "project-service venv";      Path = "services\project-service\venv" },
    @{ Label = "project-service database";  Path = "services\project-service\mockingbird.db" },
    @{ Label = "ingestion-service venv";    Path = "services\ingestion-service\venv" },
    @{ Label = "auth-service node_modules"; Path = "services\auth-service\node_modules" },
    @{ Label = "portal node_modules";       Path = "portal\node_modules" }
)

$allOk = $true
foreach ($check in $checks) {
    $fullPath = Join-Path $root $check.Path
    if (Test-Path $fullPath) {
        OK $check.Label
    } else {
        Write-Host "  [MISSING] $($check.Label) -- $fullPath" -ForegroundColor Red
        $allOk = $false
    }
}

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

Write-Host ""
if ($allOk) {
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "  Setup complete. All checks passed." -ForegroundColor Green
    Write-Host "============================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Yellow
    Write-Host "  1. Start services:  .\start-dev.ps1" -ForegroundColor White
    Write-Host "  2. Open browser:    http://localhost:3000" -ForegroundColor White
    Write-Host "  3. Create admin:    see docs\LOCAL_DEVELOPMENT.md Section A5" -ForegroundColor White
} else {
    Write-Host "============================================" -ForegroundColor Red
    Write-Host "  Setup finished with errors (see above)." -ForegroundColor Red
    Write-Host "============================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "Fix the missing items then run .\setup.ps1 again." -ForegroundColor Yellow
    exit 1
}
