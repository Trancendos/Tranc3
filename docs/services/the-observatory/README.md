# Service Doc-Pack — The Observatory (Audit, Tracing, Health)

> Code-grounded Doc Pack per `docs/framework/DESIGN-GOVERNANCE-FRAMEWORK.md`.
> Claims cite `src/observability/`.

**Service:** The Observatory · **Slug:** `the-observatory` · **Lead AI:** Norman Hawkins (AID-OBS-01, Tier 3) · **Prime:** Cornelius MacIntyre (Tier 2)
**Canonical status:** ✅ Self-hosted → **Live** tier (status per `CLAUDE.md`; identity/PID-OBS per `PLATFORM_ENTITIES.md`)
**Code root:** `src/observability/` · **Worker:** `monitoring` (port 8007) · **Owner:** Platform Engineering
**Version:** 1.0.0 · **Last verified against `main`:** 2026-07-02 @ `70fec6b`

---

## 1. Service Governance Charter (GOV)

- **Mission:** Record every action, change, and activity on Trancendos — the platform's
  audit log, distributed tracing, metrics, and health aggregation.
- **In scope:** append + query audit events, W3C TraceContext distributed tracing,
  Prometheus metrics, health aggregation across services, proactive health monitoring,
  self-healing triggers, tamper-evident audit verification, SSE live feed.
- **Out of scope:** long-term cold archive (The Basement), auth (Infinity), alerting
  transport beyond metric exposure (notifications worker).
- **Lead AI (Tier 3):** Norman Hawkins; **Prime (Tier 2):** Cornelius MacIntyre.
- **SLOs (target):** availability 99.5%, ingest p99 < 100 ms, no audit-event loss under
  normal load (batched flush), error budget 0.5%/30d.
- **Review cadence:** Quarterly, or on any change to the audit schema or trace propagation.
- **Hard dependencies:** its own store for audit events; instruments all other services.

## 2. Detailed Design Document (DDD)

- **Component breakdown:**

  | Module | Responsibility |
  |--------|----------------|
  | `src/observability/observatory.py` | `Observatory` — core audit store; `AuditEvent`, `EventCategory`, `EventSeverity`; batched flush (`_flush`, `_send_batch`, `flush_loop`) |
  | `src/observability/audit_middleware.py` | `AuditMiddleware` — captures actions per request (`_category_for_path`, `_extract_actor`, `_sanitise`) |
  | `src/observability/tracing.py` | `Tracer`, `Span` — W3C TraceContext (`traceparent`) propagation; `async_trace_span` |
  | `src/observability/metrics.py` / `prometheus_mount.py` | Prometheus counters/histograms; `_ensure_worker_info_metric`; null-safe fallbacks (`_NullCounter`) |
  | `src/observability/health.py` | `HealthChecker`, `SystemHealth`, `HealthSample` — health roll-up |
  | `src/observability/proactive_health.py` / `self_healer.py` | `ProactiveHealthMonitor`, `ProactiveAlert`, `SelfHealer`, `CellState` |
  | `src/observability/otel.py` | OpenTelemetry integration |
  | `src/observability/routes.py` | FastAPI routes (see interface) |

- **Public interface (routes, `routes.py`):**

  | Method | Route | Purpose |
  |--------|-------|---------|
  | GET | `/` | Observatory root/status |
  | POST | `/events` | Ingest audit event(s) |
  | GET | `/recent` | Recent events |
  | GET | `/stats` | Aggregate stats |
  | GET | `/search` | Query audit log |
  | GET | `/export` | Export events |
  | GET | `/sse` | Live event stream (SSE) |
  | GET | `/verify` | Tamper-evidence verification |
  | GET | `/health` | Liveness/readiness |

- **Data model:** `AuditEvent` (actor, category, severity, path, timestamp, payload —
  sanitised); health samples; spans keyed by `traceparent`.
- **Key sequence flows:**
  ```text
  Action:  any service request → AuditMiddleware → AuditEvent (sanitised)
        → Observatory buffer → batched _flush → store
  Trace:   inbound traceparent → Tracer.async_trace_span → child spans → export
  Health:  HealthChecker polls services → SystemHealth roll-up;
           ProactiveHealthMonitor → ProactiveAlert → SelfHealer trigger
  ```
- **Error handling:** ingest failures buffered/retried on `flush_loop`; metric hooks are
  null-safe (`_NullCounter`/`_NullSpan`) so observability never breaks the host path.
- **Concurrency / state:** async; audit events batched and flushed on a background loop;
  SSE fan-out to subscribers.

## 3. Technical Architecture Solutions Design (TASD)

- **Context:** the platform's observability spine; replaces CF `infinity-monitoring-dashboard`
  / `infinity-cost-monitor` with self-hosted Python (per `CLAUDE.md`); OSS alignment: SigNoz/Jaeger.
- **Architecture decisions:**

  | ID | Decision | Options | Why | Consequence |
  |----|----------|---------|-----|-------------|
  | AD-1 | W3C TraceContext (`traceparent`) propagation | vendor tracing, none | standards-based cross-service correlation | must propagate headers everywhere |
  | AD-2 | Batched async audit flush | write-per-event | throughput; avoids per-request I/O stalls | small in-flight loss window on hard crash |
  | AD-3 | Null-safe metric/span shims | hard dependency on OTel/Prom | observability must never break the host | slightly more code; graceful degradation |
  | AD-4 | Tamper-evidence (`/verify`) | plain log | audit integrity for compliance | verification cost on read |

- **Non-functional drivers:** zero-cost, non-intrusive (never break host), auditability, correlation.
- **Rejected alternatives:** paid APM (cost), synchronous per-event writes (latency).

## 4. RACI Matrix

| Activity | Platform Owner | Norman Hawkins (Lead AI) | Platform Eng | The Town Hall | SRE/On-call |
|----------|:--:|:--:|:--:|:--:|:--:|
| Audit schema change | **A** | C | R | **C** | I |
| Trace/metric instrumentation | C | C | R | I | C |
| Deploy | A | I | R | I | C |
| Incident (observability down) | I | I | C | I | **R/A** |
| Audit-retention/compliance | **A** | C | R | **A** | I |
| Doc verification | I | I | R | **A** | I |

## 5. Solutions Integration Model (SIM)

- **Upstream (callers):** every service emits audit events (via `AuditMiddleware` or
  `POST /events`) and propagates `traceparent`; dashboards consume `/recent`, `/stats`, `/sse`.
- **Downstream:** audit store; archived events flow to The Basement (planned); metrics
  scraped by Prometheus.
- **Events:** SSE `/sse` broadcasts live audit events; `ProactiveAlert` → `SelfHealer`.
- **Auth boundary:** ingest/query behind platform auth (Infinity); actor extracted per event.
- **Data classification:** audit payloads may contain PII/action detail — **sanitised**
  (`_sanitise`) before storage; secrets never recorded.

## 6. Architecture Scalability Document (ASD)

- **Load model:** ingest scales with total platform request volume (every action → event);
  queries are lower-rate.
- **Scaling levers:** batched flush amortizes writes; SSE subscriber cap; partition/rotate
  the store; archive cold events to The Basement.
- **Bottlenecks:** audit write throughput under burst; SSE fan-out memory; unbounded history.
- **Zero-cost limits & hard stops:** no paid APM. Retention bounded; cold data archived, not
  kept hot indefinitely; metric/trace hooks degrade to no-ops rather than incur cost.
- **Degradation:** if the store is unavailable, events buffer and flush on recovery; metric
  and span shims no-op so host services are unaffected.

## 7. Technology Framework Matrix (TFM)

| Layer | Technology | Version | Licence | Zero-cost? | CVE posture |
|-------|-----------|---------|---------|:----------:|-------------|
| Runtime | Python | 3.11+ | PSF | ✅ | see `docs/SECURITY-ASSESSMENT.md` |
| Framework | FastAPI + Starlette | pinned | MIT/BSD | ✅ | clean |
| Tracing | W3C TraceContext + OpenTelemetry | pinned | Apache 2.0 | ✅ | clean |
| Metrics | Prometheus client | pinned | Apache 2.0 | ✅ | clean |
| Transport | HTTP + SSE | — | — | ✅ | — |
| LLM trace (opt) | Langfuse integration | pinned | MIT | ✅ | optional |

## 8. Policy (POL)

- **Applicable platform policies:** `POL-OPS-002`, `POL-PRI-001`; ISO 27001 audit controls — see `docs/policies/`, `docs/compliance/`.
- **Service-specific rules:** audit events are append-only and tamper-evident (`/verify`);
  payloads sanitised; retention per compliance policy.
- **Data handling:** GDPR — audit data may be personal; retention + DSR per `PROC-DSR-001`.
- **Access:** query/export authorized-only; actor recorded on every event.

## 9. Procedure (PROC)

- **Deploy:** `monitoring` worker (port 8007) + in-process instrumentation (`worker_setup.py`); CI via `.forgejo/workflows/`.
- **Instrument a service:** wire `AuditMiddleware` + trace propagation via `worker_setup.py`.
- **Investigate an incident:** `/search` + `/recent` by `trace_id`/actor; `/verify` for integrity.
- **Retention/archival change:** via change gate (`docs/procedures/PROC-CHG-001-Change-Request.md`).

## 10. Runbook (RUN)

- **Health check:** `GET /health` → 200; platform health via `HealthChecker`/`SystemHealth`.
- **Key alerts → action:**

  | Alert | Likely cause | First action | Escalation |
  |-------|-------------|--------------|------------|
  | Ingest backlog growing | store slow/unavailable | check store; confirm `flush_loop` running | SRE → Platform Eng |
  | Missing traces | `traceparent` not propagated | verify middleware wiring on offending service | Platform Eng |
  | Proactive alert firing | subsystem unhealthy | inspect `SystemHealth`; let `SelfHealer` act; verify | SRE |
  | `/verify` fails | audit tampering/corruption | freeze store; escalate | **Security → Platform Owner** |

- **Diagnostics:** `/recent`, `/stats`, `/sse`; Prometheus `/metrics`; structured logs.
- **Rollback:** redeploy previous image; audit schema is append-compatible.
- **Recovery:** buffered events flush on store recovery; historical events restored from backup.

## 11. Standards (STD)

- **Tracing standard:** W3C TraceContext (`traceparent`); OpenTelemetry semantics.
- **Metrics standard:** Prometheus exposition; worker-info metric per service.
- **Audit standard:** append-only, sanitised, tamper-evident; `EventCategory`/`EventSeverity` taxonomy.
- **Error standard:** canonical `ErrorCode` enum — `src/errors/error_catalog.py`.
- **Logging standard:** structured JSON, `trace_id`, no secrets.
- **Naming standard:** "The Observatory" (per `CLAUDE.md`).

---

## Verification Log

| Date | Verifier | Commit | Result |
|------|----------|--------|--------|
| 2026-07-02 | Platform Engineering | `70fec6b` | Routes (`/events`, `/recent`, `/stats`, `/search`, `/export`, `/sse`, `/verify`, `/health`), W3C TraceContext tracing, Prometheus metrics, `AuditMiddleware`, `HealthChecker`/`SelfHealer`, and batched flush verified against `src/observability/`. Lead AI/Prime per PLATFORM_ENTITIES.md PID-OBS. |
