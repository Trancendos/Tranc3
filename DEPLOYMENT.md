# TRANC3 Deployment Runbook

## Prerequisites

Before deploying, ensure you have:

- A server or cloud instance (minimum: 2 vCPU, 4 GB RAM for API-only; 8 GB+ if running local inference)
- Docker and Docker Compose installed
- At least one LLM provider API key (HuggingFace free tier works for testing)
- A `SECRET_KEY` generated for JWT tokens

## Quick Start (Development)

```bash
# 1. Clone and enter the repo
git clone https://github.com/Trancendos/Tranc3.git
cd Tranc3
git checkout production-readiness-impl

# 2. Copy and edit environment config
cp .env.example .env
# Edit .env — at minimum set:
#   SECRET_KEY=<run: python -c "import secrets; print(secrets.token_hex(32))">
#   HF_API_KEY=<your HuggingFace API key>

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the production API
uvicorn api_production:app --reload --port 8000

# 5. Verify
curl http://localhost:8000/health
curl http://localhost:8000/health/detailed
```

## Production Deployment with Docker Compose

### Full Stack (API + PostgreSQL + Redis + Observability)

```bash
# 1. Set required env vars
cp .env.example .env

# Generate a secure SECRET_KEY
python3 -c "import secrets; print(secrets.token_hex(32))" >> .env

# Set a strong database password
echo "DB_PASSWORD=$(openssl rand -hex 16)" >> .env

# Set at least one LLM provider key
echo "HF_API_KEY=hf_your_key_here" >> .env
# Optional but recommended:
# echo "GROQ_API_KEY=gsk_your_key_here" >> .env

# 2. Start core services (API + DB + Redis)
docker compose up -d api db redis

# 3. Check health
docker compose logs -f api
curl http://localhost:8000/ready

# 4. (Optional) Start observability stack
docker compose --profile observability up -d
```

### Minimal Stack (API + SQLite + In-Memory Rate Limiting)

For quick testing or low-traffic deployments, you can skip PostgreSQL and Redis:

```bash
# .env settings for minimal deploy
DATABASE_URL=sqlite:///./tranc3.db
# Leave REDIS_URL empty or unset

# Run just the API
docker build -f docker/Dockerfile.api -t tranc3-api .
docker run -p 8000:8000 --env-file .env tranc3-api
```

Note: SQLite does not support concurrent writes well. Use PostgreSQL for any multi-user deployment.

## Environment Variables Reference

### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `SECRET_KEY` | JWT signing key. Must be 32+ random hex chars. | `a1b2c3...` |
| `DATABASE_URL` | SQLAlchemy connection string | `postgresql://tranc3:pw@db:5432/tranc3` |
| At least one of `HF_API_KEY`, `GROQ_API_KEY`, or `OPENAI_API_KEY` | LLM provider API key | `hf_abc123` |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | (empty) | Redis connection string for rate limiting and caching |
| `LOG_LEVEL` | `INFO` | Logging verbosity: DEBUG, INFO, WARNING, ERROR |
| `LOG_FORMAT` | `console` | `console` for human-readable, `json` for structured |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins |
| `LOCAL_MODEL_PATH` | (empty) | Path to local Tranc3 model weights |
| `STRIPE_SECRET_KEY` | (empty) | Stripe key for billing integration |

## Health Check Endpoints

| Endpoint | Purpose | Use For |
|----------|---------|---------|
| `GET /health` | Basic liveness check | Load balancer, Docker HEALTHCHECK |
| `GET /health/detailed` | Per-subsystem status | Monitoring, debugging |
| `GET /ready` | Readiness (all critical deps up) | Kubernetes readiness probe |

### Health Response Examples

**Healthy:**
```json
{
  "status": "healthy",
  "version": "3.0.0",
  "uptime_seconds": 3600
}
```

**Degraded (no Redis, but functional):**
```json
{
  "status": "degraded",
  "services": {
    "database": {"status": "healthy"},
    "redis": {"status": "unavailable", "message": "Connection refused"},
    "inference": {"status": "healthy"}
  }
}
```

## LLM Provider Setup

### HuggingFace (Free Tier — Recommended for Testing)

1. Create account at https://huggingface.co
2. Go to Settings → Access Tokens → New Token
3. Set `HF_API_KEY=hf_your_token` in `.env`
4. Free tier allows ~1000 requests/day with rate limits

### Groq (Free Tier — Fast Inference)

1. Create account at https://console.groq.com
2. Create API key in Keys section
3. Set `GROQ_API_KEY=gsk_your_key` in `.env`
4. Free tier: 30 requests/minute, 14400/day

### OpenAI (Paid — Best Quality)

1. Create account at https://platform.openai.com
2. Create API key
3. Set `OPENAI_API_KEY=sk-your-key` in `.env`
4. Pay-per-token pricing applies

### Provider Priority

The router tries providers in this order:
1. **Local Tranc3 model** (if weights available and loaded)
2. **HuggingFace** (free)
3. **Groq** (free, fast)
4. **OpenAI** (paid, highest quality)
5. **Bootstrap fallback** (returns honest "not configured" message)

## Database Migrations

```bash
# Run all migrations
alembic upgrade head

# Check current migration state
alembic current

# Rollback one migration
alembic downgrade -1

# Create a new migration after schema changes
alembic revision --autogenerate -m "description"
```

## Monitoring

### Built-in Metrics Endpoint

```bash
curl http://localhost:8000/metrics
```

Returns request counts, cache hit rates, and provider usage.

### Grafana Dashboard (with Observability Stack)

1. Start the observability profile: `docker compose --profile observability up -d`
2. Open Grafana at http://localhost:3001
3. Default credentials: admin/admin (change immediately)
4. Dashboards are auto-provisioned from `deploy/grafana-provisioning/`

### Structured Log Examples

```json
{"ts":"2024-01-15T10:30:00","level":"INFO","logger":"tranc3.api_production","msg":"request completed","duration_ms":245,"provider":"groq","tokens":128}
{"ts":"2024-01-15T10:30:01","level":"WARNING","logger":"tranc3.api_production","msg":"Redis unavailable","error":"Connection refused"}
```

## Troubleshooting

### "SECRET_KEY is not set"
Generate one: `python -c "import secrets; print(secrets.token_hex(32))"` and add to `.env`.

### "Inference service not ready"
Check that at least one LLM provider API key is set. Run `/health/detailed` to see which providers are available.

### "Database init failed"
- Check `DATABASE_URL` is correct
- For PostgreSQL: ensure the database exists and user has permissions
- For SQLite: ensure the directory is writable
- Run `alembic upgrade head` to create tables

### Rate Limiting Not Working
- Without Redis, rate limiting uses in-memory buckets (lost on restart)
- For distributed rate limiting, set `REDIS_URL` and start the Redis container

### Slow Responses
- Check `/inference/providers` to see which provider is being used
- HuggingFace free tier has queue times; Groq is faster
- Local model is instantest but requires GPU + trained weights

## Rollback Procedure

```bash
# 1. Switch to previous image
docker compose down api
docker tag tranc3-api:previous tranc3-api:current
docker compose up -d api

# 2. If database migration was applied:
alembic downgrade -1

# 3. Verify health
curl http://localhost:8000/ready
```

## Security Checklist

- [ ] `SECRET_KEY` is a strong random value (not committed to git)
- [ ] Database password is not the default
- [ ] `.env` file is not committed to git (check `.gitignore`)
- [ ] CORS origins are restricted to your frontend domains
- [ ] HTTPS is configured (via reverse proxy or cloud load balancer)
- [ ] Rate limiting is enabled (Redis-backed for production)
- [ ] Log level is INFO or higher (not DEBUG in production)
- [ ] Grafana default password is changed
