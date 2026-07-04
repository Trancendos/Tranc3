# Service Doc-Pack — Arcadian Exchange

| Field | Value |
|---|---|
| **Entity** | Arcadian Exchange |
| **Lead AI** | The Porter Family |
| **Status** | ✅ Deployed (per `CLAUDE.md` service table) — but no source code in this repo |
| **Foundation** | Cloudflare Worker `arcadia-exchange` (deployed; no source in this repo) |

> **Truthfulness / gate tier.** Per `docs/framework/DESIGN-GOVERNANCE-FRAMEWORK.md` §2.1, this
> entity's `CLAUDE.md` status maps to the **Live (by label)** gate tier, which requires only
> **GOV + RACI + TFM + POL + STD** (intent-level; no DDD/TASD/SIM/ASD/RUN — no source code exists in this repo for this CF Worker to ground a DDD/TASD/SIM/ASD/RUN against).
> Do not read this pack as describing implemented behaviour.

## 1. Service Governance Charter (GOV)

- **Mission:** financial exchange — procurement & resource trading.
- **In scope (when built):** the scope implied by the Foundation above; no implementation
  exists yet in this repo — this is a deployed Cloudflare Worker with no source under version control here.
- **Out of scope:** anything not named in the mission above; scope will be re-charter'd once
  implementation begins, per the framework's Planned→Partial promotion process.
- **Lead AI (Tier 3):** The Porter Family — role per `PLATFORM_ENTITIES.md`.
- **Owner (RACI-A):** Platform Owner (Trancendos), delegated to The Porter Family.
- **Review cadence:** re-review at Planned→Partial promotion (i.e. when code first lands),
  or quarterly per framework default, whichever is sooner.
- **Dependencies (hard):** none yet — no code exists to depend on anything.

## 2. RACI Matrix

| Activity | Platform Owner | The Porter Family | Platform Engineering | The Town Hall |
|---|---|---|---|---|
| Charter approval / scope changes | **A** | C | R | I |
| Initial implementation kickoff | **A** | **R** | C | I |
| Promotion to Partial/Live tier (doc-pack upgrade) | **A** | C | **R** | I |

## 3. Technology Framework Matrix (TFM)

| Concern | Planned choice | Zero-cost stance | Status |
|---|---|---|---|
| Foundation | Cloudflare Worker `arcadia-exchange` (deployed; no source in this repo) | self-hosted / OSS | not yet integrated |

No dependency has been added to this repo for Arcadian Exchange; the Foundation column records
platform intent (per `CLAUDE.md`'s Recommended Open Source Foundations table where applicable),
not a committed integration.

## 4. Policy (POL)

- Once implemented, Arcadian Exchange MUST comply with platform-wide policy (`docs/defstan/`,
  `POL-AI-001`) — no service-specific policy delta is recorded yet because no implementation
  exists to have deltas from the baseline.
- Zero-cost mandate applies: any future integration must pass `scripts/zero_cost_audit.py`
  before deployment, per The Citadel's deploy gate (`docs/services/the-citadel/`).

## 5. Standards (STD)

- On implementation, Arcadian Exchange MUST get a full doc-pack upgrade (DDD, TASD, SIM, ASD, PROC, RUN)
  per `docs/framework/DESIGN-GOVERNANCE-FRAMEWORK.md` §2.1's Partial/Live tier requirements —
  this Planned-tier pack is not a substitute and must not be treated as implementation sign-off.
- Naming: use the canonical name "Arcadian Exchange" exactly as it appears in `CLAUDE.md`'s service table
  and `PLATFORM_ENTITIES.md` — no informal aliases in code, routes, or logs once built.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-04 | Claude (session) | `CLAUDE.md` service table (status, Lead AI, Foundation), `PLATFORM_ENTITIES.md` (identity), repo search confirming no `arcadian_exchange` implementation exists | Confirmed ✅-labelled status but no in-repo source; pack scoped to GOV+RACI+TFM+POL+STD only per framework §2.1 pending source being added to this repo |
