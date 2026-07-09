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

## 7. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Web framework | FastAPI `APIRouter` | mounted into the main `api.py` app |
| Storage | in-memory `dict`, no persistence | zero infra cost, no durability |
| Personalization | simple incrementing affinity score | zero cost, no ML model |

## 8. Policy (POL)

- Every `user_id`-scoped route requires `Depends(get_current_user)` plus a self-or-admin
  ownership check — resolves the access-control half of the module's own "Governed by Trancendos
  Magna Carta policy" claim. The I-Mind content-filtering half remains unenforced (see DDD).
- Zero-cost mandate: no external dependency to audit against `scripts/zero_cost_audit.py`.

## 9. Procedure (PROC)

- **Activate a twin:** `POST /taimra/activate/{user_id}` (as the same user, or an admin) — sets status to `LEARNING`.
- **Record an interaction:** `POST /taimra/record/{user_id}` with `{"message", "topics",
  "personality_used"}` — no-op unless already activated; no content filtering applied.
- **Export or delete a twin:** `GET /taimra/export/{user_id}` / `DELETE /taimra/twin/{user_id}` —
  auth-gated; returns `403` unless the caller is that user or holds the `admin` role.

## 10. Runbook (RUN)

- **A user's twin data is missing after a restart:** expected — no persistence in this module.
- **`GET /taimra/twin/{user_id}` returns 404 for a user with recorded interactions elsewhere:**
  the twin must have been created via `activate()` first — `record_interaction()` is a no-op for
  a twin that was never activated.
- **A caller gets `403` on activate/export/delete:** expected — they are not the target
  `user_id` and do not hold the `admin` role; see POL §8.
- **Sensitive topics appear in a user's twin despite the "never stores I-Mind flagged content"
  claim:** expected — this guarantee is not enforced in code (see DDD).

## 11. Standards (STD)

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
