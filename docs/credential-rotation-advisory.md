# Credential Rotation Advisory

**Date:** 2026-05-22  
**Scope:** Tranc3 Smart Adaptive Automation Implementation  
**Severity:** ADVISORY — No hardcoded secrets found in source code

## Executive Summary

A comprehensive scan of the codebase was performed using the `VaultSecretLoader.detect_leaks()` utility and pattern-based grep analysis. **No hardcoded secrets were found in any source files, CI configurations, or committed dotfiles.** However, several environment-level findings warrant attention.

## Findings

### 1. GITHUB_TOKEN in Runtime Environment (Risk: HIGH)

The `GITHUB_TOKEN` environment variable is present in the CI/runtime environment. This is expected and automatically provided by GitHub Actions/Forgejo CI runners. The token is ephemeral and scoped to the current workflow run.

**Action Required:** None for the token itself. However, ensure that:
- Workflow logs do not expose the token value
- The token is not passed to child processes that log arguments
- `GITHUB_TOKEN` is never committed to `.env` files or source code

### 2. .env.example Contains Placeholder Secrets (Risk: LOW)

The `.env.example` file contains placeholder values for sensitive configuration:

| Variable | Placeholder | Purpose |
|---|---|---|
| `SECRET_KEY` | `your-secret-key-here` | Django/FastAPI session signing |
| `STRIPE_SECRET_KEY` | `sk_test_...` | Stripe payment processing |
| `STRIPE_WEBHOOK_SECRET` | `whsec_...` | Stripe webhook verification |
| `JWT_SECRET` | `your-jwt-secret` | JWT token signing |
| `CITADEL_WEBHOOK_SECRET` | `your-webhook-secret-here` | Forgejo webhook receiver |
| `SUPABASE_SERVICE_ROLE_KEY` | `eyJ...` | Supabase admin access |
| `SUPABASE_JWT_SECRET` | *(empty)* | Supabase JWT verification |
| `INTERNAL_SECRET` | *(empty)* | Inter-worker communication |
| `IP_PROTECTION_KEY` | *(empty)* | IP protection features |
| `MASTER_KEY_SEED` | *(empty)* | Deterministic key derivation |
| `BACKUP_API_TOKEN` | *(empty)* | Backup API access |
| `GRAFANA_CLOUD_API_KEY` | `your-grafana-key` | Grafana Cloud telemetry |
| `PINECONE_API_KEY` | `your-pinecone-key` | Pinecone vector DB |
| `OPENROUTER_API_KEY` | *(empty)* | OpenRouter LLM inference |
| `HF_API_KEY` | *(empty)* | HuggingFace inference |
| `GROQ_API_KEY` | *(empty)* | Groq LLM inference |
| `REDIS_URL` | `rediss://:[password]@...` | Upstash Redis |

**Action Required:** These are all placeholders — no rotation needed. If any real values were accidentally committed in the past, those specific credentials must be rotated.

### 3. Cloudflare R2 Credentials (Risk: MEDIUM)

The StorageFactory supports Cloudflare R2 for CLOUD_ONLY/HYBRID modes. R2 credentials are loaded from environment variables (`R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`). These are not committed to the repository but should be rotated if:
- They were ever logged or exposed in CI output
- They were shared outside of a secrets manager
- They have been in use for more than 90 days

**Action Required:** Follow Cloudflare R2 credential rotation procedure if any of the above apply.

### 4. AuditLedger HMAC Key (Risk: MEDIUM)

The `AuditLedger` uses an HMAC signing key derived from either the `AUDIT_LEDGER_KEY` environment variable or a generated key stored in the ledger directory. If the key file is compromised, the integrity of the entire audit chain is suspect.

**Action Required:**
- Store `AUDIT_LEDGER_KEY` in a secrets manager
- If the auto-generated key file is accessible to unauthorized users, rotate it and re-initialize the ledger
- Monitor ledger integrity with `Sentinel` periodic checks

### 5. VaultSecretLoader Zeroization (Risk: LOW)

The `VaultSecretLoader` implements memory zeroization via `ctypes.memset` for the `secret()` context manager. This reduces the window of exposure for secrets in process memory but is not guaranteed on all Python implementations due to string interning and garbage collection.

**Action Required:** None — the zeroization is a best-effort defense-in-depth measure. For environments requiring cryptographic guarantees of memory clearing, consider using `mmap` with `MAP_LOCKED` or a dedicated HSM.

## Recommendations

1. **Implement a secrets rotation schedule** — Rotate all service credentials (R2, Supabase, Stripe, etc.) every 90 days minimum
2. **Enable `VaultSecretLoader.detect_leaks()` in CI** — Add a step to the Forgejo CI workflow that runs leak detection on every push
3. **Use Forgejo Secrets** — Store all sensitive values in Forgejo's encrypted secrets storage, never in `.env` files on disk
4. **Audit log access** — Enable `VaultSecretLoader(audit_enabled=True)` in production to track all secret access
5. **Monitor with Sentinel** — Configure the `Sentinel` daemon to perform periodic integrity checks on the audit ledger and secret store

## Scan Methodology

- **Static analysis:** `grep -rn` for common secret patterns (AWS keys, API tokens, private keys)
- **Runtime analysis:** `VaultSecretLoader.detect_leaks()` scanning environment variables for high-entropy values matching known secret patterns
- **File analysis:** Checked `.env.example`, CI workflows, and all Python/YAML/JSON files for committed secrets

## Conclusion

No immediate credential rotation is required. The codebase follows good practices with placeholder-only values in `.env.example` and no hardcoded secrets in source code. The `GITHUB_TOKEN` finding is expected CI runtime behavior. Implementing the recommended rotation schedule and CI-integrated leak detection will provide ongoing protection.
