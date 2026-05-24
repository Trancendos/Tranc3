# Phase 27: Dimensional Nexus — Central Nervous System

**Branch:** `phase-24/aeonmind-polyglot-v0.9.0`  
**Commit:** `8ef9c3b`  
**Date:** 2025-05-24  
**Status:** Complete — 53 tests passing, 2781 total suite green

---

## Overview

The Dimensional Nexus is the Central Nervous System of the Tranc3 platform. It provides a unified coordination layer that binds together causal event ordering, tier-aware access control, real-time health monitoring, and cross-dimensional event routing into a single cohesive subsystem.

The Nexus sits at the heart of the `Dimensional` package (formerly `shared_core`, renamed in Phase 27) and exposes its capabilities through both a Python API and a FastAPI HTTP surface on port 8050.

---

## Architecture

```
                    ┌─────────────────────────────────────┐
                    │         DimensionalNexus             │
                    │     (Central Coordinator)            │
                    └──────┬──────┬──────┬──────┬──────────┘
                           │      │      │      │
              ┌────────────┘      │      │      └────────────┐
              ▼                   ▼      ▼                   ▼
   ┌──────────────────┐ ┌──────────────┐ ┌────────────┐ ┌───────────────┐
   │CausalOrdering    │ │TierAccess    │ │Health      │ │EventRouter    │
   │Engine            │ │Bridge        │ │Aggregator  │ │               │
   │                  │ │              │ │            │ │               │
   │• Vector clocks   │ │• Tier check  │ │• SQLite    │ │• Channel subs │
   │• Causality hash  │ │• RBAC        │ │• Heartbeat │ │• Handlers     │
   │• Event buffer    │ │• ABAC        │ │• Anomalies │ │• Routing tbl  │
   └──────────────────┘ └──────────────┘ └────────────┘ └───────────────┘
```

---

## Subsystems

### 1. CausalOrderingEngine

Distributed vector-clock implementation for cross-dimensional event ordering. Every event that flows through the Nexus is tagged with a vector clock timestamp, enabling precise causality tracking even when events originate from different dimensions with varying network latencies.

**Key capabilities:**
- **`increment()`** — Advance the local vector clock
- **`merge(incoming_clock)`** — Merge a foreign vector clock (happens-before relation)
- **`happened_before(a, b)`** — Determine if clock `a` causally precedes `b`
- **`concurrent(a, b)`** — Determine if two events are causally independent
- **`compute_causality_hash()`** — Deterministic hash of the current clock state for integrity verification
- **`record_event(event)`** — Store an event with its vector clock; buffer is size-bounded (configurable via `NEXUS_EVENT_BUFFER_SIZE` env var, default 10,000)
- **`get_ordered_events()`** — Retrieve all buffered events sorted by causal order

**Data model:**
```python
class NexusEvent(BaseModel):
    event_id: str          # UUID
    channel: SentinelChannel
    source_dimension: str
    source_tier: int       # 0-5
    event_type: str
    payload: dict = {}
    vector_clock: Dict[str, int] = {}
    timestamp: str         # ISO 8601
    correlation_id: Optional[str] = None
    causality_hash: Optional[str] = None
```

### 2. TierAccessBridge

Unified access control that enforces the Tranc3 Tier hierarchy through a layered check pipeline. Every access decision traverses: explicit deny → tier hierarchy → RBAC → ABAC → combined decision.

**Tier Hierarchy (enforced top-down):**
| Tier | Name | Description |
|------|------|-------------|
| 0 | HUMAN | Human operators — unrestricted |
| 1 | ORCHESTRATOR | System orchestration layer |
| 2 | PRIME | Prime-level AI coordination |
| 3 | AI | The overarching ML/LLM Complex |
| 4 | AGENT | Lower-level autonomous AI |
| 5 | BOT | Stateless service worker/function |

**Key capabilities:**
- **`check_access(request)`** — Full access decision pipeline returning `NexusAccessDecision`
- **`add_deny(subject, resource)`** / **`remove_deny()`** — Explicit deny list management
- **`add_rbac_policy()`** / **`add_abac_policy()`** — Policy registration

**Decision flow:**
```
Request → Explicit Deny? → Tier Check → RBAC Policies → ABAC Policies → Combined Decision
              │                  │             │               │               │
           DENIED           TIER_OK      RBAC_RESULT     ABAC_RESULT     ALLOW/DENY
```

**Data models:**
```python
class NexusAccessRequest(BaseModel):
    subject: str
    resource: str
    action: str
    subject_tier: int
    resource_tier: int
    context: dict = {}

class NexusAccessDecision(BaseModel):
    allowed: bool
    reason: str
    tier_valid: bool
    rbac_result: Optional[bool] = None
    abac_result: Optional[bool] = None
    evaluation_time_ms: float
```

### 3. HealthAggregator

Real-time health monitoring across all dimensional services, backed by SQLite for zero-cost persistence. Services register, send heartbeats, and the aggregator tracks their status while detecting anomalies like stale heartbeats and error-rate spikes.

**Key capabilities:**
- **`register_service()`** — Register a new service in the health database
- **`update_heartbeat()`** — Record a heartbeat with optional metrics
- **`get_summary()`** — Get aggregate health summary across all services
- **`detect_anomalies()`** — Identify stale heartbeats (>30s since last) and high error rates (>0.1)

**Data models:**
```python
class NexusServiceHealth(BaseModel):
    service_id: str
    dimension: str
    tier: int
    status: str = "healthy"    # healthy | degraded | unhealthy | unknown
    last_heartbeat: Optional[str] = None
    error_rate: float = 0.0
    latency_ms: float = 0.0
    metadata: dict = {}

class NexusHealthSummary(BaseModel):
    total_services: int
    healthy: int
    degraded: int
    unhealthy: int
    unknown: int
    services: List[NexusServiceHealth]
    timestamp: str
```

### 4. EventRouter

Channel-based event distribution system built on the `SentinelChannel` enum. Services subscribe to channels, register handlers, and the router dispatches published events to all matching handlers.

**SentinelChannel values:**
`PLATFORM` | `AGENTS` | `MODELS` | `WORKFLOWS` | `SECURITY` | `HIVE` | `NEXUS` | `BRIDGE` | `PILLARS` | `INFRASTRUCTURE` | `EVENTS`

**Key capabilities:**
- **`subscribe(channel, subscriber_id)`** / **`unsubscribe()`** — Channel subscription management
- **`register_handler(channel, handler)`** — Register an async callback for a channel
- **`publish(event)`** — Dispatch an event to all subscribers and handlers on the event's channel
- **`get_routing_table()`** — Return the full subscription map

### 5. DimensionalNexus (Central Coordinator)

The top-level coordinator that integrates all four subsystems and provides a unified interface. It also manages the service topology graph (nodes + edges) and exposes a FastAPI application factory.

**Key capabilities:**
- **`register_service(service)`** — Register a service with both the HealthAggregator and EventRouter
- **`add_topology_edge()`** — Add a connection between dimensional services
- **`emit_event(event)`** — Record event in causal engine and route to subscribers
- **`check_access(request)`** — Delegate to TierAccessBridge
- **`get_topology()`** — Return the full topology graph
- **`get_status()`** — Return comprehensive Nexus status

**Data models:**
```python
class NexusTopologyNode(BaseModel):
    node_id: str
    dimension: str
    tier: int
    service_type: str
    metadata: dict = {}

class NexusTopologyEdge(BaseModel):
    source: str
    target: str
    edge_type: str
    metadata: dict = {}
```

---

## FastAPI Surface

The `create_nexus_app()` factory produces a FastAPI application with the following endpoints:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Aggregate health summary |
| GET | `/health/{service_id}` | Individual service health |
| POST | `/access` | Access control decision |
| POST | `/events` | Emit an event |
| GET | `/events` | Get ordered events |
| GET | `/topology` | Service topology graph |
| POST | `/services` | Register a new service |
| GET | `/status` | Comprehensive Nexus status |

**Default port:** 8050  
**Startup:** `uvicorn Dimensional.nexus.nexus_core:create_nexus_app() --port 8050`

---

## Test Coverage

53 tests across 6 test classes:

| Class | Tests | Coverage |
|-------|-------|----------|
| TestCausalOrderingEngine | 11 | Vector clock increment, merge, happened_before, concurrent, hash, record, buffer limit |
| TestTierAccessBridge | 12 | Tier checks, deny list, hierarchy enforcement, RBAC/ABAC integration |
| TestHealthAggregator | 7 | Register, heartbeat, summary, anomaly detection |
| TestEventRouter | 7 | Subscribe, publish, handlers, routing table |
| TestDimensionalNexus | 8 | Integration: register, emit, access, topology, status |
| TestDataModels | 6 | Model defaults and auto-field generation |

All 53 tests pass. Full suite: **2781 passed, 21 skipped, 0 failed**.

---

## Zero-Cost Infrastructure

The Dimensional Nexus maintains the platform's zero-cost infrastructure commitment:

- **SQLite** for health persistence (no external database required)
- **In-process event routing** (no message broker dependency)
- **Vector clocks** for causal ordering (no external coordination service)
- **FastAPI + Uvicorn** for HTTP surface (lightweight, no license cost)
- All dependencies are open-source Python packages

---

## File Map

```
Tranc3/
├── Dimensional/
│   └── nexus/
│       ├── __init__.py          (42 lines)  — Package init, public API exports
│       └── nexus_core.py        (1037 lines) — Full implementation
└── tests/
    └── test_dimensional_nexus.py (795 lines) — 53 test cases
```

---

## Relationship to Previous Phases

| Phase | Contribution | Nexus Connection |
|-------|-------------|-----------------|
| Phase 23 | Forensic audit, Sentinel system | EventRouter uses SentinelChannel |
| Phase 24 | AeonMind Polyglot v0.9.0 | Nexus can coordinate polyglot services |
| Phase 25 | Repo review, architecture docs | Tier hierarchy formalized here |
| Phase 26 | Directory restructuring | `shared_core` → `Dimensional` rename |
| Phase 27 | **This phase** | Nexus is the central nervous system |

---

## Next Steps

- **Infinity Portal Authentication**: JWT-based login/register flow with tier-aware session management
- **Nexus Dashboard**: Real-time web UI for health monitoring and event visualization
- **Cross-Worker Heartbeat Protocol**: Standardized heartbeat format for all dimensional workers
- **Topology Visualization**: Graph-based visualization of the dimensional service mesh
