# Service Doc-Pack — DevOcity

| Field | Value |
|---|---|
| **Entity** | DevOcity |
| **Lead AI** | Kitty |
| **Status** | ✅ In repo (per `CLAUDE.md` service table) — Live tier |
| **Code** | `src/devocity/portal.py`, `src/devocity/routes.py`; router registered in `api.py` (`app.include_router(_devocity_router)`, line 864) — **plus a separate standalone worker**, `workers/devocity/worker.py` (SQLite-backed, now the actual deployed image as of the 2026-07-11 Dockerfile fix — see Verification Log) |

> **Truthfulness:** claims cite `src/devocity/portal.py` and `src/devocity/routes.py` directly,
> plus grep-verified cross-checks against `src/security/security_framework.py`. Status is owned
> by the `CLAUDE.md` service table; identity by `PLATFORM_ENTITIES.md`.
> **Major finding: issued API keys are never validated by anything.** DevOcity implements real,
> good-practice key generation (`trx_` prefix, `secrets.token_hex(28)`, SHA-256 hash stored —
> never plaintext — plain key returned exactly once at issuance with an explicit "won't be shown
> again" warning). Scopes (`READ`/`WRITE`/`ADMIN`/`SPARK`/`GRID`/`FULL`) imply these keys are
> meant to gate access to The Spark and The Digital Grid. **No code anywhere in this repo
> validates a DevOcity-issued key against any protected route** — grep confirms the only other
> `api_key`/`key_hash` validation logic in the codebase is `src/security/security_framework.py`'s
> `validate_api_key()`, a completely separate, unrelated mechanism with no cross-reference to
> DevOcity's `ApiKey.key_hash`. Issuing a key with `scope: full` has zero actual authorization
> effect anywhere in this repo today.
> **Fixed:** every `/devocity/accounts*` route now requires `Depends(get_current_user)`.
> `POST /devocity/accounts` verifies `body.user_id` matches the caller's own identity (unless the caller holds the `admin` role); every account-scoped route (`get_account`, key issuance/listing/revocation,
> webhook registration/listing) verifies `account.user_id` matches the caller via a shared
> `_get_owned_account()` helper. This closes the previously-documented gap where anyone who
> obtained an account UUID could self-issue `ADMIN`/`FULL`-scope API keys for it.

## 1. Service Governance Charter (GOV)

- **Mission:** developer portal — account management, API key issuance, webhook registration,
  and quickstart guides for platform integrators.
- **Owner (RACI-A):** Kitty; Platform Owner Trancendos.
- **Scope:** `src/devocity/portal.py`'s `DevOcity` class — account/key/webhook CRUD and static
  guide listing. Actual enforcement of issued keys against protected routes is **not**
  implemented anywhere in this repo — see truthfulness header.

## 2. Detailed Design Document (DDD)

### HTTP surface (`src/devocity/routes.py`, prefix `/devocity`)

| Method | Route | Backing |
|---|---|---|
| GET | `/devocity/status` | `DevOcity.stats()` — account/key counts, guide count |
| GET | `/devocity/guides` | `DevOcity.guides()` — static list of 4 hard-coded quickstart guides |
| POST | `/devocity/accounts` | `DevOcity.create_account()` — body `{"user_id", "display_name"}`; 400 if `user_id` missing; **no verification that `user_id` is a real Infinity user** |
| GET | `/devocity/accounts/{id}` | `DevOcity.get_account()` — 404 if missing |
| POST | `/devocity/accounts/{id}/keys` | `DevOcity.issue_api_key()` — returns the plaintext key exactly once; 400 on invalid scope, 404 if account missing |
| GET | `/devocity/accounts/{id}/keys` | Lists non-revoked keys (hash/prefix only, never plaintext) |
| DELETE | `/devocity/accounts/{id}/keys/{key_id}` | `DevOcity.revoke_api_key()` — 404 if not found |
| POST | `/devocity/accounts/{id}/webhooks` | `DevOcity.register_webhook()` — generates a 32-byte hex signing secret |
| GET | `/devocity/accounts/{id}/webhooks` | Lists active webhooks |

### Data model (`portal.py`)
- `DeveloperAccount`: `id` (uuid4), `user_id` (claimed Infinity user ID, unverified), `status`
  (`DevAccountStatus`: active/suspended/sandbox), `api_keys`, `webhooks`, `usage` (endpoint →
  call count — **field exists but is never written to anywhere in this file**, so usage tracking
  is a dead field).
- `ApiKey`: `key_prefix` (first 8 chars, shown in UI), `key_hash` (SHA-256, correctly never
  storing plaintext), `scopes` (`ApiKeyScope` enum), `revoked`, `request_count` (**also never
  incremented anywhere** — another dead counter).
- `WebhookEndpoint`: `secret` (32-byte hex, `secrets.token_hex(32)` — cryptographically sound),
  `delivery_count`/`failure_count` (**both dead — never incremented; no actual webhook delivery
  code exists in this module** — registering a webhook stores it but nothing ever POSTs to it).

### Redis persistence — real, lazily hydrated
- `_ensure_loaded()` hydrates `_accounts` from Redis (`devocity:account:*` keys) on first access
  per-process; `_persist_account()` writes back with a 1-year TTL via `_fire_persist()` (fire-and-
  forget `asyncio.create_task`, wrapped in `except Exception: pass`). This is genuinely more
  durable than most entities audited in this series (which are pure in-memory with no
  persistence) — a real positive finding, not just defects.
- **Caveat:** `_fire_persist()` only schedules the write if an event loop is already running
  (`loop.is_running()`); if called from a non-async context the persist silently never happens.

## 3. Technical Architecture Solutions Design (TASD)

- **Style:** in-process module with a module-level singleton (`get_devocity()`); Redis-backed
  persistence for accounts (with 1-year TTL, matching the module's own comment "API keys must
  outlive process restarts").
- **Decision: no key-validation middleware.** Despite `ApiKeyScope` implying gated access to The
  Spark/The Digital Grid, no dependency or middleware in this repo checks a request's key against
  `ApiKey.key_hash`. This is a substantial, real gap between the entity's stated purpose and its
  actual enforcement — documented, not fixed (adding real key-gated auth to The Spark/Grid routes
  is an architectural change well beyond this docs pass).
- **Fixed:** account-creation and key-issuance endpoints now require `Depends(get_current_user)`
  plus a self-or-admin ownership check via `_get_owned_account()`, mirroring `api.py`'s
  `gdpr_erase()` pattern. Covered by `tests/test_devocity_auth.py`.

## 4. RACI Matrix

| Activity | Kitty (Lead) | Platform Owner | Infinity | Platform Engineering |
|---|---|---|---|---|
| Account/key/webhook CRUD changes | **R** | A | I | C |
| Wiring key validation into protected routes (future) | C | **A** | C | **R** |

## 5. Solutions Integration Model (SIM)

- **Upstream:** any caller of `/devocity/accounts*` routes now requires `Depends(get_current_user)`
  plus the self-or-admin ownership check (see truthfulness header) — closed the previously-
  documented no-auth gap. `GET /status` and `GET /guides` remain intentionally public.
- **Downstream:** Redis (`src/core/redis_store`) for account persistence; best-effort Observatory
  `observe()` on create/issue/register events. **No downstream call to The Spark, The Digital
  Grid, or any other protected service** — the `SPARK`/`GRID` scopes are purely descriptive
  metadata with no enforcement wiring.
- **Partially integrated:** Infinity (SSO) — `create_account()` now requires the caller-supplied
  `user_id` to match the authenticated caller's own identity (or the `admin` role), which backs
  the access-control half of the "wired to Infinity (SSO)" claim; it does not verify the `user_id`
  against a real Infinity account record.

## 6. Architecture Scalability Document (ASD)

- **Load model:** in-memory `_accounts` dict, lazily hydrated from Redis; unbounded in-process
  growth per running instance until Redis TTL (1 year) expires entries.
- **Bottleneck:** `_fire_persist()`'s fire-and-forget write can silently no-op outside a running
  event loop — see TASD caveat.
- **Zero-cost limits:** Redis usage is within the platform's existing Upstash free-tier budget
  (no new dependency introduced by this module).
- **Degradation:** Redis unavailability degrades to in-memory-only for the running process's
  lifetime (both hydration and persist wrapped in `except Exception`).

## 7. Deployment Scope Matrix (DSM)

- **Mode awareness:** No — this entity's own code does not call `PlatformInfraMode` / `src/platform/infrastructure_mode.py`. (Some platform-wide, cross-cutting code *does* branch on the mode — `src/routers/adaptive.py` and `src/routers/ecosystem.py` read/set `PLATFORM_INFRA_MODE`/`SYSTEM_MODE` directly, and `Dimensional/architecture/storage_factory.py` selects a storage provider from `SYSTEM_MODE` — but none of that code is owned by this or any other one of the 43 named entities; it is shared platform infrastructure, not this service's own logic. The Citadel is the only one of the 43 named entities whose own code branches on the mode — see `docs/services/the-citadel/README.md`.) This entity's deployment scope is determined externally — by which `docker-compose.production.yml` service block runs, and where — not by in-process mode detection.
- **Runtime placement:** standalone worker with its own `docker-compose.production.yml` service block (`devocity`, port 8110) and its own Traefik route — does not run inside the `tranc3-backend` monolith. **This worker's Dockerfile previously only `COPY`'d a placeholder `main.py`** (the same deployed-stub-vs-undeployed-real defect found for The Academy/The Basement/The Studio) — **fixed**: it now builds and runs the real, more complete SQLite-backed `worker.py`, with a named volume (`devocity-data:/app/data`) added so its data survives redeploys.
- **Persistence:** named volume now attached to the `devocity` compose service (added alongside the worker.py fix above) — state survives container restarts/redeploys in any mode
- **Note:** this entity has **two** deployment surfaces — a router mounted in the `tranc3-backend` monolith (`api.py`) *and* a separate standalone worker (`devocity`, port 8110). The table below describes the standalone worker; the monolith-mounted router follows the monolith's own placement (see the monolith pattern noted across this platform's other entities) and shares its volume.
- **Note:** the monolith router (`src/devocity/portal.py`) has its own, separate persistence story — real Redis-backed storage (per this pack's own DDD/ASD) via the shared platform Redis service. That finding is specifically about the monolith side; checked directly against `workers/devocity/worker.py` and confirmed it does **not** use Redis at all — the standalone worker's persistence is exclusively the SQLite + volume described above, unrelated to the monolith's Redis usage.

| Setup | What runs, and where | Data locality | Hard blockers / caveats |
|---|---|---|---|
| **Cloud-Only** | the `devocity` compose block runs on a single cloud host, now running the real `worker.py`; Traefik/edge in front | persists via its attached volume as long as the disk is preserved on that host | none beyond standard single-host durability (no built-in cross-host replication) |
| **Hybrid** | same `devocity` compose block; per `docs/architecture/infrastructure-modes.md`'s Hybrid diagram, this worker itself still runs as a single instance (cloud or local host), with only shared persistent data (not specific to this worker) split via TrueNAS/Syncthing | as above, optionally local-synced if a volume exists | requires `CITADEL_LOCAL_STACK=true` if a local compose stack should run alongside the cloud one |
| **Local-Only** | same `devocity` compose block, run entirely on local/Citadel hardware behind local Traefik | fully local, volume-backed | none beyond standard local-hardware ops |

- **Zero-cost posture per mode:** Cloud-Only defaults to the `zero_cost_cloud` AI-rotation chain; Hybrid/Local-Only default to `zero_cost_full` (`config/platform/infrastructure_mode.yaml`) — this only affects AI-Gateway-routed calls, not this entity's own logic
- **Switching modes:** operator-level via `PLATFORM_INFRA_MODE` (or legacy `SYSTEM_MODE`); this entity needs no code change to move between modes, only a redeploy-target change for its own compose block

## 8. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Web framework | FastAPI `APIRouter` | mounted into the main `api.py` app |
| Key generation | `secrets.token_hex()` + SHA-256 hash storage | OSS, in-process, correct practice |
| Persistence | Redis (`src/core/redis_store`), 1-year TTL | existing platform dependency, zero new cost |
| Key validation (missing) | none | N/A — not implemented anywhere |

## 9. Environment Support Matrix (ESM)

> Grounded against `docker-compose.development.yml` (6 services), `docker-compose.uat.yml` (16 services), and `docker-compose.production.yml` (286 services) — checked by exact compose service name, not assumed.

| Environment | Covered? | What runs | Notes |
|---|---|---|---|
| **Dev** | Partial | the `api` service in `docker-compose.development.yml` runs the monolith router — the standalone `devocity` worker is **not** in this compose file | standalone worker has zero Dev coverage |
| **UAT** | Partial | same monolith router via `api` in `docker-compose.uat.yml` — the standalone `devocity` worker is **not** in this compose file either | standalone worker has zero UAT coverage |
| **Production** | Yes | both surfaces — full detail in the DSM above | — |

- **Gap:** the standalone `devocity` worker (the more complete of this entity's two surfaces, per the DSM above) has **no Dev or UAT environment at all** — the first place it runs is Production. This is the norm for the ~90 standalone workers on this platform, not specific to this entity, but worth stating plainly rather than assuming pre-production validation exists where it doesn't.

## 10. Policy (POL)

- Every `/devocity/accounts*` route requires `Depends(get_current_user)` plus a self-or-admin
  ownership check — resolves the account-creation and key-issuance auth gap. The key-*validation*
  gap (issued keys not being checked against The Spark/Grid) remains open; see TASD.
- Zero-cost mandate: Redis usage stays within the existing platform budget; no new dependency.

## 11. Procedure (PROC)

- **Create a developer account:** `POST /devocity/accounts` with `{"user_id": "...",
  "display_name": "..."}` as the same user (or an admin) — `user_id` must
  match the caller's own identity.
- **Issue an API key:** `POST /devocity/accounts/{id}/keys` with `{"name": "...", "scopes":
  ["read"]}` on an account you own — capture the returned `key` field immediately; it is never
  retrievable again (only the hash is stored). Note the key currently has no enforcement effect
  anywhere downstream (see TASD).
- **Register a webhook:** `POST /devocity/accounts/{id}/webhooks` — stores the endpoint and a
  signing secret; no delivery mechanism exists to actually call it.

## 12. Runbook (RUN)

- **Issued API keys don't grant any real access:** expected — see the major finding in the
  truthfulness header; this is not a bug to chase, it's an unimplemented enforcement layer.
- **Webhooks never fire:** expected — `register_webhook()` only stores metadata; no delivery
  code exists in this module.
- **`usage`/`request_count`/`delivery_count`/`failure_count` fields always read zero:** expected
  — none of these counters are ever incremented anywhere in `portal.py`.
- **Account data missing after a restart:** check Redis connectivity — `_ensure_loaded()`
  degrades to empty in-memory state silently if Redis is unreachable.

## 13. Standards (STD)

- Naming: canonical entity name "DevOcity" per `CLAUDE.md`/`PLATFORM_ENTITIES.md`.
- Any DevOcity-issued API key that is documented as granting a `scope` MUST have a corresponding
  validation dependency wired into the routes it claims to gate before that scope is advertised
  as functional in user-facing documentation — this remains open (see TASD); the separate
  account/key-ownership auth gap is now closed.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-05 | Claude (session) | `src/devocity/portal.py` (350 lines), `src/devocity/routes.py` (103 lines), `api.py` router registration (line 864), grep cross-check against `src/security/security_framework.py` | Confirmed Live-tier, full pack authored. Major finding: DevOcity implements real, well-practiced API key generation (hashed, one-time plaintext reveal) and genuine Redis persistence, but no code anywhere in the repo validates an issued key against any protected route — the `SPARK`/`GRID`/`ADMIN`/`FULL` scopes are purely descriptive with zero enforcement. Also flagged: unauthenticated account creation with unverified `user_id` (contradicts the module's own "wired to Infinity SSO" claim), unauthenticated key issuance for any known account ID, and four dead counters (`usage`, `request_count`, `delivery_count`, `failure_count`) that are declared but never incremented. None of these were code-fixed — each requires an architectural auth/enforcement decision out of scope for a docs pass. |
| 2026-07-08 | Claude (session) | `src/devocity/routes.py` (168 lines, post-fix), `workers/devocity/worker.py` | Closed the account-creation/key-issuance no-auth gap: every `/devocity/accounts*` route now requires `Depends(get_current_user)` plus `_get_owned_account()`'s self-or-admin check. Verified via `tests/test_devocity_auth.py`. Also fixed a separate, more severe defect in the standalone `workers/devocity/worker.py`: `INTERNAL_SECRET` defaulted to the hardcoded literal `"dev-secret"` rather than failing open on an unset secret (the pattern used by every other `INTERNAL_SECRET`-gated worker in this codebase) — a guessable, undocumented backdoor credential shipped by default in production since `INTERNAL_SECRET` is unset in `docker-compose.production.yml`/`.env.example`. Changed the default to `""`, matching the established fail-open-if-unset convention. The key-*validation* gap (issued DevOcity keys never checked against The Spark/Grid) remains open — unrelated to this fix, requires a separate architectural decision. |
| 2026-07-09 | Claude (session) | `src/devocity/routes.py` (post-fix), `src/auth/tokens.py` | cubic correctly flagged the same class of bug already found in Tranquility/tAimra: the initial fix's cross-user override checked `tier == "enterprise"`, but real JWTs carry `tier` as a numeric int and never that string. `_require_account_owner()`'s override now checks `role == "admin"` instead. Tests updated to assert real-shaped payloads. |
| 2026-07-11 | Claude (session, DSM/implementation pass) | `workers/devocity/Dockerfile`, `workers/devocity/main.py`, `workers/devocity/worker.py` | Found, while authoring the Deployment Scope Matrix, that `workers/devocity/` has the same deployed-stub-vs-undeployed-real defect previously found for The Academy/The Basement/The Studio: the Dockerfile only `COPY`'d a placeholder `main.py` (zero storage, hardcoded empty/placeholder responses) while a genuinely more complete SQLite-backed `worker.py` sat unused in the same directory. **Fixed this time** (unlike Academy's prior pass, this was caught and corrected in the same session rather than left for a follow-up): changed the Dockerfile to build/run `worker.py` and added a named volume (`devocity-data:/app/data`) to `docker-compose.production.yml`. DSM rewritten to reflect the fix. Note this is independent of the `src/devocity/portal.py` monolith-router finding above (API-key issuance) — two separate surfaces, two separate fixes. |
