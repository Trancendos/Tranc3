# Service Doc-Pack — The Digital Grid (Workflow DAG Engine)

> Code-grounded Doc Pack per `docs/framework/DESIGN-GOVERNANCE-FRAMEWORK.md`.
> Claims cite `src/workflow/`.

**Service:** The Digital Grid · **Slug:** `the-digital-grid` · **Lead AI:** Tyler Towncroft (AID-DGR-01, Tier 3) · **Prime:** The Doctor / Nikolai O'denhim (Tier 2)
**Canonical status:** ✅ In repo → **Live** tier (status per `CLAUDE.md`; identity/PID-DGR per `PLATFORM_ENTITIES.md`)
**Code root:** `src/workflow/` · **Worker:** `the-grid` (port 8010) · **Owner:** Platform Engineering
**Version:** 1.0.0 · **Last verified against `main`:** 2026-07-02 @ `2250aaf`

---

## 1. Service Governance Charter (GOV)

- **Mission:** Build and execute workflow **DAGs** (n8n-style) — a fluent builder plus a
  topological executor that runs independent nodes in parallel layers, with an event bus
  for observability.
- **In scope:** workflow definition/registration, topological scheduling, node execution
  across a typed node registry, execution state tracking, cancellation, status reporting.
- **Out of scope:** model inference (Luminous / AI Gateway), tool registry (The Spark),
  auth issuance (Infinity), long-term persistence beyond execution records.
- **Lead AI (Tier 3):** Tyler Towncroft; **Prime (Tier 2):** The Doctor (Nikolai O'denhim).
- **SLOs (target):** availability 99.5%, workflow scheduling overhead p99 < 100 ms
  (excl. node work), error budget 0.5%/30d.
- **Review cadence:** Quarterly, or on any change to the workflow API or executor semantics.
- **Hard dependencies:** none to build/schedule; individual nodes may call other services.

## 2. Detailed Design Document (DDD)

- **Component breakdown:**

  | Module | Responsibility |
  |--------|----------------|
  | `src/workflow/builder.py` | `WorkflowBuilder` (fluent DAG DSL) + `WorkflowDefinition` |
  | `src/workflow/executor.py` | `WorkflowExecutor` (`_topological_sort`, `_build_adjacency`, `_gather_inputs`, parallel layer execution), `ExecutionState`, `WorkflowEventBus` |
  | `src/workflow/nodes/` | Typed node registry: `agents`, `ai`, `code`, `data`, `flow`, `http`, `neural`, `reasoning`, `tools` (+ `base`, `registry`) |
  | `src/workflow/phase4_nodes.py`, `phase5_nodes.py` | Extended node packs (`register_phase`, `extend_node_registry`) |
  | `src/workflow/routes.py` | FastAPI routes (see interface) |

- **Public interface (routes, `src/workflow/routes.py`):**

  | Method | Route | Handler |
  |--------|-------|---------|
  | GET | `/status` | `grid_status` |
  | GET | `/workflows` | `list_workflows` |
  | POST | `/workflows` | `register_workflow` |
  | GET | `/workflows/{workflow_id}` | `get_workflow` |
  | POST | `/workflows/{workflow_id}/run` | `run_workflow` |
  | GET | `/executions/{execution_id}` | `get_execution` |
  | POST | `/executions/{execution_id}/cancel` | `cancel_execution` |

- **Data model:** `WorkflowDefinition` (nodes + edges); `ExecutionState` (per-run status,
  node outputs); node registry keyed by node type.
- **Key sequence flow:**
  ```text
  POST /workflows/{id}/run
    → executor._build_adjacency() → _topological_sort()
    → for each layer: execute independent nodes in parallel
        (_gather_inputs from upstream outputs → node.run())
    → ExecutionState updated; WorkflowEventBus emits node/execution events
    → GET /executions/{id} returns status + outputs
  ```
- **Error handling:** node failures recorded on `ExecutionState`; canonical codes via
  `src/errors/error_catalog.py`; cancellation via `/executions/{id}/cancel`.
- **Concurrency / state:** async; each topological layer's independent nodes run
  concurrently; `WorkflowEventBus` fans execution events to subscribers.

## 3. Technical Architecture Solutions Design (TASD)

- **Context:** the platform's workflow/automation engine; foundation `src/workflow/`;
  open-source alignment target n8n (self-host free) per `CLAUDE.md`.
- **Architecture decisions:**

  | ID | Decision | Options | Why | Consequence |
  |----|----------|---------|-----|-------------|
  | AD-1 | In-house topological DAG executor | n8n, Prefect, Temporal, Airflow | zero-cost, no external runtime, tight platform integration | must maintain scheduler ourselves |
  | AD-2 | Parallel execution per topological layer | sequential, full async graph | throughput without a full dataflow engine | layer granularity, not per-edge streaming |
  | AD-3 | Typed node registry (`nodes/`) + phase packs | monolithic node file | extensibility, isolation per node class | registry must be kept in sync |

- **Non-functional drivers:** zero-cost, extensibility, observability (event bus), parallelism.
- **Rejected alternatives:** external orchestrators (operational cost / vendor runtime).

## 4. RACI Matrix

| Activity | Platform Owner | Tyler Towncroft (Lead AI) | Platform Eng | Town Hall | SRE/On-call |
|----------|:--:|:--:|:--:|:--:|:--:|
| Workflow API change | A | C | R | C | I |
| New node type | C | C | R | I | I |
| Deploy | A | I | R | I | C |
| Incident response | I | I | C | I | **R/A** |
| Doc verification | I | I | R | **A** | I |

## 5. Solutions Integration Model (SIM)

- **Upstream (callers):** services/agents registering and running workflows via the routes;
  The Spark surfaces grid status (`/mcp/grid/status`).
- **Downstream:** node types reach out per class — `http` nodes (external calls), `ai`/`neural`
  nodes (Luminous / AI Gateway), `tools` nodes (The Spark), `agents` nodes (agent runtimes).
- **Events:** `WorkflowEventBus` publishes node-start/complete/fail + execution lifecycle.
- **Auth boundary:** routes behind platform auth (Infinity/JWT).
- **Data classification:** workflow payloads may carry user data; persistence limited to
  execution records.

## 6. Architecture Scalability Document (ASD)

- **Load model:** concurrency bounded by DAG width per layer × registered workflows in flight.
- **Scaling levers:** horizontal executor workers; cap parallelism per layer; offload
  heavy nodes (AI/HTTP) to their own rate-limited services.
- **Bottlenecks:** a very wide layer of heavy nodes; unbounded execution history in memory.
- **Zero-cost limits & hard stops:** nodes calling rate-limited free services (AI, HTTP)
  MUST honour the platform quota-monitor + hard-stop / rotation policy (`src/ai_gateway/`);
  the executor fails the affected node, not the whole run.
- **Degradation:** a failing node fails its branch; independent branches continue; partial
  results are retained on `ExecutionState`.

## 7. Deployment Scope Matrix (DSM)

- **Mode awareness:** No — this entity's own code does not call `PlatformInfraMode` / `src/platform/infrastructure_mode.py` (repo-wide grep confirms none of the 43 named platform entities branch on `PLATFORM_INFRA_MODE`/`SYSTEM_MODE` directly). Its deployment scope is determined externally — by which `docker-compose.production.yml` service block runs, and where — not by in-process mode detection.
- **Runtime placement:** standalone worker with its own `docker-compose.production.yml` service block (`the-grid`, port 8010) and its own Traefik route — does not run inside the `tranc3-backend` monolith
- **Persistence:** named volume attached to the `the-grid` compose service — state survives container restarts/redeploys in any mode
- **Note:** this entity has **two** deployment surfaces — a router mounted in the `tranc3-backend` monolith (`api.py`) *and* a separate standalone worker (`the-grid`, port 8010). The table below describes the standalone worker; the monolith-mounted router follows the monolith's own placement (see the monolith pattern noted across this platform's other entities) and shares its volume.

| Setup | What runs, and where | Data locality | Hard blockers / caveats |
|---|---|---|---|
| **Cloud-Only** | the `the-grid` compose block runs on a single cloud host; Traefik/edge in front | persists via its attached volume as long as the volume/disk is preserved on that host | none beyond standard single-host durability (no built-in cross-host replication) |
| **Hybrid** | same `the-grid` compose block; per `docs/architecture/infrastructure-modes.md`'s Hybrid diagram, this worker itself still runs as a single instance (cloud or local host), with only shared persistent data (not specific to this worker) split via TrueNAS/Syncthing | as above, optionally local-synced if a volume exists | requires `CITADEL_LOCAL_STACK=true` if a local compose stack should run alongside the cloud one |
| **Local-Only** | same `the-grid` compose block, run entirely on local/Citadel hardware behind local Traefik | fully local, volume-backed | none beyond standard local-hardware ops |

- **Zero-cost posture per mode:** Cloud-Only defaults to the `zero_cost_cloud` AI-rotation chain; Hybrid/Local-Only default to `zero_cost_full` (`config/platform/infrastructure_mode.yaml`) — this only affects AI-Gateway-routed calls, not this entity's own logic
- **Switching modes:** operator-level via `PLATFORM_INFRA_MODE` (or legacy `SYSTEM_MODE`); this entity needs no code change to move between modes, only a redeploy-target change for its own compose block

## 8. Technology Framework Matrix (TFM)

| Layer | Technology | Version | Licence | Zero-cost? | CVE posture |
|-------|-----------|---------|---------|:----------:|-------------|
| Runtime | Python | 3.11+ | PSF | ✅ | see `docs/SECURITY-ASSESSMENT.md` |
| Framework | FastAPI + Starlette | pinned | MIT/BSD | ✅ | clean |
| Concurrency | asyncio | stdlib | PSF | ✅ | — |
| Validation | Pydantic v2 | pinned | MIT | ✅ | clean |
| Design target (OSS) | n8n (reference) | — | Fair-code (self-host free) | ✅ | — |

## 9. Policy (POL)

- **Applicable platform policies:** `POL-AI-001`, `POL-OPS-002` — see `docs/policies/`.
- **Service-specific rules:** `code` nodes execute logic — must run within platform
  sandboxing/validation; no arbitrary unauthenticated code execution via public routes.
- **Data handling:** execution payloads follow the calling context's data classification.
- **Access:** workflow routes require a valid platform token (Infinity); tier limits per
  `src/monetisation/`.

## 10. Procedure (PROC)

- **Deploy:** as the `the-grid` worker (port 8010) and/or mounted routes; CI via
  `.forgejo/workflows/`.
- **Add a node type:** implement under `src/workflow/nodes/`, register in the node registry
  (or via `register_phase`/`extend_node_registry`); add tests.
- **Register a workflow:** `POST /workflows` or a prebuilt factory
  (`ml_training_workflow`, `self_healing_workflow`, `spark_ignition_workflow`).
- **Config change:** through change gate (`docs/procedures/PROC-CHG-001-Change-Request.md`).

## 11. Runbook (RUN)

- **Health check:** `GET /status` → grid status body.
- **Key alerts → action:**

  | Alert | Likely cause | First action | Escalation |
  |-------|-------------|--------------|------------|
  | Executions stuck | node hung / downstream dependency down | inspect `/executions/{id}`; cancel; check node's target service | SRE → Platform Eng |
  | Run failure spike | bad workflow or node regression | identify failing node type from events; isolate | Platform Eng |
  | Memory growth | execution history retention | cap/evict history; restart worker | SRE |

- **Diagnostics:** `WorkflowEventBus` events; structured logs with `trace_id`; metrics `/metrics`.
- **Rollback:** redeploy previous image; workflow API is versioned/backward-compatible by policy.
- **Recovery:** re-register workflows from source factories; in-flight executions are re-runnable.

## 12. Standards (STD)

- **API standard:** REST conventions (`src/workflow/routes.py`).
- **Error standard:** canonical `ErrorCode` enum — `src/errors/error_catalog.py`.
- **Logging standard:** structured JSON, `trace_id`/`service_name`, no secrets.
- **Test standard:** `tests/test_spark_grid_integration.py` (Spark + Grid integration),
  plus workflow-executor unit coverage.
- **Naming standard:** "The Digital Grid" — always with a space (per `CLAUDE.md`).

---

## Verification Log

| Date | Verifier | Commit | Result |
|------|----------|--------|--------|
| 2026-07-02 | Platform Engineering | `2250aaf` | Routes, executor internals (topological sort + parallel layers), node registry, event bus, and prebuilt workflows verified against `src/workflow/`. Lead AI/Prime per PLATFORM_ENTITIES.md PID-DGR. |
