# Service Doc-Pack — The Void (Secrets & Password Vault)

| Field | Value |
|---|---|
| **Entity** | The Void (`PID-VOI`) |
| **Lead AI** | Prometheus (`AID-VOI-01`); Prime: The Guardian (Marcus Magnolia) |
| **Status** | 🔧 Migrating (per `CLAUDE.md` service table) — CF Worker → self-hosted |
| **Code** | `workers/infinity-void/worker.py` (self-hosted); legacy `cloudflare/infinity-void/` |
| **Port** | app default **8082** (`int(os.getenv("PORT","8082"))`). *Note:* the Dockerfile `EXPOSE`s **8002** (stale/cosmetic — the app binds `PORT`); sync tracked in issue #188 |

> **Truthfulness:** claims cite `workers/infinity-void/worker.py` (`worker` v2.1.0). Status is owned by
> the `CLAUDE.md` service table; identity by `PLATFORM_ENTITIES.md`. `PLATFORM_ENTITIES.md` lists The
> Void's *primary worker* as `config-service` (8024) — a separate worker under the same entity; this
> pack documents the **vault** worker (`infinity-void`).

## 1. Service Governance Charter (GOV)

- **Mission:** self-hosted encrypted secrets + password vault — AES-256-GCM at rest, replacing the
  Cloudflare Worker + D1 + KV + R2 stack at zero cost.
- **Owner (RACI-A):** Prometheus (Lead AI); Prime The Guardian (Marcus Magnolia).
- **Scope:** a FastAPI worker exposing vault status + secret CRUD + per-secret audit, behind
  Infinity-delegated auth.

## 2. Detailed Design Document (DDD)

### HTTP surface (`workers/infinity-void/worker.py`)
| Method | Route | Auth | Backing |
|---|---|---|---|
| GET | `/health` | **public** | SQLite schema init + `sealed` state + active-secret count |
| GET | `/vault/status` | Infinity auth | sealed state + secret count |
| POST | `/secrets` | Infinity auth | store (AES-256-GCM encrypt) |
| POST | `/secrets/retrieve` | Infinity auth | decrypt + return |
| GET | `/secrets` | Infinity auth | list metadata |
| GET | `/secrets/{secret_id}` | Infinity auth | metadata for one secret |
| DELETE | `/secrets/{secret_id}` | Infinity auth | delete |
| GET | `/secrets/{secret_id}/audit` | Infinity auth | per-secret audit trail |

- **Auth:** `get_auth_user_id(authorization)` delegates verification to Infinity One when
  `INFINITY_ONE_URL` is set — it `POST`s to `{INFINITY_ONE_URL}/auth/verify` with the caller's
  `Authorization` and the worker's `X-Internal-Secret`. No verified `user_id` → `401`. `/health` is open.

### Cryptography & storage
- **AES-256-GCM** (`cryptography.hazmat` `AESGCM`) with **PBKDF2-HMAC-SHA256, 100k iterations**
  (`PBKDF2HMAC`) key derivation from `MASTER_KEY_SEED`; random IV per secret.
- **Metadata:** SQLite at `VOID_DATA_DIR/void.db` (`void_secrets`, `void_vault_state`) — replaces CF D1.
- **Secret blobs:** filesystem under `VOID_DATA_DIR/secrets` (`R2_DIR`) — replaces CF R2.
- **Rate limiting:** in-memory `RateLimiter` (default 50 requests / 3600 s) — replaces CF KV.

### Fail-fast config
- The worker **raises `RuntimeError` at import** if `MASTER_KEY_SEED` is unset or still `change-me-in-production`,
  and likewise if `INTERNAL_SECRET` is unset or still `internal-dev-secret`. No weak-default startup.

## 3. Technical Architecture Solutions Design (TASD)

- **Style:** single FastAPI worker; encryption in-process; state on local disk (SQLite + files).
- **Decision:** delegate identity to Infinity (`/auth/verify`) rather than re-implement auth; keep the
  crypto boundary (key derivation + AES-GCM) inside the worker.
- **CORS:** `ALLOWED_ORIGINS` fixed to the `trancendos.com` / `api.` / `arcadia.` origins.

## 4. RACI Matrix

| Activity | Prometheus (Lead) | The Guardian (Prime) | Platform Owner | The Observatory |
|---|---|---|---|---|
| Crypto (key derivation, AES-GCM) | **R** | **A** | C | I |
| Secret CRUD + audit | **R/A** | C | C | I |
| Auth delegation (Infinity) | **R** | A | C | I |
| Incident (vault down / sealed) | **R** | **A** | I | C |

## 5. Solutions Integration Model (SIM)

- **Upstream:** any service needing a secret calls the vault with an Infinity-issued token; the vault
  verifies it via Infinity One.
- **Downstream:** SQLite + filesystem persistence; audit rows per secret.
- **Auth boundary:** all secret + status routes require a verified Infinity `user_id`; `/health` open.

## 6. Architecture Scalability Document (ASD)

- **Load model:** vault ops are low-rate, crypto-bound (PBKDF2 100k is intentionally costly).
- **Bottleneck:** SQLite + local files are single-node — **not** horizontally shared; a single vault
  instance (or a shared volume + external DB) is required. Scaling out is out of scope today.
- **Zero-cost limits & hard stops:** no CF D1/KV/R2; in-memory rate limiter caps abuse. No paid dependency.
- **Degradation:** `/health` reports `degraded` if the SQLite schema/queries fail.

## 7. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Encryption | AES-256-GCM (`cryptography`) | OSS |
| Key derivation | PBKDF2-HMAC-SHA256 (100k) | in-process |
| Metadata store | SQLite | local file |
| Blob store | local filesystem (`R2_DIR`) | local disk |
| Rate limiting | in-memory sliding window | in-process |
| Identity | delegated to Infinity One | self-hosted |

## 8. Policy (POL)

- `MASTER_KEY_SEED` + `INTERNAL_SECRET` MUST be strong, unique, non-default (enforced by fail-fast).
  Secrets never logged; keys from env/vault only. Reuses platform policy (`POL-AI-001`, `docs/defstan/`).

## 9. Procedure (PROC)

- **Rotate the master key:** re-encrypt stored secrets under a new `MASTER_KEY_SEED` (offline
  migration); never change the seed without re-encryption or existing secrets become undecryptable.

## 10. Runbook (RUN)

- **Startup `RuntimeError` (MASTER_KEY_SEED / INTERNAL_SECRET):** the value is unset or a known default —
  set a strong unique value (`python -c "import secrets; print(secrets.token_hex(32))"`).
- **`/health` `degraded`:** SQLite schema/query failed — check `VOID_DATA_DIR` is writable and the DB intact.
- **All secret routes return `401`:** Infinity verification failed (or `INFINITY_ONE_URL` unset) — confirm
  the token and that Infinity One `/auth/verify` is reachable with the worker's `X-Internal-Secret`.

## 11. Standards (STD)

- AES-256-GCM; PBKDF2-HMAC-SHA256 100k; random IV per secret. Auth delegated to Infinity.
- Fail-fast on weak/absent secrets; CORS restricted to platform origins.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-03 | Claude (session) | `workers/infinity-void/worker.py` (routes, `get_auth_user_id`, AESGCM/PBKDF2, SQLite/`R2_DIR`, `RateLimiter`, fail-fast config, PORT default), Dockerfile | Routes, auth delegation, crypto, storage, rate limiting, and the 8082-vs-EXPOSE-8002 port note verified against code |
