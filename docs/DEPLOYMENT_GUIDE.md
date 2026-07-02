# Tranc3 Deployment Guide — Zero-Cost Infrastructure

> **Version:** 0.1.0  
> **Mandate:** All cloud services must be zero-cost. Free-tier only. No paid tiers, no credit-expiring trials.  
> **Last Updated:** 2026-05-23  

---

## Overview

This guide covers deploying the Tranc3 platform using exclusively zero-cost infrastructure. The system is designed to auto-modulate across providers to maintain zero cost while maximizing resilience. The storage priority chain is: ZFS (local) → MinIO (self-hosted) → Ceph (self-hosted) → Cloudflare R2 (free tier) → OCI (always free).

---

## Prerequisites

### Local Development

- **Python 3.11+** (required)
- **Docker** and **Docker Compose** (for self-hosted services)
- **Git** (for repository cloning)
- **4 GB RAM minimum** (8 GB recommended for local AI inference)

### Cloud Accounts (All Free)

| Provider | Account Type | Key Free Resources |
|----------|-------------|-------------------|
| Oracle Cloud | Always Free | 2 AMD VMs, 4 ARM VMs (24GB RAM), 200GB storage |
| Cloudflare | Free Plan | R2 storage (10GB), Workers (100K req/day), Pages |
| GitHub | Public Repo | Actions (2000 min/month), CodeQL, Packages |

---

## Quick Start (Local Development)

### 1. Clone and Install

```bash
git clone https://github.com/Trancendos/Tranc3.git
cd Tranc3
pip install -r requirements.txt
pip install -r requirements-test.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your configuration (all defaults work for local dev)
```

### 3. Run the API Server

```bash
# Primary API (port 8000)
python -m uvicorn api:app --host 0.0.0.0 --port 8000 --reload

# Nanoservices layer (port 8001)
python -m uvicorn src.nanoservices.app:app --host 0.0.0.0 --port 8001 --reload
```

### 4. Verify

```bash
curl http://localhost:8000/health
curl http://localhost:8001/health
```

---

## Docker Compose Deployment

### Start All Services

```bash
docker-compose -f docker-compose.storage.yml up -d
```

This starts:
- **MinIO** (S3-compatible object storage) — port 9000/9001
- **Prometheus** (metrics collection) — port 9090
- **Alertmanager** (alert routing) — port 9093
- **PostgreSQL** (primary database) — port 5432
- **Redis** (caching & session store) — port 6379

### Storage Configuration

The SmartStorageOrchestrator automatically handles storage tiering:

1. **ZFS** (local filesystem with snapshots and replication)
2. **MinIO** (self-hosted S3-compatible storage)
3. **Ceph** (distributed storage — self-hosted)
4. **Cloudflare R2** (zero-cost egress, 10GB free)
5. **OCI Object Storage** (always free, 20GB)

---

## Oracle Cloud Infrastructure (OCI) Deployment

OCI provides the most generous always-free tier, making it the primary cloud provider for Tranc3.

### 1. Create Always Free Compute Instance

```bash
# Using OCI CLI (install from: https://docs.oracle.com/en-us/iaas/Content/API/Concepts/clickstart.htm)
oci compute instance launch \
  --availability-domain "your-ad" \
  --compartment-id "your-compartment" \
  --shape "VM.Standard.E2.1.Micro" \
  --image-id "Oracle-Linux-9" \
  --display-name "tranc3-server"
```

### 2. Configure the Instance

```bash
# SSH into the instance
ssh opc@<instance-ip>

# Install Python 3.11
sudo dnf install python3.11 python3.11-pip

# Clone the repository
git clone https://github.com/Trancendos/Tranc3.git
cd Tranc3

# Install dependencies
pip3.11 install -r requirements.txt
```

### 3. Set Up as systemd Service

Create `/etc/systemd/system/tranc3.service`:

```ini
[Unit]
Description=Tranc3 AI Platform
After=network.target

[Service]
Type=simple
User=opc
WorkingDirectory=/home/opc/Tranc3
ExecStart=/usr/bin/python3.11 -m uvicorn api:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable tranc3
sudo systemctl start tranc3
```

---

## Cloudflare Workers Deployment (Edge Inference)

For lightweight edge inference and API routing:

### 1. Install Wrangler CLI

```bash
npm install -g wrangler
wrangler login
```

### 2. Deploy Worker

```bash
cd Tranc3
wrangler deploy
```

### 3. Configure R2 Storage

```bash
wrangler r2 bucket create tranc3-storage
```

The free tier includes:
- **Workers**: 100,000 requests/day
- **R2**: 10 GB storage, 10 million Class A ops/month, 1 million Class B ops/month
- **Pages**: 500 builds/month, 100GB bandwidth

---

## CI/CD Pipeline

### GitHub Actions (Free for Public Repos)

The CI pipeline runs automatically on all pull requests:

1. **Lint Gate** — Ruff lint + format check
2. **Test Suite** — Pytest with 1231 tests
3. **CodeQL** — Security analysis (python + javascript-typescript)
4. **Trivy** — Vulnerability and misconfiguration scanning

### Forgejo CI (Self-Hosted)

The adaptive CI pipeline provides:
- Adaptive quality gates with trend analysis
- Regression detection via historical comparison
- Auto-issue creation on security regression
- Configuration drift detection
- Security telemetry aggregation

---

## Monitoring Stack

### Prometheus + Alertmanager

Metrics are collected by Prometheus and alerts are routed through Alertmanager:

```bash
# Start monitoring stack
docker-compose -f docker-compose.storage.yml up prometheus alertmanager -d

# Access dashboards
# Prometheus: http://localhost:9090
# Alertmanager: http://localhost:9093
```

### Tranc3 Built-in Monitoring

```bash
# Health check
curl http://localhost:8000/health

# Prometheus metrics
curl http://localhost:8000/metrics

# Admin endpoints (authenticated)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/admin/registry
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/admin/circuits
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/admin/healing
```

---

## Security Configuration

### Authentication

The platform uses JWT-based authentication with zero-trust principles:

- All protected endpoints require Bearer token
- Token refresh with rotating refresh tokens
- Rate limiting per user (configurable by billing tier)
- Circuit breakers for all external service calls

### Secret Management

- **Never** commit secrets to the repository
- Use environment variables for all sensitive configuration
- The `.env.example` file documents all required variables
- GitGuardian scans all PRs for accidentally committed secrets

### Vault Security

The VaultSecurityManager provides:
- Zero-knowledge encryption of stored data
- Key rotation with configurable intervals
- Audit logging of all vault operations
- Immutable forensic compliance records

---

## Scaling Strategy

### Vertical (Single Instance)

The Tranc3 platform is designed to run efficiently on a single OCI Always Free VM:
- ARM Ampere A1 (4 OCPUs, 24GB RAM) — recommended
- AMD E2 Micro (1/8 OCPU, 1GB RAM) — minimal

### Horizontal (Multi-Instance)

For higher availability using only free-tier resources:
- Deploy to multiple OCI regions (always free resources per region)
- Use Cloudflare Workers for edge routing and caching
- Use OCI Load Balancer (always free: 1 LB, 10Mbps)

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` |
| Port already in use | Change port with `--port` flag or kill existing process |
| OOM during inference | Reduce `max_tokens` or use a smaller model |
| Docker Compose fails | Ensure Docker daemon is running: `sudo systemctl start docker` |
| OCI instance unreachable | Check security list rules allow inbound traffic on port 8000 |

### Logs

```bash
# Application logs
python -m uvicorn api:app --log-level debug

# Docker service logs
docker-compose -f docker-compose.storage.yml logs -f

# systemd service logs
journalctl -u tranc3 -f
```

---

*Generated for the Tranc3 platform. For architecture details, see [System Architecture](DOC-02-System-Architecture.md). For zero-cost cloud providers research, see [Zero-Cost Cloud Providers](ZERO_COST_CLOUD_PROVIDERS.md). For the full self-hosted production runbook see [DEPLOYMENT_RUNBOOK.md](DEPLOYMENT_RUNBOOK.md).*
