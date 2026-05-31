#!/usr/bin/env bash
# One-command live deploy for The Citadel — generates secrets, builds stack, waits for health.
# Usage: ./scripts/deploy_live.sh [--skip-build] [--profile full]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE_FILE="docker-compose.production.yml"
SKIP_BUILD=false
PROFILE="${DEPLOY_PROFILE:-core}"

for arg in "$@"; do
  case "$arg" in
    --skip-build) SKIP_BUILD=true ;;
    --profile=*) PROFILE="${arg#*=}" ;;
  esac
done

# Core P0+P1 — minimum live product
CORE_SERVICES=(
  traefik valkey vault ollama
  tranc3-backend tranc3-ai infinity-void
  infinity-ws infinity-auth
  users-service products-service orders-service payments-service
  api-gateway
  monitoring notifications infinity-ai
  infinity-admin swarm-coordinator
  prometheus grafana
)

FULL_EXTRA=(
  the-grid files-service identity-service health-aggregator
  vault-service gbrain-bridge
)

echo "==> Generate production environment (if missing)"
if [[ ! -f .env.production ]]; then
  ./scripts/generate_production_env.sh
else
  echo "Using existing .env.production"
fi

echo "==> Preflight"
python3 scripts/citadel_compose_validate.py
python3 scripts/citadel_preflight.py || {
  echo "WARN: preflight reported issues — continuing for local Citadel bootstrap"
}

SERVICES=("${CORE_SERVICES[@]}")
if [[ "$PROFILE" == "full" ]]; then
  SERVICES+=("${FULL_EXTRA[@]}")
fi

if [[ "$SKIP_BUILD" != true ]]; then
  echo "==> Build images"
  docker compose -f "$COMPOSE_FILE" build "${SERVICES[@]}"
fi

echo "==> Start infrastructure first"
docker compose -f "$COMPOSE_FILE" up -d valkey vault traefik ollama

echo "==> Vault init (if sealed)"
if docker compose -f "$COMPOSE_FILE" ps vault 2>/dev/null | grep -q Up; then
  sleep 5
  if docker compose -f "$COMPOSE_FILE" exec -T vault vault status 2>&1 | grep -q "Initialized.*false"; then
    echo "Run ./deploy/vault/init-citadel.sh manually if Vault is not initialized."
  fi
fi

echo "==> Start platform workers"
docker compose -f "$COMPOSE_FILE" up -d "${SERVICES[@]}"

echo "==> Wait for health (up to 10 min)"
python3 scripts/wait_for_healthy.py --timeout 600 || {
  echo "Some services still starting — run: make monitor"
  exit 1
}

echo "==> Post-deploy checks"
python3 scripts/health_check.py --json || python3 scripts/health_check.py || true
python3 scripts/zero_cost_audit.py
python3 scripts/production_readiness_score.py

if [[ -f scripts/seed_uat_data.py ]]; then
  echo "==> Optional UAT seed"
  python3 scripts/seed_uat_data.py || true
fi

echo ""
echo "Live deploy complete."
echo "  API:        http://localhost:8000/health"
echo "  Gateway:    http://localhost:8003/"
echo "  Dashboard:  http://localhost:8000/dashboard/"
echo "  Admin OS:   http://localhost:8000/dashboard/infinity-admin-os.html"
echo "  Grafana:    http://localhost:3000"
echo "  Traefik:    http://localhost:8888"
