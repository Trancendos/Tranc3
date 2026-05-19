#!/usr/bin/env bash
# deploy/forgejo/set-org-secrets.sh
#
# Bootstrap: push all production secrets into Forgejo org secrets store.
# Run this ONCE from a machine with access to trancendos.com/the-workshop.
#
# Prerequisites:
#   1. Forgejo running at trancendos.com/the-workshop
#   2. A Forgejo admin token: FORGEJO_TOKEN env var
#   3. FLY_API_TOKEN from https://fly.io/user/personal_access_tokens
#   4. CF_API_TOKEN from https://dash.cloudflare.com/profile/api-tokens
#      (permissions: Workers:Edit, KV:Edit, D1:Edit, Account:Read)
#
# Usage:
#   export FORGEJO_TOKEN="your-forgejo-admin-token"
#   export FLY_API_TOKEN="your-fly-api-token"
#   export CF_API_TOKEN="your-cloudflare-api-token"
#   bash deploy/forgejo/set-org-secrets.sh

set -euo pipefail

FORGEJO_URL="${FORGEJO_URL:-https://trancendos.com/the-workshop}"
ORG="${FORGEJO_ORG:-Trancendos}"
API="$FORGEJO_URL/api/v1"

if [[ -z "${FORGEJO_TOKEN:-}" ]]; then
  echo "ERROR: FORGEJO_TOKEN is not set"
  exit 1
fi

if [[ -z "${FLY_API_TOKEN:-}" ]]; then
  echo "ERROR: FLY_API_TOKEN is not set. Get it from https://fly.io/user/personal_access_tokens"
  exit 1
fi

if [[ -z "${CF_API_TOKEN:-}" ]]; then
  echo "ERROR: CF_API_TOKEN is not set. Get it from https://dash.cloudflare.com/profile/api-tokens"
  exit 1
fi

set_secret() {
  local name="$1"
  local value="$2"
  echo "  → Setting $name..."
  curl -sf -X PUT "$API/orgs/$ORG/actions/secrets/$name" \
    -H "Authorization: token $FORGEJO_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"data\":$(echo -n "$value" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')}" \
    && echo "    ✓ $name" || echo "    ✗ $name (check permissions)"
}

echo "=== Trancendos — Forgejo org secrets bootstrap ==="
echo "    Org:  $ORG"
echo "    API:  $API"
echo ""

# ── Deployment tokens ──────────────────────────────────────────────────────
echo "--- Deployment tokens ---"
set_secret "FLY_API_TOKEN"   "$FLY_API_TOKEN"
set_secret "CF_API_TOKEN"    "$CF_API_TOKEN"

# ── Signing keys (from .env.production) ───────────────────────────────────
echo "--- Signing keys ---"
set_secret "SECRET_KEY"      "REDACTED_SECRET_KEY"
set_secret "JWT_SECRET"      "REDACTED_JWT_SECRET"
set_secret "CITADEL_WEBHOOK_SECRET" "REDACTED_CITADEL_WEBHOOK_SECRET"

# ── Supabase ───────────────────────────────────────────────────────────────
echo "--- Supabase ---"
set_secret "DATABASE_URL"              "postgresql://postgres:REDACTED_DB_PASSWORD@db.ijizzeycvmqlobszojhf.supabase.co:5432/postgres"
set_secret "SUPABASE_URL"              "https://ijizzeycvmqlobszojhf.supabase.co"
set_secret "SUPABASE_ANON_KEY"         "REDACTED_SUPABASE_ANON_KEY"
set_secret "SUPABASE_SERVICE_ROLE_KEY" "REDACTED_SUPABASE_SERVICE_ROLE_KEY"

# ── Upstash Redis ──────────────────────────────────────────────────────────
echo "--- Upstash Redis ---"
set_secret "REDIS_URL"                 "rediss://:REDACTED_UPSTASH_REDIS_TOKEN@chief-buzzard-130766.upstash.io:6379"
set_secret "UPSTASH_REDIS_REST_URL"   "https://chief-buzzard-130766.upstash.io"
set_secret "UPSTASH_REDIS_REST_TOKEN" "REDACTED_UPSTASH_REDIS_TOKEN"

echo ""
echo "=== Done. Verify at: $FORGEJO_URL/org/$ORG/settings/secrets ==="
echo ""
echo "Next steps:"
echo "  1. Merge this branch to main → deploy-fly.yml auto-runs"
echo "  2. Configure Forgejo webhook in tranc3-backend repo settings:"
echo "     URL: https://tranc3-backend.fly.dev/citadel/webhooks/forgejo"
echo "     Secret: (value of CITADEL_WEBHOOK_SECRET above)"
