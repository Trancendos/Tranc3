# Self-Hosted Workers — Replacing Cloudflare Worker Dependencies

This directory contains **self-hosted Python workers** that replace all Cloudflare Worker dependencies in the Tranc3 platform. This migration supports the **zero-cost model** — no external provider dependencies, no billing surprises, full self-ownership.

## Migration Map

| Cloudflare Worker | Self-Hosted Replacement | Port |
|---|---|---|
| `cloudflare/tranc3-ai` | `workers/tranc3-ai/worker.py` | 8001 |
| `cloudflare/infinity-void` | `workers/infinity-void/worker.py` | 8002 |
| `cloudflare/trancendos-api-gateway` | `workers/api-gateway/worker.py` | 8003 |

## Architecture Principles

1. **Zero external dependencies** — no Cloudflare, no wrangler, no paid APIs
2. **Self-owned inference** — all AI inference through Tranc3 backend or honest stubs
3. **Pure Python** — FastAPI + uvicorn, the same stack as the main Tranc3 backend
4. **Containerized** — Docker + docker-compose for deployment anywhere
5. **Feature parity** — every Cloudflare Worker feature is replicated in Python

## What Changed from Cloudflare Workers

### tranc3-ai (AI Inference Worker)
- **Before**: Cloudflare Worker using `fetch()` to call backends, stub responses
- **After**: FastAPI app using `httpx` to call backends, same stub responses
- **Improvements**: Native Python async, easier testing, no cold starts, full control

### infinity-void (Secrets Vault)
- **Before**: Cloudflare Worker using D1 (SQL), KV (rate limiting), R2 (file storage)
- **After**: FastAPI app using SQLite (replaces D1), in-memory rate limiter (replaces KV), local file storage (replaces R2)
- **Improvements**: Data sovereignty (your data on your hardware), no D1 limits, persistent storage

### api-gateway (API Gateway)
- **Before**: Cloudflare Worker with JWT auth, circuit breakers, KV rate limiting, proxying
- **After**: FastAPI app with same JWT auth, circuit breakers, in-memory rate limiting, httpx proxying
- **Improvements**: No Cloudflare dependency, no KV costs, full control over routing

## Quick Start

### Development (local)
```bash
# Run individual workers
cd workers/tranc3-ai && pip install -r requirements-worker.txt && python worker.py
cd workers/infinity-void && pip install -r requirements-worker.txt && python worker.py
cd workers/api-gateway && pip install -r requirements-worker.txt && python worker.py
```

### Production (Docker Compose)
```bash
# Build and run all workers
docker compose -f docker-compose.self-hosted.yml up -d

# Check health
curl http://localhost:8001/health  # tranc3-ai
curl http://localhost:8002/health  # infinity-void
curl http://localhost:8003/health  # api-gateway
```

### Production (Fly.io — zero cost)
```bash
# Deploy each worker to Fly.io free tier
fly launch --name tranc3-ai-worker --path workers/tranc3-ai
fly launch --name infinity-void-worker --path workers/infinity-void
fly launch --name api-gateway-worker --path workers/api-gateway
```

## Forgejo CI Integration

All worker deployments are managed through Forgejo CI workflows:
- `.forgejo/workflows/deploy-self-hosted.yml` — builds and deploys workers
- `.forgejo/workflows/security-scan.yml` — includes npm audit for remaining CF code

## Cloudflare Worker Source (Reference Only)

The original Cloudflare Worker source code remains in `cloudflare/` for reference during the transition period. Once the self-hosted workers are fully validated in production, the `cloudflare/` directory can be removed entirely.

## Zero-Cost Guarantee

| Component | Before | After |
|---|---|---|
| AI Inference | Cloudflare Workers (paid tier) | Self-hosted FastAPI (free) |
| Secrets Vault | Cloudflare D1 + KV + R2 (paid tier) | SQLite + in-memory + local files (free) |
| API Gateway | Cloudflare Workers + KV (paid tier) | Self-hosted FastAPI (free) |
| CI/CD | GitHub Actions (billed) | Forgejo CI (self-hosted, free) |
| Deployment | Cloudflare wrangler | Docker / Fly.io free tier |

**Total external provider cost: $0**
