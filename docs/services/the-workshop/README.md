# Service Doc-Pack — The Workshop (CI/CD Hub)

| Field | Value |
|---|---|
| **Entity** | The Workshop (`PID-WRK`) |
| **Lead AI** | Larry Lowhammer (`AID-WRK-01`); Prime: The Doctor (Nikolai O'denhim) |
| **Status** | ✅ In repo (per `CLAUDE.md` service table) |
| **Code** | `deploy/forgejo/` (deployment config + scripts) |
| **Endpoint** | `trancendos.com/the-workshop` (Nginx → Forgejo on `127.0.0.1:3456`) |

> **Truthfulness:** claims cite `deploy/forgejo/`. The Workshop is a **deployment/config** service
> (self-hosted Forgejo + act-runner), not application code — the pack documents the compose stack,
> scripts, and proxy as they are written. Status owned by the `CLAUDE.md` service table; identity by
> `PLATFORM_ENTITIES.md`.

## 1. Service Governance Charter (GOV)

- **Mission:** self-hosted CI/CD sovereignty — a Forgejo git server + Forgejo Actions runner, replacing
  GitHub Actions (per `CLAUDE.md`: *all CI/CD runs through The Workshop*).
- **Owner (RACI-A):** Larry Lowhammer (Lead AI); Prime The Doctor (Nikolai O'denhim).
- **Scope:** container stack (`docker-compose.yml`), bootstrap/setup scripts, reverse-proxy config, and a
  custom runner image.

## 2. Detailed Design Document (DDD) — `deploy/forgejo/`

### Container stack (`docker-compose.yml`)
| Service | Image | Notes |
|---|---|---|
| `forgejo` (`container_name: the-workshop`) | `codeberg.org/forgejo/forgejo:7` | SQLite DB (`FORGEJO__database__PATH=/data/forgejo/forgejo.db`); Actions enabled (`DEFAULT_ACTIONS_URL=https://code.forgejo.org`); published on `127.0.0.1:3456:3000`; healthcheck `GET /-/health` |
| `act-runner` (`the-workshop-runner`) | `${RUNNER_IMAGE:-code.forgejo.org/forgejo/runner:3}` | talks to Forgejo internally (`FORGEJO_INSTANCE_URL=http://forgejo:3000/the-workshop`); `FORGEJO_RUNNER_NAME=trancendos-runner-1` |

### Scripts
- **`setup.sh`** — start containers + wait for health (quick start).
- **`bootstrap.sh`** — full automated bootstrap: admin user, org, runner registration, secrets.
- **`runner-setup.sh`**, **`set-org-secrets.sh`**, **`act-runner.yml`** — runner + org-secret wiring.
- **`runner.Dockerfile`** — custom runner image bundling `flyctl`, `wrangler`, Python, Node (so pipelines
  can deploy without extra installs). Falls back to the upstream `runner:3` image if unbuilt.

### Reverse proxy
- **`nginx-the-workshop.conf`** — `location /the-workshop/ → proxy_pass http://127.0.0.1:3456/the-workshop/`,
  with a `301` from bare `/the-workshop`; `ROOT_URL=https://trancendos.com/the-workshop`.
- **`caddy-the-workshop.conf`** — Caddy equivalent.

## 3. Technical Architecture Solutions Design (TASD)

- **Style:** single-host Docker Compose — Forgejo (git + Actions) + a runner, fronted by Nginx/Caddy on a
  path prefix (`/the-workshop`), not a subdomain (consistent with the platform's subdirectory topology).
- **Decision:** own the entire CI/CD chain (Forgejo, not GitHub Actions) for sovereignty and zero cost;
  bundle deploy tooling into the runner image so pipelines are self-contained.

## 4. RACI Matrix

| Activity | Larry Lowhammer (Lead) | The Doctor (Prime) | Platform Owner | The Observatory |
|---|---|---|---|---|
| Forgejo + runner ops | **R/A** | C | C | I |
| Pipeline/runner image | **R** | **A** | C | I |
| Org secrets (`CF_API_TOKEN`, `FLY_API_TOKEN`) | **R/A** | C | **A** | I |

## 5. Solutions Integration Model (SIM)

- **Upstream:** developers push to Forgejo; workflows live in `.forgejo/workflows/`.
- **Downstream:** the runner deploys (Fly.io / Cloudflare) using bundled `flyctl`/`wrangler` + org secrets.
- **Auth boundary:** Forgejo is bound to `127.0.0.1:3456` and exposed only via the Nginx/Caddy path prefix.

## 6. Architecture Scalability Document (ASD)

- **Load model:** CI throughput scales with runner count; the compose file ships **one** runner
  (`trancendos-runner-1`) — add runners for parallelism.
- **Zero-cost limits & hard stops:** self-hosted Forgejo + SQLite; no paid CI minutes.
- **Bottleneck:** single-host SQLite Forgejo; DR is by data-volume backup (`forgejo-data`).

## 7. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Git + CI | Forgejo 7 (`codeberg.org/forgejo/forgejo`) | OSS self-hosted |
| Runner | Forgejo act-runner (custom image) | OSS |
| DB | SQLite | local file |
| Reverse proxy | Nginx / Caddy | OSS |
| Deploy tooling | `flyctl`, `wrangler` (in runner image) | free tiers |

## 8. Policy (POL)

- All CI/CD flows through The Workshop (no GitHub Actions for platform pipelines). Org secrets
  (`CF_API_TOKEN`, `FLY_API_TOKEN`) are set via `set-org-secrets.sh`, never committed.

## 9. Procedure (PROC)

- **Stand up The Workshop:** `bash deploy/forgejo/setup.sh` (or `bootstrap.sh` for full setup), add the
  Nginx block from `nginx-the-workshop.conf`, then `runner-setup.sh` to register the runner.

## 10. Runbook (RUN)

- **Forgejo unhealthy:** the compose healthcheck hits `http://localhost:3000/-/health`; check the
  `forgejo` container and the `forgejo-data` volume.
- **Runner not picking up jobs:** verify `FORGEJO_INSTANCE_URL` + runner registration (`runner-setup.sh`);
  the runner talks to Forgejo **internally** (`forgejo:3000`), not through Nginx.
- **Deploy step fails on missing `flyctl`/`wrangler`:** the custom `runner.Dockerfile` image wasn't built —
  either build it or accept the upstream `runner:3` image (no deploy tooling).

## 11. Standards (STD)

- Forgejo bound to localhost + reverse-proxied on `/the-workshop`; secrets via org-secret script; runner
  image pins its deploy toolchain.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-03 | Claude (session) | `deploy/forgejo/docker-compose.yml`, `setup.sh`/`bootstrap.sh`, `nginx-the-workshop.conf`, `runner.Dockerfile` | Compose services, ports (3456→3000), proxy path, scripts, and runner image verified against config |
