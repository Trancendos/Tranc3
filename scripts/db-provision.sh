#!/usr/bin/env bash
# scripts/db-provision.sh
# ─────────────────────────────────────────────────────────────────────────────
# Provision the Tranc3 development database.
#
# Usage:
#   ./scripts/db-provision.sh              # start postgres + run migrations
#   ./scripts/db-provision.sh --reset      # drop & recreate the volume first
#   ./scripts/db-provision.sh --migrate-only  # only run alembic upgrade head
#   ./scripts/db-provision.sh --status     # show migration status + table list
#
# After this runs, connect with:
#   psql postgresql://tranc3:tranc3dev@localhost:5432/tranc3
#   http://localhost:8080  (adminer — server: postgres, db: tranc3)
#
# For Supabase (production), set DATABASE_URL in .env and run:
#   ./scripts/db-provision.sh --migrate-only
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.development.yml}"
LOCAL_DB_URL="postgresql://tranc3:tranc3dev@localhost:5432/tranc3"
CONTAINER_DB_URL="postgresql://tranc3:tranc3dev@postgres:5432/tranc3"
POSTGRES_CONTAINER="tranc3-dev-postgres"
MAX_WAIT=60   # seconds to wait for postgres to be healthy

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[db-provision]${RESET} $*"; }
success() { echo -e "${GREEN}[db-provision]${RESET} $*"; }
warn()    { echo -e "${YELLOW}[db-provision]${RESET} $*"; }
die()     { echo -e "${RED}[db-provision] ERROR:${RESET} $*" >&2; exit 1; }

# ── Parse arguments ───────────────────────────────────────────────────────────
RESET_DB=false
MIGRATE_ONLY=false
STATUS_ONLY=false

for arg in "$@"; do
  case "$arg" in
    --reset)        RESET_DB=true ;;
    --migrate-only) MIGRATE_ONLY=true ;;
    --status)       STATUS_ONLY=true ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \?//' | head -20
      exit 0
      ;;
    *) die "Unknown argument: $arg" ;;
  esac
done

# ── Dependency checks ─────────────────────────────────────────────────────────
command -v docker >/dev/null 2>&1 || die "docker is not installed"
command -v docker-compose >/dev/null 2>&1 || \
  docker compose version >/dev/null 2>&1 || \
  die "docker-compose / docker compose plugin is not installed"

# Prefer 'docker compose' (v2) over 'docker-compose' (v1)
if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
else
  DC="docker-compose"
fi

# ── Status mode ───────────────────────────────────────────────────────────────
if $STATUS_ONLY; then
  info "Migration status:"
  if docker ps --format '{{.Names}}' | grep -q "^${POSTGRES_CONTAINER}$"; then
    DATABASE_URL="$LOCAL_DB_URL" alembic current 2>/dev/null || \
      warn "alembic not in PATH — run inside venv"
    info "Tables in tranc3 database:"
    docker exec "$POSTGRES_CONTAINER" \
      psql -U tranc3 -d tranc3 -c "\dt" 2>/dev/null || \
      warn "Could not list tables — is postgres running?"
  else
    warn "Postgres container (${POSTGRES_CONTAINER}) is not running"
    info "Run: ./scripts/db-provision.sh"
  fi
  exit 0
fi

# ── Migrate-only mode (no docker management, uses DATABASE_URL from env) ─────
if $MIGRATE_ONLY; then
  DB_URL="${DATABASE_URL:-$LOCAL_DB_URL}"
  info "Running alembic upgrade head against: ${DB_URL%%@*}@..."
  command -v alembic >/dev/null 2>&1 || die "alembic not in PATH — activate your venv"
  DATABASE_URL="$DB_URL" alembic upgrade head
  success "Migrations applied."
  exit 0
fi

# ── Reset: tear down volume ───────────────────────────────────────────────────
if $RESET_DB; then
  warn "Resetting database — this will DELETE ALL local dev data!"
  read -r -p "Are you sure? [y/N] " confirm
  [[ "$confirm" =~ ^[Yy]$ ]] || { info "Aborted."; exit 0; }
  info "Stopping postgres and removing volume..."
  $DC -f "$COMPOSE_FILE" stop postgres db-migrate adminer 2>/dev/null || true
  $DC -f "$COMPOSE_FILE" rm -f postgres db-migrate adminer 2>/dev/null || true
  docker volume rm tranc3_postgres_dev 2>/dev/null || true
  success "Volume removed."
fi

# ── Start postgres ────────────────────────────────────────────────────────────
info "Starting postgres service..."
$DC -f "$COMPOSE_FILE" up -d postgres

# ── Wait for healthy ──────────────────────────────────────────────────────────
info "Waiting for postgres to be healthy (up to ${MAX_WAIT}s)..."
elapsed=0
until docker inspect --format='{{.State.Health.Status}}' \
    "$POSTGRES_CONTAINER" 2>/dev/null | grep -q "healthy"; do
  if [[ $elapsed -ge $MAX_WAIT ]]; then
    die "Postgres did not become healthy within ${MAX_WAIT}s"
  fi
  sleep 2
  elapsed=$((elapsed + 2))
  printf '.'
done
echo ""
success "Postgres is healthy."

# ── Run migrations via db-migrate container ───────────────────────────────────
info "Running alembic migrations..."
$DC -f "$COMPOSE_FILE" run --rm db-migrate
success "Migrations applied."

# ── Show result ───────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${GREEN}  Database provisioned successfully${RESET}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""
echo -e "  ${BOLD}Connection string:${RESET}"
echo -e "    ${CYAN}postgresql://tranc3:tranc3dev@localhost:5432/tranc3${RESET}"
echo ""
echo -e "  ${BOLD}psql:${RESET}"
echo -e "    ${CYAN}psql postgresql://tranc3:tranc3dev@localhost:5432/tranc3${RESET}"
echo ""
echo -e "  ${BOLD}Adminer (browser UI):${RESET}"
echo -e "    Start: ${CYAN}$DC -f $COMPOSE_FILE up -d adminer${RESET}"
echo -e "    URL:   ${CYAN}http://localhost:8080${RESET}"
echo -e "    Login: server=postgres  user=tranc3  password=tranc3dev  db=tranc3"
echo ""
echo -e "  ${BOLD}Check migration status:${RESET}"
echo -e "    ${CYAN}./scripts/db-provision.sh --status${RESET}"
echo ""
echo -e "  ${BOLD}For Supabase (production):${RESET}"
echo -e "    Set DATABASE_URL in .env, then:"
echo -e "    ${CYAN}./scripts/db-provision.sh --migrate-only${RESET}"
echo ""
