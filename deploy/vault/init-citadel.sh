#!/usr/bin/env bash
# Vault init entry point for Citadel.
# Delegates to scripts/vault-init.sh which handles:
#   - Shamir 5-of-3 initialisation
#   - AES-256-CBC encrypted key backup
#   - Auto-unseal, KV v2, audit log, ACL policies, service tokens
# Run after: docker compose -f docker-compose.production.yml up -d vault
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
exec "$ROOT/scripts/vault-init.sh" "$@"
