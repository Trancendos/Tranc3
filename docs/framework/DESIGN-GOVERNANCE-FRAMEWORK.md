# Design Governance Framework — Trancendos Platform

**Version:** 1.0.0 | **Owner:** Trancendos Platform Engineering | **Classification:** UNCLASSIFIED — PUBLIC
**Effective:** 2026-07-02 | **Review Cycle:** Quarterly | **Approver:** Platform Owner (The Citadel)

---

## 1. Purpose

This framework defines the **mandatory design, architecture, and governance artifacts**
that every Trancendos service (a "named entity" per `PLATFORM_ENTITIES.md`) must carry,
and the process by which those artifacts are authored, reviewed, approved, and kept
truthful against the running code.

It exists to prevent two failure modes:

1. **Undocumented services** — code with no design intent, no ownership, no runbook.
2. **Fictional documentation** — polished docs describing behaviour the code does not
   implement. Per platform principle, **a doc that overstates the code is a defect**.

> **Truthfulness rule.** Every artifact states its `Implementation Status` using the
> canonical status string from `PLATFORM_ENTITIES.md` verbatim, and the framework maps
> that to one of three **gate tiers** (§2.1) which drive artifact requirements.
> A `Planned`-tier service gets a **Charter + Standards + Policy + RACI + TFM** pack only
> (intent-level); it does **not** get a DDD/TASD/Runbook claiming implemented behaviour
> until code exists.

### 2.1 Status vocabulary → gate tier (normalization)

`PLATFORM_ENTITIES.md` uses several canonical status labels. Docs keep that exact label
(it carries deployment nuance), but the honesty gate and any CI automation operate on the
three **gate tiers** below. This is the single source of truth for the mapping:

| Canonical status label (from `PLATFORM_ENTITIES.md`) | Gate tier | Required pack |
|------------------------------------------------------|-----------|---------------|
| `✅ In repo`, `✅ Self-hosted`, `✅ Deployed`, `✅ Integrated` | **Live** | Full 11-artifact pack, code-grounded |
| `🔧 Partial`, `🔧 Migrating`, `🔧 Self-hosted` | **Partial** | Live pack, scoped to what exists; gaps flagged |
| `🔧 Planned` | **Planned** | GOV + RACI + TFM + POL + STD only |

> A `✅` label always maps to **Live**; a `🔧` label maps to **Partial** unless it is
> exactly `🔧 Planned`, which maps to **Planned**. Automation keys off the emoji + the
> word `Planned`, so new nuance labels remain forward-compatible.

---

## 2. Artifact Catalogue

Each service maintains a **Doc Pack** under `docs/services/<service-slug>/`. The pack
comprises the following artifacts. The template for each lives in
`docs/framework/SERVICE-DOC-PACK-TEMPLATE.md`.

| # | Artifact | Code | Answers | Required at status |
|---|----------|------|---------|--------------------|
| 1 | **Detailed Design Document** | DDD | *How is it built?* Components, data model, sequence flows, error handling | ✅ / 🔧 Partial |
| 2 | **Technical Architecture Solutions Design** | TASD | *Why this architecture?* Options, trade-offs, decisions (ADRs) | ✅ / 🔧 Partial |
| 3 | **RACI Matrix** | RACI | *Who owns what?* Responsible/Accountable/Consulted/Informed per activity | All |
| 4 | **Solutions Integration Model** | SIM | *What does it talk to?* Upstream/downstream contracts, events, auth | ✅ / 🔧 Partial |
| 5 | **Architecture Scalability Document** | ASD | *How does it grow?* Load model, scaling levers, zero-cost limits | ✅ / 🔧 Partial |
| 6 | **Technology Framework Matrix** | TFM | *What is it made of?* Languages, libs, licences, versions, CVE posture | All |
| 7 | **Policy** | POL | *What rules govern it?* Security, data, AI, access policies | All |
| 8 | **Procedure** | PROC | *What are the repeatable steps?* Deploy, rotate, onboard, incident | ✅ / 🔧 Partial |
| 9 | **Runbook** | RUN | *What do I do at 3am?* Alerts, diagnostics, recovery, rollback | ✅ |
| 10 | **Standards** | STD | *What must it conform to?* Naming, API, logging, error, test standards | All |
| 11 | **Service Governance Charter** | GOV | *What is it for?* Mission, scope, Lead AI, SLOs, review cadence | All |

**Cross-references, not copies.** Platform-wide policies (e.g. `POL-AI-001`), standards,
and procedures already in `docs/policies/`, `docs/procedures/`, `docs/defstan/` are
**referenced**, not duplicated. A service Policy artifact records only the *deltas and
applicability* for that service. This keeps the single-source-of-truth intact and avoids
the duplication class this framework was created to eliminate.

---

## 3. Ownership Model (RACI at framework level)

| Activity | Platform Owner | Service Lead AI | Platform Eng | The Town Hall (Governance) |
|----------|:--:|:--:|:--:|:--:|
| Approve Doc Pack standard | **A** | I | R | C |
| Author service Doc Pack | I | C | **R** | I |
| Approve service TASD/DDD | **A** | C | R | C |
| Verify docs match code | I | I | **R** | **A** |
| Quarterly review | C | C | R | **A** |

Lead AI ownership per service is defined in `PLATFORM_ENTITIES.md` (e.g. The Spark →
Norman Hawkins). The Lead AI is **Consulted** on design and **Informed** on changes;
accountability for correctness rests with Platform Engineering and The Town Hall.

---

## 4. Lifecycle

```
 Draft ──► Peer Review ──► Governance Gate ──► Approved ──► Live
   ▲                          (Town Hall)                    │
   └──────────────── Quarterly re-verification ◄─────────────┘
```

1. **Draft** — authored from the template, grounded in the actual code (cite files/lines).
2. **Peer Review** — a second engineer confirms every claim is backed by code or config.
3. **Governance Gate** — The Town Hall (CranBania board) checks completeness + status honesty.
4. **Approved** — merged; artifact header stamped with approver + date.
5. **Re-verification** — each quarter, or on any material change, docs are re-checked
   against `main`. Drift is a nonconformity (tracked per `docs/governance/`).

**Automation hook (planned):** a CI check (`scripts/verify_doc_pack.py`, TBD) asserts that
every ✅/🔧-Partial entity in `PLATFORM_ENTITIES.md` has the required artifacts present,
failing the build on gaps — the same pattern already used for entity-name linting.

---

## 5. Standards & Conventions

- **Naming & file layout:** the **default** is a single combined pack at
  `docs/services/<slug>/README.md` containing all artifacts as `##` sections (see The Spark
  reference pack) — this keeps a service's design in one reviewable place. For large or
  ✅-Live services where a single file becomes unwieldy, artifacts **may** be split into
  `docs/services/<slug>/<ARTIFACT>-<service-slug>.md` (e.g. `DDD-the-spark.md`), with the
  `README.md` retained as the pack index that links them. Both layouts satisfy the gate;
  choose one per service and stay consistent within it.
- **Entity names:** use canonical names only (`PLATFORM_ENTITIES.md` / `CLAUDE.md` rules).
- **Zero-cost mandate:** every ASD and TFM must state the free-tier limits and the
  hard-stop / rotation strategy — no artifact may assume a paid dependency.
- **Classification:** default `UNCLASSIFIED — PUBLIC`; secrets never appear in docs.

---

## 6. Rollout & Coverage

Coverage is tracked in `docs/services/INDEX.md`. The honest rollout order is:

1. **✅ In-repo services first** (The Spark, The Digital Grid, Infinity, The Nexus,
   The Observatory, The Workshop, The Town Hall) — full 11-artifact packs, code-grounded.
2. **🔧 Partial services** — DDD/TASD scoped to what exists; gaps flagged, not faked.
3. **🔧 Planned services** — Charter + Standards + Policy only, until code lands.

The Spark (`docs/services/the-spark/`) is the **reference implementation** of a complete,
code-grounded pack. New packs are cloned from the template and from that exemplar.

---

## 7. Review History

| Date | Reviewer | Action |
|------|----------|--------|
| 2026-07-02 | Trancendos Platform Engineering | Initial framework — artifact catalogue, RACI, lifecycle, rollout |
