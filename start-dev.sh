#!/usr/bin/env bash
# start-dev.sh — Start all Mockingbird services on RHEL 9 / Linux
#
# Run this every time you want to start the platform.
# Prerequisite: run ./setup.sh once first.
#
# Usage:
#   ./start-dev.sh
#
# To stop: press Ctrl+C (stops all background processes together)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RED='\033[0;31m'; NC='\033[0m'

step() { echo -e "\n${CYAN}===> $1${NC}"; }
ok()   { echo -e "  ${GREEN}[OK]${NC} $1"; }
fail() { echo -e "\n  ${RED}[ERROR]${NC} $1\n"; exit 1; }

# Verify setup was done
for f in \
    "services/parser-worker/venv" \
    "services/project-service/venv" \
    "services/ingestion-service/venv" \
    "services/auth-service/node_modules" \
    "portal/node_modules"; do
    [[ -e "$ROOT/$f" ]] || fail "$f not found — run ./setup.sh first"
done

step "Starting Mockingbird services"

# Collect PIDs so Ctrl+C kills all of them cleanly
PIDS=()

cleanup() {
    echo ""
    echo -e "${YELLOW}Stopping all services...${NC}"
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    exit 0
}
trap cleanup SIGINT SIGTERM

# 1. auth-service
echo "  Starting auth-service on port 3001..."
pushd "$ROOT/services/auth-service" >/dev/null
npm run dev > "$ROOT/logs/auth-service.log" 2>&1 &
PIDS+=($!)
popd >/dev/null

# 2. project-service
echo "  Starting project-service on port 8001..."
pushd "$ROOT/services/project-service" >/dev/null
DATABASE_URL="sqlite:///./mockingbird.db" \
    venv/bin/python -m uvicorn project_service.main:app \
    --host 0.0.0.0 --port 8001 --reload \
    > "$ROOT/logs/project-service.log" 2>&1 &
PIDS+=($!)
popd >/dev/null

# 3. ingestion-service
echo "  Starting ingestion-service on port 8003..."
pushd "$ROOT/services/ingestion-service" >/dev/null
DATABASE_URL="sqlite:///./ingestion.db" \
LOCAL_STORAGE_PATH="./uploads" \
JWT_SECRET="local-dev-secret" \
    venv/bin/python -m uvicorn ingestion_service.main:app \
    --host 0.0.0.0 --port 8003 --reload \
    > "$ROOT/logs/ingestion-service.log" 2>&1 &
PIDS+=($!)
popd >/dev/null

# 4. portal
echo "  Starting portal on port 3000..."
pushd "$ROOT/portal" >/dev/null
npm run dev -- --host 0.0.0.0 > "$ROOT/logs/portal.log" 2>&1 &
PIDS+=($!)
popd >/dev/null

ok "All services started (PIDs: ${PIDS[*]})"
echo ""
echo -e "${YELLOW}Logs are written to:${NC} $ROOT/logs/"
echo -e "${YELLOW}Open browser at:${NC}    http://localhost:3000"
echo ""
echo "Press Ctrl+C to stop all services."
echo ""

# Wait — keeps script alive until Ctrl+C
wait
