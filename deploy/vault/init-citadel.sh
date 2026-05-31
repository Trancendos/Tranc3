#!/usr/bin/env bash
# One-time HashiCorp Vault init helper for Citadel (file storage, not -dev).
# Run after: docker compose -f docker-compose.production.yml up -d vault
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

export VAULT_ADDR="${VAULT_ADDR:-http://127.0.0.1:8200}"

echo "==> Vault status"
if vault status 2>/dev/null | grep -q "Sealed.*false"; then
  echo "Vault already initialized and unsealed."
  exit 0
fi

if vault status 2>&1 | grep -q "Initialized.*false"; then
  echo "==> Initializing Vault (save keys securely!)"
  vault operator init -key-shares=5 -key-threshold=3 | tee vault-init-keys.txt
  chmod 600 vault-init-keys.txt
  echo "Keys written to vault-init-keys.txt — store offline, then delete from server."
fi

echo "==> Unseal Vault (enter 3 unseal keys when prompted)"
vault operator unseal
vault operator unseal
vault operator unseal

vault status
echo "Done. Load app secrets into Vault; map to .env.production via your secret sync."
