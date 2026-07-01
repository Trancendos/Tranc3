# Trancendos Documentation Index

This file maps the full documentation landscape. Conceptual, governance, and historical
docs live in the **GitHub Wiki** (trancendos/tranc3/wiki) to keep the repo tree clean.
Code-adjacent docs (referenced by automation, tests, or CI) stay in the repo.

---

## In This Repo (code-adjacent — must stay)

| File | Purpose |
|------|---------|
| `CLAUDE.md` | AI assistant instructions — read by Claude Code |
| `PLATFORM_ENTITIES.md` | Canonical service/entity names — referenced by `src/entities/platform.py` |
| `ARCHITECTURE_THREAT_MODEL.md` | STRIDE threat model — auditable alongside code changes |
| `SECURITY.md` | GitHub standard — vulnerability disclosure policy |
| `CODE_OF_CONDUCT.md` | GitHub standard — contributor conduct |
| `README.md` | Repo entry point |
| `config/estate/naming_conventions.md` | Naming rules used by automation scripts |
| `docs/runbooks/` | Operational runbooks (api-backend, disaster-recovery, zero-downtime-deploy) |
| `docs/compliance/` | Live compliance controls (ISO 27001, SOC2, GDPR, AI governance) |
| `docs/architecture/` | As-built architecture, blueprints, infrastructure modes |
| `docs/API_REFERENCE.md` | Developer API reference |
| `docs/DESIGN_SYSTEM.md` | Frontend design tokens and component guidelines |
| `deploy/` | Deploy scripts, DNS cutover, Vault runbook |

---

## GitHub Wiki (living docs — navigate at trancendos/tranc3/wiki)

### Platform Overview
- **Home** — What is Trancendos / Tranc3?
- **Platform Entities** — All 43 named services, Lead AIs, ports, and status
- **Architecture Overview** — Self-hosted zero-cost architecture, service mesh, inference pipeline
- **Deployment Topology** — Traefik, Docker Compose, Fly.io, Cloudflare Workers map

### Development Guides
- **Getting Started** — Clone, env setup, dev server, first commit
- **Branch & PR Workflow** — Branch naming, CI gates, merge strategy
- **Worker Development** — How to add a new self-hosted Python worker
- **Frontend Development** — React + Vite + Tailwind conventions, component library

### Service Runbooks (extended)
- **The Spark (MCP)** — JSON-RPC 2.0, tool registry, SSE bus
- **The Digital Grid** — DAG builder, workflow executor, event bus
- **Infinity (Auth)** — OAuth2, SSO, MFA setup and troubleshooting
- **The HIVE** — Queue coordination, agent management
- **The Void** — AES-GCM secrets, Shamir unseal procedure

### Governance & Compliance
- **Magna Carta Rules** — 9 runtime compliance rules, enforcement points
- **Change Management** — CAB workflow, PROC-CHG-001
- **Data Protection** — GDPR/ROPA, PROC-DSR-001, Privacy Impact Assessment
- **Security Policies** — POL-AI-001, POL-OPS-002, POL-PRI-001
- **Audit Evidence** — Pen test programme, policy attestation register
- **AI Governance** — EU AI Act classification, bias controls, explainability

### Strategic / Historical (read-only reference)
- **Phase Reports** — PHASE20–PHASE28 forensic reports and SWOT analyses
- **Zero-Cost Architecture Decision** — Why self-hosted over Cloudflare paid tiers
- **CF Worker Migration Roadmap** — 26+ workers being migrated to Python/FastAPI
- **Cross-Repo Synergy** — 29 infinity-adminOS packages mapped to Python equivalents
- **Research Findings** — Security CVE research, open-source library evaluations

---

## Docs to Migrate to Wiki (planned — not yet moved)

The following files in this repo are candidates for Wiki migration once the Wiki is
set up. They are kept here in the interim so nothing is lost:

- `PHASE8-11_ARCHITECTURE.md`, `PHASE*` root files
- `SWOT_PHASE24_FORENSIC.md`, `FORENSIC_REPORT_*`
- `docs/PHASE25_*`, `docs/PHASE26_*`, `docs/PHASE27_*`, `docs/PHASE28_*`
- `docs/DOC-01-*` through `docs/DOC-18-*` (project charter, mind maps, brainstorming)
- `docs/BRANCH_*`, `docs/MERGE_STRATEGY.md` (historical branch reports)
- `ARCHITECTURE_UPDATE.md`, `INFINITY_ARCHITECTURE.md`, `TIER_ARCHITECTURE.md`, `FRAMEWORK.md`
- `CF_WORKER_MIGRATION_ROADMAP.md`, `CROSS_REPO_SYNERGY.md`
- `VERIFICATION.md`, `REVERT_LOG.md`, `PROJECT_PULSE.md`
- `todo.md`, `todo_infra.md`, `tranc3-ts/todo.md`
- `SECURITY_ALERT_REGISTER.md`, `docs/SECURITY_ALERT_DISMISSALS.md`

**Migration procedure:** Copy content to the Wiki page → delete file from repo → add
the Wiki page title to the index above.
