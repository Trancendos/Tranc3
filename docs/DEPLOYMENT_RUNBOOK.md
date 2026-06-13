# Tranc3 Production Deployment Runbook

## Architecture Overview

The Tranc3 production stack is a fully self-hosted, zero-cost architecture that replaces all Cloudflare Worker dependencies with Python/FastAPI workers. The stack runs entirely on your own infrastructure with no paid external API dependencies.

**Core Principle:** Zero cost. No paid APIs. No third-party dependencies that incur costs. All services are self-hosted Python workers or open-source infrastructure components.

**What This Stack Replaces:**

| Cloudflare Service | Self-Hosted Replacement |
|---|---|
| Cloudflare Workers | 29 Python/FastAPI workers |
| Cloudflare D1 | SQLite (per-worker) |
| Cloudflare KV | In-memory rate limiting + SQLite |
| Cloudflare R2 | IPFS + local filesystem |
| Cloudflare Routing | Traefik reverse proxy |
| Cloudflare Analytics | Prometheus + Grafana + Loki |
| Cloudflare Secrets | HashiCorp Vault |

---

## Service Inventory

### Infrastructure Layer (7 services)

| Service | Image | Port | Purpose |
|---|---|---|---|
| Traefik | `traefik:v3.0` | 80, 443, 8080, 9090 | Reverse proxy, load balancer, auto-discovery |
| Vault | `hashicorp/vault:1.15` | 8200 | Secrets management (dev mode for initial setup) |
| Prometheus | `prom/prometheus:v2.48.1` | 9091 (host) → 9090 (container) | Metrics collection and alerting |
| Grafana | `grafana/grafana:10.2.2` | 3001 (host) → 3000 (container) | Dashboards and visualization |
| Loki | `grafana/loki:2.9.3` | 3100 | Log aggregation |
| Promtail | `grafana/promtail:2.9.3` | — | Log shipping to Loki |
| IPFS | `ipfs/kubo:v0.24.0` | 4001, 5001 | Distributed storage (replaces R2) |

### Worker Layer — P0 Critical (3 workers)

| Worker | Port | Purpose |
|---|---|---|
| `tranc3-ai` | 8001 | Core AI orchestration service |
| `infinity-void` | 8002 | Encrypted secrets vault (AES-256-GCM, PBKDF2) |
| `api-gateway` | 8003 | Central API gateway and request routing |

### Worker Layer — P1 Essential (5 workers)

| Worker | Port | Purpose |
|---|---|---|
| `infinity-ws` | 8004 | WebSocket real-time communication |
| `infinity-auth` | 8005 | Authentication and JWT management |
| `users-service` | 8006 | User profile and account management |
| `monitoring` | 8007 | System monitoring and alerting |
| `notifications` | 8008 | Push notification delivery |

### Worker Layer — P2 Important (7 workers)

| Worker | Port | Purpose |
|---|---|---|
| `infinity-ai` | 8009 | AI gateway with priority failover (Ollama → OpenRouter → Offline) |
| `the-grid` | 8010 | Mesh topology and grid computation |
| `products-service` | 8011 | Product catalog management |
| `orders-service` | 8012 | Order processing and tracking |
| `payments-service` | 8013 | Payment handling |
| `files-service` | 8014 | File upload and storage |
| `identity-service` | 8015 | Identity and access management |

### Worker Layer — P3 Stub (14 workers)

These are stub implementations ready for future development. They expose `/health` endpoints and basic structure.

| Worker | Port | Purpose |
|---|---|---|
| `analytics-service` | 8016 | Usage analytics and reporting |
| `search-service` | 8017 | Full-text search |
| `email-service` | 8018 | Email delivery |
| `sms-service` | 8019 | SMS delivery |
| `storage-service` | 8020 | Distributed storage management |
| `cron-service` | 8021 | Scheduled task execution |
| `queue-service` | 8022 | Message queue processing |
| `cache-service` | 8023 | Distributed caching |
| `config-service` | 8024 | Dynamic configuration |
| `audit-service` | 8025 | Audit log aggregation |
| `rate-limit-service` | 8026 | Rate limiting service |
| `geo-service` | 8027 | Geolocation services |
| `cdn-service` | 8028 | CDN edge caching |
| `health-aggregator` | 8029 | Health check aggregation |

---

## Prerequisites

### System Requirements

| Requirement | Minimum | Recommended |
|---|---|---|
| CPU | 4 cores | 8+ cores |
| RAM | 8 GB | 16+ GB |
| Disk | 40 GB | 100+ GB SSD |
| OS | Linux (Docker-supported) | Ubuntu 22.04+ / Debian 12+ |
| Docker | 24.0+ | Latest stable |
| Docker Compose | v2.20+ | Latest stable |

### Software Dependencies

```bash
# Verify Docker and Compose versions
docker --version          # >= 24.0
docker compose version    # >= v2.20

# Verify available disk space (need 20+ GB for images)
df -h /var/lib/docker

# Verify available ports (80, 443, 3001, 8080, 8200, 8001-8029, 9090)
ss -tlnp | grep -E ':(80|443|3001|8080|8200|800[1-9]|801[0-9]|802[0-9]|9090)\b'
```

### Network Requirements

All services communicate over the `tranc3-net` Docker bridge network. No external network access is required for core functionality. The only outbound connections are:

- **Ollama** (optional): If using local AI inference at `http://ollama:11434`
- **OpenRouter** (optional): If using OpenRouter as AI fallback — requires `OPENROUTER_API_KEY`
- **Hugging Face** (optional): For model downloads — requires `HUGGINGFACE_API_KEY`

---

## Pre-Deployment

### Step 1: Clone the Repository

```bash
git clone https://github.com/Trancendos/Tranc3.git
cd Tranc3
git checkout main
```

### Step 2: Create Environment File

Create `.env.production` in the project root:

```bash
cp .env.example .env.production 2>/dev/null || cat > .env.production << 'EOF'
# ─── Core ───
ENVIRONMENT=production
JWT_SECRET=<generate-a-64-char-hex-secret>
INTERNAL_SECRET=<generate-a-64-char-hex-secret>
MASTER_KEY_SEED=<generate-a-64-char-hex-secret>

# ─── AI (Optional — leave blank for offline mode) ───
OLLAMA_BASE_URL=http://ollama:11434
OPENROUTER_API_KEY=
HUGGINGFACE_API_KEY=

# ─── Vault ───
VAULT_DEV_ROOT_TOKEN_ID=tranc3-root-token

# ─── Grafana ───
GF_SECURITY_ADMIN_USER=admin
GF_SECURITY_ADMIN_PASSWORD=<set-a-strong-password>
GF_SERVER_ROOT_URL=http://localhost:3001
EOF
```

Generate secure secrets:

```bash
# Generate random secrets for production
python3 -c "import secrets; print('JWT_SECRET=' + secrets.token_hex(32))"
python3 -c "import secrets; print('INTERNAL_SECRET=' + secrets.token_hex(32))"
python3 -c "import secrets; print('MASTER_KEY_SEED=' + secrets.token_hex(32))"
```

### Step 3: Validate Configuration

```bash
# Run the integration test to validate docker-compose.production.yml
python scripts/test_docker_integration.py

# Expected: All validation checks passed!
# - 36 services (15 P0-P2 workers + 14 P3 stubs + 7 infrastructure)
# - All health checks configured
# - All dependencies correct
# - Networks and volumes defined
```

### Step 4: Pull Docker Images

```bash
docker compose -f docker-compose.production.yml pull
```

This pulls the following images:

- `traefik:v3.0`
- `hashicorp/vault:1.15`
- `prom/prometheus:v2.48.1`
- `grafana/grafana:10.2.2`
- `grafana/loki:2.9.3`
- `grafana/promtail:2.9.3`
- `ipfs/kubo:v0.24.0`
- Worker images (built locally from `workers/*/Dockerfile`)

### Step 5: Build Worker Images

If worker Dockerfiles exist:

```bash
docker compose -f docker-compose.production.yml build
```

If workers are run directly (development/initial setup):

```bash
# Workers can be started individually for testing:
cd workers/infinity-void
pip install -r requirements.txt
uvicorn worker:app --host 0.0.0.0 --port 8002
```

---

## Deployment

### Step 1: Start Infrastructure Layer First

```bash
# Start infrastructure services and wait for health
docker compose -f docker-compose.production.yml up -d \
  traefik vault prometheus grafana loki promtail ipfs

# Wait for infrastructure to become healthy (30-60 seconds)
docker compose -f docker-compose.production.yml ps --format json | \
  python3 -c "
import sys, json
for line in sys.stdin:
    svc = json.loads(line)
    print(f\"{svc['Name']}: {svc['Health']}\")
"
```

Verify each infrastructure service:

```bash
# Traefik dashboard
curl -s http://localhost:8080/api/overview | python3 -m json.tool

# Vault health
curl -s http://localhost:8200/v1/sys/health | python3 -m json.tool

# Prometheus targets
curl -s http://localhost:9091/api/v1/targets | python3 -m json.tool

# Grafana (login with admin / password from .env)
curl -s http://localhost:3001/api/health | python3 -m json.tool

# Loki readiness
curl -s http://localhost:3100/ready | python3 -m json.tool

# IPFS node ID
curl -s http://localhost:5001/api/v0/id | python3 -m json.tool
```

### Step 2: Start P0 Critical Workers

```bash
docker compose -f docker-compose.production.yml up -d \
  tranc3-ai infinity-void api-gateway

# Wait for health checks to pass
sleep 15

# Verify
curl -s http://localhost:8001/health | python3 -m json.tool
curl -s http://localhost:8002/health | python3 -m json.tool
curl -s http://localhost:8003/health | python3 -m json.tool
```

### Step 3: Start P1 Essential Workers

```bash
docker compose -f docker-compose.production.yml up -d \
  infinity-ws infinity-auth users-service monitoring notifications

# Wait for health checks
sleep 15

# Verify
for port in 8004 8005 8006 8007 8008; do
  echo -n "Port $port: "
  curl -s http://localhost:$port/health | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','UNKNOWN'))" 2>/dev/null || echo "UNREACHABLE"
done
```

### Step 4: Start P2 Important Workers

```bash
docker compose -f docker-compose.production.yml up -d \
  infinity-ai the-grid products-service orders-service \
  payments-service files-service identity-service

# Wait for health checks
sleep 15

# Verify
for port in 8009 8010 8011 8012 8013 8014 8015; do
  echo -n "Port $port: "
  curl -s http://localhost:$port/health | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','UNKNOWN'))" 2>/dev/null || echo "UNREACHABLE"
done
```

### Step 5: Start P3 Stub Workers

```bash
docker compose -f docker-compose.production.yml up -d \
  analytics-service search-service email-service sms-service \
  storage-service cron-service queue-service cache-service \
  config-service audit-service rate-limit-service geo-service \
  cdn-service health-aggregator

# Wait for health checks
sleep 15

# Verify all 14 P3 stubs
for port in 8016 8017 8018 8019 8020 8021 8022 8023 8024 8025 8026 8027 8028 8029; do
  echo -n "Port $port: "
  curl -s http://localhost:$port/health | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','UNKNOWN'))" 2>/dev/null || echo "UNREACHABLE"
done
```

### Step 6: Start All Services at Once (Alternative)

If you prefer to start everything in one command (useful for development):

```bash
docker compose -f docker-compose.production.yml up -d

# Monitor startup
docker compose -f docker-compose.production.yml ps
```

---

## Post-Deployment Verification

### Full Health Check

```bash
# Check all 36 services at once
echo "=== Infrastructure ==="
for port in 8080 8200 9091 3001 3100 5001; do
  echo -n "  Port $port: "
  curl -s -o /dev/null -w "%{http_code}" http://localhost:$port/ 2>/dev/null || echo "UNREACHABLE"
  echo
done

echo "=== P0-P2 Workers ==="
for port in 8001 8002 8003 8004 8005 8006 8007 8008 8009 8010 8011 8012 8013 8014 8015; do
  echo -n "  Port $port: "
  curl -s http://localhost:$port/health 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','UNKNOWN'))" 2>/dev/null || echo "UNREACHABLE"
done

echo "=== P3 Stubs ==="
for port in 8016 8017 8018 8019 8020 8021 8022 8023 8024 8025 8026 8027 8028 8029; do
  echo -n "  Port $port: "
  curl -s http://localhost:$port/health 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','UNKNOWN'))" 2>/dev/null || echo "UNREACHABLE"
done
```

### Service Mesh Verification

The ServiceMesh provides inter-worker communication with circuit breaker protection. Verify mesh connectivity:

```bash
# Check the AI gateway's priority failover chain
curl -s http://localhost:8009/health | python3 -m json.tool

# The AI gateway follows: Ollama → OpenRouter → Offline
# Without Ollama or OpenRouter configured, it should report "offline" mode
```

### Run Test Suite

```bash
# Run all worker and mesh integration tests (344 tests)
cd /workspace/Tranc3
python -m pytest tests/ -v --tb=short

# Run only worker health tests
python -m pytest tests/test_all_workers_health.py -v

# Run only ServiceMesh integration tests
python -m pytest tests/test_worker_mesh_integration.py -v

# Run docker-compose validation
python scripts/test_docker_integration.py
```

---

## Monitoring & Observability

### Prometheus Metrics

```bash
# Check Prometheus targets
curl -s http://localhost:9091/api/v1/targets | python3 -m json.tool

# Query worker health metrics
curl -s 'http://localhost:9091/api/v1/query?query=up' | python3 -m json.tool
```

### Grafana Dashboards

Access Grafana at `http://localhost:3001` with credentials from `.env.production`:

1. Navigate to **Dashboards → Import**
2. Import the Tranc3 dashboard JSON (if available in `grafana/dashboards/`)
3. Key metrics to monitor:
   - Worker health status (up/down)
   - Request latency per worker
   - Circuit breaker state (closed/open/half-open)
   - ServiceMesh call success rate
   - AI gateway token budget utilization

### Log Aggregation (Loki)

```bash
# Query logs via Loki API
curl -s 'http://localhost:3100/loki/api/v1/query_range' \
  --data-urlencode 'query={job="tranc3"}' \
  --data-urlencode 'start=now-1h' \
  --data-urlencode 'end=now' \
  --data-urlencode 'limit=100' | python3 -m json.tool

# View worker logs directly
docker compose -f docker-compose.production.yml logs -f infinity-void
docker compose -f docker-compose.production.yml logs -f api-gateway
```

### Traefik Dashboard

Access the Traefik dashboard at `http://localhost:8080`. This shows:

- Active routers and services
- Request rates and latencies
- Backend health status
- TLS certificate status

---

## Common Operations

### Scaling a Worker

```bash
# Scale a worker to 3 instances
docker compose -f docker-compose.production.yml up -d \
  --scale infinity-void=3

# Note: Scaling requires Traefik load balancing configuration
# and may require port remapping
```

### Restarting a Single Service

```bash
# Restart a specific worker
docker compose -f docker-compose.production.yml restart infinity-void

# Restart with fresh container
docker compose -f docker-compose.production.yml up -d --force-recreate infinity-void
```

### Viewing Logs

```bash
# Follow logs for a specific service
docker compose -f docker-compose.production.yml logs -f infinity-void

# Follow logs for all workers
docker compose -f docker-compose.production.yml logs -f --no-log-prefix | \
  grep -E "infinity-void|api-gateway"

# Export last 1000 lines of logs
docker compose -f docker-compose.production.yml logs --tail 1000 > logs-$(date +%Y%m%d).txt
```

### Updating a Worker

```bash
# Pull latest code
git pull origin main

# Rebuild and restart a specific worker
docker compose -f docker-compose.production.yml build infinity-void
docker compose -f docker-compose.production.yml up -d infinity-void

# Or rebuild and restart all workers
docker compose -f docker-compose.production.yml build
docker compose -f docker-compose.production.yml up -d
```

### Vault Operations

```bash
# Check vault status
docker compose -f docker-compose.production.yml exec vault vault status

# List secrets
docker compose -f docker-compose.production.yml exec vault \
  vault kv list secret/

# Read a specific secret
docker compose -f docker-compose.production.yml exec vault \
  vault kv get secret/tranc3/jwt

# Write a secret
docker compose -f docker-compose.production.yml exec vault \
  vault kv put secret/tranc3/new-key value="secret-value"
```

---

## Backup & Recovery

### Volume Backup

All persistent data is stored in Docker named volumes. Back them up:

```bash
#!/bin/bash
# backup-volumes.sh
BACKUP_DIR="./backups/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

# List all Tranc3 volumes
VOLUMES=$(docker volume ls --filter name=tranc3 --format '{{.Name}}')

for vol in $VOLUMES; do
  echo "Backing up $vol..."
  docker run --rm \
    -v "$vol:/source:ro" \
    -v "$BACKUP_DIR:/backup" \
    alpine tar czf "/backup/${vol}.tar.gz" -C /source .
done

echo "Backups saved to $BACKUP_DIR"
```

### Volume Restore

```bash
#!/bin/bash
# restore-volumes.sh
BACKUP_DIR="$1"

if [ -z "$BACKUP_DIR" ]; then
  echo "Usage: ./restore-volumes.sh <backup-directory>"
  exit 1
fi

for archive in "$BACKUP_DIR"/*.tar.gz; do
  vol=$(basename "$archive" .tar.gz)
  echo "Restoring $vol..."
  docker run --rm \
    -v "$vol:/target" \
    -v "$BACKUP_DIR:/backup:ro" \
    alpine sh -c "cd /target && tar xzf /backup/${vol}.tar.gz"
done
```

### SQLite Database Backup

Worker databases (SQLite) are stored in their respective volumes. For direct backup:

```bash
# Backup the void vault database
docker compose -f docker-compose.production.yml exec infinity-void \
  sqlite3 /data/void.db ".backup /data/void.db.bak"

# Copy backup out
docker compose -f docker-compose.production.yml cp \
  infinity-void:/data/void.db.bak ./backups/void-$(date +%Y%m%d).db
```

---

## Troubleshooting

### Service Won't Start

```bash
# Check logs for the failing service
docker compose -f docker-compose.production.yml logs infinity-void

# Common issues:
# 1. Port already in use
ss -tlnp | grep 8002

# 2. Volume permission issues
docker compose -f docker-compose.production.yml exec infinity-void ls -la /data

# 3. Missing environment variables
docker compose -f docker-compose.production.yml config | grep -A5 infinity-void
```

### Health Check Failing

```bash
# Check health status
docker compose -f docker-compose.production.yml ps

# Manually run the health check command
docker compose -f docker-compose.production.yml exec infinity-void \
  python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8002/health').read())"

# Check if worker process is running
docker compose -f docker-compose.production.yml exec infinity-void ps aux
```

### Circuit Breaker Open

The ServiceMesh circuit breaker trips after 5 consecutive failures. Check worker health:

```bash
# The circuit breaker opens when a worker is consistently unhealthy
# Check the target worker's health endpoint
curl -s http://localhost:8002/health

# If the worker is down, restart it
docker compose -f docker-compose.production.yml restart infinity-void

# The circuit breaker will transition to half-open after 30 seconds,
# then close after successful calls
```

### High Memory Usage

```bash
# Check container resource usage
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"

# Check for SQLite database bloat
docker compose -f docker-compose.production.yml exec infinity-void \
  sqlite3 /data/void.db "SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()"

# Vacuum SQLite databases if needed
docker compose -f docker-compose.production.yml exec infinity-void \
  sqlite3 /data/void.db "VACUUM;"
```

### Traefik Routing Issues

```bash
# Check Traefik configuration
docker compose -f docker-compose.production.yml exec traefik \
  cat /etc/traefik/traefik.yml

# List active routers
curl -s http://localhost:8080/api/http/routers | python3 -m json.tool

# List active services
curl -s http://localhost:8080/api/http/services | python3 -m json.tool
```

---

## Shutdown Procedures

### Graceful Shutdown

```bash
# Stop all services gracefully
docker compose -f docker-compose.production.yml down

# Stop but preserve volumes
docker compose -f docker-compose.production.yml stop

# Stop and remove volumes (DESTRUCTIVE — loses all data)
docker compose -f docker-compose.production.yml down -v
```

### Rolling Restart (Zero Downtime)

```bash
# Restart workers one at a time, waiting for health between each
for svc in tranc3-ai infinity-void api-gateway infinity-ws infinity-auth \
           users-service monitoring notifications infinity-ai the-grid \
           products-service orders-service payments-service files-service \
           identity-service; do
  echo "Restarting $svc..."
  docker compose -f docker-compose.production.yml up -d --force-recreate "$svc"
  sleep 15
  echo -n "  Health: "
  curl -s "http://localhost:$(docker compose -f docker-compose.production.yml port $svc 8000 2>/dev/null || echo 'unknown')/health" 2>/dev/null || echo "checking manually"
  docker compose -f docker-compose.production.yml ps "$svc"
done
```

---

## Security Considerations

### Production Hardening Checklist

- [ ] Change all default secrets in `.env.production` (JWT_SECRET, INTERNAL_SECRET, MASTER_KEY_SEED)
- [ ] Set `GRAFANA_ADMIN_PASSWORD` to a strong, unique password
- [ ] Configure Vault for production mode (not dev mode) with TLS
- [ ] Enable Traefik TLS with Let's Encrypt or custom certificates
- [ ] Restrict Docker API access (no exposed Docker socket without TLS)
- [ ] Configure firewall rules to limit port exposure
- [ ] Enable Docker content trust for image verification
- [ ] Set up log rotation (configured: 10MB max, 3 files per service)
- [ ] Review and restrict inter-service network access
- [ ] Disable Traefik dashboard in production or bind to localhost only
- [ ] Configure backup encryption for vault data

### Vault Production Configuration

The default configuration runs Vault in dev mode. For production:

```yaml
# Replace the vault service command in docker-compose.production.yml:
vault:
  command: server -config=/vault/config/vault.hcl
  volumes:
    - ./vault-config:/vault/config:ro
    - vault-data:/vault/data
    - vault-config:/vault/config
```

Create `vault-config/vault.hcl`:

```hcl
storage "file" {
  path = "/vault/data"
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = 0
  tls_cert_file = "/vault/config/tls/cert.pem"
  tls_key_file  = "/vault/config/tls/key.pem"
}

disable_mlock = true
api_addr = "http://vault:8200"
```

---

## Port Reference

| Port Range | Service Type | Count |
|---|---|---|
| 80 | Traefik HTTP | 1 |
| 443 | Traefik HTTPS | 1 |
| 3001 | Grafana Dashboard | 1 |
| 4001 | IPFS Swarm | 1 |
| 5001 | IPFS API | 1 |
| 8001–8015 | P0–P2 Workers | 15 |
| 8016–8029 | P3 Stub Workers | 14 |
| 8080 | Traefik Dashboard | 1 |
| 8200 | Vault API | 1 |
| 9090 | Traefik Metrics | 1 |
| 9091 | Prometheus | 1 |

---

## File Reference

| File | Purpose |
|---|---|
| `docker-compose.production.yml` | Full production stack definition (36 services) |
| `.env.production` | Environment variables (secrets, API keys) |
| `scripts/test_docker_integration.py` | Compose file validation script |
| `workers/*/worker.py` | Individual worker FastAPI applications |
| `workers/*/Dockerfile` | Worker container build definitions |
| `tests/test_all_workers_health.py` | Worker health endpoint tests |
| `tests/test_worker_mesh_integration.py` | ServiceMesh integration tests |

---

## Emergency Contacts & Escalation

1. **Service Down**: Check health endpoint → Check logs → Restart service → Check circuit breaker
2. **Data Loss**: Stop all services → Restore from volume backup → Verify data integrity
3. **Security Incident**: Rotate all secrets in `.env.production` → Restart all services → Audit Vault access logs
4. **Full Stack Failure**: `docker compose -f docker-compose.production.yml down` → Verify volumes intact → `docker compose -f docker-compose.production.yml up -d`

---

*Last Updated: Phase 9 — Production Readiness*
*Stack Version: Zero-Cost Architecture (Self-Hosted Mesh)*
