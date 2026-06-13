#!/usr/bin/env bash
# =============================================================================
# Tranc3 Platform Deployment Selector
# Supports three deployment modes:
#   cloud   — Fly.io backend + Cloudflare Workers (edge)
#   hybrid  — Local FastAPI + Cloudflare Workers (CF handles edge traffic)
#   local   — Fully self-hosted Docker Compose stack (zero external deps)
# =============================================================================
set -euo pipefail

MODE="${1:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

usage() {
    cat <<EOF
Usage: $0 <mode> [options]

Modes:
  cloud   Deploy to Fly.io + Cloudflare Workers
  hybrid  Start local workers + configure Cloudflare edge
  local   Start fully self-hosted Docker Compose stack

Options:
  --skip-checks   Skip pre-flight environment checks
  --dry-run       Print commands without executing them
  --help          Show this help

Examples:
  $0 cloud
  $0 local --skip-checks
  $0 hybrid --dry-run
EOF
    exit 1
}

SKIP_CHECKS=false
DRY_RUN=false

for arg in "${@:2}"; do
    case "$arg" in
        --skip-checks) SKIP_CHECKS=true ;;
        --dry-run)     DRY_RUN=true ;;
        --help)        usage ;;
        *) echo "Unknown option: $arg"; usage ;;
    esac
done

run() {
    if [ "$DRY_RUN" = true ]; then
        echo "[dry-run] $*"
    else
        echo "▶ $*"
        "$@"
    fi
}

check_env() {
    local var="$1"
    if [ -z "${!var:-}" ]; then
        echo "✗ Missing required env var: $var"
        return 1
    fi
    echo "✓ $var"
}

preflight_cloud() {
    echo "=== Cloud pre-flight checks ==="
    check_env SECRET_KEY
    check_env JWT_SECRET
    check_env DATABASE_URL
    check_env REDIS_URL
    command -v fly  >/dev/null 2>&1 || { echo "✗ flyctl not installed"; exit 1; }
    echo "✓ flyctl"
}

preflight_local() {
    echo "=== Local pre-flight checks ==="
    command -v docker >/dev/null 2>&1 || { echo "✗ Docker not installed"; exit 1; }
    echo "✓ docker"
    command -v docker compose >/dev/null 2>&1 || docker-compose version >/dev/null 2>&1 \
        || { echo "✗ docker compose not available"; exit 1; }
    echo "✓ docker compose"
    if [ ! -f "${REPO_ROOT}/.env" ]; then
        echo "⚠ No .env file found — copying .env.example"
        cp "${REPO_ROOT}/.env.example" "${REPO_ROOT}/.env"
        echo "  Edit ${REPO_ROOT}/.env before production use."
    fi
}

deploy_cloud() {
    echo ""
    echo "═══════════════════════════════════════"
    echo " TRANC3 — CLOUD DEPLOYMENT (Fly.io)"
    echo "═══════════════════════════════════════"

    [ "$SKIP_CHECKS" = false ] && preflight_cloud

    echo ""
    echo "1/3 — Backend (tranc3-backend)"
    run fly deploy --remote-only --app tranc3-backend --config "${REPO_ROOT}/fly.toml"

    echo ""
    echo "2/3 — Bots (tranc3-bots)"
    run fly deploy --remote-only --app tranc3-bots --config "${REPO_ROOT}/tranc3-bots/fly.toml"

    echo ""
    echo "3/3 — Cloudflare Workers"
    for worker in tranc3-ai infinity-void trancendos-api-gateway; do
        dir="${REPO_ROOT}/cloudflare/${worker}"
        if [ -d "$dir" ] && [ -f "${dir}/wrangler.toml" ]; then
            echo "  Deploying CF worker: ${worker}"
            run sh -c "cd '${dir}' && npm ci --silent && npx wrangler deploy"
        fi
    done

    echo ""
    echo "✅ Cloud deployment complete"
}

deploy_hybrid() {
    echo ""
    echo "═══════════════════════════════════════"
    echo " TRANC3 — HYBRID DEPLOYMENT"
    echo "═══════════════════════════════════════"

    [ "$SKIP_CHECKS" = false ] && preflight_local

    echo ""
    echo "1/2 — Starting local services"
    run docker compose -f "${REPO_ROOT}/docker-compose.hybrid.yml" up -d --build

    echo ""
    echo "2/2 — Cloudflare Workers (edge layer)"
    for worker in tranc3-ai trancendos-api-gateway; do
        dir="${REPO_ROOT}/cloudflare/${worker}"
        if [ -d "$dir" ] && [ -f "${dir}/wrangler.toml" ]; then
            echo "  Deploying CF worker: ${worker}"
            run sh -c "cd '${dir}' && npm ci --silent && npx wrangler deploy"
        fi
    done

    echo ""
    echo "✅ Hybrid deployment complete"
    echo "   Local API:  http://localhost:8000"
    echo "   Edge proxy: https://api.trancendos.com"
}

deploy_local() {
    echo ""
    echo "═══════════════════════════════════════"
    echo " TRANC3 — LOCAL / SELF-HOSTED DEPLOYMENT"
    echo "═══════════════════════════════════════"

    [ "$SKIP_CHECKS" = false ] && preflight_local

    echo ""
    echo "1/1 — Starting full self-hosted stack (29 workers + infra)"
    run docker compose -f "${REPO_ROOT}/docker-compose.production.yml" up -d --build

    echo ""
    echo "Waiting for core services..."
    sleep 5

    # Health check
    if docker compose -f "${REPO_ROOT}/docker-compose.production.yml" ps --format json 2>/dev/null | grep -q '"Status":"running"' || \
       docker compose -f "${REPO_ROOT}/docker-compose.production.yml" ps 2>/dev/null | grep -q "Up"; then
        echo "✅ Local deployment healthy"
    else
        echo "⚠ Some services may still be starting — check with:"
        echo "  docker compose -f docker-compose.production.yml ps"
    fi

    echo ""
    echo "Service endpoints:"
    echo "  Main API:       http://localhost:8000"
    echo "  Traefik dash:   http://localhost:8080"
    echo "  Grafana:        http://localhost:3000"
    echo "  Prometheus:     http://localhost:9090"
    echo "  The Town Hall:  http://localhost:8071"
}

case "$MODE" in
    cloud)  deploy_cloud  ;;
    hybrid) deploy_hybrid ;;
    local)  deploy_local  ;;
    ""|--help) usage ;;
    *) echo "Unknown mode: $MODE"; usage ;;
esac
