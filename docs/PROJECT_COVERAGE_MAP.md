# Project Structure → Documentation Coverage Map

> **Purpose.** Maps the actual code layout of this repository to its documentation, so we can
> see at a glance where code exists without docs (the gaps) and where to spend the next
> documentation effort. This is the output of the coverage-mapping step of the documentation
> audit (`docs/WIKI_INDEX.md` is the index this map plugs into; it supersedes the one-off
> `DOC_AUDIT.md` style notes).
>
> **Method.** Enumerated every top-level code area with `ls`/`find`, then searched `docs/`,
> `wiki-content/`, and root `.md` files for references to each component. "Doc refs" counts in
> the tables below mean *mentions somewhere in the documentation tree* — a high count means the
> component is described conceptually (usually in `CLAUDE.md`, `docs/architecture/TOPOLOGY_MAP.md`,
> or a `docs/services/<entity>/` doc-pack), not that it has a dedicated page.
>
> **Reference automation.** Two scripts already encode structural knowledge the platform
> maintains about itself:
> - `scripts/port_registry_validate.py` — regression guard that checks `CLAUDE.md`'s worker
>   port table against `docker-compose.production.yml` (issue #188).
> - `scripts/zero_cost_audit.py` — validates `src/zero_cost/registry.py` (capabilities,
>   rotation chains, hard stops) and asserts `docs/ZERO_COST_VENDOR_MATRIX.md` exists.
> Both are quoted below where relevant.

---

## 1. Coverage scoreboard

| Area | Code location | Approx. size | Primary doc(s) | Coverage |
|------|---------------|-------------|----------------|----------|
| Core API | `api.py`, `auth.py` | 1 file, ~100 KB | `CLAUDE.md`, `docs/API_REFERENCE.md`, `docs/architecture/TOPOLOGY_MAP.md` | ✅ Strong |
| `src/` Python packages | `src/` (90 top-level dirs) | ~90 modules | `CLAUDE.md`, `TOPOLOGY_MAP.md`, `docs/services/*`, `docs/architecture/*` | 🟡 Conceptual (no per-module pages) |
| Workers | `workers/` | 92 dirs | `workers/README.md`, `docs/services/*` (43 packs) | 🟡 Entities covered, dirs not 1:1 |
| Dimensional framework | `Dimensional/` | 17 `.py` + 14 subpkgs | `wiki-content/Historical-PHASE27_DIMENSIONAL_NEXUS.md` (historical) | 🔴 Weak (no live arch doc) |
| Web frontend | `web/` | React/Vite app | `docs/DESIGN_SYSTEM.md`, wiki "Frontend Development" | 🟡 Partial (no per-component docs) |
| aeonmind | `aeonmind/` | Go/Py/Rust/WASM | `aeonmind/docs/AI_DEFINITIONS_DICTIONARY.md` | ✅ Strong |
| Docker Compose | `docker-compose*.yml` (9 files) | 9 files | `TOPOLOGY_MAP.md`, `docs/DEPLOYMENT_GUIDE.md`, `DEPLOYMENT_RUNBOOK.md` | 🟡 Prod strong, others light |
| CI/CD | `.github/workflows/` (16), `.forgejo/workflows/` (34) | 50 files | `CLAUDE.md` CI/CD section, `docs/workflow-action-sha-audit.md` | 🟡 Partial |
| Other top-level code | `tranc3-bots/`, `shared_core/`, `rust_extensions/`, `tranc3-ts/`, `t2ance/`, `trance_one/`, `cloudflare/` | 7 areas | `CLAUDE.md`, `cloudflare/README.md`+`DEPLOY.md` | 🔴 Mostly undocumented (no READMEs) |
| Bots | `tranc3-bots/` (12 bot types) | 1 package | `CLAUDE.md` "BotRegistry" section | 🟡 Conceptual only |
| Scripts | `scripts/` (~150 files) | 150 | referenced ad hoc; `docs/` runbooks use some | 🔴 Undocumented as a set |

Legend: ✅ strong · 🟡 partial/conceptual · 🔴 weak/absent.

---

## 2. Component → Documentation mapping

### 2.1 Core API & entrypoints

| Component | Path | Doc location | Status |
|-----------|------|--------------|--------|
| FastAPI app | `api.py` | `CLAUDE.md` (Backend `api.py`), `docs/API_REFERENCE.md`, `TOPOLOGY_MAP.md` | ✅ |
| Auth bootstrap | `auth.py` | `CLAUDE.md` (Required Env Vars), `TOPOLOGY_MAP.md` (JWT auth flow) | ✅ |
| Alt entrypoints | `main_2060.py`, `train.py`, `verify_phase10.py` | none (internal/legacy) | 🔴 |
| `tranc3_enhanced_config.yaml`, `tranc3_2060_config.yaml` | root | none | 🔴 |

### 2.2 `src/` modules (sampled; all 90 top-level dirs exist)

Most `src/` packages are *described* in `CLAUDE.md` / `TOPOLOGY_MAP.md` but have **no dedicated
reference page**. Doc-ref counts below = number of doc/wiki files that mention the module name
(signal of conceptual coverage, not a guarantee of accuracy):

| Module | Doc refs | Notes |
|--------|---------:|-------|
| `core/` (Tranc3Engine) | 176 | ✅ Strong (`CLAUDE.md`, bootstrap-mode notes) |
| `auth/` + `zero_trust` | 174 + 22 | ✅ (`CLAUDE.md`, Zero Trust IAM) |
| `entities/` | 131 | ✅ (`PLATFORM_ENTITIES.md`, `src/entities/platform.py`) |
| `security/` | 129 | ✅ (`CLAUDE.md`, `SECURITY.md`) |
| `workers/` (registry) | 171 | ✅ |
| `routers/` | 77 | 🟡 mount list in `CLAUDE.md` |
| `registry/` (BotRegistry) | 97 | 🟡 |
| `models/` | 55 | 🟡 (`docs/governance/TRANCENDOS-MODELS-MATRIX.md`) |
| `compliance/` | 151 | ✅ (`docs/compliance/`, Magna Carta) |
| `workflow/` (Digital Grid) | 105 | ✅ (`docs/services/the-digital-grid/`) |
| `nanoservices/` | 33 | 🟡 (`CLAUDE.md`, port 8001) |
| `mcp/` (The Spark) | 29 | ✅ (`docs/services/the-spark/`) |
| `mesh/`, `event_bus/`, `ai_gateway/` | 40 / 20 / 30 | ✅ (`CLAUDE.md` Named subsystems) |
| `bio_neural/` (Luminous), `quantum/` (Think Tank) | 18 / 35 | 🟡 |
| `personality/` (Turing's Hub) | 33 | 🟡 |
| `cryptex/` | 25 | ✅ (`docs/services/cryptex/`) |

**Gaps within `src/`:** the long tail of ~60 smaller modules — `access/`, `adaptive/`,
`admin_os/`, `analytics/`, `backup/`, `benchmark/`, `capacity/`, `cellular` (Dimensional),
`citadel/`, `cloud/`, `cmdb/`, `coding/`, `deepmind/`, `distributed/`, `evaluation/`,
`evolution/`, `fluidic/`, `gbrain/`, `healing/`, `holographic/`, `imind/`, `intelligence/`,
`knowledge/`, `lab/`, `library/`, `master/`, `master_worker/`, `neural/`, `nexus/`,
`notebooks/`, `relations/`, `resilience/`, `roles/`, `search/`, `section7/`, `skills/`,
`storage/`, `studio/`, `taimra/`, `tensorflow_core/`, `training/`, `tranquility/`, `vector/`,
`vrar3d/`, `warp_radio/` — are **not** individually documented. Many are thin or experimental;
the audit should mark which are live vs. stub before writing pages.

### 2.3 Workers — `workers/`

There are **92 directories** under `workers/`. Conventions observed:

- **No per-worker README exists** — `workers/README.md` is a single top-level file (3.9 KB), not
  one per service. So the requested "each worker should have a README" norm is **not met**.
- Documentation is instead centralized as **43 service doc-packs** under `docs/services/`
  (governed by `docs/services/INDEX.md` + `docs/framework/DESIGN-GOVERNANCE-FRAMEWORK.md`),
  each carrying a multi-artifact pack (GOV/RACI/TFM/DSM/ESM/POL/PROC/RUN/STD …). `INDEX.md`
  reports **43/43 named entities** now carry a Deployment Scope Matrix (DSM) and Environment
  Support Matrix (ESM) — i.e. the *canonical platform entities* are fully covered.
- The 92 directories include **Rust/auxiliary/duplicate** services that are not 1:1 with the 43
  named entities (e.g. `*-rs` Rust ports: `nexus-ws-rs`, `rate-limit-service-rs`,
  `vault-service-rs`; render workers: `blender-worker`, `ffmpeg-worker`, `remotion-render-service`,
  `triposr-worker`; generated: `_generate_workers.py`; the `README.md` itself). After excluding
  those and matching naming variants (e.g. `artifactory-service` ↔ `the-artifactory`,
  `basement` ↔ `the-basement`, `cranbania` ↔ `the-town-hall`, `infinity-void` ↔ `the-void`), a
  meaningful set of **~45–50 worker directories have neither a README nor a dedicated
  `docs/services/` page**. Representative examples:

| Undocumented worker dir | Suggested doc-pack |
|-------------------------|--------------------|
| `analytics-service`, `audit-service`, `backup-service`, `cache-service`, `cdn-service`, `config-service`, `email-service`, `geo-service`, `health-aggregator`, `identity-service`, `ledger-service`, `mlflow-service`, `model-router-service`, `notifications`, `orders-service`, `payments-service`, `products-service`, `queue-service`, `rate-limit-service`, `search-service`, `sms-service`, `storage-service`, `topology-service`, `users-service` | create P3 service doc-packs (these are real compose services per `CLAUDE.md` worker map) |
| `deepagents-orchestrator-service`, `dimensional-nexus-service`, `dspy-service`, `haystack-service`, `langchain-integration-service`, `llamaindex-service`, `litellm-service`, `sentinel-station-service`, `skills-benchmark-service`, `swarm-coordinator-service`, `workflow-engine-service` | AI-framework / orchestration packs |
| `gateway-service`, `api-gateway`, `infinity-bridge-service`, `infinity-one-service`, `infinity-portal-service`, `infinity-admin-service`, `infinity-shards-service` | Infinity sub-service packs |
| `bullmq-queue-service`, `optional-services-health` | auxiliary/health packs |
| `*-rs` Rust ports (`nexus-ws-rs`, `rate-limit-service-rs`, `vault-service-rs`) | note in `rust_extensions`/aeonmind Rust docs |

> **Note:** A naive `comm` of `workers/` vs `docs/services/` over-reports gaps because of
> deliberate naming differences (kebab `the-artifactory` vs `artifactory-service`). The
> `docs/services/INDEX.md` honesty-gate (Live/Partial/Planned tiers) is the authoritative coverage
> source for *named entities*; the table above captures the *raw directory* gap the audit asked
> for. Reconcile both before writing new pages.

### 2.4 Dimensional framework — `Dimensional/`

| Component | Path | Doc location | Status |
|-----------|------|--------------|--------|
| Core modules (`url_validation.py`, `security.py`, `registry.py`, `path_validation.py`, `service_auth*.py`, `cross_bridge_orchestrator.py`, `three_bridge_coordinator.py`, `log_sanitize.py`, `sanitize.py`, `middleware.py`, `error_handlers.py`, `models.py`, `circuit_state.py`, `bus.py`, `optional_import.py`) | `Dimensional/*.py` (17) | scattered mentions in `docs/services/*` (taimra, the-library, docutari, …) | 🔴 no dedicated arch doc |
| Sub-packages | `architecture/`, `cellular/`, `dimensionals/`, `gas/`, `genetics/`, `hive/`, `infinity/`, `liquid/`, `middleware/`, `nexus/`, `orchestration/`, `pillars/`, `quantum/`, `reservoir/`, `security_automation/`, `swarm/` | `wiki-content/Historical-PHASE27_DIMENSIONAL_NEXUS.md` (read-only historical) | 🔴 |
| `security_automation/` | `Dimensional/security_automation/` | none live | 🔴 |

**Gap:** The Dimensional framework is a first-class subsystem (14 sub-packages + 17 modules) but
has **no live architecture document** — only a historical PHASE27 page. It is not in
`docs/architecture/` and is not referenced from `TOPOLOGY_MAP.md`.

### 2.5 Web frontend — `web/`

| Component | Path | Doc location | Status |
|-----------|------|--------------|--------|
| App shell / routing | `web/src/App.tsx`, `AppRouter.tsx`, `pages/`, `components/`, `store/`, `contexts/`, `hooks/`, `lib/`, `trancendos/`, `config/`, `types/` | `docs/DESIGN_SYSTEM.md`, wiki "Frontend Development" page | 🟡 Partial |
| Design system | `web/src`, `tailwind.config.js`, `DESIGN_SYSTEM.md` | `docs/DESIGN_SYSTEM.md` | ✅ |
| Build/CI | `web/Dockerfile`, `vite.config.ts`, `package.json` | `.github/workflows/frontend-build.yml`, `.forgejo/workflows/frontend-build.yml` | 🟡 |
| Stories/tests | `web/src/stories/`, `web/src/test/` | none | 🔴 |

**Gap:** No per-route or per-component documentation; only global design tokens and build notes.
No frontend architecture doc describing the SPA↔API contract beyond the wiki "Frontend
Development" page.

### 2.6 aeonmind — `aeonmind/`

| Component | Path | Doc location | Status |
|-----------|------|--------------|--------|
| Taxonomy dictionary | `aeonmind/docs/AI_DEFINITIONS_DICTIONARY.md` | ✅ (6-tier HUMAN→ORCHESTRATOR→PRIME→AI→AGENT→BOT) |
| Go module | `aeonmind/go/` (`cmd/`, `orchestrator/`, `proto/`) | referenced in `CLAUDE.md` "AeonMind" note + dictionary | 🟡 |
| Python adaptive | `aeonmind/python/` (`aeonmind/`, `tests/`) | 🟡 |
| Rust runtime | `aeonmind/rust/` | 🟡 (CI-scanned, not deployed per `CLAUDE.md`) |
| WASM | `aeonmind/wasm/` | 🟡 |

**Note:** `CLAUDE.md` explicitly warns not to conflate AeonMind's tier vocabulary with
`PLATFORM_ENTITIES.md`'s tiers. The dictionary doc is the single source of truth and is adequate.

### 2.7 Docker Compose — `docker-compose*.yml`

| File | Purpose | Doc location | Status |
|------|---------|--------------|--------|
| `docker-compose.production.yml` (195 KB) | Full prod stack (29 workers + infra) | `TOPOLOGY_MAP.md`, `CLAUDE.md` worker map, `port_registry_validate.py` | ✅ |
| `docker-compose.yml` | Default/dev base | `docs/DEPLOYMENT_GUIDE.md` | 🟡 |
| `docker-compose.development.yml` | Dev tier | `DEPLOYMENT_GUIDE.md`, ESM in `docs/services/INDEX.md` | 🟡 |
| `docker-compose.uat.yml` | UAT tier | `DEPLOYMENT_GUIDE.md`, ESM | 🟡 |
| `docker-compose.optional-services.yml` | Optional services | `CLAUDE.md`, `scripts/optional-services.sh` | 🟡 |
| `docker-compose.oss-foundations.yml` | OSS foundation services | `ZERO_COST_VENDOR_MATRIX.md`, `CLAUDE.md` foundations | 🟡 |
| `docker-compose.planned-entities.yml` | Planned entities (not live) | none | 🔴 |
| `docker-compose.storage.yml` | Storage (MinIO/IPFS) | `CLAUDE.md` storage section | 🟡 |
| `docker-compose.self-hosted.yml` | Self-hosted path | `CLAUDE.md` Fortiere section | 🟡 |

**Gap:** `docker-compose.planned-entities.yml` has no accompanying doc explaining what is planned
vs. live; service-to-compose mapping is only implicit.

### 2.8 CI/CD — `.github/workflows/` & `.forgejo/workflows/`

| Area | Count | Doc location | Status |
|------|------:|--------------|--------|
| `.github/workflows/` | 16 | `CLAUDE.md` CI/CD section (a SHA-pin audit exists on the code-scanning-remediation convoy; not yet on this branch) | 🟡 |
| `.forgejo/workflows/` | 34 | `CLAUDE.md` CI/CD section; `.forgejo/workflows/dependency-scanner.yml` referenced in `CLAUDE.md` | 🟡 |

**Gap:** No index of *what each workflow does* or the division of labour between GitHub Actions
(kept for PR status checks, CodeQL, Pages/Wiki) and Forgejo (primary deploy/security). The
only workflow-specific doc is `docs/workflow-action-sha-audit.md`.

### 2.9 Other top-level code areas

| Area | Path | README | Dedicated doc | Status |
|------|------|--------|---------------|--------|
| Bots | `tranc3-bots/` (12 types) | ❌ | `CLAUDE.md` "BotRegistry" section | 🟡 |
| Shared core | `shared_core/` | ❌ | none | 🔴 |
| Rust extensions | `rust_extensions/` (`tranc3_crypto`, `tranc3_snn`) | ❌ | none | 🔴 |
| TS client | `tranc3-ts/` (`core/`, `factories/`, `hubs/`, `protocols/`, `providers/`) | ❌ | none | 🔴 |
| T2ance (Tier-2) | `t2ance/` | ❌ | `CLAUDE.md` Models Matrix | 🟡 |
| Trance-One (Tier-1) | `trance_one/` | ❌ | `CLAUDE.md` Models Matrix | 🟡 |
| Cloudflare Workers | `cloudflare/` (legacy, migrating) | ✅ `README.md` + `DEPLOY.md` | `CLAUDE.md` CF Worker sections | ✅ |
| Scripts | `scripts/` (~150) | n/a | ad hoc; some used by runbooks | 🔴 as a set |
| Tests | `tests/` | n/a | `CLAUDE.md` test commands | 🟡 |

---

## 3. Gaps summary (code without adequate docs)

1. **Per-worker READMEs absent (0/92).** Documentation is centralized in `docs/services/` doc-packs
   (43 entities) instead — a defensible model, but the raw directory gap (~45–50 worker dirs with
   neither README nor pack) should be closed or explicitly declared out-of-scope.
2. **Dimensional framework undocumented live.** 14 sub-packages + 17 modules, only a historical
   PHASE27 page. No `docs/architecture/DIMENSIONAL.md`.
3. **~60 `src/` modules lack individual pages** (conceptual coverage only). Need a live-vs-stub
   triage before authoring.
4. **Web frontend lacks route/component docs**; only design tokens + build notes.
5. **Six top-level code areas have no README at all:** `tranc3-bots/`, `shared_core/`,
   `rust_extensions/`, `tranc3-ts/`, `t2ance/`, `trance_one/`.
6. **CI/CD has no workflow index** (50 workflows, one SHA-audit doc).
7. **`docker-compose.planned-entities.yml` is undocumented** as planned-vs-live.
8. **`scripts/` (~150 files) undocumented as a set** — only individually referenced by runbooks.

---

## 4. Recommendations (prioritized)

**P0 — close the highest-risk gaps**
- Author `docs/architecture/DIMENSIONAL.md` (live architecture for the Dimensional framework),
  linking the 14 sub-packages and the bridge/orchestration coordinators. Reference
  `wiki-content/Historical-PHASE27_DIMENSIONAL_NEXUS.md` for history.
- Add a **Dimensional** section to `docs/architecture/TOPOLOGY_MAP.md` (it is currently absent).
- Decide and document the worker-doc policy: either (a) add a short `README.md` per *live* worker
  dir pointing to its `docs/services/` pack, or (b) explicitly state in `workers/README.md` that
  `docs/services/INDEX.md` is the authoritative per-service doc and list the ~45 uncovered dirs as
  "auxiliary/duplicate — not individually documented".

**P1 — broaden coverage**
- Triage the ~60 thin `src/` modules (live vs stub) and create a `docs/src/` index page listing
  each module, its responsibility, and status; expand to per-module pages only for live services.
- Add a **CI/CD workflow index** (`docs/engineering/CI_CD_WORKFLOWS.md`) describing each of the
  50 workflows and the GitHub-vs-Forgejo split.
- Document `docker-compose.planned-entities.yml` planned-vs-live status.

**P2 — peripheral areas**
- Add READMEs (or a single `docs/engineering/OTHER_CODE_AREAS.md`) for `tranc3-bots/`,
  `shared_core/`, `rust_extensions/`, `tranc3-ts/`, `t2ance/`, `trance_one/`.
- Add a web frontend architecture doc (`docs/engineering/FRONTEND_ARCHITECTURE.md`) covering
  routing, the SPA↔API contract, and the `stories/`/`test/` layout.
- Create a `docs/engineering/SCRIPTS_INDEX.md` categorizing the ~150 `scripts/` files by purpose,
  linking each to the runbook/CI that uses it.

**P3 — housekeeping**
- Extend `scripts/port_registry_validate.py` to also flag `workers/` dirs lacking a
  `docs/services/` entry (turns gap #1 into a CI-enforced check).
- Add `zero_cost_audit.py`-style existence assertions for the new docs this map recommends, so
  coverage regressions fail CI.

---

## 5. Appendix — what the system already "knows" about its structure

- `scripts/port_registry_validate.py` → encodes the `CLAUDE.md` port table ↔
  `docker-compose.production.yml` contract (issue #188). Use it as the model for a
  worker-doc-coverage check.
- `scripts/zero_cost_audit.py` → loads `src/zero_cost/registry.py`, validates rotation chains,
  and asserts `docs/ZERO_COST_VENDOR_MATRIX.md` exists. Pattern to copy for doc-existence gates.
- `docs/services/INDEX.md` → the authoritative per-entity doc-pack coverage index (43/43 with
  DSM/ESM); the real measure of *named-entity* documentation health.
- `docs/architecture/TOPOLOGY_MAP.md` → the single curated service-topology/port/data-flow map;
  the place to add Dimensional and any missing subsystem sections.
- `docs/WIKI_INDEX.md` → the documentation hierarchy this map plugs into; new pages should be
  filed under `docs/architecture/`, `docs/services/`, or `docs/engineering/` per the index.
