# Service Doc-Pack — tAimra

| Field | Value |
|---|---|
| **Entity** | tAimra |
| **Lead AI** | tAImra |
| **Status** | ✅ In repo (per `CLAUDE.md` service table) — Live tier |
| **Code** | `src/taimra/digital_twin.py`, `src/taimra/routes.py`; router registered in `api.py` (`app.include_router(_taimra_router)`, line 819) — **plus a separate standalone worker**, `workers/taimra/worker.py` not audited in detail by this pack |

> **Truthfulness:** claims cite `src/taimra/digital_twin.py` and `src/taimra/routes.py` directly.
> Status is owned by the `CLAUDE.md` service table; identity by `PLATFORM_ENTITIES.md`.
> **No auth on any route — including activate, export, and delete of a user's digital twin.**
> Every route takes `user_id` as a raw path parameter with zero verification that the caller is
> that user. Any caller who knows or guesses a `user_id` string can activate/deactivate another
> user's twin, record fabricated interactions into it, export its full contents, or permanently
> delete it. This is the same class of gap found in Tranquility (this session, same batch), but
> arguably more consequential here given the module's own stated privacy guarantees.
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
  delete) with in-memory storage. The I-Mind content-filtering guarantee described in the
  module's own comments is not implemented — see truthfulness header.

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
| GET | `/taimra/export/{user_id}` | `TAimra.export()` — full twin data (GDPR portability, per comment); 404 if missing |
| DELETE | `/taimra/twin/{user_id}` | `TAimra.delete()` — full erasure (GDPR right to erasure, per comment); 404 if missing |

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
- "Governed by Trancendos Magna Carta policy" — no route-level auth exists to back this claim in
  practice (see truthfulness header); Magna Carta governance is not verifiable from this code
  alone.
- The GDPR export/erasure functions (`export()`, `delete()`) are real and functionally correct in
  isolation, but since no auth gates who can call them for a given `user_id`, they don't actually
  deliver GDPR-compliant self-service data rights as currently wired — anyone could trigger
  another user's "right to erasure" without that user's involvement.

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
- **Not fixed:** no-auth routes and the unenforced I-Mind content-filtering claim — both require
  architectural decisions (real per-user auth; a content-screening call before storage) out of
  scope for a docs pass, but flagged clearly given the module's own explicit privacy promises.

## 4. RACI Matrix

| Activity | tAImra (Lead) | Platform Owner | I-Mind | Platform Engineering |
|---|---|---|---|---|
| Twin lifecycle logic changes | **R** | A | I | C |
| Wiring real per-user auth (future) | C | **A** | I | **R** |
| Wiring the I-Mind content-filtering guarantee (future) | C | **A** | **R** | C |

## 5. Solutions Integration Model (SIM)

- **Upstream:** any caller of `/taimra/*` routes — **no auth on any route**, including
  activate/export/delete of another user's twin data (see truthfulness header).
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

- No route-level auth on any `/taimra/*` route — see SIM §5; materially sensitive given this
  module's own "Governed by Trancendos Magna Carta policy" and I-Mind-filtering claims.
- Zero-cost mandate: no external dependency to audit against `scripts/zero_cost_audit.py`.

## 9. Procedure (PROC)

- **Activate a twin:** `POST /taimra/activate/{user_id}` — sets status to `LEARNING`.
- **Record an interaction:** `POST /taimra/record/{user_id}` with `{"message", "topics",
  "personality_used"}` — no-op unless already activated; no content filtering applied.
- **Export or delete a twin:** `GET /taimra/export/{user_id}` / `DELETE /taimra/twin/{user_id}` —
  currently reachable by anyone who knows the `user_id`.

## 10. Runbook (RUN)

- **A user's twin data is missing after a restart:** expected — no persistence in this module.
- **`GET /taimra/twin/{user_id}` returns 404 for a user with recorded interactions elsewhere:**
  the twin must have been created via `activate()` first — `record_interaction()` is a no-op for
  a twin that was never activated.
- **Twin data was exported/deleted/activated by an unexpected caller:** expected given the
  current no-auth state — see POL §8; a genuine security/privacy gap, not a misconfiguration.
- **Sensitive topics appear in a user's twin despite the "never stores I-Mind flagged content"
  claim:** expected — this guarantee is not enforced in code (see DDD).

## 11. Standards (STD)

- Naming: canonical entity name "tAimra" per `CLAUDE.md`/`PLATFORM_ENTITIES.md` (note the
  lowercase-t "tAimra" for the entity vs. capital-T "tAImra" for its Lead AI — both correct per
  `CLAUDE.md`'s own naming-rules section).
- Any privacy guarantee stated in a module's own header comment (e.g. "never stores I-Mind
  flagged content") MUST be backed by actual code before being repeated as fact in user-facing
  documentation — the gap documented here is the reason for this standard.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-05 | Claude (session) | `src/taimra/digital_twin.py` (165 lines), `src/taimra/routes.py` (74 lines), `api.py` router registration (line 819) | Confirmed Live-tier, full pack authored. Verified the twin lifecycle state machine (OFFLINE→LEARNING→ACTIVE) and offline-by-default no-op behavior are real and correctly implemented. Major finding, documented not fixed: no auth on any route (including export/delete of another user's twin), and the module's own stated privacy guarantee ("never infers or stores sensitive I-Mind flagged content") has zero enforcement in code — no I-Mind import or call exists anywhere in this module. Also noted a dead `TwinStatus.PAUSED` enum member never assigned anywhere. |
