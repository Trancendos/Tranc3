#!/usr/bin/env bash
# deploy/forgejo/runner-setup.sh
# Register the act runner with Forgejo and set deployment secrets.
#
# Run AFTER Forgejo is up and you have the registration token:
#   1. Visit https://trancendos.com/the-workshop/-/admin/runners
#   2. Click "Create new runner" → copy the token
#   3. RUNNER_REGISTRATION_TOKEN=<token> ./deploy/forgejo/runner-setup.sh

set -euo pipefail

COMPOSE_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/docker-compose.yml"

log() { echo "[runner-setup] $*"; }
die() { echo "[runner-setup] ERROR: $*" >&2; exit 1; }

: "${RUNNER_REGISTRATION_TOKEN:?Set RUNNER_REGISTRATION_TOKEN first}"

# CF_API_TOKEN and FLY_API_TOKEN are only needed when FORGEJO_ADMIN_TOKEN is set
# (to push secrets via the Forgejo API).  They are NOT required for runner registration.
CF_API_TOKEN="${CF_API_TOKEN:-}"
FLY_API_TOKEN="${FLY_API_TOKEN:-}"

# ── Start/restart both runners ────────────────────────────────────────────────
# act-runner (default, no host Docker access) and act-runner-deploy (the
# privileged deploy-host runner — see act-runner-deploy.yml). Both need the
# same registration token; Forgejo gives each connecting runner its own
# identity from it.
log "Starting act runner…"
RUNNER_REGISTRATION_TOKEN="$RUNNER_REGISTRATION_TOKEN" \
  docker compose -f "$COMPOSE_FILE" up -d act-runner

log "Starting act-runner-deploy…"
RUNNER_REGISTRATION_TOKEN="$RUNNER_REGISTRATION_TOKEN" \
  docker compose -f "$COMPOSE_FILE" up -d act-runner-deploy

log "Waiting for runners to register…"
sleep 8

# ── Store deploy secrets in Forgejo ──────────────────────────────────────────
# Uses Forgejo API to create org-level secrets (available to all repos).
# Adjust FORGEJO_URL and ORG if needed.
FORGEJO_URL="${FORGEJO_URL:-https://trancendos.com/the-workshop}"
FORGEJO_ADMIN_TOKEN="${FORGEJO_ADMIN_TOKEN:-}"
ORG="${FORGEJO_ORG:-trancendos}"

if [ -n "$FORGEJO_ADMIN_TOKEN" ]; then
  [ -n "$CF_API_TOKEN" ]  || die "CF_API_TOKEN must be set when FORGEJO_ADMIN_TOKEN is provided"
  [ -n "$FLY_API_TOKEN" ] || die "FLY_API_TOKEN must be set when FORGEJO_ADMIN_TOKEN is provided"

  log "Storing CF_API_TOKEN secret in Forgejo org ${ORG}…"
  curl -sf -X PUT "${FORGEJO_URL}/api/v1/orgs/${ORG}/actions/secrets/CF_API_TOKEN" \
    -H "Authorization: token ${FORGEJO_ADMIN_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"data\": \"${CF_API_TOKEN}\"}" && log "  CF_API_TOKEN stored"

  log "Storing FLY_API_TOKEN secret in Forgejo org ${ORG}…"
  curl -sf -X PUT "${FORGEJO_URL}/api/v1/orgs/${ORG}/actions/secrets/FLY_API_TOKEN" \
    -H "Authorization: token ${FORGEJO_ADMIN_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"data\": \"${FLY_API_TOKEN}\"}" && log "  FLY_API_TOKEN stored"
else
  log ""
  log "FORGEJO_ADMIN_TOKEN not set — add secrets manually:"
  log "  The Workshop → org trancendos → Settings → Actions → Secrets"
  log "  Add: CF_API_TOKEN  (Cloudflare Workers deploy token)"
  log "  Add: FLY_API_TOKEN (Fly.io deploy token)"
fi

log ""
log "Runner setup complete!"
log "Check runner status at: ${FORGEJO_URL}/-/admin/runners"
log ""
log "Push to main to trigger auto-deploy, or use:"
log "  The Workshop → repo → Actions → Run workflow"
