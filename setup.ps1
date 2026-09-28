# setup.ps1 -- Mockingbird one-time environment setup (Windows)
#
# Run this once before the first start-dev.ps1, and again every time you copy
# or pull a newer version of the code (it upgrades in place).
# Safe to re-run: it skips steps that are already done.
#
# Usage:
#   cd C:\Workspace\Mockingbird
#   .\setup.ps1
#
# Step-by-step guide (incl. company-network notes): docs\COMPANY_SETUP_GUIDE.html

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

$MIN_NODE_MAJOR = 24
$MIN_PYTHON = [version]"3.11"

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

function Note($msg) {
    Write-Host "  [NOTE] $msg" -ForegroundColor Yellow
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

# Run a command and stop if it fails (native executables don't throw on $ErrorActionPreference = Stop)
function Run($cmd) {
    Invoke-Expression $cmd
    if ($LASTEXITCODE -ne 0) {
        Fail "Command failed (exit $LASTEXITCODE): $cmd"
    }
}

function Ensure-Venv {
    if (Test-Path "venv") {
        Warn "venv already exists - reusing it"
    } else {
        Write-Host "  Creating virtual environment..."
        Run "python -m venv venv"
        OK "venv created"
    }
    Write-Host "  Upgrading pip..."
    Run ".\venv\Scripts\python.exe -m pip install --upgrade pip --quiet"
}

# The package itself is installed WITH its dependencies (pyproject.toml is the
# source of truth). Installing it with --no-deps meant a dependency added
# later (e.g. openpyxl for the xlsx template) never reached an existing venv.
function Setup-Python-Service($label, $dir) {
    Step "Python service: $label"
    Push-Location (Join-Path $root $dir)
    Ensure-Venv
    Write-Host "  Installing packages from requirements.txt..."
    Run ".\venv\Scripts\python.exe -m pip install -r requirements.txt --quiet"
    Write-Host "  Installing the service and its dependencies..."
    Run ".\venv\Scripts\python.exe -m pip install -e . --quiet"
    OK "packages installed"
    Pop-Location
}

# `npm rebuild` recompiles native modules (better-sqlite3, bcrypt) for the
# Node version running now — node_modules built under an older Node fail at
# startup with "NODE_MODULE_VERSION ... requires ...".
function Setup-Node-Service($label, $dir, $nativeModules) {
    Step "Node.js service: $label"
    Push-Location (Join-Path $root $dir)
    Run "npm install --no-fund --no-audit"
    Run "npm rebuild"
    foreach ($m in $nativeModules) {
        node -e "require('$m')" 2>$null
        if ($LASTEXITCODE -ne 0) {
            Pop-Location
            Fail ("Native module '$m' does not load under Node $(node --version) in $dir. " +
                  "Delete $dir\node_modules and re-run .\setup.ps1. If it still fails, see " +
                  "docs\COMPANY_SETUP_GUIDE.html, section 'Native modules' (build tools / proxy).")
        }
        OK "$m loads under Node $(node --version)"
    }
    OK "npm packages installed"
    Pop-Location
}

function Read-EnvValue($file, $key) {
    if (-not (Test-Path $file)) { return $null }
    $line = Get-Content $file | Where-Object { $_ -match "^(?i)$key=" } | Select-Object -First 1
    if (-not $line) { return $null }
    return ($line -replace "^(?i)$key=", "").Trim()
}

function Write-EnvFile($file, $lines) {
    # ASCII, no BOM — a BOM makes the first key unreadable to some .env loaders.
    Set-Content -Path $file -Value $lines -Encoding ascii
}

# ---------------------------------------------------------------------------
# 1. Prerequisites
# ---------------------------------------------------------------------------

Step "Checking prerequisites"

Require-Command "python" "Install Python 3.11 or newer and tick 'Add Python to PATH'"
Require-Command "node"   "Install Node.js $MIN_NODE_MAJOR (LTS)"
Require-Command "npm"    "npm comes with Node.js - reinstall Node.js $MIN_NODE_MAJOR"
Require-Command "git"    "Install Git for Windows"

$nodever = (node --version).Trim()
$nodeMajor = [int]($nodever.TrimStart("v").Split(".")[0])
if ($nodeMajor -lt $MIN_NODE_MAJOR) {
    Fail "Node.js $nodever found - Mockingbird needs Node.js $MIN_NODE_MAJOR or newer. Install Node $MIN_NODE_MAJOR, open a NEW terminal, and re-run."
}
OK "Node.js : $nodever"

$pyText = (python --version 2>&1).ToString().Trim()
$pyVer = [version](($pyText -replace "^Python\s+", "") -replace "[^0-9.].*$", "")
if ($pyVer -lt $MIN_PYTHON) {
    Fail "$pyText found - Mockingbird needs Python $MIN_PYTHON or newer."
}
OK "Python  : $pyText"

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
        $effective = Get-ExecutionPolicy
        if ($allowedPolicies -contains $effective) {
            OK "ExecutionPolicy is '$effective' (managed by Group Policy, scripts can run)"
        } else {
            Fail "ExecutionPolicy '$effective' blocks scripts. Ask IT to allow PowerShell scripts."
        }
    }
}

# ---------------------------------------------------------------------------
# 3. Configuration files (.env) — not in git, so a fresh copy has none.
#    All three services must share ONE JWT secret, and ingestion-service must
#    point at project-service's database in THIS folder.
# ---------------------------------------------------------------------------

Step "Configuration files (.env)"

$authEnv = Join-Path $root "services\auth-service\.env.local"
$projEnv = Join-Path $root "services\project-service\.env"
$ingEnv  = Join-Path $root "services\ingestion-service\.env"

$secrets = @(
    (Read-EnvValue $authEnv "JWT_SECRET"),
    (Read-EnvValue $projEnv "jwt_secret"),
    (Read-EnvValue $ingEnv  "jwt_secret")
) | Where-Object { $_ }
$distinct = @($secrets | Sort-Object -Unique)
if ($distinct.Count -gt 1) {
    Fail ("The JWT secret differs between auth-service\.env.local, project-service\.env and " +
          "ingestion-service\.env - logins would work but every other call would fail with 401. " +
          "Make all three the same value (no trailing spaces) and re-run.")
}
if ($distinct.Count -eq 1) {
    $jwtSecret = $distinct[0]
    OK "existing JWT secret reused"
} else {
    $chars = [char[]]((48..57) + (65..90) + (97..122))
    $jwtSecret = -join (1..40 | ForEach-Object { $chars | Get-Random })
    OK "new JWT secret generated"
}

$projDbPath = (Join-Path $root "services\project-service\mockingbird.db").Replace("\", "/")

if (Test-Path $authEnv) { Warn "auth-service\.env.local exists" } else {
    Write-EnvFile $authEnv @("JWT_SECRET=$jwtSecret")
    OK "created auth-service\.env.local"
}
if (Test-Path $projEnv) { Warn "project-service\.env exists" } else {
    Write-EnvFile $projEnv @("database_url=sqlite:///./mockingbird.db", "jwt_secret=$jwtSecret", "local_storage_path=./uploads")
    OK "created project-service\.env"
}
if (Test-Path $ingEnv) {
    $ingDb = Read-EnvValue $ingEnv "database_url"
    $expected = "sqlite:///$projDbPath"
    if ($ingDb -and $ingDb.StartsWith("sqlite:") -and $ingDb -ne $expected) {
        (Get-Content $ingEnv) | ForEach-Object { if ($_ -match "^(?i)database_url=") { "database_url=$expected" } else { $_ } } |
            Set-Content -Path $ingEnv -Encoding ascii
        Note "ingestion-service\.env database_url pointed at '$ingDb' - corrected to this folder's project database"
    } else {
        Warn "ingestion-service\.env exists"
    }
} else {
    Write-EnvFile $ingEnv @("database_url=sqlite:///$projDbPath", "jwt_secret=$jwtSecret", "local_storage_path=./uploads")
    OK "created ingestion-service\.env"
}

# ---------------------------------------------------------------------------
# 4. parser-worker -- must install BEFORE ingestion-service
# ---------------------------------------------------------------------------

Setup-Python-Service "parser-worker" "services\parser-worker"

# ---------------------------------------------------------------------------
# 5. project-service
# ---------------------------------------------------------------------------

Setup-Python-Service "project-service" "services\project-service"

# ---------------------------------------------------------------------------
# 6. project-service database
#    Existing database managed by Alembic -> upgrade it (applies any new
#    migrations, keeps all projects/stubs). Existing database created before
#    Alembic was used (no alembic_version table) -> stamp it. No database ->
#    create it.
# ---------------------------------------------------------------------------

Step "Setting up project-service database"
Push-Location (Join-Path $root "services\project-service")
$env:DATABASE_URL = "sqlite:///./mockingbird.db"

if (Test-Path "mockingbird.db") {
    # Single quotes only inside the Python snippet: Windows PowerShell 5.1
    # strips embedded double quotes when passing arguments to native programs.
    $hasAlembic = .\venv\Scripts\python.exe -c "import sqlite3; c = sqlite3.connect('mockingbird.db'); print(1 if c.execute('select name from sqlite_master where type=? and name=?', ('table', 'alembic_version')).fetchone() else 0)"
    if ($LASTEXITCODE -ne 0 -or -not $hasAlembic) {
        Pop-Location
        Fail "Could not inspect the existing services\project-service\mockingbird.db (is it a valid SQLite file?)."
    }
    if ($hasAlembic.Trim() -eq "1") {
        $backup = "mockingbird.db.bak-" + (Get-Date -Format "yyyyMMdd-HHmmss")
        Copy-Item "mockingbird.db" $backup
        OK "backed up existing database to $backup"
        Write-Host "  Applying any new migrations to the existing database..."
        Run ".\venv\Scripts\python.exe -m alembic upgrade head"
        OK "database upgraded to the latest version (projects and stubs kept)"
    } else {
        Write-Host "  Database predates migrations - stamping it to the current version..."
        Run ".\venv\Scripts\python.exe -m alembic stamp head"
        OK "database stamped"
    }
} else {
    Write-Host "  Creating database and running migrations..."
    Run ".\venv\Scripts\python.exe -m alembic upgrade head"
    OK "database created and tables set up (mockingbird.db)"
}
Remove-Item Env:DATABASE_URL

Pop-Location

# ---------------------------------------------------------------------------
# 7. ingestion-service
#    parser-worker must be installed into this venv first because
#    ingestion-service imports parser_worker at runtime.
# ---------------------------------------------------------------------------

Step "Python service: ingestion-service"
Push-Location (Join-Path $root "services\ingestion-service")
Ensure-Venv

Write-Host "  Installing parser-worker (and its dependencies) first..."
Run ".\venv\Scripts\python.exe -m pip install -e '..\parser-worker' --quiet"
OK "parser-worker installed"

Write-Host "  Installing packages from requirements.txt..."
Run ".\venv\Scripts\python.exe -m pip install -r requirements.txt --quiet"

Write-Host "  Installing the service and its dependencies..."
Run ".\venv\Scripts\python.exe -m pip install -e . --quiet"
OK "packages installed"

.\venv\Scripts\python.exe -c "import openpyxl, parser_worker.detector" 2>$null
if ($LASTEXITCODE -ne 0) {
    Pop-Location
    Fail "ingestion-service cannot import the parser (xlsx support needs openpyxl). Re-run .\setup.ps1; if it persists, check the pip output above for install errors."
}
OK "xlsx parser importable"

Pop-Location

# ---------------------------------------------------------------------------
# 8. auth-service (Node.js)
# ---------------------------------------------------------------------------

Setup-Node-Service "auth-service" "services\auth-service" @("better-sqlite3", "bcrypt")

# ---------------------------------------------------------------------------
# 9. portal (Node.js)
# ---------------------------------------------------------------------------

Setup-Node-Service "portal" "portal" @()

# ---------------------------------------------------------------------------
# 10. Verify everything is in place
# ---------------------------------------------------------------------------

Step "Verifying setup"

$checks = @(
    @{ Label = "auth-service .env.local";   Path = "services\auth-service\.env.local" },
    @{ Label = "project-service .env";      Path = "services\project-service\.env" },
    @{ Label = "ingestion-service .env";    Path = "services\ingestion-service\.env" },
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
    Write-Host "  2. Open browser:    http://localhost:3010" -ForegroundColor White
    Write-Host "  3. First time only: .\scripts\seed-users.ps1   (creates sv.admin / sv.user)" -ForegroundColor White
} else {
    Write-Host "============================================" -ForegroundColor Red
    Write-Host "  Setup finished with errors (see above)." -ForegroundColor Red
    Write-Host "============================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "Fix the missing items then run .\setup.ps1 again." -ForegroundColor Yellow
    exit 1
}
