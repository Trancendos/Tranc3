# The Workshop — Recovery Runbook

When `https://trancendos.com/the-workshop` is unreachable. Cloudflare **HTTP 522**
means "connection timed out to origin" — i.e. Cloudflare reached the trancendos.com
edge but the **origin server never answered**. The fault is somewhere on this path:

```
Cloudflare  →  DNS/edge  →  host:443  →  nginx/Caddy  →  127.0.0.1:3456 (Forgejo)  →  act-runner
```

## TL;DR — one command

SSH to the server, then from the repo checkout:

```bash
bash deploy/forgejo/recover.sh          # diagnose + self-heal each layer
# or, to look without changing anything:
bash deploy/forgejo/recover.sh --check
```

It walks the path inside-out, restarts whatever layer is down (Docker, the
containers, the reverse proxy), waits for Forgejo health, and prints a report of
what it healed vs. what still needs a human.

## Manual triage (if you want to do it by hand)

Work **inside-out** — fix the innermost broken layer first.

| # | Check | Command | If it fails |
|---|---|---|---|
| 1 | Host reachable | `ssh <server>` | Host/VM is down or network-isolated → power it on / check provider console. This is the classic silent 522. |
| 2 | Docker up | `docker info` | `sudo systemctl start docker && sudo systemctl enable docker` |
| 3 | Containers up | `docker ps \| grep the-workshop` | `docker compose -f deploy/forgejo/docker-compose.yml up -d` |
| 4 | Forgejo healthy | `curl -sf http://127.0.0.1:3456/-/health` | `docker logs --tail 50 the-workshop` — look for disk-full, DB lock, bad config |
| 5 | Reverse proxy up | `systemctl is-active nginx` (or `caddy`) | `sudo systemctl restart nginx` |
| 6 | Proxy routes subpath | `curl -sf http://127.0.0.1/the-workshop/` | Ensure `deploy/forgejo/nginx-the-workshop.conf` (or `caddy-the-workshop.conf`) is included in the site config, then reload the proxy |
| 7 | Origin reachable from edge | (from off-host) `curl -I https://trancendos.com/the-workshop/` | If 1–6 are green but this is still 522: **Cloudflare side** — check the DNS record points at the right IP, SSL/TLS mode is *Full*, the origin's `:443` is open to Cloudflare IPs, and no host firewall/`ufw` rule is dropping them. |

**Rule of thumb:** if `curl http://127.0.0.1:3456/-/health` returns `200` on the host
but the public URL is still 522, the origin is healthy and the problem is **layer 5–7**
(proxy routing, host firewall, or Cloudflare), not Forgejo.

## Prevent recurrence: survive host reboots

`restart: unless-stopped` on the containers does **not** cover a full host reboot
unless something runs `docker compose up`. Install the systemd unit so the stack
comes back on every boot:

```bash
# edit WorkingDirectory in the unit if your checkout isn't /opt/tranc3
sudo cp deploy/forgejo/the-workshop.service /etc/systemd/system/the-workshop.service
sudo systemctl daemon-reload
sudo systemctl enable --now the-workshop.service
systemctl status the-workshop
```

## After it's back up

1. Confirm the runner registered: `https://trancendos.com/the-workshop/-/admin/runners`
   should show `trancendos-runner-1` online. If not: `docker logs the-workshop-runner`.
2. Confirm org secrets exist (needed for deploys):
   `https://trancendos.com/the-workshop/org/Trancendos/settings/secrets` — in particular
   **`CF_API_TOKEN`** and **`CF_ACCOUNT_ID`** for the Cloudflare deploy workflow
   (see `cloudflare/DEPLOY.md`). Re-push them with `deploy/forgejo/set-org-secrets.sh`
   if missing.
3. Any workflow that should have run while it was down (e.g. the CF deploy for a
   `cloudflare/**` change already on `main`) won't auto-fire retroactively — trigger it
   manually from the Actions tab (`workflow_dispatch`).

## First-time install (not recovery)

If the host was rebuilt from scratch, use the full bootstrap instead:
`bash deploy/forgejo/bootstrap.sh` (see its header for required env vars).
