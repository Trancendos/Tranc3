#!/usr/bin/env bash
# scripts/rollback.sh — Instant rollback to a previous docker-compose snapshot.
#
# Usage:
#   ./scripts/rollback.sh                  # rollback to previous git tag
#   ./scripts/rollback.sh v1.2.3           # rollback to specific tag
#   ./scripts/rollback.sh --dry-run        # show what would happen without acting
#   TIER=P0 ./scripts/rollback.sh          # verify only P0 after rollback

set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.production.yml}"
DRY_RUN=0
TARGET_TAG=""
VERIFY_TIER="${TIER:-P0}"
ROLLBACK_LOG="logs/rollback.log"

# ── Argument parsing ──────────────────────────────────────────────────────────
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --help|-h)
            echo "Usage: $0 [tag] [--dry-run]"
            echo "  tag        Git tag or commit to rollback to (default: previous tag)"
            echo "  --dry-run  Show steps without executing"
            exit 0
            ;;
        *) TARGET_TAG="$arg" ;;
    esac
done

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

log()  { echo -e "${CYAN}[rollback]${RESET} $*" | tee -a "$ROLLBACK_LOG"; }
ok()   { echo -e "${GREEN}[✓]${RESET} $*"       | tee -a "$ROLLBACK_LOG"; }
warn() { echo -e "${YELLOW}[!]${RESET} $*"      | tee -a "$ROLLBACK_LOG"; }
fail() { echo -e "${RED}[✗]${RESET} $*"         | tee -a "$ROLLBACK_LOG"; exit 1; }
dry()  { echo -e "${YELLOW}[dry-run]${RESET} would run: $*"; }

mkdir -p logs

echo -e "${BOLD}═══════════════════════════════════════════════════════${RESET}"
echo -e "${BOLD}           Tranc3 Rollback — $(date '+%Y-%m-%d %H:%M:%S')${RESET}"
echo -e "${BOLD}═══════════════════════════════════════════════════════${RESET}"
log "Compose file : $COMPOSE_FILE"
log "Dry-run      : $DRY_RUN"

# ── Resolve target tag ────────────────────────────────────────────────────────
if [[ -z "$TARGET_TAG" ]]; then
    CURRENT_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "")
    if [[ -z "$CURRENT_TAG" ]]; then
        fail "No git tags found and no target tag specified. Cannot determine rollback target."
    fi
    # Find the tag before current
    TARGET_TAG=$(git tag --sort=-version:refname | grep -v "^${CURRENT_TAG}$" | head -1 || true)
    if [[ -z "$TARGET_TAG" ]]; then
        fail "Only one tag exists ($CURRENT_TAG). Cannot rollback further."
    fi
    log "Current tag  : $CURRENT_TAG"
fi

log "Rollback to  : $TARGET_TAG"

# ── Confirm ───────────────────────────────────────────────────────────────────
if [[ "$DRY_RUN" -eq 0 ]]; then
    warn "This will stop all running containers and restore code to $TARGET_TAG."
    read -r -p "$(echo -e "${YELLOW}Proceed? [y/N]:${RESET} ")" confirm
    [[ "${confirm,,}" == "y" ]] || { warn "Aborted."; exit 0; }
fi

# ── Step 1: Save snapshot of current state ────────────────────────────────────
log "Saving current compose snapshot..."
SNAP_FILE="logs/rollback_snapshot_$(date +%s).yml"
if [[ "$DRY_RUN" -eq 0 ]]; then
    cp "$COMPOSE_FILE" "$SNAP_FILE" 2>/dev/null || warn "Could not save snapshot (compose file may not exist)"
    ok "Snapshot saved to $SNAP_FILE"
else
    dry "cp $COMPOSE_FILE $SNAP_FILE"
fi

# ── Step 2: Stop running stack ────────────────────────────────────────────────
log "Stopping current stack..."
if [[ "$DRY_RUN" -eq 0 ]]; then
    if [[ -f "$COMPOSE_FILE" ]]; then
        docker compose -f "$COMPOSE_FILE" down --remove-orphans --timeout 30 \
            2>&1 | tee -a "$ROLLBACK_LOG" || warn "Some containers may not have stopped cleanly"
        ok "Stack stopped"
    else
        warn "Compose file not found — skipping docker compose down"
    fi
else
    dry "docker compose -f $COMPOSE_FILE down --remove-orphans --timeout 30"
fi

# ── Step 3: Checkout target tag ───────────────────────────────────────────────
log "Checking out $TARGET_TAG..."
if [[ "$DRY_RUN" -eq 0 ]]; then
    git stash push -m "rollback-stash-$(date +%s)" 2>/dev/null || true
    git checkout "$TARGET_TAG" -- docker-compose.production.yml 2>&1 | tee -a "$ROLLBACK_LOG" \
        || fail "git checkout $TARGET_TAG failed"
    ok "Checked out compose file at $TARGET_TAG"
else
    dry "git checkout $TARGET_TAG -- docker-compose.production.yml"
fi

# ── Step 4: Pull updated images ───────────────────────────────────────────────
log "Pulling images for $TARGET_TAG..."
if [[ "$DRY_RUN" -eq 0 ]]; then
    docker compose -f "$COMPOSE_FILE" pull --quiet 2>&1 | tee -a "$ROLLBACK_LOG" \
        || warn "Some images could not be pulled — will use cached versions"
    ok "Images pulled"
else
    dry "docker compose -f $COMPOSE_FILE pull --quiet"
fi

# ── Step 5: Start rolled-back stack ──────────────────────────────────────────
log "Starting rolled-back stack..."
if [[ "$DRY_RUN" -eq 0 ]]; then
    docker compose -f "$COMPOSE_FILE" up -d --remove-orphans \
        2>&1 | tee -a "$ROLLBACK_LOG" || fail "Failed to start rolled-back stack"
    ok "Stack started"
else
    dry "docker compose -f $COMPOSE_FILE up -d --remove-orphans"
fi

# ── Step 6: Wait for P0 services ─────────────────────────────────────────────
log "Waiting 15s for P0 services to initialise..."
if [[ "$DRY_RUN" -eq 0 ]]; then
    sleep 15
fi

# ── Step 7: Post-rollback verification ────────────────────────────────────────
# This script runs `docker compose` directly on the host, not inside a
# container on tranc3-net — post_deploy_verify.py's default per-service
# Docker-DNS probing wouldn't resolve from here, so pass the host's
# published ports explicitly (docker-compose.production.yml publishes every
# worker port to the host — see the "Port source of truth" note in
# CLAUDE.md).
log "Running post-rollback verification (tier=$VERIFY_TIER)..."
VERIFY_CMD="python3 scripts/post_deploy_verify.py --base http://127.0.0.1 --tier $VERIFY_TIER --retries 3"

if [[ "$DRY_RUN" -eq 0 ]]; then
    if $VERIFY_CMD 2>&1 | tee -a "$ROLLBACK_LOG"; then
        ok "Post-rollback verification passed"
    else
        warn "Verification reported failures — check logs/deploy_verify.json"
        warn "Manual inspection may be required"
    fi
else
    dry "$VERIFY_CMD"
fi

echo ""
echo -e "${BOLD}═══════════════════════════════════════════════════════${RESET}"
if [[ "$DRY_RUN" -eq 1 ]]; then
    echo -e "${YELLOW}Dry-run complete — no changes made${RESET}"
else
    echo -e "${GREEN}Rollback to $TARGET_TAG complete${RESET}"
    echo -e "Log: $ROLLBACK_LOG"
fi
echo -e "${BOLD}═══════════════════════════════════════════════════════${RESET}"
