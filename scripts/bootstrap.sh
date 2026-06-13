#!/usr/bin/env bash
# =============================================================================
# Tranc3 Platform Bootstrap
# Single-command setup for self-hosted zero-cost architecture
#
# Usage:
#   ./scripts/bootstrap.sh [--env dev|staging|production] [--skip-deps]
#
# What this does:
#   1. Validates dependencies (Python 3.11+, Docker, Docker Compose)
#   2. Generates cryptographically strong secrets
#   3. Creates .env from .env.example with real secrets injected
#   4. Initialises all SQLite databases for workers
#   5. Validates the environment (imports, config checks)
#   6. Optionally starts all P0/P1 workers (--start)
# =============================================================================
set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'
BOLD='\033[1m'; NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }
die()   { error "$*"; exit 1; }

# ── Argument parsing ─────────────────────────────────────────────────────────
ENV_MODE="dev"
SKIP_DEPS=false
START_WORKERS=false

for arg in "$@"; do
  case "$arg" in
    --env=*) ENV_MODE="${arg#*=}" ;;
    --skip-deps) SKIP_DEPS=true ;;
    --start) START_WORKERS=true ;;
    -h|--help)
      echo "Usage: $0 [--env dev|staging|production] [--skip-deps] [--start]"
      exit 0 ;;
    *) warn "Unknown argument: $arg" ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║      Tranc3 Platform Bootstrap — ${ENV_MODE}           ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════╝${NC}"
echo ""

# ── 1. Dependency checks ─────────────────────────────────────────────────────
if [ "$SKIP_DEPS" = false ]; then
  info "Checking required dependencies..."

  # Python 3.11+
  if ! command -v python3 &>/dev/null; then
    die "Python 3 not found. Install Python 3.11+."
  fi
  PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
  PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
  PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
  if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]; }; then
    die "Python 3.11+ required (found $PY_VER)."
  fi
  ok "Python $PY_VER"

  # Docker
  if ! command -v docker &>/dev/null; then
    warn "Docker not found — Docker-based workers will not start."
  else
    ok "Docker $(docker --version | awk '{print $3}' | tr -d ',')"
  fi

  # Docker Compose
  if docker compose version &>/dev/null 2>&1; then
    ok "Docker Compose $(docker compose version --short 2>/dev/null || echo 'v2')"
  elif command -v docker-compose &>/dev/null; then
    ok "docker-compose (legacy)"
  else
    warn "Docker Compose not found — stack orchestration unavailable."
  fi

  # pip
  if ! python3 -m pip --version &>/dev/null; then
    die "pip not found. Install pip for Python $PY_VER."
  fi
  ok "pip $(python3 -m pip --version | awk '{print $2}')"
fi

# ── 2. Generate secrets ───────────────────────────────────────────────────────
info "Generating cryptographic secrets..."

SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
VAULT_MASTER_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
LIGHTHOUSE_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
HIVE_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

ok "Secrets generated (hex-256 entropy)"

# ── 3. Create .env ────────────────────────────────────────────────────────────
ENV_FILE="$REPO_ROOT/.env"

if [ -f "$ENV_FILE" ]; then
  warn ".env already exists — preserving secrets, filling any blanks"
else
  info "No .env found — generating fresh configuration..."
fi

# Use generate_env.py as the authoritative .env generator.
# It auto-detects running services, generates all secrets, and validates output.
PROD_FLAG=""
if [ "$ENV_MODE" = "production" ]; then
  PROD_FLAG="--prod"
fi
python3 "$REPO_ROOT/scripts/generate_env.py" $PROD_FLAG || die "generate_env.py failed — check Python dependencies"

ok ".env ready at $ENV_FILE"

# ── 4. Initialise SQLite databases ────────────────────────────────────────────
info "Initialising SQLite databases for workers..."

DB_DIR="$REPO_ROOT/data/databases"
mkdir -p "$DB_DIR"

# List of workers that use SQLite (from Dockerfile WORKDIR patterns)
SQLITE_WORKERS=(
  "infinity-auth:8005"
  "infinity-ws:8004"
  "users-service:8006"
  "monitoring:8007"
  "notifications:8008"
  "infinity-ai:8009"
  "the-grid:8010"
  "products-service:8011"
  "orders-service:8012"
  "payments-service:8013"
  "files-service:8014"
  "identity-service:8015"
  "queue-service:8016"
  "vault-service:8030"
  "workflow-engine-service:8034"
  "langchain-integration-service:8036"
  "deepagents-orchestrator-service:8037"
)

for entry in "${SQLITE_WORKERS[@]}"; do
  worker="${entry%%:*}"
  db_path="$DB_DIR/${worker}.db"
  if [ ! -f "$db_path" ]; then
    python3 -c "
import sqlite3, pathlib
db = pathlib.Path('$db_path')
db.parent.mkdir(parents=True, exist_ok=True)
conn = sqlite3.connect(str(db))
conn.execute('PRAGMA journal_mode=WAL')
conn.execute('PRAGMA synchronous=NORMAL')
conn.commit()
conn.close()
print(f'  Created: $db_path')
"
  fi
done

ok "SQLite databases initialised in $DB_DIR"

# ── 5. Install Python dependencies ────────────────────────────────────────────
if [ "$SKIP_DEPS" = false ] && [ "$ENV_MODE" != "production" ]; then
  info "Installing Python dependencies (dev mode)..."
  python3 -m pip install --quiet --upgrade pip
  python3 -m pip install --quiet -r requirements.txt || {
    warn "Some packages failed to install — this may be normal if CUDA/torch unavailable"
    warn "Core platform will still function in bootstrap mode"
  }
  ok "Dependencies installed"
fi

# ── 6. Validate environment ───────────────────────────────────────────────────
info "Validating platform configuration..."

python3 - <<'PYEOF'
import sys, os
sys.path.insert(0, os.getcwd())

checks_passed = 0
checks_failed = 0

def check(name, fn):
    global checks_passed, checks_failed
    try:
        fn()
        print(f"  ✓ {name}")
        checks_passed += 1
    except Exception as e:
        print(f"  ✗ {name}: {e}", file=sys.stderr)
        checks_failed += 1

# Check core imports
check("FastAPI importable", lambda: __import__("fastapi"))
check("Pydantic v2", lambda: __import__("pydantic"))
check("structlog importable", lambda: __import__("structlog"))
check("httpx importable", lambda: __import__("httpx"))

# Check shared_core basics
try:
    sys.path.insert(0, os.path.join(os.getcwd(), "shared_core"))
    check("shared_core.genetics importable", lambda: __import__("shared_core.genetics"))
    check("shared_core.liquid importable", lambda: __import__("shared_core.liquid"))
    check("shared_core.gas importable", lambda: __import__("shared_core.gas"))
except Exception:
    pass

# Check optional advanced packages
for pkg, label in [
    ("ncps", "ncps (Liquid Neural Networks)"),
    ("deap", "DEAP (Genetic Algorithms)"),
    ("pygad", "PyGAD (Simple GA)"),
    ("prometheus_client", "prometheus-client"),
    ("opentelemetry.api", "OpenTelemetry API"),
    ("cachetools", "cachetools"),
    ("nats", "nats-py"),
]:
    try:
        __import__(pkg)
        print(f"  ✓ {label}")
        checks_passed += 1
    except ImportError:
        print(f"  ~ {label} (optional, not installed)")

print(f"\n  Passed: {checks_passed}  |  Failed: {checks_failed}")
if checks_failed:
    sys.exit(1)
PYEOF

ok "Environment validation complete"

# ── 7. Optional: start P0 workers ─────────────────────────────────────────────
if [ "$START_WORKERS" = true ]; then
  info "Starting P0 workers (infinity-ws :8004, infinity-auth :8005)..."

  if command -v docker &>/dev/null && docker compose version &>/dev/null 2>&1; then
    docker compose -f docker-compose.production.yml up -d infinity-ws infinity-auth 2>/dev/null || {
      warn "Docker Compose start failed — try: make dev-api"
    }
  else
    warn "Docker not available — start workers manually:"
    warn "  uvicorn workers.infinity_ws.main:app --port 8004 &"
    warn "  uvicorn workers.infinity_auth.worker:app --port 8005 &"
  fi
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  Tranc3 Platform Bootstrap Complete!${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"
echo ""
echo "  Environment : $ENV_MODE"
echo "  .env        : $ENV_FILE"
echo "  Databases   : $DB_DIR"
echo ""
echo "  Next steps:"
echo "    make dev-api          # Start FastAPI backend on :8000"
echo "    make dev-web          # Start frontend dev server"
echo "    make test             # Run full test suite"
echo "    docker compose up -d  # Start full production stack"
echo ""
echo -e "  ${YELLOW}IMPORTANT:${NC} Set DATABASE_URL and REDIS_URL in .env"
echo "             before starting production workers."
echo ""
