# Phase 27: Three-Bridge Architecture — Nexus, HIVE, and InfinityBridge

**Branch:** `phase-24/aeonmind-polyglot-v0.9.0`  
**Date:** 2025-05-24  
**Status:** Complete — 120 tests passing (67 Nexus + 53 HIVE), full suite green

---

## Overview

Sentinel Station routes three distinct types of traffic through the Tranc3 platform, each handled by a dedicated bridge system:

| Bridge | Traffic Type | Description |
|--------|-------------|-------------|
| **InfinityBridge** | User context / human traffic | Light bridges connecting users across Admin, Arcadia, and The Citadel |
| **The Nexus** | AI, Agent, and Bot traffic | Routing and coordination for intelligence entities (Tier 3–5) |
| **The HIVE** | Data movement and swarm systems | Data pipelines, chunk routing, swarm coordination, flow monitoring |

These are **three separate systems**, each purpose-built for its traffic type. They share the Dimensional package for core services but are architecturally distinct.

**Critical Distinction:**
- **Nexus** = AI, Agent, and Bot movement and traffic ONLY
- **Dimensional** = Core/shared services package
- **"DimensionalNexus"** = Only valid when referring to BOTH Dimensional AND Nexus in conjunction — NOT a merged system
- **The HIVE** = Data movement and swarm coordination ONLY
- **InfinityBridge** = User/human traffic ONLY

---

## Three-Bridge Architecture

```
                        ┌──────────────────────┐
                        │   Sentinel Station    │
                        │  (Interplexus Hub)    │
                        │   Redis Pub/Sub +     │
                        │   In-Process Fallback │
                        └──────┬───────┬───────┘
                               │       │
              ┌────────────────┤       ├────────────────┐
              │                │       │                │
    ┌─────────▼─────────┐  ┌──▼───────▼──┐  ┌──────────▼──────────┐
    │  InfinityBridge   │  │  The Nexus  │  │     The HIVE        │
    │  (Light Bridges)  │  │             │  │                     │
    │                   │  │ AI/Agent/Bot│  │ Data movement &     │
    │  User traffic     │  │ traffic &   │  │ swarm coordination  │
    │  Human context    │  │ coordination│  │                     │
    │  Tier 0           │  │ Tier 3-5    │  │ Pipelines & Swarms  │
    └───────────────────┘  └──────┬──────┘  └──────────┬──────────┘
                                │                     │
                    ┌───────────┼───────────┐    ┌────┼─────┐
                    │           │           │    │    │     │
              ┌─────▼──┐ ┌─────▼──┐ ┌─────▼──┐  ┌▼──┐ ┌▼──┐ ┌▼──┐
              │Causal  │ │Tier    │ │Health  │  │Flow│ │Pipe│ │Swrm│
              │Ordering│ │Access  │ │Aggreg  │  │Mon │ │Mgmt│ │Coor│
              │Engine  │ │Bridge  │ │        │  │    │ │    │ │    │
              └────────┘ └────────┘ └────────┘  └────┘ └────┘ └────┘
```

---

## Bridge 1: InfinityBridge — User/Human Traffic

The InfinityBridge handles all user context and human movement across the platform. Users traversing between Admin, Arcadia, and The Citadel use the light bridges of the InfinityBridge.

**Defined in:** `Dimensional/infinity/nomenclature.py`
```python
TransferSystem.BRIDGE  # "bridge" — The Infinity Bridge
InfinityLocation.BRIDGE  # "infinity_bridge"
SentinelChannel.BRIDGE  # "bridge" — Bridge User Events
```

**Transfers:** Users  
**Description:** User transfer system within Infinity — connects Admin, Arcadia, and The Citadel

The InfinityBridge infrastructure already exists within the `Dimensional/infinity/` package, including the Infinity Portal, Auth Gateway, and Sentinel Station for event distribution.

---

## Bridge 2: The Nexus — AI, Agent, and Bot Traffic

The Nexus is the dedicated routing and coordination system for AI, Agent, and Bot traffic (Tier 3–5). It provides causal event ordering, tier-aware access control, real-time health aggregation, cross-Nexus event routing, and a live WebSocket dashboard.

**Package:** `Dimensional/nexus/`  
**Port:** 8050

### Nexus Subsystems

#### CausalOrderingEngine
Distributed vector-clock implementation for cross-Nexus event ordering. Every AI/Agent/Bot event is tagged with a vector clock timestamp, enabling precise causality tracking.

**Key capabilities:**
- `increment()` — Advance the local vector clock
- `merge(incoming_clock)` — Merge a foreign vector clock (happens-before relation)
- `happened_before(a, b)` — Determine if clock `a` causally precedes `b`
- `concurrent(a, b)` — Determine if two events are causally independent
- `compute_causality_hash()` — Deterministic hash of the current clock state
- `record_event(event)` — Store an event with its vector clock (buffer size configurable)
- `get_ordered_events()` — Retrieve all buffered events sorted by causal order

#### TierAccessBridge
Unified access control enforcing the Tranc3 Tier hierarchy through a layered check pipeline: explicit deny → tier hierarchy → RBAC → ABAC → combined decision.

**Tier Hierarchy:**
| Tier | Name | Description |
|------|------|-------------|
| 0 | HUMAN | Human operators — unrestricted |
| 1 | ORCHESTRATOR | System orchestration layer |
| 2 | PRIME | Prime-level AI coordination |
| 3 | AI | The overarching ML/LLM Complex |
| 4 | AGENT | Lower-level autonomous AI |
| 5 | BOT | Stateless service worker/function |

#### HealthAggregator
Real-time health monitoring for AI/Agent/Bot services, backed by SQLite for zero-cost persistence. Tracks status, detects anomalies (stale heartbeats, error-rate spikes).

#### EventRouter
Channel-based event distribution built on `SentinelChannel`. Services subscribe to channels, register handlers, and the router dispatches published events.

#### NexusSentinelBridge
Bidirectional event bridge between The Nexus and Sentinel Station. AI/Agent/Bot events are forwarded to Sentinel for cross-worker distribution; Sentinel events are routed into the Nexus for dashboard visualization and causal tracking.

### Nexus FastAPI Surface

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Nexus info with three-bridge architecture |
| GET | `/health` | Aggregate health summary |
| GET | `/health/anomalies` | Anomaly detection results |
| GET | `/health/service/{service_id}` | Individual service health |
| POST | `/access/check` | Access control decision |
| GET | `/access/tiers` | Tier hierarchy definition |
| POST | `/events/emit` | Emit an AI/Agent/Bot event |
| GET | `/events/recent` | Get recent events in causal order |
| GET | `/events/routing` | Event routing table |
| GET | `/topology` | Full topology graph |
| POST | `/services/register` | Register a new AI/Agent/Bot service |
| POST | `/services/heartbeat` | Submit a service heartbeat |
| GET | `/status` | Comprehensive Nexus status with three_bridges |
| GET | `/dashboard` | Real-time dashboard web UI |
| WS | `/ws/events` | WebSocket live event streaming |

### Nexus Status Response
```json
{
  "nexus_id": "nexus-abc12345",
  "bridge_type": "nexus",
  "description": "AI, Agent, and Bot traffic coordination",
  "three_bridges": {
    "infinity_bridge": "User context / human traffic (Light bridges)",
    "nexus": "AI, Agent, and Bot movement and traffic (THIS)",
    "hive": "Data movement and swarm system coordination"
  },
  "tier_hierarchy": { "HUMAN": 0, "ORCHESTRATOR": 1, "PRIME": 2, "AI": 3, "AGENT": 4, "BOT": 5 }
}
```

---

## Bridge 3: The HIVE — Data Movement and Swarm Coordination

The HIVE is the dedicated routing and coordination system for data movement and swarm systems. It handles data pipelines, chunk routing with priority and replication, distributed swarm coordination for data processing, and flow monitoring with throughput/latency tracking.

**Package:** `Dimensional/hive/`  
**Port:** 8060

### HIVE Subsystems

#### FlowMonitor
Monitors data flow through the HIVE. Tracks throughput (Mbps), latency (ms), chunk delivery rates, and error rates for all data pipelines and swarm operations. Backed by SQLite for persistent metrics.

**Key capabilities:**
- `record_throughput(pipeline_id, mbps)` — Record a throughput sample
- `record_latency(pipeline_id, latency_ms)` — Record a latency sample
- `record_chunk_status(status)` — Track chunk delivery/pend/fail counts
- `get_throughput(pipeline_id)` — Average throughput over last 60s
- `get_latency(pipeline_id)` — Average latency over last 60s
- `get_summary()` — Aggregate flow metrics across all pipelines

#### SwarmCoordinator
Manages data-processing swarms — groups of nodes processing shared data tasks (ETL, aggregation, replication, etc.). Handles the full lifecycle: formation, task distribution, scaling, completion, and dissolution.

**Key capabilities:**
- `create_swarm(name, purpose)` — Create a new data-processing swarm
- `add_node(swarm_id, node)` — Add a processing node (auto-activates forming swarms)
- `remove_node(swarm_id, node_id)` — Remove a node (drains swarm if empty)
- `update_task_progress(swarm_id, node_id, completed, failed)` — Track task progress
- `dissolve_swarm(swarm_id)` — Release all nodes and dissolve the swarm
- `list_swarms(status)` — List swarms, optionally filtered by status

**Swarm Lifecycle:**
```
FORMING → ACTIVE → SCALING → COMPLETED
                  → DRAINING → (removed)
                  → FAILED
```

#### PipelineManager
Manages data pipelines — the routes through which data chunks flow from sources to sinks. Handles pipeline creation, chunk routing, replication, delivery tracking, and status management.

**Key capabilities:**
- `create_pipeline(name, source_id, sink_ids, priority, replication)` — Create a pipeline
- `start_pipeline(pipeline_id)` — Start a pending pipeline
- `pause_pipeline(pipeline_id)` — Pause a running pipeline
- `route_chunk(chunk)` — Route a data chunk through its pipeline
- `list_pipelines(status)` — List pipelines, optionally filtered by status

**Replication:** Capped at `HIVE_MAX_REPLICATION` (default 5) to prevent runaway replication.

### HIVE Data Models

```python
class DataPriority(str, Enum):
    CRITICAL | HIGH | NORMAL | LOW | BACKGROUND

class SwarmStatus(str, Enum):
    FORMING | ACTIVE | SCALING | DRAINING | COMPLETED | FAILED

class PipelineStatus(str, Enum):
    PENDING | RUNNING | PAUSED | COMPLETED | FAILED

class HiveDataSource(BaseModel):
    source_id, name, data_type, pillar, throughput_mbps, status, metadata

class HiveDataSink(BaseModel):
    sink_id, name, data_type, pillar, consumption_rate_mbps, status, metadata

class DataChunk(BaseModel):
    chunk_id, pipeline_id, source_id, sink_id, priority, size_bytes,
    checksum, status, hops, created_at, delivered_at, metadata

class Swarm(BaseModel):
    swarm_id, name, purpose, status, nodes, data_type,
    total_tasks, completed_tasks, failed_tasks, metadata

class DataPipeline(BaseModel):
    pipeline_id, name, source_id, sink_ids, status, priority,
    replication_factor, total_chunks, delivered_chunks, failed_chunks,
    throughput_mbps, latency_ms, metadata
```

### HIVE FastAPI Surface

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | HIVE info with three-bridge architecture |
| GET | `/status` | Comprehensive HIVE status |
| GET | `/health` | HIVE health summary |
| POST | `/sources` | Register a data source |
| GET | `/sources` | List all data sources |
| POST | `/sinks` | Register a data sink |
| GET | `/sinks` | List all data sinks |
| POST | `/pipelines` | Create a data pipeline |
| POST | `/pipelines/{id}/start` | Start a pipeline |
| POST | `/pipelines/{id}/pause` | Pause a pipeline |
| GET | `/pipelines` | List all pipelines |
| POST | `/swarms` | Create a data-processing swarm |
| GET | `/swarms` | List all swarms |
| POST | `/swarms/{id}/nodes` | Add a processing node |
| DELETE | `/swarms/{id}/nodes/{nid}` | Remove a processing node |
| DELETE | `/swarms/{id}` | Dissolve a swarm |
| POST | `/route` | Route a data chunk |
| GET | `/flow` | Flow monitoring summary |
| WS | `/ws` | WebSocket live event streaming |

### HIVE Status Response
```json
{
  "hive_id": "hive-abc12345",
  "bridge_type": "hive",
  "description": "Data movement and swarm system coordination",
  "three_bridges": {
    "infinity_bridge": "User context / human traffic (Light bridges)",
    "nexus": "AI, Agent, and Bot movement and traffic",
    "hive": "Data movement and swarm system coordination (THIS)"
  },
  "flow": { "total_throughput_mbps": 0, "avg_latency_ms": 0, "chunks_delivered": 0 }
}
```

---

## Nomenclature Integration

The three bridges are formally defined in `Dimensional/infinity/nomenclature.py`:

```python
class TransferSystem(str, Enum):
    NEXUS = "nexus"      # The Nexus — AI, Agent, and Bot traffic
    HIVE = "hive"        # The HIVE — Data movement and swarm systems
    BRIDGE = "bridge"    # The Infinity Bridge — User traffic

TRANSFER_SYSTEMS = {
    TransferSystem.NEXUS: {
        "name": "The Nexus",
        "transfers": "AI's, Agents, and Bots",
        "description": "Routing and distribution system for all intelligence entities (Tier 3-5)",
    },
    TransferSystem.HIVE: {
        "name": "The HIVE",
        "transfers": "Data",
        "description": "Data transfer system that moves information across the entire ecosystem",
    },
    TransferSystem.BRIDGE: {
        "name": "The Infinity Bridge",
        "transfers": "Users",
        "description": "User transfer system within Infinity — connects Admin, Arcadia, and The Citadel",
    },
}

class SentinelChannel(str, Enum):
    # ...
    HIVE = "hive"       # HIVE Data Events
    NEXUS = "nexus"     # Nexus Entity Events (AI/Agent/Bot movement)
    BRIDGE = "bridge"   # Bridge User Events
    # ...
```

---

## Dimensional Package — Core/Shared Services

The `Dimensional` package provides core/shared services that all three bridges use:

- **Models** — EventMessage, ServiceInfo, ServiceHealth, VectorClock
- **EventBus** — In-process event distribution
- **Security** — JWT, password hashing, RBAC, ABAC
- **Registry** — Service discovery and registration
- **Path/URL Validation** — Security hardening
- **Error Handlers** — Safe error responses
- **Log Sanitization** — Structured logging with PII protection
- **Optional Imports** — Lazy loading for heavy dependencies

The Dimensional package is NOT a bridge itself. It is the shared foundation upon which the bridges are built.

---

## Test Coverage

### Nexus Tests (67)
| Class | Tests | Coverage |
|-------|-------|----------|
| TestCausalOrderingEngine | 11 | Vector clock increment, merge, happened_before, concurrent, hash, record, buffer limit |
| TestTierAccessBridge | 12 | Tier checks, deny list, hierarchy enforcement, RBAC/ABAC integration |
| TestHealthAggregator | 7 | Register, heartbeat, summary, anomaly detection |
| TestEventRouter | 7 | Subscribe, publish, handlers, routing table |
| TestNexusIntegration | 8 | Integration: register, emit, access, topology, status |
| TestNexusSingleton | 2 | Singleton pattern, instance type |
| TestDataModels | 6 | Model defaults and auto-field generation |
| TestNexusWSManager | 4 | Connect/disconnect, channel subscribe, broadcast, dead cleanup |
| TestDashboardEndpoint | 2 | Dashboard HTML, root endpoint listing |
| TestNexusSentinelBridge | 8 | Bridge creation, stats, pause/resume, status, forwarding, singleton |

### HIVE Tests (53)
| Class | Tests | Coverage |
|-------|-------|----------|
| TestFlowMonitor | 6 | Throughput, latency, chunk tracking, empty state |
| TestSwarmCoordinator | 9 | Create, add/remove nodes, task progress, completion, dissolution, filtering |
| TestPipelineManager | 9 | Create, start, pause, route chunks, replication cap, filtering |
| TestHiveIntegration | 12 | Sources, sinks, pipelines, swarms, routing, events, status, health |
| TestHiveSingleton | 2 | Singleton pattern, instance type |
| TestHiveDataModels | 9 | Priority enum, SwarmStatus, PipelineStatus, all model defaults |
| TestHiveApp | 3 | App creation, root endpoint, status endpoint |

**Total: 120 tests passing.**

---

## Zero-Cost Infrastructure

All three bridges maintain the platform's zero-cost infrastructure commitment:

- **SQLite** for persistence (Nexus health, HIVE flow metrics — no external database)
- **In-process routing** (no message broker dependency for local operations)
- **Vector clocks** for causal ordering (no external coordination service)
- **FastAPI + Uvicorn** for HTTP surfaces (lightweight, no license cost)
- **WebSocket** for live dashboards (no polling overhead)
- **Sentinel Station** provides cross-worker event distribution via Redis Pub/Sub with in-process fallback
- All dependencies are open-source Python packages

---

## File Map

```
Tranc3/
├── Dimensional/
│   ├── nexus/
│   │   ├── __init__.py           — Package init, exports Nexus as primary class
│   │   ├── nexus_core.py         — Nexus coordinator + FastAPI + WebSocket
│   │   ├── sentinel_bridge.py    — Bidirectional Sentinel Station bridge
│   │   └── dashboard.html        — Real-time web dashboard UI
│   ├── hive/
│   │   ├── __init__.py           — Package init, exports Hive as primary class
│   │   └── hive_core.py          — Hive coordinator + FastAPI + WebSocket
│   └── infinity/
│       ├── nomenclature.py       — TransferSystem enum (NEXUS, HIVE, BRIDGE)
│       ├── sentinel_station.py   — Redis Pub/Sub hub (Interplexus)
│       └── worker_bridges.py     — Worker integration bridges
├── workers/
│   └── dimensional-nexus-service/
│       ├── Dockerfile            — Docker deployment
│       ├── requirements-worker.txt — Python dependencies
│       └── worker.py             — Standalone Nexus worker entry point
└── tests/
    ├── test_nexus.py             — 67 Nexus test cases
    └── test_hive.py              — 53 HIVE test cases
```

---

## Backward Compatibility

The `DimensionalNexus` name is preserved as a backward-compatible alias for `Nexus`:

```python
# In nexus_core.py:
DimensionalNexus = Nexus  # Only valid when referring to both Dimensional AND Nexus

# In __init__.py:
from Dimensional.nexus.nexus_core import Nexus, DimensionalNexus
```

This alias should ONLY be used when referring to both the Dimensional package AND The Nexus in conjunction. For the Nexus specifically, always use the `Nexus` class name.

The old test file `test_dimensional_nexus.py` is superseded by `test_nexus.py`.

---

## Relationship to Previous Phases

| Phase | Contribution | Connection |
|-------|-------------|-----------|
| Phase 22 | Infinity Portal, Auth Gateway, Sentinel Station | Bridges connect through Sentinel Station |
| Phase 23 | Forensic audit, Sentinel system | All three bridges use SentinelChannel |
| Phase 24 | AeonMind Polyglot v0.9.0 | Nexus coordinates polyglot AI/Agent/Bot services |
| Phase 25 | Repo review, architecture docs | Tier hierarchy formalized |
| Phase 26 | Directory restructuring | `shared_core` → `Dimensional` rename |
| Phase 27 | **This phase** | Three-bridge architecture implemented |

---

## Next Steps

- **HIVE Worker Service**: Create `workers/hive-service/` with Dockerfile and worker entry point
- **HIVE Dashboard**: Real-time data flow visualization web UI
- **InfinityBridge Coordinator**: Dedicated coordinator class for user traffic (currently modeled in nomenclature.py)
- **Cross-Bridge Event Flow**: Events flowing between all three bridges through Sentinel Station
- **Nexus Cluster Mode**: Multi-node Nexus with Raft consensus for HA
- **HIVE Swarm Auto-Scaling**: Dynamic swarm node allocation based on pipeline throughput
