# Service Doc-Pack — The Spark (MCP Server)

> **Reference implementation** of the Trancendos per-service Doc Pack. Every claim below
> is grounded in code under `src/mcp/`. Governed by
> `docs/framework/DESIGN-GOVERNANCE-FRAMEWORK.md`.

**Service:** The Spark · **Slug:** `the-spark` · **Lead AI:** Imfy (AID-SPK-01, Tier 3) · **Prime:** Norman Hawkins (Tier 2)
**Canonical status:** ✅ In repo (matches `PLATFORM_ENTITIES.md`)
**Code root:** `src/mcp/` · **Routes prefix:** `/mcp` · **Owner:** Platform Engineering
**Version:** 1.0.0 · **Last verified against `main`:** 2026-07-02 @ `60b3b18`

---

## 1. Service Governance Charter (GOV)

- **Mission:** Expose the platform's AI tool registry to agents and services via a
  standards-compliant **Model Context Protocol** server (JSON-RPC 2.0 over HTTP + SSE).
- **In scope:** tool registration/discovery, JSON-RPC request handling, SSE event bus,
  semantic tool selection (RAG-MCP), prompt-injection scanning of inbound payloads,
  Digital Grid status surfacing.
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
  | `src/mcp/payload_scanner.py` | Prompt-injection scan of `/mcp/rpc` payloads (`ScanFinding`/`ScanResult`) |
  | `src/mcp/client.py` | Outbound `MCPClient` / `MCPClientPool` for remote MCP servers |
  | `src/mcp/spark_*_tools.py` | Tool packs: gbrain, knowledge, phase4, phase5 |
- **Public interface (routes, `src/mcp/server.py`):**
  | Method | Route | Purpose |
  |--------|-------|---------|
  | POST | `/mcp/rpc` | JSON-RPC 2.0 request/response |
  | GET | `/mcp/sse` | Server-Sent Events stream (`StreamingResponse`) |
  | GET | `/mcp/tools` | List registered tools |
  | GET | `/mcp/health` | Liveness/readiness |
  | GET | `/mcp/grid/status` | The Digital Grid status passthrough |
- **Data model:** `MCPRequest` / `MCPResponse` / `MCPError` Pydantic models;
  `jsonrpc="2.0"` constant; standard JSON-RPC error codes defined in `server.py`.
- **Key sequence flow:**
  ```
  client → POST /mcp/rpc → payload_scanner.scan_rpc_payload()
        → [clean] dispatch to tool registry (tools.py, optionally tool_rag selection)
        → MCPResponse | MCPError → client
        (SSE subscribers notified via _SSEBus)
  ```
- **Error handling:** JSON-RPC standard codes in `server.py`; platform canonical codes via
  `src/errors/error_catalog.py` (42 `ErrorCode` members defined). Scanner failures **fail open with logging**
  by design (documented in `payload_scanner.py`) so a scanner bug cannot deny all callers.
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
- **Auth boundary:** MCP routes sit behind platform auth middleware (Infinity/JWT);
  inbound payloads additionally pass `payload_scanner`.
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

## 7. Technology Framework Matrix (TFM)

| Layer | Technology | Version | Licence | Zero-cost? | CVE posture |
|-------|-----------|---------|---------|:----------:|-------------|
| Runtime | Python | 3.11+ | PSF | ✅ | see `docs/SECURITY-ASSESSMENT.md` |
| Framework | FastAPI + Starlette | pinned | MIT/BSD | ✅ | clean |
| Transport | JSON-RPC 2.0 over HTTP + SSE | — | — | ✅ | — |
| Tool RAG | FAISS (`faiss-cpu`) + sentence-transformers | pinned | MIT/Apache | ✅ | clean |
| Validation | Pydantic v2 | pinned | MIT | ✅ | clean |

## 8. Policy (POL)

- **Applicable platform policies:** `POL-AI-001` (AI Ethics & Governance),
  `POL-OPS-002`, `POL-PRI-001` — see `docs/policies/`.
- **Service-specific rules:** all inbound `/mcp/rpc` payloads are scanned for prompt
  injection; scanner bypass events MUST be logged (audit to The Observatory).
- **Data handling:** The Spark persists no user content; tool-level data handling is
  governed by the downstream service's policy.
- **Access:** MCP routes require a valid platform token (Infinity); tier limits per
  `src/monetisation/`.

## 9. Procedure (PROC)

- **Deploy:** included in the FastAPI app (`api.py`) / worker image; CI via
  `.forgejo/workflows/` (no GitHub Actions).
- **Register a tool:** add to the relevant `spark_*_tools.py` pack via its `register_*`
  entrypoint; covered by `tests/test_spark_grid_integration.py`.
- **Config change:** through change gate (`docs/procedures/PROC-CHG-001-Change-Request.md`).
- **Secret rotation:** N/A for The Spark core (holds no secrets); downstream tools use The Void.

## 10. Runbook (RUN)

- **Health check:** `GET /mcp/health` → 200 with status body.
- **Key alerts → action:**
  | Alert | Likely cause | First action | Escalation |
  |-------|-------------|--------------|------------|
  | `/mcp/rpc` 5xx spike | tool exception / dependency down | check logs for tool id; isolate failing tool | SRE → Platform Eng |
  | SSE connection saturation | too many subscribers | scale replicas / cap subscribers | SRE |
  | Scanner error rate up | `payload_scanner` bug | confirm fail-open (calls still served); patch scanner | Platform Eng |
  | Cold-start latency | model load | pre-warm / pin replica | SRE |
- **Diagnostics:** structured JSON logs with `trace_id`; metrics at `/metrics`; traces via
  The Observatory (`src/observability/`).
- **Rollback:** redeploy previous image tag; MCP surface is backward-compatible by policy.
- **Recovery:** stateless — restart restores service; RAG index rebuilds automatically.

## 11. Standards (STD)

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
| 2026-07-02 | Platform Engineering | `60b3b18` | All routes, models, RAG stack, scanner behaviour, and error catalog claims verified against `src/mcp/`. No overstated behaviour. |
