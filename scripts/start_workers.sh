#!/usr/bin/env bash
# scripts/start_workers.sh — Start Tranc3 self-owned worker pool
#
# Usage:
#   ./scripts/start_workers.sh            # 2 workers (default)
#   TRANC3_WORKERS=4 ./scripts/start_workers.sh
#   ./scripts/start_workers.sh --nano-only   # only start nanoservice server
#   ./scripts/start_workers.sh --workers-only # only start inference workers
#
# Requires: Redis running on REDIS_URL (default: redis://localhost:6379)

set -euo pipefail

WORKERS=${TRANC3_WORKERS:-2}
MODE=${1:-"all"}

log() { echo "[tranc3-workers] $*"; }

# ── Check Redis ───────────────────────────────────────────────────────────────
if command -v redis-cli &>/dev/null; then
  if redis-cli -u "${REDIS_URL:-redis://localhost:6379}" ping &>/dev/null; then
    log "Redis: connected"
  else
    log "WARNING: Redis not reachable at ${REDIS_URL:-redis://localhost:6379}"
    log "         Workers will use in-memory queue fallback"
  fi
else
  log "redis-cli not found — skipping Redis check"
fi

# ── Start nanoservice HTTP server ─────────────────────────────────────────────
start_nano() {
  log "Starting nanoservice server on port ${NANO_PORT:-8001}…"
  python -m src.nanoservices.nano_server &
  NANO_PID=$!
  log "Nanoservice server PID: $NANO_PID"
}

# ── Start inference workers ───────────────────────────────────────────────────
start_workers() {
  for i in $(seq 0 $((WORKERS - 1))); do
    log "Starting inference worker $i…"
    TRANC3_WORKER_ID=$i python -m src.workers.inference_worker &
    log "  Worker $i PID: $!"
  done
}

# ── Cleanup on exit ───────────────────────────────────────────────────────────
cleanup() {
  log "Shutting down workers…"
  kill 0 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# ── Run ───────────────────────────────────────────────────────────────────────
case "$MODE" in
  "--nano-only")
    start_nano
    ;;
  "--workers-only")
    start_workers
    ;;
  *)
    start_nano
    start_workers
    ;;
esac

log "Tranc3 worker pool started ($WORKERS workers + nanoservice server)"
log "Press Ctrl+C to stop"
wait
