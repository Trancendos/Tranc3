#!/usr/bin/env bash
# scripts/start.sh — Start the Tranc3 Bots service
#
# Usage:
#   ./scripts/start.sh             # default port 8080, 1 worker
#   PORT=9000 ./scripts/start.sh   # custom port
#   WORKERS=4 ./scripts/start.sh   # multiple uvicorn workers

set -euo pipefail

PORT=${PORT:-8080}
WORKERS=${WORKERS:-1}

log() { echo "[tranc3-bots] $*"; }

log "Starting Tranc3 Bots service on port $PORT ($WORKERS worker(s))…"
log "Engine URL: ${TRANC3_ENGINE_URL:-<not set — running standalone stubs>}"
log "Redis URL:  ${REDIS_URL:-redis://localhost:6379}"

exec uvicorn server.app:app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --workers "$WORKERS" \
  --log-level "${LOG_LEVEL:-info}"
