# Service Doc-Pack — Tranquility

| Field | Value |
|---|---|
| **Entity** | Tranquility |
| **Lead AI** | Savania |
| **Status** | ✅ In repo (per `CLAUDE.md` service table) — Live tier |
| **Code** | `src/tranquility/wellbeing.py`, `src/tranquility/routes.py`; router registered in `api.py` (`app.include_router(_tranquility_router)`, line 826) — **plus a separate standalone worker**, `workers/tranquility/worker.py` (374 lines) not audited in detail by this pack |

> **Truthfulness:** claims cite `src/tranquility/wellbeing.py` and `src/tranquility/routes.py`
> directly. Status is owned by the `CLAUDE.md` service table; identity by `PLATFORM_ENTITIES.md`.
> **Fixed:** every route in `src/tranquility/routes.py` taking a `user_id` path parameter now
> requires `Depends(get_current_user)` plus a `_require_self_or_admin()` ownership check
> (mirrors `api.py`'s `gdpr_erase()` pattern) — callers can only act on their own data unless they
> hold the `admin` role. `GET /tranquility/status` remains intentionally public (no per-user
> data). This closes the previously-documented gap where any caller who knew a `user_id` could
> read or delete another user's full mood-tracking history despite the module's own
> "governed by Magna Carta + I-Mind protocols" claim.
> **Two of four "Provides" claims in the module header are unimplemented.** "Routes to Resonate
> for empathy services" and "Burnout pattern detection (overuse signals from tAimra)" appear only
> as comments — no import of or call to Resonate or tAimra exists anywhere in `wellbeing.py`. The
> other two claims (mood check-in tracking, wellbeing score) are real and implemented.

## 1. Service Governance Charter (GOV)

- **Mission:** wellbeing hub — mood check-in tracking, session-length/message-volume-based break
  prompts, and (per stated but unimplemented intent) burnout detection and empathy routing.
- **Owner (RACI-A):** Savania; Platform Owner Trancendos.
- **Scope:** `src/tranquility/*` implements mood logging and break-prompt logic only. Resonate and
  tAimra integration, and any GDPR-grade access control on the export/delete endpoints, are not
  implemented — see truthfulness header.

## 2. Detailed Design Document (DDD)

### HTTP surface (`src/tranquility/routes.py`, prefix `/tranquility`)

| Method | Route | Backing |
|---|---|---|
| GET | `/tranquility/status` | `Tranquility.stats()` — total users, total mood entries |
| POST | `/tranquility/mood/{user_id}` | `Tranquility.log_mood()` — body `{"mood": 1-5, "notes", "tags"}`; 400 if `mood` missing |
| POST | `/tranquility/message/{user_id}` | `Tranquility.record_message()` — increments session message counter |
| GET | `/tranquility/break/{user_id}` | `Tranquility.get_break_prompt()` — returns a random mindfulness prompt if a break is due, else `null` |
| GET | `/tranquility/profile/{user_id}` | Reaches directly into `Tranquility()._profiles` (a private attribute) rather than a public getter — see TASD; 404 `JSONResponse` if no profile exists yet (unlike other routes, does **not** implicitly create one via `get_or_create()`) |
| GET | `/tranquility/export/{user_id}` | `Tranquility.export_user_data()` — full mood-entry export; auth-gated, self-or-admin |
| DELETE | `/tranquility/data/{user_id}` | `Tranquility.delete_user_data()` — deletes the whole profile; auth-gated, self-or-admin |

### Mood tracking and break logic (`wellbeing.py`) — real
- `MoodLevel` int enum (1–5); `log_mood()` clamps out-of-range input to the valid range rather
  than rejecting it (`max(1, min(5, mood))`), falling back to `NEUTRAL` only on a non-numeric
  value.
- `WellbeingProfile.needs_break()`: session > 90 minutes OR > 100 messages since the last break
  prompt — both counters reset on `get_break_prompt()` being called (not on the break actually
  being taken, which the module can't know).
- `average_mood()` — simple mean of the last 7 entries, defaulting to 3.0 (neutral) if none exist.

### Genuine I-Mind cross-entity call — real, not aspirational
- `log_mood()` calls `IMind.assess()` (`src/imind/protocol.py`) whenever a logged mood is
  `VERY_LOW` or `LOW`, passing `f"User reported mood: {mood_level.name}"` as the text to assess.
  This is a real, working cross-entity integration — confirmed by direct code read, consistent
  with the module header's "governed by ... I-Mind protocols" claim for this specific behavior
  (unlike the Resonate/tAimra claims, which are not backed by code).

### Unimplemented claims (module header vs. code)
- "Routes to Resonate for empathy services" — no `import` or call referencing Resonate anywhere
  in `src/tranquility/wellbeing.py`.
- "Burnout pattern detection (overuse signals from tAimra)" — no `import` or call referencing
  tAimra anywhere in this module. `needs_break()`'s session-length heuristic is the closest
  existing behavior, but it does not consume any tAimra signal.

## 3. Technical Architecture Solutions Design (TASD)

- **Style:** in-process module with a module-level singleton (`get_tranquility()`); in-memory
  `_profiles` dict, no persistence, no external DB.
- **Code-quality note:** `GET /tranquility/profile/{user_id}` accesses
  `get_tranquility()._profiles.get(user_id)` directly from `routes.py` — reaching into a private
  (`_`-prefixed) attribute of the singleton rather than calling a public method. This is also
  behaviorally inconsistent with the rest of the module: every other route implicitly creates a
  profile via `get_or_create()` on first access, but this one returns 404 instead, since it
  bypasses that method.
- **Fixed:** export/delete (and every other `user_id`-scoped route) now require
  `Depends(get_current_user)` plus the `_require_self_or_admin()` ownership check, matching
  `api.py`'s `gdpr_erase()` pattern. Covered by `tests/test_tranquility_taimra_auth.py`.

## 4. RACI Matrix

| Activity | Savania (Lead) | Platform Owner | I-Mind | Platform Engineering |
|---|---|---|---|---|
| Mood tracking / break-prompt logic changes | **R** | A | I | C |
| Resonate / tAimra integration (future, currently unimplemented) | C | **A** | I | **R** |

## 5. Solutions Integration Model (SIM)

- **Upstream:** any caller of `/tranquility/*` routes except `/status` now requires
  `Depends(get_current_user)` plus the self-or-admin ownership check (see truthfulness
  header) — closed the previously-documented no-auth gap.
- **Downstream:** genuinely calls `IMind.assess()` on low/very-low mood entries; best-effort
  Observatory `observe()` on mood-logged events.
- **Not integrated:** Resonate, tAimra — both named in the module's own mission comment but never
  called.

## 6. Architecture Scalability Document (ASD)

- **Load model:** in-memory `_profiles` dict, no cap defined — unbounded growth, no eviction.
- **Bottleneck:** single-process, no persistence; a restart loses all mood history for every user.
- **Zero-cost limits:** no external dependency in this module.
- **Degradation:** Observatory emission and I-Mind assessment calls are both wrapped in
  `except Exception: pass` — failures don't block mood logging.

## 7. Deployment Scope Matrix (DSM)

- **Mode awareness:** No — this entity's own code does not call `PlatformInfraMode` / `src/platform/infrastructure_mode.py`. (Some platform-wide, cross-cutting code *does* branch on the mode — `src/routers/adaptive.py` and `src/routers/ecosystem.py` read/set `PLATFORM_INFRA_MODE`/`SYSTEM_MODE` directly, and `Dimensional/architecture/storage_factory.py` selects a storage provider from `SYSTEM_MODE` — but none of that code is owned by this or any other one of the 43 named entities; it is shared platform infrastructure, not this service's own logic. The Citadel is the only one of the 43 named entities whose own code branches on the mode — see `docs/services/the-citadel/README.md`.) This entity's deployment scope is determined externally — by which `docker-compose.production.yml` service block runs, and where — not by in-process mode detection.
- **Runtime placement:** **two independent surfaces**, not one — a router mounted in the `tranc3-backend` monolith (`api.py`) *and* a **separate standalone worker** with its own `docker-compose.production.yml` service block (`tranquility`, port 8077) and its own Traefik route; the standalone worker is a distinct, more complete SQLite-backed reimplementation, not the same code deployed twice (confirmed by reading both — this matches the "two independent implementations" pattern already documented for several other entities in this platform's doc-pack series).
- **Persistence:** split between the two surfaces — this entity's own state is an in-memory `_profiles` dict (per this pack's own TFM/ASD) on the monolith side, with no persistence of its own; the standalone `tranquility` worker uses real SQLite (`import sqlite3`), but its compose service has **no named volume attached**, so its SQLite file lives on the container's ephemeral filesystem and is still lost on redeploy in every mode — a real durability gap in the standalone worker specifically, distinct from the monolith router's by-design statelessness.

| Setup | What runs, and where | Data locality | Hard blockers / caveats |
|---|---|---|---|
| **Cloud-Only** | both surfaces run on a single cloud host (the monolith's `tranc3-backend` block and the standalone `tranquility` block); Traefik/edge in front for the standalone worker | ephemeral for both — the monolith router holds no state of its own, and the standalone worker's SQLite has no volume to survive a redeploy | no entity-specific blocker beyond the standalone worker's missing volume |
| **Hybrid** | same two surfaces; per `docs/architecture/infrastructure-modes.md`'s Hybrid diagram, the monolith's other data can sync to local TrueNAS, but this does not help the standalone `tranquility` worker's SQLite file since it has no volume to sync from | as above — neither surface benefits from the Hybrid data-locality split | requires `CITADEL_LOCAL_STACK=true` if a local compose stack should run alongside the cloud one |
| **Local-Only** | same two surfaces, run entirely on local/Citadel hardware | monolith side still stateless by design; the standalone `tranquility` worker's SQLite file is still lost on restart/redeploy since no volume is attached, even on local hardware | adding a named volume to the `tranquility` compose service would fix this in any mode — it is not currently mode-specific |

- **Zero-cost posture per mode:** Cloud-Only defaults to the `zero_cost_cloud` AI-rotation chain; Hybrid/Local-Only default to `zero_cost_full` (`config/platform/infrastructure_mode.yaml`) — this only affects AI-Gateway-routed calls, not this entity's own logic
- **Switching modes:** operator-level via `PLATFORM_INFRA_MODE` (or legacy `SYSTEM_MODE`); this entity needs no code change to move between modes, only a redeploy-target change for the monolith as a whole

## 8. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Web framework | FastAPI `APIRouter` | mounted into the main `api.py` app |
| Storage | in-memory `dict`, no persistence | zero infra cost, no durability |
| Cross-entity call | direct in-process call to `IMind.assess()` | zero cost |

## 9. Policy (POL)

- Every `user_id`-scoped route requires `Depends(get_current_user)` plus a self-or-admin
  ownership check — resolves the compliance gap against the module's own "governed by Magna
  Carta + I-Mind protocols" claim. `GET /status` remains intentionally public.
- Zero-cost mandate: no external dependency to audit against `scripts/zero_cost_audit.py`.

## 10. Procedure (PROC)

- **Log a mood check-in:** `POST /tranquility/mood/{user_id}` (as the same user, or an admin) with `{"mood": 1-5, "notes": "...", "tags": [...]}`. A `LOW`/`VERY_LOW`
  mood triggers an I-Mind assessment automatically.
- **Check for a break prompt:** `GET /tranquility/break/{user_id}` — returns `null` unless the
  session has exceeded 90 minutes or 100 messages since the last prompt.
- **Export or delete a user's data:** `GET /tranquility/export/{user_id}` / `DELETE
  /tranquility/data/{user_id}` — auth-gated; returns `403` unless the caller is that user or holds
  the `admin` role.

## 11. Runbook (RUN)

- **A user's mood history is missing after a restart:** expected — no persistence in this module.
- **`GET /tranquility/profile/{user_id}` returns 404 for a user who has logged moods elsewhere:**
  check whether the profile was created via a route that calls `get_or_create()` — the profile
  route itself does not create one; see TASD code-quality note.
- **A caller gets `403` on export/delete:** expected — they are not the target `user_id` and do
  not hold the `admin` role; see POL §9.

## 12. Standards (STD)

- Naming: canonical entity name "Tranquility" per `CLAUDE.md`/`PLATFORM_ENTITIES.md`.
- Any route exposing per-user personal data export or deletion MUST verify caller identity
  against the `user_id` in the path — now enforced via `Depends(get_current_user)` +
  `_require_self_or_admin()`, consistent with `api.py`'s `gdpr_erase()`.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-05 | Claude (session) | `src/tranquility/wellbeing.py` (179 lines), `src/tranquility/routes.py` (71 lines), `api.py` router registration (line 826) | Confirmed Live-tier, full pack authored. Verified a genuine, working cross-entity integration: `log_mood()` really calls `IMind.assess()` on low-mood entries. Major finding, documented not fixed: no auth on any route, most consequentially the full-history export and delete-all-data endpoints, which any caller can invoke for any `user_id` — a materially sensitive gap given the module's own "governed by Magna Carta + I-Mind protocols" claim. Also documented: two of the module's four stated capabilities (Resonate routing, tAimra burnout signals) are unimplemented comments only. |
| 2026-07-08 | Claude (session) | `src/tranquility/routes.py` (102 lines, post-fix) | Closed the no-auth gap: every `user_id`-scoped route now requires `Depends(get_current_user)` plus `_require_self_or_admin()`, mirroring `api.py`'s `gdpr_erase()`. Verified via `tests/test_tranquility_taimra_auth.py` (own-data access, cross-user 403, admin override, unauthenticated 401/403). |
| 2026-07-09 | Claude (session) | `src/tranquility/routes.py` (post-fix, renamed helper), `src/auth/tokens.py` | cubic correctly flagged that the initial fix's cross-user override checked `tier == "enterprise"`, but real JWTs (`src/auth/tokens.py`) carry `tier` as a numeric int and never that string — the override was dead for every real token. Renamed `_require_self_or_enterprise()` to `_require_self_or_admin()` and switched the check to `role == "admin"`, a claim real tokens do carry, matching the admin-check convention already used elsewhere (`api.py`'s `ai_provider_reset`, Cryptex's `_require_admin`). Tests updated to assert real-shaped payloads. |
