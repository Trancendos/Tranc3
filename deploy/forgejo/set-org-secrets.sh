#!/usr/bin/env bash
# deploy/forgejo/set-org-secrets.sh
#
# Bootstrap: push all production secrets into Forgejo org secrets store.
# Run this ONCE from a machine with access to trancendos.com/the-workshop.
#
# Prerequisites:
#   1. Forgejo running at trancendos.com/the-workshop
#   2. Source your local .env first:  set -a; source .env; set +a
#   3. A Forgejo admin token: FORGEJO_TOKEN env var
#   4. FLY_API_TOKEN from https://fly.io/user/personal_access_tokens
#   5. CF_API_TOKEN from https://dash.cloudflare.com/profile/api-tokens
#      (permissions: Workers:Edit, KV:Edit, D1:Edit, Account:Read)
#
# Usage:
#   set -a; source .env; set +a          # load .env into shell
#   export FORGEJO_TOKEN="your-forgejo-admin-token"
#   bash deploy/forgejo/set-org-secrets.sh

set -euo pipefail

# Parse CLI flags
INCLUDE_SERVICE_ROLE="false"
for arg in "$@"; do
  case "$arg" in
    --include-service-role) INCLUDE_SERVICE_ROLE="true" ;;
    -h|--help)
      echo "Usage: $0 [--include-service-role]"
      echo ""
      echo "Options:"
      echo "  --include-service-role  Also set SUPABASE_SERVICE_ROLE_KEY (bypasses RLS)"
      echo ""
      echo "Environment variables can also be used:"
      echo "  INCLUDE_SERVICE_ROLE=true  $0"
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 1
      ;;
  esac
done

# Allow env var to override / supplement CLI flag
if [[ "${INCLUDE_SERVICE_ROLE_ENV:-}" == "true" ]]; then
  INCLUDE_SERVICE_ROLE="true"
fi

FORGEJO_URL="${FORGEJO_URL:-https://trancendos.com/the-workshop}"
ORG="${FORGEJO_ORG:-Trancendos}"
API="$FORGEJO_URL/api/v1"

# ── Pre-flight checks ──────────────────────────────────────────────────────
# SECURITY: All secrets must be sourced from the environment (.env file).
# NEVER hardcode secret values in this script or commit .env to version control.
# The SUPABASE_SERVICE_ROLE_KEY is a highly privileged credential that bypasses
# Row Level Security. Only use it when CI/CD requires it; prefer ANON_KEY + RLS.
REQUIRED_VARS=(
  FORGEJO_TOKEN
  FLY_API_TOKEN
  CF_API_TOKEN
  SECRET_KEY
  JWT_SECRET
  CITADEL_WEBHOOK_SECRET
  DATABASE_URL
  SUPABASE_URL
  SUPABASE_ANON_KEY
  REDIS_URL
  UPSTASH_REDIS_REST_URL
  UPSTASH_REDIS_REST_TOKEN
)

# Optional high-privilege secret — only set when --include-service-role is passed
# SUPABASE_SERVICE_ROLE_KEY (bypasses RLS; use with extreme caution)

for VAR in "${REQUIRED_VARS[@]}"; do
  if [[ -z "${!VAR:-}" ]]; then
    echo "ERROR: $VAR is not set. Source your .env first:"
    echo "  set -a; source .env; set +a"
    exit 1
  fi
done

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

# ── Deployment tokens (from env) ──────────────────────────────────────────
echo "--- Deployment tokens ---"
set_secret "FLY_API_TOKEN"   "$FLY_API_TOKEN"
set_secret "CF_API_TOKEN"    "$CF_API_TOKEN"

# ── Signing keys (from .env) ──────────────────────────────────────────────
echo "--- Signing keys ---"
set_secret "SECRET_KEY"               "$SECRET_KEY"
set_secret "JWT_SECRET"               "$JWT_SECRET"
set_secret "CITADEL_WEBHOOK_SECRET"   "$CITADEL_WEBHOOK_SECRET"

# ── Supabase (from .env) ──────────────────────────────────────────────────
echo "--- Supabase ---"
set_secret "DATABASE_URL"              "$DATABASE_URL"
set_secret "SUPABASE_URL"              "$SUPABASE_URL"
set_secret "SUPABASE_ANON_KEY"         "$SUPABASE_ANON_KEY"
# SUPABASE_SERVICE_ROLE_KEY — only pushed when --include-service-role flag is set
if [[ "${INCLUDE_SERVICE_ROLE:-}" == "true" ]]; then
  set_secret "SUPABASE_SERVICE_ROLE_KEY" "$SUPABASE_SERVICE_ROLE_KEY"
else
  echo "  ⊘ Skipping SUPABASE_SERVICE_ROLE_KEY (pass --include-service-role or set INCLUDE_SERVICE_ROLE=true)"
fi

# ── Upstash Redis (from .env) ─────────────────────────────────────────────
echo "--- Upstash Redis ---"
set_secret "REDIS_URL"                 "$REDIS_URL"
set_secret "UPSTASH_REDIS_REST_URL"   "$UPSTASH_REDIS_REST_URL"
set_secret "UPSTASH_REDIS_REST_TOKEN" "$UPSTASH_REDIS_REST_TOKEN"

echo ""
echo "=== Done. Verify at: $FORGEJO_URL/org/$ORG/settings/secrets ==="
echo ""
echo "Next steps:"
echo "  1. Merge this branch to main → deploy-fly.yml auto-runs"
echo "  2. Configure Forgejo webhook in tranc3-backend repo settings:"
echo "     URL: https://trancendos-backend.fly.dev/citadel/webhooks/forgejo"
echo "     Secret: (value of CITADEL_WEBHOOK_SECRET from .env)"
