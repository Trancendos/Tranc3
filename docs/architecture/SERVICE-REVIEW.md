# Platform Service Review

Generated from repo state at `ec8650ee`. Regenerate with 
`python scripts/build_service_review.py`; CI checks freshness with `--check`.

## Where the estate stands

| State | Count | Meaning |
|---|---:|---|
| **INFRA** | 86 | third-party image — counted, not checked |
| **NEEDS_WORK** | 34 | deployed, but at least one connection check fails |
| **ORPHANED** | 3 | real code and a Dockerfile, nothing builds it |
| **RUNNING** | 54 | deployed and every applicable check passes |

## What is failing, by check

| Check | Services | Which |
|---|---:|---|
| telemetry_reaches | 34 | `audit-service`, `blender-worker`, `cdn-service`, `config-service`, `cron-service`, `deepagents-orchestrator-service`, `email-service`, `ffmpeg-worker` … +26 |
| not built by any compose service | 3 | `dimensional-nexus-service`, `gateway-service`, `optional-services-health` |

## Dimensionals — what is in scope, what is not

`Dimensional/` holds 104 modules. 
A concern is *in scope* when the shared core owns it; a *candidate* when two or
more services solve it independently; *out of scope* when exactly one service
does, because that is not shared code, it is that service's job.

| Concern | In core | Services doing it themselves | Verdict |
|---|:---:|---:|---|
| internal-secret verification | yes | 42 | IN SCOPE, NOT REACHING — in the core, but 42 service(s) implement it anyway |
| OTel worker setup | no | 35 | CANDIDATE — 35 services implement it independently, core has nothing |
| log sanitisation | yes | 2 | IN SCOPE, NOT REACHING — in the core, but 2 service(s) implement it anyway |
| path traversal guard | yes | 2 | IN SCOPE, NOT REACHING — in the core, but 2 service(s) implement it anyway |
| circuit breaker | yes | 1 | IN SCOPE, NOT REACHING — in the core, but 1 service(s) implement it anyway |
| token-bucket rate limit | no | 0 | ABSENT — nothing implements it |
| JWT verify | yes | 0 | IN SCOPE — in the core, nothing duplicating it |

### Why `internal-secret verification` is the first one to fix

42 services each write their own check, and they have not stayed
the same. `Dimensional/security.py` already exposes a constant-time compare
that none of them import.

| Behaviour | Services |
|---|---:|
| constant-time (`compare_digest`) | 41 |
| timing-unsafe (`==` / `!=`) | 0 |
| **fails open when the secret is unset** | 0 |

## NEEDS_WORK

### `audit-service`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `blender-worker`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `cdn-service`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `config-service`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `cron-service`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `deepagents-orchestrator-service`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `email-service`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `ffmpeg-worker`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `gbrain-bridge`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `geo-service`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `health-aggregator`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `identity-service`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `infinity-ai`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `infinity-void`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `langchain-integration-service`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `ledger-service`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `mlflow-service`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `model-router-service`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `monitoring`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `notifications`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `orders-service`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `payments-service`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `products-service`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `queue-service`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `rate-limit-service`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `search-service`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `skills-benchmark-service`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `sms-service`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `topology-service`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `tranc3-ai`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `triposr-worker`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `turings-hub-service`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `vault-service`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

### `workflow-engine-service`
- **telemetry_reaches** — import is guarded but src/ is absent — telemetry silently off

## ORPHANED

### `dimensional-nexus-service`
- **not built by any compose service** — 

### `gateway-service`
- **not built by any compose service** — 

### `optional-services-health`
- **not built by any compose service** — 

## Running clean

54 services pass every applicable check:

`analytics-service`, `api-gateway`, `artifactory-service`, `backup-service`, `basement`, `bullmq-queue-service`, `cache-service`, `chaos-party`, `cranbania`, `cryptex`, `devocity`, `dspy-service`, `fabulousa-service`, `files-service`, `haystack-service`, `hive-service`, `ice-box-service`, `imaginarium`, `imind`, `infinity-admin`, `infinity-auth`, `infinity-bridge`, `infinity-one`, `infinity-portal`, `infinity-shards`, `infinity-ws`, `lab-service`, `library-service`, `litellm-service`, `llamaindex-service`, `nexus-ws-rs`, `observatory`, `rate-limit-service-rs`, `remotion-render-service`, `resonate`, `sashas-photo-studio`, `sentinel-station-service`, `storage-service`, `swarm-coordinator-service`, `taimra`, `tateking`, `the-academy`, `the-dutchy`, `the-grid`, `the-lab`, `the-studio`, `tranc3-backend`, `tranceflow`, `tranquility`, `users-service`, `vault-service-rs`, `vrar3d`, `warp-radio`, `warp-tunnel`

