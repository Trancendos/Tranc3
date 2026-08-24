# Location-to-Location Traffic Matrix

> **What this is.** An honest map of what actually exists today for understanding which Locations
> talk to which — and a plain statement of what doesn't. The obvious-sounding candidate,
> `workers/topology-service/`, turns out to document something else entirely; this doc corrects
> that and points to the real (partial) building blocks instead of inventing a matrix that isn't
> there.

**Owner:** Platform Owner Trancendos · **Version:** 1.1.0 · **Last verified:** 2026-08-21

---

## 1. Correction: `topology-service` is not this

`workers/topology-service/worker.py` (port 8031, `CLAUDE.md`'s Self-Hosted Worker Map) is the
obvious first place to look for "Location-to-Location traffic" and is not it. Its schema
(`topology_state`, `topology_history`, `node_health`, `migrations` tables; `ModeSwitchRequest`,
`NodeRegister`, `NodeHealthUpdate`, `MigrationCreate` models) is entirely about **deployment-mode
topology**: which of `TRUE_NAS` / `HYBRID` / `CLOUD_ONLY` (`FAILOVER_ORDER` in that file) a node is
running under, node health, and migrations between modes — the Fortiere Cloud-Only/Hybrid/Local
model from `CLAUDE.md`'s Architecture section. It has no concept of a Location, no request/byte
counters, and nothing resembling an inter-service traffic graph. Nothing needs fixing here; the
worker is doing its actual job correctly. It just isn't a traffic matrix, and no other file in the
repo is either — this document exists to say so plainly rather than leave the gap implicit.

## 2. What real, populated data exists today

Three things come close, none of them a traffic matrix:

| Source | What it actually tracks | Populated? |
|---|---|---|
| `docker-compose.production.yml` `depends_on:` (31 occurrences) | Container **startup ordering** — e.g. `grafana` depends on `prometheus`/`loki`, `promtail` depends on `loki` | Yes — this is real, live compose config |
| `src/mesh/types.py`'s `ServiceDescriptor.dependencies: list[str]` + `ServiceMesh.get_dependency_graph()` (`src/mesh/service_mesh.py`) | A per-service list of upstream dependencies, exposed as a graph | **No** — grepping every `ServiceMesh.register()`/`ServiceDescriptor(...)` call site in the repo, none ever passes `dependencies=`. The method is real and callable; the graph it returns today is empty for every service |
| `docs/governance/AI-RELATIONSHIP-MATRIX.md` / `src/relations/registry.py` | Pairwise **trust/relationship scores** between the 39 Lead AIs, plus an Activity Feed and per-Location "brochure" (visit stats, sentiment, highlights) | Yes — SQLite-backed, live, mounted at `/relations` |

The `depends_on:` graph is infrastructure startup ordering, not business traffic — it says
Grafana must come up after Prometheus, not that Royal Bank of Arcadia sends N requests/day to
Arcadian Exchange. The Relationship Matrix is explicit that it does not model this either:
`AI-RELATIONSHIP-MATRIX.md` §9 lists **"Location-to-Location relationships (e.g. Cryptex and The
Ice Box cooperating on a threat response) — currently only AI-to-AI and AI-to-Location (via the
feed) are modelled"** as a brainstormed, not-built extension.

## 3. The actual gap

No file in this repository — code or doc — currently instruments or reports real inter-Location
traffic: request counts, message volumes, or data flow between the 43 canonical Locations. The
platform's real inter-service transport carriers (The HIVE's queue/agent coordination, The Nexus's
AI communications hub, The Digital Grid's workflow DAG execution, The Spark's MCP tool-call
routing) each move real traffic between Locations today, but none of them currently expose a
queryable "who talked to whom, how much" view. The Observatory (`src/observability/`) is the
platform's audit/metrics layer and is the natural home for this if it's ever built, but it does
not do so today.

## 4. Path forward, if this is ever prioritized

> **Update, 2026-08-21.** A fourth option — declaring the intended flows and measuring them —
> has since been built: `docs/governance/LOCATION-FLOW-CONTRACT.md`, backed by
> `config/estate/flow_contract.yaml` and `scripts/flow_conformance.py`. It does not produce
> traffic volumes and does not replace options 1–3 below; it establishes whether each declared
> flow exists in code at all, which turned out to be the prior question. Of 39 declared flows,
> 14 are reached by nothing.

Not committed work — recorded here so a future pass doesn't have to re-derive it:

1. **Cheapest, static**: populate `ServiceDescriptor.dependencies` at each service's real
   registration call site and read `ServiceMesh.get_dependency_graph()` — turns an already-built,
   already-tested method from dead code into a real static dependency graph.
2. **Cheapest, semantic**: extend `src/relations/registry.py`'s Activity Feed with a
   Location-to-Location event type (the extension its own §9 already names), giving actual
   observed traffic a place to land using infrastructure that already exists and is tested.
3. **Real traffic counts**: instrument request/message counters in The Observatory, keyed by
   source and destination Location — the only option that would produce genuine volume data
   rather than a static or activity-derived graph.

## 5. Cross-references

- `docs/governance/AI-RELATIONSHIP-MATRIX.md` — the closest real, live system; §9 names this exact
  gap
- `workers/topology-service/worker.py` — deployment-mode topology; not inter-Location traffic
- `CLAUDE.md`'s Architecture section — the Fortiere Cloud-Only/Hybrid/Local model `topology-service`
  actually serves
