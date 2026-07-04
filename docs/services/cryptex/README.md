# Service Doc-Pack — Cryptex

| Field | Value |
|---|---|
| **Entity** | Cryptex |
| **Lead AI** | Renik |
| **Status** | 🔧 Planned (per `CLAUDE.md` service table) |
| **Foundation** | Wazuh + MISP (self-hosted) |

> **Truthfulness / gate tier.** Per `docs/framework/DESIGN-GOVERNANCE-FRAMEWORK.md` §2.1, this
> entity's `CLAUDE.md` status maps to the **Planned** gate tier, which requires only
> **GOV + RACI + TFM + POL + STD** (intent-level; no DDD/TASD/SIM/ASD/RUN normally — **but see the correction immediately below: code
> already exists here**, and this pack is charter-only as an interim gap, not because no
> code exists).
> Do not read this pack as describing implemented behaviour.

> **Correction (2026-07-04) — this pack's "no code exists" claims are FALSE.** A PR review
> (cubic) caught that this pack asserted no implementation exists, when in fact `src/cryptex/` (10 files) + `workers/cryptex/worker.py`
> is already in this repo. `CLAUDE.md`'s `🔧 Planned` status label for this entity is **stale** —
> it has not been updated to reflect the code above. This pack remains charter-only
> (GOV+RACI+TFM+POL+STD) as an **interim, honestly-flagged gap**: the sections below still
> describe intent rather than the real implementation, because a proper Partial/Live-tier
> upgrade (code-grounded DDD/TASD/SIM/ASD/RUN citing the actual routes, modules, and — where
> applicable — worker service) has not yet been authored. Do not treat the "no implementation
> exists" language in the sections below as accurate; treat it as **not yet corrected** pending
> that upgrade. Tracked as a known follow-up in `docs/services/INDEX.md`.

## 1. Service Governance Charter (GOV)

- **Mission:** cyber defense — threat intelligence, DDoS mitigation, CVE tracking for the platform.
- **In scope (when built):** the scope implied by the Foundation above. NOTE: code already
  exists in this repo (see the correction blockquote above) but has not yet been reviewed to
  scope this section accurately — treat "the scope implied by the Foundation" as unverified
  against the real implementation.
- **Out of scope:** anything not named in the mission above; scope will be re-chartered once
  the Partial/Live-tier doc-pack upgrade is authored (code already exists — see correction
  above — the pending step is the doc upgrade, not implementation).
- **Lead AI (Tier 3):** Renik — role per `PLATFORM_ENTITIES.md`.
- **Owner (RACI-A):** Platform Owner (Trancendos), delegated to Renik.
- **Review cadence:** re-review at Planned→Partial promotion (i.e. when the doc-pack is
  upgraded to match the code that already exists — see correction above), or quarterly per
  framework default, whichever is sooner.
- **Dependencies (hard):** unverified — see correction above; not re-derived from the
  actual code in this pass.

## 2. RACI Matrix

| Activity | Platform Owner | Renik | Platform Engineering | The Town Hall |
|---|---|---|---|---|
| Charter approval / scope changes | **A** | C | R | I |
| Initial implementation kickoff | **A** | **R** | C | I |
| Promotion to Partial/Live tier (doc-pack upgrade) | **A** | C | **R** | I |

## 3. Technology Framework Matrix (TFM)

| Concern | Planned choice | Zero-cost stance | Status |
|---|---|---|---|
| Foundation | Wazuh + MISP (self-hosted) | self-hosted / OSS | **code exists, integration unverified** — see correction above |

NOTE: this claim is stale — code already exists in this repo for Cryptex (see correction
above); the Foundation column below has not yet been updated to cite it. It records
platform intent (per `CLAUDE.md`'s Recommended Open Source Foundations table where applicable),
not a committed integration.

## 4. Policy (POL)

- Once implemented, Cryptex MUST comply with platform-wide policy (`docs/defstan/`,
  `POL-AI-001`). NOTE: code already exists in this repo (see correction above); any
  service-specific policy delta has not yet been assessed against it.
- Zero-cost mandate applies: any future integration must pass `scripts/zero_cost_audit.py`
  before deployment, per The Citadel's deploy gate (`docs/services/the-citadel/`).

## 5. Standards (STD)

- On implementation, Cryptex MUST get a full doc-pack upgrade (DDD, TASD, SIM, ASD, PROC, RUN)
  per `docs/framework/DESIGN-GOVERNANCE-FRAMEWORK.md` §2.1's Partial/Live tier requirements —
  this charter-only pack — even as corrected — is not a substitute for that upgrade and
  must not be treated as implementation sign-off.
- Naming: use the canonical name "Cryptex" exactly as it appears in `CLAUDE.md`'s service table
  and `PLATFORM_ENTITIES.md` — no informal aliases in code, routes, or logs once built.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-04 | Claude (session) | `CLAUDE.md` service table (status, Lead AI, Foundation), `PLATFORM_ENTITIES.md` (identity), initial repo search | **SUPERSEDED — was wrong.** Initial search incorrectly concluded no implementation exists. |
| 2026-07-04 | Claude (session), corrected after cubic PR review | actual repo contents (`src/*`, `workers/*/worker.py` — see correction blockquote above) | **Correction: code DOES exist.** `CLAUDE.md`'s Planned label is stale. Pack remains charter-only as an interim, honestly-flagged gap pending a real Partial/Live-tier rewrite — not a valid Planned-tier no-code determination. |
