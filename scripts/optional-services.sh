#!/usr/bin/env bash
# Trancendos Optional Services Management Script
# Usage:
#   bash scripts/optional-services.sh start <profile|all>
#   bash scripts/optional-services.sh stop  <profile|all>
#   bash scripts/optional-services.sh restart <profile|all>
#   bash scripts/optional-services.sh status
#   bash scripts/optional-services.sh logs <profile>
#   bash scripts/optional-services.sh init-network
#
# Profiles: library | documents | design | workshop | scheduling | registry | api-marketplace | sandbox | health | all

set -euo pipefail

COMPOSE_FILE="$(dirname "$(realpath "$0")")/../docker-compose.optional-services.yml"
ENV_FILE="$(dirname "$(realpath "$0")")/../.env.optional-services"

PROFILES=(library documents design workshop scheduling registry api-marketplace sandbox health)

# Colour helpers
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

info()    { echo -e "${CYAN}[optional-svc]${NC} $*"; }
success() { echo -e "${GREEN}[optional-svc]${NC} $*"; }
warn()    { echo -e "${YELLOW}[optional-svc]${NC} $*"; }
error()   { echo -e "${RED}[optional-svc]${NC} $*"; exit 1; }

require_env() {
  if [[ ! -f "$ENV_FILE" ]]; then
    warn ".env.optional-services not found — copying from .env.optional-services.example"
    cp "$(dirname "$ENV_FILE")/.env.optional-services.example" "$ENV_FILE" 2>/dev/null || \
      error "No .env.optional-services.example found. Run: cp .env.optional-services.example .env.optional-services"
  fi
}

init_network() {
  if ! docker network inspect tranc3-network >/dev/null 2>&1; then
    info "Creating tranc3-network..."
    docker network create tranc3-network
    success "Network created."
  else
    info "tranc3-network already exists."
  fi
}

compose() {
  local profile="$1"; shift
  if [[ -f "$ENV_FILE" ]]; then
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" --profile "$profile" "$@"
  else
    docker compose -f "$COMPOSE_FILE" --profile "$profile" "$@"
  fi
}

cmd_start() {
  local profile="${1:-all}"
  require_env
  init_network
  info "Starting profile: $profile..."
  compose "$profile" up -d --remove-orphans
  success "Started: $profile"
}

cmd_stop() {
  local profile="${1:-all}"
  info "Stopping profile: $profile..."
  compose "$profile" down
  success "Stopped: $profile"
}

cmd_restart() {
  cmd_stop "${1:-all}"
  cmd_start "${1:-all}"
}

cmd_status() {
  info "Optional services status:"
  echo ""
  for profile in "${PROFILES[@]}"; do
    containers=$(docker compose -f "$COMPOSE_FILE" --profile "$profile" ps --format json 2>/dev/null || echo "[]")
    count=$(echo "$containers" | python3 -c "import sys,json; d=json.load(sys.stdin) if isinstance(json.load(open('/dev/stdin')) if False else json.loads(sys.stdin.read()), list) else []; print(len(d))" 2>/dev/null || echo "?")
    echo -e "  ${CYAN}${profile}${NC}"
  done
  echo ""
  docker ps --filter "name=the-library" \
            --filter "name=docutari" \
            --filter "name=fabulousa" \
            --filter "name=the-workshop" \
            --filter "name=chronossphere" \
            --filter "name=the-artifactory" \
            --filter "name=api-marketplace" \
            --filter "name=the-ice-box" \
            --filter "name=optional-services-health" \
            --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || true
}

cmd_logs() {
  local profile="${1:-all}"
  compose "$profile" logs -f --tail=100
}

cmd_init_network() {
  init_network
}

cmd_generate_secrets() {
  info "Generating random secrets for .env.optional-services..."
  python3 - <<'PYEOF'
import secrets, string, sys

def gen(n=32):
    return secrets.token_hex(n)

def gen_pw(n=20):
    alpha = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alpha) for _ in range(n))

print(f"OUTLINE_SECRET_KEY={gen()}")
print(f"OUTLINE_UTILS_SECRET={gen()}")
print(f"OUTLINE_DB_PASSWORD={gen_pw()}")
print(f"PAPERLESS_SECRET_KEY={gen()}")
print(f"PAPERLESS_DB_PASSWORD={gen_pw()}")
print(f"PAPERLESS_ADMIN_PASSWORD={gen_pw(16)}")
print(f"PENPOT_SECRET_KEY={gen()}")
print(f"PENPOT_DB_PASSWORD={gen_pw()}")
print(f"CAL_NEXTAUTH_SECRET={gen()}")
print(f"CAL_DB_PASSWORD={gen_pw()}")
print(f"CAL_ENCRYPTION_KEY={gen(16)}")
print(f"ICEBOX_SECRET_KEY={gen()}")
PYEOF
  success "Copy the above values into your .env.optional-services file."
}

case "${1:-help}" in
  start)   cmd_start "${2:-all}" ;;
  stop)    cmd_stop "${2:-all}" ;;
  restart) cmd_restart "${2:-all}" ;;
  status)  cmd_status ;;
  logs)    cmd_logs "${2:-all}" ;;
  init-network) cmd_init_network ;;
  gen-secrets)  cmd_generate_secrets ;;
  help|*)
    echo ""
    echo "  Trancendos Optional Services Manager"
    echo ""
    echo "  Commands:"
    echo "    start [profile]     Start services (default: all)"
    echo "    stop  [profile]     Stop services"
    echo "    restart [profile]   Restart services"
    echo "    status              Show running containers"
    echo "    logs [profile]      Follow logs"
    echo "    init-network        Create tranc3-network if missing"
    echo "    gen-secrets         Generate random secrets for .env"
    echo ""
    echo "  Profiles: ${PROFILES[*]} | all"
    echo ""
    ;;
esac
