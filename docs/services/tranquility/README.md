# Service Doc-Pack — Tranquility

| Field | Value |
|---|---|
| **Entity** | Tranquility |
| **Lead AI** | Savania |
| **Status** | ✅ In repo (per `CLAUDE.md` service table) — Live tier |
| **Code** | `src/tranquility/wellbeing.py`, `src/tranquility/routes.py`; router registered in `api.py` (`app.include_router(_tranquility_router)`, line 826) — **plus a separate standalone worker**, `workers/tranquility/worker.py` (374 lines) not audited in detail by this pack |

> **Truthfulness:** claims cite `src/tranquility/wellbeing.py` and `src/tranquility/routes.py`
> directly. Status is owned by the `CLAUDE.md` service table; identity by `PLATFORM_ENTITIES.md`.
> **No auth on user wellbeing data — a materially sensitive gap.** Every route in
> `src/tranquility/routes.py` — including `GET /tranquility/export/{user_id}` (full mood-entry
> export) and `DELETE /tranquility/data/{user_id}` — takes `user_id` as a raw path parameter with
> **zero verification that the caller is that user or an authorized admin.** Any caller who knows
> or guesses a `user_id` string can read or delete another user's full mood-tracking history. This
> is more consequential here than most no-auth findings in this series, since the module's own
> header explicitly claims this data is "governed by Magna Carta + I-Mind protocols" — the
> data-sensitivity intent is stated, but the access control to back it is absent.
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
| GET | `/tranquility/export/{user_id}` | `Tranquility.export_user_data()` — full mood-entry export; **no auth** |
| DELETE | `/tranquility/data/{user_id}` | `Tranquility.delete_user_data()` — deletes the whole profile; **no auth** |

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
- **Not fixed:** the no-auth export/delete endpoints — adding real per-user auth is an
  architectural change (would need integration with Infinity's session/JWT layer) out of scope
  for a docs pass, but flagged as a materially sensitive gap given the data involved.

## 4. RACI Matrix

| Activity | Savania (Lead) | Platform Owner | I-Mind | Platform Engineering |
|---|---|---|---|---|
| Mood tracking / break-prompt logic changes | **R** | A | I | C |
| Wiring real per-user auth on export/delete (future) | C | **A** | I | **R** |
| Resonate / tAimra integration (future, currently unimplemented) | C | **A** | I | **R** |

## 5. Solutions Integration Model (SIM)

- **Upstream:** any caller of `/tranquility/*` routes — **no auth on any route**, most notably
  the export and delete endpoints (see truthfulness header).
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

## 7. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Web framework | FastAPI `APIRouter` | mounted into the main `api.py` app |
| Storage | in-memory `dict`, no persistence | zero infra cost, no durability |
| Cross-entity call | direct in-process call to `IMind.assess()` | zero cost |

## 8. Policy (POL)

- No route-level auth on any `/tranquility/*` route — see SIM §5. Given the module's own
  "governed by Magna Carta + I-Mind protocols" claim, this is a real compliance gap against that
  stated intent, not just a generic missing-auth finding.
- Zero-cost mandate: no external dependency to audit against `scripts/zero_cost_audit.py`.

## 9. Procedure (PROC)

- **Log a mood check-in:** `POST /tranquility/mood/{user_id}` with `{"mood": 1-5, "notes": "...",
  "tags": [...]}`. A `LOW`/`VERY_LOW` mood triggers an I-Mind assessment automatically.
- **Check for a break prompt:** `GET /tranquility/break/{user_id}` — returns `null` unless the
  session has exceeded 90 minutes or 100 messages since the last prompt.
- **Export or delete a user's data:** `GET /tranquility/export/{user_id}` / `DELETE
  /tranquility/data/{user_id}` — currently reachable by anyone who knows the `user_id`; no
  confirmation or ownership check.

## 10. Runbook (RUN)

- **A user's mood history is missing after a restart:** expected — no persistence in this module.
- **`GET /tranquility/profile/{user_id}` returns 404 for a user who has logged moods elsewhere:**
  check whether the profile was created via a route that calls `get_or_create()` — the profile
  route itself does not create one; see TASD code-quality note.
- **Sensitive mood data was exported/deleted by an unexpected caller:** expected given the current
  no-auth state — see POL §8; this is a genuine security gap, not a misconfiguration.

## 11. Standards (STD)

- Naming: canonical entity name "Tranquility" per `CLAUDE.md`/`PLATFORM_ENTITIES.md`.
- Any route exposing per-user personal data export or deletion MUST verify caller identity
  against the `user_id` in the path before this entity can be considered compliant with its own
  stated Magna Carta/I-Mind governance claim — the gap documented here is the reason for this
  standard.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-05 | Claude (session) | `src/tranquility/wellbeing.py` (179 lines), `src/tranquility/routes.py` (71 lines), `api.py` router registration (line 826) | Confirmed Live-tier, full pack authored. Verified a genuine, working cross-entity integration: `log_mood()` really calls `IMind.assess()` on low-mood entries. Major finding, documented not fixed: no auth on any route, most consequentially the full-history export and delete-all-data endpoints, which any caller can invoke for any `user_id` — a materially sensitive gap given the module's own "governed by Magna Carta + I-Mind protocols" claim. Also documented: two of the module's four stated capabilities (Resonate routing, tAimra burnout signals) are unimplemented comments only. |
