# Service Doc-Pack — Resonate

| Field | Value |
|---|---|
| **Entity** | Resonate |
| **Lead AI** | Magdalena |
| **Status** | ✅ In repo (per `CLAUDE.md` service table) — Live tier |
| **Code** | `src/resonate/empathy.py`, `src/resonate/routes.py`; router registered in `api.py` (`app.include_router(_resonate_router)`, line 833) — **plus a separate standalone worker**, `workers/resonate/worker.py` not audited in detail by this pack |

> **Truthfulness:** claims cite `src/resonate/empathy.py` and `src/resonate/routes.py` directly.
> Status is owned by the `CLAUDE.md` service table; identity by `PLATFORM_ENTITIES.md`.
> **`escalate_to_human()`'s return message is misleading — it claims an action that does not
> happen.** The method's own docstring is honest: "In production this would trigger a
> notification to the support team" (present-conditional, i.e. not yet real). But the value it
> **returns to the caller** states as fact: `"message": "A support team member has been
> notified. You are not alone."` No notification transport exists anywhere in this module or
> `routes.py` — the only side effect is a best-effort Observatory `SECURITY`-severity event
> (wrapped in `except Exception: pass`) and a `logger.warning()` call. If this response string is
> ever surfaced to an end user in crisis, it tells them something false: that a human has been
> notified, when nothing has notified anyone. This is a more serious instance of the "escalate:
> true is a flag, not an action" pattern already documented for The Studio and I-Mind in this
> series — here the gap is compounded by an affirmatively false user-facing claim, not just an
> unactioned flag.
> **No confirmed caller in the real inference pipeline**, matching I-Mind's own documented gap:
> `get_resonate()` has no caller outside `src/resonate/*` and `api.py`'s router mount — no
> evidence `wrap_response()` or `escalate_to_human()` is invoked from
> `src/core/tranc3_inference.py` or `src/ai_gateway/` before every real response, despite the
> module's stated mission of wrapping AI-generated responses with empathetic framing.

## 1. Service Governance Charter (GOV)

- **Mission:** empathy service layer — wraps AI response text with empathetic framing based on
  I-Mind sensitivity level or Tranquility mood signals, and provides a human-escalation flag.
- **Owner (RACI-A):** Magdalena; Platform Owner Trancendos.
- **Scope:** `src/resonate/*` — text wrapping and an escalation-flagging function. No actual
  human-notification transport, and no confirmed wiring into the real inference response path.

## 2. Detailed Design Document (DDD)

### HTTP surface (`src/resonate/routes.py`, prefix `/resonate`)

| Method | Route | Backing |
|---|---|---|
| GET | `/resonate/status` | `Resonate.stats()` — static `{"service": "resonate", "status": "active"}`, not a real health probe |
| POST | `/resonate/wrap` | `Resonate.wrap_response()` — body `{"response", "sensitivity_level", "user_mood", "crisis_resources"}`; 400 if `response` missing |
| POST | `/resonate/escalate/{user_id}` | `Resonate.escalate_to_human()` — body `{"context"}`; returns the misleading "notified" message described in the truthfulness header |

### `wrap_response()` — real, deterministic text wrapping
- No-op (returns input unchanged) when `sensitivity_level == "none"` and `user_mood` is `None` or
  `>= 3` — a real, correct short-circuit.
- CRITICAL/HIGH sensitivity → prepends a random empathy prefix; MEDIUM or `user_mood <= 2` →
  prepends a narrower empathy-prefix subset. `crisis_resources=True` appends the exact same UK
  Samaritans (116 123) / US 988 Suicide & Crisis Lifeline text block cited in I-Mind's own
  `response_modifier` for CRITICAL — consistent phrasing between the two entities, not verified
  in this pass whether that's by shared constant or independent duplication (appears to be the
  latter — no shared import between `src/imind/protocol.py` and this file).
- This function is real, working, unit-testable logic — the defect is entirely in
  `escalate_to_human()`, not here.

### `escalate_to_human()` — the misleading-message finding
- See truthfulness header. The fix, if made, would be either (a) implementing a real notification
  transport (Slack/email/PagerDuty-style — an infrastructure decision out of scope for a docs
  pass), or (b) at minimum changing the returned message to not claim an action that didn't
  happen (e.g. "Your message has been logged for review" instead of "A support team member has
  been notified"). Neither was code-fixed in this pass — flagged as the most safety-relevant
  finding in this doc-pack batch given it's an active user-facing crisis-support claim.

## 3. Technical Architecture Solutions Design (TASD)

- **Style:** in-process module with a module-level singleton (`get_resonate()`); fully stateless
  — no storage of any kind, unlike most other entities in this series.
- **Decision (implicit): text-transformation layer, not a decision engine.** `wrap_response()`
  takes `sensitivity_level`/`user_mood` as caller-supplied parameters rather than computing them
  itself — same "caller-driven, not self-triggered" pattern documented in VRAR3D's doc-pack this
  session. Resonate does not call I-Mind or Tranquility itself.
- **Not fixed:** the misleading escalation message and the unconfirmed inference-pipeline wiring
  — both require decisions beyond a docs pass (real notification infra; confirming/adding the
  actual call site).

## 4. RACI Matrix

| Activity | Magdalena (Lead) | Platform Owner | I-Mind | Platform Engineering |
|---|---|---|---|---|
| Empathy-wrapping logic changes | **R** | A | I | C |
| Fixing the misleading escalation message (recommended, not yet actioned) | **R** | **A** | I | I |
| Implementing real human-notification transport (future) | C | **A** | I | **R** |
| Confirming/wiring `wrap_response()` into the real inference path (future) | C | **A** | C | **R** |

## 5. Solutions Integration Model (SIM)

- **Upstream:** any caller of `/resonate/*` routes — no auth on any route.
- **Downstream:** best-effort Observatory `observe()` on escalation only (not on every
  `wrap_response()` call).
- **Not integrated:** no confirmed caller of `wrap_response()`/`escalate_to_human()` from the real
  inference pipeline was found in this pass — routable but integration into the actual chat flow
  is unverified, the same honest gap documented for I-Mind. No real human-notification transport
  (Slack/email/PagerDuty/etc.) exists anywhere in this repo for `escalate_to_human()` to call.

## 6. Architecture Scalability Document (ASD)

- **Load model:** fully stateless, no storage — trivially horizontally scalable.
- **Bottleneck:** none identified — pure text transformation.
- **Zero-cost limits:** no external dependency.
- **Degradation:** Observatory emission failure on escalation is wrapped in
  `except Exception: pass` and explicitly does not block the (already-hollow) escalation
  response.

## 7. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Web framework | FastAPI `APIRouter` | mounted into the main `api.py` app |
| Text wrapping | Python string templating + `random.choice` | OSS, in-process, zero cost |
| Human notification (missing) | none | N/A — not implemented anywhere in this repo |

## 8. Policy (POL)

- No route-level auth on any `/resonate/*` route.
- **Policy gap:** any user-facing message claiming a human action ("notified") MUST correspond to
  a real action, or be reworded to avoid the false claim — `escalate_to_human()` currently
  violates this and should be prioritized for correction ahead of most other findings in this
  doc-pack series, given the crisis-support context.

## 9. Procedure (PROC)

- **Wrap a response with empathetic framing:** `POST /resonate/wrap` with `{"response": "...",
  "sensitivity_level": "high", "crisis_resources": true}`.
- **Flag a human escalation:** `POST /resonate/escalate/{user_id}` with `{"context": "..."}` —
  currently only logs and emits an Observatory event; does not notify anyone despite its response
  message.

## 10. Runbook (RUN)

- **A user was told "a support team member has been notified" but no one responded:** this is
  expected given the current implementation — no notification transport exists. This is the
  single most important finding in this pack; escalate to product/eng ownership (Magdalena /
  Platform Owner) for prioritization, not merely a documentation note.
- **`wrap_response()` doesn't seem to run on real chat responses:** expected if nothing in the
  inference pipeline calls it — see SIM's unconfirmed-integration note (same class of gap as
  I-Mind).

## 11. Standards (STD)

- Naming: canonical entity name "Resonate" per `CLAUDE.md`/`PLATFORM_ENTITIES.md`.
- Any function whose return value is shown to an end user and claims a real-world action (e.g.
  "notified", "escalated", "alerted") MUST only make that claim if the action genuinely occurs —
  the `escalate_to_human()` finding here is the reason for this standard, and it applies
  platform-wide, not just to this entity.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-05 | Claude (session) | `src/resonate/empathy.py` (119 lines), `src/resonate/routes.py` (41 lines), `api.py` router registration (line 833) | Confirmed Live-tier, full pack authored. Verified `wrap_response()` is real, correct, deterministic logic. Major finding, the most safety-relevant in this doc-pack batch: `escalate_to_human()` returns a user-facing message claiming "A support team member has been notified" when no notification transport exists anywhere in the repo — only a best-effort Observatory event and a log line occur. Flagged for prioritized correction, not merely documented as a routine gap. Also confirmed, matching I-Mind's own documented pattern: no caller of this module was found in the real inference pipeline. |
