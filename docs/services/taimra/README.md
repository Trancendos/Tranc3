# Service Doc-Pack — tAimra

| Field | Value |
|---|---|
| **Entity** | tAimra |
| **Lead AI** | tAImra |
| **Status** | ✅ In repo (per `CLAUDE.md` service table) — Live tier |
| **Code** | `src/taimra/digital_twin.py`, `src/taimra/routes.py`; router registered in `api.py` (`app.include_router(_taimra_router)`, line 819) — **plus a separate standalone worker**, `workers/taimra/worker.py` not audited in detail by this pack |

> **Truthfulness:** claims cite `src/taimra/digital_twin.py` and `src/taimra/routes.py` directly.
> Status is owned by the `CLAUDE.md` service table; identity by `PLATFORM_ENTITIES.md`.
> **Fixed:** every route in `src/taimra/routes.py` taking a `user_id` path parameter now requires
> `Depends(get_current_user)` plus a `_require_self_or_admin()` ownership check (mirrors
> `api.py`'s `gdpr_erase()` pattern) — callers can only activate/deactivate/record/export/delete
> their own twin unless they hold the `admin` role. `GET /taimra/status` remains
> intentionally public. This closes the previously-documented gap where any caller who knew a
> `user_id` could act on another user's digital twin.
> **The stated privacy guarantee "the twin never infers or stores sensitive I-Mind flagged
> content" is not enforced by any code.** No import of or call to `src.imind` exists anywhere in
> `src/taimra/digital_twin.py`. `record_interaction()` stores whatever `topics` list the caller
> supplies with no filtering, gating, or I-Mind pre-check — the privacy guarantee in the module's
> own header comment is aspirational, not implemented.

## 1. Service Governance Charter (GOV)

- **Mission:** opt-in digital twin — builds a per-user behavioural model (topics of interest,
  personality affinity, goals) from recorded interactions, to personalize future responses.
  Offline by default; the module's design intent is that it only activates on explicit user
  consent.
- **Owner (RACI-A):** tAImra; Platform Owner Trancendos.
- **Scope:** `src/taimra/*` implements twin lifecycle (activate/deactivate/record/suggest/export/
  delete) with in-memory storage, now auth-gated per truthfulness header. The I-Mind
  content-filtering guarantee described in the module's own comments is still not implemented.

## 2. Detailed Design Document (DDD)

### HTTP surface (`src/taimra/routes.py`, prefix `/taimra`)

| Method | Route | Backing |
|---|---|---|
| GET | `/taimra/status` | `TAimra.stats()` — total twins, by-status counts |
| POST | `/taimra/activate/{user_id}` | `TAimra.activate()` — creates-if-missing, sets status to `LEARNING` |
| POST | `/taimra/deactivate/{user_id}` | `TAimra.deactivate()` — sets status to `OFFLINE` if a twin exists |
| GET | `/taimra/twin/{user_id}` | Reaches directly into `TAimra()._twins` (private attribute) rather than a public getter — see TASD; 404 if no twin exists |
| POST | `/taimra/record/{user_id}` | `TAimra.record_interaction()` — no-op if twin is `OFFLINE` or doesn't exist |
| GET | `/taimra/suggest/{user_id}` | `TAimra.suggest_personality()` — highest-affinity personality, or `null` |
| GET | `/taimra/export/{user_id}` | `TAimra.export()` — full twin data (GDPR portability, per comment); auth-gated, self-or-admin; 404 if missing |
| DELETE | `/taimra/twin/{user_id}` | `TAimra.delete()` — full erasure (GDPR right to erasure, per comment); auth-gated, self-or-admin; 404 if missing |

### Twin lifecycle (`digital_twin.py`) — real, self-consistent state machine
- `TwinStatus`: OFFLINE (default) → LEARNING (on `activate()`) → ACTIVE (auto-promoted once
  `interaction_count >= 10`) → PAUSED (not actually set anywhere — `deactivate()` sets `OFFLINE`,
  not `PAUSED`, so the `PAUSED` enum member is currently dead/unreachable).
- `record_interaction()` is correctly a no-op when the twin is `OFFLINE` or doesn't exist,
  consistent with the "offline by default" design intent — this part of the privacy design is
  real and enforced.
- `suggest_personality()` returns the highest-affinity personality from a simple incrementing
  score (`+0.05` per use, capped at 1.0) — real, working, if simplistic.

### Unenforced privacy claims (module header vs. code)
- "The twin never infers or stores sensitive I-Mind flagged content" — **not implemented**. No
  I-Mind import or call anywhere in this file. `record_interaction()`'s `topics` parameter is
  stored verbatim with no content screening.
- "Governed by Trancendos Magna Carta policy" — route-level auth now exists (see truthfulness
  header), which backs the access-control half of this claim; content-filtering does not.
- The GDPR export/erasure functions (`export()`, `delete()`) are real and functionally correct,
  and now auth-gated (self-or-admin), so they deliver genuine GDPR-compliant self-service
  data rights as wired.

## 3. Technical Architecture Solutions Design (TASD)

- **Style:** in-process module with a module-level singleton (`get_taimra()`); in-memory `_twins`
  dict, no persistence, no external DB.
- **Code-quality note:** `GET /taimra/twin/{user_id}` accesses `get_taimra()._twins.get(user_id)`
  directly from `routes.py` — the same private-attribute-reach pattern flagged in Tranquility's
  doc-pack (this session, same batch). Consider a public `get()` method for consistency.
- **Dead enum member:** `TwinStatus.PAUSED` is declared but never assigned anywhere in
  `digital_twin.py` — `deactivate()` uses `OFFLINE` instead. Either `PAUSED` is vestigial or a
  planned "pause without losing LEARNING/ACTIVE progress" feature was never wired up; not
  resolved in this pass.
- **Fixed:** every `user_id`-scoped route now requires `Depends(get_current_user)` plus
  `_require_self_or_admin()`, matching `api.py`'s `gdpr_erase()` pattern. Covered by
  `tests/test_tranquility_taimra_auth.py`.
- **Not fixed:** the unenforced I-Mind content-filtering claim — wiring a content-screening call
  before `record_interaction()` stores `topics` is a separate architectural change, out of scope
  for this auth fix.

## 4. RACI Matrix

| Activity | tAImra (Lead) | Platform Owner | I-Mind | Platform Engineering |
|---|---|---|---|---|
| Twin lifecycle logic changes | **R** | A | I | C |
| Wiring the I-Mind content-filtering guarantee (future) | C | **A** | **R** | C |

## 5. Solutions Integration Model (SIM)

- **Upstream:** any caller of `/taimra/*` routes except `/status` now requires
  `Depends(get_current_user)` plus the self-or-admin ownership check (see truthfulness
  header) — closed the previously-documented no-auth gap.
- **Downstream:** best-effort Observatory `observe()` on activate/deactivate/delete events. **No
  call to I-Mind** despite the module's own stated privacy guarantee referencing it.
- **Not integrated:** I-Mind (content filtering), and no verified integration with Infinity for
  identity/auth.

## 6. Architecture Scalability Document (ASD)

- **Load model:** in-memory `_twins` dict, no cap defined — unbounded growth, no eviction.
- **Bottleneck:** single-process, no persistence; a restart loses every user's twin state
  entirely, contradicting any expectation of a durable "digital twin."
- **Zero-cost limits:** no external dependency in this module.
- **Degradation:** Observatory emission failures are wrapped in `except Exception: pass` and
  don't block twin operations.

## 7. Deployment Scope Matrix (DSM)

- **Mode awareness:** No — this entity's own code does not call `PlatformInfraMode` / `src/platform/infrastructure_mode.py`. (Some platform-wide, cross-cutting code *does* branch on the mode — `src/routers/adaptive.py` and `src/routers/ecosystem.py` read/set `PLATFORM_INFRA_MODE`/`SYSTEM_MODE` directly, and `Dimensional/architecture/storage_factory.py` selects a storage provider from `SYSTEM_MODE` — but none of that code is owned by this or any other one of the 43 named entities; it is shared platform infrastructure, not this service's own logic. The Citadel is the only one of the 43 named entities whose own code branches on the mode — see `docs/services/the-citadel/README.md`.) This entity's deployment scope is determined externally — by which `docker-compose.production.yml` service block runs, and where — not by in-process mode detection.
- **Runtime placement:** **two independent surfaces**, not one — a router mounted in the `tranc3-backend` monolith (`api.py`) *and* a **separate standalone worker** (`taimra`, port 8074) with its own `docker-compose.production.yml` service block and its own Traefik route. **The standalone worker's Dockerfile previously only `COPY`'d a placeholder `main.py`** (the same deployed-stub-vs-undeployed-real defect found for The Academy/The Basement/The Studio) — **fixed**: it now builds and runs the real, more complete SQLite-backed `worker.py`, with a named volume (`taimra-data:/app/data`) added so its data survives redeploys.
- **Persistence:** split between the two surfaces — the monolith router's own state is an in-memory `_twins` dict (per this pack's own TFM/ASD); the standalone `taimra` worker (now that it actually runs `worker.py`) uses real SQLite, now backed by a named volume — genuinely durable across redeploys in every mode.

| Setup | What runs, and where | Data locality | Hard blockers / caveats |
|---|---|---|---|
| **Cloud-Only** | both surfaces run on a single cloud host (the monolith's `tranc3-backend` block and the standalone `taimra` block, now running the real `worker.py`); Traefik/edge in front for the standalone worker | monolith router ephemeral by design; standalone worker's SQLite now persists via its attached volume as long as the disk is preserved | none beyond standard single-host durability |
| **Hybrid** | same two surfaces; per `docs/architecture/infrastructure-modes.md`'s Hybrid diagram, the monolith's other data can sync to local TrueNAS, and the standalone `taimra` worker's SQLite volume can be synced the same way now that it exists | monolith ephemeral; worker's SQLite local-syncable | requires `CITADEL_LOCAL_STACK=true` if a local compose stack should run alongside the cloud one |
| **Local-Only** | same two surfaces, run entirely on local/Citadel hardware | monolith side still stateless by design; standalone worker fully local, volume-backed | none beyond standard local-hardware ops |

- **Zero-cost posture per mode:** Cloud-Only defaults to the `zero_cost_cloud` AI-rotation chain; Hybrid/Local-Only default to `zero_cost_full` (`config/platform/infrastructure_mode.yaml`) — this only affects AI-Gateway-routed calls, not this entity's own logic
- **Switching modes:** operator-level via `PLATFORM_INFRA_MODE` (or legacy `SYSTEM_MODE`); this entity needs no code change to move between modes, only a redeploy-target change for the monolith as a whole

## 8. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Web framework | FastAPI `APIRouter` | mounted into the main `api.py` app |
| Storage | in-memory `dict`, no persistence | zero infra cost, no durability |
| Personalization | simple incrementing affinity score | zero cost, no ML model |

## 9. Environment Support Matrix (ESM)

> Grounded against `docker-compose.development.yml` (6 services), `docker-compose.uat.yml` (16 services), and `docker-compose.production.yml` (286 services) — checked by exact compose service name, not assumed.

| Environment | Covered? | What runs | Notes |
|---|---|---|---|
| **Dev** | Partial | the `api` service in `docker-compose.development.yml` runs the monolith router — the standalone `taimra` worker is **not** in this compose file | standalone worker has zero Dev coverage |
| **UAT** | Partial | same monolith router via `api` in `docker-compose.uat.yml` — the standalone `taimra` worker is **not** in this compose file either | standalone worker has zero UAT coverage |
| **Production** | Yes | both surfaces — full detail in the DSM above | — |

- **Gap:** the standalone `taimra` worker (the more complete of this entity's two surfaces, per the DSM above) has **no Dev or UAT environment at all** — the first place it runs is Production. This is the norm for the ~90 standalone workers on this platform, not specific to this entity, but worth stating plainly rather than assuming pre-production validation exists where it doesn't.

## 10. Policy (POL)

- Every `user_id`-scoped route requires `Depends(get_current_user)` plus a self-or-admin
  ownership check — resolves the access-control half of the module's own "Governed by Trancendos
  Magna Carta policy" claim. The I-Mind content-filtering half remains unenforced (see DDD).
- Zero-cost mandate: no external dependency to audit against `scripts/zero_cost_audit.py`.

## 11. Procedure (PROC)

- **Activate a twin:** `POST /taimra/activate/{user_id}` (as the same user, or an admin) — sets status to `LEARNING`.
- **Record an interaction:** `POST /taimra/record/{user_id}` with `{"message", "topics",
  "personality_used"}` — no-op unless already activated; no content filtering applied.
- **Export or delete a twin:** `GET /taimra/export/{user_id}` / `DELETE /taimra/twin/{user_id}` —
  auth-gated; returns `403` unless the caller is that user or holds the `admin` role.

## 12. Runbook (RUN)

- **A user's twin data is missing after a restart:** expected — no persistence in this module.
- **`GET /taimra/twin/{user_id}` returns 404 for a user with recorded interactions elsewhere:**
  the twin must have been created via `activate()` first — `record_interaction()` is a no-op for
  a twin that was never activated.
- **A caller gets `403` on activate/export/delete:** expected — they are not the target
  `user_id` and do not hold the `admin` role; see POL §9.
- **Sensitive topics appear in a user's twin despite the "never stores I-Mind flagged content"
  claim:** expected — this guarantee is not enforced in code (see DDD).

## 13. Standards (STD)

- Naming: canonical entity name "tAimra" per `CLAUDE.md`/`PLATFORM_ENTITIES.md` (note the
  lowercase-t "tAimra" for the entity vs. capital-T "tAImra" for its Lead AI — both correct per
  `CLAUDE.md`'s own naming-rules section).
- Any privacy guarantee stated in a module's own header comment (e.g. "never stores I-Mind
  flagged content") MUST be backed by actual code before being repeated as fact in user-facing
  documentation — the access-control half of this is now backed by code; content-filtering is not.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-05 | Claude (session) | `src/taimra/digital_twin.py` (165 lines), `src/taimra/routes.py` (74 lines), `api.py` router registration (line 819) | Confirmed Live-tier, full pack authored. Verified the twin lifecycle state machine (OFFLINE→LEARNING→ACTIVE) and offline-by-default no-op behavior are real and correctly implemented. Major finding, documented not fixed: no auth on any route (including export/delete of another user's twin), and the module's own stated privacy guarantee ("never infers or stores sensitive I-Mind flagged content") has zero enforcement in code — no I-Mind import or call exists anywhere in this module. Also noted a dead `TwinStatus.PAUSED` enum member never assigned anywhere. |
| 2026-07-08 | Claude (session) | `src/taimra/routes.py` (109 lines, post-fix) | Closed the no-auth gap: every `user_id`-scoped route now requires `Depends(get_current_user)` plus `_require_self_or_admin()`, mirroring `api.py`'s `gdpr_erase()`. Verified via `tests/test_tranquility_taimra_auth.py`. The I-Mind content-filtering gap remains open — unchanged, unrelated to this fix. |
| 2026-07-09 | Claude (session) | `src/taimra/routes.py` (post-fix, renamed helper), `src/auth/tokens.py` | cubic correctly flagged that the initial fix's cross-user override checked `tier == "enterprise"`, but real JWTs (`src/auth/tokens.py`) carry `tier` as a numeric int and never that string — the override was dead for every real token. Renamed `_require_self_or_enterprise()` to `_require_self_or_admin()` and switched the check to `role == "admin"`, a claim real tokens do carry. Tests updated to assert real-shaped payloads. |
| 2026-07-11 | Claude (session, DSM/implementation pass) | `workers/taimra/Dockerfile`, `workers/taimra/main.py`, `workers/taimra/worker.py` | Found, while authoring the Deployment Scope Matrix, that `workers/taimra/` has the same deployed-stub-vs-undeployed-real defect previously found for The Academy/The Basement/The Studio: the Dockerfile only `COPY`'d a placeholder `main.py` (zero storage, hardcoded empty/placeholder responses) while a genuinely more complete SQLite-backed `worker.py` sat unused in the same directory. **Fixed this time** (unlike Academy's prior pass, this was caught and corrected in the same session rather than left for a follow-up): changed the Dockerfile to build/run `worker.py` and added a named volume (`taimra-data:/app/data`) to `docker-compose.production.yml`. DSM rewritten to reflect the fix. Note this is independent of the `src/taimra/digital_twin.py` monolith-router finding above (digital-twin lifecycle) — two separate surfaces, two separate fixes. |
