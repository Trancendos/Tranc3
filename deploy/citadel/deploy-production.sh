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

echo "==> Citadel preflight (compose, Vault HCL, env keys)"
python3 scripts/citadel_preflight.py

echo "==> Zero-cost provider audit"
python3 scripts/zero_cost_audit.py

echo "==> Branch benefit audit (logs/branch_benefit_audit_latest.md)"
python3 scripts/branch_benefit_audit.py || true

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

echo "==> Run proactive swarm manifests (optional)"
python3 scripts/swarm_runner.py --manifest config/swarm/manifests/platform-health.yaml || true
python3 scripts/swarm_runner.py --manifest config/swarm/manifests/citadel-deploy.yaml || true

echo "==> Vault (file storage) — init/unseal if first deploy"
if docker compose -f docker-compose.production.yml ps vault 2>/dev/null | grep -q Up; then
  docker compose -f docker-compose.production.yml exec -T vault vault status 2>/dev/null || \
    echo "WARN: Vault may need: vault operator init && vault operator unseal (see HashiCorp docs)"
fi

echo "Done. Backend :8000 | Dashboard /dashboard | Admin OS | Swarm :8053 | infinity-admin :8044"
