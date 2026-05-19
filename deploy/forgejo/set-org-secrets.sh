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
set_secret "SECRET_KEY"      "3d72bdc7d150cb9c4ab1a500127cc3286160fa33c3f10bd7e81bf86c3ce5bdb9"
set_secret "JWT_SECRET"      "9611c0c69d3ad5571b695733c393ee445169ed20d4cc02800ab173fd01c84797"
set_secret "CITADEL_WEBHOOK_SECRET" "0b497d1a2716a43d593b9f4b0d67529dfe06fcd3fdc55f4a14a59988825b6fe6"

# ── Supabase ───────────────────────────────────────────────────────────────
echo "--- Supabase ---"
set_secret "DATABASE_URL"              "postgresql://postgres:Tr@3mf0ZVnA1kTKlP8H916A3@db.ijizzeycvmqlobszojhf.supabase.co:5432/postgres"
set_secret "SUPABASE_URL"              "https://ijizzeycvmqlobszojhf.supabase.co"
set_secret "SUPABASE_ANON_KEY"         "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlqaXp6ZXljdm1xbG9ic3pvamhmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzkyMDM1NzMsImV4cCI6MjA5NDc3OTU3M30.y_4opOlzUMHWFnykDumI4XpGnhgU4UIr6gb0RYSO6lc"
set_secret "SUPABASE_SERVICE_ROLE_KEY" "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlqaXp6ZXljdm1xbG9ic3pvamhmIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3OTIwMzU3MywiZXhwIjoyMDk0Nzc5NTczfQ.JxYq4YAu8veDJd3qHT97JNkDWJx2V8YQrb9rcYYl7F0"

# ── Upstash Redis ──────────────────────────────────────────────────────────
echo "--- Upstash Redis ---"
set_secret "REDIS_URL"                 "rediss://:gQAAAAAAAf7OAAIgcDFlOGVjOTYyOTY3MGI0MDFmYmQyYzRmZTBmZDA3NjY2OQ@chief-buzzard-130766.upstash.io:6379"
set_secret "UPSTASH_REDIS_REST_URL"   "https://chief-buzzard-130766.upstash.io"
set_secret "UPSTASH_REDIS_REST_TOKEN" "gQAAAAAAAf7OAAIgcDFlOGVjOTYyOTY3MGI0MDFmYmQyYzRmZTBmZDA3NjY2OQ"

echo ""
echo "=== Done. Verify at: $FORGEJO_URL/org/$ORG/settings/secrets ==="
echo ""
echo "Next steps:"
echo "  1. Merge this branch to main → deploy-fly.yml auto-runs"
echo "  2. Configure Forgejo webhook in tranc3-backend repo settings:"
echo "     URL: https://tranc3-backend.fly.dev/citadel/webhooks/forgejo"
echo "     Secret: (value of CITADEL_WEBHOOK_SECRET above)"
