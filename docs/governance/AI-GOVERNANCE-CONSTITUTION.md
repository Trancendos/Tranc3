---
title: "AI Governance Constitution"
category: Reference
last-reviewed: 2026-08-07
status: needs-update
---

# AI Governance Constitution

> **What this is.** A response to a real, owner-raised question: should Trancendos have a formal
> governing document ("oath" / "constitution") for its ~40 named AIs, with machine-enforceable
> per-agent charters, escalation rules, and a JSON Schema policy pack? Short answer: partly built
> already, partly a genuine gap. This doc (1) reconciles a tier-naming ambiguity the owner asked to
> resolve, (2) defines the per-agent charter schema and escalation model that's genuinely missing,
> and (3) is explicit about what's real today vs. designed-but-not-yet-enforced — following the
> same honesty discipline as `HARD-STOP-MATRIX.md` and `OBSERVABILITY-AND-AUTOMATION-GOVERNANCE.md`.
>
> **This is not a new governance system competing with Magna Carta.** Magna Carta
> (`compliance/magna-carta/FRAMEWORK.md`) already is the platform's constitution — a 6-layer
> pyramid (Governance&Rights → Policies → Procedures → Compliance&Regs → Architecture&Controls →
> Evidence&Assurance) with 7 core digital-rights principles that already cover truthfulness,
> traceability, human oversight, and accountability. This doc fills the two pieces Magna Carta
> doesn't yet have: a per-agent action-level charter, and a unified escalation state machine. Both
> are designed to plug into Magna Carta's existing machinery (CAB Gate, Observatory, `ai_governance.py`),
> not replace it.

**Owner:** Platform Owner Trancendos · **Version:** 1.2.0 · **Status:** Phase 3 landed (terminology,
schema, a real escalation FSM with 11 seed charters, and both Tier 4/5 dispatch call sites now
actually route through it — see §3.5) · **Last verified:** 2026-08-06

---

## 1. Tier terminology reconciliation

### 1.1 The ambiguity

Two tier vocabularies exist in this codebase and, until now, were deliberately left unreconciled
(`CLAUDE.md`'s AeonMind naming rule: *"Do not conflate its Tier 0–5 vocabulary with
`PLATFORM_ENTITIES.md`'s own Tier 1–5... note `docs/architecture/infrastructure-modes.md`
separately calls Tier 5 'Nanos', a third, minor naming variant not resolved here"*):

| | AeonMind (`aeonmind/docs/AI_DEFINITIONS_DICTIONARY.md`) | Platform (`PLATFORM_ENTITIES.md`, `src/entities/platform.py`) |
|---|---|---|
| Vocabulary | Tier 0 HUMAN → 1 ORCHESTRATOR → 2 PRIME → 3 AI → 4 AGENT → 5 BOT | Tier 1 Sovereign → 2 Primes → 3 Lead AI → 4 Agents → 5 Bots (no Tier 0) |
| What it defines | Generic **behavioral semantics** — autonomy level, state model, confidence scoring, what each tier is *allowed to do* | **Identity** — the 43 named platform entities, their live HTTP surfaces, their base model tier |
| Deployment status | Not deployed — no `docker-compose.production.yml` service; only a thin bridge (`src/routers/aeonmind.py`) is live | Fully live — `/sovereign` (`trance_one/`), `/primes` (`t2ance/`), `/models`, `/roles`, all 43 entities |

### 1.2 The resolution

Per owner direction (2026-08-06): **AeonMind's tier *definitions* are canonical going forward** for
governance purposes. This is adopted as a **semantic overlay, not a rename** — the live naming
(Sovereign/Primes/Lead AI/Agents/Bots, Trance-One/T2ance/Tranc3) stays exactly as-is in code,
routes, and the 43-entity table, because it is load-bearing across dozens of live files and HTTP
surfaces that a rename would put at real risk for no governance benefit.

The mapping:

| AeonMind Tier | Platform equivalent | Notes |
|---|---|---|
| 0 — HUMAN | *(previously unnamed)* | AeonMind genuinely fills a gap here — the platform has human authority (Governance Board, CAB approvers) but no single named "Tier 0" concept until now |
| 1 — ORCHESTRATOR | Sovereign / Trance-One | Cornelius MacIntyre, The Queen, tAImra — the 3 cross-cutting Orchestrators |
| 2 — PRIME | Primes / T2ance | The 9 `PrimeDomain`s (ArchPrime, CommPrime, CreatePrime, DevPrime, KnowPrime, SecPrime, WellPrime, GovPrime, OpsPrime — `t2ance/domain_authority.py`) |
| 3 — AI | Lead AI / Tranc3 | The default tier for every named AI not elevated above — ~40 of the 43 entities |
| 4 — AGENT | Agents (`agent_alpha`/`agent_beta`, `agent_teams`) | **Correction to the brainstorm this doc responds to, refined 2026-08-06**: every one of the 43 Locations has exactly 2 base Agents (`agent_alpha`, `agent_beta` — non-optional fields on `LocationEntity`, confirmed by grep: 43/43). For the 39 single-AI Locations that base pair *is* effectively "2 agents per AI." The uneven part is `agent_teams`, populated for only 4 Locations (TateKing, Arcadian Exchange, The Lab, Infinity) where the primary named AI reuses the Location's base pair and every additional named AI gets its own dedicated pair on top of that — so "every AI (at name granularity, ~40 of them) owns exactly 2 agents" still doesn't hold platform-wide, but "every Location owns exactly 2" does |
| 5 — BOT | Bots (`bot_01`–`bot_04`, `BotRegistry`) | **Correction, refined 2026-08-06**: two distinct things, neither is 6. `platform.py` gives every one of the 43 Locations exactly 4 uniquely-flavored Bot entities (`bot_01`–`bot_04`, e.g. Ping-Bot/Ack-Bot/Syn-Bot/Fin-Bot — confirmed by grep: 172 = 43×4, no Location has 5+). Separately, `tranc3-bots/bots/registry.py`'s `BotRegistry` dispatches 12 functional bot *types*, shared platform-wide — not owned per-AI or per-Location at all |

**What AeonMind's definitions add that the platform naming never specified**: autonomy semantics per
tier (a Bot has zero decision-making capability and no state; an Agent has delegated autonomy
bounded by a confidence threshold ≥0.5; an AI Complex coordinates Agents/Bots and reports to a
Prime or Orchestrator) — these become the *behavioral contract* each charter in §2 is written
against.

**What stays exactly as documented in `CLAUDE.md`**: entity identity, canonical names, HTTP routes,
the Trance-One/T2ance/Tranc3 model matrix, and the governed advancement pipeline (Prime → Cornelius
→ Human). None of that changes.

---

## 2. Per-agent charter schema

### 2.1 Why not the brainstormed "2 agents + 6 bots, one charter per AI" model

The originating brainstorm's numbers were partly right: every Location genuinely does have 2 base
Agents (see §1.2's corrected row — that part of the brainstorm holds at Location granularity). The
"6 bots" figure was never right in either sense the code actually has (4 named per Location, or 12
shared types platform-wide), and `agent_teams`'s extra per-name pairs for 4 Locations mean the ratio
isn't uniform at AI-name granularity either. More fundamentally, "one charter per AI" doesn't hold
regardless of the ownership numbers: a single 40-entity charter list would just duplicate
`PLATFORM_ENTITIES.md` rather than add anything. Instead, charters are scoped to **capability
classes** shared across entities at the same tier — much closer to how `t2ance/domain_authority.py`
already governs entities by `PrimeDomain` rather than one-off per entity.

### 2.2 Schema

Draft 2020-12, same standard the earlier brainstorm correctly identified. Lives at
`docs/governance/schemas/agent-charter.schema.json` (companion file to this doc). Deliberately
reuses existing platform vocabulary instead of inventing parallel enums:

- `tier` — the AeonMind tier (0–5) this charter applies to, reconciled per §1.2.
- `risk_tier` — reuses `ai_governance.py`'s existing `RiskTier` enum (`unacceptable` / `high` /
  `limited` / `minimal` — EU AI Act Annex III / Art. 6), not a new risk vocabulary.
- `approval_required` — boolean; when true, the action must clear **CAB Gate**
  (`src/compliance/cab_gate.py`, MC-RULE-007) before executing. Not a new approval mechanism — this
  points at the one that already exists and is already wired to `/admin/`, `/config/`, `/deploy/`,
  `/workers/`.
- `escalation_severity` — reuses `ai_governance.py`'s existing `IncidentSeverity` enum (`low` /
  `medium` / `high` / `critical`), not the 5-level scheme (…+`fatal`) the brainstorm proposed.
- `audit_sink` — always `"observatory"` today; the field exists so a future sink can be added
  without a schema break, but there is exactly one real audit log on this platform and the schema
  should say so rather than imply a choice that doesn't exist.

See the companion schema file for the full structure, required fields, and the worked example
(a Tier 4 Agent charter under ArchPrime's domain).

### 2.3 Phase 2 status — enforcement now exists

Updated 2026-08-06: this is no longer designed-but-not-built. `src/compliance/escalation_fsm.py`
loads and validates every charter in `docs/governance/charters/` against the schema at import time,
and `EscalationFSM.submit()` genuinely resolves an action request against a charter and blocks or
routes it — this is real code, not aspiration. 11 seed charters ship today: one Tier 4 Agent charter
per `PrimeDomain` (§1.2's 9 domains), a Tier 4 fallback for unmapped entities, and one shared Tier 5
Bot charter. See §3 for what the FSM actually does.

**Update 2026-08-06 (Phase 3):** both real dispatch call sites now route through it — see §3.5 for
what actually landed and why `AgentOrchestrator` and `BotRegistry` needed different integration
shapes.

---

## 3. Unified escalation state machine — implemented

### 3.1 The gap this closes

`HARD-STOP-MATRIX.md` already found and documented this gap independently: 5 real, independent stop
mechanisms exist (Trance-One `emergency_stop()`, 4 separate circuit breakers, AI Gateway hard-stop,
CapacityGuard, Zero-Cost Enforcer blocklist) and its own stated conclusion is *"there is no single
place that answers 'has anything been hard-stopped right now'."* This section is the design for
that missing aggregator, extended to also cover the escalation states the original brainstorm
wanted (routing a policy violation from detection through human approval).

### 3.2 States and transitions

Reusing the brainstormed FSM shape, because it's sound — the states themselves aren't the novel
part, wiring them to *real* platform mechanisms instead of hypothetical ones is:

```text
draft -> validated              (charter schema validation passes)
draft -> rejected                (schema validation fails)
validated -> policy_checked      (no charter conflict — see §3.4)
validated -> escalated           (charter or constitution conflict)
policy_checked -> approved        (approval_required: false)
policy_checked -> pending_cab     (approval_required: true — routes to CAB Gate, not a new gate)
pending_cab -> approved           (CAB Gate: status=approved)
pending_cab -> rejected           (CAB Gate: status rejected)
pending_cab -> escalated          (CAB Gate: timeout)
approved -> executing -> completed
executing -> escalated            (execution failure)
escalated -> frozen               (severity: critical — logged to ai_governance.py AIIncident)
frozen -> halted                  (irreversible violation — this is the Hard Stop Matrix's missing
                                    aggregation point: halted state = "yes, something is stopped")
```

### 3.3 Where each transition actually writes data

No new logging system. Every transition writes to systems that already exist — this is what
`EscalationFSM` in `src/compliance/escalation_fsm.py` does today, not a plan:

- Schema validation results → not persisted (stateless check, `CharterRegistry.reload()`)
- `pending_cab` (CAB path) → `cab_gate.register_change()`, resolved via `EscalationFSM.resolve_cab()`
  which calls back into the same `cab_changes` table `src/compliance/cab_gate.py` already owns
- `escalated` / `frozen` → `AIIncident` log, `src/compliance/ai_governance.py` (`log_ai_incident()`)
- Every transition → **The Observatory** audit trail via `Observatory.record()`, `category=GOVERNANCE`
- `halted` → `EscalationFSM.list_halted()` / `GET /governance/halted` is the aggregation point Hard
  Stop Matrix asked for — answers "is anything hard-stopped right now" for the first time
- State + full history persisted in SQLite (`escalation_records` table, zero-cost/self-hosted, same
  pattern as `cab_changes`), exposed at `/governance/actions/{record_id}`, `/governance/charters*`

### 3.4 Conflict resolution

Precedence ladder, reusing Magna Carta's own existing layer order rather than inventing a new one
(`FRAMEWORK.md` §2): Constitution (Magna Carta Layer 1) → Regulatory (Layer 4) → this charter
schema → workflow-specific instruction. Deny wins over allow when rules at the same layer conflict.
Ambiguity escalates (`escalated` state) rather than defaulting permissive — matching Magna Carta's
own "human agency" principle (*"high-risk decisions require human review"*).

### 3.5 Explicitly out of scope for this phase

What Phase 2 built: `src/compliance/escalation_fsm.py` (charter loading/validation, the FSM itself,
CAB Gate + `ai_governance` + Observatory wiring, `list_halted()`), `src/compliance/governance_routes.py`
(`/governance/charters`, `/governance/actions`, `/governance/halted`, mounted in `api.py`), 11 real
seed charters, and 52 passing tests (`tests/test_escalation_fsm.py`).

Hardened post-landing after cubic's review of the first commit found 2 P1s and 7 P2s in this code
(all fixed, not declined): `resolve_cab()` now actually calls into `CABGate.approve_change()` /
`reject_change()` and verifies the decision was applied before transitioning FSM state, rather than
trusting the caller's boolean and leaving `cab_changes` permanently diverged from
`escalation_records`; every non-confidence escalation trigger a charter declares
(`sensitive_data_detected`, `prompt_injection_suspected`, etc.) is now actually evaluated against
`ActionRequest.context`, not just `confidence_below_threshold`; every transition is now also
appended to a durable `escalation_transitions` table (`GET /governance/actions/{id}/transitions`),
since `escalation_records` alone only ever held current state; Observatory severity is drawn from
each charter's own `escalation_severity` instead of a flat `WARNING`; every escalation and freeze
now logs an `AIIncident`; `jsonschema` is a hard, pinned dependency (fails closed, not silently
unvalidated); and `scripts/check_ecdsa_direct_usage.py` uses `ast` instead of line regex, so it
can't miss `ecdsa.*` submodule imports or false-positive on its own docstring.

**Phase 3 (2026-08-06): both real Tier 4/5 dispatch call sites now route through `submit()`.**
Matching how Matrix Suites was built in stages (7.1 design → 7.2 event emission → 7.3–7.5 further
integration) rather than landing everything at once, the two call sites needed different
integration shapes because they have very different risk profiles:

- **`src/agents/orchestrator.py`'s `AgentOrchestrator` (Tier 4, zero existing callers anywhere in
  the repo — verified by grep before wiring, so this was a safe unconditional change).**
  `AgentConfig` gained a `domain` field (`PrimeDomain` slug, default `"unassigned"`); `AgentTask`
  gained `action` (the charter-matched verb; falls back to `description` if unset) and
  `escalation_record_id`. `submit_task()` now calls `EscalationFSM.submit()` (tier=4) before
  touching the priority queue: an `approved` outcome enqueues the task exactly as before;
  `rejected`/`halted` leaves it un-queued with `status="blocked_governance"`;
  `escalated`/`pending_cab` leaves it un-queued with `status="pending_governance"`, inspectable via
  `get_task()` and resolvable through the existing `/governance/actions/{id}/cab-decision` route.
  No exception is raised in the non-approved cases — the task record itself carries the outcome,
  consistent with how `pending_cab` already works for CAB Gate elsewhere in this FSM. A new
  `get_escalation_fsm()` singleton getter was added to `escalation_fsm.py` (mirroring
  `get_charter_registry()`) for in-process callers to share. `submit_task()` on its own does *not*
  close the loop, though: the `/governance/actions/{id}/cab-decision` route only updates the FSM
  record, it has no idea `AgentOrchestrator` or a given task exists — so a CAB-approved task would
  otherwise stay `pending_governance` forever (a real gap cubic caught). `resync_governance(task_id)`
  is the explicit closing step: call it after a decision lands (from a poller, or right after a
  known cab-decision call) and it re-checks the task's escalation record, enqueueing on `approved`
  or setting `blocked_governance` on `rejected`/`halted`; it's a no-op (returns the task unchanged)
  for anything not currently `pending_governance`, so it's safe to call repeatedly. There is no
  automatic trigger between the two modules yet — that would need an event bus this platform
  doesn't have between compliance and agents today. Reloading tasks from SQLite on restart is also
  gated: a `status='pending'` row with no `escalation_record_id` predates this wiring entirely and
  is loaded but deliberately left out of the runnable queue rather than trusted at face value.
- **`tranc3-bots/bots/registry.py`'s `BotRegistry` (Tier 5, a separately deployed live service —
  its own `pyproject.toml`, own Dockerfile that does not `COPY` the main repo's `src/` tree, no
  `jsonschema` dependency, and zero existing `from src.` / `import src.` precedent anywhere in that
  package).** A direct Python import of `src.compliance.escalation_fsm` was not a risk to manage
  down, it was architecturally infeasible — the package that would import it doesn't ship the
  module. Instead `bots/governance_client.py` calls the main backend's existing
  `POST /governance/actions` HTTP route (the same route `/governance/*` already exposes for
  exactly this kind of cross-service check), reusing `TRANC3_ENGINE_URL` — the env var this
  package already uses to reach the main backend for inference-bot dispatch. The whole thing is
  gated behind `GOVERNANCE_GATE_ENABLED` (mirroring `cab_gate.py`'s `CAB_GATE_ENABLED` precedent),
  defaulting to off, so this can ship without unconditionally coupling every live bot dispatch to
  the main backend's availability. When enabled: a network/timeout error talking to the governance
  endpoint fails **open** (logged, dispatch proceeds) — that's an infrastructure availability
  problem, not a policy signal — but an actual `rejected`/`halted` FSM decision fails **closed**
  (`GovernanceBlockedError`, which `BotPool._execute()` already turns into a normal
  `JobStatus.FAILED` result — no new error-handling path needed). `bot-stateless-utility.json`'s
  `allowed_actions` was also corrected from a placeholder AeonMind-inspired verb list to the real
  `BotType` enum values (`generate`, `embed`, `emotion`, `tokenize`, `consciousness`,
  `personality`, `predict`, `code`, `memory`, `monitor`, `search`, `summarise`) — the previous list
  couldn't have matched a real dispatch and would have escalated every single bot call as
  ambiguous the moment the gate was ever turned on.

What's still explicitly not done: `GOVERNANCE_GATE_ENABLED` has not been turned on for the deployed
`tranc3-bots` service — that's a separate, deliberate rollout decision (it changes live bot-traffic
behavior and needs a shared `INTERNAL_SECRET` provisioned between the two services first), not a
code gap. Expanding the 11 seed charters as real capability gaps are found remains ongoing, ordinary
maintenance rather than a phase of its own.

---

## 4. Further enhancements identified during this review

Not requested directly, but real, already-existing, underused platform capability that would
strengthen this constitution beyond what the originating brainstorm proposed, because it's grounded
in code that already exists rather than invented from scratch:

- **Confidence-based escalation** — AeonMind's `Intelligence Score` (decision_quality 0.30 /
  adaptation_speed 0.25 / state_coherence 0.20 / resource_efficiency 0.15 / communication 0.10) and
  `Fluidic State` (energy/coherence/entropy) are a fully-specified confidence model that can drive
  the `escalation_severity` field in §2.2 directly, instead of a bare "confidence < threshold"
  check with no real scoring behind it.
- **Sentinel Channel routing** — the `SECURITY`, `AGENTS`, and `PLATFORM` channels
  (`AI_DEFINITIONS_DICTIONARY.md`) are a specified broadcast bus that escalation events could ride,
  rather than inventing new pub/sub.
- **Hard Stop Matrix aggregation** — see §3.2; this constitution's `halted` state is the first real
  answer to a gap that doc already flagged.
- **Cost Governance's fixed-policy/live-state split** — `COST-AND-REVENUE-GOVERNANCE.md` already
  separates "the escalation chain" (this file) from "what's actually been reviewed"
  (`18_cost_and_revenue_review.csv`). This doc follows the same split deliberately.
- **Continuous Improvement Programme** — the quarterly PDCA cycle (ISO 27001 Clause 10, Magna Carta
  MC-011) is the natural home for reviewing and versioning this constitution, rather than a bespoke
  amendment process.

---

## 5. Cross-references

- `compliance/magna-carta/FRAMEWORK.md` — the platform's actual constitution; this doc is a fill-in
  for its two missing layers, not a replacement.
- `docs/governance/AI-AGENT-BOT-TIER-MATRIX.md` — the existing Tier 1–5 cross-reference map this doc
  extends with the AeonMind reconciliation.
- `docs/governance/HARD-STOP-MATRIX.md` — source of the aggregation gap §3 closes.
- `aeonmind/docs/AI_DEFINITIONS_DICTIONARY.md` — source of the canonical tier definitions per §1.2.
- `src/compliance/cab_gate.py`, `src/compliance/ai_governance.py`, `src/roles/registry.py` — the
  real systems this design wires into rather than duplicates.
- `docs/governance/schemas/agent-charter.schema.json` — companion JSON Schema (§2).
- `docs/governance/charters/` — the 11 real seed charters (§2.3).
- `src/compliance/escalation_fsm.py`, `src/compliance/governance_routes.py` — the Phase 2
  implementation (§3), `/governance/*` routes mounted in `api.py`.
- `tests/test_escalation_fsm.py` — 52 tests covering the FSM, charter registry, and routes.
- `scripts/check_ecdsa_direct_usage.py` — unrelated to this doc's subject but landed alongside it in
  the same PR: a CI drift guard for the ecdsa accepted-risk scope claim in `.trivyignore`.
