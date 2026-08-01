# Cloud-only go-live runbook

The canonical procedure to take Trancendos live **without The Citadel**.

`LIVE_DEPLOY.md` is the self-hosted path and is blocked on server funding.
`DNS_CUTOVER.md` describes migrating *away* from the cloud *to* the Citadel — the
opposite direction to this document. Neither describes going live on the surface the
platform can actually reach today, which is what this runbook covers.

**Scope.** Three surfaces, none of which need owned hardware:

| Surface | What runs there | Deploy path |
|---|---|---|
| Fly.io | `tranc3-backend` (FastAPI), `trancendos-bots` | `scripts/deploy_cloud.py` |
| Cloudflare Workers | `trancendos-api-gateway`, `tranc3-ai`, `infinity-void` | `cloudflare/deploy-manifest.json` → CI |
| Cloudflare Pages | `web/` frontend at trancendos.com | `frontend-build.yml` / `wrangler pages deploy` |

Everything else in `docker-compose.production.yml` — the ~80 self-hosted workers, Vault,
Prometheus, Grafana, Loki, IPFS — is **out of scope for cloud-only** and stays down until
the Citadel host exists. Cloud-only is a real, reachable production state, not a
degraded one; it is the mode `CLAUDE.md` names as the current default for every Location.

---

## 0. Preflight (no credentials needed)

Run from a plain checkout. This validates every artifact the deploy consumes — Fly app
names, worker manifests, lockfiles, wrangler config, frontend source — without docker,
network or secrets:

```bash
python scripts/cloud_preflight.py
```

`PASS` means the surface is deployable. Fix any `FAIL` before continuing; `WARN` is
advisory. Then run the code gate:

```bash
python scripts/deploy_cloud.py --gate-only
```

This runs `pre_deploy_quality_gate.py --cloud-only`, which deliberately skips the
compose validation that the Citadel path requires.

---

## 1. Credentials

Set these once. **Never paste tokens into a chat, a commit, or a PR.**

| Name | Where it goes | Notes |
|---|---|---|
| `FLY_API_TOKEN` | shell env, `.env.production` (gitignored), or `flyctl auth login` | https://fly.io/user/personal_access_tokens |
| `CF_API_TOKEN` | GitHub repo secret **and** Forgejo org secret | API token with the **Account → Workers Scripts → Edit** permission |
| `CF_ACCOUNT_ID` | GitHub repo secret **and** Forgejo org secret | `e0214028cb64d31232f5662548a55e4e` |

The two CI systems do not share a secret store — set Cloudflare secrets in both, or the
copy that lacks them skips cleanly (a warning, not a failure).

Fly app secrets, set once per app:

```bash
fly secrets set \
  SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')" \
  JWT_SECRET="$(python -c 'import secrets; print(secrets.token_hex(32))')" \
  AUDIT_SIGNING_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')" \
  DATABASE_URL="postgresql://..." \
  REDIS_URL="rediss://..." \
  ENVIRONMENT=production \
  ROLLOUT_STAGE=owner \
  ROLLOUT_INVITE_CODE="$(python -c 'import secrets; print(secrets.token_urlsafe(12))')" \
  --app tranc3-backend

fly secrets set \
  REDIS_URL="rediss://..." \
  TRANC3_ENGINE_URL="https://tranc3-backend.fly.dev" \
  --app trancendos-bots
```

> The bots Fly app is **`trancendos-bots`**, not `tranc3-bots` — that is the source
> directory. `cloud_preflight.py` checks this, because setting secrets on the wrong app
> name fails silently until the deploy cannot start.

---

## 2. Deploy the backend and bots (Fly.io)

```bash
python scripts/deploy_cloud.py
```

This gates, resolves credentials, deploys both apps, and polls health. Useful variants:

```bash
python scripts/deploy_cloud.py --backend-only   # skip bots
python scripts/deploy_cloud.py --skip-health    # don't wait on cold start
```

A first deploy needs the app to exist — `fly apps create tranc3-backend` — and the
script says so explicitly rather than failing opaquely.

---

## 3. Deploy the edge workers (Cloudflare)

Preferred: push to `main` touching `cloudflare/**`. The pipeline is change-aware and
deploys only the workers whose own files changed. To deploy deliberately, use
`workflow_dispatch` on **Deploy Cloudflare Workers** with `worker: all`, `force: true`.

Manual fallback, one worker at a time:

```bash
cd cloudflare/trancendos-api-gateway && npm ci && npx wrangler deploy
```

See `cloudflare/DEPLOY.md` for the manifest contract and how to onboard a worker.

---

## 4. Deploy the frontend (Cloudflare Pages)

```bash
cd web && npm install && npm run build
cd ../cloudflare/pages && npx wrangler pages deploy
```

Or let `frontend-build.yml` do it on a push touching `web/**`. Set these in the Pages
dashboard (Settings → Environment variables) — they are build-time, not secrets:

```
VITE_API_URL   = https://api.trancendos.com
VITE_AI_URL    = https://tranc3-ai.luminous-aimastermind.workers.dev
VITE_AUTH_URL  = https://infinity-auth-api.luminous-aimastermind.workers.dev
VITE_WS_URL    = wss://infinity-ws.luminous-aimastermind.workers.dev
```

---

## 5. Verify

```bash
curl -fsS https://tranc3-backend.fly.dev/health
curl -fsS https://trancendos-bots.fly.dev/health
curl -fsS https://api.trancendos.com/health
```

`post_deploy_verify.py` targets localhost ports and is for the Citadel stack — it does
**not** verify the cloud surface. Use the health URLs in `cloudflare/deploy-manifest.json`
and the two Fly endpoints above, or run the automated version:

```bash
python scripts/cloud_smoke_check.py \
  --gateway-url https://api.trancendos.com \
  --expect-stage owner
```

It checks `/health`, `/ready`, that the registration gate is enforcing the stage you
think it is, and optional gateway/frontend reachability — using a probe that can never
create an account. Run it after **every** deploy and every stage change.

---

## 6. Staged rollout

Registration is gated by `ROLLOUT_STAGE` (`src/auth/rollout_gate.py`). The gate is
**fail-closed**: a production deploy with no stage set behaves as `owner`.

| Stage | Cap | Who |
|---|---|---|
| `owner` | 2 accounts | Your own testing |
| `private_beta` | 10 | First tester wave |
| `extended_beta` | 25 | ~20 testers with headroom |
| `public` | none | Open registration; invite code ignored |

`ROLLOUT_INVITE_CODE` (optional but recommended pre-public) makes every non-public
registration require the shared code — give it to testers alongside the URL, rotate it
between waves. Testers pass it as `invite_code` in the register payload. The code does
**not** bypass the cap.

Advancing a stage is one command — `fly secrets set` restarts the app with the new
stage automatically, no code deploy involved:

```bash
# Generate into a shell variable and PRINT it — Fly secrets are write-only, so
# a value piped straight into `fly secrets set` can never be read back, and you
# need it to give to testers.
INVITE=$(python -c 'import secrets; print(secrets.token_urlsafe(12))')
echo "Invite code for this wave: $INVITE"      # record this before moving on

fly secrets set ROLLOUT_STAGE=private_beta ROLLOUT_INVITE_CODE="$INVITE" \
  --app tranc3-backend
python scripts/cloud_smoke_check.py --expect-stage private_beta
```

Keep the code at least 12 characters. Failed invite attempts are throttled
(20/minute per instance) so a weak code cannot be guessed quickly, but the
entropy is the real defence — the app registers no general rate-limiting
middleware, so `/auth/register` is otherwise unthrottled.

When a wave's cap is hit, further registrations get a 403 naming the stage — that is the
expected signal, not an error. Before flipping to `public`, run through the compliance
gates below (ICO registration at minimum).

---

## What cloud-only does *not* give you

State these plainly rather than discovering them under load:

- **No The Town Hall (CranBania).** It is a compose service; it has no cloud deploy
  path. Its read routes are also still ungated — an open owner decision (see
  `docs/GO_LIVE_GAP_ANALYSIS.md` §2.2) that must be settled before it is published
  anywhere network-reachable.
- **No self-hosted observability.** Prometheus, Grafana, Loki and Tempo are compose
  services. Cloud-only observability is Fly logs plus Cloudflare analytics.
- **No Vault / The Void self-hosted.** The CF `infinity-void` worker covers the vault
  function at the edge in this phase.
- **No Forgejo (The Workshop).** Its runner lives on the Citadel host, which is why the
  GitHub Actions mirrors exist. They are interim by explicit decision and should be
  retired when The Workshop returns — see `cloudflare/DEPLOY.md`.

## Compliance gates are independent of all of this

Going live technically does not make going live *lawful*. `docs/GO_LIVE_GAP_ANALYSIS.md`
§5 lists 14 open owner gates; ICO registration and the PSP DPA in particular gate lawful
operation and have long external lead times. They are not blocked on any of the above and
should be progressed in parallel.
