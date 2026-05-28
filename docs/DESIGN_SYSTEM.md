# Trancendos Platform — Design System

> Canonical reference for all development work on the Trancendos / Tranc3 platform.
> Every naming decision, code pattern, architectural layer, and energy constant defined here
> takes precedence over any older document or comment in the codebase.

---

## 1. Tier Hierarchy

The platform organises all AI entities into five tiers, each with a distinct base class,
identity record, and lifecycle contract.

| Tier | Role | Base class | Identity record | ID prefix |
|------|------|-----------|-----------------|-----------|
| **T1 — Orchestrator** | Sovereign governance, cross-pillar coordination | `TrancOne` | `TrancOneDNA` | `AID-LMN-*` |
| **T2 — Prime** | Pillar / domain leader, HIL-A authority | `T2ance` | `T2anceDNA` | `AID-*` |
| **T3 — Lead AI** | Location manager, adaptive + genetic + liquid | `Tranc3` | `Tranc3DNA` | `AID-*` |
| **T4 — Agent** | Mid-tier automation, alpha/beta roles | `InfinityAgent` | `AgentDNA` | `SID-*` |
| **T5 — Bot** | Atomic nanoservice worker, slots 01–04 | `InfinityBot` | `BotDNA` | `NID-*` |

### Base class locations

```text
src/entities/templates/
  trance_one_base.py      ← TrancOne   (T1)
  t2ance_base.py          ← T2ance     (T2)
  tranc3_base.py          ← Tranc3     (T3)
  infinity_agent_base.py  ← InfinityAgent (T4)
  infinity_bot_base.py    ← InfinityBot   (T5)
```

### Slot / role rules

- T1: exactly three slots — 1 (Cornelius McIntyre), 2 (The Queen), 3 (tAImra). Slot 3 is opt-in.
- T4: role must be `"alpha"` or `"beta"` — enforced at construction.
- T5: slot must be `"01"` | `"02"` | `"03"` | `"04"` — enforced at construction.

---

## 2. Canonical Entity Names

All 43 platform entities are defined in `PLATFORM_ENTITIES.md` and `src/entities/platform.py`.
**Never invent names** — look them up. Key rules:

| Rule | Correct | Wrong |
|------|---------|-------|
| Space in The Digital Grid | `The Digital Grid` | `TheDigitalGrid` |
| No apostrophe | `Sashas Photo Studio` | `Sasha's Photo Studio` |
| Lead AI capitalisation | `tAImra` (Lead AI) | `tAimra` (location name) |
| Full Guardian title | `The Guardian (Anchor: Orb of Orisis)` | `The Guardian` |

### Naming in code

```python
# CORRECT — look up via entity registry
from src.entities.platform import get_entity_by_pid
entity = get_entity_by_pid("PID-TDG")  # The Digital Grid

# CORRECT — use canonical constant
from src.entities.platform import PLATFORM_ENTITIES
```

---

## 3. Energy & Crystal Terminology

The platform uses a crystal/energy metaphor for resource classes, routing priorities,
and computational cost tiers.

| Term | Domain | Usage |
|------|--------|-------|
| **Dialithium** | Primary power crystal | High-priority tasks, premium routing, Crystal Bridge energy source |
| **Trilithium** | Stabiliser crystal | Consistency / quorum operations, cross-bridge stabilisation |
| **Crystal** | Generic energy | Base routing token; Crystal Bridge default carrier |
| **Lightning** | Impulse energy | Transwarp Bridge short-burst high-speed transfers |
| **Light** | Continuous energy | Cell Bridge ambient propagation, cellular automata ticks |
| **Transwarp** | Warp-drive class | Transwarp Bridge topology; high-throughput async corridors |
| **Cell** | Cellular unit | Cell Bridge cellular automata grid; micro-state units |

### Constants location

```python
# src/bridge/energy_constants.py
from src.bridge.energy_constants import (
    DIALITHIUM_PRIORITY,
    TRILITHIUM_STABILITY_FACTOR,
    CRYSTAL_BASE_COST,
    LIGHTNING_BURST_LIMIT_MS,
    LIGHT_AMBIENT_TICK_HZ,
)
```

### Routing cost model

```text
Dialithium ──▶ cost × 1.0   (highest priority, Crystal Bridge)
Trilithium ──▶ cost × 0.8   (stability-weighted)
Crystal    ──▶ cost × 0.6   (standard)
Lightning  ──▶ cost × 0.3   (burst, Transwarp Bridge)
Light      ──▶ cost × 0.1   (ambient, Cell Bridge)
```

---

## 4. Three-Bridge Architecture

Three specialised bridges handle different classes of inter-service communication.

```text
┌─────────────────────────────────────────────────────────────────┐
│                     Cross-Bridge Orchestrator                    │
│          (Dimensional.cross_bridge_orchestrator)                 │
└──────────────┬──────────────────┬──────────────────┬────────────┘
               │                  │                  │
      ┌────────▼───────┐ ┌────────▼───────┐ ┌───────▼────────┐
      │  Crystal Bridge│ │Transwarp Bridge│ │   Cell Bridge  │
      │  (Dialithium / │ │  (Lightning)   │ │    (Light)     │
      │  Trilithium)   │ │                │ │                │
      └────────────────┘ └────────────────┘ └────────────────┘
```

| Bridge | Energy | Best for | Pattern |
|--------|--------|----------|---------|
| **Crystal Bridge** | Dialithium / Trilithium | Persistent state, consensus, quorum writes | Request–response |
| **Transwarp Bridge** | Lightning | High-throughput async pipelines, event streams | Fire-and-forget / stream |
| **Cell Bridge** | Light | Cellular automata propagation, distributed counters | Tick-based diffusion |

### Bridge coordinator import

```python
from Dimensional.cross_bridge_orchestrator import CrossBridgeOrchestrator
from Dimensional.three_bridge_coordinator import ThreeBridgeCoordinator
```

---

## 5. Module Namespace — Dimensional

The platform's core shared library is **`Dimensional`** (renamed from `shared_core` in Phase 24).
All new imports **must** use `Dimensional.*`.

```text
Dimensional/
  __init__.py
  bus.py                          ← event bus
  error_handlers.py
  cross_bridge_orchestrator.py
  three_bridge_coordinator.py
  architecture/                   ← OCI/MicroCeph/Vault/Sentinel/proactive
  dimensionals/                   ← service bus, registry, underverse
  hive/                           ← HIVE autoscaler, sentinel bridge
  infinity/                       ← auth, RBAC, ABAC, bridge, sentinel cluster
  nexus/                          ← Raft consensus, Nexus core
  pillars/                        ← pillar entity definitions
  gas/                            ← Maxwell-Boltzmann pressure routing
  liquid/                         ← LTC ODE router
  genetics/                       ← NSGA-II genetic optimiser
```

### Import pattern — graceful degradation

Always wrap `Dimensional` imports in `try/except ImportError` at module level
so services start cleanly even when the package isn't installed:

```python
try:
    from Dimensional.gas.pressure import PressureBalancer
    from Dimensional.liquid.ltc_router import LiquidRouter
    from Dimensional.genetics.optimizer import GeneticOptimizer
    from Dimensional.genetics.fitness import LatencyThroughputFitness
    _DIMENSIONAL_AVAILABLE = True
except ImportError:
    _DIMENSIONAL_AVAILABLE = False
    PressureBalancer = LiquidRouter = GeneticOptimizer = LatencyThroughputFitness = None
```

---

## 6. Adaptive Subsystems

Three adaptive subsystems are wired into every T3 Lead AI (and optionally T2 Primes).

### 6.1 Gas — Maxwell-Boltzmann Pressure Routing

```python
from Dimensional.gas.pressure import PressureBalancer
from Dimensional.gas.kinetic import KineticEnergyTracker

balancer = PressureBalancer(peers)
result = balancer.select()          # returns .selected peer
tracker = KineticEnergyTracker(worker="SID-NXS-01")
tracker.record(rps)
temp = balancer.system_temperature()  # scalar load indicator
```

- **Cycle interval** is dynamically derived from `system_temperature() / 100`, clamped 1–30 s.
- Temperature > 1000 triggers a SWOT threat ("System pressure critical").

### 6.2 Liquid — LTC ODE Router

```python
from Dimensional.liquid.ltc_router import LiquidRouter

router = LiquidRouter(peers)
result = router.route(signals)   # signals: dict[str, float] | None
target = result.target
```

Liquid Time-Constant (LTC) ODEs provide smooth context-continuity for routing decisions.
Use when request pattern has temporal correlation (e.g. user session affinity).

### 6.3 Genetics — NSGA-II Multi-Objective Optimiser

```python
from Dimensional.genetics.optimizer import GeneticOptimizer
from Dimensional.genetics.fitness import LatencyThroughputFitness

optimizer = GeneticOptimizer(fitness=LatencyThroughputFitness())
result = await optimizer.evolve(generations=30, pop_size=20)
best = result.best_config   # dict of optimised parameters
```

Schedule `evolve()` periodically (e.g. every 100 cycles) to adapt routing weights.

---

## 7. SWOT Self-Assessment Pattern

Every T1–T3 entity exposes `assess_swot()` returning a `SWOTSnapshot`:

```python
from src.entities.templates.tranc3_base import SWOTSnapshot

snap: SWOTSnapshot = entity.assess_swot()
# snap.strengths / .weaknesses / .opportunities / .threats  — list[str]
# snap.age_seconds()  — seconds since last assessment
```

### Standard SWOT triggers

| Condition | Category | Message |
|-----------|----------|---------|
| `health_score > 0.8` | Strength | "High health score" |
| `in_home_hub == True` | Strength | "Operating within home hub — full power-ups active" |
| `error_count > 5` | Weakness | "Elevated error count: N" |
| `latency_ms > 500` | Weakness | "High latency: Nms" |
| `health_score < 0.4` | Threat | "Critical health degradation — escalate to Prime" |
| `gas.temperature > 1000` | Threat | "System pressure critical — consider scale-out" |

---

## 8. HIL-A (Human-in-the-Loop Authority)

HIL-A is the escalation mechanism for decisions exceeding an entity's authority threshold.

```text
T5 Bot  ──escalates──▶  T4 Agent  ──escalates──▶  T3 Lead AI
T3 Lead AI ──escalates──▶ T2 Prime ──escalates──▶ T1 Orchestrator
```

```python
from src.entities.templates.t2ance_base import HILARequest

req = HILARequest(
    description="Approval required for budget > £10k",
    raised_by="AID-NXS-01",
    authority_required=0.9,
)
prime.raise_hila(req)
# ...later...
prime.decide_hila(req.request_id, approved=True, reason="Board authorised")
```

---

## 9. Worker Service Pattern

Every worker in `workers/*/worker.py` follows the same FastAPI structure:

```python
# Standard worker skeleton
from fastapi import FastAPI
from Dimensional.architecture.adaptive_pulse import AdaptivePulse
from Dimensional.architecture.proactive_orchestrator import ProactiveOrchestrator

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    yield
    # shutdown

app = FastAPI(title="<service-name>-worker", version="1.0.0", lifespan=lifespan)

# Health endpoint (required)
@app.get("/health")
async def health(): return {"status": "ok", "service": "<name>"}

# Metrics endpoint (required)
@app.get("/metrics")
async def metrics(): ...
```

### Port assignments

| Port | Service |
|------|---------|
| 8000 | tranc3-backend (main FastAPI) |
| 8001 | nanoservices |
| 8004 | infinity-ws (The Nexus) |
| 8005 | infinity-auth (Infinity) |
| 8006 | users-service |
| 8007 | monitoring (The Observatory) |
| 8008 | notifications |
| 8009 | infinity-ai (AI Gateway) |
| 8010 | the-grid (The Digital Grid) |
| 8011–8013 | products / orders / payments |
| 8014–8015 | files / identity |
| 8016–8029 | P3 stub workers |

---

## 10. Inference Pipeline — 5-Tier Fallback

```text
Request → infinity-ai (:8009) → AIGatewayRouter
  Tier 1: Ollama          localhost:11434  (zero-cost, local)
  Tier 2: HuggingFace     free inference API
  Tier 3: OpenRouter      free :models
  Tier 4: TRANC3_BACKEND  Fly.io :8000
  Tier 5: OfflineProvider deterministic stub
```

All tiers implement `BaseProvider.complete(messages) -> str`.
Circuit breaker per provider — half-open retry after 60 s.

---

## 11. Code Conventions

### Imports

```python
# 1. stdlib
import asyncio, logging, time, uuid

# 2. third-party (exact-pinned in requirements.txt)
from fastapi import FastAPI
from pydantic import BaseModel

# 3. Dimensional (graceful-degradation wrapper)
try:
    from Dimensional.gas.pressure import PressureBalancer
    _GAS_AVAILABLE = True
except ImportError:
    _GAS_AVAILABLE = False

# 4. src.*
from src.entities.platform import get_entity_by_pid
```

### Dependency pinning — exact versions only

```text
# CORRECT
fastapi==0.115.12
pydantic==2.11.5

# WRONG — never use ranges
fastapi>=0.100
pydantic~=2.0
```

### Logging

```python
logger = logging.getLogger(__name__)
logger.info("%s started (tier=%d)", self.dna, self.TIER)
# Use %-formatting, not f-strings, for lazy evaluation
```

### Error handling

```python
# Use canonical error codes from error_catalog
from src.errors.error_catalog import ErrorCode
raise HTTPException(status_code=400, detail=ErrorCode.INVALID_PAYLOAD.value)
```

### Security boundaries

- Validate **all** external inputs at the API boundary (`src/validation/`)
- Never validate internal service-to-service calls (trust the mesh)
- Wrap secrets access through The Void (`workers/infinity-void/`) — never hardcode
- All endpoints require JWT unless explicitly public (`/health`, `/metrics`)

---

## 12. Testing Standards

```text
tests/
  test_smoke.py          # fast sanity checks (<2 s)  — run first
  test_uat.py            # user acceptance / end-to-end journeys
  test_chaos.py          # fault injection + resilience (The Chaos Party)
  test_penetration.py    # OWASP injection / security boundary
  test_compliance.py     # error catalog, MCP protocol, GDPR
  test_nanoservices.py   # nanoservice layer (port 8001)
  test_compatibility.py  # JSON-RPC 2.0, Pydantic v2, serialisation
  test_validation.py     # input validation + schema enforcement
  test_spark_grid_integration.py  # The Spark + The Digital Grid
```

All tests emit structured results to `logs/test_results.jsonl`.

Test bootstrap mode — no model weights required. `Tranc3Engine` falls back:
`Ollama → OpenRouter → honest stub`.

---

## 13. CI/CD — The Workshop (Forgejo)

All CI runs through Forgejo at `trancendos.com/the-workshop`. **No GitHub Actions.**

```text
.forgejo/workflows/
  deploy-fly.yml          # backend + bots to Fly.io
  deploy-cloudflare.yml   # legacy CF Workers (phasing out)
  security-scan.yml       # pip-audit, bandit, semgrep, gitleaks
  dependency-audit.yml    # weekly + on-PR CVE scanning
```

Pre-commit hooks run locally: ruff → black → isort → bandit → semgrep → gitleaks → safety.

---

## 14. Production Infrastructure

```text
Traefik (reverse proxy + TLS)
  └── 26 FastAPI workers (ports 8004–8029)
  └── Vault (Shamir unseal, secrets)
  └── Prometheus → Grafana dashboards
  └── Loki + Promtail (log aggregation)
  └── IPFS (content-addressed storage)
```

All services are subdirectories of `trancendos.com` — not subdomains.
Zero paid dependencies target: eliminate all cost-incurring third-party APIs.

---

## 15. Dimensional Nexus & Raft Consensus

The Nexus (`workers/infinity-ws/`, port 8004) uses Raft for distributed consensus:

```python
from Dimensional.nexus.raft.raft_core import RaftNode, RaftState

node = RaftNode(node_id="nexus-01", peers=["nexus-02", "nexus-03"])
await node.start()
# state: FOLLOWER → CANDIDATE → LEADER
```

Leader election timeout: 150–300 ms randomised. Heartbeat: 50 ms.

---

*Last updated: Phase 27 (AeonMind v0.9.0 + Three-Bridge Architecture)*
*Maintained by: The Workshop CI + Cornelius McIntyre (T1 Orchestrator)*
