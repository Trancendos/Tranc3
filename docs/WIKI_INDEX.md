# Trancendos Documentation Index

This file maps the full documentation landscape. Conceptual, governance, and historical
docs are staged in **`wiki-content/`** (version-controlled in this repo) and published to
the **GitHub Wiki** (trancendos/tranc3/wiki) via `scripts/publish-wiki.sh`. Code-adjacent
docs (referenced by automation, tests, or CI) stay in the repo under `docs/`.

> **Wiki publishing status.** The 62 pages under `wiki-content/` are the canonical source.
> The live GitHub Wiki is populated by running `scripts/publish-wiki.sh` (requires push
> access to `…/Tranc3.wiki.git`). Edit pages in `wiki-content/` on a branch, get them
> reviewed, then re-run the script to publish — the wiki is a *mirror* of `wiki-content/`,
> not an independently-edited source, so nothing can drift or be lost.

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
| `docs/SECURITY-ASSESSMENT.md` | PyTorch CVE risk assessment and Bandit SAST results |
| `deploy/` | Deploy scripts, DNS cutover, Vault runbook |

---

## GitHub Wiki (source: `wiki-content/` → published via `scripts/publish-wiki.sh`)

The following pages exist as real files under `wiki-content/` today and are published to the
GitHub Wiki by the script above. Navigation is generated into `wiki-content/_Sidebar.md`.

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

## Migration status — DONE (staged), publish pending

The historical/strategic/architecture docs listed above have **already been moved** into
`wiki-content/` and are now stored as **flat, GitHub-Wiki-native pages** named
`Section-Name.md` (e.g. `Architecture-FRAMEWORK.md`, `Strategy-FREE_TIER_REGISTRY.md`,
`Historical-PHASE7_ARCHITECTURE.md`) plus `Home.md` and `_Sidebar.md`. The original moves
were `R100` (100%-identical) git renames in PR #184; the pages were later flattened from
subdirectories (`architecture/`, `strategy/`, …) to flat `Section-` slugs so that GitHub
Wiki links resolve reliably (subdirectory-style links rendered as empty "create this page"
shells). No content was lost. The former root/`docs/` copies no longer duplicate them.

**To publish (or re-publish) to the live GitHub Wiki:**

```bash
scripts/publish-wiki.sh          # mirrors wiki-content/ → the GitHub Wiki, then pushes
DRY_RUN=1 scripts/publish-wiki.sh  # build the commit without pushing (preview)
```

Requires push access to `…/Tranc3.wiki.git`. To **add or edit** a wiki page: change the file
under `wiki-content/` on a branch, get it reviewed, regenerate `_Sidebar.md` if you added a
page, then re-run the script. The wiki is a mirror of `wiki-content/` — never edit it directly.

**Automated publishing:** `.github/workflows/publish-wiki.yml` runs the script automatically
on every push to `main` that touches `wiki-content/` (and supports manual dispatch), so the
live wiki stays in sync hands-free. It authenticates with the default `GITHUB_TOKEN`, or a
`WIKI_TOKEN` secret (PAT with `repo` scope) if the org restricts default-token wiki writes.
