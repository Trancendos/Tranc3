# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Commands

```bash
# Testing
make test            # full pytest suite with coverage
make test-fast       # skip slow/integration tests
pytest tests/test_tranc3_ml.py -v  # single test file

# Linting
make lint            # ruff + mypy

# Dev servers
make dev-api         # FastAPI backend on :8000 (hot-reload)
make dev-web         # frontend dev server

# Database
make migrate         # apply pending Alembic migrations
make migrate-new msg="describe change"  # create a new migration

# Cleanup
make clean           # remove __pycache__, .pyc, build artefacts
```

The `tranc3-bots` sub-project has its own pyproject.toml with matching pytest config; run tests from `tranc3-bots/` with `pytest`.

## Architecture

### Service map

| Service | Port | Repo path | Notes |
|---|---|---|---|
| tranc3-backend | 8000 | `/` (root) | FastAPI, SQLAlchemy, JWT auth |
| nanoservices | 8001 | `src/nanoservices/` | Thin proxy to tranc3-bots |
| tranc3-bots | 8080 | `tranc3-bots/` | Separate Fly.io app, 12 bot types |
| tranc3-ai | edge | `cloudflare/tranc3-ai/` | CF Worker — AI edge proxy |
| infinity-void | edge | `cloudflare/infinity-void/` | CF Worker — encrypted secrets vault |

### Inference pipeline (3-tier fallback)

```
Client → tranc3-ai CF Worker
           ↓ (cf.ai → Workers AI)
           ↓ FAIL → TRANC3_BACKEND_URL (Fly.io :8000)
           ↓ FAIL → TRANC3_NANO_URL (:8001 nanoservices)
           ↓ FAIL → deterministic stub response
```

### Backend (`api.py`)

Entry point: `api.py`. Fails fast if `SECRET_KEY` is unset.

Key module domains under `src/`:
- `core/` — Tranc3Engine (transformer inference), startup validator, circuit breaker
- `registry/` — BotRegistry: maps BotType → handler
- `personality/` — 5 named personality instances (dorris-fontaine, cornelius-macintyre, the-guardian, vesper-nightingale, atlas-meridian)
- `monetisation/` — billing tiers: free (100 req/hr), pro £29 (1k/hr), business £149 (10k/hr)
- `database/` — SQLAlchemy models + Alembic migrations
- `auth/` — JWT, session management
- `mcp/` — MCP server integration
- `workers/` — background worker tasks
- `workflow/` — multi-step workflow orchestration
- `errors/error_catalog.py` — canonical ErrorCode enum
- `validation/loop_validator.py` — CircuitBreaker + LoopValidator (prevents cascade failures)
- `observability/` — metrics, tracing

### Tranc3Engine (bootstrap mode)

`src/core/tranc3_inference.py` loads weights from `MODEL_PATH` / `TOKENIZER_PATH`. If the weight files are absent it enters **bootstrap mode**: inference returns structured placeholder responses so the full service keeps running. All tests use bootstrap/synthetic mode — no real model weights are needed to run the test suite.

### BotRegistry (tranc3-bots)

12 bot types split into two groups:
- **Inference bots** (proxy to Tranc3Engine): GENERATE, EMBED, EMOTION, TOKENIZE, CONSCIOUSNESS, PERSONALITY, PREDICT
- **Utility bots** (standalone): CODE, MEMORY, MONITOR, SEARCH, SUMMARISE

### Cloudflare Workers

**tranc3-ai** (`cloudflare/tranc3-ai/`): edge AI proxy. Wrangler config binds `CACHE` (KV) and `SESSIONS` (KV).

**infinity-void** (`cloudflare/infinity-void/`): AES-GCM encrypted secrets vault.
- Encryption: PBKDF2 key derivation (100k iterations, SHA-256), 256-bit keys, random IV per secret
- Storage: D1 database (`DB`) for metadata + encrypted payload; R2 (`R2_SECRETS`) is **optional** — ciphertext stored in D1 `payload` column when R2 is absent
- Routes: `GET /health`, `GET /vault/status`, `POST /secrets`, `POST /secrets/retrieve`, `GET /secrets`, `GET/DELETE /secrets/:id`, `GET /secrets/:id/audit`
- Rate limiting via KV (`KV_RATE_LIMIT`)
- To upgrade to R2: enable R2 in CF dashboard, create `void-secrets` bucket, uncomment `[[r2_buckets]]` in `cloudflare/infinity-void/wrangler.toml`, redeploy

## Required Environment Variables

See `.env.example` for the full list. Critical ones:

```
SECRET_KEY               # FastAPI signing key (hard fail if missing)
DATABASE_URL             # SQLAlchemy connection string
TRANC3_BACKEND_URL       # Fly.io backend URL (set as CF Worker secret)
MODEL_PATH / TOKENIZER_PATH  # Weight file paths (omit to run in bootstrap mode)
STRIPE_SECRET_KEY        # Payment processing
```

## CI/CD

**All CI/CD runs through Forgejo (The Workshop) — no GitHub Actions.**

Workflow files live in `.forgejo/workflows/`:
- `deploy-fly.yml` — deploys tranc3-backend + tranc3-bots to Fly.io (triggers on push to `main` for `.py`, `Dockerfile`, `fly.toml`, `requirements.txt`, `tranc3-bots/**`)
- `deploy-cloudflare.yml` — deploys tranc3-ai + infinity-void CF Workers (triggers on push to `main` for `cloudflare/**`)

Forgejo runs at `trancendos.com/the-workshop`. The act-runner (`deploy/forgejo/docker-compose.yml`) executes jobs on the self-hosted machine. Secrets (`CF_API_TOKEN`, `FLY_API_TOKEN`) are stored as Forgejo org-level secrets.

### Manual deploy (from desktop, not sandbox)

```bash
# Backend
fly deploy --remote-only                # from repo root
# Bots
cd tranc3-bots && fly deploy --remote-only

# CF Worker secrets (after Fly deploy)
echo "https://tranc3-backend.fly.dev" | wrangler secret put TRANC3_BACKEND_URL --name tranc3-ai

# Workshop setup (on trancendos.com server)
./deploy/forgejo/setup.sh
# then add nginx block from deploy/forgejo/nginx-the-workshop.conf
# then register runner via deploy/forgejo/runner-setup.sh
```

## Deployment Topology

All Trancendos services are **subdirectories** of `trancendos.com`, not subdomains:
- `trancendos.com/the-workshop` → Forgejo (port 3456)

Fly.io apps:
- `tranc3-backend` — region `lhr`, 256MB, 1GB encrypted volume mounted at `/app/models`
- `tranc3-bots` — region `lhr`, 256MB

Zero-cost model enforced — no paid external services beyond the committed Fly.io/Cloudflare free tiers.
