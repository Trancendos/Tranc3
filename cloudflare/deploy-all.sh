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
  step "Setting secrets for tranc3-ai (adaptive AI rotation — 12 free providers)"
  echo "Set all free-tier API keys. Press Enter to skip any you don't have yet."
  echo "You need at least ONE to enable non-stub AI responses."
  echo "All providers listed are genuinely free — no credit card required."
  echo
  echo "  Sign-up links (all free):"
  echo "    GROQ        → console.groq.com"
  echo "    GEMINI      → aistudio.google.com"
  echo "    CEREBRAS    → cerebras.ai"
  echo "    SAMBANOVA   → sambanova.ai"
  echo "    OPENROUTER  → openrouter.ai"
  echo "    HF          → huggingface.co"
  echo "    DEEPSEEK    → platform.deepseek.com"
  echo "    MISTRAL     → console.mistral.ai"
  echo "    COHERE      → dashboard.cohere.com"
  echo "    TOGETHER    → api.together.ai"
  echo "    FIREWORKS   → fireworks.ai"
  echo

  for key in GROQ_API_KEY GEMINI_API_KEY CEREBRAS_API_KEY SAMBANOVA_API_KEY \
             OPENROUTER_API_KEY HF_API_KEY DEEPSEEK_API_KEY \
             MISTRAL_API_KEY COHERE_API_KEY TOGETHER_API_KEY FIREWORKS_API_KEY \
             TRANC3_AUTH_URL ALLOWED_ORIGINS; do
    read -rp "  $key (enter to skip): " val
    if [[ -n "$val" ]]; then
      echo "$val" | wrangler secret put "$key" --name tranc3-ai
      green "    ✓ $key set"
    else
      yellow "    ↷ $key skipped"
    fi
  done

  step "Setting secrets for tranc3-notifications (adaptive email rotation)"
  echo "All 3 email providers are genuinely free forever:"
  echo "  Resend   → resend.com     (3K emails/month free)"
  echo "  Brevo    → brevo.com      (9K emails/month free)"
  echo "  Mailjet  → mailjet.com    (6K emails/month free)"
  echo

  for key in RESEND_API_KEY BREVO_API_KEY MAILJET_API_KEY MAILJET_SECRET_KEY FROM_EMAIL FROM_NAME; do
    read -rp "  $key (enter to skip): " val
    if [[ -n "$val" ]]; then
      echo "$val" | wrangler secret put "$key" --name tranc3-notifications
      green "    ✓ $key set"
    else
      yellow "    ↷ $key skipped"
    fi
  done

  step "Setting secrets for tranc3-storage (adaptive storage rotation)"
  echo "Storage provider rotation — all genuinely free forever:"
  echo "  Cloudflare R2 → 10 GB free (configured via R2 binding — no secret needed)"
  echo "  Backblaze B2  → backblaze.com    (10 GB free forever)"
  echo "  Oracle Cloud  → oracle.com/cloud (20 GB free forever — Always Free tier)"
  echo

  for key in BACKBLAZE_KEY_ID BACKBLAZE_APP_KEY BACKBLAZE_BUCKET_ID BACKBLAZE_BUCKET_NAME \
             ORACLE_NAMESPACE ORACLE_BUCKET_NAME ORACLE_REGION ORACLE_ACCESS_KEY ORACLE_SECRET_KEY; do
    read -rp "  $key (enter to skip): " val
    if [[ -n "$val" ]]; then
      echo "$val" | wrangler secret put "$key" --name tranc3-storage
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
  step "Deploying tranc3-ai (adaptive AI gateway — 12 free providers)"
  cd "$SCRIPT_DIR/tranc3-ai"
  npm ci --silent
  wrangler deploy
  green "✓ tranc3-ai deployed → https://tranc3-ai.luminous-aimastermind.workers.dev"

  step "Deploying tranc3-notifications (adaptive email rotation — Resend+Brevo+Mailjet)"
  cd "$SCRIPT_DIR/notifications-rotation"
  npm ci --silent
  wrangler deploy
  green "✓ tranc3-notifications deployed → https://tranc3-notifications.luminous-aimastermind.workers.dev"

  step "Deploying tranc3-storage (adaptive storage rotation — R2+B2+Oracle)"
  cd "$SCRIPT_DIR/storage-rotation"
  # Create R2 bucket if it doesn't exist
  wrangler r2 bucket create trancendos-storage 2>/dev/null || true
  npm ci --silent
  wrangler deploy
  green "✓ tranc3-storage deployed → https://tranc3-storage.luminous-aimastermind.workers.dev"

  step "Deploying tranc3-search (adaptive search rotation — Typesense+Meilisearch+Algolia+KV)"
  cd "$SCRIPT_DIR/search-rotation"
  npm ci --silent
  wrangler deploy
  green "✓ tranc3-search deployed → https://tranc3-search.luminous-aimastermind.workers.dev"

  step "Deploying tranc3-queue (adaptive task queue — CF Queues+Upstash+KV)"
  cd "$SCRIPT_DIR/queue-rotation"
  wrangler queues create tranc3-tasks 2>/dev/null || true
  npm ci --silent
  wrangler deploy
  green "✓ tranc3-queue deployed → https://tranc3-queue.luminous-aimastermind.workers.dev"

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
green "  AI Gateway:      https://tranc3-ai.luminous-aimastermind.workers.dev/health"
green "  Email Rotation:  https://tranc3-notifications.luminous-aimastermind.workers.dev/health"
green "  Storage Rotation:https://tranc3-storage.luminous-aimastermind.workers.dev/health"
green "  API Gateway:     https://trancendos-api-gateway.luminous-aimastermind.workers.dev/health"
green "  The Void:        https://infinity-void.luminous-aimastermind.workers.dev/health"
green ""
green "  To check adaptive rotation status:"
green "  curl https://tranc3-ai.luminous-aimastermind.workers.dev/api/v1/ai/status"
green "  curl https://tranc3-notifications.luminous-aimastermind.workers.dev/status"
green "  curl https://tranc3-storage.luminous-aimastermind.workers.dev/status"
green ""
green "  Search Rotation: https://tranc3-search.luminous-aimastermind.workers.dev/health"
green "  Task Queue:      https://tranc3-queue.luminous-aimastermind.workers.dev/health"
green ""
green "  Zero-cost capacity per day (all providers combined):"
green "    AI:      ~18,000 requests (12 providers)"
green "    Email:   600 emails/day — 18,000/month (3 providers)"
green "    Storage: 40 GB total (R2 10GB + B2 10GB + Oracle 20GB)"
green "    Search:  Unlimited (Typesense) + 20K/month fallback"
green "    Queue:   1M messages/month (CF Queues) + 10K/day (Upstash)"
green ""
green "  See FREE_TIER_REGISTRY.md for full honest breakdown of all free tiers."
green "════════════════════════════════════════════════════════"
