#!/usr/bin/env bash
# setup.sh — Mockingbird one-time environment setup (RHEL 9 / Linux)
#
# Run this ONCE on a fresh EC2 instance or Linux machine before starting services.
# Safe to re-run: it skips steps that are already done.
#
# Usage:
#   chmod +x setup.sh
#   ./setup.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── colours ──────────────────────────────────────────────────────────────────

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RED='\033[0;31m'; NC='\033[0m'

step()  { echo -e "\n${CYAN}===> $1${NC}"; }
ok()    { echo -e "  ${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "  ${YELLOW}[SKIP]${NC} $1"; }
fail()  { echo -e "\n  ${RED}[ERROR]${NC} $1\n"; exit 1; }

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || fail "$1 not found. $2"
}

# ── 1. system packages (RHEL 9 / dnf) ───────────────────────────────────────

step "Installing system packages (requires sudo)"
sudo dnf install -y \
    python3.11 python3.11-pip python3.11-devel \
    gcc gcc-c++ make \
    git curl wget \
    postgresql-devel    # needed by psycopg2-binary build on RHEL

# Install Node.js 20 via NodeSource if not already present
if ! command -v node >/dev/null 2>&1 || [[ "$(node --version | cut -d. -f1 | tr -d 'v')" -lt 20 ]]; then
    step "Installing Node.js 20 (via NodeSource)"
    curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
    sudo dnf install -y nodejs
fi

ok "System packages ready"

# ── 2. verify tools ──────────────────────────────────────────────────────────

step "Checking tool versions"
require_cmd "python3.11" "Run: sudo dnf install python3.11"
require_cmd "node"       "Run: sudo dnf install nodejs"
require_cmd "git"        "Run: sudo dnf install git"

ok "Python  : $(python3.11 --version)"
ok "Node.js : $(node --version)"
ok "Git     : $(git --version)"

# ── helper: set up a Python service ──────────────────────────────────────────

setup_python_service() {
    local label="$1"
    local dir="$2"
    local extras="$3"

    step "Python service: $label"
    pushd "$ROOT/$dir" >/dev/null

    if [[ -d "venv" ]]; then
        warn "venv already exists — skipping creation"
    else
        echo "  Creating virtual environment..."
        python3.11 -m venv venv
        ok "venv created"
    fi

    echo "  Upgrading pip..."
    venv/bin/python -m pip install --upgrade pip --quiet

    echo "  Installing packages..."
    # shellcheck disable=SC2086
    venv/bin/python -m pip install $extras --quiet
    ok "packages installed"

    echo "  Generating requirements.txt..."
    venv/bin/python -m pip freeze > requirements.txt
    ok "requirements.txt written"

    popd >/dev/null
}

# ── helper: set up a Node.js service ─────────────────────────────────────────

setup_node_service() {
    local label="$1"
    local dir="$2"

    step "Node.js service: $label"
    pushd "$ROOT/$dir" >/dev/null
    npm install --silent
    ok "npm packages installed"
    popd >/dev/null
}

# ── 3. parser-worker (must install BEFORE ingestion-service) ─────────────────

setup_python_service "parser-worker" "services/parser-worker" "-e '.[dev]'"

# ── 4. project-service ────────────────────────────────────────────────────────

setup_python_service "project-service" "services/project-service" "-e '.[dev]'"

step "Creating project-service SQLite database"
pushd "$ROOT/services/project-service" >/dev/null
DATABASE_URL="sqlite:///./mockingbird.db" venv/bin/python -m alembic upgrade head
ok "database tables created — mockingbird.db"
popd >/dev/null

# ── 5. ingestion-service ─────────────────────────────────────────────────────

step "Python service: ingestion-service"
pushd "$ROOT/services/ingestion-service" >/dev/null

if [[ -d "venv" ]]; then
    warn "venv already exists — skipping creation"
else
    echo "  Creating virtual environment..."
    python3.11 -m venv venv
    ok "venv created"
fi

echo "  Upgrading pip..."
venv/bin/python -m pip install --upgrade pip --quiet

echo "  Installing parser-worker into this venv first..."
venv/bin/python -m pip install -e "../parser-worker" --quiet
ok "parser-worker installed"

echo "  Installing ingestion-service packages..."
venv/bin/python -m pip install -e ".[dev]" --quiet
ok "packages installed"

echo "  Generating requirements.txt..."
venv/bin/python -m pip freeze > requirements.txt
ok "requirements.txt written"

popd >/dev/null

# ── 6. auth-service ───────────────────────────────────────────────────────────

setup_node_service "auth-service" "services/auth-service"

# ── 7. portal ─────────────────────────────────────────────────────────────────

setup_node_service "portal" "portal"

# ── 8. verify ────────────────────────────────────────────────────────────────

step "Verifying setup"
ALL_OK=true
declare -A checks=(
    ["parser-worker venv"]="services/parser-worker/venv"
    ["project-service venv"]="services/project-service/venv"
    ["project-service database"]="services/project-service/mockingbird.db"
    ["ingestion-service venv"]="services/ingestion-service/venv"
    ["auth-service node_modules"]="services/auth-service/node_modules"
    ["portal node_modules"]="portal/node_modules"
)
for label in "${!checks[@]}"; do
    path="$ROOT/${checks[$label]}"
    if [[ -e "$path" ]]; then
        ok "$label"
    else
        echo -e "  ${RED}[MISSING]${NC} $label — $path"
        ALL_OK=false
    fi
done

# ── done ─────────────────────────────────────────────────────────────────────

echo ""
if [[ "$ALL_OK" == "true" ]]; then
    echo -e "${GREEN}============================================${NC}"
    echo -e "${GREEN}  Setup complete. All checks passed.${NC}"
    echo -e "${GREEN}============================================${NC}"
    echo ""
    echo -e "${YELLOW}Next steps:${NC}"
    echo "  1. Start services:  ./start-dev.sh"
    echo "  2. Open browser:    http://<server-ip>:3000"
    echo "  3. Create admin:    see docs/LOCAL_DEVELOPMENT.md Section 5"
else
    echo -e "${RED}============================================${NC}"
    echo -e "${RED}  Setup finished with errors (see above).${NC}"
    echo -e "${RED}============================================${NC}"
    echo ""
    echo "Fix the missing items then run ./setup.sh again."
    exit 1
fi
