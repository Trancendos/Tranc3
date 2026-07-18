# Cloudflare Workers — Deploy

Cloudflare deploys are **data-driven and change-aware**, and currently run through
**two** CI systems in parallel:

- **The Workshop** (self-hosted Forgejo) — `.forgejo/workflows/deploy-cloudflare.yml`.
  This is the platform's documented CI/CD sovereignty path (see `CLAUDE.md`) and
  remains the long-term system of record.
- **GitHub Actions** — `.github/workflows/deploy-cloudflare.yml`. Added as a
  **deliberate, interim, cloud-only-phase measure**: the platform is currently
  running cloud-only (Cloudflare Workers + Fly.io), and The Workshop runner itself
  depends on the self-hosted host that this phase explicitly defers standing back
  up. Without a second trigger path, a cloud-only deploy would have no way to fire.
  This diverges from the "NO GitHub Actions" principle by explicit operator
  decision; retire the GitHub Actions copy once The Workshop is back and hybrid/local
  is reactivated, rather than maintaining both indefinitely.

Both workflows share the same planner script and manifest below, so a worker only
needs to be onboarded once — it deploys from whichever CI system currently has
working credentials and connectivity.

> **Note on direction:** these Cloudflare Workers are **legacy** and are being
> migrated to the self-hosted stack (Traefik + Python workers — see
> `CF_WORKER_MIGRATION_ROADMAP.md`). This pipeline keeps the edge workers
> deployable and safe to operate *during* that migration; it is not an
> endorsement of adding new CF Workers.

## Moving parts

| File | Role |
|---|---|
| `cloudflare/deploy-manifest.json` | Single source of truth — every deployable worker (`name` = its `wrangler.toml` name, `dir` = its folder, optional `health_url`). |
| `.forgejo/scripts/cf_deploy_plan.py` | Computes *which* workers to deploy from the changed files (push) or the dispatch inputs, and emits the CI matrix. Shared by both workflow copies below. |
| `.forgejo/workflows/deploy-cloudflare.yml` | The Workshop (Forgejo) workflow: preflight (credential guard + plan) → matrix deploy → advisory health poll → summary. |
| `.github/workflows/deploy-cloudflare.yml` | GitHub Actions workflow — same logic, cloud-only-phase interim trigger path. Keep in sync with the Forgejo copy. |

## How it triggers

- **On push to `main`** touching `cloudflare/**` (or the workflow/planner): only the
  workers whose own `cloudflare/<dir>/` tree changed are deployed. If the workflow
  or the manifest itself changed, *all* workers deploy (behaviour may have changed
  for all).
- **Manually** via `workflow_dispatch` with inputs:
  - `worker`: a name from the manifest, or `all` (default).
  - `force`: `true` to deploy even when no matching files changed.

## Credentials

Each workflow reads two secrets; without them it **skips** cleanly (a warning, not a
failure), so a runner that isn't yet configured doesn't red-X every push:

- `CF_API_TOKEN` — Cloudflare API token with Workers edit scope.
- `CF_ACCOUNT_ID` — `<your-cloudflare-account-id>` (the `account_id` in each worker's `wrangler.toml`).

Set them as org or repo secrets in **Forgejo** (Settings → Actions → Secrets) for
The Workshop's copy, and separately as **GitHub repo secrets** (Settings → Secrets
and variables → Actions) for the GitHub Actions copy — the two CI systems do not
share a secret store.

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

## Not covered here (yet)

- The legacy `*-rotation` workers (`notifications-`, `queue-`, `search-`, `storage-rotation`)
  are omitted from the manifest until each carries a **committed, reviewed `package-lock.json`**.
  (Generating one via `wrangler ^4` pulls `wrangler`'s optional `@img/sharp-*` platform binaries
  into the lock, which the license scanner flags as LGPL — build-tool-only and never shipped in
  the deployed worker, but call it out before adding these locks.) To onboard one: commit its lock,
  then add its manifest line.
- `cloudflare/pages/` (`trancendos-frontend`) is a Cloudflare **Pages** project with a different
  lifecycle (`wrangler pages deploy <build-dir>`) and no `package.json`; intentionally excluded
  from this Workers matrix.
