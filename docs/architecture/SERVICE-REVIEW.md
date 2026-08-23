# Platform Service Review

Generated from repo state at `8909268`. Regenerate with
`python scripts/build_service_review.py`; CI checks freshness with `--check`.

## Where the estate stands

| State | Count | Meaning |
|---|---:|---|
| **INFRA** | 86 | third-party image — counted, not checked |
| **NEEDS_WORK** | 67 | deployed, but at least one connection check fails |
| **ORPHANED** | 3 | real code and a Dockerfile, nothing builds it |
| **RUNNING** | 21 | deployed and every applicable check passes |

## What is failing, by check

| Check | Services | Which |
|---|---:|---|
| imports_resolve | 65 | `analytics-service`, `artifactory-service`, `audit-service`, `basement`, `blender-worker`, `cache-service`, `cdn-service`, `chaos-party` … +57 |
| telemetry_reaches | 34 | `audit-service`, `blender-worker`, `cdn-service`, `config-service`, `cron-service`, `deepagents-orchestrator-service`, `email-service`, `ffmpeg-worker` … +26 |
| not built by any compose service | 3 | `dimensional-nexus-service`, `gateway-service`, `optional-services-health` |

## Dimensionals — what is in scope, what is not

`Dimensional/` holds 105 modules. 
A concern is *in scope* when the shared core owns it; a *candidate* when two or
more services solve it independently; *out of scope* when exactly one service
does, because that is not shared code, it is that service's job.

| Concern | In core | Services doing it themselves | Verdict |
|---|:---:|---:|---|
| internal-secret verification | yes | 41 | IN SCOPE, NOT REACHING — in the core, but 41 service(s) implement it anyway |
| OTel worker setup | no | 35 | CANDIDATE — 35 services implement it independently, core has nothing |
| log sanitisation | yes | 2 | IN SCOPE, NOT REACHING — in the core, but 2 service(s) implement it anyway |
| path traversal guard | yes | 2 | IN SCOPE, NOT REACHING — in the core, but 2 service(s) implement it anyway |
| circuit breaker | yes | 1 | IN SCOPE, NOT REACHING — in the core, but 1 service(s) implement it anyway |
| token-bucket rate limit | no | 0 | ABSENT — nothing implements it |
| JWT verify | yes | 0 | IN SCOPE — in the core, nothing duplicating it |

### Why `internal-secret verification` is the first one to fix

41 services each write their own check, and they have not stayed
the same. `Dimensional/security.py` already exposes a constant-time compare
that none of them import.

| Behaviour | Services |
|---|---:|
| constant-time (`compare_digest`) | 0 |
| timing-unsafe (`==` / `!=`) | 1 |
| **fails open when the secret is unset** | 0 |

## NEEDS_WORK

### `analytics-service`
- **imports_resolve** — 1 unguarded, 0 guarded, 0 vendored
  - `workers/analytics-service/worker.py:35 Dimensional.service_auth_fastapi`

### `artifactory-service`
- **imports_resolve** — 1 unguarded, 0 guarded, 0 vendored
  - `workers/artifactory-service/worker.py:30 Dimensional.service_auth_fastapi`

### `audit-service`
- **imports_resolve** — 1 unguarded, 1 guarded, 0 vendored
  - `workers/audit-service/worker.py:43 Dimensional.service_auth_fastapi`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `basement`
- **imports_resolve** — 1 unguarded, 0 guarded, 0 vendored
  - `workers/basement/worker.py:25 Dimensional.service_auth_fastapi`

### `blender-worker`
- **imports_resolve** — 1 unguarded, 1 guarded, 0 vendored
  - `workers/blender-worker/worker.py:29 Dimensional.service_auth_fastapi`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `cache-service`
- **imports_resolve** — 1 unguarded, 0 guarded, 0 vendored
  - `workers/cache-service/worker.py:36 Dimensional.service_auth_fastapi`

### `cdn-service`
- **imports_resolve** — 1 unguarded, 1 guarded, 0 vendored
  - `workers/cdn-service/worker.py:31 Dimensional.service_auth_fastapi`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `chaos-party`
- **imports_resolve** — 1 unguarded, 0 guarded, 0 vendored
  - `workers/chaos-party/worker.py:27 Dimensional.service_auth_fastapi`

### `config-service`
- **imports_resolve** — 1 unguarded, 1 guarded, 0 vendored
  - `workers/config-service/worker.py:27 Dimensional.service_auth_fastapi`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `cron-service`
- **imports_resolve** — 1 unguarded, 1 guarded, 0 vendored
  - `workers/cron-service/worker.py:45 Dimensional.service_auth_fastapi`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `cryptex`
- **imports_resolve** — 1 unguarded, 0 guarded, 0 vendored
  - `workers/cryptex/router.py:12 Dimensional.service_auth_fastapi`

### `deepagents-orchestrator-service`
- **imports_resolve** — 1 unguarded, 1 guarded, 0 vendored
  - `workers/deepagents-orchestrator-service/worker.py:30 Dimensional.service_auth_fastapi`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `devocity`
- **imports_resolve** — 1 unguarded, 0 guarded, 0 vendored
  - `workers/devocity/worker.py:25 Dimensional.service_auth_fastapi`

### `dspy-service`
- **imports_resolve** — 1 unguarded, 0 guarded, 0 vendored
  - `workers/dspy-service/worker.py:28 Dimensional.service_auth_fastapi`

### `email-service`
- **imports_resolve** — 1 unguarded, 1 guarded, 0 vendored
  - `workers/email-service/worker.py:33 Dimensional.service_auth_fastapi`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `fabulousa-service`
- **imports_resolve** — 1 unguarded, 0 guarded, 0 vendored
  - `workers/fabulousa-service/worker.py:28 Dimensional.service_auth_fastapi`

### `ffmpeg-worker`
- **imports_resolve** — 1 unguarded, 1 guarded, 0 vendored
  - `workers/ffmpeg-worker/worker.py:23 Dimensional.service_auth_fastapi`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `files-service`
- **imports_resolve** — 1 unguarded, 0 guarded, 0 vendored
  - `workers/files-service/worker.py:37 Dimensional.service_auth_fastapi`

### `gbrain-bridge`
- **imports_resolve** — 1 unguarded, 1 guarded, 0 vendored
  - `workers/gbrain-bridge/worker.py:42 Dimensional.service_auth_fastapi`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `geo-service`
- **imports_resolve** — 1 unguarded, 1 guarded, 0 vendored
  - `workers/geo-service/worker.py:34 Dimensional.service_auth_fastapi`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `haystack-service`
- **imports_resolve** — 1 unguarded, 0 guarded, 0 vendored
  - `workers/haystack-service/worker.py:27 Dimensional.service_auth_fastapi`

### `health-aggregator`
- **imports_resolve** — 1 unguarded, 2 guarded, 0 vendored
  - `workers/health-aggregator/worker.py:31 Dimensional.service_auth_fastapi`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `identity-service`
- **imports_resolve** — 1 unguarded, 1 guarded, 0 vendored
  - `workers/identity-service/worker.py:25 Dimensional.service_auth_fastapi`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `imaginarium`
- **imports_resolve** — 2 unguarded, 0 guarded, 0 vendored
  - `workers/imaginarium/main.py:14 Dimensional.service_auth_fastapi`
  - `workers/imaginarium/worker.py:25 Dimensional.service_auth_fastapi`

### `imind`
- **imports_resolve** — 1 unguarded, 0 guarded, 0 vendored
  - `workers/imind/worker.py:26 Dimensional.service_auth_fastapi`

### `infinity-ai`
- **imports_resolve** — 1 unguarded, 6 guarded, 0 vendored
  - `workers/infinity-ai/router.py:14 Dimensional.service_auth_fastapi`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `infinity-void`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `lab-service`
- **imports_resolve** — 1 unguarded, 0 guarded, 0 vendored
  - `workers/lab-service/router.py:13 Dimensional.service_auth_fastapi`

### `langchain-integration-service`
- **imports_resolve** — 1 unguarded, 1 guarded, 0 vendored
  - `workers/langchain-integration-service/worker.py:48 Dimensional.service_auth_fastapi`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `ledger-service`
- **imports_resolve** — 1 unguarded, 1 guarded, 0 vendored
  - `workers/ledger-service/worker.py:43 Dimensional.service_auth_fastapi`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `library-service`
- **imports_resolve** — 1 unguarded, 0 guarded, 0 vendored
  - `workers/library-service/router.py:12 Dimensional.service_auth_fastapi`

### `litellm-service`
- **imports_resolve** — 1 unguarded, 0 guarded, 0 vendored
  - `workers/litellm-service/worker.py:42 Dimensional.service_auth_fastapi`

### `llamaindex-service`
- **imports_resolve** — 1 unguarded, 0 guarded, 0 vendored
  - `workers/llamaindex-service/worker.py:28 Dimensional.service_auth_fastapi`

### `mlflow-service`
- **imports_resolve** — 1 unguarded, 1 guarded, 0 vendored
  - `workers/mlflow-service/worker.py:69 Dimensional.service_auth_fastapi`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `model-router-service`
- **imports_resolve** — 1 unguarded, 1 guarded, 0 vendored
  - `workers/model-router-service/worker.py:43 Dimensional.service_auth_fastapi`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `monitoring`
- **imports_resolve** — 2 unguarded, 1 guarded, 0 vendored
  - `workers/monitoring/worker.py:43 Dimensional.service_auth`
  - `workers/monitoring/worker.py:44 Dimensional.service_auth_fastapi`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `notifications`
- **imports_resolve** — 1 unguarded, 1 guarded, 0 vendored
  - `workers/notifications/worker.py:766 Dimensional.service_auth_fastapi`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `observatory`
- **imports_resolve** — 1 unguarded, 0 guarded, 0 vendored
  - `workers/observatory/router.py:12 Dimensional.service_auth_fastapi`

### `orders-service`
- **imports_resolve** — 1 unguarded, 1 guarded, 0 vendored
  - `workers/orders-service/worker.py:26 Dimensional.service_auth_fastapi`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `payments-service`
- **imports_resolve** — 1 unguarded, 1 guarded, 0 vendored
  - `workers/payments-service/worker.py:25 Dimensional.service_auth_fastapi`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `products-service`
- **imports_resolve** — 1 unguarded, 1 guarded, 0 vendored
  - `workers/products-service/worker.py:25 Dimensional.service_auth_fastapi`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `queue-service`
- **imports_resolve** — 1 unguarded, 1 guarded, 0 vendored
  - `workers/queue-service/worker.py:28 Dimensional.service_auth_fastapi`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `rate-limit-service`
- **imports_resolve** — 1 unguarded, 1 guarded, 0 vendored
  - `workers/rate-limit-service/worker.py:27 Dimensional.service_auth_fastapi`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `resonate`
- **imports_resolve** — 1 unguarded, 0 guarded, 0 vendored
  - `workers/resonate/worker.py:25 Dimensional.service_auth_fastapi`

### `sashas-photo-studio`
- **imports_resolve** — 1 unguarded, 0 guarded, 0 vendored
  - `workers/sashas-photo-studio/worker.py:27 Dimensional.service_auth_fastapi`

### `search-service`
- **imports_resolve** — 1 unguarded, 1 guarded, 0 vendored
  - `workers/search-service/worker.py:28 Dimensional.service_auth_fastapi`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `skills-benchmark-service`
- **imports_resolve** — 1 unguarded, 1 guarded, 0 vendored
  - `workers/skills-benchmark-service/worker.py:43 Dimensional.service_auth_fastapi`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `sms-service`
- **imports_resolve** — 1 unguarded, 1 guarded, 0 vendored
  - `workers/sms-service/worker.py:32 Dimensional.service_auth_fastapi`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `storage-service`
- **imports_resolve** — 1 unguarded, 0 guarded, 0 vendored
  - `workers/storage-service/worker.py:41 Dimensional.service_auth_fastapi`

### `taimra`
- **imports_resolve** — 1 unguarded, 0 guarded, 0 vendored
  - `workers/taimra/worker.py:24 Dimensional.service_auth_fastapi`

### `tateking`
- **imports_resolve** — 2 unguarded, 0 guarded, 0 vendored
  - `workers/tateking/main.py:33 Dimensional.service_auth_fastapi`
  - `workers/tateking/worker.py:26 Dimensional.service_auth_fastapi`

### `the-academy`
- **imports_resolve** — 1 unguarded, 0 guarded, 0 vendored
  - `workers/the-academy/worker.py:24 Dimensional.service_auth_fastapi`

### `the-dutchy`
- **imports_resolve** — 1 unguarded, 0 guarded, 0 vendored
  - `workers/the-dutchy/worker.py:26 Dimensional.service_auth_fastapi`

### `the-grid`
- **imports_resolve** — 1 unguarded, 0 guarded, 0 vendored
  - `workers/the-grid/router.py:13 Dimensional.service_auth_fastapi`

### `the-lab`
- **imports_resolve** — 2 unguarded, 0 guarded, 0 vendored
  - `workers/the-lab/main.py:26 Dimensional.service_auth_fastapi`
  - `workers/the-lab/worker.py:27 Dimensional.service_auth_fastapi`

### `the-studio`
- **imports_resolve** — 1 unguarded, 0 guarded, 0 vendored
  - `workers/the-studio/worker.py:25 Dimensional.service_auth_fastapi`

### `topology-service`
- **imports_resolve** — 1 unguarded, 1 guarded, 0 vendored
  - `workers/topology-service/worker.py:44 Dimensional.service_auth_fastapi`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `tranc3-ai`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `tranceflow`
- **imports_resolve** — 2 unguarded, 0 guarded, 0 vendored
  - `workers/tranceflow/router.py:12 Dimensional.service_auth_fastapi`
  - `workers/tranceflow/worker.py:25 Dimensional.service_auth_fastapi`

### `tranquility`
- **imports_resolve** — 1 unguarded, 0 guarded, 0 vendored
  - `workers/tranquility/worker.py:25 Dimensional.service_auth_fastapi`

### `triposr-worker`
- **imports_resolve** — 1 unguarded, 1 guarded, 0 vendored
  - `workers/triposr-worker/worker.py:31 Dimensional.service_auth_fastapi`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `turings-hub-service`
- **imports_resolve** — 1 unguarded, 1 guarded, 0 vendored
  - `workers/turings-hub-service/worker.py:55 Dimensional.service_auth_fastapi`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `vault-service`
- **imports_resolve** — 1 unguarded, 1 guarded, 0 vendored
  - `workers/vault-service/worker.py:48 Dimensional.service_auth_fastapi`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `vrar3d`
- **imports_resolve** — 2 unguarded, 0 guarded, 0 vendored
  - `workers/vrar3d/router.py:13 Dimensional.service_auth_fastapi`
  - `workers/vrar3d/worker.py:25 Dimensional.service_auth_fastapi`

### `warp-radio`
- **imports_resolve** — 1 unguarded, 0 guarded, 0 vendored
  - `workers/warp-radio/worker.py:26 Dimensional.service_auth_fastapi`

### `warp-tunnel`
- **imports_resolve** — 1 unguarded, 0 guarded, 0 vendored
  - `workers/warp-tunnel/worker.py:28 Dimensional.service_auth_fastapi`

### `workflow-engine-service`
- **imports_resolve** — 1 unguarded, 1 guarded, 0 vendored
  - `workers/workflow-engine-service/worker.py:40 Dimensional.service_auth_fastapi`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

## ORPHANED

### `dimensional-nexus-service`
- **not built by any compose service** — 

### `gateway-service`
- **not built by any compose service** — 

### `optional-services-health`
- **not built by any compose service** — 

## Running clean

21 services pass every applicable check:

`api-gateway`, `backup-service`, `bullmq-queue-service`, `cranbania`, `hive-service`, `ice-box-service`, `infinity-admin`, `infinity-auth`, `infinity-bridge`, `infinity-one`, `infinity-portal`, `infinity-shards`, `infinity-ws`, `nexus-ws-rs`, `rate-limit-service-rs`, `remotion-render-service`, `sentinel-station-service`, `swarm-coordinator-service`, `tranc3-backend`, `users-service`, `vault-service-rs`

