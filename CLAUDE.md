# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Commands

```bash
# Testing
make test            # full pytest suite with coverage
make test-fast       # skip slow/integration tests
pytest tests/test_tranc3_ml.py -v  # single test file

# Targeted test suites (all produce logs/test_results.jsonl)
pytest tests/test_smoke.py -v           # fast sanity checks (<2s)
pytest tests/test_uat.py -v             # user acceptance / end-to-end journeys
pytest tests/test_chaos.py -v           # fault injection and resilience
pytest tests/test_penetration.py -v     # OWASP injection / security boundary
pytest tests/test_compliance.py -v      # error catalog, MCP protocol, GDPR
pytest tests/test_nanoservices.py -v    # nanoservice layer (port 8001)
pytest tests/test_compatibility.py -v  # JSON-RPC 2.0, Pydantic v2, serialization
pytest tests/test_validation.py -v     # input validation and schema enforcement
pytest tests/test_spark_grid_integration.py -v  # The Spark + The Digital Grid integration

# Linting
make lint            # ruff + mypy

# Dev servers
make dev-api         # FastAPI backend on :8000 (hot-reload)
make dev-web         # frontend dev server

# Database
make migrate         # apply pending Alembic migrations
make migrate-new msg="describe change"  # create a new migration

# Cleanup
make clean           # remove __pycache__, .pyc, build artefacts
```

The `tranc3-bots` sub-project has its own pyproject.toml with matching pytest config; run tests from `tranc3-bots/` with `pytest`.

## Trancendos Platform — Named Services

Every service, location, and subsystem has a canonical code name. Use ONLY these names in code, comments, routes, log messages, and documentation.

Canonical reference for all 43 platform entities: `PLATFORM_ENTITIES.md` and `src/entities/platform.py`.

**Location Functions & Job Descriptions.** Every Location has a functional Job Description title
(e.g. Royal Bank of Arcadia → Chief Financial Officer) distinct from its canonical `lead_ai` name
— see `docs/governance/LOCATION-FUNCTIONS.md`. Which AI currently holds that Job Description is
mutable at runtime via the Role Assignment Registry (`src/roles/registry.py`, SQLite-backed,
exposed at `/roles` — `src/roles/routes.py`, mounted in `api.py`), letting operators add, remove,
or reassign AIs to a role without a code change; every change is recorded in an audit history.

**Backlog Routing Register.** Which Location owns an outstanding item is a Town Hall
decision, not a lookup: `src/townhall/routing.py` (SQLite-backed, exposed at
`/townhall/routing` — `src/townhall/routing_routes.py`, mounted in `api.py`) records the
Location, the named authority, the written reason and the Location's solution pack, emits
`townhall.item.routed` to The Observatory, and never overwrites — a re-route supersedes and
both rows stay in `routing_history`. It refuses a Location that is not one of the 43, and one
with no solution pack, because routing work to a place with no architecture or acceptance
criteria is what "unrouted" already means. Decisions are exported to
`config/estate/backlog_routing.yaml`, which is what `scripts/build_action_backlog.py` reads in
CI — the export is also what makes a routing decision show up in a diff. Items with no
decision stay `_unrouted_` in the backlog, and that count is a queue the Town Hall owes an
answer to rather than a number assigned away by judgement.

**Trancendos Models Matrix.** Every named AI's base model is one of the platform's existing
orchestration tiers — **Trance-One** (Tier 1, Sovereign/Orchestrator, most capable), **T2ance**
(Tier 2, Primes), or **Tranc3** (Tier 3, Lead AI/AI Base, the default) — via
`get_orchestration_tier()` in `src/entities/platform.py`. An AI's base model can expand into a
named specialized variant when associated with a distinguishing skill matrix (e.g. The Dr. →
`T2ance-CODE`, George Porter → `Tranc3-Crypto`); see `docs/governance/TRANCENDOS-MODELS-MATRIX.md`
for the full base-tier/variant table, the regular benchmarking mechanism, and the governed
advancement pipeline (Prime → Cornelius → Human, each with its own % threshold) that gates a real
skill/feature improvement into a model rather than baking in routine updates unchecked. Code:
`src/models/` (`matrix.py`, `benchmark.py`, `governance.py`, `routes.py`, exposed at `/models`,
mounted in `api.py`).

**Naming rules:**
- **"The Foundation"** is the parent governance/ownership entity above Trancendos —
  introduced 2026-08-01, described fully in `docs/governance/THE-FOUNDATION.md`.
  Trancendos remains the platform/product/domain name for all ordinary references;
  use "The Foundation" only when specifically referring to the parent entity itself.
- **The platform is "Trancendos", not "Tranc3".** Trancendos is the org, domain
  (trancendos.com) and product identity; Tranc3 is the Tier-3 *model base* (with
  Trance-One and T2ance) per the Models Matrix. The repo name "Tranc3" is historical.
  `tranc3-*` service names stay only where they genuinely serve the Tier-3 engine
  (Tranc3Engine, tranc3-backend, tranc3-ai); new platform-level names use
  "trancendos-*". See `config/estate/naming_conventions.md` §0.
- **Norman Hawkins holds two different tiers and they are not interchangeable.** He is
  **The Observatory's Lead AI (Tier 3)** and separately **The Spark's Prime (Tier 2)**.
  The Spark's own Lead AI is **Imfy** (`AID-SPK-01`) — `PLATFORM_ENTITIES.md` PID-SPK and
  `src/entities/platform.py` have always said so; this table said "Norman Hawkins" until
  2026-08-22, which put a Prime in a Lead AI column. `src/personality/role_resolution.py`
  had the same collapse, mapping Imfy onto `norman-hawkins.json`, so The Spark answered in
  The Observatory's voice. Both are corrected; `imfy.json` now exists.
- "The Digital Grid" — always with a space (entity table has a known typo "The DigitalGrid"; ignore it)
- "Sashas Photo Studio" — no apostrophe (canonical; not "Sasha's Photo Studio")
- "tAimra" = location name; "tAImra" = its Lead AI name (different capitalisation — both correct)
- "The Nexus" — self-referential by design, not a documentation error: the location and its Lead
  AI share the same common name because The Nexus is unique among the 43 entities in being both a
  location and an entity in its own right (it doesn't have a separate humanoid-styled AI persona
  the way most other locations do). `PLATFORM_ENTITIES.md`'s AID-NXS-01 gives it a formal/full
  designation, **Nexus-Prime**, for entity-ID contexts — use "The Nexus" in this table and casual
  references, "Nexus-Prime" where a distinct AID is required (matching how "The Guardian" below
  gets a full title only in entity contexts).
- Infinity's Lead AI is "The Guardian (Marcus Magnolia)" — Infinity has two distinct Tier-3 AIs (`lead_ais` in `src/entities/platform.py`): The Guardian (Marcus Magnolia) and The Orb of Orisis. As Prime (Tier 2) elsewhere (The Void, The Lighthouse, The Warp Tunnel, Cryptex, The Ice Box), use "The Guardian (Marcus Magnolia)" without a qualifier — "(Anchor: Orb of Orisis)" is retired as a combined title.
- TateKing's Lead AI is "Benji Tate" and Arcadian Exchange's is "Clarence Porter" — both have several distinct Tier-3 AIs (`lead_ais`) that each run their own dedicated Agent Alpha/Beta pair (`agent_teams` in `src/entities/platform.py`): TateKing's Sam King has The Director-S/The Editor-S; Arcadian Exchange's Ann, George, Edward, and James Porter each have their own Speculator-X/Trader-X pair. Infinity (The Guardian (Marcus Magnolia) vs. The Orb of Orisis), The Lab (The Dr. (Nikolai O'denhime) vs. Slime) and The Chaos Party (The Mad Hatter vs. **Alice Dream**) also each have their own dedicated `agent_teams` pair per Lead AI — all **five** multi-AI Locations follow this same per-name pairing, none share a single team across their Lead AIs. The Chaos Party's split is the clearest illustration of why: The Mad Hatter runs adversarial testing (fault injection, chaos, boundary abuse) with The March Hare / The Dormouse, while Alice Dream runs the deterministic half (acceptance, regression, smoke) with The White Rabbit / The Looking-Glass. A chaos agent seeks variance and an acceptance agent requires none, so a shared pair would leave the repeatable suite inheriting non-determinism.
- `vesper-nightingale`, `atlas-meridian` — internal legacy profiles in `src/personality/profiles/`; NOT platform entities; unmapped pending future assignment
- "Section 7" is the **Location** (PID-DUT) and "The Dutchy" is its **Lead AI** (AID-DUT-01) — corrected 2026-07-31 by the owner; the entity table previously inverted this ("The Dutchy" as location, "Predictive lore" as Lead AI). "Predictive lore" survives only inside the primary-function descriptor and as the persona profile file `src/personality/profiles/predictive-lore.json` (which "The Dutchy" resolves to). Code paths `src/section7/`, `src/research/section7.py` and worker dir `workers/the-dutchy/` are unchanged.
- **AeonMind** (`aeonmind/` — Rust/Go/Python/WASM) — a separate, generic polyglot agent-framework
  specification, NOT one of the 43 platform entities and not a competing description of them. Its
  own canonical taxonomy lives in `aeonmind/docs/AI_DEFINITIONS_DICTIONARY.md` (a 6-tier
  HUMAN→ORCHESTRATOR→PRIME→AI→AGENT→BOT hierarchy for *building* agents generically). Only a thin
  Python bridge (`src/routers/aeonmind.py`, mounted in `api.py` as `_aeonmind_router`) is live; the
  Rust/Go/WASM agent-runtime code is scanned in CI (`.forgejo/workflows/dependency-scanner.yml`)
  but has no `docker-compose.production.yml` service of its own — it is not deployed. Do not
  conflate its Tier 0–5 vocabulary with `PLATFORM_ENTITIES.md`'s own Tier 1–5 (Sovereign/Primes/
  Lead AI/Agents/**Bots** — note `docs/architecture/infrastructure-modes.md` separately calls Tier
  5 "Nanos", a third, minor naming variant not resolved here) — they describe different things (a
  generic agent framework vs. this platform's specific named entities), even though the tier
  *numbers* loosely correspond in role (Orchestrator≈Sovereign, Prime≈Primes, AI≈Lead AI,
  Agent≈Agents, Bot≈Bots/BotRegistry).

| Code Name | Lead AI (Tier 3) | Role / Description | Status | Foundation |
|---|---|---|---|---|
| **The Spark** | Imfy | MCP server — AI tool registry, JSON-RPC 2.0 over HTTP/SSE (Norman Hawkins is The Spark's **Prime**, Tier 2 — not its Lead AI) | ✅ In repo | `src/mcp/` |
| **The Digital Grid** | Tyler Towncroft | Workflow DAG builder + executor (n8n-style) | ✅ In repo | `src/workflow/` |
| **The Void** | Prometheus | Secrets + password vault (AES-GCM) | 🔧 Migrating | `cloudflare/infinity-void/` → self-hosted |
| **The Workshop** | Larry Lowhammer | CI/CD hub — Forgejo self-hosted git + pipelines | ✅ In repo | `deploy/forgejo/` |
| **Infinity** | The Guardian (Marcus Magnolia) + The Orb of Orisis | OAuth, SSO, central user management (1 account, all services) | ✅ Self-hosted | `workers/infinity-auth/` (Port 8005) |
| **The Lighthouse** | Rocking Ricki | Cryptographic token assignment, authenticator, token scanner | ✅ Deployed | CF: `infinity-lighthouse` |
| **The HIVE** | The Queen | Data transport hub, agent + queue coordination | ✅ Deployed | CF: `infinity-hive` |
| **Royal Bank of Arcadia** | Dorris Fontaine | Financial hub — billing, payments | ✅ Deployed | CF: `arcadia-royal-bank` |
| **Arcadian Exchange** | Clarence, Ann, George, Edward & James Porter | Financial exchange — procurement & resource trading | ✅ Deployed | CF: `arcadia-exchange` |
| **The Observatory** | Norman Hawkins | Audit log — every action, change, activity on Trancendos | ✅ Self-hosted | `src/observability/`, `workers/monitoring/` |
| **Luminous** | Cornelius MacIntyre | Core platform brain — AI intelligence & orchestration engine | 🔧 Partial | `src/bio_neural/`, `src/core/` |
| **Turing's Hub** | Samantha Turing | AI creation centre — personality template creator | 🔧 Partial | `src/personality/` |
| **Arcadia** | Lilli SC | Front-end post-login, forum & email hub | 🔧 Partial | `web/` |
| **The Nexus** | The Nexus | AI communications and transfer hub | 🔧 Self-hosted | `workers/infinity-ws/` (Port 8004) |
| **The Town Hall** | Tristuran | Governance hub — PRINCE2, ITIL, Agile/Kanban, ITSM, rooms, templates | ✅ Integrated | `workers/cranbania/` (CranBania submodule, Port 8071), `src/townhall/`, `src/compliance/middleware.py` |
| **The Library** | Zimik | Knowledge base & wiki | ✅ In repo | `src/library/` (router registered in `api.py`); Outline (self-hosted) planned frontend |
| **The Academy** | Shimshi | Learning management — education & skill training | ✅ In repo | `workers/the-academy/worker.py` (standalone worker, port 8056); Custom LMS |
| **DocUtari** | Fiddsy | Document management hub | ✅ In repo | `workers/files-service/`, `workers/storage-service/` (standalone workers); Paperless-ngx planned frontend |
| **The Basement** | Gary Glowman (Glow-Worm) | Archived information store from The Observatory | ✅ In repo | `src/basement/` (router registered in `api.py`) |
| **The Studio** | Voxx | Central hub of the Creativity Center | ✅ Self-hosted | `workers/the-studio/` (Port 8069) — supersedes the old `src/studio/` router once mounted in `api.py`, unmounted (dead duplicate removed, see #56/#57 duplication-sweep pattern) |
| **Sashas Photo Studio** | Madam Krystal | Photo & image generation center | ✅ In repo | `workers/sashas-photo-studio/main.py` (standalone worker, actual Dockerfile `CMD` entrypoint — the sibling `worker.py` is a superseded Pollinations.ai-backed implementation no longer run in production); ComfyUI (primary) + AUTOMATIC1111 (fallback) backend now integrated via HTTP against self-hosted instances, offline placeholder as last resort |
| **TranceFlow** | Junior Cesar | 3D modeling & games creation studio | ✅ In repo | `workers/tranceflow/worker.py` (standalone worker); Godot Engine integration planned |
| **TateKing** | Benji Tate & Sam King | Video creation & editing platform | ✅ In repo | `workers/tateking/worker.py` (standalone worker); FFmpeg + custom UI planned |
| **Fabulousa** | Baron Von Hilton | Styling, UX, UI & design center | ✅ In repo | `workers/fabulousa-service/` (standalone worker, port 8048); Penpot planned integration |
| **Imaginarium** | Voxx | Omni-creative masterpiece wizard (Fabulousa + TateKing + TranceFlow + Studio + Photo) | ✅ In repo | `workers/imaginarium/worker.py` (standalone worker); orchestrates the others |
| **The Lab** | The Dr. (Nikolai O'denhime) + Slime | Code creation platform (Claude Code-style) | ✅ Self-hosted | `workers/the-lab/` (Port 8055) + `workers/lab-service/` (Port 8066) — supersedes the old `src/lab/` router once mounted in `api.py`, unmounted (dead duplicate removed) |
| **The Chaos Party** | The Mad Hatter + Alice Dream | Central testing platform — validation & compliance (Alice in Wonderland themed) | ✅ Self-hosted | `workers/chaos-party/worker.py` (Port 8079 — its own Traefik host rule `chaos-party.trancendos.com` + PathPrefix `/chaos-party`, one of the few Locations with a dedicated host); `tests/test_chaos.py` and `tests/e2e/` are suites it runs, not the service. `src/entities/platform.py` recorded `tests/` as its `worker_path` with no port until 2026-09-05, which made a deployed, Traefik-routed Location read as having nowhere to receive traffic |
| **The Artifactory** | Lunascene | Central artifact repository library | ✅ Self-hosted | `workers/artifactory-service/` (Port 8047, Zot OCI registry bridge) — supersedes the old `src/artifactory/` router once mounted in `api.py`, unmounted (dead duplicate removed) |
| **API Marketplace** | Solarscene | Central integration hub — REST, webhooks, OAuth | ✅ In repo | `src/apimarket/` (router registered in `api.py`); Gravitee.io planned integration |
| **Cryptex** | Renik | Cyber defense — threat intel, DDoS, CVE | ✅ In repo | `src/cryptex/` (router registered in `api.py`); Wazuh + MISP planned integration |
| **The Ice Box** | Neonach | Sandbox threat isolation & quarantine | ✅ In repo | `workers/ice-box-service/` (standalone worker, port 8046); Cuckoo sandbox planned integration |
| **The Warp Tunnel** | Rocking Ricki | Cryptographic scanner & quarantine transport | ✅ In repo | `src/security/warp_tunnel/tunnel.py`; `workers/warp-tunnel/worker.py` (standalone worker, port 8072) |
| **Warp Radio** | Rocking Ricki | Music & audio streaming integration | ✅ In repo | `src/warp_radio/station.py`; `workers/warp-radio/worker.py` (standalone worker) |
| **Section 7** | The Dutchy | Intelligence & market analysis | ✅ In repo | `src/research/` |
| **The Citadel** | Trancendos | Strategic ops & DevOps fortress | ✅ Self-hosted | Docker Compose + Traefik + Forgejo |
| **Think Tank** | Trancendos | R&D centre — solutions & forefront technologies | ✅ In repo | `src/quantum/` (router registered in `api.py`), `src/deepmind/` |
| **ChronosSphere / ArcStream** | Chronos | Task, time & scheduling management | ✅ In repo | `workers/cron-service/` (standalone worker, port 8021); Cal.com planned integration |
| **DevOcity** | Kitty | Development operations hub | ✅ Self-hosted | `workers/devocity/` (Port 8110) — supersedes the old `src/devocity/` router once mounted in `api.py`, unmounted (dead duplicate removed); custom dev portal concept |
| **Tranquility** | Savania | Wellbeing central hub | ✅ In repo | `src/tranquility/` (router registered in `api.py`) |
| **I-Mind** | Elouise | Sensitivity to emotion engine | ✅ In repo | `src/imind/` (router registered in `api.py`) |
| **tAimra** | tAImra | Opt-in digital twin & life assistant | ✅ Self-hosted | `workers/taimra/` (Port 8074) — a real, SQLite-backed superset of the old `src/taimra/` router once mounted in `api.py`, unmounted (dead duplicate removed) |
| **VRAR3D** | Entari | Standalone 3D / VR immersion | ✅ Self-hosted | `workers/vrar3d/` (Port 8060) — supersedes the old `src/vrar3d/` router once mounted in `api.py`, unmounted (dead duplicate removed); Three.js / A-Frame planned frontend |
| **Resonate** | Magdalena | Empathy engine | ✅ In repo | `src/resonate/` (router registered in `api.py`); `workers/resonate/` (Port 8076) exists but exposes a different API surface (score/conversation, not the router's status/wrap/escalate) — not yet a drop-in replacement, so the in-process mount stays for now |

### Already-deployed Cloudflare Workers (not yet in this repo)

Workers subdomain: `luminous-aimastermind.workers.dev`

| Worker name | Maps to | Modified |
|---|---|---|
| `infinity-one` | Infinity main app | 2026-03-17 |
| `infinity-auth-api` | Infinity / SSO auth | 2026-04-06 |
| `infinity-ai-api` | Luminous / AI API | 2026-04-06 |
| `infinity-os-identity` | Infinity identity | 2026-04-04 |
| `infinity-hive` | The HIVE | 2026-04-04 |
| `infinity-lighthouse` | The Lighthouse | 2026-04-04 |
| `infinity-void` | The Void | 2026-05-17 |
| `infinity-adaptive-intelligence` | Luminous / AI core | 2026-04-04 |
| `infinity-adminos-mesh` | Admin mesh | 2026-04-03 |
| `infinity-cost-monitor` | The Observatory (costs) | 2026-04-04 |
| `infinity-files-api` | DocUtari (files) | 2026-04-04 |
| `infinity-monitoring-dashboard` | The Observatory | 2026-03-17 |
| `infinity-ws-api` | The Nexus (WebSocket) | 2026-04-04 |
| `the-grid-api` | The Digital Grid API | 2026-04-04 |
| `orchestrator` | The Nexus (orchestrator) | 2026-03-17 |
| `dpid-registry` | DocUtari (IDs) | 2026-04-04 |
| `arcadia-exchange` | Arcadian Exchange | 2026-03-17 |
| `arcadia-royal-bank` | Royal Bank of Arcadia | 2026-03-17 |
| `trancendos-api-gateway` | API gateway (route: `api.trancendos.com/*`) | 2026-04-06 |
| `trancendos-api-gateway-production` | API gateway (production) | 2026-04-06 |
| `trancendos-notifications-service` | Notification service | 2026-04-06 |
| `trancendos-orders-service` | Orders / Arcadian Exchange | 2026-04-06 |
| `trancendos-payments-service` | Royal Bank / payments | 2026-04-06 |
| `trancendos-products-service` | Products catalogue | 2026-04-06 |
| `trancendos-users-service` | Infinity / user management | 2026-04-06 |
| `tranc3-ai` | AI edge proxy (no route yet — workers.dev only) | 2026-05-17 |

## Architecture

### Zero-Cost Self-Hosted Architecture (Fortiere)

The Tranc3 platform is moving from a Cloudflare Workers + paid-services architecture toward a self-hosted, zero-cost Python/FastAPI architecture — but this is gated on funding, not unconditional. Every Location (Application/Service) supports three deployment modes: **Cloud Only** (current default for all Locations — the founder's local server needs repair/replacement money that isn't available yet), **Hybrid** (part cloud/part local), and **Local/Self-Hosted** (fully on owned hardware, blocked purely on server funding). The ~26 already-live Cloudflare Workers stay in place under Cloud Only; migrating them to self-hosted Python workers (SQLite, in-memory state, local filesystem) is the Hybrid/Local path, not a committed timeline. Each Location also carries Dev/UAT/Prod per mode, with Dev/UAT provisioned on demand only once Think Tank has scoped actual R&D work — they are not standing environments. Standing policy: avoid GitHub Actions and Cloudflare Workers wherever possible (both carry rate limits that bite under prolonged/heavy use) — this is the actual reason for the zero-cost, self-hosted-by-default posture, not a rejection of the CF Workers currently in place.

**Key documents:**
- `wiki-content/Architecture-CROSS_REPO_SYNERGY.md` — Maps all 29 infinity-adminOS TypeScript packages to Python equivalents (moved from repo root during the wiki-content migration — see `docs/WIKI_INDEX.md`)
- `wiki-content/Architecture-CF_WORKER_MIGRATION_ROADMAP.md` — Full migration plan for all 26+ CF Workers to self-hosted Python, describing the Hybrid/Local path once funded (moved from repo root — see `docs/WIKI_INDEX.md`)
- `ARCHITECTURE_THREAT_MODEL.md` — STRIDE analysis and risk register for self-hosted architecture
- `docs/governance/SWOT-FORENSIC-ASSESSMENT.md` — the current SWOT and forensic assessment,
  measured rather than carried forward, with the eight findings and the repository state. The
  five prior phase assessments stay in `wiki-content/Historical-*` and are indexed from it
- `docs/governance/ACTION-BACKLOG.md` — generated sweep of every outstanding item across 44
  registers, routed to Locations and linked to their solution packs
- `docs/governance/DVMS-COMPETITIVE-ANALYSIS.md` — DVMS measured against comparable platforms
- `docs/governance/REFERENCE-NUMBERING.md` — Wiki (`WIX`, administrative) vs Knowledge Base
  (`KB`, user) reference numbering across three scopes: platform-wide `TKB000001`/`TWIX000042`,
  Location-scoped `Infi-KB-0001`, and personal `#One:KB-0001` (Infinity-One, per-user, private
  unless shared). Set by the owner 2026-09-05; implemented in `src/library/references.py`,
  which derives Location codes rather than tabulating them and extends the three colliding
  pairs (Arcadia/Arcadian Exchange, TranceFlow/Tranquility, Warp Tunnel/Warp Radio)
- `docs/architecture/topology-3d.json` — the estate's shape derived from compose, `api.py` and
  the entity register; regenerated by `scripts/build_topology_3d.py --check`
- `docker-compose.production.yml` — Full production stack (29 workers + infrastructure)
- `docs/architecture/ea-workbook/` — EA/CMDB workbook (19 CSVs + runbooks/API-spec/compliance
  docs) covering 6 real anchor services in depth (The Spark, The Digital Grid, Infinity,
  The Void, The Workshop, The Observatory) — not a full inventory of all 90+ services

**Architecture principles:**
1. **SQLite over Cloudflare D1** — Each worker owns its own database file; no shared state
2. **In-memory rate limiting over Cloudflare KV** — Token-bucket algorithm per-worker
3. **Local filesystem + IPFS over Cloudflare R2** — Docker volumes + content-addressed distribution
4. **Self-hosted Python/FastAPI over Cloudflare Workers** — No cold starts, no vendor API limits
5. **Forgejo over GitHub Actions** — Complete CI/CD sovereignty (`.forgejo/workflows/`)
6. **Vault over Cloudflare secrets** — Self-hosted secret management with Shamir unseal

### Core Python Packages (ported from infinity-adminOS)

| Package | Code path | Origin | Role |
|---|---|---|---|
| **Service Mesh** | `src/mesh/` | infinity-adminOS @trancendos/service-mesh | CircuitBreaker + ServiceMesh with health monitoring, retries |
| **Event Bus** | `src/event_bus/` | infinity-adminOS @trancendos/event-bus | Pattern-based routing, subscriptions, SQLite persistence |
| **AI Gateway** | `src/ai_gateway/` | infinity-adminOS @trancendos/ai-gateway | Priority failover (Ollama→OpenRouter→Offline), token budgets |
| **Zero Trust IAM** | `src/auth/zero_trust.py` | infinity-adminOS @trancendos/iam | Device posture, MFA, geographic policies, risk scoring |

### Named subsystems (in this repo)

| Identity | Code path | Role |
|---|---|---|
| **The Spark** | `src/mcp/` | MCP server + tool registry — JSON-RPC 2.0 over HTTP/SSE |
| **The Digital Grid** | `src/workflow/` | Workflow DAG builder + topological executor + event bus |
| **The Void** | `cloudflare/infinity-void/` | AES-GCM encrypted secrets vault (CF Worker — migrating to self-hosted) |
| **The Workshop** | `deploy/forgejo/` | Self-hosted Forgejo CI/CD at trancendos.com/the-workshop |
| **The Observatory** | `src/observability/` | Metrics, tracing, health aggregation, audit log |
| **The Nexus** | `workers/infinity-ws/` | WebSocket hub (replaces CF infinity-ws-api) — Port 8004 |
| **Infinity** | `workers/infinity-auth/` | OAuth2/SSO/MFA auth (replaces CF infinity-auth-api) — Port 8005 |
| **The Citadel** | Docker Compose + Traefik | DevOps hub, production infrastructure |
| **Luminous** | `src/bio_neural/`, `src/core/tranc3_inference.py` | AI brain, consciousness, inference |
| **Think Tank** | `src/quantum/`, `src/deepmind/` | Quantum + deep research engines |
| **Turing's Hub** | `src/personality/` | Personality profiles + spawner |
| **The Town Hall** | `workers/cranbania/` (git submodule) | CranBania — Kanban+ITSM+Prince2+Agile board, 40+ MCP tools — Port 8071, Traefik `/townhall` |
| **Magna Carta** | `compliance/magna-carta/` (git submodule) | Compliance framework — 9 runtime rules, 150+ governance docs; wired via `src/compliance/magna_carta.py` + `src/compliance/middleware.py` |

### Self-Hosted Worker Map (replacing Cloudflare Workers)

| Service | Port | Priority | Repo path | Replaces CF Worker |
|---|---|---|---|---|
| tranc3-backend | 8000 | — | `/` (root) | FastAPI main app |
| nanoservices | 8001 | — | `src/nanoservices/` | Internal proxy |
| tranc3-bots | 8080 | — | `tranc3-bots/` | 12 bot types |
| infinity-ws | 8004 | P0 | `workers/infinity-ws/` | infinity-ws-api |
| infinity-auth | 8005 | P0 | `workers/infinity-auth/` | Infinity Core Auth engine (OAuth2/SSO/MFA) |
| infinity-portal-service | 8042 | P1 | `workers/infinity-portal-service/` | Infinity Portal — front entrance + Infinity Gate (embedded) |
| infinity-one-service | 8043 | P1 | `workers/infinity-one-service/` | Infinity-One — single identity layer |
| infinity-admin-service | 8044 | P1 | `workers/infinity-admin-service/` | Infinity Admin — Admin OS |
| infinity-shards-service | 8045 | P1 | `workers/infinity-shards-service/` | Infinity Shards — pluggable entity power-ups |
| infinity-bridge-service | 8070 | P1 | `workers/infinity-bridge-service/` | Infinity Bridge — human traffic transfer hub |
| cranbania | 8071 | P1 | `workers/cranbania/` (git submodule: `https://github.com/Trancendos/CranBania`) | The Town Hall — Kanban+ITSM+Agile+Prince2, 40+ MCP tools, Traefik at `/townhall` |
| users-service | 8006 | P1 | `workers/users-service/` | trancendos-users-service |
| monitoring | 8007 | P1 | `workers/monitoring/` | infinity-monitoring-dashboard |
| notifications | 8008 | P1 | `workers/notifications/` | trancendos-notifications-service |
| infinity-ai | 8009 | P1 | `workers/infinity-ai/` | infinity-ai-api |
| the-grid | 8010 | P2 | `workers/the-grid/` | the-grid-api |
| products-service | 8011 | P2 | `workers/products-service/` | trancendos-products-service |
| orders-service | 8012 | P2 | `workers/orders-service/` | trancendos-orders-service |
| payments-service | 8013 | P2 | `workers/payments-service/` | trancendos-payments-service |
| files-service | 8014 | P2 | `workers/files-service/` | infinity-files-api |
| identity-service | 8015 | P2 | `workers/identity-service/` | infinity-os-identity |
| analytics-service | 8016 | P3 | `workers/analytics-service/` | Analytics / metrics store |
| audit-service | 8025 | P3 | `workers/audit-service/` | The Observatory audit trail |
| cache-service | 8023 | P3 | `workers/cache-service/` | Distributed cache layer |
| cdn-service | 8028 | P3 | `workers/cdn-service/` | Static asset delivery |
| config-service | 8024 | P3 | `workers/config-service/` | Central configuration |
| cron-service | 8021 | P3 | `workers/cron-service/` | ChronosSphere task scheduler |
| email-service | 8018 | P3 | `workers/email-service/` | Arcadia email hub |
| geo-service | 8027 | P3 | `workers/geo-service/` | Geographic routing |
| search-service | 8017 | P3 | `workers/search-service/` | Full-text + semantic search |
| sms-service | 8019 | P3 | `workers/sms-service/` | SMS gateway |
| storage-service | 8020 | P3 | `workers/storage-service/` | IPFS + local blob storage |
| queue-service | 8022 | P3 | `workers/queue-service/` | The HIVE task queue |
| rate-limit-service | 8026 | P3 | `workers/rate-limit-service/` | Token-bucket rate limiter |
| health-aggregator | 8029 | P3 | `workers/health-aggregator/` | Platform-wide health roll-up |
| gbrain-bridge | 8030 | P3 | `workers/gbrain-bridge/` | GBrain AI bridge |
| topology-service | 8031 | P3 | `workers/topology-service/` | Service topology graph |
| ledger-service | 8032 | P3 | `workers/ledger-service/` | Royal Bank ledger |
| model-router-service | 8033 | P3 | `workers/model-router-service/` | AI model routing |
| workflow-engine-service | 8034 | P3 | `workers/workflow-engine-service/` | The Digital Grid engine |
| skills-benchmark-service | 8035 | P3 | `workers/skills-benchmark-service/` | Turing's Hub benchmarks |
| langchain-integration-service | 8036 | P3 | `workers/langchain-integration-service/` | LangChain — chain/RAG/agent orchestration |
| llamaindex-service | 8096 | P3 | `workers/llamaindex-service/` | LlamaIndex — RAG framework / document Q&A |
| haystack-service | 8097 | P3 | `workers/haystack-service/` | Haystack — production RAG pipelines |
| dspy-service | 8098 | P3 | `workers/dspy-service/` | DSPy — programmatic LLM prompt compiler |
| deepagents-orchestrator-service | 8037 | P3 | `workers/deepagents-orchestrator-service/` | Deep agent orchestration |
| vault-service | 8038 | P3 | `workers/vault-service/` | The Void self-hosted vault (AES-GCM) |
| mlflow-service | 8039 | P3 | `workers/mlflow-service/` | MLflow experiment tracking |
| litellm-service | 8049 | P3 | `workers/litellm-service/` | LiteLLM zero-cost AI proxy (x10 provider rotation) |
| artifactory-service | 8047 | P2 | `workers/artifactory-service/` | The Artifactory — Zot OCI registry bridge |
| sentinel-station-service | 8041 | P3 | `workers/sentinel-station-service/` | Sentinel Station — platform guardian |
| swarm-coordinator-service | 8109 | P3 | `workers/swarm-coordinator-service/` | Swarm Coordinator — agent swarm management |
| dimensional-nexus-service | 8050 | P3 | `workers/dimensional-nexus-service/` | Dimensional Nexus — multi-dimensional data routing |
| hive-service | 8051 | P3 | `workers/hive-service/` | The HIVE — task queue / agent coordination |
| ice-box-service | 8046 | P3 | `workers/ice-box-service/` | The Ice Box — sandbox threat isolation |
| cryptex | 8053 | P3 | `workers/cryptex/` | Cryptex — cyber defense / threat intel |
| imaginarium | 8064 | P3 | `workers/imaginarium/` | Imaginarium — omni-creative orchestrator |
| the-studio | 8069 | P3 | `workers/the-studio/` | The Studio — central creativity hub |
| the-academy | 8056 | P3 | `workers/the-academy/` | The Academy — LMS / skill training |
| the-dutchy | 8057 | P3 | `workers/the-dutchy/` | The Dutchy — intelligence & market analysis |
| turings-hub-service | 8058 | P3 | `workers/turings-hub-service/` | Turing's Hub — AI personality creator |
| tranceflow | 8059 | P3 | `workers/tranceflow/` | TranceFlow — 3D/game creation (Godot) |
| vrar3d | 8060 | P3 | `workers/vrar3d/` | VRAR3D — Three.js / A-Frame immersion |
| tateking | 8061 | P3 | `workers/tateking/` | TateKing — video creation/editing |
| sashas-photo-studio | 8062 | P3 | `workers/sashas-photo-studio/` | Sashas Photo Studio — image generation |
| fabulousa-service | 8048 | P3 | `workers/fabulousa-service/` | Fabulousa — UX/UI/design (Penpot) |
| the-lab | 8055 | P3 | `workers/the-lab/` | The Lab — code creation platform |
| observatory | 8065 | P3 | `workers/observatory/` | The Observatory — audit trail worker |
| lab-service | 8066 | P3 | `workers/lab-service/` | The Lab extended service layer |
| library-service | 8067 | P3 | `workers/library-service/` | The Library — knowledge base / wiki |
| basement | 8068 | P3 | `workers/basement/` | The Basement — archived info store |
| devocity | 8110 | P3 | `workers/devocity/` | DevOcity — development ops hub |
| warp-tunnel | 8072 | P3 | `workers/warp-tunnel/` | The Warp Tunnel — crypto scanner / quarantine |
| warp-radio | 8073 | P3 | `workers/warp-radio/` | Warp Radio — music/audio streaming |
| taimra | 8074 | P3 | `workers/taimra/` | tAimra — opt-in digital twin |
| imind | 8075 | P3 | `workers/imind/` | I-Mind — emotion sensitivity engine |
| resonate | 8076 | P3 | `workers/resonate/` | Resonate — empathy engine |
| tranquility | 8077 | P3 | `workers/tranquility/` | Tranquility — wellbeing hub |
| backup-service | 8078 | P3 | `workers/backup-service/` | Backup — automated data backup |
| chaos-party | 8079 | P3 | `workers/chaos-party/` | The Chaos Party — central testing platform |
| infinity-void | 8002 | P3 | `workers/infinity-void/` | The Void — self-hosted AES-GCM vault |

> **Port source of truth:** the port column above is aligned to each worker's **mapped port in
> `docker-compose.production.yml`** (the deployment truth — `PORT` env / Traefik
> `loadbalancer.server.port` / published `ports:`), reconciled against `PLATFORM_ENTITIES.md` and
> each worker's actual code bind port. The P3 block `8016–8029` was previously mis-paired here (it
> had been assigned alphabetically, e.g. `email-service` shown as `8022`); it is now corrected to the
> compose mapping (`email-service` `8018`, `search-service` `8017`, `queue-service` `8022`, …). Most of
> these workers' code binds agree with compose, but **4 do not** — see the routing-defects table below.
>
> **Routing defects (issue #188) — resolved.** A prior pass flagged 4 workers whose *code-level*
> `PORT` default differed from the compose-routed port (`audit-service`, `queue-service`,
> `search-service`, `infinity-void`) as unreachable. Re-verified against each worker's actual
> **Dockerfile `CMD`**, not just its Python default: `audit-service`, `queue-service`, and
> `search-service` all hardcode `uvicorn ... --port <N>` in their Dockerfile `CMD`, which overrides
> the Python-level default at the container level — these were **never actually broken**; the
> `os.getenv("PORT", ...)` fallback is dead code, only reachable if the CMD were changed to a bare
> `python worker.py` invocation. Only `infinity-void` (`CMD ["python", "worker.py"]`, no CLI port
> override) genuinely depended on the `PORT` env value; compose set none, so it fell back to the
> code default (8082) while compose only routed to 8002. Fixed by adding an explicit `PORT=8002`
> to its compose `environment:` block (matching the value 7+ other references — monitoring,
> `workers/README.md`, wiki, `docs/vault_security.md` — already treated as canonical). Zero known
> routing defects remain in this class. Workers that read a
> *custom* port env instead of `PORT` (e.g. `hive-service` → `HIVE_PORT=8051`, `cache-service` →
> `CACHE_PORT`, `storage-service` → `STORAGE_PORT`) are **not** defects — compose sets that var, so they
> route correctly. `Dockerfile EXPOSE` values remain cosmetic (the app reads its port env at runtime);
> syncing them is also #188.

### Production Infrastructure Stack

| Component | Role | Config |
|---|---|---|
| Traefik | Reverse proxy, TLS, rate limiting | `docker-compose.production.yml` |
| Vault | Secrets management (Shamir unseal) | `docker-compose.production.yml` |
| Prometheus | Metrics collection | `monitoring/prometheus.yml` |
| Grafana | Dashboards | `monitoring/grafana/` |
| Loki + Promtail | Log aggregation | `monitoring/loki.yml`, `monitoring/promtail.yml` |
| IPFS | Distributed content storage | `docker-compose.production.yml` |

### Legacy Cloudflare Workers (being decommissioned)

| Service | Port | Repo path | Notes |
|---|---|---|---|
| tranc3-ai | edge | `cloudflare/tranc3-ai/` | CF Worker — AI edge proxy (migrating to workers/infinity-ai) |
| infinity-void | edge | `cloudflare/infinity-void/` | CF Worker — The Void encrypted vault (migrating to self-hosted) |
| trancendos-api-gateway | edge | `cloudflare/trancendos-api-gateway/` | CF Worker — `api.trancendos.com/*` (migrating to Traefik) |

### Inference pipeline (5-tier fallback via AI Gateway)

The self-hosted AI Gateway (`src/ai_gateway/`, worker `workers/infinity-ai/` on port 8009) provides an OpenAI-compatible API with priority-based failover:

```
Client → infinity-ai worker (:8009) → AIGatewayRouter
           ↓ Tier 1: Ollama (localhost:11434, zero-cost, local)
           ↓ FAIL → Tier 2: HuggingFace Inference API (free tier)
           ↓ FAIL → Tier 3: OpenRouter free models (cloud, zero-cost)
           ↓ FAIL → Tier 4: TRANC3_BACKEND_URL (Fly.io :8000)
           ↓ FAIL → Tier 5: OfflineProvider (deterministic stub response)
```

Features: LRU cache (1000 entries), token budgets per tenant, circuit breaker per provider, request logging to SQLite.

**Legacy CF Worker pipeline** (being decommissioned):
```
Client → tranc3-ai CF Worker → same 5-tier fallback
```

### Backend (`api.py`)

Entry point: `api.py`. Fails fast if `SECRET_KEY` is unset.

Key module domains under `src/`:
- `core/` — Tranc3Engine (transformer inference), startup validator, circuit breaker
- `core/ollama_adapter.py` — free local LLM fallback (Ollama)
- `core/openrouter_adapter.py` — free cloud LLM fallback (OpenRouter :free models)
- `mesh/` — **Service Mesh**: CircuitBreaker (closed/open/half-open) + ServiceMesh (registration, health, retries, httpx)
- `event_bus/` — **Event Bus**: pattern-based routing, subscriptions, SQLite persistence, batch processing
- `ai_gateway/` — **AI Gateway**: priority-based failover router, LRU cache, token budgets, provider health tracking
- `auth/zero_trust.py` — **Zero Trust IAM**: device posture, MFA, geographic policies, risk scoring
- `registry/` — BotRegistry: maps BotType → handler
- `personality/` — 47 personality profile files in `src/personality/profiles/` covering the
  platform's 47 Lead AIs (plus 6 `tranc3-*` base archetypes and the 2 unmapped legacy
  profiles `vesper-nightingale` / `atlas-meridian`). Some files are deliberately shared:
  the five Porters resolve to `the-porter-family.json`, The Dutchy to `predictive-lore.json`,
  Nexus-Prime to `the-nexus-ai.json`
- `monetisation/` — billing tiers: free (100 req/hr), pro £29 (1k/hr), business £149 (10k/hr)
- `database/` — SQLAlchemy models + Alembic migrations
- `database/vector_store.py` — Pinecone/in-memory vector store (user memory)
- `knowledge/vector_store.py` — FAISS in-process vector store (MCP/RAG)
- `auth/` — JWT, session management
- `mcp/` — **The Spark**: JSON-RPC 2.0 MCP server + tool registry + SSE bus. Routes: `/mcp/rpc`, `/mcp/sse`, `/mcp/tools`, `/mcp/health`, `/mcp/grid/status`
- `mcp/tool_rag.py` — semantic tool selection (RAG-MCP, FAISS + sentence-transformers)
- `workers/` — background worker tasks; `InferenceWorker` drains Redis queue → Tranc3Engine
- `workflow/` — **The Digital Grid**: `WorkflowBuilder` (fluent DAG DSL) + `WorkflowExecutor` (topological BFS, parallel layers) + `WorkflowEventBus`
- `errors/error_catalog.py` — canonical ErrorCode enum
- `validation/loop_validator.py` — CircuitBreaker + LoopValidator (prevents cascade failures)
- `observability/` — **The Observatory**: metrics, tracing
- `bio_neural/` — **Luminous**: consciousness engine (IIT), neuromorphic processor
- `quantum/` — **Think Tank**: quantum neural core (qiskit)
- `personality/` — **Turing's Hub**: personality matrix + profile spawner

### Tranc3Engine (bootstrap mode)

`src/core/tranc3_inference.py` loads weights from `MODEL_PATH` / `TOKENIZER_PATH`. If absent, enters **bootstrap mode**: tries Ollama → OpenRouter → honest stub. All tests use bootstrap/synthetic mode — no model weights are needed to run the test suite.

### BotRegistry (tranc3-bots)

12 bot types split into two groups:
- **Inference bots** (proxy to Tranc3Engine): GENERATE, EMBED, EMOTION, TOKENIZE, CONSCIOUSNESS, PERSONALITY, PREDICT
- **Utility bots** (standalone): CODE, MEMORY, MONITOR, SEARCH, SUMMARISE

### Cloudflare Workers

**tranc3-ai** (`cloudflare/tranc3-ai/`): edge AI proxy. KV: CACHE (`2a0e09cfd22741eeb3245607ce6e76fd`) + SESSIONS (`f321bee2495547ad9e224522f214defd`). Secrets: TRANC3_BACKEND_URL, TRANC3_AUTH_URL, ALLOWED_ORIGINS ✅

**infinity-void** (`cloudflare/infinity-void/`): AES-GCM encrypted secrets vault.
- Encryption: PBKDF2 key derivation (100k iterations, SHA-256), 256-bit keys, random IV per secret
- Storage: D1 database (`48e89d58-abd8-456b-a6ad-58ededaba597`) + KV rate limiter
- Routes: `GET /health`, `GET /vault/status`, `POST /secrets`, `POST /secrets/retrieve`, `GET /secrets`, `GET/DELETE /secrets/:id`, `GET /secrets/:id/audit`

**trancendos-api-gateway** (`cloudflare/trancendos-api-gateway/`): routes `api.trancendos.com/*`. KV: CACHE (`aa064ae803e5423db7b517400187b693`). Secrets: JWT_SECRET, TRANC3_AI_SERVICE_URL, USERS_SERVICE_URL, PRODUCTS_SERVICE_URL, ORDERS_SERVICE_URL, PAYMENTS_SERVICE_URL ✅

## Required Environment Variables

See `.env.example` for the full list. Critical ones:

```
SECRET_KEY               # FastAPI signing key (hard fail if missing)
DATABASE_URL             # Supabase PostgreSQL connection string
REDIS_URL                # Upstash Redis URL (rediss://...)
JWT_SECRET               # JWT signing key
TRANC3_BACKEND_URL       # Set on tranc3-ai CF Worker
STRIPE_SECRET_KEY        # Payment processing (optional in dev)
OLLAMA_URL               # http://localhost:11434 (free local LLM)
EMBED_MODEL              # all-MiniLM-L6-v2 (sentence-transformers)
```

## CI/CD

**Forgejo (The Workshop) is the *intended* primary CI/CD system for deployment and heavier
pipelines — but it is dormant, so today GitHub Actions is the only CI that actually runs.**
`.forgejo/workflows/` holds 32 files and 57 of their 83 jobs pin `runs-on: self-hosted`, against
an act-runner on the Citadel host that the cloud-only phase defers standing back up. None of them
execute. Describe them as the target state, not as a system currently gating anything.

`.github/workflows/` has **19** files (this said 12 until 2026-08-28 and 20 until 2026-09-03,
when `codecov.yml` was retired). Several gate this repo's PRs directly (`ci.yml`'s Ruff/lint,
Service Topology and Pytest jobs, `codeql.yml`, `trivy.yml`, `python.yml`, `rust.yml`, `go.yml`,
`production-gate.yml`, `submodule-pins.yml`, `perf-smoke.yml`).

**`codecov.yml` was retired on 2026-09-03**, not dropped: coverage is now produced by `ci.yml`'s
Pytest job, which already ran the same suite. The retired workflow existed only to run that suite
a second time with `--cov` flags attached, on every PR and every push to `main`, and it was
suppressed with `|| true` exactly as `ci.yml`'s run is — so it gated nothing either way. Its
checkout also omitted `submodules: recursive`, so tests reading real `compliance/magna-carta`
content silently took a "no suites"/404 path; the job coverage now runs in does not. `test.yml`'s
`Ruff Lint + Format` job went at the same time: it ran the identical ruff command at the identical
pin as `ci.yml`'s `lint`, and both fire on a push to `main`.

**`ci.yml`'s Pytest job no longer runs with `-x`.** With it, one teardown error stopped the run
after four tests and `|| true` reported the job green — measured on run 33808374262, whose entire
pytest output was `....E`. The suppression was not "run everything and ignore failures"; it was
"run five tests and ignore the result". The error itself was a module-level `os.environ` write in
`tests/test_backup_service.py` executing during collection; `scripts/check_test_env_isolation.py`
now fails CI on that pattern.

Two of the 19 are deliberate, narrow exceptions for GitHub-native features with no Forgejo
equivalent — `publish-wiki.yml` (GitHub Wiki) and `publish-matrix-site.yml` (GitHub Pages, publishing
`docs/architecture/ea-workbook/Trancendos_Master_Service_Matrix.xlsx`). Prefer Forgejo for new
deployment/build automation; GitHub Actions stays in play for checks GitHub itself needs to run
(PR status checks, CodeQL, Pages/Wiki) rather than being phased out.

**Seven workflows exist in both trees** — `bot-health-watchdog.yml`, `ci.yml`,
`deploy-cloudflare.yml`, `deploy-fly.yml`, `frontend-build.yml`, `perf-smoke.yml`,
`production-gate.yml`. They are meant to differ only in header comments, the runner label, and
platform hardening. Nothing enforced that until `scripts/check_workflow_drift.py` (run in
`ci.yml`'s Service Topology job), and the contract was already broken: the Forgejo copy of the
production merge gate had lost the `Dependency vulnerability census` step, so the two copies of
the platform's gate enforced materially different things. Forgejo's dormancy is what hid it —
the weaker gate is the one that takes over the day The Workshop returns. Legitimate divergences
now have to be listed with a written reason in that script's `ACCEPTED_DIVERGENCES`; an
unexplained one fails CI.

Workflow files in `.forgejo/workflows/`:
- `deploy-fly.yml` — tranc3-backend + trancendos-bots to Fly.io
- `deploy-cloudflare.yml` — tranc3-ai + infinity-void + trancendos-api-gateway CF Workers (legacy, being phased out)
- `security-scan.yml` — Python security (pip-audit, bandit, safety, ruff), Node security (npm audit), Semgrep SAST, Secret detection (gitleaks)
- `dependency-audit.yml` — Weekly + on-PR dependency vulnerability scanning (pip-audit, Safety, npm audit, worker requirements scan)

Forgejo at `trancendos.com/the-workshop`. Act-runner in `deploy/forgejo/docker-compose.yml`. Org secrets: `CF_API_TOKEN`, `FLY_API_TOKEN`.

### Pre-commit Hooks (`.pre-commit-config.yaml`)

Runs on every local commit — zero-cost security gate:
- **ruff** — Fast Python linter
- **black** — Code formatting
- **isort** — Import sorting
- **bandit** — Python security linter
- **semgrep** — Multi-language SAST
- **gitleaks** — Secret detection
- **detect-secrets** — Additional secret scanning
- **safety** — Dependency vulnerability check
- **typos** — Typo detection

### Manual deploy (from your machine)

```bash
# 1. Set Fly.io secrets (one time)
fly secrets set \
  SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')" \
  JWT_SECRET="$(python -c 'import secrets; print(secrets.token_hex(32))')" \
  DATABASE_URL="postgresql://postgres:[pw]@db.[project].supabase.co:5432/postgres" \
  REDIS_URL="rediss://:[pw]@[endpoint].upstash.io:6379" \
  ENVIRONMENT=production \
  --app tranc3-backend

# 2. Deploy backend
fly deploy --remote-only --app tranc3-backend

# 3. Deploy bots
fly secrets set REDIS_URL="..." TRANC3_ENGINE_URL="https://tranc3-backend.fly.dev" --app trancendos-bots
fly deploy --remote-only --app trancendos-bots

# 4. Redeploy CF workers (after wrangler.toml changes)
cd cloudflare/trancendos-api-gateway && npm ci && wrangler deploy
cd cloudflare/tranc3-ai && npm ci && wrangler deploy

# 5. Workshop setup (on trancendos.com server)
./deploy/forgejo/setup.sh
./deploy/forgejo/runner-setup.sh
# Add nginx config from deploy/forgejo/nginx-the-workshop.conf
```

## Deployment Topology

All Trancendos services are **subdirectories** of `trancendos.com`, not subdomains.
- `trancendos.com/the-workshop` → Forgejo (port 3456)
- `api.trancendos.com/*` → Traefik → self-hosted workers (replacing CF trancendos-api-gateway)

**Self-Hosted Production Stack** (`docker-compose.production.yml`):
- **Traefik** — Reverse proxy, TLS termination, rate limiting
- **Vault** — Secrets management with Shamir unseal
- **Prometheus** — Metrics collection from all workers
- **Grafana** — Dashboards (auto-provisioned with Prometheus + Loki datasources)
- **Loki + Promtail** — Log aggregation from Docker containers
- **IPFS** — Distributed content-addressed storage
- **38 workers** — P0/P1/P2/P3 FastAPI + uvicorn + SQLite workers (ports 8004–8038)

Fly.io apps (region `lhr`) — legacy, evaluating for migration:
- `tranc3-backend` — 256MB RAM, 1GB encrypted volume at `/app/models`
- `trancendos-bots` — 256MB RAM (the Fly app name; the source directory is `tranc3-bots/`)

Cloudflare account ID: `e0214028cb64d31232f5662548a55e4e`
Workers subdomain: `luminous-aimastermind.workers.dev`

**Zero-cost model** — no paid external services beyond committed Fly.io/Cloudflare free tiers. Goal: eliminate all paid dependencies entirely.

### Observability Stack

- **Distributed Tracing**: W3C TraceContext propagation across all workers (`src/observability/tracing.py`)
- **Health Aggregation**: Central health checker monitoring all P0–P2 services (`src/observability/health.py`)
- **Structured Logging**: JSON logs with trace_id, user_id, service_name bindings
- **Alerting**: Prometheus alert rules via monitoring worker (port 8007)

## Recommended Open Source Foundations

When building new services, prefer these vetted open-source projects:

| Your Service | Repo to fork/integrate | Stars | License |
|---|---|---|---|
| **The Digital Grid** | n8n-io/n8n | 95K | Fair-code (self-host free) |
| The Digital Grid | PrefectHQ/prefect | 17K | Apache 2.0 |
| The Digital Grid | temporalio/temporal | 12K | MIT |
| The Digital Grid | apache/airflow | 38K | Apache 2.0 |
| **The Library** | outline/outline | 29K | BSL (self-host free) |
| The Library | BookStackApp/BookStack | 15K | MIT |
| **The Observatory** | SigNoz/signoz | 21K | Apache 2.0 |
| The Observatory | jaegertracing/jaeger | 20K | Apache 2.0 |
| The Observatory | netdata/netdata | 73K | GPL 3.0 |
| **Fabulousa** | penpot/penpot | 35K | MPL 2.0 |
| Fabulousa | storybookjs/storybook | 84K | MIT |
| **API Marketplace** | gravitee-io/gravitee-api-management | 4K | Apache 2.0 |
| **Cryptex** | MISP/MISP | 5.7K | AGPL 3.0 |
| Cryptex | greenbone/openvas-scanner | 3.5K | AGPL 3.0 |
| **The Ice Box** | cuckoosandbox/cuckoo | 5.7K | GPL 3.0 |
| **DocUtari** | paperless-ngx/paperless-ngx | 24K | GPL 3.0 |
| DocUtari | Stirling-Tools/Stirling-PDF | 52K | MIT |
| **TranceFlow** | godotengine/godot | 94K | MIT |
| **VRAR3D** | mrdoob/three.js | 103K | MIT |
| VRAR3D | aframevr/aframe | 16K | MIT |
| VRAR3D | BabylonJS/Babylon.js | 23K | Apache 2.0 |
| **The Artifactory** | project-zot/zot | 1.2K | Apache 2.0 |
| **ChronosSphere** | calcom/cal.com | 34K | AGPL 3.0 |
| ChronosSphere | kestra-io/kestra | 14K | Apache 2.0 |
| **The Void (self-hosted)** | hashicorp/vault | 31K | BSL (self-host free) |
| **Luminous AI** | vllm-project/vllm | 47K | Apache 2.0 |
| **Sashas Photo Studio** | comfyanonymous/ComfyUI | 72K | GPL 3.0 |
| Sashas Photo Studio | AUTOMATIC1111/stable-diffusion-webui | 147K | AGPL 3.0 |
| **TateKing (Video)** | remotion-dev/remotion | 22K | Company licence (basic free) |
| **I-Mind / Resonate** | openai/evals | 14K | MIT |
| **The Lab** | continuedev/continue | 24K | Apache 2.0 |
| The Lab | TabbyML/tabby | 23K | Apache 2.0 |
| The Lab | Aider-AI/aider | 24K | Apache 2.0 |
| **Frontend components** | shadcn-ui/ui | 83K | MIT |
| **Frontend testing** | microsoft/playwright | 68K | Apache 2.0 |
| **AI Gateway** | BerriAI/litellm | 18K | MIT |
| **Vector / RAG** | qdrant/qdrant | 22K | Apache 2.0 |
| Vector / RAG | weaviate/weaviate | 12K | BSD 3-Clause |
| Vector / RAG | chroma-core/chroma | 17K | Apache 2.0 |
| Vector / RAG | meilisearch/meilisearch | 48K | MIT |
| **Database / Storage** | minio/minio | 50K | AGPL 3.0 |
| Database / Storage | duckdb/duckdb | 25K | MIT |
| **The Workshop (enhance)** | forgejo/forgejo | — | MIT |
| **LangChain / AI Framework** | langchain-ai/langchain | 95K | MIT |
| LangChain / AI Framework | run-llama/llama_index | 38K | MIT |
| LangChain / AI Framework | deepset-ai/haystack | 18K | Apache 2.0 |
| LangChain / AI Framework | microsoft/semantic-kernel | 23K | MIT |
| LangChain / AI Framework | stanfordnlp/dspy | 22K | MIT |
| **Agent Frameworks** | microsoft/autogen | 35K | MIT |
| Agent Frameworks | crewAIInc/crewAI | 25K | MIT |
| **MLOps / Experiment Tracking** | mlflow/mlflow | 19K | Apache 2.0 |
| MLOps / Experiment Tracking | wandb/wandb | 9K | MIT |
| **Agent Orchestration** | microsoft/autogen | 35K | MIT |
| Agent Orchestration | crewAIInc/crewAI | 25K | MIT |
