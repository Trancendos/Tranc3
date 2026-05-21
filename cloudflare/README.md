# Tranc3 — Cloudflare Deployment

## Architecture

```
Internet
  │
  ▼
trancendos-api-gateway          (Cloudflare Worker — rate-limit, auth, circuit-break)
  ├── /api/auth/*           →   infinity-auth-api          (D1 database, JWT, RBAC)
  ├── /api/users/*          →   trancendos-users-service
  ├── /api/products/*       →   trancendos-products-service
  ├── /api/orders/*         →   trancendos-orders-service
  ├── /api/payments/*       →   trancendos-payments-service
  └── /api/v1/ai/*          →   tranc3-ai                  ← NEW

tranc3-ai
  ├── CF Workers AI          (default: LLaMA 3.1 8B, Mistral 7B, BGE embeddings)
  └── TRANC3_BACKEND_URL     (optional: proxy to Python Tranc3 backend when available)
```

## Important Constraint

**Cloudflare Workers cannot run Python/PyTorch.**

The `tranc3-ai` worker handles the AI API layer:
- **Without a backend**: Uses Cloudflare's hosted AI models (LLaMA, Mistral, BGE)
- **With a backend**: Proxies to your Tranc3 Python server, falls back to CF Workers AI on error

## Quick Deploy

```bash
# 1. Get a Cloudflare API token (Workers Scripts:Edit + Workers Routes:Edit permissions)
#    https://dash.cloudflare.com/profile/api-tokens

export CLOUDFLARE_API_TOKEN="your-token-here"
./cloudflare/deploy.sh
```

## Manual Deploy Steps

### 1. Deploy tranc3-ai worker

```bash
cd cloudflare/tranc3-ai
npm install
npx wrangler deploy

# Set auth URL so tranc3-ai can validate JWTs
echo "https://infinity-auth-api.trancendos.workers.dev" \
  | npx wrangler secret put TRANC3_AUTH_URL --name tranc3-ai
```

### 2. Deploy updated API gateway

```bash
cd cloudflare/trancendos-api-gateway
# First find your CACHE KV namespace ID:
npx wrangler kv:namespace list
# Edit wrangler.toml: set id = "<your-kv-id>"

npx wrangler deploy

# Set service URLs
echo "https://tranc3-ai.trancendos.workers.dev" \
  | npx wrangler secret put TRANC3_AI_SERVICE_URL --name trancendos-api-gateway
echo "https://infinity-auth-api.trancendos.workers.dev" \
  | npx wrangler secret put USERS_SERVICE_URL --name trancendos-api-gateway
```

### 3. Update auth CORS to allow trancendos.com

```bash
echo "https://trancendos.com,https://www.trancendos.com" \
  | npx wrangler secret put ALLOWED_ORIGINS --name infinity-auth-api
```

### 4. Delete stale workers

These workers are safe to delete (duplicates and old unrelated projects):

```bash
for w in trancendos-api-gateway-production trancendos-users-service-production \
          infinity-api-gateway arcadia-exchange arcadia-royal-bank \
          orchestrator infinity-void infinity-lighthouse infinity-one infinity-hive; do
  npx wrangler delete "$w" --force
done
```

### 5. Connect Tranc3 Python backend (when ready)

When you have the Tranc3 Python server running on a VPS:

```bash
echo "https://your-tranc3-server.com" \
  | npx wrangler secret put TRANC3_BACKEND_URL --name tranc3-ai
```

Start the backend:
```bash
# On your VPS:
pip install -r requirements.txt
python -m uvicorn api:app --host 0.0.0.0 --port 8000

# Or with Docker:
docker build -t tranc3 .
docker run -d -p 8000:8000 --env-file .env tranc3
```

## API Endpoints (after deploy)

| Endpoint | Auth | Description |
|---|---|---|
| `GET  /health` | None | Health check |
| `GET  /api/v1/ai/models` | None | List available models |
| `POST /api/v1/ai/chat` | Bearer token | Text generation / chat |
| `POST /api/v1/ai/embeddings` | Bearer token | Vector embeddings |
| `POST /api/v1/ai/analyze-emotion` | Bearer token | Emotion detection |
| `POST /api/v1/ai/consciousness` | Bearer token | Consciousness scoring (requires backend) |

## Environment Variables

| Worker | Variable | Description |
|---|---|---|
| `tranc3-ai` | `TRANC3_BACKEND_URL` | URL of Tranc3 Python backend (optional) |
| `tranc3-ai` | `TRANC3_AUTH_URL` | URL of auth worker |
| `tranc3-ai` | `ALLOWED_ORIGINS` | Extra allowed CORS origins (comma-separated) |
| `trancendos-api-gateway` | `TRANC3_AI_SERVICE_URL` | URL of tranc3-ai worker |
| `trancendos-api-gateway` | `JWT_SECRET` | Shared JWT secret (must match auth worker) |
| `infinity-auth-api` | `ALLOWED_ORIGINS` | Extra CORS origins (trancendos.com) |

## Workers to Keep

| Worker | Purpose | Action |
|---|---|---|
| `trancendos-api-gateway` | Main reverse proxy | **Update** (this directory) |
| `infinity-auth-api` | JWT auth + D1 user DB | **Keep** (update ALLOWED_ORIGINS) |
| `infinity-ai-api` | Legacy AI (can keep as fallback or delete) | Optional |
| `trancendos-*-service` | E-commerce microservices | **Keep** |
| `tranc3-ai` | Tranc3 AI layer | **Deploy** (this repo) |

## Workers to Delete

| Worker | Reason |
|---|---|
| `trancendos-api-gateway-production` | Duplicate of gateway |
| `trancendos-users-service-production` | Duplicate |
| `infinity-api-gateway` | Superseded by `trancendos-api-gateway` |
| `arcadia-exchange` | Old/unrelated project |
| `arcadia-royal-bank` | Old/unrelated project |
| `orchestrator` | Old/unused |
| `infinity-void`, `infinity-lighthouse`, `infinity-one`, `infinity-hive` | Old/unused |
