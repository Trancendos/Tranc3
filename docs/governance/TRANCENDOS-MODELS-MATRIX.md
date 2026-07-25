# Trancendos Models Matrix

> **What this is.** A governance framework, not just a naming scheme: it tracks which base AI
> model powers every named AI across the platform's 43 Locations, which of those AIs have earned a
> specialized model variant through real, benchmarked skill/feature advancement, and the review
> pipeline (**Prime → Cornelius → Human**) that gates a new advancement into the platform rather
> than letting routine/minor updates get baked in unchecked.

**Code:** `src/models/matrix.py` (base tiers + specialized variants), `src/models/benchmark.py`
(SQLite-backed benchmark history + % advancement calculation), `src/models/governance.py`
(SQLite-backed Prime → Cornelius → Human proposal pipeline), `src/models/routes.py` (HTTP API,
mounted in `api.py` at `/models`).
**Owner:** Platform Owner Trancendos · **Version:** 1.0.0 · **Last verified:** 2026-07-25

---

## 1. Model

Two things, kept deliberately distinct — the same separation `LOCATION-FUNCTIONS.md` draws between
a Location's fixed Job Description and its mutable assigned holder:

| Concept | What it is | Where it lives | Mutability |
|---|---|---|---|
| **Base model tier** | Trance-One, T2ance, or Tranc3 — already the platform's Tier 1/2/3 orchestration-tier naming (`OrchestrationTier` in `src/entities/platform.py`) | `ORCHESTRATION_TIER` dict, `src/entities/platform.py` | Fixed per AI — resolved via `get_orchestration_tier()`, not editable through this matrix |
| **Specialized model variant** | A named AI's *earned* expansion of its base model into a distinguishing skill matrix (e.g. `T2ance-CODE`, `Tranc3-Crypto`) | `MODEL_VARIANTS` dict, `src/models/matrix.py` | Only ever added after a proposal clears the full Prime → Cornelius → Human pipeline below — this table is intentionally static and code-reviewed, not runtime-mutable like the Role Assignment Registry |

Every named AI already resolves to exactly one base tier via the existing
`get_orchestration_tier()` — this matrix does not reinvent that; it adds the specialization layer
on top, plus the benchmarking and governance machinery to earn one.

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
Models Matrix has a single place that documents it end-to-end alongside the specialization and
governance layers this document adds.

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

## 5. Governance pipeline — Prime → Cornelius → Human

A benchmarked advancement doesn't reach a model until it clears three review stages, each with its
own bar — this is what stops minor/routine updates from being silently baked in, and makes sure
only real skill/feature gains actually advance the platform's models:

```
Benchmark scan (2+) --> submit_proposal() --> Prime review --> Cornelius review --> Human approval
                                                    |                  |
                                          reject if advancement   reject if Skills &
                                          % is minimal            Features % is below bar
```

| Stage | Reviewer | Threshold | What happens |
|---|---|---|---|
| 1 — Prime review | The relevant Pillar's T2ance Prime (e.g. Dorris Fontaine for Arcadian Exchange/Royal Bank) | `PRIME_MIN_ADVANCEMENT_PCT` (3%) | Screens the raw benchmark advancement %. Below the bar, the Prime rejects outright — the proposal never reaches Cornelius or a Human |
| 2 — Cornelius review | Cornelius MacIntyre (Trance-One, primary Orchestrator) | `CORNELIUS_MIN_ADVANCEMENT_PCT` (8%) | Assesses Skills & Features and calculates its own %, which may differ from the raw benchmark delta a Prime screened on. Below Cornelius's own (higher) bar, the proposal is rejected here |
| 3 — Human approval | A real human operator | N/A — final judgement call | Final sign-off. Approval doesn't itself change which model an AI runs — see the note below |

Every stage transition is recorded (`src/models/governance.py`'s `AdvancementProposal`: reviewer,
notes, decided-at timestamp, and the relevant %) and best-effort logged to The Observatory under
`EventCategory.GOVERNANCE`, so the full trail — who reviewed what, when, and at what % — is
auditable after the fact, not just in the moment.

**Approval is a decision record, not a code deploy.** A proposal reaching `APPROVED` is the signal
that baking the corresponding specialized-variant change into `src/models/matrix.py`'s
`MODEL_VARIANTS` (§3) is now justified — it does not auto-mutate that table at runtime. That table
is intentionally a static, code-reviewed registry: an approved proposal still needs a human to
actually make (and review) the follow-up code change, keeping "the governance pipeline said yes"
and "the model variant is live in code" as two distinct, both-necessary steps.

## 6. Live API

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/models/matrix` | Public | Every named AI across all 43 Locations: base tier + any specialized variant |
| GET | `/models/matrix/{ai_name}` | Public | One AI's effective model right now |
| GET | `/models/variants` | Public | The full specialized-variant seed table (§3) |
| POST | `/models/benchmark` | Admin | Record one benchmark scan result |
| GET | `/models/benchmark/{model_name}` | Public | A model's benchmark history (optionally filtered by `skill_domain`) |
| POST | `/models/proposals` | Admin | Open a new advancement proposal from the latest two benchmark scans |
| GET | `/models/proposals` | Public | List proposals, optionally filtered by `stage` or `model_name` |
| GET | `/models/proposals/{id}` | Public | One proposal's full review trail |
| POST | `/models/proposals/{id}/prime-review` | Admin | Stage 1 |
| POST | `/models/proposals/{id}/cornelius-review` | Admin | Stage 2 |
| POST | `/models/proposals/{id}/human-decision` | Admin | Stage 3 (final) |

## 7. Cross-references

- `src/entities/templates/tranc3_base.py`, `t2ance_base.py`, `trance_one_base.py` — the runtime
  base classes for Tier 3/2/1 AIs (SWOT self-assessment, HIL-A approval gates, hub power-ups,
  emergency stop) this matrix's tier naming already builds on
- `t2ance/`, `trance_one/` — the `/primes` and `/sovereign` HTTP surfaces for those same tiers
- [LOCATION-FUNCTIONS.md](LOCATION-FUNCTIONS.md) — the same fixed-vs-mutable pattern applied to
  Job Descriptions instead of models
- [PERSONALITY-ARCHETYPES.md](PERSONALITY-ARCHETYPES.md) — trait targets per Location, a distinct
  concern from which model tier/variant an AI runs
- `tests/test_models_matrix.py`, `test_models_benchmark.py`, `test_models_governance.py`,
  `test_models_routes.py` — full test coverage for every layer of this document
