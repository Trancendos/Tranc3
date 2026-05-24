# Phase 27: Dimensional Nexus — Central Nervous System

**Branch:** `phase-24/aeonmind-polyglot-v0.9.0`  
**Commits:** `8ef9c3b` → `79dc8e8` → `537b84f`  
**Date:** 2025-05-24  
**Status:** Complete — 67 tests passing, 2795 total suite green

---

## Overview

The Dimensional Nexus is the Central Nervous System of the Tranc3 platform. It provides a unified coordination layer that binds together causal event ordering, tier-aware access control, real-time health monitoring, cross-dimensional event routing, live WebSocket dashboard streaming, and bidirectional Sentinel Station integration into a single cohesive subsystem.

The Nexus sits at the heart of the `Dimensional` package (formerly `shared_core`, renamed in Phase 27) and exposes its capabilities through both a Python API and a FastAPI HTTP surface on port 8050. A Docker-ready worker service is provided for standalone deployment.

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
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
   ┌──────────────────┐    ┌───────────────────┐
   │ NexusWSManager   │    │NexusSentinelBridge│
   │ (WebSocket)      │    │(Bidirectional)    │
   │                  │    │                   │
   │• Live dashboard  │    │• Nexus → Sentinel │
   │• Channel subs    │    │• Sentinel → Nexus │
   │• Dead conn clean │    │• Pause/Resume     │
   └──────────────────┘    └───────────────────┘
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
- **`record_event(event)`** — Store an event with its vector clock; buffer is size-bounded (configurable via `buffer_size` parameter or `NEXUS_EVENT_BUFFER_SIZE` env var, default 10,000)
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
- **`emit_event(event)`** — Record event in causal engine, route to subscribers, and broadcast to WebSocket dashboards
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

### 6. NexusWSManager (NEW)

WebSocket connection manager for live event streaming to dashboards. Manages connections, tracks channel subscriptions, and broadcasts events in real-time with automatic dead-connection cleanup.

**Key capabilities:**
- **`connect(ws, channels)`** — Accept a WebSocket connection with optional channel subscriptions
- **`disconnect(ws)`** — Clean up a connection from all tracking lists
- **`broadcast(event)`** — Send an event to all connected dashboards and channel subscribers

**Integration:** Events emitted through `DimensionalNexus.emit_event()` are automatically broadcast to all connected WebSocket clients.

### 7. NexusSentinelBridge (NEW)

Bidirectional event bridge between the Dimensional Nexus and the Sentinel Station. Events published to the Nexus are forwarded to the Sentinel Station for cross-worker distribution, and Sentinel events are routed into the Nexus for dashboard visualization and causal tracking.

**Channel Mapping:**
| Sentinel (lowercase) | Nexus (SentinelChannel) |
|---------------------|------------------------|
| `platform` | `PLATFORM` |
| `agents` | `AGENTS` |
| `models` | `MODELS` |
| `workflows` | `WORKFLOWS` |
| `security` | `SECURITY` |
| `hive` | `HIVE` |
| `nexus` | `NEXUS` |
| `bridge` | `BRIDGE` |
| `pillars` | `PILLARS` |
| `infrastructure` | `INFRASTRUCTURE` |
| `events` | `EVENTS` |

**Key capabilities:**
- **`attach_sentinel(sentinel_station)`** — Attach to a Sentinel Station and register handlers
- **`on_sentinel_event()`** — Forward Sentinel events into the Nexus
- **`pause_sentinel_forward()`** / **`resume_sentinel_forward()`** — Control Nexus→Sentinel flow
- **`pause_nexus_forward()`** / **`resume_nexus_forward()`** — Control Sentinel→Nexus flow
- **`get_status()`** — Bridge status including stats and channel map

**Stats tracking:** `nexus_to_sentinel`, `sentinel_to_nexus`, `errors`

---

## Dimensional Dashboard

A real-time web dashboard served from the `/dashboard` endpoint. Features:

- **6 tabs:** Overview, Health, Events, Topology, Access Control, Tier Hierarchy
- **Live event feed** via WebSocket with channel color-coding
- **Service health cards** with status indicators and tier badges
- **Canvas-based topology graph** visualization with tier-colored nodes and directional edges
- **Interactive access control checker** with decision logging
- **Channel distribution grid** showing event counts per Sentinel channel
- **Auto-refresh** every 10 seconds for health and anomaly data

**Technology:** Pure HTML + CSS + JavaScript, no build tools required. Connects to the Nexus via REST API and WebSocket.

---

## Dimensional Nexus Worker Service

A Docker-ready standalone service for deploying the Nexus:

**Files:**
```
workers/dimensional-nexus-service/
├── Dockerfile
├── requirements-worker.txt
└── worker.py
```

**Startup initialization:**
- Registers 8 core dimensional services (nexus-self, infinity-portal, infinity-auth, sentinel-station, health-aggregator, the-grid, tranc3-ai, deepagents-orchestrator)
- Builds 11 default topology edges connecting core services
- Emits a `nexus_startup` event on the NEXUS channel
- Health check on `/health` endpoint

**Docker deployment:**
```bash
docker build -t dimensional-nexus .
docker run -p 8050:8050 dimensional-nexus
```

---

## FastAPI Surface

The `create_nexus_app()` factory produces a FastAPI application with the following endpoints:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Nexus info and endpoint listing |
| GET | `/health` | Aggregate health summary |
| GET | `/health/anomalies` | Anomaly detection results |
| GET | `/health/service/{service_id}` | Individual service health |
| POST | `/access/check` | Access control decision |
| GET | `/access/tiers` | Tier hierarchy definition |
| POST | `/events/emit` | Emit an event |
| GET | `/events/recent` | Get recent events in causal order |
| GET | `/events/routing` | Event routing table |
| GET | `/topology` | Full topology graph |
| GET | `/topology/nodes` | Topology nodes only |
| GET | `/topology/edges` | Topology edges only |
| POST | `/services/register` | Register a new service |
| POST | `/services/heartbeat` | Submit a service heartbeat |
| GET | `/status` | Comprehensive Nexus status |
| GET | `/dashboard` | Real-time dashboard web UI |
| WS | `/ws/events` | WebSocket live event streaming |

**Default port:** 8050  
**Startup:** `uvicorn Dimensional.nexus.nexus_core:app --host 0.0.0.0 --port 8050`

---

## Test Coverage

67 tests across 8 test classes:

| Class | Tests | Coverage |
|-------|-------|----------|
| TestCausalOrderingEngine | 11 | Vector clock increment, merge, happened_before, concurrent, hash, record, buffer limit |
| TestTierAccessBridge | 12 | Tier checks, deny list, hierarchy enforcement, RBAC/ABAC integration |
| TestHealthAggregator | 7 | Register, heartbeat, summary, anomaly detection |
| TestEventRouter | 7 | Subscribe, publish, handlers, routing table |
| TestDimensionalNexus | 8 | Integration: register, emit, access, topology, status |
| TestDataModels | 6 | Model defaults and auto-field generation |
| TestNexusWSManager | 4 | Connect/disconnect, channel subscribe, broadcast, dead cleanup |
| TestDashboardEndpoint | 2 | Dashboard HTML, root endpoint listing |
| TestNexusSentinelBridge | 8 | Bridge creation, stats, pause/resume, status, forwarding, singleton |

All 67 tests pass. Full suite: **2795 passed, 21 skipped, 0 failed**.

---

## Zero-Cost Infrastructure

The Dimensional Nexus maintains the platform's zero-cost infrastructure commitment:

- **SQLite** for health persistence (no external database required)
- **In-process event routing** (no message broker dependency)
- **Vector clocks** for causal ordering (no external coordination service)
- **FastAPI + Uvicorn** for HTTP surface (lightweight, no license cost)
- **WebSocket** for live dashboard (no polling overhead)
- **Sentinel Bridge** integrates with existing Sentinel Station (no new infrastructure)
- All dependencies are open-source Python packages

---

## File Map

```
Tranc3/
├── Dimensional/
│   └── nexus/
│       ├── __init__.py           (62 lines)  — Package init, public API exports
│       ├── nexus_core.py         (~1100 lines) — Full implementation + FastAPI + WebSocket
│       ├── sentinel_bridge.py    (~230 lines) — Bidirectional Sentinel Station bridge
│       └── dashboard.html        (~620 lines) — Real-time web dashboard UI
├── workers/
│   └── dimensional-nexus-service/
│       ├── Dockerfile            — Docker deployment
│       ├── requirements-worker.txt — Python dependencies
│       └── worker.py             (~160 lines) — Standalone worker entry point
└── tests/
    └── test_dimensional_nexus.py (~900 lines) — 67 test cases
```

---

## Relationship to Previous Phases

| Phase | Contribution | Nexus Connection |
|-------|-------------|-----------------|
| Phase 22 | Infinity Portal, Auth Gateway, Sentinel Station | Nexus Sentinel Bridge provides bidirectional flow |
| Phase 23 | Forensic audit, Sentinel system | EventRouter uses SentinelChannel from Phase 23 |
| Phase 24 | AeonMind Polyglot v0.9.0 | Nexus can coordinate polyglot services |
| Phase 25 | Repo review, architecture docs | Tier hierarchy formalized here |
| Phase 26 | Directory restructuring | `shared_core` → `Dimensional` rename |
| Phase 27 | **This phase** | Nexus is the central nervous system |

---

## Next Steps

- **Nexus Dashboard Enhancement**: Add time-series health charts and topology auto-layout
- **Nexus Cluster Mode**: Multi-node Nexus with Raft consensus for HA
- **Cross-Worker Heartbeat Protocol**: Standardized heartbeat format for all dimensional workers
- **Topology Auto-Discovery**: Automatic topology building from service registration
