# DEPRECATED: vault-service

> **DO NOT USE for new secrets.** This worker is superseded by `workers/infinity-void/`.

## Status

**Deprecated as of 2026-06-14.** This service will be removed once all consumers
have migrated to `workers/infinity-void/` (canonical AES-256-GCM vault, The Void,
Lead AI: Prometheus, port 8002).

## Correction (2026-07-30)

This document originally pointed to `workers/the-void/` as the successor. That
directory was a separate, parallel implementation (with a Rust crypto extension)
that was never wired into `docker-compose.production.yml` and has since been
removed — it was superseded before ever being deployed. The actual, deployed,
zero-cost-aligned successor has been `workers/infinity-void/` (pure Python
standard library + SQLite, no external crypto dependency) all along; see
`CLAUDE.md`'s Self-Hosted Worker Map. Migration instructions below are corrected
to match.

## Why deprecated

`vault-service` wraps OpenBao (a HashiCorp Vault fork) and carries operational
overhead (unseal ceremony, Shamir shards) that is disproportionate for the
Trancendos self-hosted zero-cost architecture. `workers/infinity-void/` provides
equivalent AES-256-GCM encryption using only the Python standard library and
SQLite, with no external unsealing dependency.

## Migration instructions

A real migration tool already exists — use it rather than the manual curl steps
below:

```bash
python scripts/migrate_vault_secrets.py --dry-run   # verify first
python scripts/migrate_vault_secrets.py             # then run for real
```

It reads every active secret from vault-service's SQLite database, decrypts with
`VAULT_MASTER_KEY`, and re-stores each one via The Void's HTTP API
(`VOID_URL`, default `http://localhost:8002`) using `MASTER_KEY_SEED`-based
encryption. See that script's own docstring for required environment variables.

Manual equivalent, if needed:

1. Export secrets via the vault-service read API before decommissioning:
   ```bash
   curl -H "X-Vault-Token: $TOKEN" http://localhost:8038/v1/secret/data/<path>
   ```
2. Restore each secret in The Void (`workers/infinity-void/`, port 8002):
   ```bash
   curl -X POST http://localhost:8002/secrets \
        -H "Authorization: Bearer $INTERNAL_SECRET" \
        -H "Content-Type: application/json" \
        -d '{"key": "<name>", "value": "<secret>"}'
   ```
3. Update all service references from `VAULT_ADDR=http://vault-service:8038` to
   `http://infinity-void:8002`.
4. Only after `migrate_vault_secrets.py` has run successfully against production
   and been verified: remove `vault-service` from `docker-compose.production.yml`
   and set `VAULT_DECOMMISSIONED=1` (per that script's own docstring). This is a
   live-data migration, not a code change — do not remove the compose entry
   before that run has actually happened.

## Contact

Raise an issue in The Workshop (Forgejo) under the `the-void` milestone.
