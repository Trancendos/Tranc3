# DNS cutover — api.trancendos.com → Citadel (Phase 3)

Run **after** `make deploy-live` and `make monitor` show P0/P1 UP.

## 1. Verify Traefik locally

```bash
curl -sS http://localhost:8003/health
curl -sS -H 'Host: api.trancendos.com' http://localhost/api/health || true
```

## 2. DNS records

| Record | Type | Target |
|--------|------|--------|
| `api.trancendos.com` | A or CNAME | Citadel public IP / hostname |
| `trancendos.com` | A or CNAME | Same (if serving dashboard via Traefik) |

Disable Cloudflare orange-cloud proxy **only after** TLS is working on Citadel, or terminate TLS at Cloudflare with origin pointing to Citadel.

## 3. Cloudflare Worker routes to remove

Per `CF_WORKER_MIGRATION_ROADMAP.md`, disable routes for:

- `api.trancendos.com/*` → `trancendos-api-gateway`
- Migrated auth/AI paths already served by self-hosted workers

## 4. TLS on Citadel

Enable Let's Encrypt on Traefik (`certificatesresolvers.letsencrypt` in static config) before forcing HTTPS. Until then, use `http://` entrypoint `web` labels on `api-gateway`.

## 5. Post-cutover checks

```bash
curl -sS https://api.trancendos.com/health
make monitor
pytest tests/test_uat.py -v --base-url=https://api.trancendos.com
```
