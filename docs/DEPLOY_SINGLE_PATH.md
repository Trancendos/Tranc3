# Deploy — one path (stop the fix loop)

## What went wrong before

Several deploy paths pointed at **different Fly app names** (`trancendos-backend` vs `tranc3-backend`). Code landed on **GitHub `main`** while **Forgejo** runs CI. The Cloud Agent cannot read Forgejo org secrets. `deploy_cloud.py` only looked at `FLY_API_TOKEN` in the shell, not `.env.production` or `flyctl login`.

## Canonical production URLs

| Service | Fly app | Health |
|---------|---------|--------|
| API | `tranc3-backend` | https://tranc3-backend.fly.dev/health |
| Bots | `trancendos-bots` | https://trancendos-bots.fly.dev/health |

## Set credentials once (never in chat)

Pick **one**:

1. **`.env.production`** (gitignored) — add a line:
   `FLY_API_TOKEN=...`  
   Then: `py -3.12 scripts\deploy_cloud.py`

2. **`flyctl auth login`** on your PC — token in `%USERPROFILE%\.fly\config.yml`  
   Deploy script reads it automatically.

3. **Forgejo** — org secret `FLY_API_TOKEN` + push `main` to **The Workshop** (not GitHub only).  
   Workflow: **Deploy to Fly.io** (targets `tranc3-backend`).

4. **Cursor Cloud Agent** — environment secret `FLY_API_TOKEN` (new run after saving).

## After `main` changes

```cmd
cd %USERPROFILE%\Documents\Tranc3
git pull origin main
py -3.12 scripts\deploy_cloud.py
```

Or trigger Forgejo **Deploy to Fly.io** on `main`.

## Verify

- https://tranc3-backend.fly.dev/health → 200
- https://tranc3-backend.fly.dev/admin-os/health → 200
- https://tranc3-backend.fly.dev/dashboard/infinity-admin-os.html
