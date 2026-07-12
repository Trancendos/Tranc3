# Design Governance Framework — Trancendos Platform

**Version:** 1.1.0 | **Owner:** Trancendos Platform Engineering | **Classification:** UNCLASSIFIED — PUBLIC
**Effective:** 2026-07-11 | **Review Cycle:** Quarterly | **Approver:** Platform Owner (The Citadel)

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
> canonical status label from the service table in **`CLAUDE.md`** verbatim (that table —
> not `PLATFORM_ENTITIES.md`, which carries identity/ownership only — is the source of
> the ✅/🔧 status). The framework maps that label to one of three **gate tiers** (§2.1)
> which drive artifact requirements. A `Planned`-tier service gets a
> **GOV + RACI + TFM + DSM + ESM + POL + STD** pack only (intent-level); it does **not** get a
> DDD/TASD/Runbook claiming implemented behaviour until code exists.
>
> **Source split:** identity/ownership (canonical name, Lead AI, PID) → `PLATFORM_ENTITIES.md`
> / `src/entities/platform.py`; implementation status (✅/🔧) → `CLAUDE.md` service table.
> The status→gate-tier normalization that drives artifact requirements is defined in §2.1.

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
| 7 | **Deployment Scope Matrix** | DSM | *Where can this run?* Cloud-Only / Hybrid / Local-Only topology, mode-awareness, data locality, per-mode blockers | All |
| 8 | **Environment Support Matrix** | ESM | *Which SDLC environments actually run this?* Dev / UAT / Production coverage, grounded against the three `docker-compose.*.yml` files | All |
| 9 | **Policy** | POL | *What rules govern it?* Security, data, AI, access policies | All |
| 10 | **Procedure** | PROC | *What are the repeatable steps?* Deploy, rotate, onboard, incident | ✅ / 🔧 Partial |
| 11 | **Runbook** | RUN | *What do I do at 3am?* Alerts, diagnostics, recovery, rollback | ✅ |
| 12 | **Standards** | STD | *What must it conform to?* Naming, API, logging, error, test standards | All |
| 13 | **Service Governance Charter** | GOV | *What is it for?* Mission, scope, Lead AI, SLOs, review cadence | All |

**Environment Support Matrix — grounding.** ESM answers a distinct question from DSM: DSM is
about *physical location* (Cloud-Only/Hybrid/Local-Only); ESM is about *SDLC promotion stage*
(Dev/UAT/Production) — an orthogonal axis. The platform has exactly three environment-tier
compose files: `docker-compose.development.yml` (a small fixed set — `api`, `redis`,
`infinity-ws`, `infinity-auth`, `infinity-ai`, `mailhog`), `docker-compose.uat.yml` (a superset
adding, among others, `vault`, `users-service`, `monitoring`, `the-grid`, `products-service`,
`orders-service`, `payments-service`, `prometheus`, `grafana`, `seed-data`), and
`docker-compose.production.yml` (the full platform — do not hardcode an exact count here, since
it drifts; see `docs/services/INDEX.md` for the current total). An ESM must state, per service: (a) whether its monolith
router (if any) has Dev/UAT coverage — true for every entity mounted in `api.py`, since the `api`
service is present in all three compose files running the same code; (b) whether its standalone
worker (if any) has its own service block in the Dev and/or UAT compose files by name — true only
for `infinity-ws` (The Nexus) and `infinity-auth` (Infinity) in both Dev and UAT, and
additionally `the-grid` (The Digital Grid) and `monitoring` (The Observatory) in UAT only; every
other standalone worker (the other ~90) is Production-only — it has no Dev or UAT environment to
validate against before a production deploy. **Note on `infinity-ai`:** the Dev/UAT compose files
also include `infinity-ai` (port 8009), but that worker is the shared, cross-cutting AI Gateway
(`src/ai_gateway/`, per `CLAUDE.md`'s "Core Python Packages" table) — the same category as Service
Mesh, Event Bus, and Zero Trust IAM — not one of the 43 named entities' own logic. A legacy
Cloudflare-Worker mapping table in `CLAUDE.md` labels the old `infinity-ai-api` worker
"Luminous / AI API," but nothing in `workers/infinity-ai/` or `src/ai_gateway/` imports from or
references Luminous's own code root (`src/bio_neural/`, `src/core/`) — treat that legacy label as
informal, not an ownership claim, and do not count `infinity-ai`'s Dev/UAT presence toward
Luminous's own ESM. This is a real, checkable gap, not speculation: state it plainly rather than
assuming parity across environments. Planned-tier and
charter-only (§2.1) ESMs are intent-level only.

**Deployment Scope Matrix — grounding.** DSM answers a distinct question from ASD (which is
about *load* scaling): it is about *where the service's process(es) physically run* — the
platform recognizes exactly three deployment scopes, defined in code by
`src/platform/infrastructure_mode.py` (`PlatformInfraMode`: `CLOUD_ONLY` / `HYBRID` /
`LOCAL_ONLY`, selected via the `PLATFORM_INFRA_MODE` env var, legacy alias `SYSTEM_MODE`) and
illustrated platform-wide in `docs/architecture/infrastructure-modes.md`. A DSM must state,
per service: (a) whether the service's own code calls `PlatformInfraMode` / branches on the
mode directly (verify by grep against that entity's own code root — of the 43 named entities,
only **The Citadel** does, via `should_run_citadel_docker()`; note that mode-aware code *does*
exist elsewhere in the repo — `src/routers/adaptive.py`, `src/routers/ecosystem.py`,
`Dimensional/architecture/storage_factory.py` — but none of it is owned by one of the 43
named entities, so it must not be cited as evidence for or against any *other* entity's own
mode-awareness), (b) what actually runs and where under each of the three modes (which
`docker-compose.production.yml` service block, on which host class, whether a persistent
volume is attached), and (c) any hard per-mode blocker (e.g. a GPU/Ollama/local-hardware
dependency that has no cloud equivalent, or a Cloudflare-Worker-only foundation with no
Local-Only path). Planned-tier and charter-only (§2.1) DSMs are intent-level only — state
target mode support, not implemented
behaviour.

**Cross-references, not copies.** Platform-wide policies (e.g. `POL-AI-001`), standards,
and procedures already in `docs/policies/`, `docs/procedures/`, `docs/defstan/` are
**referenced**, not duplicated. A service Policy artifact records only the *deltas and
applicability* for that service. This keeps the single-source-of-truth intact and avoids
the duplication class this framework was created to eliminate.

### 2.1 Status vocabulary → gate tier (normalization)

The `CLAUDE.md` service table uses several status labels. Docs keep that exact label
(it carries deployment nuance), but the honesty gate and any CI automation operate on the
three **gate tiers** below. This is the single source of truth for the mapping:

| Canonical status label (from `CLAUDE.md`) | Gate tier | Required pack |
|------------------------------------------------------|-----------|---------------|
| `✅ In repo`, `✅ Self-hosted`, `✅ Deployed`, `✅ Integrated` | **Live** | Full 13-artifact pack, code-grounded |
| `🔧 Partial`, `🔧 Migrating`, `🔧 Self-hosted` | **Partial** | Live pack, scoped to what exists; gaps flagged |
| `🔧 Planned` | **Planned** | GOV + RACI + TFM + DSM + ESM + POL + STD only |

> A `✅` label always maps to **Live**; a `🔧` label maps to **Partial** unless it is
> exactly `🔧 Planned`, which maps to **Planned**. Automation keys off the emoji + the
> word `Planned`, so new nuance labels remain forward-compatible.

> **Charter-only exception (documented deviation from Live, not a fourth gate tier).** A `✅`
> label normally requires the full Live pack above, but 4 entities (The Lighthouse, The HIVE,
> Royal Bank of Arcadia, Arcadian Exchange) are `✅ Deployed` Cloudflare Workers with **no source
> code in this repo** to ground DDD/TASD/SIM/ASD/PROC/RUN against. For these, and only these, the
> required pack is reduced to **GOV + RACI + TFM + DSM + ESM + POL + STD** — the same artifact set
> as Planned-tier, despite the entity's status being Live — tracked as an explicit,
> individually-named exception, not a general-purpose escape hatch. See
> `docs/services/INDEX.md`'s "Known §2.1 gap" note for the up-to-date list and rationale. Other
> references in this document to "charter-only (§2.1)" point back to this paragraph.

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
Imfy, AID-SPK-01, with Norman Hawkins as its Tier-2 Prime). The Lead AI is **Consulted**
on design and **Informed** on changes;
accountability for correctness rests with Platform Engineering and The Town Hall.

---

## 4. Lifecycle

```text
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
   The Observatory, The Workshop, The Town Hall) — full 13-artifact packs, code-grounded.
2. **🔧 Partial services** — DDD/TASD scoped to what exists; gaps flagged, not faked.
3. **🔧 Planned services** — GOV + RACI + TFM + DSM + ESM + POL + STD only (per §2.1), until code lands.

The Spark (`docs/services/the-spark/`) is the **reference implementation** of a complete,
code-grounded pack. New packs are cloned from the template and from that exemplar.

---

## 7. Review History

| Date | Reviewer | Action |
|------|----------|--------|
| 2026-07-02 | Trancendos Platform Engineering | Initial framework — artifact catalogue, RACI, lifecycle, rollout |
| 2026-07-11 | Trancendos Platform Engineering | Added **Deployment Scope Matrix (DSM)** as artifact #7, required at all gate tiers. Every application must document its Cloud-Only, Hybrid, and Local-Only deployment scope, code-grounded against `src/platform/infrastructure_mode.py` (`PlatformInfraMode`) and `docker-compose.production.yml`. Packs bumped from 11 to 12 artifacts; see `docs/services/INDEX.md` for per-entity rollout. |
| 2026-07-11 | Trancendos Platform Engineering | Added **Environment Support Matrix (ESM)** as artifact #9 (between TFM and POL), required at all gate tiers. Every application must document its Dev/UAT/Production compose-coverage, grounded against `docker-compose.development.yml`, `docker-compose.uat.yml`, and `docker-compose.production.yml`. Packs bumped from 12 to 13 artifacts; charter-only packs from 6 to 7. See `docs/services/INDEX.md` for per-entity rollout. |
