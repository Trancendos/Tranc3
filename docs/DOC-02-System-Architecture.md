# TRANC3 System Architecture
**Version:** 3.0.0 | **Date:** May 23, 2026

---

## 1. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                        TRANC3 PLATFORM                           │
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐    │
│  │  Web UI  │  │Mobile App│  │  CLI     │  │  3rd Party   │    │
│  │ (React)  │  │(iOS/And) │  │  Tools   │  │  Integrations│    │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬───────┘    │
│       └─────────────┴─────────────┴────────────────┘            │
│                           │                                      │
│                    ┌──────▼──────┐                               │
│                    │  API Gateway │                               │
│                    │  (FastAPI)   │                               │
│                    └──────┬──────┘                               │
│                           │                                      │
│         ┌─────────────────┼─────────────────┐                   │
│         │                 │                 │                   │
│  ┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐            │
│  │  Core AI    │  │  Quantum    │  │Consciousness│            │
│  │  Engine     │  │  Module     │  │  Engine     │            │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘            │
│         │                 │                 │                   │
│  ┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐            │
│  │Neuromorphic │  │  Holographic│  │   Self-     │            │
│  │  Module     │  │  Memory     │  │  Evolution  │            │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘            │
│         └─────────────────┼─────────────────┘                   │
│                           │                                      │
│         ┌─────────────────┼─────────────────┐                   │
│         │                 │                 │                   │
│  ┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐            │
│  │  Redis      │  │  PostgreSQL  │  │  Vector DB  │            │
│  │  Cache      │  │  (Primary)   │  │  (Pinecone) │            │
│  └─────────────┘  └─────────────┘  └─────────────┘            │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              OBSERVABILITY LAYER                          │   │
│  │  Prometheus │ Grafana │ OTEL Collector │ Jaeger │ Loki   │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              CLOUD LAYER                                  │   │
│  │    GKE (Primary) │ AKS (Failover) │ EKS (DR)            │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

## 2. Component Details

### 2.1 API Gateway (FastAPI)
- **Port:** 8000
- **Workers:** 4 (production)
- **Auth:** JWT + OAuth2
- **Rate Limiting:** 1000 req/min per user
- **Endpoints:** /chat, /health, /ready, /metrics, /features, /feedback

### 2.2 Core AI Engine
- **Architecture:** Transformer (BERT-based, 12 layers)
- **Vocab Size:** 119,547 tokens
- **Hidden Size:** 768
- **Attention Heads:** 12
- **Max Sequence:** 512 tokens
- **Languages:** 50+

### 2.3 Quantum Module
- **Framework:** Qiskit 1.1.1
- **Qubits:** Up to 16 (simulation)
- **Backend:** AerSimulator (statevector)
- **Features:** Quantum attention, Grover search, QFT

### 2.4 Consciousness Engine
- **Theory:** IIT (Integrated Information Theory)
- **Metric:** Φ (phi) score
- **Target Φ:** > 2.0
- **Introspection Depth:** 3 levels

### 2.5 Neuromorphic Module
- **Type:** Spiking Neural Networks (SNN)
- **Framework:** Custom PyTorch SNN
- **Neuron Model:** Leaky Integrate-and-Fire (LIF)

### 2.6 Data Layer
- **Cache:** Redis 7 (in-memory)
- **Primary DB:** PostgreSQL 16
- **Vector DB:** Pinecone (embeddings)
- **Object Storage:** S3/GCS/Azure Blob

## 3. Data Flow

```
User Input
    │
    ▼
API Gateway (auth, rate limit, validate)
    │
    ▼
Language Detection & Tokenization
    │
    ├──► Quantum Attention Enhancement
    │
    ├──► Consciousness State Evaluation
    │
    ├──► Neuromorphic Processing
    │
    ├──► Holographic Memory Recall
    │
    ▼
Core Transformer Inference
    │
    ▼
Personality Matrix Application
    │
    ▼
Self-Evolution Feedback Loop
    │
    ▼
Response Generation & Caching
    │
    ▼
User Output
```

## 4. Non-Functional Requirements

| Requirement | Target |
|-------------|--------|
| Availability | 99.9% |
| Latency (p95) | < 1s |
| Throughput | 10,000 req/s |
| Concurrent Users | 100,000 |
| Data Retention | 90 days |
| RTO | < 15 min |
| RPO | < 5 min |

## 5. Proactive Systems Architecture (Phase 10)

The Proactive Systems layer provides autonomous self-healing, predictive scaling, adaptive pulse control, and zero-cost compliance enforcement. It operates as a bridge between the observability layer and the operational infrastructure.

```
┌──────────────────────────────────────────────────────────────┐
│                  PROACTIVE SYSTEMS LAYER                      │
│                                                              │
│  ┌──────────────────────┐  ┌──────────────────────────────┐  │
│  │ ProactiveOrchestrator│  │  AdaptivePulseController     │  │
│  │  (HEAL, SCALE,       │  │  (STEADY→ACCELERATED→        │  │
│  │   MIGRATE, HARDEN,   │  │   EMERGENCY→RECOVERY)        │  │
│  │   RECONFIGURE, etc.) │  │  Baseline 30s, Min 1s        │  │
│  └──────────┬───────────┘  └──────────────┬───────────────┘  │
│             │                              │                 │
│  ┌──────────┴───────────┐  ┌──────────────┴───────────────┐  │
│  │ AutoConfigManager    │  │  PredictiveAutoscaler        │  │
│  │ (TRUE_NAS, HYBRID,   │  │  (Load forecasting via       │  │
│  │  CLOUD_ONLY, DEV,    │  │   double exponential         │  │
│  │  PRODUCTION)         │  │   smoothing; zero-cost       │  │
│  │  Hot-reload, Rollback│  │   constraint enforcement)    │  │
│  └──────────┬───────────┘  └──────────────┬───────────────┘  │
│             │                              │                 │
│  ┌──────────┴──────────────────────────────┴───────────────┐  │
│  │              ProactiveMetricsCollector                   │  │
│  │  SystemVitals │ SubsystemMetrics │ Prometheus Export     │  │
│  │  Composite Health │ Health Trends │ Action Statistics    │  │
│  └──────────────────────────┬──────────────────────────────┘  │
│                              │                                │
│  ┌──────────────────────────┴──────────────────────────────┐  │
│  │           ProactiveSystemBootstrap (Wiring)             │  │
│  │  EVENT_BUS │ STORAGE │ SENTINEL │ DEFENSE │ PULSE │     │  │
│  │  CONFIG │ SCALER │ ROUTING │ REGISTRY │ RESILIENCE │    │  │
│  │  FORESIGHT                                               │  │
│  └─────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### 5.1 ProactiveOrchestrator

The ProactiveOrchestrator is the central decision engine for autonomous system management. It operates in four modes: OBSERVE (passive monitoring), ASSIST (suggests actions), AUTONOMOUS (executes without approval), and EMERGENCY (critical response). The orchestrator maintains a PredictiveHealthAnalyzer that records subsystem health scores and forecasts degradation, an AutoHealingEngine that creates and tracks healing actions with rollback support, a ZeroCostModulator that enforces the zero-cost mandate by checking storage compliance and recommending tier migrations, and an ActionDispatcher that queues and dispatches action plans asynchronously with registered handlers per action type.

### 5.2 AdaptivePulseController

The AdaptivePulseController manages the system heartbeat, dynamically adjusting interval timing based on overall health. In STEADY mode, the pulse fires at the configured baseline interval (default 30 seconds). When health degrades, the controller transitions to ACCELERATED mode with shorter intervals. Under critical conditions, it enters EMERGENCY mode with the fastest cadence (as low as 1 second). After resolution, the system transitions through RECOVERY back to STEADY. Each named daemon can be registered with its own baseline interval and the controller tracks mode transitions, compression ratios, and time spent in each mode.

### 5.3 AutoConfigManager

The AutoConfigManager provides environment-aware configuration with automatic detection and hot-reload capabilities. It defines profiles for TRUE_NAS, HYBRID, CLOUD_ONLY, and DEVELOPMENT environments, each with specific settings for storage tiers, sentinel intervals, orchestrator modes, and scaling parameters. The EnvironmentDetector probes the runtime environment to determine the correct profile automatically. Configuration changes are tracked with status (DEFAULT, DETECTED, OVERRIDDEN, HOT_RELOADED, VALIDATED, ROLLED_BACK) and support rollback to previous values. Change listeners receive notifications when configuration values are modified.

### 5.4 PredictiveAutoscaler

The PredictiveAutoscaler uses double exponential smoothing (Holt's method) to forecast load and make scaling decisions within zero-cost constraints. Resources are registered with current units, min/max bounds, and free-tier limits. The LoadForecaster maintains level and trend components that adapt to changing load patterns, producing confidence-bounded predictions. Scaling decisions include the direction (UP, DOWN, MAINTAIN), reason (PREDICTED_DEMAND, CURRENT_LOAD, ZERO_COST_LIMIT, COOLDOWN, etc.), and zero-cost compliance status. The scaler respects cooldown periods between actions and will not exceed free-tier limits.

### 5.5 ProactiveMetricsCollector

The ProactiveMetricsCollector aggregates vitals from all proactive subsystems into a unified view. It produces SystemVitals containing composite health scores, subsystem health breakdowns, health trends, orchestrator mode, pulse mode, zero-cost compliance status, and counts of active, pending, and failed actions. SubsystemMetrics track per-component health scores, event processing rates, and error counts. The collector supports Prometheus-format export for integration with the existing observability stack and allows custom collectors to be registered for domain-specific metrics.

### 5.6 ProactiveSystemBootstrap

The ProactiveSystemBootstrap handles the wiring and lifecycle management of all proactive system components. It establishes BridgeConnections across 11 bridge types (EVENT_BUS, STORAGE, SENTINEL, DEFENSE, FORESIGHT, ROUTING, REGISTRY, RESILIENCE, PULSE, CONFIG, SCALER) with status tracking through DISCONNECTED, CONNECTING, CONNECTED, ACTIVE, ERROR, and DISABLED states. The bootstrap process is asynchronous: wire_all connects all subsystem bridges, start initiates monitoring, and stop gracefully shuts down all connections.

## 6. Zero-Cost Cloud Provider Integration (Phase 9B)

The platform supports a tiered zero-cost storage strategy across multiple cloud providers:

| Provider | Free Tier | Storage | Use Case |
|----------|-----------|---------|----------|
| Cloudflare R2 | 10 GB | Object | Primary static assets |
| Supabase | 1 GB | PostgreSQL | Metadata, configs |
| Neon | 0.5 GB | PostgreSQL | Operational data |
| Vercel Blob | 0.25 GB | Object | Temporary uploads |
| GitHub Pages | Unlimited | Static | Documentation sites |

The ZeroCostModulator within the ProactiveOrchestrator continuously monitors storage utilization against free-tier limits and triggers automated migration when a tier approaches its threshold, ensuring the platform remains within zero-cost boundaries at all times.

## 7. CI/CD Pipeline (Phase 11)

The codebase quality and CI/CD hardening pipeline runs on GitHub Actions (free tier for public repositories):

- **ci.yml**: Triggers on PRs to main/develop — runs ruff lint + format check, then pytest with fail-fast
- **test.yml**: Triggers on push to main — runs the full test suite with coverage collection across Python 3.11

Both workflows use `ruff check --select E,F,W,B --ignore E501,B008,B904` for linting, reflecting the project's established conventions for line length, function call defaults, and exception chaining.