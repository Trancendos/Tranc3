# TRANC3 INFINITY — Comprehensive Directory Structure Document

## Phase 26 — Complete Architecture Map v0.9.0

---

## 1. Repository Overview

| Metric | Value |
|---|---|
| **Total Directories** | 196 |
| **Total Files** | 1,016 (in tarball) |
| **Repository Size** | 62 MB (excluding .git) |
| **Python Files** | 476 |
| **Rust Files** | 13 |
| **Go Files** | 2 |
| **TypeScript/TSX** | 12 |
| **YAML Configs** | 43 |
| **Dockerfiles** | 34 |
| **Shell Scripts** | 21 |
| **Markdown Docs** | 54 |
| **Proto Definitions** | 1 |
| **TOML Configs** | 13 |
| **Test Files** | 75 |
| **Lines of Python** | 153,036 |
| **Lines of Rust** | 5,731 |
| **Lines of Go** | 386 |
| **Lines of Proto** | 300 |

---

## 2. Directory Tree

```
Tranc3/
│
├── .github/                          # GitHub configuration
│   └── workflows/
│       ├── rust.yml                  # Rust CI/CD (check, test, maturin-build)
│       ├── go.yml                    # Go CI/CD (lint, build, test)
│       └── python.yml                # Python CI/CD (ruff, mypy, test matrix)
│
├── aeonmind/                         # ═══ AeonMind Polyglot Framework v0.9.0 ═══
│   ├── docs/
│   │   └── AI_DEFINITIONS_DICTIONARY.md  # Canonical AI/Agent/Bot hierarchy
│   │
│   ├── rust/                         # Rust Core Crate (PyO3)
│   │   ├── Cargo.toml               # Crate config: aeonmind-core v0.1.0
│   │   └── src/
│   │       ├── lib.rs               # Tier enum, SentinelChannel, EntityType
│   │       ├── liquid.rs            # LiquidReservoir, FluidicState, spectral radius
│   │       ├── genetic.rs           # EvolutionEngine, tournament select, crossover
│   │       ├── quantum.rs           # QuantumDecisionCircuit, Rot+CNOT, param shift
│   │       ├── adaptive.rs          # AdaptiveMetaLearner, L-BFGS two-loop
│   │       ├── wasm_bridge.rs       # FluidicAgentState, IntelligenceScore, WasmAgent
│   │       └── python_bindings.rs   # PyO3 module definitions
│   │
│   ├── python/                       # Python Integration Layer
│   │   ├── pyproject.toml           # Package config: aeonmind v0.9.0
│   │   ├── aeonmind/
│   │   │   ├── __init__.py          # Top-level exports
│   │   │   ├── core/
│   │   │   │   ├── __init__.py      # Core re-exports
│   │   │   │   ├── definitions.py   # Tier, SentinelChannel, AiComplex, AgentEntity, BotService
│   │   │   │   ├── quantum.py       # PennyLane + NumPy QuantumDecisionCircuit
│   │   │   │   ├── frontier_agent.py # FrontierAgent (Reservoir+Quantum+Adaptive+Evolution)
│   │   │   │   ├── rust_bridge.py   # Conditional Rust bindings with Python fallbacks
│   │   │   │   ├── adaptive.py      # AdaptiveMetaLearner with L-BFGS
│   │   │   │   ├── genetic_dna.py   # DNAEvolutionEngine with DEAP-style evolution
│   │   │   │   └── fluidic_liquidic.py # LiquidReservoir with fluidic state tracking
│   │   │   ├── systems/
│   │   │   │   ├── __init__.py
│   │   │   │   └── orchestrator.py  # LogicalOrchestrator (Tier 1) with Ray
│   │   │   └── services/
│   │   │       ├── __init__.py
│   │   │       └── bot_services.py  # BotServiceWorker (T5) + BotServiceRegistry
│   │   └── tests/
│   │       ├── conftest.py
│   │       ├── test_definitions.py  # 19 tests
│   │       ├── test_quantum.py      # 11 tests
│   │       ├── test_frontier_agent.py # 7 tests
│   │       ├── test_bot_services.py  # 9 tests
│   │       ├── test_adaptive.py     # 9 tests
│   │       ├── test_genetic.py      # 12 tests
│   │       └── test_liquidic.py     # 13 tests  (91 total)
│   │
│   ├── go/                           # Go gRPC Orchestrator
│   │   ├── go.mod                   # Module: github.com/Trancendos/Tranc3/aeonmind/go
│   │   ├── cmd/
│   │   │   └── main.go              # gRPC server entry point (port 50051)
│   │   └── orchestrator/
│   │       └── server.go            # OrchestratorServer, entity management, broadcast
│   │
│   ├── proto/                        # Protocol Buffer Definitions
│   │   └── aeonmind.proto           # Enums, messages, AeonMindOrchestrator service
│   │
│   └── wasm/                         # WebAssembly Edge Agent
│       ├── Cargo.toml               # Crate config: aeonmind-wasm v0.9.0
│       └── src/
│           └── lib.rs               # wasm-bindgen: FluidicAgentState, IntelligenceScore, WasmAgent
│
├── cloudflare/                       # Cloudflare Workers
│   ├── infinity-void/
│   │   └── src/
│   ├── tranc3-ai/
│   │   └── src/
│   └── trancendos-api-gateway/
│       └── src/
│
├── dashboard/                        # Platform Dashboard (Vanilla HTML/CSS/JS)
│   ├── index.html                   # Cosmic dark theme dashboard
│   ├── styles.css                   # CSS custom properties + animations
│   └── app.js                       # Dashboard logic
│
├── data/                             # Runtime data directory
│
├── deploy/                           # ═══ Deployment Infrastructure ═══
│   ├── alertmanager/                # Prometheus AlertManager config
│   ├── forgejo/                     # Forgejo (Gitea fork) self-hosted
│   ├── grafana-provisioning/        # Grafana dashboards + datasources
│   │   ├── dashboards/
│   │   └── datasources/
│   ├── k3s/                         # K3s Kubernetes manifests
│   │   └── templates/
│   ├── k8s/                         # Standard Kubernetes manifests
│   ├── minio/                       # MinIO object storage config
│   └── terraform/                   # OpenTofu/Terraform IaC
│       ├── cloud-init/              # Cloud-init scripts
│       ├── main.tf                  # Root module: Oracle Cloud + Cloudflare
│       ├── oci-free-tier.tf         # Oracle Cloud Always Free resources
│       ├── oci-network.tf           # VCN, subnets, security lists
│       ├── oci-storage.tf           # Block volumes, object storage
│       ├── outputs.tf               # Terraform outputs
│       └── variables.tf             # Input variables
│
├── docker/                           # Docker build contexts
│
├── docs/                             # ═══ Documentation ═══
│   ├── architecture/                # Architecture documentation
│   ├── reference/                   # API reference docs
│   ├── PHASE25_REPO_REVIEW.md       # Trancendos org repo analysis (51 repos)
│   ├── PHASE25_ZERO_COST_ASSESSMENT.md  # Container/Podman vs Terraform/GitHub
│   ├── PHASE25_PROGRESS_CALCULATION.md  # Before/After Phase 23 progress
│   └── PHASE25_UXUI_ENHANCEMENT.md  # UX/UI design system research
│
├── logs/                             # Runtime logs
│   └── audit/                       # Audit trail logs
│
├── migrations/                       # Database migrations (Alembic)
│   └── versions/
│
├── monitoring/                       # Monitoring configuration
│   └── grafana/
│       └── provisioning/
│
├── scripts/                          # Utility scripts
│
├── shared_core/                      # ═══ Shared Core Libraries ═══
│   ├── __init__.py
│   ├── architecture/                # Architecture patterns
│   ├── dimensionals/                # Dimensional service abstractions
│   ├── infinity/                    # Infinity-specific core
│   ├── middleware/                   # Shared middleware
│   ├── orchestration/               # Orchestration patterns
│   ├── security_automation/         # Security automation core
│   ├── bus.py                       # Event bus
│   ├── models.py                    # Shared data models
│   ├── registry.py                  # Service registry
│   ├── security.py                  # Security utilities
│   └── sanitize.py                  # Input sanitization
│
├── src/                              # ═══ Core Platform Source ═══
│   ├── adaptive/                    # Adaptive automation engine
│   ├── agents/                      # Agent framework
│   ├── ai_gateway/                  # AI gateway + model routing
│   │   └── providers/              # LLM provider integrations
│   ├── analytics/                   # Analytics engine
│   ├── apimarket/                   # API marketplace
│   ├── artifactory/                 # Artifact management
│   ├── auth/                        # Authentication & authorization
│   ├── basement/                    # Foundation utilities
│   ├── bio_neural/                  # Bio-neural computing
│   ├── chronos/                     # Time management
│   ├── citadel/                     # Security citadel
│   ├── cloud/                       # Cloud integration
│   ├── coding/                      # Code generation
│   ├── compliance/                  # Compliance engine
│   ├── config/                      # Configuration management
│   ├── core/                        # Platform core
│   ├── cryptex/                     # Encryption & security
│   ├── database/                    # Database layer
│   ├── deepmind/                    # Deep learning integration
│   ├── devocity/                    # DevOps automation
│   ├── distributed/                 # Distributed computing
│   ├── entities/                    # Entity management
│   ├── errors/                      # Error handling
│   ├── event_bus/                   # Event-driven architecture
│   ├── evolution/                   # Evolutionary algorithms
│   ├── fluidic/                     # Fluidic computing
│   ├── gateway/                     # API gateway
│   ├── healing/                     # Self-healing system
│   ├── holographic/                 # Holographic processing
│   ├── imind/                       # Intelligent mind framework
│   ├── inference/                   # ML inference engine
│   ├── intelligence/                # Intelligence scoring
│   ├── knowledge/                   # Knowledge management
│   ├── lab/                         # Experimental features
│   ├── library/                     # Knowledge library
│   ├── mcp/                         # Model Context Protocol
│   ├── mesh/                        # Service mesh
│   ├── monetisation/                # Monetization engine
│   ├── nanoservices/                # Micro/nano services
│   │   └── rust/                    # Rust nanoservice (tranc3-nanoservice)
│   ├── neural/                      # Neural network framework
│   ├── nexus/                       # Nexus connection hub
│   ├── observability/               # Observability stack
│   ├── personality/                 # AI personality system
│   │   ├── profiles/               # Personality profiles
│   │   └── turingshub/             # Turing test hub
│   ├── quantum/                     # Quantum computing
│   ├── registry/                    # Service registry
│   ├── research/                    # Research module
│   ├── resilience/                  # Resilience patterns
│   ├── resonate/                    # Resonance computing
│   ├── security/                    # Security framework
│   ├── skills/                      # Skills system
│   ├── studio/                      # Development studio
│   ├── taimra/                      # TAIMRA module
│   ├── tensorflow_core/             # TensorFlow integration
│   ├── townhall/                    # Governance system
│   ├── training/                    # ML training pipeline
│   ├── tranquility/                 # Wellness module
│   ├── validation/                  # Input validation
│   ├── vrar3d/                      # VR/AR/3D processing
│   ├── workers/                     # Worker management
│   └── workflow/                    # Workflow engine
│
├── tests/                            # ═══ Platform Test Suite ═══
│   ├── test_adaptive_automation.py
│   ├── test_adaptive_intelligence.py
│   ├── test_adaptive_pulse.py
│   ├── test_agents.py
│   ├── test_ai_gateway.py
│   ├── test_all_workers_health.py
│   ├── test_analytics.py
│   ├── test_api.py
│   ├── test_auth.py
│   ├── test_basement.py
│   ├── test_chaos.py
│   ├── test_chronos.py
│   ├── test_coding.py
│   ├── test_compatibility.py
│   ├── test_compliance.py
│   ├── test_core.py
│   ├── test_cryptex.py
│   ├── test_devocity.py
│   ├── test_dimensional_services.py
│   ├── test_enhanced_api.py
│   ├── test_entities.py
│   ├── test_errors.py
│   ├── test_event_bus.py
│   ├── test_fluidic.py
│   ├── test_full_suite.py
│   ├── test_gateway_service.py
│   ├── test_healing.py
│   ├── test_health.py
│   ├── test_hil_a.py
│   ├── test_infinity_admin.py
│   ├── test_infinity_one.py
│   ├── test_infinity_portal.py
│   ├── test_library.py
│   ├── test_mesh.py
│   ├── test_microceph_provider.py
│   ├── test_nanoservices.py
│   ├── test_observability.py
│   ├── test_oci_adaptive_provider.py
│   ├── test_penetration.py
│   ├── test_personality.py
│   ├── test_phase4_ml_mcp_workflow.py
│   ├── test_phase5_agent_orchestration.py
│   ├── test_platform_routes.py
│   ├── test_predictive_scaler.py
│   ├── test_proactive_metrics.py
│   ├── test_proactive_orchestrator.py
│   ├── test_proactive_wiring.py
│   ├── test_resilience.py
│   ├── test_security_automation.py
│   ├── test_security_remediation.py
│   ├── test_smoke.py
│   ├── test_spark_grid_integration.py
│   ├── test_tracing.py
│   ├── test_tranc3_ml.py
│   ├── test_uat.py
│   ├── test_validation.py
│   ├── test_worker_bridges.py
│   ├── test_worker_mesh_integration.py
│   ├── test_workers_p0.py
│   ├── test_workers_p1.py
│   ├── test_workers_p2.py
│   ├── test_workers_p3.py
│   ├── test_workers_p4.py
│   ├── test_workflow.py
│   ├── test_zero_trust.py
│   └── test_zkp.py
│
├── tranc3-bots/                      # ═══ Bot Framework ═══
│   ├── bots/                        # Bot implementations
│   ├── client/                      # Bot client SDK
│   ├── scripts/                     # Bot management scripts
│   └── server/                      # Bot orchestration server
│
├── web/                              # ═══ Web Frontend (React + Vite) ═══
│   ├── package.json                 # Dependencies: React 18, Lucide, Tailwind
│   ├── vite.config.ts              # Vite configuration
│   ├── tailwind.config.js          # Tailwind CSS configuration
│   ├── tsconfig.json               # TypeScript configuration
│   └── src/
│       ├── App.tsx                  # Root application component
│       ├── AppRouter.tsx           # Client-side routing
│       ├── ChatView.tsx            # AI chat interface
│       ├── LoginPage.tsx           # Authentication page
│       ├── UpgradeModal.tsx        # Subscription upgrade UI
│       ├── main.tsx                # React entry point
│       ├── index.css               # Global styles
│       ├── components/
│       │   └── spark/              # Spark component library
│       └── trancendos/
│           ├── Dashboard.tsx        # Main dashboard view
│           ├── apiClient.ts        # API client layer
│           └── tokens.ts           # Auth token management
│
├── workers/                          # ═══ Worker Services (44 services) ═══
│   ├── analytics-service/           # Data analytics pipeline
│   ├── api-gateway/                 # API gateway service
│   ├── audit-service/               # Audit trail service
│   ├── cache-service/               # Caching layer
│   ├── cdn-service/                 # CDN management
│   ├── config-service/              # Configuration service
│   ├── cron-service/                # Scheduled tasks
│   ├── deepagents-orchestrator-service/ # Deep agents orchestration
│   ├── email-service/               # Email notification service
│   ├── files-service/               # File management
│   ├── gateway-service/             # API gateway (enhanced)
│   ├── geo-service/                 # Geolocation service
│   ├── health-aggregator/           # Health check aggregation
│   ├── identity-service/            # Identity management
│   ├── infinity-admin-service/      # Admin portal service
│   ├── infinity-ai/                 # AI service
│   ├── infinity-auth/               # Authentication service
│   ├── infinity-one-service/        # Infinity One integration
│   ├── infinity-portal-service/     # Portal service
│   ├── infinity-void/               # Void operations
│   ├── infinity-ws/                 # WebSocket service
│   ├── langchain-integration-service/ # LangChain integration
│   ├── ledger-service/              # Financial ledger
│   ├── model-router-service/        # AI model routing
│   ├── monitoring/                  # Monitoring service
│   ├── notifications/               # Push notifications
│   ├── orders-service/              # Order management
│   ├── payments-service/            # Payment processing
│   ├── products-service/            # Product catalog
│   ├── queue-service/               # Message queue
│   ├── rate-limit-service/          # Rate limiting
│   ├── search-service/              # Search engine
│   ├── sentinel-station-service/    # Sentinel security monitoring
│   ├── skills-benchmark-service/    # Skills benchmarking
│   ├── sms-service/                 # SMS notification
│   ├── storage-service/             # Object storage
│   ├── the-grid/                    # Grid computing
│   ├── topology-service/            # Network topology
│   ├── tranc3-ai/                   # Core AI service
│   ├── users-service/               # User management
│   ├── vault-service/               # Secrets vault
│   └── workflow-engine-service/     # Workflow orchestration
│
├── api.py                            # Main FastAPI application
├── api_ecosystem.py                  # Ecosystem API endpoints
├── api_enhanced.py                   # Enhanced API with extended features
├── auth.py                           # Authentication module
├── main_2060.py                      # 2060 vision configuration
├── train.py                          # ML training pipeline
├── verify_phase10.py                 # Phase verification script
│
├── docker-compose.yml                # Development compose (api, web, redis, otel)
├── docker-compose.production.yml     # Production compose (full stack)
├── docker-compose.storage.yml        # Storage compose (MinIO, PostgreSQL)
├── docker-compose.self-hosted.yml    # Self-hosted compose
├── Dockerfile                        # Main Docker build
├── docker-entrypoint.sh             # Container entry point
│
├── pyproject.toml                    # Python project configuration
├── requirements.txt                  # Core Python dependencies
├── requirements-ai.txt               # AI/ML dependencies
├── requirements-security.txt         # Security dependencies
├── requirements-test.txt             # Test dependencies
│
├── Makefile                          # Build automation
├── alembic.ini                       # Database migration config
├── fly.toml                          # Fly.io deployment config
├── tranc3_2060_config.yaml           # 2060 configuration
├── tranc3_enhanced_config.yaml       # Enhanced configuration
│
├── ARCHITECTURE_UPDATE.md            # Architecture documentation
├── ARCHITECTURE_THREAT_MODEL.md      # Threat model analysis
├── CLAUDE.md                         # AI assistant instructions
├── CODE_OF_CONDUCT.md                # Community code of conduct
├── CROSS_REPO_SYNERGY.md             # Cross-repository synergy analysis
├── PLATFORM_ENTITIES.md              # Platform entity definitions
├── PROJECT_PULSE.md                  # Project status & pulse
├── README.md                         # Project overview
├── RESEARCH_FINDINGS.md              # Research documentation
├── REVERT_LOG.md                     # Revert/change log
├── SECURITY.md                       # Security policy
├── SECURITY-ASSESSMENT.md            # Security assessment
├── VERIFICATION.md                   # Verification status
├── todo.md                           # Phase tracking
│
└── INFINITY_ARCHITECTURE.md          # Infinity architecture specification
```

---

## 3. Tier-Aware Component Map

### 3.1 Tier 0 — HUMAN
- `web/src/LoginPage.tsx` — Human authentication
- `dashboard/` — Human dashboard interface

### 3.2 Tier 1 — ORCHESTRATOR
- `aeonmind/go/orchestrator/server.go` — gRPC orchestrator
- `aeonmind/python/aeonmind/systems/orchestrator.py` — Python LogicalOrchestrator
- `src/gateway/` — API gateway
- `workers/api-gateway/` — Gateway service

### 3.3 Tier 2 — PRIME
- `aeonmind/python/aeonmind/core/frontier_agent.py` — FrontierAgent (multi-system)
- `src/core/` — Platform core
- `workers/deepagents-orchestrator-service/` — Deep agent orchestration

### 3.4 Tier 3 — AI (ML/LLM Complex)
- `aeonmind/python/aeonmind/core/definitions.py` — AiComplex class
- `src/ai_gateway/` — AI model gateway
- `src/deepmind/` — Deep learning integration
- `src/inference/` — ML inference engine
- `src/intelligence/` — Intelligence scoring
- `src/neural/` — Neural network framework
- `src/tensorflow_core/` — TensorFlow integration
- `src/training/` — ML training pipeline
- `train.py` — Training entry point
- `workers/model-router-service/` — Model routing
- `workers/tranc3-ai/` — Core AI service

### 3.5 Tier 4 — AGENT (Autonomous AI)
- `aeonmind/python/aeonmind/core/definitions.py` — AgentEntity class
- `aeonmind/rust/src/lib.rs` — Agent EntityType
- `src/agents/` — Agent framework
- `src/adaptive/` — Adaptive automation
- `src/evolution/` — Evolutionary algorithms
- `src/fluidic/` — Fluidic computing
- `src/healing/` — Self-healing agent
- `src/personality/` — Agent personality
- `src/quantum/` — Quantum decision circuits
- `workers/sentinel-station-service/` — Sentinel agent

### 3.6 Tier 5 — BOT (Stateless Service Worker)
- `aeonmind/python/aeonmind/core/definitions.py` — BotService class
- `aeonmind/python/aeonmind/services/bot_services.py` — BotServiceWorker + Registry
- `aeonmind/rust/src/lib.rs` — BotService (stateless=true)
- `tranc3-bots/` — Bot framework
- `workers/` — All 44 worker services

---

## 4. Sentinel Channel Mapping

| Channel | Source Files | Workers |
|---|---|---|
| PLATFORM | `api.py`, `api_ecosystem.py` | api-gateway, gateway-service |
| AGENTS | `src/agents/`, `aeonmind/.../frontier_agent.py` | deepagents-orchestrator |
| MODELS | `src/ai_gateway/`, `src/inference/` | model-router-service, tranc3-ai |
| WORKFLOWS | `src/workflow/`, `aeonmind/.../orchestrator.py` | workflow-engine-service |
| SECURITY | `src/cryptex/`, `src/security/`, `src/citadel/` | sentinel-station, vault-service |
| HIVE | `src/mesh/`, `src/distributed/` | the-grid |
| NEXUS | `src/nexus/` | topology-service |
| BRIDGE | `src/gateway/`, `aeonmind/.../rust_bridge.py` | langchain-integration |
| PILLARS | `src/knowledge/`, `src/library/` | infinity-admin-service |
| INFRASTRUCTURE | `deploy/terraform/`, `src/cloud/` | config-service, storage-service |
| EVENTS | `src/event_bus/`, `src/chronos/` | cron-service, notifications |

---

## 5. Language Distribution by Directory

| Directory | Primary Language | Secondary | Purpose |
|---|---|---|---|
| `aeonmind/rust/` | Rust (7 modules) | — | Performance-critical core |
| `aeonmind/python/` | Python (10 modules) | — | High-level orchestration |
| `aeonmind/go/` | Go (2 modules) | — | gRPC orchestrator |
| `aeonmind/wasm/` | Rust (1 module) | — | Edge deployment |
| `aeonmind/proto/` | Protocol Buffers | — | Service definitions |
| `src/` | Python (47+ modules) | — | Platform core |
| `workers/` | Python (44 services) | Docker | Microservice workers |
| `web/` | TypeScript/React | CSS | Frontend application |
| `dashboard/` | HTML/CSS/JS | — | Standalone dashboard |
| `deploy/terraform/` | HCL | Shell | Infrastructure-as-Code |
| `cloudflare/` | JavaScript | — | Edge workers |
| `shared_core/` | Python | — | Shared libraries |
| `tests/` | Python (67 files) | — | Platform test suite |
| `tranc3-bots/` | Python | — | Bot framework |

---

## 6. Build & Deployment Artifacts

| File | Purpose | Format |
|---|---|---|
| `Dockerfile` | Main container build | Docker |
| `docker/Dockerfile.api` | API server image | Docker |
| `docker/Dockerfile.web` | Web frontend image | Docker |
| `docker-compose.yml` | Development stack | YAML |
| `docker-compose.production.yml` | Production stack | YAML |
| `fly.toml` | Fly.io deployment | TOML |
| `Makefile` | Build automation | Make |
| `pyproject.toml` | Python packaging | TOML |
| `aeonmind/rust/Cargo.toml` | Rust crate | TOML |
| `aeonmind/wasm/Cargo.toml` | WASM crate | TOML |
| `aeonmind/go/go.mod` | Go module | Go |
| `aeonmind/python/pyproject.toml` | AeonMind Python package | TOML |
| `deploy/terraform/main.tf` | Infrastructure | HCL |
| `.github/workflows/*.yml` | CI/CD pipelines | YAML |

---

## 7. Version Information

| Component | Version | Status |
|---|---|---|
| **Tranc3 Platform** | v0.3.2 | Main branch (d7be344) |
| **AeonMind Framework** | v0.9.0 | Phase 24 branch (064d522) |
| **Rust Crate** | aeonmind-core v0.1.0 | Phase 24 branch |
| **WASM Crate** | aeonmind-wasm v0.9.0 | Phase 24 branch |
| **Go Module** | v0.0.0 | Phase 24 branch |
| **Python Package** | aeonmind v0.9.0 | Phase 24 branch |
| **Test Suite** | 91 AeonMind + 67 Platform | All passing |
| **Current Phase** | Phase 25 → 26 | In progress |
