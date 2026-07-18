# Cross-Repo Synergy Report: Trancendos Ecosystem

> **Status note.** Porting these packages to Python is part of the Hybrid/Local deployment
> path (see `Architecture-CF_WORKER_MIGRATION_ROADMAP.md`), gated on funding a repaired or
> replacement local server. Cloud Only remains the default for every Location in the
> meantime — this report describes a destination, not a committed schedule.

## Executive Summary

Analysis of 16 Trancendos repositories reveals that **infinity-adminOS** is a critical monorepo containing 29 production-ready TypeScript packages that form the backbone of the Trancendos platform. These packages must be ported to Python to power Tranc3's self-hosted, zero-cost architecture. The remaining repos are mostly scaffold/stub implementations that will be absorbed into Tranc3's unified worker model.

---

## Repository Inventory

### Tier 1: Production-Ready Code (Immediate Value)

| Repository | Language | Packages | Status | Value |
|---|---|---|---|---|
| **infinity-adminOS** | TypeScript | 29 packages | Production-ready | **CRITICAL** — service mesh, event bus, AI gateway, void service, IAM, quantum-safe crypto |
| **Dimensional** | TypeScript + Python | Middleware + compliance | Partial | Auth middleware, resilience patterns, compliance scanner |

### Tier 2: Scaffold with Domain Logic (Medium Value)

| Repository | Language | Status | Notes |
|---|---|---|---|
| **the-void** | TypeScript | Stub | Only `src/index.ts` — real code is in infinity-adminOS `packages/void/` |
| **the-lighthouse** | TypeScript | Stub | Only `src/index.ts` — real code is in infinity-adminOS `packages/lighthouse/` |
| **the-hive** | TypeScript | Stub | Only `src/index.ts` — real code is in infinity-adminOS `packages/hive/` |
| **the-citadel** | TypeScript | Stub | DevOps hub — just scaffold |
| **the-workshop** | TypeScript | Stub | CI/CD hub — Forgejo is the real implementation |
| **the-forge** | TypeScript | Stub | Code creation hub |
| **the-foundation** | TypeScript | Stub | Base platform |
| **infrastructure** | Config | Partial | Docker configs, deployment scripts |
| **the-observatory** | TypeScript | Stub | Monitoring — real stack is in infinity-adminOS |
| **the-nexus** | TypeScript | Stub | Communications hub — needs WebSocket implementation |
| **the-cryptex** | TypeScript | Stub | Security hub |
| **arcadia** | TypeScript | Stub | Front-end hub |
| **docs** | Markdown | Partial | Documentation |

### Tier 3: Primary Development Repository

| Repository | Language | Status | Notes |
|---|---|---|---|
| **Tranc3** | Python | **Active** | Main development repo — all ports land here |

---

## infinity-adminOS Package Analysis

### Core Infrastructure Packages (Port First — P0)

#### 1. service-mesh (`packages/service-mesh/`)
- **Source**: TypeScript — `ServiceMesh` class + `CircuitBreaker` class
- **Features**: Service discovery, circuit breaking (closed/open/half-open), health monitoring, retries with backoff, dependency graphs, distributed tracing, nanoservice intelligence
- **Python Target**: `src/mesh/` — FastAPI-native service mesh
- **Zero-Cost**: No external dependencies — pure Python asyncio + httpx

#### 2. event-bus (`packages/event-bus/`)
- **Source**: TypeScript — `EventBus` class
- **Features**: Pattern-based routing (`user.*`, `order.created`), in-memory callbacks, batch processing, event persistence, fire-and-forget emission, payload validation, subscription management
- **Python Target**: `src/event_bus/` — asyncio event bus with SQLite persistence
- **Zero-Cost**: Replaces Cloudflare Queue bindings

#### 3. ai-gateway (`packages/ai-gateway/`)
- **Source**: TypeScript — `AIGateway` class + 7 provider implementations
- **Features**: Priority-based failover routing, token budget enforcement, response caching, latency-based failover, per-provider health tracking, condition-based routing (plan, tags, time)
- **Providers**: OpenAI, Anthropic, OpenRouter, HuggingFace, WorkersAI, Offline, Transformers.js
- **Python Target**: `src/ai_gateway/` — Python AI gateway with local providers
- **Zero-Cost**: Prioritises Ollama (local) → OpenRouter (free tier) → offline fallback

### Security & Identity Packages (Port Second — P1)

#### 4. iam-middleware (`packages/iam-middleware/`)
- **Features**: Zero Trust device posture, MFA verification, geographic access policies, risk scoring
- **Python Target**: `src/auth/zero_trust.py`
- **Zero-Cost**: Self-hosted — no Cloudflare Zero Trust dependency

#### 5. void (`packages/void/`)
- **Features**: AES-256-GCM/ChaCha20 encryption, Shamir's Secret Sharing (5-of-9), zero-knowledge proofs, key rotation, GDPR compliance, RBAC+ABAC access control
- **Python Target**: Enhance `workers/infinity-void/worker.py`
- **Zero-Cost**: Pure Python cryptography (cryptography lib)

#### 6. quantum-safe (`packages/quantum-safe/`)
- **Features**: ML-KEM-1024 (Kyber), SLH-DSA (Dilithium), hybrid classical+post-quantum encryption
- **Python Target**: `src/crypto/quantum_safe.py`
- **Zero-Cost**: liboqs Python bindings (optional) or pure Python stubs

#### 7. webauthn (`packages/webauthn/`)
- **Features**: WebAuthn/FIDO2 passkey authentication
- **Python Target**: `src/auth/webauthn.py`
- **Zero-Cost**: py_webauthn library

### Platform Packages (Port Third — P2)

#### 8. kernel (`packages/kernel/`)
- **29 source files** — platform core services, lifecycle management
- **Python Target**: `src/kernel/`

#### 9. adapters (`packages/adapters/`)
- **15 source files** — external service adapters
- **Python Target**: `src/adapters/`

#### 10. observability (`packages/observability/`)
- **Features**: Metrics collection, tracing, log aggregation
- **Python Target**: `src/observability/` — enhance existing module

#### 11. policy-engine (`packages/policy-engine/`)
- **Features**: OPA-style policy evaluation, RBAC/ABAC rules
- **Python Target**: `src/policy/`

#### 12. permissions (`packages/permissions/`)
- **Features**: Granular permission system, role hierarchies
- **Python Target**: `src/auth/permissions.py`

#### 13. tiga-middleware (`packages/tiga-middleware/`)
- **Features**: TIGA (Trancendos Intelligence Governance Architecture) middleware
- **Python Target**: `src/governance/`

### Domain Packages (Port Fourth — P3)

| Package | Purpose | Python Target |
|---|---|---|
| `infinity-one` | Main app service | `workers/infinity-one/` |
| `lighthouse` | Token verification | `workers/infinity-lighthouse/` |
| `hive` | Data transfer hub | `workers/infinity-hive/` |
| `adaptive-intelligence` | AI core | `src/adaptive/` (enhance) |
| `agent-sdk` | Agent development kit | `src/agents/sdk.py` |
| `swarm-intelligence` | Multi-agent coordination | `src/agents/swarm.py` |
| `slipstream-protocol` | Inter-service protocol | `src/protocol/` |
| `ipc` | Inter-process communication | `src/mesh/ipc.py` |
| `sdk` | Platform SDK | `src/sdk/` |
| `platform-core` | Core platform abstractions | `src/core/` (enhance) |
| `tenant-do` | Tenant management | `src/tenant/` |
| `financial-types` | Financial data types | `src/financial/` |
| `quantum-computing` | Quantum computing bridge | `src/quantum/` (enhance) |
| `types` | Shared TypeScript types | `src/types.py` |
| `ui` | UI components | N/A (stays frontend) |

---

## Docker Production Stack

The infinity-adminOS repo includes a complete production Docker Compose stack at `infrastructure/docker/docker-compose.prod.yml`:

| Service | Purpose | Zero-Cost |
|---|---|---|
| **Traefik** | Reverse proxy + automatic TLS (Let's Encrypt) | Yes — free TLS certs |
| **HashiCorp Vault** | Secrets management + crypto-shredding | Yes — open source |
| **Prometheus** | Metrics collection | Yes — open source |
| **Grafana** | Dashboards + alerting | Yes — open source |
| **Loki** | Log aggregation | Yes — open source |
| **Promtail** | Log shipping | Yes — open source |
| **IPFS** | Decentralised storage | Yes — open source |
| **Langfuse** | AI observability (LLM tracing) | Yes — open source |

This stack will be adapted for Tranc3's self-hosted worker architecture, replacing all Cloudflare-specific infrastructure.

---

## Migration Strategy

### Phase 1: Foundation (P0 — This PR)
1. Port `service-mesh` → Python `src/mesh/`
2. Port `event-bus` → Python `src/event_bus/`
3. Port `ai-gateway` → Python `src/ai_gateway/`
4. Create CF Worker migration roadmap

### Phase 2: Workers (Next PR)
1. Implement WebSocket worker (The Nexus)
2. Implement OAuth2/SSO worker (Infinity)
3. Implement Users, Notifications, Monitoring workers
4. Create production Docker Compose stack

### Phase 3: Security (Future PR)
1. Port IAM/ZeroTrust middleware
2. Port quantum-safe crypto
3. Port WebAuthn/FIDO2
4. Enhanced Void service with Shamir's Secret Sharing

### Phase 4: Platform (Future PR)
1. Port kernel, adapters, policy engine
2. Port remaining domain packages
3. Unified test coverage
4. Documentation and deployment guides

---

## Key Architectural Decisions

1. **Python over TypeScript**: All self-hosted workers use Python/FastAPI for consistency with the Tranc3 codebase. No Node.js runtime needed.

2. **SQLite over D1**: Cloudflare D1 is replaced by SQLite for local persistence. Zero cost, file-based, no server needed.

3. **In-Memory over KV**: Cloudflare KV rate limiting is replaced by in-memory rate limiting with periodic persistence to SQLite.

4. **Local Files over R2**: Cloudflare R2 object storage is replaced by local filesystem with optional IPFS for decentralised storage.

5. **httpx over fetch**: All HTTP calls use Python's `httpx` with async support, replacing Cloudflare's `fetch` API.

6. **asyncio over Workers**: Cloudflare Worker isolates are replaced by Python asyncio tasks within FastAPI workers.

7. **Ollama-first AI**: The AI gateway prioritises Ollama (local, zero-cost) over cloud providers, with OpenRouter free tier as fallback.

8. **No External Dependencies**: Every port must work with zero paid services. Optional providers (OpenAI, Anthropic) are just that — optional.
