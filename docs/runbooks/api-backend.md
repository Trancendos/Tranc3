# Runbook: tranc3-backend (FastAPI API)

| Field | Value |
|---|---|
| **Service** | tranc3-backend |
| **Port** | 8000 |
| **Priority** | P0 |
| **SLA** | 99.5% uptime, <500ms p95 latency |
| **Owner** | The Citadel |
| **Last reviewed** | 2026-06-06 |

## 1. Service Overview

The main FastAPI application. Provides REST API, auth endpoints, MCP server
(The Spark), workflow engine (The Digital Grid), and all platform sub-system
routes. Entry point: `api.py`. Fails fast if `SECRET_KEY` is unset.

**Dependencies:**
- PostgreSQL (port 5432) — user/session/settings data
- Redis (optional) — rate limiting, caching
- AI Gateway (port 8009) — inference routing

## 2. Health Check

```bash
curl http://localhost:8000/health
# Expected: {"status":"healthy","version":"2.0.0",...}

curl http://localhost:8000/ready
# Expected: {"ready":true}
```

## 3. Start / Stop / Restart

```bash
# Via Docker Compose (production)
docker compose -f docker-compose.production.yml up -d tranc3-backend
docker compose -f docker-compose.production.yml stop tranc3-backend
docker compose -f docker-compose.production.yml restart tranc3-backend

# Via Make (development)
make dev-api          # hot-reload on :8000

# Direct (manual)
SECRET_KEY=xxx uvicorn api:app --host 0.0.0.0 --port 8000 --workers 2
```

## 4. Common Incidents

### 4.1 Service fails to start — "SECRET_KEY not set"
**Symptom:** Container exits immediately with `FATAL: SECRET_KEY environment variable is not set`.  
**Cause:** Missing environment variable.  
**Fix:** Set `SECRET_KEY` in `.env` or Docker secrets, then restart.

### 4.2 Database connection refused
**Symptom:** `sqlalchemy.exc.OperationalError: could not connect to server`.  
**Cause:** PostgreSQL not running or `DATABASE_URL` incorrect.  
**Fix:**
```bash
docker compose up -d postgres
# verify
docker exec tranc3-dev-postgres pg_isready -U tranc3 -d tranc3
```

### 4.3 High latency (>1s p95)
**Symptom:** Prometheus alert `tranc3_request_latency_p95 > 1`.  
**Cause:** Usually AI inference timeout or database slow query.  
**Diagnosis:**
```bash
curl http://localhost:8000/metrics | grep tranc3_request_duration
curl http://localhost:8000/health  # check ai_gateway status
```
**Fix:** Check AI Gateway tier fallback, check DB slow query log.

### 4.4 Memory leak / OOM
**Symptom:** Container OOM-killed.  
**Cause:** Large inference results accumulating in LRU cache.  
**Fix:** Restart service; consider reducing `LIMIT_HTTP_MAX_CONNECTIONS`.

## 5. Escalation Path

| Severity | Contact | Response Time |
|---|---|---|
| P0 (complete outage) | On-call DevOps | 15 min |
| P1 (degraded) | Platform team | 1 hour |
| P2 (minor) | Engineering | Next business day |

## 6. Recovery Procedures

### Database restore
```bash
# Stop API
docker compose stop tranc3-backend

# Restore from backup
pg_restore -U tranc3 -d tranc3 /backups/tranc3_latest.dump

# Run migrations
docker compose run --rm db-migrate

# Restart
docker compose up -d tranc3-backend
```

### Rollback deployment
```bash
# Via Forgejo (The Workshop) — trigger rollback workflow
# Or manually via Fly.io
fly releases list --app tranc3-backend
fly deploy --image <previous-image> --app tranc3-backend
```

## 7. Monitoring

Key Prometheus metrics:
- `tranc3_requests_total` — request throughput
- `tranc3_request_duration_seconds` — latency histogram
- `tranc3_ai_gateway_fallback_total` — AI fallback frequency
- `tranc3_circuit_breaker_state` — circuit breaker state (0=closed, 1=open)

Alert thresholds (Prometheus rules in `monitoring/`):
- Error rate > 5% over 5 min → P1 alert
- p95 latency > 2s → P1 alert  
- Circuit breaker open > 60s → P0 alert
