# Trancendos 5-Tier AI Architecture

## Hierarchy

```
Tier 1  ─  Trance-One        trance_one/          Sovereign Orchestrator
Tier 2  ─  T2ance            t2ance/              Prime Level (9 Domain Primes)
Tier 3  ─  Tranc3            src/core/ + src/bio_neural/ + ...  ML/LLM AI Base
Tier 4  ─  Infinity-Agent    src/agents/          Low-Level AI Agents (α + β)
Tier 5  ─  Infinity-Worker   tranc3-bots/ + workers/  Bots, Workers, Scrapers
```

---

## Tier 1 — Trance-One (Sovereign)

| Module | Path | Role |
|--------|------|------|
| Sovereign Controller | `trance_one/sovereign_controller.py` | Platform-wide authority |
| Platform Manifest | `trance_one/platform_manifest.py` | 43-entity canonical registry |
| Tier Bridge | `trance_one/tier_bridge.py` | Inter-tier command relay |

---

## Tier 2 — T2ance (Prime Level)

| Module | Path | Role |
|--------|------|------|
| Prime Registry | `t2ance/prime_registry.py` | 9 Domain Primes registry |
| Domain Authority | `t2ance/domain_authority.py` | Per-domain executive AI |
| Tier Relay | `t2ance/tier_relay.py` | T2↔T3 command relay |

**Domain Primes → Entity Mapping:**

| Prime | Domain | Entities |
|-------|--------|----------|
| ArchPrime | Architectural | The Spark, The Digital Grid, The HIVE, The Nexus, Infinity, Luminous |
| CommPrime | Commercial | Royal Bank, Arcadian Exchange, ChronosSphere |
| CreatePrime | Creativity | The Studio, Sashas Photo Studio, TranceFlow, TateKing, Fabulousa, Imaginarium, Warp Radio, VRAR3D |
| DevPrime | Development | The Workshop, The Lab, Think Tank, The Artifactory, API Marketplace, DevOcity |
| KnowPrime | Knowledge | The Library, The Academy, DocUtari, The Basement, Turing's Hub, The Dutchy |
| SecPrime | Security | Cryptex, The Void, The Lighthouse, The Ice Box, The Warp Tunnel |
| WellPrime | Wellbeing | Tranquility, I-Mind, Resonate, tAimra |
| GovPrime | Governance | The Town Hall, Arcadia |
| OpsPrime | Operations | The Citadel, The Observatory |

---

## Tier 3 — Tranc3 (ML/LLM AI Base)

All AI/ML modules stay in `src/` — these form the Tranc3 base AI layer:

| Module | Path | Role |
|--------|------|------|
| Tranc3 Engine | `src/core/tranc3_inference.py` | Core transformer inference |
| ML Pipeline | `src/core/ml_pipeline.py` | Training + inference pipeline |
| Bio Neural | `src/bio_neural/` | Consciousness engine (Luminous) |
| Personality | `src/personality/` | Personality matrix (Turing's Hub) |
| Inference | `src/inference/` | LLM router, model loader |
| Neural | `src/neural/` | Attention router, collective memory |
| Quantum | `src/quantum/` | Quantum neural core (Think Tank) |
| Deep Mind | `src/deepmind/` | World model, MCTS, planning |
| Evolution | `src/evolution/` | Self-improving adaptive tuner |
| Intelligence | `src/intelligence/` | Causal reasoner, semantic knowledge |
| Skills | `src/skills/` | Code generator, enhanced registry |
| Training | `src/training/` | LoRA trainer, datasets |
| TensorFlow Core | `src/tensorflow_core/` | Hybrid TF engine |

---

## Tier 4 — Infinity-Agent (Low-Level AI Agents)

Each entity gets an **Alpha agent** (primary) and **Beta agent** (shadow/backup).

| Module | Path | Role |
|--------|------|------|
| Agent Runtime | `src/agents/agent_runtime.py` | Alpha + Beta agent execution |
| Task Decomposer | `src/agents/task_decomposer.py` | Goal → subtask decomposition |
| Goal Manager | `src/agents/goal_manager.py` | Goal lifecycle |
| Memory Stream | `src/agents/memory_stream.py` | Agent episodic memory |
| Tool Bridge | `src/agents/tool_bridge.py` | MCP tool access layer |
| Agent Types | `src/agents/agent_types.py` | Tier 4 agent type definitions |

---

## Tier 5 — Infinity-Worker (Bots, Workers, Scrapers)

| Module | Path | Role |
|--------|------|------|
| Bot Registry | `tranc3-bots/` | 12 bot types (inference + utility) |
| Workers | `workers/` | 38 self-hosted Python workers (ports 8004–8038) |
| Inference Worker | `src/workers/inference_worker.py` | Queue drain → Tranc3Engine |
| Worker Pool | `src/workers/pool.py` | Worker lifecycle management |

---

## Dimensional — Shared-Core Services

> `shared_core/` and `Dimensional/` are the **same thing** — canonical name is **Dimensional**.
> All `shared_core` references should resolve to `Dimensional`.

| Module | Path | Role |
|--------|------|------|
| Service Bus | `Dimensional/bus.py` | Cross-entity event bus |
| Hive Core | `Dimensional/hive/` | The HIVE autoscaler + sentinel bridge |
| Infinity IAM | `Dimensional/infinity/` | Auth gateway, RBAC, ZKP, OWASP hardening |
| Orchestration | `Dimensional/orchestration/` | Health monitor, config drift, dependency graph |
| Security Automation | `Dimensional/security_automation/` | Adaptive scanner, defense engine, watchdog |
| Middleware | `Dimensional/middleware/` | Auth, rate limiter, telemetry |
| Dimensionals | `Dimensional/dimensionals/` | Service registry, underverse |
| AI Gateway | `src/ai_gateway/` | 5-tier AI provider failover (Dimensional service) |
| Service Mesh | `src/mesh/` | CircuitBreaker + service registry (Dimensional service) |
| Event Bus | `src/event_bus/` | NATS JetStream transport (Dimensional service) |
| Auth / Zero Trust | `src/auth/` | JWT, zero-trust IAM (Dimensional service) |
| Healing | `src/healing/` | Anomaly detection, self-repair (Dimensional service) |
| Adaptive | `src/adaptive/` | Provider + layer rotation (Dimensional service) |
| Fluidic | `src/fluidic/` | Causal bus, reactive state (Dimensional service) |
| Resilience | `src/resilience/` | Circuit breaker (Dimensional service) |

---

## Entity Locations

Entity-specific modules live under `src/entities/locations/<entity>/`.
Current in-place locations (not yet moved — canonically owned here):

| Entity | Current Path | Canonical Location |
|--------|-------------|-------------------|
| The Spark | `src/mcp/` | Entity: The Spark |
| The Digital Grid | `src/workflow/` | Entity: The Digital Grid |
| The Observatory | `src/observability/` | Entity: The Observatory |
| The Town Hall | `src/townhall/` | Entity: The Town Hall |
| The Studio | `src/studio/` | Entity: The Studio |
| The Nexus | `src/nexus/` | Entity: The Nexus |
| The Lab | `src/lab/` | Entity: The Lab |
| The Basement | `src/basement/` | Entity: The Basement |
| The Library | `src/library/` | Entity: The Library |
| Cryptex | `src/cryptex/` | Entity: Cryptex |
| The Artifactory | `src/artifactory/` | Entity: The Artifactory |
| API Marketplace | `src/apimarket/` | Entity: API Marketplace |
| DevOcity | `src/devocity/` | Entity: DevOcity |
| The Citadel | `src/citadel/` | Entity: The Citadel |
| ChronosSphere | `src/chronos/` | Entity: ChronosSphere |
| Tranquility | `src/tranquility/` | Entity: Tranquility |
| I-Mind | `src/imind/` | Entity: I-Mind |
| Resonate | `src/resonate/` | Entity: Resonate |
| tAimra | `src/taimra/` | Entity: tAimra |
| VRAR3D | `src/vrar3d/` | Entity: VRAR3D |
| The Dutchy | `src/research/` | Entity: The Dutchy |
| Luminous | `src/bio_neural/` (AI core) + entity folder | Entity: Luminous |
| Turing's Hub | `src/personality/` | Entity: Turing's Hub |

---

## Trancendos-Backend (Platform Infra)

Everything that is not AI, not Dimensional, not an entity location:

| Module | Path | Role |
|--------|------|------|
| Database | `src/database/` | SQLAlchemy models, Alembic migrations |
| Monetisation | `src/monetisation/` | Billing tiers |
| Config | `src/config/` | Environment + runtime config |
| Errors | `src/errors/` | Canonical error catalog |
| Registry | `src/registry/` | File registry |
| Protocols | `src/protocols/` | Protocol definitions |
| Routers | `src/routers/` | FastAPI router wiring |
| Analytics | `src/analytics/` | Predictive analytics |
| Admin OS | `src/admin_os/` | System administration |
| Nanoservices | `src/nanoservices/` | Internal micro-proxy |
| Cloud | `src/cloud/` | Cost optimiser, federation |
| Compliance | `src/compliance/` | Magna Carta compliance |
| Validation | `src/validation/` | Loop validator |
| Bridge | `src/bridge/` | Ecosystem bridge |
| GBrain | `src/gbrain/` | GBrain AI bridge |
| Platform | `src/platform/` | Entity rotation, scanning, detection |
| Benchmark | `src/benchmark/` | Performance suite |
| API Entry | `api.py`, `api_ecosystem.py` | FastAPI application entry points |
