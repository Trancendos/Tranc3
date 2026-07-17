#!/usr/bin/env bash
# deploy/forgejo/runner-setup.sh
# Register the act runner with Forgejo and set deployment secrets.
#
# Run AFTER Forgejo is up and you have the registration token:
#   1. Visit https://trancendos.com/the-workshop/-/admin/runners
#   2. Click "Create new runner" → copy the token
#   3. RUNNER_REGISTRATION_TOKEN=<token> ./deploy/forgejo/runner-setup.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.yml"

log() { echo "[runner-setup] $*"; }
warn() { echo "[runner-setup] WARN: $*" >&2; }
die() { echo "[runner-setup] ERROR: $*" >&2; exit 1; }

: "${RUNNER_REGISTRATION_TOKEN:?Set RUNNER_REGISTRATION_TOKEN first}"

# CF_API_TOKEN and FLY_API_TOKEN are only needed when FORGEJO_ADMIN_TOKEN is set
# (to push secrets via the Forgejo API).  They are NOT required for runner registration.
CF_API_TOKEN="${CF_API_TOKEN:-}"
FLY_API_TOKEN="${FLY_API_TOKEN:-}"

# ── Build the custom runner image if missing ──────────────────────────────────
# docker-compose.yml defaults RUNNER_IMAGE to trancendos/act-runner:latest for
# both runners (neither the bare upstream image nor a missing image work —
# every label depends on this image's toolchain, see act-runner.yml). Unlike
# bootstrap.sh, this script is the "re-run later" / manual re-registration
# path, so it can't assume the image already exists from a prior bootstrap.
if ! docker image inspect trancendos/act-runner:latest >/dev/null 2>&1; then
  log "trancendos/act-runner:latest not found locally — building it…"
  docker build -f "${SCRIPT_DIR}/runner.Dockerfile" -t trancendos/act-runner:latest "${REPO_ROOT}" \
    || die "Runner image build failed. Fix deploy/forgejo/runner.Dockerfile and re-run."
fi

check_runner_up() {
  local service="$1" container="$2"
  if [[ "$(docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null)" == "true" ]]; then
    log "  ${service} is running"
  else
    warn "${service} did not stay running — check: docker compose -f $COMPOSE_FILE logs ${service}"
    docker compose -f "$COMPOSE_FILE" logs --tail 20 "$service" 2>&1 || true
  fi
}

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

check_runner_up act-runner the-workshop-runner
check_runner_up act-runner-deploy the-workshop-runner-deploy

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
