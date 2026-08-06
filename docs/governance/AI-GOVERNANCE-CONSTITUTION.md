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

**Owner:** Platform Owner Trancendos · **Version:** 1.1.0 · **Status:** Phase 2 complete (terminology,
schema, and a real escalation FSM with 11 seed charters — not yet called by any live agent/bot code
path; see §3.5) · **Last verified:** 2026-08-06

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
| 4 — AGENT | Agents (`agent_teams`) | **Correction to the brainstorm this doc responds to**: only 4 of 43 Locations (TateKing, Arcadian Exchange, The Lab, Infinity) have populated `agent_teams`; there is no uniform "every AI owns 2 agents" ratio in the actual code |
| 5 — BOT | Bots (`BotRegistry`) | **Correction**: 12 bot *types*, shared platform-wide via `tranc3-bots/bots/registry.py` — not something each AI separately owns 6 of |

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

The originating brainstorm assumed a uniform ownership ratio and one charter per AI. Neither holds:
agent/bot ownership is genuinely uneven (§1.2), and a single 40-entity charter list would duplicate
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

**What's still not done**: no live platform code *calls* `EscalationFSM.submit()` yet — Tier 4/5
entities don't route their actions through it today. The FSM exists, is tested, and is reachable via
`/governance/*`, but nothing in `src/agents/orchestrator.py` or `tranc3-bots/bots/registry.py` calls
it. Wiring an actual caller in is Phase 3.

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
seed charters, and 38 passing tests (`tests/test_escalation_fsm.py`).

What's still explicitly not done, matching how Matrix Suites was built in stages (7.1 design → 7.2
event emission → 7.3–7.5 further integration) rather than landing all at once: **no live platform
code calls `EscalationFSM.submit()` yet.** The FSM works, is tested, and is reachable via HTTP, but
`src/agents/orchestrator.py`'s `AgentOrchestrator` and `tranc3-bots/bots/registry.py`'s `BotRegistry`
don't route dispatched tasks through it — so today it validates and would-enforce, but doesn't yet
actually intercept a real Tier 4/5 action anywhere in the platform. Wiring that call site in, and
expanding the 11 seed charters as real capability gaps are found, is Phase 3.

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
- `tests/test_escalation_fsm.py` — 38 tests covering the FSM, charter registry, and routes.
- `scripts/check_ecdsa_direct_usage.py` — unrelated to this doc's subject but landed alongside it in
  the same PR: a CI drift guard for the ecdsa accepted-risk scope claim in `.trivyignore`.
