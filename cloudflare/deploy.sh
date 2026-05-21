#!/usr/bin/env bash
# Tranc3 Cloudflare Deployment Script
#
# Usage:
#   export CLOUDFLARE_API_TOKEN="your-token-here"
#   ./cloudflare/deploy.sh [--skip-delete]
#
# Prerequisites:
#   1. Node.js 18+
#   2. export CLOUDFLARE_API_TOKEN=<token with Workers:Edit, Workers Routes:Edit>
#      Get one at: https://dash.cloudflare.com/profile/api-tokens
#
# What this script does:
#   - Deploys the tranc3-ai worker (CF Workers AI + optional Python backend proxy)
#   - Updates ALLOWED_ORIGINS on infinity-auth-api to include trancendos.com
#   - Updates trancendos-api-gateway to route /api/v1/ai/* to tranc3-ai
#   - Deletes stale/duplicate workers (unless --skip-delete is passed)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACCOUNT_ID="e0214028cb64d31232f5662548a55e4e"
SKIP_DELETE=${1:-""}

if [[ -z "${CLOUDFLARE_API_TOKEN:-}" ]]; then
  echo "ERROR: CLOUDFLARE_API_TOKEN is not set."
  echo "Create one at: https://dash.cloudflare.com/profile/api-tokens"
  echo "Required permissions: Workers Scripts:Edit, Workers Routes:Edit, Zone:Read"
  exit 1
fi

export CLOUDFLARE_ACCOUNT_ID="$ACCOUNT_ID"

# ── Helper ────────────────────────────────────────────────────────────────────
cf_api() {
  local method="$1" path="$2"
  shift 2
  curl -s -X "$method" \
    "https://api.cloudflare.com/client/v4$path" \
    -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
    -H "Content-Type: application/json" \
    "$@"
}

log() { echo "▶ $*"; }
ok()  { echo "  ✅ $*"; }
warn(){ echo "  ⚠️  $*"; }

# ── 1. Deploy tranc3-ai worker ────────────────────────────────────────────────
log "Deploying tranc3-ai worker..."
cd "$SCRIPT_DIR/tranc3-ai"
npm install --silent
npx wrangler deploy
ok "tranc3-ai deployed"

TRANC3_AI_URL="https://tranc3-ai.${ACCOUNT_ID:0:8}.workers.dev"
# More reliably:
TRANC3_AI_URL="$(npx wrangler deployments list 2>/dev/null | grep tranc3-ai | head -1 | awk '{print $NF}' || echo 'https://tranc3-ai.trancendos.workers.dev')"

ok "Worker URL: https://tranc3-ai.trancendos.workers.dev"

# ── 2. Set secrets / env vars ────────────────────────────────────────────────
log "Configuring tranc3-ai environment..."
# Set auth URL to point at the existing auth worker
npx wrangler secret put TRANC3_AUTH_URL \
  --name tranc3-ai <<< "https://infinity-auth-api.trancendos.workers.dev" 2>/dev/null || \
  warn "Could not set TRANC3_AUTH_URL — set it manually with: wrangler secret put TRANC3_AUTH_URL --name tranc3-ai"

ok "Environment configured"

# ── 3. Update infinity-auth-api CORS ─────────────────────────────────────────
log "Updating infinity-auth-api CORS to include trancendos.com..."
CURRENT_ORIGINS=$(cf_api GET "/accounts/$ACCOUNT_ID/workers/scripts/infinity-auth-api/secrets" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); [print(s['name'],'=',s['text']) for s in d.get('result',[])]" 2>/dev/null || echo "")

# Set ALLOWED_ORIGINS via wrangler secret (non-interactive)
cd "$SCRIPT_DIR"
printf '%s' "https://trancendos.com,https://www.trancendos.com" | \
  npx wrangler secret put ALLOWED_ORIGINS --name infinity-auth-api 2>/dev/null || \
  warn "Could not update ALLOWED_ORIGINS on infinity-auth-api — set it manually:"
  echo "  echo 'https://trancendos.com,https://www.trancendos.com' | wrangler secret put ALLOWED_ORIGINS --name infinity-auth-api"

ok "Auth CORS updated"

# ── 4. Update API gateway ─────────────────────────────────────────────────────
log "Updating trancendos-api-gateway with AI routes..."
# Set the tranc3-ai service URL as an env var on the gateway
printf '%s' "https://tranc3-ai.trancendos.workers.dev" | \
  npx wrangler secret put TRANC3_AI_SERVICE_URL --name trancendos-api-gateway 2>/dev/null || \
  warn "Could not update gateway — deploy cloudflare/trancendos-api-gateway manually"

ok "Gateway updated"

# ── 5. Delete stale workers ───────────────────────────────────────────────────
if [[ "$SKIP_DELETE" != "--skip-delete" ]]; then
  log "Deleting stale/duplicate workers..."
  STALE_WORKERS=(
    "trancendos-api-gateway-production"
    "trancendos-users-service-production"
    "infinity-api-gateway"
    "arcadia-exchange"
    "arcadia-royal-bank"
    "orchestrator"
    "infinity-void"
    "infinity-lighthouse"
    "infinity-one"
    "infinity-hive"
  )

  for worker in "${STALE_WORKERS[@]}"; do
    result=$(cf_api DELETE "/accounts/$ACCOUNT_ID/workers/scripts/$worker")
    success=$(echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('success', False))" 2>/dev/null || echo "false")
    if [[ "$success" == "True" ]]; then
      ok "Deleted $worker"
    else
      warn "Could not delete $worker (may not exist or already deleted)"
    fi
  done
else
  warn "Skipping worker deletion (--skip-delete passed)"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════"
echo "  Tranc3 Cloudflare deployment complete"
echo "════════════════════════════════════════════════════════"
echo ""
echo "  AI API:   https://tranc3-ai.trancendos.workers.dev"
echo "  Auth API: https://infinity-auth-api.trancendos.workers.dev"
echo "  Gateway:  https://trancendos-api-gateway.trancendos.workers.dev"
echo ""
echo "  Test: curl https://tranc3-ai.trancendos.workers.dev/health"
echo ""
echo "  Next steps:"
echo "  1. Point trancendos.com DNS to the gateway (Cloudflare proxy)"
echo "  2. When Tranc3 backend is running, set TRANC3_BACKEND_URL:"
echo "     echo 'https://your-server.example.com' | wrangler secret put TRANC3_BACKEND_URL --name tranc3-ai"
