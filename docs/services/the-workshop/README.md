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

### Container stack (`deploy/forgejo/docker-compose.yml`)

> **Two separate compose files exist for this entity, with two different runner service names —
> not a naming bug.** `deploy/forgejo/docker-compose.yml` (this table, the standalone
> manual-deploy path per §11 PROC) names its runner service `act-runner`. The unified
> `docker-compose.production.yml` (the DSM below) names the equivalent service `forgejo-runner`.
> Both are genuinely correct for their own file — operators following this pack's Procedure
> section should look for `act-runner`; operators inspecting the production stack as a whole
> should look for `forgejo-runner`.

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

## 7. Deployment Scope Matrix (DSM)

- **Mode awareness:** No — this entity's own code does not call `PlatformInfraMode` / `src/platform/infrastructure_mode.py`. (Some platform-wide, cross-cutting code *does* branch on the mode — `src/routers/adaptive.py` and `src/routers/ecosystem.py` read/set `PLATFORM_INFRA_MODE`/`SYSTEM_MODE` directly, and `Dimensional/architecture/storage_factory.py` selects a storage provider from `SYSTEM_MODE` — but none of that code is owned by this or any other one of the 43 named entities; it is shared platform infrastructure, not this service's own logic. The Citadel is the only one of the 43 named entities whose own code branches on the mode — see `docs/services/the-citadel/README.md`.) This entity's deployment scope is determined externally — by which `docker-compose.production.yml` service block runs, and where — not by in-process mode detection.
- **Runtime placement:** self-hosted Forgejo git+CI/CD — two compose services, `forgejo` (server) and `forgejo-runner` (act-runner); not part of the `tranc3-backend` monolith.
- **Persistence:** both `forgejo` and `forgejo-runner` have named volumes attached in compose (repos, CI artefacts, runner state).

| Setup | What runs, and where | Data locality | Hard blockers / caveats |
|---|---|---|---|
| **Cloud-Only** | both compose blocks run on a single cloud host; Nginx/Caddy (not Traefik — this entity uses its own reverse proxy, per `nginx-the-workshop.conf`/`caddy-the-workshop.conf`) routes `trancendos.com/the-workshop` to it | persists via each service's attached volume as long as the disk is preserved | no entity-specific blocker beyond standard single-host durability |
| **Hybrid** | `forgejo` server can run centrally (cloud or local) while `forgejo-runner` instances run in either location and pick up jobs from the same server — a genuinely useful split for this entity specifically | server data central; runner state wherever each runner instance lives | requires network reachability between runner and server regardless of which side is local vs cloud; the runner's `FORGEJO_INSTANCE_URL` currently defaults to the Compose-internal `http://forgejo:3000/the-workshop`, which only resolves inside the same Docker network — a runner placed on a genuinely separate host (the whole point of this Hybrid split) needs that value changed to an externally-reachable Forgejo endpoint, plus appropriate TLS/network-policy and runner-registration configuration; this is not automated today |
| **Local-Only** | both compose blocks run entirely on local/Citadel hardware | fully local, volume-backed | none beyond standard local-hardware ops |

- **Zero-cost posture per mode:** Cloud-Only defaults to the `zero_cost_cloud` AI-rotation chain; Hybrid/Local-Only default to `zero_cost_full` (`config/platform/infrastructure_mode.yaml`) — this only affects AI-Gateway-routed calls, not this entity's own logic
- **Switching modes:** operator-level via `PLATFORM_INFRA_MODE` (or legacy `SYSTEM_MODE`); no code change needed, though runner placement is worth deciding deliberately given the Hybrid split noted above.

## 8. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Git + CI | Forgejo 7 (`codeberg.org/forgejo/forgejo`) | OSS self-hosted |
| Runner | Forgejo act-runner (custom image) | OSS |
| DB | SQLite | local file |
| Reverse proxy | Nginx / Caddy | OSS |
| Deploy tooling | `flyctl`, `wrangler` (in runner image) | free tiers |

## 9. Environment Support Matrix (ESM)

> Grounded against `docker-compose.development.yml`, `docker-compose.uat.yml`, and `docker-compose.production.yml` — checked by exact compose service name, not assumed (see `docs/services/INDEX.md` for current platform-wide compose service totals, which change as the topology evolves).

| Environment | Covered? | What runs | Notes |
|---|---|---|---|
| **Dev** | No | not present in `docker-compose.development.yml` (only `api`, `redis`, `infinity-ws`, `infinity-auth`, `infinity-ai`, `mailhog` exist there) | no compose-defined pre-production environment |
| **UAT** | No | not present in `docker-compose.uat.yml` either | same — no compose-defined pre-production environment |
| **Production** | Yes | full detail in the DSM above | — |

- **Gap:** this entity has **no compose-orchestrated non-Production environment** — `forgejo / forgejo-runner` only exists in `docker-compose.production.yml`, not in the shared Dev/UAT compose stacks. It does have a documented local/manual startup path outside of compose — §11 PROC's `bash deploy/forgejo/setup.sh` (or `bootstrap.sh`) — so "no environment but Production" means no *compose-orchestrated* Dev/UAT coverage, not that Production is the only place it can ever run. This lack of compose-orchestrated pre-production coverage is the norm for most standalone workers on this platform (only The Nexus and Infinity have full pre-production standalone-worker compose coverage, and The Observatory and The Digital Grid have UAT-only standalone-worker coverage), not a defect specific to this entity — stated here so it isn't assumed otherwise.

## 10. Policy (POL)

- All CI/CD flows through The Workshop (no GitHub Actions for platform pipelines). Org secrets
  (`CF_API_TOKEN`, `FLY_API_TOKEN`) are set via `set-org-secrets.sh`, never committed.

## 11. Procedure (PROC)

- **Stand up The Workshop:** `bash deploy/forgejo/setup.sh` (or `bootstrap.sh` for full setup), add the
  Nginx block from `nginx-the-workshop.conf`, then `runner-setup.sh` to register the runner.

## 12. Runbook (RUN)

- **Workshop unreachable / Cloudflare 522 (whole service down):** run
  `bash deploy/forgejo/recover.sh` on the server — it diagnoses and self-heals each layer
  (Docker → containers → Forgejo health → reverse proxy) and reports what still needs a human.
  Full triage table + prevention in `deploy/forgejo/RUNBOOK.md`. A **522 with a healthy
  local `curl http://127.0.0.1:3456/-/health`** means the fault is the reverse proxy / host
  firewall / Cloudflare side, not Forgejo.
- **Survives host reboots:** the containers are `restart: unless-stopped`, but that does not
  cover a full host reboot — install `deploy/forgejo/the-workshop.service` (systemd) so the
  stack comes back on boot (`systemctl enable --now the-workshop`).
- **Forgejo unhealthy:** the compose healthcheck hits `http://localhost:3000/-/health`; check the
  `forgejo` container and the `forgejo-data` volume.
- **Runner not picking up jobs:** verify `FORGEJO_INSTANCE_URL` + runner registration (`runner-setup.sh`);
  the runner talks to Forgejo **internally** (`forgejo:3000`), not through Nginx.
- **Deploy step fails on missing `flyctl`/`wrangler`:** the custom `runner.Dockerfile` image wasn't built —
  either build it or accept the upstream `runner:3` image (no deploy tooling).

## 13. Standards (STD)

- Forgejo bound to localhost + reverse-proxied on `/the-workshop`; secrets via org-secret script; runner
  image pins its deploy toolchain.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-03 | Claude (session) | `deploy/forgejo/docker-compose.yml`, `setup.sh`/`bootstrap.sh`, `nginx-the-workshop.conf`, `runner.Dockerfile` | Compose services, ports (3456→3000), proxy path, scripts, and runner image verified against config |
| 2026-07-11 | Claude (session, cubic-dev-ai review triage) | ESM §9, PROC §11 | Fixed an internal contradiction: the ESM Gap bullet said "no local run command is documented in §11 PROC either," but §11 explicitly documents `bash deploy/forgejo/setup.sh`/`bootstrap.sh` as a local startup procedure. Reworded the Dev/UAT rows and Gap bullet to say "no compose-orchestrated pre-production environment" instead of implying no local run path exists at all. |
