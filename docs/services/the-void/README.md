# Service Doc-Pack — The Void (Secrets & Password Vault)

| Field | Value |
|---|---|
| **Entity** | The Void (`PID-VOI`) |
| **Lead AI** | Prometheus (`AID-VOI-01`); Prime: The Guardian (Marcus Magnolia) |
| **Status** | 🔧 Migrating (per `CLAUDE.md` service table) — CF Worker → self-hosted |
| **Code** | `workers/infinity-void/worker.py` (self-hosted); legacy `cloudflare/infinity-void/` |
| **Port** | **8002** — compose sets `PORT=8002` explicitly (`docker-compose.production.yml`), overriding the Python-level default of `int(os.getenv("PORT","8082"))` in `worker.py`. This was a real #188 routing defect (bare `CMD ["python","worker.py"]`, previously no compose `PORT` override → the container fell back to 8082 while compose only routed to 8002) — fixed by adding the explicit override. |

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

## 7. Deployment Scope Matrix (DSM)

- **Mode awareness:** No — this entity's own code does not call `PlatformInfraMode` / `src/platform/infrastructure_mode.py`. (Some platform-wide, cross-cutting code *does* branch on the mode — `src/routers/adaptive.py` and `src/routers/ecosystem.py` read/set `PLATFORM_INFRA_MODE`/`SYSTEM_MODE` directly, and `Dimensional/architecture/storage_factory.py` selects a storage provider from `SYSTEM_MODE` — but none of that code is owned by this or any other one of the 43 named entities; it is shared platform infrastructure, not this service's own logic. The Citadel is the only one of the 43 named entities whose own code branches on the mode — see `docs/services/the-citadel/README.md`.) This entity's deployment scope is determined externally — by which `docker-compose.production.yml` service block runs, and where — not by in-process mode detection.
- **Runtime placement:** standalone worker with its own `docker-compose.production.yml` service block (`infinity-void`, port 8002) and its own Traefik route — does not run inside the `tranc3-backend` monolith
- **Persistence:** named volume attached to the `infinity-void` compose service — state survives container restarts/redeploys in any mode
- **Note:** this is a secrets vault — losing its volume is a materially worse event than for most other entities (all encrypted secrets, not just cache/derived state), so backup of this specific volume matters more than the platform-wide default in every mode.

| Setup | What runs, and where | Data locality | Hard blockers / caveats |
|---|---|---|---|
| **Cloud-Only** | the `infinity-void` compose block runs on a single cloud host; Traefik/edge in front | persists via its attached volume as long as the volume/disk is preserved on that host | none beyond standard single-host durability (no built-in cross-host replication) |
| **Hybrid** | same `infinity-void` compose block; per `docs/architecture/infrastructure-modes.md`'s Hybrid diagram, this worker itself still runs as a single instance (cloud or local host), with only shared persistent data (not specific to this worker) split via TrueNAS/Syncthing | as above, optionally local-synced if a volume exists | requires `CITADEL_LOCAL_STACK=true` if a local compose stack should run alongside the cloud one |
| **Local-Only** | same `infinity-void` compose block, run entirely on local/Citadel hardware behind local Traefik | fully local, volume-backed | none beyond standard local-hardware ops |

- **Zero-cost posture per mode:** Cloud-Only defaults to the `zero_cost_cloud` AI-rotation chain; Hybrid/Local-Only default to `zero_cost_full` (`config/platform/infrastructure_mode.yaml`) — this only affects AI-Gateway-routed calls, not this entity's own logic
- **Switching modes:** operator-level via `PLATFORM_INFRA_MODE` (or legacy `SYSTEM_MODE`); this entity needs no code change to move between modes, only a redeploy-target change for its own compose block

## 8. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Encryption | AES-256-GCM (`cryptography`) | OSS |
| Key derivation | PBKDF2-HMAC-SHA256 (100k) | in-process |
| Metadata store | SQLite | local file |
| Blob store | local filesystem (`R2_DIR`) | local disk |
| Rate limiting | in-memory sliding window | in-process |
| Identity | delegated to Infinity One | self-hosted |

## 9. Policy (POL)

- `MASTER_KEY_SEED` + `INTERNAL_SECRET` MUST be strong, unique, non-default (enforced by fail-fast).
  Secrets never logged; keys from env/vault only. Reuses platform policy (`POL-AI-001`, `docs/defstan/`).

## 10. Procedure (PROC)

- **Rotate the master key:** re-encrypt stored secrets under a new `MASTER_KEY_SEED` (offline
  migration); never change the seed without re-encryption or existing secrets become undecryptable.

## 11. Runbook (RUN)

- **Startup `RuntimeError` (MASTER_KEY_SEED / INTERNAL_SECRET):** the value is unset or a known default —
  set a strong unique value (`python -c "import secrets; print(secrets.token_hex(32))"`).
- **`/health` `degraded`:** SQLite schema/query failed — check `VOID_DATA_DIR` is writable and the DB intact.
- **All secret routes return `401`:** Infinity verification failed (or `INFINITY_ONE_URL` unset) — confirm
  the token and that Infinity One `/auth/verify` is reachable with the worker's `X-Internal-Secret`.

## 12. Standards (STD)

- AES-256-GCM; PBKDF2-HMAC-SHA256 100k; random IV per secret. Auth delegated to Infinity.
- Fail-fast on weak/absent secrets; CORS restricted to platform origins.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-03 | Claude (session) | `workers/infinity-void/worker.py` (routes, `get_auth_user_id`, AESGCM/PBKDF2, SQLite/`R2_DIR`, `RateLimiter`, fail-fast config, PORT default), Dockerfile | Routes, auth delegation, crypto, storage, rate limiting, and the 8082-vs-EXPOSE-8002 port note verified against code |
| 2026-07-03 | Claude (session, follow-up) | `docker-compose.production.yml` (was missing an explicit `PORT` override) | Corrected: the earlier "8082 is the real app default, EXPOSE 8002 is stale" claim was wrong — 8002 is the consistently-referenced, intended port (matches monitoring scrape targets, `workers/README.md`, wiki, `docs/vault_security.md`). Fixed by adding `PORT=8002` to compose's `environment:` block rather than changing the port itself. |
