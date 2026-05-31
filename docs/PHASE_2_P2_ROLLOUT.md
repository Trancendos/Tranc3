# Phase 2 — P2 rollout (after P0 live)

**Enter only when:** `make deploy-live` + `make monitor` show all P0/P1 UP on Citadel.

## Scope

- The Digital Grid (`the-grid` :8010)
- Commerce: `products-service`, `orders-service`, `payments-service`
- Files + identity: `files-service`, `identity-service`
- `health-aggregator`, `vault-service`, `gbrain-bridge`

## Deploy

```bash
DEPLOY_PROFILE=full ./scripts/deploy_live.sh
python3 scripts/wait_for_healthy.py --timeout 900
pytest tests/test_uat.py -v
```

## Exit criteria

- All P2 `/health` return 200 with `entity` block
- Gateway routes smoke-tested (`/api/products`, `/api/auth`)
- Grafana dashboards show P2 targets
