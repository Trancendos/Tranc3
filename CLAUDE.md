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

| Code Name | Role / Description | Status | Foundation |
|---|---|---|---|
| **The Spark** | MCP server — AI tool registry, JSON-RPC 2.0 over HTTP/SSE | ✅ In repo | `src/mcp/` |
| **The Digital Grid** | Workflow DAG builder + executor (n8n-style) | ✅ In repo | `src/workflow/` |
| **The Void** | Secrets + password vault (AES-GCM, CF Worker) | ✅ Deployed | `cloudflare/infinity-void/` |
| **The Workshop** | CI/CD hub — Forgejo self-hosted git + pipelines | ✅ In repo | `deploy/forgejo/` |
| **Infinity** | OAuth, SSO, central user management (1 account, all services) | ✅ Deployed | CF workers: `infinity-*` |
| **The Lighthouse** | Cryptographic token assignment, authenticator, token scanner | ✅ Deployed | CF: `infinity-lighthouse` |
| **The HIVE** | Data transfer hub, agent coordination | ✅ Deployed | CF: `infinity-hive` |
| **Royal Bank of Arcadia** | Financial hub — billing, payments | ✅ Deployed | CF: `arcadia-royal-bank` |
| **Arcadian Exchange** | Financial exchange, trading, crypto/stocks | ✅ Deployed | CF: `arcadia-exchange` |
| **The Observatory** | Audit log — every action, change, activity on Trancendos | 🔧 Scaffold | `src/observability/` |
| **Luminous** | Brain of Trancendos — AI intelligence core | 🔧 Partial | `src/bio_neural/`, `src/core/` |
| **Turing's Hub** | AI creation centre — personality template creator | 🔧 Partial | `src/personality/` |
| **Arcadia** | Front-end post-login + forum | 🔧 Partial | `web/` |
| **The Nexus** | AI communications and transfer hub | 🔧 Planned | `src/nexus/` (to create) |
| **The Town Hall** | Governance hub — PRINCE2, ITIL, legal, compliance, policies | 🔧 Planned | `src/townhall/` (to create) |
| **The Library** | KB (user-facing), Wiki (admin), Basement (archived) articles | 🔧 Planned | Outline (self-hosted) |
| **The Academy** | Learning management — courses from Library articles | 🔧 Planned | Custom LMS |
| **DocUtari** | Document repository | 🔧 Planned | Paperless-ngx |
| **The Basement** | Archived information from The Observatory | 🔧 Planned | `src/basement/` (to create) |
| **The Studio** | Creativity hub | 🔧 Planned | `src/studio/` (to create) |
| **Sashas Photo Studio** | Image creation and editing | 🔧 Planned | Stable Diffusion + ComfyUI |
| **TranceFlow** | 3D game development studio | 🔧 Planned | Godot Engine integration |
| **TateKing** | Video creation and editing | 🔧 Planned | FFmpeg + custom UI |
| **Fabulousa** | UX/UI + Aria styling and design platform | 🔧 Planned | Penpot (self-hosted) |
| **Imaginarium** | Creative megahub (Fabulousa + TateKing + TranceFlow + Studio + Photo) | 🔧 Planned | Orchestrates above |
| **The Lab** | Code creation platform (Claude Code-style) | 🔧 Planned | `src/lab/` (to create) |
| **The Chaos Party** | Testing + validation compliance (Ansible-style, Alice in Wonderland themed) | 🔧 Partial | `tests/test_chaos.py` |
| **The Artifactory** | Artefact repository (JFrog-style) | 🔧 Planned | Gitea packages / Zot |
| **API Marketplace** | API connector hub — REST, webhooks, OAuth | 🔧 Planned | Gravitee.io |
| **Cryptex** | Threat analysis, cyber security defence, bug bounty | 🔧 Planned | Wazuh + MISP |
| **The Ice Box** | Threat holding + assessment (malware, virus, trojans) | 🔧 Planned | Cuckoo sandbox |
| **Section 7** | Research + analysis hub, information analytics | 🔧 Planned | `src/research/` |
| **The Citadel** | DevOps hub | 🔧 Planned | `deploy/` + Forgejo |
| **Think Tank** | Solutions + forefront technologies innovation centre | 🔧 Planned | `src/quantum/`, `src/deepmind/` |
| **ChronosSphere / ArcStream** | Time and schedule management | 🔧 Planned | Cal.com (self-hosted) |
| **DevOcity** | Developer centre — user developer hub | 🔧 Planned | Custom dev portal |
| **Tranquility** | Wellbeing hub | 🔧 Planned | `src/tranquility/` (to create) |
| **I-Mind** | Critical and sensitivity protocol | 🔧 Planned | `src/imind/` (to create) |
| **tAimra** | Digital twin — offline by default | 🔧 Planned | `src/taimra/` (to create) |
| **VRAR3D** | AR/VR wellbeing centre | 🔧 Planned | Three.js / A-Frame |
| **Resonate** | Empathy and understanding services | 🔧 Planned | `src/resonate/` (to create) |

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

### Named subsystems (in this repo)

| Identity | Code path | Role |
|---|---|---|
| **The Spark** | `src/mcp/` | MCP server + tool registry — JSON-RPC 2.0 over HTTP/SSE |
| **The Digital Grid** | `src/workflow/` | Workflow DAG builder + topological executor + event bus |
| **The Void** | `cloudflare/infinity-void/` | AES-GCM encrypted secrets vault (CF Worker) |
| **The Workshop** | `deploy/forgejo/` | Self-hosted Forgejo CI/CD at trancendos.com/the-workshop |
| **The Observatory** | `src/observability/` | Metrics, tracing, audit log |
| **Luminous** | `src/bio_neural/`, `src/core/tranc3_inference.py` | AI brain, consciousness, inference |
| **Think Tank** | `src/quantum/`, `src/deepmind/` | Quantum + deep research engines |
| **Turing's Hub** | `src/personality/` | Personality profiles + spawner |

### Service map

| Service | Port | Repo path | Notes |
|---|---|---|---|
| tranc3-backend | 8000 | `/` (root) | FastAPI, SQLAlchemy, JWT auth |
| nanoservices | 8001 | `src/nanoservices/` | Thin proxy to tranc3-bots (internal only) |
| tranc3-bots | 8080 | `tranc3-bots/` | Separate Fly.io app, 12 bot types |
| tranc3-ai | edge | `cloudflare/tranc3-ai/` | CF Worker — AI edge proxy |
| infinity-void | edge | `cloudflare/infinity-void/` | CF Worker — The Void encrypted vault |
| trancendos-api-gateway | edge | `cloudflare/trancendos-api-gateway/` | CF Worker — `api.trancendos.com/*` |

### Inference pipeline (5-tier fallback)

```
Client → tranc3-ai CF Worker
           ↓ Tier 1: Tranc3Engine local weights (if trained)
           ↓ FAIL → Tier 2: Ollama (localhost:11434, zero-cost)
           ↓ FAIL → Tier 3: OpenRouter free models (cloud, zero-cost)
           ↓ FAIL → Tier 4: TRANC3_BACKEND_URL (Fly.io :8000)
           ↓ FAIL → Tier 5: deterministic stub response
```

### Backend (`api.py`)

Entry point: `api.py`. Fails fast if `SECRET_KEY` is unset.

Key module domains under `src/`:
- `core/` — Tranc3Engine (transformer inference), startup validator, circuit breaker
- `core/ollama_adapter.py` — free local LLM fallback (Ollama)
- `core/openrouter_adapter.py` — free cloud LLM fallback (OpenRouter :free models)
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
- `deploy-cloudflare.yml` — tranc3-ai + infinity-void + trancendos-api-gateway CF Workers

Forgejo at `trancendos.com/the-workshop`. Act-runner in `deploy/forgejo/docker-compose.yml`. Org secrets: `CF_API_TOKEN`, `FLY_API_TOKEN`.

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
- `api.trancendos.com/*` → trancendos-api-gateway CF Worker

Fly.io apps (region `lhr`):
- `tranc3-backend` — 256MB RAM, 1GB encrypted volume at `/app/models`
- `tranc3-bots` — 256MB RAM

Cloudflare account ID: `e0214028cb64d31232f5662548a55e4e`
Workers subdomain: `luminous-aimastermind.workers.dev`

**Zero-cost model** — no paid external services beyond committed Fly.io/Cloudflare free tiers.

## Recommended Open Source Foundations

When building new services, prefer these vetted open-source projects:

| Service to build | Foundation | GitHub |
|---|---|---|
| The Digital Grid (enhance) | n8n (188k⭐) | github.com/n8n-io/n8n |
| The Library / Wiki | Outline (38k⭐) | github.com/outline/outline |
| The Observatory | SigNoz (27k⭐, OpenTelemetry) | github.com/SigNoz/signoz |
| ChronosSphere / ArcStream | Cal.com | cal.com/self-hosting |
| Fabulousa (UX/design) | Penpot | penpot.app/self-host |
| API Marketplace | Gravitee.io | gravitee.io |
| Cryptex (security SIEM) | Wazuh + MISP | wazuh.com |
| The Ice Box (threat analysis) | Cuckoo Sandbox | cuckoosandbox.org |
| DocUtari (documents) | Paperless-ngx | github.com/paperless-ngx |
| TranceFlow (3D game dev) | Godot Engine | godotengine.org |
| The Artifactory | Zot (OCI registry) | zotregistry.dev |
| The Workshop (enhance) | Forgejo | forgejo.org |
