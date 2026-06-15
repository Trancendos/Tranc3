# DEPRECATED: vault-service

> **DO NOT USE for new secrets.** This worker is superseded by `workers/the-void/`.

## Status

**Deprecated as of 2026-06-14.** This service will be removed once all consumers
have migrated to `workers/the-void/` (canonical AES-256-GCM vault, The Void,
Lead AI: Prometheus).

## Why deprecated

`vault-service` wraps OpenBao (a HashiCorp Vault fork) and carries operational
overhead (unseal ceremony, Shamir shards) that is disproportionate for the
Trancendos self-hosted zero-cost architecture. `workers/the-void/` provides
equivalent AES-256-GCM encryption using only the Python standard library and
SQLite, with no external unsealing dependency.

## Migration instructions

1. Export secrets via the vault-service read API before decommissioning:
   ```bash
   curl -H "X-Vault-Token: $TOKEN" http://localhost:8038/v1/secret/data/<path>
   ```
2. Restore each secret in The Void:
   ```bash
   curl -X POST http://localhost:8038/secrets \
        -H "Content-Type: application/json" \
        -d '{"key": "<name>", "value": "<secret>"}'
   ```
   (Adjust port to `workers/the-void/` port — see `docker-compose.production.yml`.)
3. Update all service references from `VAULT_ADDR=http://vault-service:8038` to
   the `the-void` service URL.
4. Remove `vault-service` from `docker-compose.production.yml` after verification.

## Contact

Raise an issue in The Workshop (Forgejo) under the `the-void` milestone.
