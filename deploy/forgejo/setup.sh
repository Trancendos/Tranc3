#!/usr/bin/env bash
# deploy/forgejo/setup.sh — Quick start for The Workshop (Forgejo).
#
# For FULL automated bootstrap (admin user, org, runner, secrets), use instead:
#   bash deploy/forgejo/bootstrap.sh
#
# This script only starts the Docker containers and waits for health.
# Run from the repo root on your trancendos.com server:
#   ./deploy/forgejo/setup.sh

set -euo pipefail

COMPOSE_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/docker-compose.yml"

log() { echo "[workshop] $*"; }

log "Starting The Workshop (Forgejo)…"
docker compose -f "$COMPOSE_FILE" up -d forgejo

log "Waiting for Forgejo to be ready…"
# Health check uses the internal mapped port (3456) and correct path
until curl -sf http://127.0.0.1:3456/-/health > /dev/null 2>&1; do
    printf "."
    sleep 3
done
echo ""

log ""
log "The Workshop is running!"
log ""
log "Complete setup at:  https://trancendos.com/the-workshop"
log "  (or locally at:  http://127.0.0.1:3456/the-workshop)"
log ""
log "Nginx/Caddy config:"
log "  nginx  → deploy/forgejo/nginx-the-workshop.conf"
log "  caddy  → deploy/forgejo/caddy-the-workshop.conf"
log ""
log "SSH clone URL (once set up):"
log "  git clone ssh://git@trancendos.com:2222/USERNAME/REPO.git"
log ""
log "Next: push tranc3-bots →"
log "  cd tranc3-bots"
log "  git remote add workshop ssh://git@trancendos.com:2222/trancendos/tranc3-bots.git"
log "  git push workshop main"
