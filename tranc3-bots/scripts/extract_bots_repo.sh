#!/usr/bin/env bash
# scripts/extract_bots_repo.sh — Push tranc3-bots/ as its own GitHub repository.
#
# Prerequisites:
#   - GitHub CLI (gh) installed and authenticated: gh auth login
#   - git configured with your username/email
#
# Usage (run from the root of the Tranc3 repo):
#   ./tranc3-bots/scripts/extract_bots_repo.sh
#
# What it does:
#   1. Creates a new GitHub repo: trancendos/tranc3-bots (public, with description)
#   2. Initialises a fresh git repo inside tranc3-bots/
#   3. Commits all files and pushes to the new repo
#   4. Reports the new repo URL

set -euo pipefail

REPO_OWNER="trancendos"
REPO_NAME="tranc3-bots"
BOTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

log() { echo "[extract] $*"; }
die() { echo "[extract] ERROR: $*" >&2; exit 1; }

command -v gh  >/dev/null 2>&1 || die "GitHub CLI (gh) not found. Install: https://cli.github.com"
command -v git >/dev/null 2>&1 || die "git not found"

log "Bot source directory: $BOTS_DIR"
log "Target repo: github.com/$REPO_OWNER/$REPO_NAME"

# ── Create the GitHub repo ────────────────────────────────────────────────────
log "Creating GitHub repository $REPO_OWNER/$REPO_NAME…"
gh repo create "$REPO_OWNER/$REPO_NAME" \
  --public \
  --description "Self-owned worker bots for the Tranc3 AI system" \
  --confirm 2>/dev/null || log "Repo may already exist — continuing"

REMOTE="https://github.com/$REPO_OWNER/$REPO_NAME.git"

# ── Initialise local git repo ─────────────────────────────────────────────────
cd "$BOTS_DIR"

if [ -d .git ]; then
  log "Git repo already initialised in $BOTS_DIR"
else
  log "Initialising git repo…"
  git init -b main
  git remote add origin "$REMOTE"
fi

# ── Stage and commit ──────────────────────────────────────────────────────────
log "Staging files…"
git add -A

if git diff --cached --quiet; then
  log "Nothing to commit — already up to date."
else
  log "Committing…"
  git commit -m "feat: initial tranc3-bots standalone service

Self-owned, zero-external-dependency worker bots for the Tranc3 AI.
Includes: BotPool (Redis + in-memory fallback), BotRegistry, handlers
for 12 bot types (generate, embed, emotion, tokenize, consciousness,
personality, predict, code, memory, monitor, search, summarise),
FastAPI HTTP server, Python client, Dockerfile, Fly.io config."
fi

# ── Push ──────────────────────────────────────────────────────────────────────
log "Pushing to $REMOTE…"
git push -u origin main --force

log ""
log "Done! Repository available at: https://github.com/$REPO_OWNER/$REPO_NAME"
log ""
log "Next steps:"
log "  1. Deploy to Fly.io:  cd $BOTS_DIR && fly deploy"
log "  2. Set engine URL:    fly secrets set TRANC3_ENGINE_URL=https://tranc3-backend.fly.dev"
log "  3. Update Tranc3:     fly secrets set TRANC3_BOTS_URL=https://tranc3-bots.fly.dev --app tranc3-backend"
