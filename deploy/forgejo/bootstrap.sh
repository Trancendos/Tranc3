#!/usr/bin/env bash
# deploy/forgejo/bootstrap.sh
# Full automated bootstrap for The Workshop (Forgejo + act-runner).
#
# Run ONCE on the trancendos.com server.  Idempotent — safe to re-run.
#
# Prerequisites (all required):
#   - Docker + docker compose installed
#   - Repo checked out at /opt/tranc3 (or wherever — script uses its own dir)
#   - .env present (source it first, or set vars manually — see below)
#   - CF_API_TOKEN    Cloudflare API token (Workers:Edit, KV:Edit, D1:Edit)
#   - FLY_API_TOKEN  Fly.io PERSONAL deploy token (fm1_... not fm2_!)
#   - SECRET_KEY, JWT_SECRET, DATABASE_URL, REDIS_URL etc. from .env
#
# Usage:
#   set -a; source .env; set +a            # load .env into shell
#   bash deploy/forgejo/bootstrap.sh
#
# What it does:
#   1.  Build custom runner image (flyctl + wrangler + Python tools)
#   2.  Start Forgejo via docker compose
#   3.  Wait until Forgejo is healthy
#   4.  Create admin user (non-interactively via Forgejo CLI)
#   5.  Lock the installer (INSTALL_LOCK=true)
#   6.  Create org: Trancendos
#   7.  Mirror Tranc3 repo into Forgejo (optional — if GITHUB_MIRROR_TOKEN set)
#   8.  Get runner registration token via Forgejo API
#   9.  Start act-runner
#   10. Push all org secrets via Forgejo API
#   11. Print next-steps summary

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.yml"

FORGEJO_URL="${FORGEJO_URL:-https://trancendos.com/the-workshop}"
FORGEJO_INTERNAL="http://127.0.0.1:3456"
ORG="${FORGEJO_ORG:-Trancendos}"

# Colours
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${CYAN}[workshop]${NC} $*"; }
ok()   { echo -e "${GREEN}[workshop] ✓${NC} $*"; }
warn() { echo -e "${YELLOW}[workshop] ⚠${NC} $*"; }
die()  { echo -e "${RED}[workshop] ✗ ERROR:${NC} $*" >&2; exit 1; }

# ── Pre-flight: required env vars ────────────────────────────────────────────
check_var() {
  local v="$1"
  [[ -n "${!v:-}" ]] || die "$v is not set. Run: set -a; source .env; set +a"
}

log "Checking required environment variables…"
check_var CF_API_TOKEN
check_var FLY_API_TOKEN
check_var SECRET_KEY
check_var JWT_SECRET
check_var DATABASE_URL
check_var REDIS_URL

# Optional but logged
FORGEJO_ADMIN_USER="${FORGEJO_ADMIN_USER:-trancendos-admin}"
FORGEJO_ADMIN_PASS="${FORGEJO_ADMIN_PASS:-}"
FORGEJO_ADMIN_EMAIL="${FORGEJO_ADMIN_EMAIL:-admin@trancendos.com}"

if [[ -z "$FORGEJO_ADMIN_PASS" ]]; then
  FORGEJO_ADMIN_PASS="$(python3 -c 'import secrets; print(secrets.token_urlsafe(20))')"
  warn "FORGEJO_ADMIN_PASS not set — generated: ${FORGEJO_ADMIN_PASS}"
  warn "Save this password! It will not be shown again."
fi

ok "Pre-flight checks passed"

# ── Step 1: Build custom runner image ────────────────────────────────────────
log "Building custom runner image (trancendos/act-runner:latest)…"
if docker build \
    -f "${SCRIPT_DIR}/runner.Dockerfile" \
    -t trancendos/act-runner:latest \
    "${REPO_ROOT}" 2>&1 | tail -5; then
  ok "Runner image built"
  export RUNNER_IMAGE="trancendos/act-runner:latest"
else
  warn "Custom runner build failed — falling back to upstream image"
  export RUNNER_IMAGE="code.forgejo.org/forgejo/runner:3"
fi

# ── Step 2: Start Forgejo ─────────────────────────────────────────────────────
log "Starting Forgejo…"
docker compose -f "$COMPOSE_FILE" up -d forgejo

# ── Step 3: Wait for health ───────────────────────────────────────────────────
log "Waiting for Forgejo to be healthy (up to 120s)…"
ATTEMPTS=0
until curl -sf "${FORGEJO_INTERNAL}/-/health" > /dev/null 2>&1; do
  ATTEMPTS=$((ATTEMPTS + 1))
  [[ $ATTEMPTS -gt 40 ]] && die "Forgejo did not start within 120s. Check: docker logs the-workshop"
  printf "."
  sleep 3
done
echo ""
ok "Forgejo is healthy at ${FORGEJO_INTERNAL}"

# ── Step 4: Create admin user ─────────────────────────────────────────────────
log "Creating admin user '${FORGEJO_ADMIN_USER}'…"
if docker exec the-workshop \
    forgejo admin user create \
    --username "${FORGEJO_ADMIN_USER}" \
    --password "${FORGEJO_ADMIN_PASS}" \
    --email "${FORGEJO_ADMIN_EMAIL}" \
    --admin \
    --must-change-password=false 2>&1; then
  ok "Admin user created"
else
  warn "Admin user may already exist — continuing"
fi

# ── Step 5: Get admin API token ───────────────────────────────────────────────
log "Creating API token for admin user…"
FORGEJO_TOKEN=$(docker exec the-workshop \
  forgejo admin user generate-access-token \
  --username "${FORGEJO_ADMIN_USER}" \
  --token-name "bootstrap-$(date +%s)" \
  --raw 2>/dev/null) || true

if [[ -z "$FORGEJO_TOKEN" ]]; then
  warn "Could not auto-generate token — trying API with password…"
  FORGEJO_TOKEN=$(curl -sf -X POST \
    "${FORGEJO_INTERNAL}/the-workshop/api/v1/users/${FORGEJO_ADMIN_USER}/tokens" \
    -u "${FORGEJO_ADMIN_USER}:${FORGEJO_ADMIN_PASS}" \
    -H "Content-Type: application/json" \
    -d "{\"name\":\"bootstrap-$(date +%s)\"}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["sha1"])' 2>/dev/null) || true
fi

[[ -n "$FORGEJO_TOKEN" ]] || die "Could not obtain Forgejo admin API token. Check credentials."
ok "API token obtained"

API="${FORGEJO_INTERNAL}/the-workshop/api/v1"
AUTH_HEADER="Authorization: token ${FORGEJO_TOKEN}"

# ── Step 6: Lock installer ────────────────────────────────────────────────────
log "Locking installer (INSTALL_LOCK=true)…"
docker exec the-workshop \
  forgejo admin app-ini-patch \
  "security.INSTALL_LOCK=true" 2>/dev/null || true

# ── Step 7: Create org ────────────────────────────────────────────────────────
log "Creating org '${ORG}'…"
ORG_STATUS=$(curl -sf -o /dev/null -w "%{http_code}" \
  -X GET "$API/orgs/${ORG}" \
  -H "$AUTH_HEADER" 2>/dev/null || echo "000")

if [[ "$ORG_STATUS" == "200" ]]; then
  warn "Org '${ORG}' already exists — skipping creation"
else
  curl -sf -X POST "$API/orgs" \
    -H "$AUTH_HEADER" \
    -H "Content-Type: application/json" \
    -d "{
      \"username\": \"${ORG}\",
      \"full_name\": \"Trancendos Platform\",
      \"description\": \"The Workshop — Trancendos CI/CD\",
      \"visibility\": \"private\"
    }" > /dev/null && ok "Org '${ORG}' created"
fi

# ── Step 8: Get runner registration token ────────────────────────────────────
log "Getting runner registration token…"
RUNNER_REGISTRATION_TOKEN=$(curl -sf \
  -X POST "$API/orgs/${ORG}/actions/runners/registration-token" \
  -H "$AUTH_HEADER" | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])' 2>/dev/null) || true

if [[ -z "$RUNNER_REGISTRATION_TOKEN" ]]; then
  # Fallback: get from site admin
  RUNNER_REGISTRATION_TOKEN=$(curl -sf \
    -X GET "$API/admin/runners/registration-token" \
    -H "$AUTH_HEADER" | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])' 2>/dev/null) || true
fi

[[ -n "$RUNNER_REGISTRATION_TOKEN" ]] || die "Could not get runner registration token"
ok "Runner registration token obtained"

# ── Step 9: Start act-runner ──────────────────────────────────────────────────
# act-runner joins tranc3-net as an `external: true` network (see
# docker-compose.yml) so CI jobs can reach the docker-compose.production.yml
# fleet by service name. That network is normally created by bringing up the
# production stack first; create it here too so a Workshop-only bootstrap
# (production stack not yet deployed) doesn't fail with "network not found".
log "Ensuring tranc3-net exists…"
docker network inspect tranc3-net >/dev/null 2>&1 \
  || docker network create --driver bridge --subnet 172.28.0.0/16 tranc3-net
ok "tranc3-net ready"

log "Starting act-runner…"
export RUNNER_REGISTRATION_TOKEN
docker compose -f "$COMPOSE_FILE" up -d act-runner
sleep 10
ok "act-runner started"

# ── Step 10: Push all org secrets ─────────────────────────────────────────────
log "Pushing org secrets to Forgejo…"

push_secret() {
  local name="$1"
  local value="$2"
  local encoded
  encoded=$(python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))' <<< "$value")
  local status
  status=$(curl -sf -o /dev/null -w "%{http_code}" \
    -X PUT "$API/orgs/${ORG}/actions/secrets/${name}" \
    -H "$AUTH_HEADER" \
    -H "Content-Type: application/json" \
    -d "{\"data\":${encoded}}" 2>/dev/null || echo "000")
  if [[ "$status" =~ ^2 ]]; then
    ok "  ${name}"
  else
    warn "  ${name} (HTTP ${status})"
  fi
}

echo "  --- Deployment tokens ---"
push_secret "FLY_API_TOKEN"             "${FLY_API_TOKEN}"
push_secret "CF_API_TOKEN"              "${CF_API_TOKEN}"

echo "  --- Signing keys ---"
push_secret "SECRET_KEY"                "${SECRET_KEY}"
push_secret "JWT_SECRET"                "${JWT_SECRET}"
push_secret "CITADEL_WEBHOOK_SECRET"    "${CITADEL_WEBHOOK_SECRET:-$(python3 -c 'import secrets; print(secrets.token_hex(32))')}"

echo "  --- Supabase ---"
[[ -n "${DATABASE_URL:-}"              ]] && push_secret "DATABASE_URL"              "${DATABASE_URL}"
[[ -n "${SUPABASE_URL:-}"              ]] && push_secret "SUPABASE_URL"              "${SUPABASE_URL}"
[[ -n "${SUPABASE_ANON_KEY:-}"         ]] && push_secret "SUPABASE_ANON_KEY"         "${SUPABASE_ANON_KEY}"
[[ -n "${SUPABASE_SERVICE_ROLE_KEY:-}" ]] && push_secret "SUPABASE_SERVICE_ROLE_KEY" "${SUPABASE_SERVICE_ROLE_KEY}"

echo "  --- Upstash Redis ---"
push_secret "REDIS_URL"                 "${REDIS_URL}"
[[ -n "${UPSTASH_REDIS_REST_URL:-}"    ]] && push_secret "UPSTASH_REDIS_REST_URL"   "${UPSTASH_REDIS_REST_URL}"
[[ -n "${UPSTASH_REDIS_REST_TOKEN:-}"  ]] && push_secret "UPSTASH_REDIS_REST_TOKEN" "${UPSTASH_REDIS_REST_TOKEN}"

# ── Step 11: Configure repo webhook ──────────────────────────────────────────
log "Checking if Tranc3 repo exists in Forgejo…"
REPO_STATUS=$(curl -sf -o /dev/null -w "%{http_code}" \
  "$API/repos/${ORG}/Tranc3" \
  -H "$AUTH_HEADER" 2>/dev/null || echo "000")

if [[ "$REPO_STATUS" == "404" ]]; then
  log "Repo not found — you can mirror it from GitHub or push manually:"
  log "  git remote add workshop ssh://git@trancendos.com:2222/${ORG}/Tranc3.git"
  log "  git push workshop ${BRANCH:-main}"
else
  ok "Repo '${ORG}/Tranc3' exists"

  # Register Citadel webhook on the repo
  WEBHOOK_SECRET="${CITADEL_WEBHOOK_SECRET:-webhook-secret-placeholder}"
  WEBHOOK_STATUS=$(curl -sf -o /dev/null -w "%{http_code}" \
    -X POST "$API/repos/${ORG}/Tranc3/hooks" \
    -H "$AUTH_HEADER" \
    -H "Content-Type: application/json" \
    -d "{
      \"type\": \"forgejo\",
      \"active\": true,
      \"events\": [\"push\",\"pull_request\",\"workflow_run\"],
      \"config\": {
        \"url\": \"https://trancendos-backend.fly.dev/citadel/webhooks/forgejo\",
        \"content_type\": \"json\",
        \"secret\": \"${WEBHOOK_SECRET}\"
      }
    }" 2>/dev/null || echo "000")
  [[ "$WEBHOOK_STATUS" =~ ^2 ]] && ok "Citadel webhook registered" || warn "Webhook setup (HTTP ${WEBHOOK_STATUS}) — add manually if needed"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  The Workshop bootstrap complete!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  URL:          ${FORGEJO_URL}"
echo -e "  Admin user:   ${FORGEJO_ADMIN_USER}"
echo -e "  Admin pass:   ${FORGEJO_ADMIN_PASS}  ← SAVE THIS"
echo -e "  API token:    ${FORGEJO_TOKEN:0:12}…  (partial — stored in runner env)"
echo ""
echo -e "  SSH clone:    ssh://git@trancendos.com:2222/${ORG}/Tranc3.git"
echo ""
echo "  Next steps:"
echo "  1. Add SSH public key at ${FORGEJO_URL}/user/settings/keys"
echo "  2. Push Tranc3 repo:  git push ssh://git@trancendos.com:2222/${ORG}/Tranc3.git main"
echo "  3. Verify runner:     ${FORGEJO_URL}/-/admin/runners"
echo "  4. Verify secrets:    ${FORGEJO_URL}/org/${ORG}/settings/secrets"
echo "  5. Get a Fly.io personal token from https://fly.io/user/personal_access_tokens"
echo "     then update FLY_API_TOKEN in Forgejo org secrets"
echo ""
echo -e "${CYAN}  To rebuild runner image after changes:${NC}"
echo "    docker build -f deploy/forgejo/runner.Dockerfile -t trancendos/act-runner:latest ."
echo "    RUNNER_IMAGE=trancendos/act-runner:latest docker compose -f deploy/forgejo/docker-compose.yml up -d act-runner"
echo ""
