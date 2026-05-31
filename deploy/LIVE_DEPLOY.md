# Live deploy guide (Citadel — 100% self-hosted path)

This is the **canonical procedure** to go from git clone to a running platform without Cloudflare Workers.

## Prerequisites

- Linux host (Citadel) with Docker Compose v2
- Python 3.11+
- Ports 80, 443, 3000, 6379, 8000–8013, 8044, 8053, 8200, 9091 free

## One command

```bash
./scripts/deploy_live.sh
```

What it does:

1. `scripts/generate_production_env.sh` → `.env.production` (real secrets, SQLite, Valkey)
2. `scripts/citadel_compose_validate.py` + `scripts/citadel_preflight.py`
3. `docker compose -f docker-compose.production.yml up` (core P0+P1 + observability)
4. `scripts/wait_for_healthy.py`
5. Health audit + production scorecard

## Step by step

```bash
git clone https://github.com/Trancendos/Tranc3.git && cd Tranc3
pip install -r requirements.txt

./scripts/generate_production_env.sh --force   # once
make citadel-preflight
./scripts/deploy_live.sh

# First-time Vault (file storage):
./deploy/vault/init-citadel.sh

make monitor
make production-score
```

## URLs (default local)

| Surface | URL |
|---------|-----|
| Tranc3 API | http://localhost:8000 |
| Readiness | http://localhost:8000/ready |
| API Gateway | http://localhost:8003 |
| Infinity Admin OS | http://localhost:8000/dashboard/infinity-admin-os.html |
| Grafana | http://localhost:3000 |
| Traefik dashboard | http://localhost:8888 |

## Production DNS

Point `api.trancendos.com` to Traefik on Citadel (port 443). Disable Cloudflare Worker routes for migrated paths.

## Profiles

```bash
DEPLOY_PROFILE=full ./scripts/deploy_live.sh   # more P2 workers
./scripts/deploy_live.sh --skip-build          # faster restarts
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Vault sealed | `./deploy/vault/init-citadel.sh` |
| Redis errors | Ensure `valkey` container is up; `REDIS_URL=redis://valkey:6379/0` |
| `/ready` 503 | Wait for bootstrap; check `docker logs tranc3-backend` |
| Ollama offline | `docker exec tranc3-ollama ollama pull llama3.2:1b` |

See also: `docs/PRODUCTION_READINESS_STATUS.md`
