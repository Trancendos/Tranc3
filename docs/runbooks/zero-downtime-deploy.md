# Runbook: Zero-Downtime Deployment Procedure

| Field | Value |
|---|---|
| **Applies to** | All P0/P1 self-hosted workers, Fly.io services |
| **DEF STAN ref** | REQ-SU-007 (DEF STAN 00-600) |
| **Owner** | The Citadel / DevOps |
| **Last reviewed** | 2026-06-06 |

## Overview

All Tranc3 platform deployments follow a rolling update strategy that ensures
zero service interruption. The strategy varies by deployment target.

## Fly.io Services (tranc3-backend, tranc3-bots)

Fly.io performs rolling deploys by default. The Forgejo deploy workflow
(`deploy-fly.yml`) adds an explicit health-check gate:

```yaml
deploy:
  strategy: rolling
  max_unavailable: 0    # never take all instances down simultaneously
  healthcheck:
    grace_period: 30s
    interval: 10s
    timeout: 5s
    threshold: 2         # require 2 consecutive successes before cutting traffic
```

**Manual rollback:**
```bash
fly releases list --app tranc3-backend
fly deploy --image registry.fly.io/tranc3-backend:<previous-version>
```

## Self-Hosted Docker Compose Workers

For the 38+ self-hosted workers, use the rolling update script:

```bash
# Update a single worker without downtime
./scripts/rolling-update.sh <service-name>

# Example: update the AI gateway
./scripts/rolling-update.sh infinity-ai

# Update all P0 workers in order
./scripts/rolling-update.sh --tier p0

# Update all workers (careful — takes ~10 min)
./scripts/rolling-update.sh --all
```

### How it works

1. Pull new image / rebuild container
2. Start new instance on a temporary port
3. Health-check new instance (3 consecutive passes required)
4. Switch Traefik upstream to new instance
5. Wait 10s for in-flight requests to drain
6. Stop old instance
7. Log deployment event to The Observatory

### Manual procedure (if script unavailable)

```bash
# 1. Build new image
docker compose -f docker-compose.production.yml build <service>

# 2. Start new instance with --no-deps
docker compose -f docker-compose.production.yml up -d --no-deps --scale <service>=2 <service>

# 3. Wait for health check
until docker inspect --format='{{.State.Health.Status}}' <new-container> | grep -q healthy; do
  sleep 2
done

# 4. Scale down old instance
docker compose -f docker-compose.production.yml up -d --no-deps --scale <service>=1 <service>
```

## Database Migrations (Zero-Downtime)

All Alembic migrations must be **backward-compatible** with the running
version. Follow the expand/contract pattern:

1. **Expand** — add new column as nullable (old code ignores it, new code uses it)
2. **Deploy** — deploy new code that writes to both old and new columns
3. **Contract** — make column NOT NULL / drop old column in next release

```bash
# Run migration during maintenance window or via rolling update
docker compose run --rm db-migrate alembic upgrade head
```

## Verification After Deploy

```bash
# Check all P0 services are healthy
./scripts/db-provision.sh --status

# Check compliance gate still passes
make compliance-ci

# Check Lighthouse score (if web changes deployed)
cd web && node ../scripts/lighthouse-audit.mjs --ci
```

## Rollback Decision Criteria

Trigger immediate rollback if within 15 minutes of deploy:
- Error rate > 10% (normal: < 1%)
- P95 latency > 5s (normal: < 500ms)
- Any P0 circuit breaker opens
- Compliance gate score drops below 70%
