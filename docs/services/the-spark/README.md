# Service Doc-Pack — The Spark (MCP Server)

> **Reference implementation** of the Trancendos per-service Doc Pack. Every claim below
> is grounded in code under `src/mcp/`. Governed by
> `docs/framework/DESIGN-GOVERNANCE-FRAMEWORK.md`.

**Service:** The Spark · **Slug:** `the-spark` · **Lead AI:** Imfy (AID-SPK-01, Tier 3) · **Prime:** Norman Hawkins (Tier 2)
**Canonical status:** ✅ In repo → **Live** tier (status per `CLAUDE.md`; identity/PID-SPK per `PLATFORM_ENTITIES.md`)
**Code root:** `src/mcp/` · **Routes prefix:** `/mcp` · **Owner:** Platform Engineering
**Version:** 1.0.0 · **Last verified against `main`:** 2026-07-02 @ `60b3b18`

---

## 1. Service Governance Charter (GOV)

- **Mission:** Expose the platform's AI tool registry to agents and services via a
  standards-compliant **Model Context Protocol** server (JSON-RPC 2.0 over HTTP + SSE).
- **In scope:** tool registration/discovery, JSON-RPC request handling, SSE event bus,
  semantic tool selection (RAG-MCP), prompt-injection scanning of inbound payloads
  (scanner module present; runtime wiring **PLANNED** — see §2), The Digital Grid
  status surfacing.
- **Out of scope:** model inference (delegated to Luminous / AI Gateway), workflow
  execution (The Digital Grid), auth issuance (Infinity).
- **Lead AI (Tier 3):** Imfy (AID-SPK-01); **Prime (Tier 2):** Norman Hawkins.
- **SLOs (target):** availability 99.5%, p99 `/mcp/rpc` latency < 250 ms (excl. tool work),
  error budget 0.5%/30d.
- **Review cadence:** Quarterly, or on any change to the JSON-RPC surface.
- **Hard dependencies:** none to serve the registry; tool execution may fan out to other
  services (see §5).

## 2. Detailed Design Document (DDD)

- **Component breakdown:**

  | Module | Responsibility |
  |--------|----------------|
  | `src/mcp/server.py` | JSON-RPC 2.0 handler, routes, `_SSEBus`, request/response/error models |
  | `src/mcp/tools.py` | Tool registry + tool implementations |
  | `src/mcp/tool_rag.py` | Semantic tool selection — FAISS `IndexFlatIP` + sentence-transformers |
  | `src/mcp/payload_scanner.py` | Prompt-injection scanner (`scan_rpc_payload` → `ScanFinding`/`ScanResult`). **Present but NOT yet wired into `server.py`'s `/mcp/rpc` handler — integration PLANNED.** |
  | `src/mcp/client.py` | Outbound `MCPClient` / `MCPClientPool` for remote MCP servers |
  | `src/mcp/spark_*_tools.py` | Tool packs: gbrain, knowledge, phase4, phase5 |

- **Public interface (routes, `src/mcp/server.py`):**

  | Method | Route | Auth (`Depends(get_current_user)`) | Purpose |
  |--------|-------|:--:|---------|
  | POST | `/mcp/rpc` | ✅ required | JSON-RPC 2.0 request/response |
  | GET | `/mcp/sse` | ✅ required | Server-Sent Events stream (`StreamingResponse`) |
  | GET | `/mcp/tools` | ⬜ open | List registered tools |
  | GET | `/mcp/health` | ⬜ open | Liveness/readiness |
  | GET | `/mcp/grid/status` | ⬜ open | The Digital Grid status passthrough |

- **Data model:** `MCPRequest` / `MCPResponse` / `MCPError` Pydantic models;
  `jsonrpc="2.0"` constant; standard JSON-RPC error codes defined in `server.py`.
- **Key sequence flow (as implemented in `server.py`):**
  ```text
  client → POST /mcp/rpc (auth: Depends(get_current_user))
        → parse/validate MCPRequest
        → dispatch to tool registry (tools.py, optionally tool_rag selection)
        → MCPResponse | MCPError → client
        (SSE subscribers notified via _SSEBus)
  ```
  > **PLANNED:** `payload_scanner.scan_rpc_payload()` is intended to run on the inbound
  > payload before dispatch, failing open with logging. It is **not yet called** from the
  > handler; until wired, prompt-injection scanning is not enforced at runtime.
- **Error handling:** JSON-RPC standard codes in `server.py`; platform canonical codes via
  `src/errors/error_catalog.py` (42 `ErrorCode` members defined). The scanner's documented
  fail-open-with-logging policy (`payload_scanner.py`) applies **once the PLANNED wiring lands**.
- **Concurrency / state:** async FastAPI; `_SSEBus` fans events to subscribers; tool RAG
  index is in-process and ephemeral (rebuildable, no persistent state required to serve).

## 3. Technical Architecture Solutions Design (TASD)

- **Context:** the platform's single MCP ingress for agent tool use; foundation `src/mcp/`.
- **Architecture decisions:**

  | ID | Decision | Options | Why | Consequence |
  |----|----------|---------|-----|-------------|
  | AD-1 | JSON-RPC 2.0 over HTTP+SSE | REST, gRPC, JSON-RPC | MCP spec compliance; agent interop | Must maintain JSON-RPC envelope discipline |
  | AD-2 | In-process FAISS `IndexFlatIP` for tool RAG | external vector DB, no RAG | zero-cost, no new deps (faiss-cpu + sentence-transformers already present) | Index is ephemeral; rebuilt on start |
  | AD-3 | Regex/heuristic payload scanner, fail-open | external moderation API, fail-closed | zero-cost, no external calls; availability over strictness | Heuristic coverage only; logged bypass on scanner error |

- **Non-functional drivers:** zero-cost (no paid APIs), MCP interop, low ingress latency,
  availability-biased security (fail-open scan with audit).
- **Rejected alternatives:** external vector DB (cost), gRPC (agent-ecosystem friction),
  fail-closed scanning (single-point denial risk).

## 4. RACI Matrix

| Activity | Platform Owner | Imfy (Lead AI) | Platform Eng | Town Hall | SRE/On-call |
|----------|:--:|:--:|:--:|:--:|:--:|
| JSON-RPC surface change | A | C | R | C | I |
| Deploy | A | I | R | I | C |
| Tool registration review | C | C | R | I | I |
| Incident response | I | I | C | I | **R/A** |
| Doc verification | I | I | R | **A** | I |

## 5. Solutions Integration Model (SIM)

- **Upstream (callers):** platform agents and services posting JSON-RPC to `/mcp/rpc`;
  SSE consumers on `/mcp/sse`.
- **Downstream:** registered tools may call other subsystems (knowledge/gbrain packs →
  vector stores; `/mcp/grid/status` → The Digital Grid). Outbound remote MCP via
  `MCPClientPool` (`client.py`) with `MCPClientError` handling.
- **Events:** `_SSEBus` broadcasts tool/registry events to SSE subscribers.
- **Auth boundary:** `/mcp/rpc` and `/mcp/sse` require a valid platform token
  (`Depends(get_current_user)`, Infinity/JWT). `/mcp/tools`, `/mcp/health`, and
  `/mcp/grid/status` are currently **unauthenticated** (see §2 route table). Inbound
  payload scanning via `payload_scanner` is **PLANNED**, not yet enforced.
- **Data classification:** tool arguments may carry user content; no secrets persisted by
  The Spark itself.

## 6. Architecture Scalability Document (ASD)

- **Load model:** request/response is stateless per call → scales horizontally behind
  Traefik; SSE holds long-lived connections (connection count is the primary limit).
- **Scaling levers:** add worker replicas; cap SSE subscribers per instance; RAG index is
  per-instance and cheap to rebuild.
- **Bottlenecks:** SSE fan-out memory; sentence-transformer model load at cold start.
- **Zero-cost limits & hard stops:** no paid dependency in the serving path. Any tool that
  reaches out to a rate-limited free service must honour the platform quota-monitor and
  hard-stop policy (see AI Gateway rotation, `src/ai_gateway/`) rather than failing the
  whole MCP endpoint.
- **Degradation:** if tool RAG is unavailable, fall back to exact/name-based tool lookup;
  if a downstream tool is down, return a JSON-RPC error for that call only.

## 7. Deployment Scope Matrix (DSM)

- **Mode awareness:** No — this entity's own code does not call `PlatformInfraMode` / `src/platform/infrastructure_mode.py`. (Some platform-wide, cross-cutting code *does* branch on the mode — `src/routers/adaptive.py` and `src/routers/ecosystem.py` read/set `PLATFORM_INFRA_MODE`/`SYSTEM_MODE` directly, and `Dimensional/architecture/storage_factory.py` selects a storage provider from `SYSTEM_MODE` — but none of that code is owned by this or any other one of the 43 named entities; it is shared platform infrastructure, not this service's own logic. The Citadel is the only one of the 43 named entities whose own code branches on the mode — see `docs/services/the-citadel/README.md`.) This entity's deployment scope is determined externally — by which `docker-compose.production.yml` service block runs, and where — not by in-process mode detection.
- **Runtime placement:** mounted in the `tranc3-backend` monolith (`api.py`); runs wherever that monolith's `docker-compose.production.yml` service block is deployed, on whatever port/host the monolith uses (compose service `tranc3-backend`)
- **Persistence:** None — this entity's own state is an ephemeral, in-process FAISS tool-RAG index that is rebuilt on start (per this pack's own ASD) — no persistence of its own. While the `tranc3-backend` monolith has a named volume, that volume backs *other* entities' state, not this one; this service's own state (if any) is lost on restart/redeploy in every mode alike.
- **Note:** stateless by design — its FAISS tool-RAG index is ephemeral and rebuilt on start (per this pack's own ASD), so the volume above matters to the monolith generally, not to The Spark specifically.

| Setup | What runs, and where | Data locality | Hard blockers / caveats |
|---|---|---|---|
| **Cloud-Only** | the `tranc3-backend` compose block runs on a single cloud host (e.g. Fly.io / Oracle Free Tier); Traefik/edge in front | ephemeral — this service holds no state of its own; the monolith's volume does not apply to it | no entity-specific blocker beyond whatever applies to the monolith as a whole |
| **Hybrid** | same monolith block; per `docs/architecture/infrastructure-modes.md`'s Hybrid diagram, persistent data can sync to local TrueNAS while the monolith itself still runs wherever it's deployed | ephemeral, same as Cloud-Only — this service's own state does not benefit from the Hybrid data-locality split | requires `CITADEL_LOCAL_STACK=true` if a local compose stack should run alongside the cloud one, per `should_run_citadel_docker()` in `infrastructure_mode.py` |
| **Local-Only** | same monolith block, run entirely on local/Citadel hardware behind local Traefik | still ephemeral — local hardware does not change this service's own statelessness | none beyond standard local-hardware ops (backup, power, network) |

- **Zero-cost posture per mode:** Cloud-Only defaults to the `zero_cost_cloud` AI-rotation chain; Hybrid/Local-Only default to `zero_cost_full` (`config/platform/infrastructure_mode.yaml`) — this only affects AI-Gateway-routed calls, not this entity's own logic
- **Switching modes:** operator-level via `PLATFORM_INFRA_MODE` (or legacy `SYSTEM_MODE`); this entity needs no code change to move between modes, only a redeploy-target change for the monolith as a whole

## 8. Technology Framework Matrix (TFM)

| Layer | Technology | Version | Licence | Zero-cost? | CVE posture |
|-------|-----------|---------|---------|:----------:|-------------|
| Runtime | Python | 3.11+ | PSF | ✅ | see `docs/SECURITY-ASSESSMENT.md` |
| Framework | FastAPI + Starlette | pinned | MIT/BSD | ✅ | clean |
| Transport | JSON-RPC 2.0 over HTTP + SSE | — | — | ✅ | — |
| Tool RAG | FAISS (`faiss-cpu`) + sentence-transformers | pinned | MIT/Apache | ✅ | clean |
| Validation | Pydantic v2 | pinned | MIT | ✅ | clean |

## 9. Environment Support Matrix (ESM)

> Grounded against `docker-compose.development.yml`, `docker-compose.uat.yml`, and `docker-compose.production.yml` — checked by exact compose service name, not assumed (see `docs/services/INDEX.md` for current platform-wide compose service totals, which change as the topology evolves).

| Environment | Covered? | What runs | Notes |
|---|---|---|---|
| **Dev** | Partial | the `api` service in `docker-compose.development.yml` runs the same `tranc3-backend` monolith, so this entity's router is present — but nothing exercises it specifically (no seed data, no entity-specific smoke test) | code is present, not validated in isolation |
| **UAT** | Partial | same monolith router via the `api` service in `docker-compose.uat.yml` | same caveat as Dev — present, not entity-specifically validated |
| **Production** | Yes | full detail in the DSM above | — |

- **Gap:** this entity has no standalone worker at all, so there is nothing *beyond* the monolith to have Dev/UAT coverage for — the gap is the same one every monolith-mounted route shares (present in all three environments' `api` service, but no entity-specific test/seed data distinguishes it from any other route in the same monolith).

## 10. Policy (POL)

- **Applicable platform policies:** `POL-AI-001` (AI Ethics & Governance),
  `POL-OPS-002`, `POL-PRI-001` — see `docs/policies/`.
- **Service-specific rules (target):** inbound `/mcp/rpc` payloads should be scanned for
  prompt injection with bypass events logged (audit to The Observatory). **Status: PLANNED
  — the scanner exists (`payload_scanner.py`) but is not yet wired into the handler.**
- **Data handling:** The Spark persists no user content; tool-level data handling is
  governed by the downstream service's policy.
- **Access:** `/mcp/rpc` and `/mcp/sse` require a valid platform token (Infinity); the
  read-only `/mcp/tools`, `/mcp/health`, `/mcp/grid/status` are currently open. Tier
  limits per `src/monetisation/`.

## 11. Procedure (PROC)

- **Deploy:** included in the FastAPI app (`api.py`) / worker image; CI via
  `.forgejo/workflows/` (no GitHub Actions).
- **Register a tool:** add to the relevant `spark_*_tools.py` pack via its `register_*`
  entrypoint; covered by `tests/test_spark_grid_integration.py`.
- **Config change:** through change gate (`docs/procedures/PROC-CHG-001-Change-Request.md`).
- **Secret rotation:** N/A for The Spark core (holds no secrets); downstream tools use The Void.

## 12. Runbook (RUN)

- **Health check:** `GET /mcp/health` → 200 with status body.
- **Key alerts → action:**

  | Alert | Likely cause | First action | Escalation |
  |-------|-------------|--------------|------------|
  | `/mcp/rpc` 5xx spike | tool exception / dependency down | check logs for tool id; isolate failing tool | SRE → Platform Eng |
  | SSE connection saturation | too many subscribers | scale replicas / cap subscribers | SRE |
  | Cold-start latency | model load | pre-warm / pin replica | SRE |

- **Diagnostics:** structured JSON logs with `trace_id`; Prometheus metrics are exposed at
  the app level (`/metrics` in `api.py`, and `/api/ecosystem/metrics` via the ecosystem
  router) — the MCP router itself serves only `/mcp/*`; traces via The Observatory
  (`src/observability/`).
- **Rollback:** redeploy previous image tag; MCP surface is backward-compatible by policy.
- **Recovery:** stateless — restart restores service; RAG index rebuilds automatically.

## 13. Standards (STD)

- **API standard:** JSON-RPC 2.0 (`jsonrpc="2.0"`, standard error codes) — `src/mcp/server.py`.
- **Error standard:** canonical `ErrorCode` enum — `src/errors/error_catalog.py`.
- **Logging standard:** structured JSON, `trace_id`/`service_name` bindings, no secrets.
- **Test standard:** `tests/test_spark_grid_integration.py`, compatibility + compliance
  suites (`tests/test_compatibility.py`, `tests/test_compliance.py` — MCP protocol checks).
- **Naming standard:** canonical entity names per `CLAUDE.md`.

---

## Verification Log

| Date | Verifier | Commit | Result |
|------|----------|--------|--------|
| 2026-07-02 | Platform Engineering | `60b3b18` | Initial pack authored against `src/mcp/`. |
| 2026-07-02 | Platform Engineering | `2250aaf` | Corrected error-code count (42) and Lead AI (Imfy). |
| 2026-07-02 | Platform Engineering | `HEAD` | **Truthfulness corrections** verified against `src/mcp/server.py`: payload scanner exists but is **not wired** into the `/mcp/rpc` handler (marked PLANNED); only `/mcp/rpc` + `/mcp/sse` are token-protected (`/mcp/tools`, `/mcp/health`, `/mcp/grid/status` are open); Prometheus `/metrics` is app-level (`api.py` / ecosystem router), not on the MCP router. |
