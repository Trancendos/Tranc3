# DEF STAN 00-600 — Supportability (ILS)

**Standard:** DEF STAN 00-600 (adapted for software platform)  
**Area Code:** SU  
**Status Summary:** 4 COMPLIANT, 2 PARTIAL, 1 PLANNED  
**Score:** ~71.4%

## Purpose

Establishes supportability requirements: health monitoring, metrics/observability, distributed tracing, log aggregation, runbook documentation, disaster recovery, and zero-downtime deployment.

## Requirements

### REQ-SU-001 — Health Monitoring Endpoints

Every service exposes /health. Platform-wide health aggregator rolls up all statuses.

**Evidence:** `src/observability/health.py`, `workers/health-aggregator/` (port 8029)  
**Status:** COMPLIANT

---

### REQ-SU-002 — Metrics and Observability

Prometheus-compatible metrics. Dashboards for latency, error rates, saturation. Alerting on SLO breaches.

**Evidence:** `monitoring/prometheus.yml`, `monitoring/grafana/`, `workers/monitoring/` (port 8007)  
**Status:** COMPLIANT

---

### REQ-SU-003 — Distributed Tracing

W3C TraceContext propagated across all inter-service calls. Traces queryable for post-incident analysis.

**Evidence:** `src/observability/tracing.py`, `tests/test_tracing.py`  
**Status:** COMPLIANT

---

### REQ-SU-004 — Structured Log Aggregation

Structured JSON logs aggregated centrally via Loki + Promtail. Searchable. JSON with trace_id, user_id, service_name.

**Evidence:** `monitoring/loki.yml`, `monitoring/promtail.yml`  
**Status:** COMPLIANT

---

### REQ-SU-005 — Service Runbook Documentation

P0 and P1 services have operational runbooks covering startup, shutdown, failure modes, recovery.

**Evidence:** `docs/`, `CLAUDE.md` (engineering reference)  
**Status:** PARTIAL — CLAUDE.md covers engineering reference; dedicated runbooks planned

---

### REQ-SU-006 — Disaster Recovery and Backup

Critical data stores backed up on schedule. DR procedures documented and tested. RTO/RPO defined.

**Evidence:** None (planned)  
**Status:** PLANNED — See Waiver WAV-002  
**Compensating Control:** Fly.io region redundancy; SQLite databases easily snapshotted

---

### REQ-SU-007 — Zero-Downtime Deployment

Production deployments support rolling updates. Health checks gate traffic shifting.

**Evidence:** `.forgejo/workflows/deploy-fly.yml`, `docker-compose.production.yml`  
**Status:** PARTIAL — Fly.io supports rolling deploys; self-hosted worker rolling strategy partial
