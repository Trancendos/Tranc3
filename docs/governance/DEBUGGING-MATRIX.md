# Debugging Matrix

> **What this is.** `docs/runbooks/` covers three operational scenarios (API backend deploy,
> disaster recovery, zero-downtime deploy) — nothing walks through how to actually debug a problem
> across a ~90-worker distributed platform. This document is that missing guide, built entirely
> from real, already-working observability infrastructure — nothing here requires new code.

**Owner:** The Observatory (Norman Hawkins) · **Version:** 1.0.0 · **Last verified:** 2026-07-30

---

## 1. Where to look first, by symptom

| Symptom | Start here |
|---|---|
| "Is anything actually broken right now?" | `GET /health` on `health-aggregator` (port 8029) — aggregates every worker in `SERVICE_REGISTRY` (`workers/health-aggregator/worker.py`) into one `healthy`/`degraded`/`unhealthy`/`unknown` verdict |
| "What happened, in order?" | The Observatory's audit log — `GET /observability/recent` (last N events), `/search` (full-text), `/export` (JSON/CSV), `/sse` (live stream) — `src/observability/routes.py` |
| "Which service, and why did it fail?" | `/observability/stats` — event counts by category/severity/service, before diving into individual events |
| "Where in the request path did this fail?" | Distributed tracing (§2) — every request carries a trace ID across worker boundaries |
| "Is this a known error, and what's the fix?" | `src/errors/error_catalog.py`'s `ErrorCode` enum — structured `TRANC3-{DOMAIN}-{CODE}` errors, each with guidance and (where applicable) a self-healing action |
| "Did the platform already try to fix this itself?" | `src/observability/self_healer.py` — polls services, detects degradation, and takes corrective action (log escalation, cooldown reset, alert) without a human; check its log before assuming nothing happened |

## 2. Distributed tracing — `src/observability/tracing.py`

Zero-cost, no external APM required: thread-local trace context + SQLite span storage + W3C
TraceContext propagation, with an optional OTEL bridge export to Grafana Tempo when available.
`current_trace_id()`/`current_span_id()` read the active context; `set_trace()`/`clear_trace()`
manage it per-thread. Because propagation follows the W3C standard, a trace ID picked up from one
worker's logs can be grepped across every other worker's logs to reconstruct the full request path
— this is the single most useful technique for a cross-worker bug that isn't reproducible from one
service's logs alone.

## 3. Log aggregation — Loki + Promtail (`monitoring/loki.yml`, `monitoring/promtail.yml`)

Real, running services in `docker-compose.production.yml` (not aspirational — see this session's
earlier correction in this platform's own history: these were initially mis-dismissed as
proposed-only, then verified as genuinely deployed). Structured JSON logs carry `trace_id`,
`user_id`, and `service_name` bindings (per `CLAUDE.md`'s Observability Stack section), so a Loki
query filtered on a trace ID from §2 pulls every log line across every worker for that one request.

## 4. Self-healing — what already happens without you

`self_healer.py`'s "cell regeneration" pattern (each service is a cell; an unhealthy cell signals
for regeneration) means some class of failures never reach a human. Before spending time debugging
something that looks intermittent, check whether it's a self-healer cooldown-reset cycle rather
than a real recurring fault — `RealtimeStatusBar`/`PlatformPulse` (see
`docs/governance/UX-UI-DESIGN-MATRIX.md` §3) surface this platform-wide state in the frontend.

## 5. Error catalog — `src/errors/error_catalog.py`

Every structured error follows `TRANC3-{DOMAIN}-{CODE}` (domains: `AUTH`, `RATE`, `MODEL`, `DB`,
`QUANT`, `CONS`, `EVOL`, `SWARM`, `HOLO`, `SEC`, `COMP`, `SYS`). When a bug report includes one of
these codes, start at its `ErrorCode` enum entry rather than the raw exception — the catalog
carries guidance and, for some codes, a documented self-healing action (§4) that may already be
firing.

## 6. What this document doesn't cover

- **Frontend debugging** — React DevTools / browser devtools are the right tool; nothing platform-
  specific exists here beyond `ErrorBoundary.tsx` (catches render errors) and the trace ID from §2
  being visible in network request headers for cross-referencing into Loki.
- **A step-by-step "how to reproduce X" playbook** — this document is a map of *where to look*, not
  a symptom-to-root-cause index; that would need real incident history to build honestly, which
  doesn't exist yet (see `docs/governance/ACCESSIBILITY-STANDARDS.md`'s similar honesty about not
  yet having a real audit trail to draw from).

## 7. Cross-references

- `docs/runbooks/` — the three existing ops runbooks this document sits alongside, not replaces
- `docs/governance/HARD-STOP-MATRIX.md` — what actually halts something, if debugging reveals a
  circuit breaker or hard-stop tripped
- `docs/governance/THRESHOLD-MATRIX.md` — numeric thresholds, if debugging reveals a rate limit or
  capacity band was crossed
