# GitHub Actions Secrets

Add these in: GitHub → Tranc3 repo → Settings → Secrets and variables → Actions

| Secret | Description | How to get it |
|--------|-------------|---------------|
| `CF_API_TOKEN` | Cloudflare API token for wrangler deploys | CF Dashboard → My Profile → API Tokens → Create Token → "Edit Cloudflare Workers" template |
| `FLY_API_TOKEN` | Fly.io deploy token | `fly tokens create deploy` (or Fly.io dashboard) |

Once secrets are added, every push to `main` auto-deploys.
To deploy from your phone: push any commit to main via the GitHub mobile app.
To trigger manually: GitHub → Actions → pick a workflow → "Run workflow".
