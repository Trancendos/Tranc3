# Service Doc-Pack — Royal Bank of Arcadia

| Field | Value |
|---|---|
| **Entity** | Royal Bank of Arcadia |
| **Lead AI** | Dorris Fontaine |
| **Status** | ✅ Deployed (per `CLAUDE.md` service table) — but no source code in this repo |
| **Foundation** | Cloudflare Worker `arcadia-royal-bank` (deployed; no source in this repo) |

> **Truthfulness / gate-tier exception.** Per `docs/framework/DESIGN-GOVERNANCE-FRAMEWORK.md` §2.1,
> this entity's `✅ Deployed` `CLAUDE.md` status maps to the **Live** gate tier, which normally
> **requires the full 11-artifact, code-grounded pack** — not the 5-artifact set below. This pack
> is an **explicit, temporary exception** to that requirement: no source code for this Cloudflare
> Worker exists in this repo, so DDD/TASD/SIM/ASD/PROC/RUN cannot be honestly grounded and are omitted
> rather than fabricated. This is a **known compliance gap against §2.1**, not a valid application
> of the Planned-tier rule — it must be closed (full pack authored) if/when this worker's source is
> ever brought into this repo, or the framework amended to define an explicit
> deployed-no-source exception tier.
> Do not read this pack as describing implemented behaviour, nor as §2.1-compliant for a Live-tier entity.

## 1. Service Governance Charter (GOV)

- **Mission:** financial hub — billing and payments.
- **In scope (when built):** the scope implied by the Foundation above; no implementation
  exists yet in this repo — this is a deployed Cloudflare Worker with no source under version control here.
- **Out of scope:** anything not named in the mission above; scope will be re-chartered once
  implementation begins, per the framework's Planned→Partial promotion process.
- **Lead AI (Tier 3):** Dorris Fontaine — role per `PLATFORM_ENTITIES.md`.
- **Owner (RACI-A):** Platform Owner (Trancendos), delegated to Dorris Fontaine.
- **Review cadence:** re-review at Planned→Partial promotion (i.e. when code first lands),
  or quarterly per framework default, whichever is sooner.
- **Dependencies (hard):** none yet — no code exists to depend on anything.

## 2. RACI Matrix

| Activity | Platform Owner | Dorris Fontaine | Platform Engineering | The Town Hall |
|---|---|---|---|---|
| Charter approval / scope changes | **A** | C | R | I |
| Initial implementation kickoff | **A** | **R** | C | I |
| Promotion to Partial/Live tier (doc-pack upgrade) | **A** | C | **R** | I |

## 3. Technology Framework Matrix (TFM)

| Concern | Planned choice | Zero-cost stance | Status |
|---|---|---|---|
| Foundation | Cloudflare Worker `arcadia-royal-bank` (deployed; no source in this repo) | self-hosted / OSS | not yet integrated |

No dependency has been added to this repo for Royal Bank of Arcadia; the Foundation column records
platform intent (per `CLAUDE.md`'s Recommended Open Source Foundations table where applicable),
not a committed integration.

## 4. Policy (POL)

- Once implemented, Royal Bank of Arcadia MUST comply with platform-wide policy (`docs/defstan/`,
  `POL-AI-001`) — no service-specific policy delta is recorded yet because no implementation
  exists to have deltas from the baseline.
- Zero-cost mandate applies: any future integration must pass `scripts/zero_cost_audit.py`
  before deployment, per The Citadel's deploy gate (`docs/services/the-citadel/`).

## 5. Standards (STD)

- On implementation, Royal Bank of Arcadia MUST get a full doc-pack upgrade (DDD, TASD, SIM, ASD, PROC, RUN)
  per `docs/framework/DESIGN-GOVERNANCE-FRAMEWORK.md` §2.1's Partial/Live tier requirements —
  this charter-only pack is not a substitute and must not be treated as implementation sign-off.
- Naming: use the canonical name "Royal Bank of Arcadia" exactly as it appears in `CLAUDE.md`'s service table
  and `PLATFORM_ENTITIES.md` — no informal aliases in code, routes, or logs once built.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-04 | Claude (session) | `CLAUDE.md` service table (status, Lead AI, Foundation), `PLATFORM_ENTITIES.md` (identity), repo search confirming no `royal_bank_of_arcadia` implementation exists | Confirmed ✅-labelled status but no in-repo source; pack scoped to GOV+RACI+TFM+POL+STD only per framework §2.1 pending source being added to this repo |
