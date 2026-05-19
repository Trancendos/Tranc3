#!/bin/sh
# docker-entrypoint.sh — Trancendos backend startup
# Runs migrations then starts all processes

set -e

echo "[entrypoint] Starting Trancendos backend..."

# Run Alembic migrations (non-fatal if DATABASE_URL missing in dev)
if [ -n "$DATABASE_URL" ]; then
    echo "[entrypoint] Running database migrations..."
    python -m alembic upgrade head && echo "[entrypoint] Migrations complete" \
        || echo "[entrypoint] WARNING: migrations failed — continuing (may be expected on first cold start)"
else
    echo "[entrypoint] No DATABASE_URL set — skipping migrations"
fi

# Start main FastAPI + nanoservices
echo "[entrypoint] Starting services on :8000 and :8001..."
exec sh -c \
    "uvicorn api:app --host 0.0.0.0 --port 8000 --workers 2 & \
     uvicorn src.nanoservices.nano_server:nano_app --host 0.0.0.0 --port 8001 & \
     wait"
