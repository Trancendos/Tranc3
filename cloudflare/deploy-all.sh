#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Trancendos — Cloudflare Unified Deploy Script
# Deploys all workers + frontend to trancendos.com at zero cost.
#
# Prerequisites:
#   npm install -g wrangler
#   wrangler login
#
# Usage:
#   ./cloudflare/deploy-all.sh           # deploy everything
#   ./cloudflare/deploy-all.sh secrets   # set secrets only (prompts for each)
#   ./cloudflare/deploy-all.sh workers   # workers only (skip frontend build)
#   ./cloudflare/deploy-all.sh frontend  # frontend only
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ACCOUNT_ID="e0214028cb64d31232f5662548a55e4e"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

green()  { echo -e "\033[32m$*\033[0m"; }
yellow() { echo -e "\033[33m$*\033[0m"; }
red()    { echo -e "\033[31m$*\033[0m"; }
step()   { echo; green "── $* ──────────────────────────────────────────"; }

MODE="${1:-all}"

# ── Secrets setup ─────────────────────────────────────────────────────────────
set_secrets() {
  step "Setting secrets for tranc3-ai (adaptive AI rotation)"
  echo "Set all free-tier API keys. Press Enter to skip any you don't have yet."
  echo "You need at least ONE to enable non-stub AI responses."
  echo

  for key in GROQ_API_KEY GEMINI_API_KEY CEREBRAS_API_KEY SAMBANOVA_API_KEY \
             OPENROUTER_API_KEY HF_API_KEY DEEPSEEK_API_KEY TRANC3_AUTH_URL ALLOWED_ORIGINS; do
    read -rp "  $key (enter to skip): " val
    if [[ -n "$val" ]]; then
      echo "$val" | wrangler secret put "$key" --name tranc3-ai
      green "    ✓ $key set"
    else
      yellow "    ↷ $key skipped"
    fi
  done

  step "Setting secrets for infinity-void (encrypted secrets vault)"
  for key in MASTER_KEY_SEED INTERNAL_SECRET INFINITY_ONE_URL; do
    read -rp "  $key (enter to skip): " val
    if [[ -n "$val" ]]; then
      echo "$val" | wrangler secret put "$key" --name infinity-void
      green "    ✓ $key set"
    fi
  done

  step "Setting secrets for trancendos-api-gateway"
  for key in JWT_SECRET TRANC3_AI_SERVICE_URL USERS_SERVICE_URL PRODUCTS_SERVICE_URL ORDERS_SERVICE_URL PAYMENTS_SERVICE_URL; do
    read -rp "  $key (enter to skip): " val
    if [[ -n "$val" ]]; then
      echo "$val" | wrangler secret put "$key" --name trancendos-api-gateway
      green "    ✓ $key set"
    fi
  done
}

# ── Deploy workers ─────────────────────────────────────────────────────────────
deploy_workers() {
  step "Deploying tranc3-ai (adaptive AI gateway)"
  cd "$SCRIPT_DIR/tranc3-ai"
  npm ci --silent
  wrangler deploy
  green "✓ tranc3-ai deployed → https://tranc3-ai.luminous-aimastermind.workers.dev"

  step "Deploying infinity-void (encrypted secrets vault)"
  cd "$SCRIPT_DIR/infinity-void"
  npm ci --silent
  wrangler deploy
  green "✓ infinity-void deployed"

  step "Deploying trancendos-api-gateway"
  cd "$SCRIPT_DIR/trancendos-api-gateway"
  npm ci --silent
  wrangler deploy
  green "✓ trancendos-api-gateway deployed → https://trancendos-api-gateway.luminous-aimastermind.workers.dev"
}

# ── Deploy frontend ────────────────────────────────────────────────────────────
deploy_frontend() {
  step "Building frontend (React/Vite)"
  cd "$REPO_ROOT/web"
  npm ci --silent
  npm run build
  green "✓ Frontend built → web/dist/"

  step "Deploying to Cloudflare Pages"
  cd "$SCRIPT_DIR/pages"
  wrangler pages deploy
  green "✓ Frontend deployed → https://trancendos.com"
}

# ── Main ───────────────────────────────────────────────────────────────────────
echo
green "╔══════════════════════════════════════════════════════╗"
green "║   Trancendos — Cloudflare Zero-Cost Deploy           ║"
green "║   Account: $ACCOUNT_ID        ║"
green "╚══════════════════════════════════════════════════════╝"
echo

case "$MODE" in
  secrets)  set_secrets ;;
  workers)  deploy_workers ;;
  frontend) deploy_frontend ;;
  all)
    deploy_workers
    deploy_frontend
    ;;
  *)
    red "Unknown mode: $MODE"
    echo "Usage: $0 [all|workers|frontend|secrets]"
    exit 1
    ;;
esac

echo
green "════════════════════════════════════════════════════════"
green "  Deploy complete!"
green ""
green "  Frontend:    https://trancendos.com"
green "  AI Gateway:  https://tranc3-ai.luminous-aimastermind.workers.dev/health"
green "  API Gateway: https://trancendos-api-gateway.luminous-aimastermind.workers.dev/health"
green "  The Void:    https://infinity-void.luminous-aimastermind.workers.dev/health"
green ""
green "  To check AI provider status:"
green "  curl https://tranc3-ai.luminous-aimastermind.workers.dev/api/v1/ai/status"
green "════════════════════════════════════════════════════════"
