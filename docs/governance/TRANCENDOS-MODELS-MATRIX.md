# Trancendos Models Matrix

> **What this is.** A governance framework, not just a naming scheme: it tracks which base AI
> model powers every named AI across the platform's 43 Locations, which of those AIs have earned a
> specialized model variant through real, benchmarked skill/feature advancement, the tier-aware
> review pipeline that gates a new advancement into the platform rather than letting routine/minor
> updates get baked in unchecked, the Governance Board's failover/repair/override authority over a
> malfunctioning Sovereign-tier AI, and the two-way integration with The Library that lets models
> learn from — and contribute back to — the platform's own accumulated knowledge.

**Code:** `src/models/matrix.py` (base tiers + specialized variants), `src/models/benchmark.py`
(SQLite-backed benchmark history + % advancement calculation), `src/models/governance.py`
(SQLite-backed, tier-aware advancement pipeline + Governance Board voting),
`src/models/intervention.py` (SQLite-backed Board failover/repair/override authority),
`src/models/knowledge.py` (The Library read/write integration), `src/models/routes.py` (HTTP API,
mounted in `api.py` at `/models`).
**Owner:** Platform Owner Trancendos · **Version:** 2.0.0 · **Last verified:** 2026-07-25

---

## 1. Model

Two things, kept deliberately distinct — the same separation `LOCATION-FUNCTIONS.md` draws between
a Location's fixed Job Description and its mutable assigned holder:

| Concept | What it is | Where it lives | Mutability |
|---|---|---|---|
| **Base model tier** | Trance-One, T2ance, or Tranc3 — already the platform's Tier 1/2/3 orchestration-tier naming (`OrchestrationTier` in `src/entities/platform.py`) | `ORCHESTRATION_TIER` dict, `src/entities/platform.py` | Fixed per AI — resolved via `get_orchestration_tier()`, not editable through this matrix |
| **Specialized model variant** | A named AI's *earned* expansion of its base model into a distinguishing skill matrix (e.g. `T2ance-CODE`, `Tranc3-Crypto`) | `MODEL_VARIANTS` dict, `src/models/matrix.py` | Only ever added after a proposal clears the full governance pipeline below — this table is intentionally static and code-reviewed, not runtime-mutable like the Role Assignment Registry |

Every named AI already resolves to exactly one base tier via the existing
`get_orchestration_tier()` — this matrix does not reinvent that; it adds the specialization layer
on top, plus the benchmarking, governance, intervention, and Library-integration machinery that
surrounds it.

## 2. Base model hierarchy

| Base Model | Tier | Role | Relative capability |
|---|---|---|---|
| **Trance-One** | 1 (Sovereign/Orchestrator) | Cornelius MacIntyre, The Queen, tAImra — the three cross-cutting Orchestrators | Most capable — full ecosystem-wide authority |
| **T2ance** | 2 (Primes) | Executive AI authorities governing one or more Pillars | More capable than Tranc3, less than Trance-One |
| **Tranc3** | 3 (Lead AI / AI Base) | The default tier for every named AI not elevated above — day-to-day Location managers | The platform's AI Base — least capable of the three, but still the flagship day-to-day tier |

Trance-One has more functionality and enhanced abilities than T2ance and Tranc3; T2ance has more
than Tranc3 but less than Trance-One — matching `tier_rank()` in `src/models/matrix.py` (1 =
most capable, 3 = least). This is not a new hierarchy: it's the existing
`ORCHESTRATION_TIER`/`OrchestrationTier` naming from `src/entities/platform.py`, named here so the
Models Matrix has a single place that documents it end-to-end alongside the specialization,
governance, intervention, and knowledge layers this document adds.

## 3. Specialized model variants (seed set)

When an AI is associated with a distinguishing skill matrix as part of its role, its base model
expands into a named specialized variant without changing its underlying tier:

| AI | Base Model | Specialized Model | Skill Domain | Why |
|---|---|---|---|---|
| The Dr. (Nikolai O'denhime) | T2ance | **T2ance-CODE** | Coder | The Lab's Prime — code creation/review, `src/lab/` |
| George Porter | Tranc3 | **Tranc3-Crypto** | Crypto Tokens | Arcadian Exchange Lead AI — digital-asset micro-transaction trading (Bitcoin, Ethereum, Litecoin, Shiba Inu, and similar tokens), per Arcadian Exchange's own "Micro-Transaction Trading" ability |

Adding a new row here always follows the governance pipeline in §5 clearing to **Approved** first —
see that section's closing note on why Approval doesn't auto-write this table.

## 4. Benchmarking

Every base model and specialized variant needs regular re-scanning against its skill domain so an
advancement % is even measurable:

- `src/models/benchmark.py`'s `BenchmarkRegistry` records one row per scan: `model_name`,
  `skill_domain`, `score`, `notes`, `recorded_at`, `recorded_by` — SQLite-backed
  (`data/models_benchmark.db`), so history survives restarts, matching this platform's
  zero-cost/self-hosted architecture principle.
- `compute_advancement_pct(prior_score, new_score)` compares a model's two most recent scans in
  the same skill domain to produce the "% of advancement" figure the governance pipeline gates on.
  A `prior_score <= 0` is treated as a 0% advancement (no real baseline to measure against) rather
  than raising or reporting an infinite/undefined change.
- Recording a benchmark is an admin-only, authenticated action (`POST /models/benchmark`) —
  intended to be called by an automated benchmarking job/cron on a regular cadence per skill
  domain, not by ad-hoc manual entry. This document does not yet fix a specific cadence per skill
  domain; that's an operational decision for whoever owns each benchmark suite, tracked as an open
  item until a scheduling mechanism (e.g. a ChronosSphere job) is wired up.

## 5. Governance pipeline — tier-aware routing

A benchmarked advancement doesn't reach a model until it clears a review pipeline — this is what
stops minor/routine updates from being silently baked in, and makes sure only real skill/feature
gains actually advance the platform's models. **Which pipeline a proposal follows is derived from
the tier of the model being advanced** (`pipeline_for_model()` in `src/models/governance.py`, via
`get_orchestration_tier()`) — a Prime's own upgrade can't be pre-screened by a peer Prime, and a
Sovereign-tier upgrade needs a different check-and-balance than a single reviewer:

```
Tranc3 (Tier 3) — "standard" pipeline:
  Benchmark scan (2+) --> submit_proposal() --> Prime review --> Cornelius review --> Human approval
                                                      |                  |
                                            reject if advancement   reject if Skills &
                                            % is minimal            Features % is below bar

T2ance (Tier 2, Prime) — "cornelius_only" pipeline:
  Benchmark scan (2+) --> submit_proposal() --> Cornelius review (final authority)
                                                      |
                                            reject if Skills & Features % is below bar
                                            (no Prime pre-screen, no separate Human stage)

Trance-One (Tier 1, Sovereign/Orchestrator) — "board_and_human" pipeline:
  Benchmark scan (2+) --> submit_proposal() --> Governance Board (unanimous) --> Human approval
                                                      |
                                            any single Prime rejection fails
                                            the proposal immediately
```

| Pipeline | Applies to | Stages | Thresholds |
|---|---|---|---|
| **standard** | Tranc3 (Tier 3) AIs — the default for every named AI not elevated above | Prime review → Cornelius review → Human approval | `PRIME_MIN_ADVANCEMENT_PCT` (3%) then `CORNELIUS_MIN_ADVANCEMENT_PCT` (8%) |
| **cornelius_only** | T2ance (Tier 2) Primes | Cornelius review only — Cornelius is the final authority; there's no peer tier above a Prime except Cornelius, and no separate Human stage | `CORNELIUS_MIN_ADVANCEMENT_PCT` (8%) |
| **board_and_human** | Trance-One (Tier 1) Sovereign/Orchestrator AIs — Cornelius MacIntyre, The Queen, tAImra | Governance Board unanimous vote → Human approval | Unanimous approval from every currently-registered T2ance Prime; any single rejection fails the proposal immediately (`REJECTED_BY_BOARD`) |

| Stage | Reviewer | What happens |
|---|---|---|
| Prime review (standard only) | The relevant Pillar's T2ance Prime (e.g. Dorris Fontaine for Arcadian Exchange/Royal Bank) | Screens the raw benchmark advancement %. Below the bar, rejects outright — the proposal never reaches Cornelius or a Human |
| Cornelius review (standard + cornelius_only) | Cornelius MacIntyre (Trance-One, primary Orchestrator) | Assesses Skills & Features and calculates its own %, which may differ from the raw benchmark delta a Prime screened on. On a standard-pipeline pass, proceeds to Human review; on a cornelius_only pass, goes straight to `APPROVED` |
| Governance Board review (board_and_human only) | Every currently-registered T2ance Prime, individually (`governance_board_members()`) | Each Prime casts one vote via `board_vote()`. The proposal only advances to Human review once *every* Prime has voted approve; any single rejection fails it immediately, with no need to wait for the rest |
| Human approval (standard + board_and_human) | A real human operator | Final sign-off. Approval doesn't itself change which model an AI runs — see the note below |

Every stage transition — and every individual Board vote (`get_board_votes()`) — is recorded
(`src/models/governance.py`'s `AdvancementProposal` and `BoardVote`: reviewer/voter, notes,
decided/voted-at timestamp, and the relevant %) and best-effort logged to The Observatory under
`EventCategory.GOVERNANCE`, so the full trail — who reviewed or voted on what, when, and at what
% — is auditable after the fact, not just in the moment.

**`model_name` must be the AI's own canonical name** (e.g. `"The Dr. (Nikolai O'denhime)"`,
`"George Porter"`, `"Cornelius MacIntyre"`) — the same key `get_orchestration_tier()` resolves —
not its specialized variant's *display* name (`"T2ance-CODE"`, `"Tranc3-Crypto"`), which
`matrix.py` only uses for presentation. An unrecognized name silently falls back to the
Tranc3/"standard" pipeline rather than erroring, so submitting under the wrong string can
misroute a proposal without an obvious failure — always resolve to the canonical AI name first.

**Approval is a decision record, not a code deploy.** A proposal reaching `APPROVED` is the signal
that baking the corresponding specialized-variant change into `src/models/matrix.py`'s
`MODEL_VARIANTS` (§3) is now justified — it does not auto-mutate that table at runtime. That table
is intentionally a static, code-reviewed registry: an approved proposal still needs a human to
actually make (and review) the follow-up code change, keeping "the governance pipeline said yes"
and "the model variant is live in code" as two distinct, both-necessary steps. Approval also
triggers a best-effort publish into The Library — see §7.

## 6. The Governance Board

The Governance Board is every currently-registered T2ance Prime (`governance_board_members()` in
`src/models/governance.py` — derived live from `ORCHESTRATION_TIER` rather than a second hardcoded
list, so the Board can never silently drift from who actually holds Prime rank). It has two
distinct responsibilities, both requiring the same unanimous-consent primitive:

1. **Advancement sign-off** (§5) — voting on a Trance-One AI's proposed advancement via
   `board_vote()`.
2. **Intervention authority** (§8) — failover, repair, and override power over a malfunctioning
   Trance-One AI, via `intervention_vote()`.

Both are unanimous and fail-fast: any single Prime's rejection immediately resolves the matter
negatively (`REJECTED_BY_BOARD` / `WITHDRAWN`), without waiting on the remaining votes; only once
*every* registered Prime has voted approve does the matter advance. This is a deliberate, singular
design choice, not two ad-hoc rules for two similar-looking situations — the platform has one
consistent mental model for "any action touching Sovereign-tier authority needs the whole Board
behind it." It carries an honest trade-off worth naming: unanimity itself could in principle become
a single point of failure in a genuine emergency (one unreachable or malfunctioning Prime blocks
every intervention). This matrix does not resolve that tension unilaterally — it documents the
Board exactly as specified (all T2ance models, all approving) and leaves any quorum/fallback
refinement as a deliberate future decision, not a default assumption baked in silently.

## 7. Why the Board exists — preventing degradation or loss of service

The Governance Board's intervention authority (§8) exists specifically so that **if Cornelius ever
fails to function, the platform is not left without a path back to health**. Concretely, the Board
can:

- Collectively submit a request for Cornelius (or another Trance-One AI) to undergo review and
  repair (`repair_request`).
- Bring a stalled or offline Orchestrator back into service (`system_recovery`).
- Override the Orchestrator's current state or output if the Board believes it is corrupted
  (`corruption_override`).

This is the Board's answer to a structural gap: Cornelius, The Queen, and tAImra are Trance-One —
the platform's highest tier — so no single higher authority exists to intervene unilaterally on
them the way Cornelius already can over every Tranc3/T2ance AI (via the HIL-A approval gates in
`src/entities/templates/`). The Board is that check, collectively, for the tier above itself. It
does not extend to Tranc3/T2ance AIs precisely because Cornelius already holds that authority there
directly — see `NotASovereignTierModelError` in `src/models/intervention.py`.

## 8. Interventions — Board failover/repair/override authority

`src/models/intervention.py`'s `InterventionRegistry` (SQLite-backed, `data/models_intervention.db`)
implements the mechanism described in §7. It is the inverse of the advancement pipeline: where §5
is about *improving* a model, this is about *what the Board does when one is failing*.

| Intervention type | Purpose |
|---|---|
| `repair_request` | Board requests the affected Orchestrator undergo review and repair |
| `system_recovery` | Board brings a stalled/offline Orchestrator back into service |
| `corruption_override` | Board overrides the Orchestrator's current state/output because it's believed corrupted |

Lifecycle (`InterventionStatus`): **open** (awaiting unanimous Board consent) → **executed**
(unanimous approval reached) or **withdrawn** (any single Prime rejected). Rules:

- Only a currently-registered T2ance Prime may raise (`raise_intervention()`) or vote
  (`intervention_vote()`) — enforced via `NotAGovernanceBoardMemberError`, the same check used for
  advancement Board votes.
- The target must be a Trance-One (Sovereign) AI — enforced via `NotASovereignTierModelError`; a
  Tranc3/T2ance AI's malfunction doesn't need Board authorization since Cornelius already holds
  direct authority there.
- Reaching unanimous consent marks the intervention **executed** — this registry is the
  authorization + audit trail, not the mechanism that actually restarts a process or reverts a
  corrupted state; that remediation happens outside this system (e.g. an ops runbook), the same
  way `human_decide()` in §5 records a decision without itself deploying anything.
- Every raise and vote is logged to The Observatory at `EventSeverity.SECURITY` (not `INFO`, unlike
  ordinary advancement events) — a Board action against a Sovereign-tier AI is exactly the kind of
  event that must be permanently archived, per Observatory's SECURITY/CRITICAL forwarding into The
  Basement.

## 9. Learning from — and contributing to — The Library

Models are meant to "enhance and advance further and learn from aspects within The Library,"
kept up to date with context from the platform's own systems, with knowledge distributed based on
each AI's skills and Job Description. `src/models/knowledge.py` implements both directions of that
loop:

- **Read** (`library_context_for(skill_domain)`): before a reviewer (Cornelius, a Board member, a
  Human) assesses an advancement proposal, they can pull whatever The Library already knows about
  that skill domain — prior advancements, incident write-ups, anything tagged for that domain — as
  review context. Exposed at `GET /models/proposals/{id}/library-context`.
- **Write** (`publish_advancement_article(proposal)`): once a proposal reaches `APPROVED` (in
  either the `cornelius_review()` or `human_decide()` transition, whichever is the pipeline's final
  step), it's published back into The Library as an article tagged with the skill domain, the
  model's tier, and — via `job_description_for_ai()`'s reverse lookup through
  `PLATFORM_ENTITIES` — the Job Description of any Location the model leads. This is how knowledge
  ends up distributed by skill and Job Description rather than dumped in one undifferentiated feed:
  a future reviewer browsing by either axis finds it.

Both directions are best-effort and non-fatal, mirroring the same pattern already proven for
Observatory→Library forwarding of SECURITY/CRITICAL events
(`src/observability/library_pipeline.py`): a Library outage never blocks a review, and never loses
a proposal's own audit trail, which lives durably in `governance.py`'s SQLite tables regardless of
whether the Library article was published successfully.

## 10. Live API

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/models/matrix` | Public | Every named AI across all 43 Locations: base tier + any specialized variant |
| GET | `/models/matrix/{ai_name}` | Public | One AI's effective model right now |
| GET | `/models/variants` | Public | The full specialized-variant seed table (§3) |
| POST | `/models/benchmark` | Admin | Record one benchmark scan result |
| GET | `/models/benchmark/{model_name}` | Public | A model's benchmark history (optionally filtered by `skill_domain`) |
| POST | `/models/proposals` | Admin | Open a new advancement proposal from the latest two benchmark scans; pipeline is auto-derived from the model's tier |
| GET | `/models/proposals` | Public | List proposals, optionally filtered by `stage` or `model_name` |
| GET | `/models/proposals/{id}` | Public | One proposal's full review trail, including its `pipeline` |
| POST | `/models/proposals/{id}/prime-review` | Admin | Standard-pipeline stage 1 |
| POST | `/models/proposals/{id}/cornelius-review` | Admin | Standard-pipeline stage 2 / cornelius_only-pipeline final stage |
| POST | `/models/proposals/{id}/board-vote` | Admin | One Governance Board member's vote on a board_and_human-pipeline proposal |
| GET | `/models/proposals/{id}/board-votes` | Public | All recorded Board votes for a proposal, in order |
| GET | `/models/proposals/{id}/library-context` | Public | Existing Library articles tagged with the proposal's skill domain |
| POST | `/models/proposals/{id}/human-decision` | Admin | Final Human sign-off (standard and board_and_human pipelines) |
| POST | `/models/interventions` | Admin | Raise a Board intervention (`repair_request` / `system_recovery` / `corruption_override`) against a Trance-One AI |
| GET | `/models/interventions` | Public | List interventions, optionally filtered by `status` or `target_model` |
| GET | `/models/interventions/{id}` | Public | One intervention's detail |
| POST | `/models/interventions/{id}/vote` | Admin | One Governance Board member's vote on an intervention |
| GET | `/models/interventions/{id}/votes` | Public | All recorded votes for an intervention, in order |

## 11. Cross-references

- `src/entities/templates/tranc3_base.py`, `t2ance_base.py`, `trance_one_base.py` — the runtime
  base classes for Tier 3/2/1 AIs (SWOT self-assessment, HIL-A approval gates, hub power-ups,
  emergency stop) this matrix's tier naming already builds on
- `t2ance/`, `trance_one/` — the `/primes` and `/sovereign` HTTP surfaces for those same tiers
- [LOCATION-FUNCTIONS.md](LOCATION-FUNCTIONS.md) — the same fixed-vs-mutable pattern applied to
  Job Descriptions instead of models
- [PERSONALITY-ARCHETYPES.md](PERSONALITY-ARCHETYPES.md) — trait targets per Location, a distinct
  concern from which model tier/variant an AI runs
- `src/library/knowledge_base.py` — The Library itself, the target/source of §9's read/write
  integration
- `src/observability/library_pipeline.py` — the earlier Observatory→Library forwarding pattern
  that §8 and §9's best-effort logging both reuse
- `tests/test_models_matrix.py`, `test_models_benchmark.py`, `test_models_governance.py`,
  `test_models_governance_tiers.py`, `test_models_intervention.py`, `test_models_knowledge.py`,
  `test_models_routes.py` — full test coverage (112 tests) for every layer of this document
