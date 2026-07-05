# Service Doc-Pack — I-Mind

| Field | Value |
|---|---|
| **Entity** | I-Mind |
| **Lead AI** | Elouise |
| **Status** | ✅ In repo (per `CLAUDE.md` service table) — Live tier |
| **Code** | `src/imind/protocol.py`, `src/imind/routes.py`; router registered in `api.py` (`app.include_router(_imind_router)`, line 814) |

> **Truthfulness:** claims cite `src/imind/protocol.py` and `src/imind/routes.py` directly. Status
> is owned by the `CLAUDE.md` service table; identity by `PLATFORM_ENTITIES.md`.
> **Bug found and fixed while authoring this pack:** the self-harm escalation branch compared
> `SensitivityLevel` **string enum values** with `<` (e.g. `"none" < "high"`), which is lexical
> string comparison, not severity ordering. Because `"none" > "high"` alphabetically, the guard
> was always false and self-harm detections never escalated the level past `NONE` — a real safety
> defect in crisis-detection logic. Fixed in this same change (see Verification Log) by removing
> the faulty guard, since the branch only runs when level is still `NONE` anyway.

## 1. Service Governance Charter (GOV)

- **Mission:** sensitivity-to-emotion engine — scans user messages for mental-health, crisis,
  self-harm, and safeguarding signals before inference, and injects response guidance / triggers
  human escalation.
- **Owner (RACI-A):** Elouise; Platform Owner Trancendos.
- **Scope:** regex-based text scanning, severity classification, AI response-modifier generation,
  and Observatory event emission for sensitive detections. No human escalation transport
  (notification, ticketing) is implemented in this module — `escalate: true` is a flag returned to
  the caller, not an action taken by I-Mind itself.

## 2. Detailed Design Document (DDD)

### HTTP surface (`src/imind/routes.py`, prefix `/imind`)

| Method | Route | Backing |
|---|---|---|
| GET | `/imind/status` | static `{"service": "i-mind", "status": "active"}` — not a real health probe |
| POST | `/imind/assess` | `IMind.assess(text, actor)` — 400 if `text` missing; returns `SensitivityAssessment.to_dict()` |

### Detection logic (`protocol.py`)
- **Crisis** (`_CRISIS_PATTERNS[0]`): suicide/self-harm-intent phrases (e.g. "kill myself", "want
  to die") → `SensitivityCategory.CRISIS`, `SensitivityLevel.CRITICAL`, immediately breaks out of
  further category checks for this call.
- **Self-harm** (`_CRISIS_PATTERNS[1:]`): "self-harm", "cut myself", "hurt myself" — only checked
  if CRISIS wasn't already matched → `SensitivityCategory.SELF_HARM`, `SensitivityLevel.HIGH`.
- **Mental health** (`_MENTAL_HEALTH_PATTERNS`): depression/anxiety/therapy-related terms →
  `SensitivityCategory.MENTAL_HEALTH`, `SensitivityLevel.MEDIUM` (only if level is still `NONE`).
- `escalate = level in (CRITICAL, HIGH)`.
- `response_modifier`: a hard-coded instruction string per level (CRITICAL includes UK Samaritans
  116 123 and US 988 Suicide & Crisis Lifeline numbers), intended to be prepended to the AI's
  system prompt/context by the caller — **I-Mind does not itself call any inference path**; it
  only returns the modifier string.

### Observatory emission (`_emit()`)
- Fires only if `level != NONE`.
- Event name: `f"imind.sensitivity.{level.value}"`.
- Severity: `EventSeverity.SECURITY` if `escalate`, else `EventSeverity.WARNING`.
- Wrapped in a bare `except Exception: pass` (`# nosec B110`) — emission failures never affect the
  assessment result returned to the caller.

## 3. Technical Architecture Solutions Design (TASD)

- **Style:** stateless regex-classification module with a module-level singleton (`get_imind()`);
  no persistence, no ML model — purely pattern-based.
- **Decision: regex over ML classification.** Zero-cost, zero-latency, fully deterministic and
  auditable — trades recall/precision against a trained classifier for simplicity and no inference
  cost. Documented as-is, not evaluated for accuracy in this pack.
- **Fixed defect:** the self-harm level-upgrade guard used enum-value string comparison
  (`level.value < SensitivityLevel.HIGH.value`) instead of a severity ordering — see truthfulness
  header. Removed the guard since the branch is unreachable with any prior level other than `NONE`.

## 4. RACI Matrix

| Activity | Elouise (Lead) | Platform Owner | The Observatory | Platform Engineering |
|---|---|---|---|---|
| Crisis/self-harm pattern changes | **R/A** | C | I | C |
| Response-modifier wording | **R** | A | I | I |
| Escalation transport (future) | C | **A** | I | **R** |

## 5. Solutions Integration Model (SIM)

- **Upstream:** any caller of `POST /imind/assess` — no auth on either route in `routes.py`.
- **Downstream:** The Observatory, via a best-effort `observe()` call (failures silently
  swallowed).
- **Auth boundary:** none — `/imind/status` and `/imind/assess` are both open.
- **Not integrated:** no confirmed caller of `IMind.assess()` from the inference pipeline
  (`src/core/tranc3_inference.py` or `src/ai_gateway/`) was found in this pass — the module exists
  and is routable, but whether it's actually invoked before every inference call (per its stated
  mission) is unverified. This is a real gap, not a claim either way.

## 6. Architecture Scalability Document (ASD)

- **Load model:** stateless per-request regex scan — trivially horizontally scalable, no shared
  state.
- **Bottleneck:** none identified — regex compilation happens once at module import.
- **Zero-cost limits:** no external dependency; regex-only.
- **Degradation:** Observatory emission failure doesn't block the assessment response.

## 7. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Web framework | FastAPI `APIRouter` | mounted into the main `api.py` app |
| Classification | Python `re` regex patterns | OSS, in-process, zero cost |
| Observability | Observatory `observe()` (best-effort) | in-process |

## 8. Policy (POL)

- No route-level auth currently implemented — see SIM §5.
- Crisis/self-harm detections MUST fire a SECURITY-severity Observatory event per mission intent —
  verified in code (`_emit`'s `EventSeverity.SECURITY if assessment.escalate`).

## 9. Procedure (PROC)

- **Assess text:** `POST /imind/assess` with `{"text": "...", "actor": "<optional>"}` — returns
  level, categories, escalate flag, and response modifier string.
- **Add a new crisis pattern:** append a compiled regex to `_CRISIS_PATTERNS` or
  `_MENTAL_HEALTH_PATTERNS` — no other code change needed.

## 10. Runbook (RUN)

- **Assessments never escalate for self-harm text:** this was the exact bug fixed in this pass
  (string-vs-severity comparison) — confirm the fix (removal of the `level.value <
  SensitivityLevel.HIGH.value` guard) is present in the deployed version if this recurs.
- **`/imind/assess` returns 400:** `text` field missing from the request body.
- **No Observatory event for a detection:** `_emit()` swallows exceptions silently — check The
  Observatory's own health, not this module.

## 11. Standards (STD)

- Naming: canonical entity name "I-Mind" per `CLAUDE.md`/`PLATFORM_ENTITIES.md`.
- Severity comparisons between `SensitivityLevel` members MUST use an explicit ordinal mapping or
  the enum's declaration order, never raw string (`.value`) comparison — the bug fixed here is the
  reason for this standard.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-05 | Claude (session) | `src/imind/protocol.py` (169 lines), `src/imind/routes.py` (28 lines), `api.py` router registration (line 814) | Confirmed Live-tier, full pack authored. Found and fixed a real bug: the self-harm level-upgrade check used string comparison (`level.value < SensitivityLevel.HIGH.value`) instead of severity ordering, so self-harm detections never actually escalated past `NONE`. Also flagged (not fixed, unverified): no confirmed caller of `IMind.assess()` from the inference pipeline was found — routable but integration into the actual chat flow is unconfirmed. |
