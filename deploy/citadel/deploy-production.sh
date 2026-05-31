#!/usr/bin/env bash
# Deploy Tranc3 production stack on The Citadel (self-hosted, zero-cost core).
# Usage (on Citadel host, from repo root):
#   cp .env.production.example .env.production   # then fill from Vault
#   ./deploy/citadel/deploy-production.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if [[ ! -f .env.production ]]; then
  echo "ERROR: .env.production missing. Copy from .env.production.example and load secrets from The Void (Vault)." >&2
  exit 1
fi

# Required production keys (fail fast)
for key in SECRET_KEY JWT_SECRET; do
  if ! grep -q "^${key}=" .env.production 2>/dev/null; then
    echo "ERROR: ${key} must be set in .env.production" >&2
    exit 1
  fi
  if grep -q "^${key}=LOAD_FROM_VAULT" .env.production 2>/dev/null; then
    echo "WARN: ${key} still points at Vault placeholder — resolve before serving traffic" >&2
  fi
done

echo "==> Pull latest main"
git fetch origin main
git checkout main
git pull origin main

echo "==> Build and start production compose"
docker compose -f docker-compose.production.yml pull --ignore-buildable 2>/dev/null || true
docker compose -f docker-compose.production.yml build
docker compose -f docker-compose.production.yml up -d

echo "==> Wait for P0 health"
sleep 15
python3 scripts/health_check.py || true

echo "==> Run proactive swarm manifest (optional)"
python3 scripts/swarm_runner.py --manifest config/swarm/manifests/platform-health.yaml || true

echo "Done. Dashboard: infinity-admin :8044 | Swarm coordinator :8053"
