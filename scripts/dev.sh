#!/usr/bin/env bash
set -euo pipefail

# Hive local development setup
# Usage: bash scripts/dev.sh

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

FRONTEND_PORT=3000
DB_NAME=hive
DEFAULT_HOSTED_URL="https://hive-frontend-staging-production.up.railway.app"

red()   { printf "\033[31m%s\033[0m\n" "$1"; }
green() { printf "\033[32m✓ %s\033[0m\n" "$1"; }
info()  { printf "  %s\n" "$1"; }

cleanup() {
  echo ""
  info "Shutting down..."
  [[ -n "${BACKEND_PID:-}" ]] && kill "$BACKEND_PID" 2>/dev/null
  [[ -n "${FRONTEND_PID:-}" ]] && kill "$FRONTEND_PID" 2>/dev/null
  wait 2>/dev/null
  info "Done."
}
trap cleanup EXIT

echo ""
echo "  Hive Local Development"
echo "  ──────────────────────"
echo ""
echo "  How do you want to run Hive?"
echo ""
echo "    1) Frontend only — connect to hosted backend"
echo "    2) Full local — PostgreSQL + backend + frontend"
echo ""
printf "  Choice [1]: "
read -r MODE_CHOICE
MODE_CHOICE="${MODE_CHOICE:-1}"
echo ""

# ── Common prerequisites ──

if ! command -v node &>/dev/null; then
  red "Node.js not found. Install it first."
  exit 1
fi
green "Node $(node -v)"

# ── Frontend deps ──

if [ ! -d "ui/node_modules" ]; then
  (cd ui && npm install --silent)
fi
green "Frontend deps installed"

# ═══════════════════════════════════════════
# Mode 1: Frontend only (connect to hosted)
# ═══════════════════════════════════════════

if [ "$MODE_CHOICE" = "1" ]; then
  printf "  Backend URL [%s]: " "$DEFAULT_HOSTED_URL"
  read -r BACKEND_URL
  BACKEND_URL="${BACKEND_URL:-$DEFAULT_HOSTED_URL}"

  echo "BACKEND_URL=$BACKEND_URL" > ui/.env.local
  green "Set BACKEND_URL=$BACKEND_URL"

  echo ""
  info "Starting frontend..."
  echo ""

  (cd ui && npm run dev -- --port "$FRONTEND_PORT") &>/dev/null &
  FRONTEND_PID=$!

  for i in $(seq 1 30); do
    if curl -s -o /dev/null "http://localhost:$FRONTEND_PORT" 2>/dev/null; then
      break
    fi
    sleep 1
  done

  if curl -s -o /dev/null "http://localhost:$FRONTEND_PORT" 2>/dev/null; then
    green "Frontend → http://localhost:$FRONTEND_PORT"
    echo ""
    info "Connected to backend at $BACKEND_URL"
    info "Press Ctrl+C to stop."
    echo ""
    wait
  else
    red "Frontend failed to start."
    exit 1
  fi
fi

# ═══════════════════════════════════════════
# Mode 2: Full local setup
# ═══════════════════════════════════════════

# Python
if ! command -v python3 &>/dev/null; then
  red "Python 3 not found. Install it first."
  exit 1
fi
PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
green "Python $PY_VERSION"

# uv
if ! command -v uv &>/dev/null; then
  red "uv not found. Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi
green "uv installed"

# ── PostgreSQL ──

PG_BIN=""
if command -v pg_isready &>/dev/null; then
  PG_BIN=""
elif [ -x "/opt/homebrew/opt/postgresql@17/bin/pg_isready" ]; then
  PG_BIN="/opt/homebrew/opt/postgresql@17/bin/"
elif [ -x "/opt/homebrew/opt/postgresql@16/bin/pg_isready" ]; then
  PG_BIN="/opt/homebrew/opt/postgresql@16/bin/"
else
  info "PostgreSQL not found. Installing via Homebrew..."
  if ! command -v brew &>/dev/null; then
    red "Homebrew not found. Install PostgreSQL manually."
    exit 1
  fi
  brew install postgresql@17
  PG_BIN="/opt/homebrew/opt/postgresql@17/bin/"
fi

# Start PostgreSQL if not running
if ! "${PG_BIN}pg_isready" -q 2>/dev/null; then
  info "Starting PostgreSQL..."
  if command -v brew &>/dev/null; then
    for v in 17 16 15 14; do
      if brew list "postgresql@$v" &>/dev/null; then
        brew services start "postgresql@$v" 2>/dev/null
        break
      fi
    done
  fi
  sleep 2
  if ! "${PG_BIN}pg_isready" -q 2>/dev/null; then
    red "Could not start PostgreSQL."
    exit 1
  fi
fi
green "PostgreSQL running"

# Create database if missing
if ! "${PG_BIN}psql" -lqt 2>/dev/null | grep -qw "$DB_NAME"; then
  "${PG_BIN}createdb" "$DB_NAME"
  green "Created database '$DB_NAME'"
else
  green "Database '$DB_NAME' exists"
fi

export DATABASE_URL="postgresql://localhost:5432/$DB_NAME"

# ── Python deps ──

if [ ! -d ".venv" ]; then
  uv venv
fi
uv pip install -e ".[dev]" -q
green "Python deps installed"

# ── Initialize DB schema ──

python3 -c "from hive.server.db import init_db; init_db()"
green "Database schema ready"

# ── Seed demo data (if empty) ──

TASK_COUNT=$(python3 -c "
import psycopg
conn = psycopg.connect('$DATABASE_URL')
print(conn.execute('SELECT COUNT(*) FROM tasks').fetchone()[0])
conn.close()
")
if [ "$TASK_COUNT" = "0" ]; then
  uv run python scripts/seed_chat_demo.py
  green "Seeded demo data"
else
  green "Database has $TASK_COUNT tasks"
fi

# ── .env.local ──

echo "BACKEND_URL=http://localhost:8001" > ui/.env.local
green "Set BACKEND_URL=http://localhost:8001"

# ── Start services ──

echo ""
info "Starting services..."
echo ""

DATABASE_URL="$DATABASE_URL" uvicorn hive.server.main:app --port 8001 &>/dev/null &
BACKEND_PID=$!

(cd ui && npm run dev -- --port "$FRONTEND_PORT") &>/dev/null &
FRONTEND_PID=$!

for i in $(seq 1 30); do
  if curl -s -o /dev/null "http://localhost:8001/api/tasks" 2>/dev/null; then
    break
  fi
  sleep 1
done

if curl -s -o /dev/null "http://localhost:8001/api/tasks" 2>/dev/null; then
  green "Backend  → http://localhost:8001"
else
  red "Backend failed to start. Check logs."
  exit 1
fi

for i in $(seq 1 30); do
  if curl -s -o /dev/null "http://localhost:$FRONTEND_PORT" 2>/dev/null; then
    break
  fi
  sleep 1
done

if curl -s -o /dev/null "http://localhost:$FRONTEND_PORT" 2>/dev/null; then
  green "Frontend → http://localhost:$FRONTEND_PORT"
else
  red "Frontend failed to start. Check logs."
  exit 1
fi

echo ""
info "Press Ctrl+C to stop all services."
echo ""

wait
