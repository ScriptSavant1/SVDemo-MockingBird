#!/usr/bin/env bash
# setup.sh -- Mockingbird one-time environment setup (RHEL 9 / Linux)
#
# Run this ONCE on a fresh EC2 instance or Linux machine before starting services.
# Safe to re-run: it skips steps that are already done.
#
# Usage:
#   chmod +x setup.sh
#   ./setup.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RED='\033[0;31m'; NC='\033[0m'

step()  { echo -e "\n${CYAN}===> $1${NC}"; }
ok()    { echo -e "  ${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "  ${YELLOW}[SKIP]${NC} $1"; }
fail()  { echo -e "\n  ${RED}[ERROR]${NC} $1\n"; exit 1; }

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || fail "$1 not found. $2"
}

# ---------------------------------------------------------------------------
# 1. System packages (RHEL 9 / dnf)
# ---------------------------------------------------------------------------

step "Installing system packages (requires sudo)"

sudo dnf install -y \
    python3.11 python3.11-pip python3.11-devel \
    gcc gcc-c++ make \
    git curl wget \
    postgresql-devel

# Node.js 20 via NodeSource if not present or too old
if ! command -v node >/dev/null 2>&1 || [[ "$(node --version | cut -d. -f1 | tr -d 'v')" -lt 20 ]]; then
    step "Installing Node.js 20 (NodeSource)"
    curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
    sudo dnf install -y nodejs
fi

ok "System packages ready"

# ---------------------------------------------------------------------------
# 2. Verify tool versions
# ---------------------------------------------------------------------------

step "Checking tool versions"
require_cmd "python3.11" "Run: sudo dnf install python3.11"
require_cmd "node"       "Run: curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash - && sudo dnf install nodejs"
require_cmd "git"        "Run: sudo dnf install git"

ok "Python  : $(python3.11 --version)"
ok "Node.js : $(node --version)"
ok "Git     : $(git --version)"

# ---------------------------------------------------------------------------
# Helper: set up a Python service using requirements.txt
# ---------------------------------------------------------------------------

setup_python_service() {
    local label="$1"
    local dir="$2"

    step "Python service: $label"
    pushd "$ROOT/$dir" >/dev/null

    if [[ -d "venv" ]]; then
        warn "venv already exists - skipping creation"
    else
        echo "  Creating virtual environment..."
        python3.11 -m venv venv
        ok "venv created"
    fi

    echo "  Upgrading pip..."
    venv/bin/python -m pip install --upgrade pip --quiet

    echo "  Installing packages from requirements.txt..."
    venv/bin/python -m pip install -r requirements.txt --quiet
    ok "packages installed"

    echo "  Installing package in editable mode..."
    venv/bin/python -m pip install -e . --no-deps --quiet
    ok "package registered"

    popd >/dev/null
}

# ---------------------------------------------------------------------------
# Helper: set up a Node.js service
# ---------------------------------------------------------------------------

setup_node_service() {
    local label="$1"
    local dir="$2"

    step "Node.js service: $label"
    pushd "$ROOT/$dir" >/dev/null
    npm install --silent
    ok "npm packages installed"
    popd >/dev/null
}

# ---------------------------------------------------------------------------
# 3. parser-worker -- must install BEFORE ingestion-service
# ---------------------------------------------------------------------------

setup_python_service "parser-worker" "services/parser-worker"

# ---------------------------------------------------------------------------
# 4. project-service
# ---------------------------------------------------------------------------

setup_python_service "project-service" "services/project-service"

# ---------------------------------------------------------------------------
# 5. project-service database
#    If mockingbird.db already exists, stamp to head to avoid "table already
#    exists" errors. If fresh install, run upgrade head to create tables.
# ---------------------------------------------------------------------------

step "Setting up project-service database"
pushd "$ROOT/services/project-service" >/dev/null
export DATABASE_URL="sqlite:///./mockingbird.db"

if [[ -f "mockingbird.db" ]]; then
    echo "  Database already exists - stamping to current migration head..."
    venv/bin/python -m alembic stamp head
    ok "database already at current version (no migration needed)"
else
    echo "  Creating database and running migrations..."
    venv/bin/python -m alembic upgrade head
    ok "database created and tables set up (mockingbird.db)"
fi

popd >/dev/null

# ---------------------------------------------------------------------------
# 6. ingestion-service
#    parser-worker must be installed into this venv first because
#    ingestion-service imports parser_worker at runtime.
# ---------------------------------------------------------------------------

step "Python service: ingestion-service"
pushd "$ROOT/services/ingestion-service" >/dev/null

if [[ -d "venv" ]]; then
    warn "venv already exists - skipping creation"
else
    echo "  Creating virtual environment..."
    python3.11 -m venv venv
    ok "venv created"
fi

echo "  Upgrading pip..."
venv/bin/python -m pip install --upgrade pip --quiet

echo "  Installing parser-worker dependency first..."
venv/bin/python -m pip install -e "../parser-worker" --quiet
ok "parser-worker installed"

echo "  Installing packages from requirements.txt..."
venv/bin/python -m pip install -r requirements.txt --quiet
ok "packages installed"

echo "  Installing package in editable mode..."
venv/bin/python -m pip install -e . --no-deps --quiet
ok "package registered"

popd >/dev/null

# ---------------------------------------------------------------------------
# 7. auth-service (Node.js)
# ---------------------------------------------------------------------------

setup_node_service "auth-service" "services/auth-service"

# ---------------------------------------------------------------------------
# 8. portal (Node.js)
# ---------------------------------------------------------------------------

setup_node_service "portal" "portal"

# ---------------------------------------------------------------------------
# 9. Verify
# ---------------------------------------------------------------------------

step "Verifying setup"
ALL_OK=true

check() {
    local label="$1"
    local path="$ROOT/$2"
    if [[ -e "$path" ]]; then
        ok "$label"
    else
        echo -e "  ${RED}[MISSING]${NC} $label -- $path"
        ALL_OK=false
    fi
}

check "parser-worker venv"        "services/parser-worker/venv"
check "project-service venv"      "services/project-service/venv"
check "project-service database"  "services/project-service/mockingbird.db"
check "ingestion-service venv"    "services/ingestion-service/venv"
check "auth-service node_modules" "services/auth-service/node_modules"
check "portal node_modules"       "portal/node_modules"

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

echo ""
if [[ "$ALL_OK" == "true" ]]; then
    echo -e "${GREEN}============================================${NC}"
    echo -e "${GREEN}  Setup complete. All checks passed.${NC}"
    echo -e "${GREEN}============================================${NC}"
    echo ""
    echo -e "${YELLOW}Next steps:${NC}"
    echo "  1. Start services:  ./start-dev.sh"
    echo "  2. Open browser:    http://<server-ip>:3000"
    echo "  3. Create admin:    see docs/LOCAL_DEVELOPMENT.md Section B5"
else
    echo -e "${RED}============================================${NC}"
    echo -e "${RED}  Setup finished with errors (see above).${NC}"
    echo -e "${RED}============================================${NC}"
    echo ""
    echo "Fix the missing items then run ./setup.sh again."
    exit 1
fi
