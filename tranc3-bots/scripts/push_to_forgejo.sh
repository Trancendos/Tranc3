#!/usr/bin/env bash
# scripts/push_to_forgejo.sh — Push tranc3-bots to The Workshop (Forgejo).
#
# Prerequisites:
#   - Forgejo running at trancendos.com/the-workshop (see deploy/forgejo/)
#   - SSH key added to your Forgejo account
#   - Forgejo repo created: trancendos/tranc3-bots  (or create via web UI)
#
# Usage (run from the Tranc3 repo root):
#   FORGEJO_HOST=trancendos.com ./tranc3-bots/scripts/push_to_forgejo.sh
#
# Or from inside tranc3-bots/:
#   FORGEJO_HOST=trancendos.com ./scripts/push_to_forgejo.sh

set -euo pipefail

FORGEJO_HOST="${FORGEJO_HOST:-trancendos.com}"
FORGEJO_SSH_PORT="${FORGEJO_SSH_PORT:-2222}"
FORGEJO_USER="${FORGEJO_USER:-trancendos}"
REPO_NAME="${REPO_NAME:-tranc3-bots}"

BOTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE="ssh://git@${FORGEJO_HOST}:${FORGEJO_SSH_PORT}/${FORGEJO_USER}/${REPO_NAME}.git"

log() { echo "[forgejo-push] $*"; }
die() { echo "[forgejo-push] ERROR: $*" >&2; exit 1; }

command -v git >/dev/null 2>&1 || die "git not found"

log "Bot source directory: $BOTS_DIR"
log "Forgejo remote:       $REMOTE"
log ""
log "Make sure you have created the repo in Forgejo first:"
log "  https://${FORGEJO_HOST}/the-workshop/org/${FORGEJO_USER}/repo/create"
log ""

cd "$BOTS_DIR"

# ── Initialise git if needed ──────────────────────────────────────────────────
if [ -d .git ]; then
    log "Git repo already initialised"
else
    log "Initialising git repo…"
    git init -b main
fi

# ── Add or update remote ──────────────────────────────────────────────────────
if git remote get-url workshop > /dev/null 2>&1; then
    log "Remote 'workshop' already exists — updating URL"
    git remote set-url workshop "$REMOTE"
else
    log "Adding remote 'workshop'…"
    git remote add workshop "$REMOTE"
fi

# ── Stage and commit ──────────────────────────────────────────────────────────
git add -A
if git diff --cached --quiet; then
    log "Nothing new to commit — already up to date."
else
    log "Committing…"
    git commit -m "feat: tranc3-bots standalone worker service

Self-owned, zero-external-dependency worker bots for Tranc3 AI.
12 bot types: generate, embed, emotion, tokenize, consciousness,
personality, predict, code, memory, monitor, search, summarise.
FastAPI HTTP server, Redis queue, BotClient, Dockerfile, Fly.io config."
fi

# ── Push ──────────────────────────────────────────────────────────────────────
log "Pushing to The Workshop…"
git push -u workshop main

log ""
log "Done! Repository available at:"
log "  https://${FORGEJO_HOST}/the-workshop/${FORGEJO_USER}/${REPO_NAME}"
log ""
log "Clone with SSH:"
log "  git clone ssh://git@${FORGEJO_HOST}:${FORGEJO_SSH_PORT}/${FORGEJO_USER}/${REPO_NAME}.git"
log ""
log "Next steps:"
log "  1. Deploy to Fly.io:  cd $BOTS_DIR && fly deploy"
log "  2. Set engine URL:    fly secrets set TRANC3_ENGINE_URL=https://tranc3-backend.fly.dev"
log "  3. Update Tranc3:     fly secrets set TRANC3_BOTS_URL=https://tranc3-bots.fly.dev --app tranc3-backend"
