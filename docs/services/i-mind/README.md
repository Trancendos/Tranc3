# Service Doc-Pack — I-Mind

| Field | Value |
|---|---|
| **Entity** | I-Mind |
| **Lead AI** | Elouise |
| **Status** | 🔧 Planned (per `CLAUDE.md` service table) |
| **Foundation** | custom (planned `src/imind/`) |

> **Truthfulness / gate tier.** Per `docs/framework/DESIGN-GOVERNANCE-FRAMEWORK.md` §2.1, this
> entity's `CLAUDE.md` status maps to the **Planned** gate tier, which requires only
> **GOV + RACI + TFM + POL + STD** (intent-level; no DDD/TASD/SIM/ASD/RUN — no code exists yet for this entity).
> Do not read this pack as describing implemented behaviour.

## 1. Service Governance Charter (GOV)

- **Mission:** sensitivity-to-emotion engine — emotional-context detection for platform interactions.
- **In scope (when built):** the scope implied by the Foundation above; no implementation
  exists yet in this repo, though `src/imind/` is the planned code path.
- **Out of scope:** anything not named in the mission above; scope will be re-chartered once
  implementation begins, per the framework's Planned→Partial promotion process.
- **Lead AI (Tier 3):** Elouise — role per `PLATFORM_ENTITIES.md`.
- **Owner (RACI-A):** Platform Owner (Trancendos), delegated to Elouise.
- **Review cadence:** re-review at Planned→Partial promotion (i.e. when code first lands),
  or quarterly per framework default, whichever is sooner.
- **Dependencies (hard):** none yet — no code exists to depend on anything.

## 2. RACI Matrix

| Activity | Platform Owner | Elouise | Platform Engineering | The Town Hall |
|---|---|---|---|---|
| Charter approval / scope changes | **A** | C | R | I |
| Initial implementation kickoff | **A** | **R** | C | I |
| Promotion to Partial/Live tier (doc-pack upgrade) | **A** | C | **R** | I |

## 3. Technology Framework Matrix (TFM)

| Concern | Planned choice | Zero-cost stance | Status |
|---|---|---|---|
| Foundation | custom (planned `src/imind/`) | self-hosted / OSS | not yet integrated |

No dependency has been added to this repo for I-Mind; the Foundation column records
platform intent (per `CLAUDE.md`'s Recommended Open Source Foundations table where applicable),
not a committed integration.

## 4. Policy (POL)

- Once implemented, I-Mind MUST comply with platform-wide policy (`docs/defstan/`,
  `POL-AI-001`) — no service-specific policy delta is recorded yet because no implementation
  exists to have deltas from the baseline.
- Zero-cost mandate applies: any future integration must pass `scripts/zero_cost_audit.py`
  before deployment, per The Citadel's deploy gate (`docs/services/the-citadel/`).

## 5. Standards (STD)

- On implementation, I-Mind MUST get a full doc-pack upgrade (DDD, TASD, SIM, ASD, PROC, RUN)
  per `docs/framework/DESIGN-GOVERNANCE-FRAMEWORK.md` §2.1's Partial/Live tier requirements —
  this Planned-tier pack is not a substitute and must not be treated as implementation sign-off.
- Naming: use the canonical name "I-Mind" exactly as it appears in `CLAUDE.md`'s service table
  and `PLATFORM_ENTITIES.md` — no informal aliases in code, routes, or logs once built.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-04 | Claude (session) | `CLAUDE.md` service table (status, Lead AI, Foundation), `PLATFORM_ENTITIES.md` (identity), repo search confirming no `src/imind/` implementation exists | Confirmed Planned-tier / no-code status; pack intentionally scoped to GOV+RACI+TFM+POL+STD only per framework §2.1 |
