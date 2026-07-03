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

**Naming rules:**
- "The Digital Grid" — always with a space (entity table has a known typo "The DigitalGrid"; ignore it)
- "Sashas Photo Studio" — no apostrophe (canonical; not "Sasha's Photo Studio")
- "tAimra" = location name; "tAImra" = its Lead AI name (different capitalisation — both correct)
- "The Guardian (Anchor: Orb of Orisis)" — full title required in entity contexts
- `vesper-nightingale`, `atlas-meridian` — internal legacy profiles in `src/personality/profiles/`; NOT platform entities; unmapped pending future assignment
- "Section 7" — internal placeholder name, NOT in the canonical entity hierarchy; closest entity is **The Dutchy** (Intelligence & Market Analysis, Lead AI: Predictive lore)

| Code Name | Lead AI (Tier 3) | Role / Description | Status | Foundation |
|---|---|---|---|---|
| **The Spark** | Norman Hawkins | MCP server — AI tool registry, JSON-RPC 2.0 over HTTP/SSE | ✅ In repo | `src/mcp/` |
| **The Digital Grid** | Tyler Towncroft | Workflow DAG builder + executor (n8n-style) | ✅ In repo | `src/workflow/` |
| **The Void** | Prometheus | Secrets + password vault (AES-GCM) | 🔧 Migrating | `cloudflare/infinity-void/` → self-hosted |
| **The Workshop** | Larry Lowhammer | CI/CD hub — Forgejo self-hosted git + pipelines | ✅ In repo | `deploy/forgejo/` |
| **Infinity** | The Guardian (Anchor: Orb of Orisis) | OAuth, SSO, central user management (1 account, all services) | ✅ Self-hosted | `workers/infinity-auth/` (Port 8005) |
| **The Lighthouse** | Rocking Ricki | Cryptographic token assignment, authenticator, token scanner | ✅ Deployed | CF: `infinity-lighthouse` |
| **The HIVE** | The Queen | Data transport hub, agent + queue coordination | ✅ Deployed | CF: `infinity-hive` |
| **Royal Bank of Arcadia** | Dorris Fontaine | Financial hub — billing, payments | ✅ Deployed | CF: `arcadia-royal-bank` |
| **Arcadian Exchange** | The Porter Family | Financial exchange — procurement & resource trading | ✅ Deployed | CF: `arcadia-exchange` |
| **The Observatory** | Norman Hawkins | Audit log — every action, change, activity on Trancendos | ✅ Self-hosted | `src/observability/`, `workers/monitoring/` |
| **Luminous** | Cornelius MacIntyre | Core platform brain — AI intelligence & orchestration engine | 🔧 Partial | `src/bio_neural/`, `src/core/` |
| **Turing's Hub** | Samantha Turing | AI creation centre — personality template creator | 🔧 Partial | `src/personality/` |
| **Arcadia** | Lilli SC | Front-end post-login, forum & email hub | 🔧 Partial | `web/` |
| **The Nexus** | The Nexus | AI communications and transfer hub | 🔧 Self-hosted | `workers/infinity-ws/` (Port 8004) |
| **The Town Hall** | Tristuran | Governance hub — PRINCE2, ITIL, Agile/Kanban, ITSM, rooms, templates | ✅ Integrated | `workers/cranbania/` (CranBania submodule, Port 8071), `src/townhall/`, `src/compliance/middleware.py` |
| **The Library** | Zimik | Knowledge base & wiki | 🔧 Planned | Outline (self-hosted) |
| **The Academy** | Shimshi | Learning management — education & skill training | 🔧 Planned | Custom LMS |
| **DocUtari** | To be Defined | Document management hub | 🔧 Planned | Paperless-ngx |
| **The Basement** | Gary Glowman (Glow-Worm) | Archived information store from The Observatory | 🔧 Planned | `src/basement/` (to create) |
| **The Studio** | Voxx | Central hub of the Creativity Center | 🔧 Planned | `src/studio/` (to create) |
| **Sashas Photo Studio** | Madam Krystal | Photo & image generation center | 🔧 Planned | Stable Diffusion + ComfyUI |
| **TranceFlow** | Junior Cesar | 3D modeling & games creation studio | 🔧 Planned | Godot Engine integration |
| **TateKing** | Benji Tate & Sam King | Video creation & editing platform | 🔧 Planned | FFmpeg + custom UI |
| **Fabulousa** | Baron Von Hilton | Styling, UX, UI & design center | 🔧 Planned | Penpot (self-hosted) |
| **Imaginarium** | Voxx | Omni-creative masterpiece wizard (Fabulousa + TateKing + TranceFlow + Studio + Photo) | 🔧 Planned | Orchestrates above |
| **The Lab** | The Dr. & Slime | Code creation platform (Claude Code-style) | 🔧 Planned | `src/lab/` (to create) |
| **The Chaos Party** | The Mad Hatter | Central testing platform — validation & compliance (Alice in Wonderland themed) | 🔧 Partial | `tests/test_chaos.py` |
| **The Artifactory** | Lunascene | Central artifact repository library | 🔧 Planned | Gitea packages / Zot |
| **API Marketplace** | Solarscene | Central integration hub — REST, webhooks, OAuth | 🔧 Planned | Gravitee.io |
| **Cryptex** | Renik | Cyber defense — threat intel, DDoS, CVE | 🔧 Planned | Wazuh + MISP |
| **The Ice Box** | Neonach | Sandbox threat isolation & quarantine | 🔧 Planned | Cuckoo sandbox |
| **The Warp Tunnel** | Rocking Ricki | Cryptographic scanner & quarantine transport | 🔧 Planned | `src/security/warp_tunnel/` (to create) |
| **Warp Radio** | Rocking Ricki | Music & audio streaming integration | 🔧 Planned | `src/warp_radio/` (to create) |
| **The Dutchy** | Predictive lore | Intelligence & market analysis | 🔧 Planned | `src/research/` |
| **The Citadel** | Trancendos | Strategic ops & DevOps fortress | ✅ Self-hosted | Docker Compose + Traefik + Forgejo |
| **Think Tank** | Trancendos | R&D centre — solutions & forefront technologies | 🔧 Planned | `src/quantum/`, `src/deepmind/` |
| **ChronosSphere / ArcStream** | Chronos | Task, time & scheduling management | 🔧 Planned | Cal.com (self-hosted) |
| **DevOcity** | Kitty | Development operations hub | 🔧 Planned | Custom dev portal |
| **Tranquility** | Savania | Wellbeing central hub | 🔧 Planned | `src/tranquility/` (to create) |
| **I-Mind** | Elouise | Sensitivity to emotion engine | 🔧 Planned | `src/imind/` (to create) |
| **tAimra** | tAImra | Opt-in digital twin & life assistant | 🔧 Planned | `src/taimra/` (to create) |
| **VRAR3D** | Entari | Standalone 3D / VR immersion | 🔧 Planned | Three.js / A-Frame |
| **Resonate** | Magdalena | Empathy engine | 🔧 Planned | `src/resonate/` (to create) |

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

The Tranc3 platform has been transformed from a Cloudflare Workers + paid-services architecture to a fully self-hosted, zero-cost Python/FastAPI architecture. All 26+ Cloudflare Workers are being migrated to self-hosted Python workers backed by SQLite, in-memory state, and local filesystem. No paid APIs, no third-party cost-incurring dependencies.

**Key documents:**
- `CROSS_REPO_SYNERGY.md` — Maps all 29 infinity-adminOS TypeScript packages to Python equivalents
- `CF_WORKER_MIGRATION_ROADMAP.md` — Full migration plan for all 26+ CF Workers to self-hosted Python
- `ARCHITECTURE_THREAT_MODEL.md` — STRIDE analysis and risk register for self-hosted architecture
- `docker-compose.production.yml` — Full production stack (29 workers + infrastructure)

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
| infinity-void | 8082 | P3 | `workers/infinity-void/` | The Void — self-hosted AES-GCM vault |

> **Port source of truth:** the port column above is aligned to each worker's **mapped port in
> `docker-compose.production.yml`** (the deployment truth — `PORT` env / Traefik
> `loadbalancer.server.port` / published `ports:`), reconciled against `PLATFORM_ENTITIES.md` and
> each worker's actual code bind port. The P3 block `8016–8029` was previously mis-paired here (it
> had been assigned alphabetically, e.g. `email-service` shown as `8022`); it is now corrected to the
> compose mapping (`email-service` `8018`, `search-service` `8017`, `queue-service` `8022`, …). Most of
> these workers' code binds agree with compose, but **4 do not** — see the routing-defects table below.
>
> **Known routing defects (issue #188).** A worker's code binds `PORT` (default shown), but compose
> routes to a different port and sets **no `PORT` env** to override it, so the container is unreachable
> at the routed port (same class as the chaos-party defect). Confirmed for **4 workers**:
>
> | Worker | code binds (`PORT` default) | compose routes | note |
> |---|---|---|---|
> | `audit-service` | 8017 | 8025 | — |
> | `queue-service` | 8027 | 8022 | code's 8027 == `geo-service`'s compose port (collision if adopted) |
> | `search-service` | 8083 | 8017 | 8083 matches neither registry |
> | `infinity-void` | 8082 | 8002 | entangled with the vault's documented `8082` app default (`docs/services/the-void/`) |
>
> Each needs a **per-worker decision** (fix the code default to the compose port, or set `PORT` / re-map
> compose) — not a bulk edit, given the collision and the vault entanglement. Workers that read a
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
- `personality/` — 5 named personality instances (dorris-fontaine, cornelius-macintyre, the-guardian, vesper-nightingale, atlas-meridian)
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

**All CI/CD runs through Forgejo (The Workshop) — NO GitHub Actions.**

Workflow files in `.forgejo/workflows/`:
- `deploy-fly.yml` — tranc3-backend + tranc3-bots to Fly.io
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
fly secrets set REDIS_URL="..." TRANC3_ENGINE_URL="https://tranc3-backend.fly.dev" --app tranc3-bots
fly deploy --remote-only --app tranc3-bots

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
- `tranc3-bots` — 256MB RAM

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
