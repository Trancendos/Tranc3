# Cloudflare Workers — Deploy

Cloudflare deploys run through **The Workshop** (Forgejo CI), not GitHub Actions,
per the platform's CI/CD sovereignty principle (see `CLAUDE.md`). The pipeline is
data-driven and change-aware.

> **Note on direction:** these Cloudflare Workers are **legacy** and are being
> migrated to the self-hosted stack (Traefik + Python workers — see
> `CF_WORKER_MIGRATION_ROADMAP.md`). This pipeline keeps the edge workers
> deployable and safe to operate *during* that migration; it is not an
> endorsement of adding new CF Workers.

## Moving parts

| File | Role |
|---|---|
| `cloudflare/deploy-manifest.json` | Single source of truth — every deployable worker (`name` = its `wrangler.toml` name, `dir` = its folder, optional `health_url`). |
| `.forgejo/scripts/cf_deploy_plan.py` | Computes *which* workers to deploy from the changed files (push) or the dispatch inputs, and emits the CI matrix. |
| `.forgejo/workflows/deploy-cloudflare.yml` | The workflow: preflight (credential guard + plan) → matrix deploy → advisory health poll → summary. |

## How it triggers

- **On push to `main`** touching `cloudflare/**` (or the workflow/planner): only the
  workers whose own `cloudflare/<dir>/` tree changed are deployed. If the workflow
  or the manifest itself changed, *all* workers deploy (behaviour may have changed
  for all).
- **Manually** via `workflow_dispatch` with inputs:
  - `worker`: a name from the manifest, or `all` (default).
  - `force`: `true` to deploy even when no matching files changed.

## Credentials (one-time, in The Workshop)

The workflow reads two secrets; without them it **skips** cleanly (a warning, not a
failure), so a runner that isn't yet configured doesn't red-X every push:

- `CF_API_TOKEN` — Cloudflare API token with Workers edit scope.
- `CF_ACCOUNT_ID` — `<your-cloudflare-account-id>` (the `account_id` in each worker's `wrangler.toml`).

Set them as org or repo secrets in Forgejo (Settings → Actions → Secrets).

## Onboarding a new worker

1. Add its folder under `cloudflare/<dir>/` with a `wrangler.toml`, a `package.json`
   pinning `wrangler` (`^4.102.0` fleet-wide), **and a committed `package-lock.json`**
   (`npm install --package-lock-only`). The deploy uses lockfile-only `npm ci` for
   reproducibility — a worker without a lock will fail the deploy by design.
2. Add one line to `cloudflare/deploy-manifest.json`:
   ```json
   { "name": "<wrangler-name>", "dir": "<folder>", "health_url": "https://<name>.luminous-aimastermind.workers.dev/health" }
   ```
   Leave `health_url` as `""` to skip the post-deploy health poll.

No workflow edit is required — the matrix picks it up automatically.

## Health polls

After each `wrangler deploy`, if the worker has a `health_url`, the workflow polls it
(5 tries, backoff). This is **advisory**: a non-200 emits a warning but does not fail
the job, because the authoritative success signal is `wrangler deploy`'s exit code.
Fill in verified `health_url`s over time to turn these into real post-deploy signals.

## Manual deploy from a workstation (fallback)

If The Workshop runner is down, deploy a single worker from a machine that has the
Cloudflare token:

```bash
cd cloudflare/<dir>
export CLOUDFLARE_API_TOKEN=...        # Workers-edit-scoped token
export CLOUDFLARE_ACCOUNT_ID=<your-cloudflare-account-id>   # the account_id in wrangler.toml
npm ci && npx wrangler deploy
```

## Not covered here

`cloudflare/pages/` (`trancendos-frontend`) is a Cloudflare **Pages** project with a
different lifecycle (`wrangler pages deploy <build-dir>`) and no `package.json`; it is
intentionally excluded from this Workers matrix.
