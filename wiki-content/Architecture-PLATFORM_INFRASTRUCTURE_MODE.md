# Platform infrastructure modes

You control where compute and storage run with **one setting**. Default is **CLOUD_ONLY** until your Citadel server is ready.

For merge history, superseded PRs (#84–#89), and branch cleanup commands, see [BRANCH_CONSOLIDATION.md](Historical-BRANCH_CONSOLIDATION).

| Mode | When to use | Citadel Docker | AI rotation |
|------|-------------|----------------|-------------|
| **CLOUD_ONLY** | Now — CF Workers, Fly, Supabase, Upstash | Not required | `zero_cost_cloud` + auto-rotate |
| **HYBRID** | Migration | Optional (`CITADEL_LOCAL_STACK=true`) | `zero_cost_full` + auto-rotate |
| **LOCAL_ONLY** | Self-hosted server ready | `citadel_deploy_all.py --local` | `zero_cost_full` |

## Environment

```bash
PLATFORM_INFRA_MODE=CLOUD_ONLY   # default
# legacy alias still works:
SYSTEM_MODE=CLOUD_ONLY
```

Adaptive (runs on API startup):

```bash
ADAPTIVE_ROTATION_ENABLED=true
ADAPTIVE_ROTATION_CHAIN=zero_cost_cloud
ADAPTIVE_CLOUD_AUTO_ROTATE=true
ADAPTIVE_CLOUD_AUTO_ROTATE_SECONDS=180
PROACTIVE_ORCHESTRATOR_ENABLED=true
```

## API

- `GET /adaptive/mode` — current mode, chain, auto-rotate flag
- `GET /adaptive/status` — rotator + proactive orchestrator
- `POST /adaptive/mode` — switch mode for this process (persist in `.env`)

## Deploy (CLOUD_ONLY — Fly.io)

From repo root, with `FLY_API_TOKEN` and Fly app secrets configured:

```bash
export FLY_API_TOKEN=...
python scripts/deploy_cloud.py
```

```cmd
set FLY_API_TOKEN=your_token
scripts\deploy_cloud.bat
```

Apps: `tranc3-backend` (repo root), `trancendos-bots` (`tranc3-bots/`). Does **not** start Citadel Docker.

## Deploy script behaviour (local Citadel later)

From repo root:

```cmd
REM Windows — quality gate only (CLOUD_ONLY default)
scripts\citadel_deploy_all.bat --gate-only
```

```bash
# Same on Linux/macOS
python scripts/citadel_deploy_all.py --gate-only
```

When **LOCAL_ONLY** and Docker are ready:

```bash
PLATFORM_INFRA_MODE=LOCAL_ONLY python scripts/citadel_deploy_all.py --local
```

**Do not** run full Citadel compose in CLOUD_ONLY unless you explicitly pass `--local`.

## Switching later

1. Set `PLATFORM_INFRA_MODE=LOCAL_ONLY` in `.env` / `.env.production`.
2. Run `scripts/citadel_deploy_all.py --local` (or `make citadel-deploy-all` with local mode).
3. Follow `deploy/traefik/DNS_CUTOVER.md` when cutting DNS to Citadel.

Until then, stay on **CLOUD_ONLY** — cloud auto-rotation and proactive systems are designed for that path.

For what rotates today vs OCI/Azure/GCP hosting plans, see [ADAPTIVE_PLATFORM_ROTATION.md](Strategy-ADAPTIVE_PLATFORM_ROTATION).
