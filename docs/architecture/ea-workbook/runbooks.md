# Operational Runbooks — Anchor Services

Incident-response and operational procedures for the six anchor services seeded in this
workbook (`README.md`). Written for the platform's **actual** infrastructure — Docker
Compose + Traefik on `SRV-CITADEL-01`, self-hosted CI via Forgejo — not Kubernetes or AWS.

The Workshop already has a dedicated, more detailed recovery runbook at
`deploy/forgejo/RUNBOOK.md` (topology-aware, backed by `deploy/forgejo/recover.sh`). Use
that one for Forgejo incidents; it is the authoritative Workshop runbook. The procedure
below is a short pointer only, kept for completeness of the six-service set.

All container names below are as declared in `docker-compose.production.yml`. Replace
`docker-compose.production.yml` with `deploy/forgejo/docker-compose.yml` where the
Workshop runbook's standalone topology applies.

---

## RUNBOOK: The Spark (MCP Tool Registry)
**Owner:** Norman Hawkins · **SLA:** 99.9% · **CriticalityCode:** CRT-001
**Service/App IDs:** `SRV-SPARK-001` / `APP-SPARK-001` (see `02_service_inventory.csv`, `03_application_catalogue.csv`)
**Hard dependencies:** `SRV-VOID-001` (secrets), `SRV-INF-001` (auth) — see `15_dependencies.csv`

### Health check
```bash
curl -s http://localhost:8000/mcp/health | jq '.status'   # expect "healthy"
docker inspect -f '{{.State.Health.Status}}' tranc3-backend
```
Escalate immediately if the vault or auth dependency checks below fail — do not restart
The Spark first, since it will come back unhealthy again while they're down:
```bash
curl -s http://localhost:8038/health   # vault-service
curl -s http://localhost:8005/health   # infinity-auth
```

### Restart
```bash
docker compose -f docker-compose.production.yml restart tranc3-backend
docker compose -f docker-compose.production.yml logs --tail 50 tranc3-backend
```
No drain step is needed — MCP tool calls are short-lived HTTP/SSE requests, not
long-running jobs; a restart simply drops in-flight requests, which callers retry.

### Rollback (bad deploy)
```bash
# Redeploy previous known-good commit via Forgejo Actions
git -C /opt/tranc3 checkout <PREVIOUS_COMMIT_SHA>
docker compose -f docker-compose.production.yml up -d --build tranc3-backend
```
Or trigger `workflow_dispatch` on `deploy-fly.yml` / `deploy-self-hosted.yml` against the
previous tag from the Forgejo Actions tab.

### Success criteria
`/mcp/health` returns `healthy` 3 consecutive checks, 10s apart; `/mcp/tools` returns the
full registered tool list.

---

## RUNBOOK: The Digital Grid (Workflow Engine)
**Owner:** Tyler Towncroft · **SLA:** 99.9% · **CriticalityCode:** CRT-001
**Service/App IDs:** `SRV-GRID-001` / `APP-GRID-001`
**Hard dependencies:** `SRV-VOID-001`, `SRV-INF-001` · **Soft dependency:** `SRV-SPARK-001` (workflow steps that call MCP tools degrade gracefully — see `DEP-003` in `15_dependencies.csv`)

### Health check
```bash
curl -s http://localhost:8034/health | jq '.status'
docker inspect -f '{{.State.Health.Status}}' workflow-engine-service-worker
```

### Restart
```bash
docker compose -f docker-compose.production.yml restart workflow-engine-service
```

### Scaling (queue backlog)
This service is the one anchor with `AutoScalingEnabled=TRUE` (`02_service_inventory.csv`,
max 3 instances). `docker compose --scale` cannot be used as-is today — the
`workflow-engine-service` entry in `docker-compose.production.yml` sets a fixed
`container_name`, and Compose refuses to start more than one container from a service
that has one. Scaling to multiple instances requires removing that fixed name — and the
fixed `"8034:8034"` host port publish, which would also fail with more than one replica
(only one container can bind a given host port). Traffic to replicas would need to go
through Traefik service discovery instead of the published host port, and anything that
depends on the literal container name (health checks, Traefik labels) needs adjusting
too, before `--scale` will work.

### Rollback
Same pattern as The Spark — redeploy the previous commit/tag via `docker compose up -d --build`
or re-run the prior successful Forgejo Actions job.

### Success criteria
Queue depth returns to baseline, `/health` green for 3 consecutive checks.

---

## RUNBOOK: Infinity (OAuth2/OIDC)
**Owner:** The Guardian (Anchor: Orb of Orisis) · **SLA:** 99.95% · **CriticalityCode:** CRT-001
**Service/App IDs:** `SRV-INF-001` / `APP-INF-001`
**Hard dependency:** `SRV-VOID-001` — Infinity cannot sign tokens if it can't reach the vault.

### Token-issuance failure
```bash
# 1. Confirm vault reachable first — this is almost always the real cause
curl -s http://localhost:8038/health

# 2. Check the auth service itself
curl -s http://localhost:8005/health

# 3. Restart if 1 and 2 are healthy but tokens still fail
docker compose -f docker-compose.production.yml restart infinity-auth
```
Infinity only implements the `authorization_code` grant (with PKCE) at `POST /auth/token` —
there is no `/oauth2/token` route and no `client_credentials` support. Its `refresh_token`
grant is currently broken in the application code (the token endpoint queries a
`refresh_tokens` table that is never created), so treat refresh failures as a known issue
rather than an operational incident.

### Threat response (Cryptex/Renik alert)
1. Confirm alert in the security channel your team uses for Cryptex notifications.
2. Block the source at the firewall layer defined in `14_firewalls.csv` (`FW-002`/`FW-003` govern this network).
3. Revoke sessions/tokens for the affected principal via Infinity's admin API (`src/auth/zero_trust.py` risk-scoring path).
4. Log the action — Observatory picks it up automatically via audit middleware.

### Success criteria
`/auth/token` issues an access token via the authorization_code grant. Note the
authorization_code path (`workers/infinity-auth/router.py` `token_endpoint`) currently
returns an opaque `secrets.token_urlsafe(32)` string, not a signed JWT — only the
refresh path builds a JWT via `jose.jwt.encode`. Verify success against the actual
token contract (a 200 response with a non-empty `access_token`), not by attempting to
decode it as a JWT. No repeated auth failures in `docker compose logs infinity-auth`.

---

## RUNBOOK: The Void (Secrets Vault)
**Owner:** Prometheus · **SLA:** 99.95% · **CriticalityCode:** CRT-001 · **StatusCode:** STS-002 (Building — in-flight CF Worker → self-hosted migration)
**Service/App IDs:** `SRV-VOID-001` / `APP-VOID-001`
**Hard dependency:** `SRV-INF-001` (caller identity verification before secret release)

### Health check
```bash
curl -s http://localhost:8038/health
docker inspect -f '{{.State.Health.Status}}' vault-service-worker
```
This is the highest-blast-radius service in the anchor set — nearly every other
service has a hard dependency on it. Treat any Void incident as SEV-1 by default.

### Secret rotation
1. Identify secrets older than the rotation window via the vault admin API.
2. Generate a new value: `openssl rand -base64 32 | tr -d "=+/" | cut -c1-32`.
3. Write the new version to the vault, update consuming services' env, then restart them
   one at a time (Infinity, The Spark, The Digital Grid, The Observatory) so no service is
   ever running with a stale secret past the rotation window.
4. Archive the previous secret version rather than deleting it immediately.

### Backup & recovery
Secrets values themselves stay AES-GCM encrypted at rest; the Shamir unseal keys must
**never** be stored in the same backup as the encrypted secrets database (`STO-VOID-001`).
Recovery requires a quorum of unseal key holders per the Shamir scheme — there is no
single-operator recovery path by design.

### Success criteria
`/health` green; a round-trip secret write/read succeeds; dependent services (Infinity,
Spark, Grid, Observatory) reconnect without manual restart once Void is healthy again.

---

## RUNBOOK: The Workshop (Forgejo CI/CD)
**Owner:** Larry Lowhammer · **SLA:** 99.9% · **CriticalityCode:** CRT-001

**See `deploy/forgejo/RUNBOOK.md` — this is the authoritative, topology-aware recovery
runbook for The Workshop, backed by `deploy/forgejo/recover.sh` and
`deploy/forgejo/the-workshop.service`.** Do not duplicate or fork that procedure here;
this entry exists only to complete the six-anchor-service set for cross-reference from
`15_dependencies.csv` and `06_service_deployments.csv`.

---

## RUNBOOK: The Observatory (Audit & Monitoring)
**Owner:** Norman Hawkins · **SLA:** 99.9% · **CriticalityCode:** CRT-001
**Service/App IDs:** `SRV-OBS-001` / `APP-OBS-001`
**Hard dependency:** `SRV-INF-001` · `DB-OBS-001` is not currently used at runtime — see caveat below

### Audit ingestion failure
```bash
docker inspect -f '{{.State.Health.Status}}' tranc3-observatory

# Restart the observatory worker
docker compose -f docker-compose.production.yml restart observatory
```
**Known gap:** `OBSERVATORY_DB_PATH` is configured but the worker never actually opens or
writes to it today — audit/metric events live only in an in-process `deque` (see
`workers/observatory/service.py`) and are lost on every restart. There is currently no
durable database to check the health of; "ingestion failure" here really means the
in-memory buffer isn't being populated, which a process restart usually clears. Treat any
retention/compliance claim about this data surviving a restart as aspirational until
persistence is implemented.
Also check Loki/Promtail (`tranc3-loki`, `tranc3-promtail` containers) if the symptom is
missing *log* data specifically rather than missing *audit* data — they are separate
pipelines feeding the same dashboards.

### Long-term archive check
Audit logs carry a 10-year retention requirement (`07_environments.csv`,
`17_configuration_baseline.csv`). Verify the daily archive job actually ran rather than
assuming it did:
```bash
docker compose -f docker-compose.production.yml logs --since 24h observatory | grep -i archive
```

### Success criteria
Recent audit log rows have timestamps < 1 minute old; Grafana/Loki dashboards show fresh
data; no backlog in the observatory worker's queue.

---

## Cross-cutting notes

- **No Kubernetes, no AWS.** This platform runs on Docker Compose + Traefik on a single
  production host (`SRV-CITADEL-01`) per `09_servers.csv`. Any inherited procedure that
  references `kubectl`, EKS, Route53, or RDS snapshots does not apply here and must be
  translated to `docker compose` / Traefik equivalents before use.
- **CI/CD is Forgejo-only.** Deploys run through `.forgejo/workflows/*.yml`
  (`deploy-fly.yml`, `deploy-self-hosted.yml`), never GitHub Actions.
- **Escalation order for any anchor service incident:** confirm The Void and Infinity are
  healthy first (nearly everything hard-depends on them per `15_dependencies.csv`) before
  investigating the reporting service itself.
