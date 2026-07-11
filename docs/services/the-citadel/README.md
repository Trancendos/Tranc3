# Service Doc-Pack — The Citadel (Strategic Ops & DevOps Fortress)

| Field | Value |
|---|---|
| **Entity** | The Citadel |
| **Lead AI** | Trancendos (Prime) |
| **Status** | ✅ Self-hosted (per `CLAUDE.md` service table) — Live tier |
| **Code** | `docker-compose.production.yml`, `deploy/citadel/deploy-production.sh`, `scripts/citadel_preflight.py`, `deploy/vault/vault.hcl`, `deploy/runbook.md` |

> **Truthfulness:** claims cite `docker-compose.production.yml`, `deploy/citadel/deploy-production.sh`,
> `scripts/citadel_preflight.py`, `scripts/zero_cost_audit.py`, `scripts/branch_benefit_audit.py`,
> `scripts/health_check.py`, and `deploy/runbook.md` directly. Status is owned by the `CLAUDE.md`
> service table; identity by `PLATFORM_ENTITIES.md`.
>
> **Version drift note:** image versions and step-by-step script behavior below (e.g. Prometheus
> `v2.50.0`, Grafana `10.3.0`, the preflight/deploy step order) are transcribed from the cited files
> as of this pack's Verification Log date. They are **not** auto-synced — if `docker-compose.production.yml`
> or the referenced scripts change, this pack must be re-verified and updated, same as any other
> code-grounded doc-pack in this repo.

## 1. Service Governance Charter (GOV)

- **Mission:** the platform's infrastructure fortress — the Docker Compose + Traefik stack that
  hosts every self-hosted worker, plus the deploy tooling and preflight gates that get it there
  safely. Not a single service; the substrate the other 42 entities run on.
- **Owner (RACI-A):** Trancendos (Prime/Platform Owner).
- **Scope:** `docker-compose.production.yml` (infrastructure + worker layer), `deploy/citadel/`
  (deploy entrypoint), `deploy/vault/` (secrets config), `scripts/citadel_preflight.py` +
  `scripts/zero_cost_audit.py` (pre-deploy gates), `scripts/health_check.py` (post-deploy check).

## 2. Detailed Design Document (DDD)

### Infrastructure layer (`docker-compose.production.yml`)
| Component | Image | Role |
|---|---|---|
| `traefik` | `traefik:v3.0` | Reverse proxy, Docker-label auto-discovery, TLS termination, ports 80/443, dashboard :8888, metrics :9090 |
| `vault` | `hashicorp/vault:1.15` | Secrets management, Shamir unseal, config at `deploy/vault/vault.hcl`, port 8200 |
| `prometheus` | `prom/prometheus:v2.50.0` | Metrics scrape, 30d retention / 5GB cap, port 9091 |
| `alertmanager` | `prom/alertmanager:v0.27.0` | Alert routing, Slack webhook via `envsubst` template, port 9093 |
| `otel-collector` | `otel/opentelemetry-collector-contrib:0.96.0` | OTLP gRPC/HTTP ingest (4317/4318) |
| `grafana` | `grafana/grafana:10.3.0` | Dashboards, auto-provisioned Prometheus + Loki datasources |
| IPFS, Loki, Promtail | (see compose) | Distributed storage; log aggregation |

All worker services (`x-worker-common` anchor) share: `env_file: .env.production`,
`tranc3-net` Docker network, JSON-file logging (10MB × 3 files), `tranc3.stack=production` label.

### Deploy pipeline (`deploy/citadel/deploy-production.sh`)
Sequential steps, each a real script invocation (not aspirational):
1. Guard: refuse to run without `.env.production` present (must be copied from
   `.env.production.example` and filled from The Void/Vault).
2. `scripts/citadel_preflight.py` — validates required env keys (`SECRET_KEY`, `JWT_SECRET`,
   `DATABASE_URL`, `REDIS_URL`), flags placeholder values (regex `LOAD_FROM_VAULT|change-me|your[-_]`),
   checks compose + `deploy/vault/vault.hcl` presence. Exit 1 blocks deploy.
3. `scripts/zero_cost_audit.py` — audits for paid-provider dependencies (platform mandate).
4. `scripts/branch_benefit_audit.py` — non-blocking (`|| true`).
5. `git fetch origin main && git checkout main && git pull` — deploys from `main`, not the
   invoking branch.
6. `docker compose -f docker-compose.production.yml build && up -d`.
7. `scripts/health_check.py` — non-blocking post-deploy check after a 15s settle.
8. Optional swarm manifests (`platform-health.yaml`, `citadel-deploy.yaml`) — non-blocking.
9. Vault status check — if the container is up, checks seal state and warns to
   `vault operator init && unseal` if needed (first-deploy only).

### Preflight gate detail (`scripts/citadel_preflight.py`)
- Reads `.env.production`, `docker-compose.production.yml`, `deploy/vault/vault.hcl` from repo root.
- `REQUIRED_KEYS`: `SECRET_KEY`, `JWT_SECRET`, `DATABASE_URL`, `REDIS_URL` — missing any → block.
- `RECOMMENDED_KEYS`: `INTERNAL_SECRET`, `MASTER_KEY_SEED`, `AUDIT_SIGNING_KEY`,
  `ENTITY_OVERRIDES_DB`, `INFINITY_ADMIN_DB_PATH` — missing → warn, not block.
- Placeholder detection regex catches unfilled template values before they reach prod.

## 3. Technical Architecture Solutions Design (TASD)

- **Decision: Docker Compose over Kubernetes.** A managed K8s cluster (EKS/GKE/AKS) is a paid
  service and contradicts the zero-cost mandate; Compose + Traefik gives auto-discovery and
  reverse-proxying without that cost. (`deploy/runbook.md`'s Kubernetes section is documented as
  unsupported/aspirational for exactly this reason — see that file's warning block.)
- **Decision: fail-fast preflight over silent partial deploys.** `citadel_preflight.py` blocks on
  missing required secrets rather than letting a worker boot with a placeholder `SECRET_KEY`.
- **Decision: deploy always pulls `main`**, never the operator's current branch — prevents
  accidental deploy of unmerged work from a laptop checkout.
- **Trade-off accepted:** most deploy-script steps that follow preflight are non-blocking
  (`|| true`) — health-check and swarm-manifest failures don't roll back the compose `up -d`.
  This favours availability (a partially-healthy stack stays up) over strict all-or-nothing deploy.

## 4. RACI Matrix

| Activity | Trancendos (Owner) | Platform Engineering | Individual Service Leads | The Observatory |
|---|---|---|---|---|
| Compose/Traefik topology changes | **A** | **R** | C | I |
| Preflight gate changes (`citadel_preflight.py`) | **A** | **R** | I | I |
| Production deploy execution | **R/A** | C | I | I |
| Vault unseal / secrets rotation | **A** | **R** | C | I |
| Per-worker health/incident | I | C | **R/A** | C |

## 5. Solutions Integration Model (SIM)

- **Upstream:** none — The Citadel is the substrate other entities deploy onto, not a consumer.
- **Downstream:** every worker in `docker-compose.production.yml`'s service list routes through
  Traefik's Docker-label discovery; Prometheus scrapes all workers exposing `/metrics`;
  Vault backs `.env.production`-sourced secrets (self-hosted, replacing CF env vars).
- **Auth boundary:** Vault's own API (port 8200, Shamir-sealed) is the trust root; workers read
  secrets via `env_file`, not direct Vault calls at this layer.

## 6. Architecture Scalability Document (ASD)

- **Load model:** single-host Docker Compose — not a multi-node orchestrator. Scaling is
  vertical (bigger host) or horizontal-by-service (external DB/volume + multiple Compose hosts
  behind an LB), not automatic.
- **Bottleneck:** `/var/run/docker.sock` mount on Traefik ties routing to the local Docker daemon;
  no built-in multi-host service mesh.
- **Zero-cost limits & hard stops:** no managed K8s, no paid LB — Traefik + Compose only. The
  `deploy/runbook.md` Kubernetes section is explicitly flagged as unsupported/aspirational
  because a managed cluster would violate this mandate.
- **Degradation:** deploy script's non-blocking steps (health check, swarm manifests) mean a
  degraded worker doesn't block the rest of the stack from starting — trades strict correctness
  for availability, per §3.

## 7. Deployment Scope Matrix (DSM)

> This entity is the deployment substrate itself (Traefik, Vault, Prometheus, Grafana, Loki/Promtail, IPFS, and the `docker-compose.production.yml` stack as a whole) — its DSM is necessarily foundational rather than a consumer of the three modes like other entities.

- **Mode awareness:** Yes, indirectly — `src/platform/infrastructure_mode.py`'s `should_run_citadel_docker()` explicitly gates whether the Citadel Docker Compose stack runs at all: **true** for `LOCAL_ONLY`, **true** for `HYBRID` only when `CITADEL_LOCAL_STACK=true` is also set, **false** for `CLOUD_ONLY`. This is the one genuine, code-level mode-branch found across all 43 platform entities.
- **Runtime placement:** the entire `docker-compose.production.yml` stack — Traefik reverse proxy, Vault, Prometheus, Grafana, Loki+Promtail, IPFS, and every worker service block on this platform.
- **Persistence:** each infrastructure component has its own named volume (`traefik`, `vault`, `prometheus`, `grafana`, etc. — confirmed present in compose).

| Setup | What runs, and where | Data locality | Hard blockers / caveats |
|---|---|---|---|
| **Cloud-Only** | the Citadel stack does **not** run; `should_run_citadel_docker()` returns `false`; the platform instead relies on Cloudflare Workers + free-tier cloud AI rotation (`zero_cost_cloud` chain) with no local Traefik/Vault/Prometheus | n/a in this mode — no local infra stack | no self-hosted observability/secrets-vault stack; relies entirely on cloud-native equivalents |
| **Hybrid** | the Citadel stack runs **only if** `CITADEL_LOCAL_STACK=true` is explicitly set; otherwise same as Cloud-Only | local volumes for whichever components are running, cloud storage for the rest — per `docs/architecture/infrastructure-modes.md`'s Hybrid diagram | operator must remember to set `CITADEL_LOCAL_STACK=true`; forgetting it silently falls back to Cloud-Only behaviour for this entity |
| **Local-Only** | the full Citadel stack runs — `should_run_citadel_docker()` returns `true` unconditionally | fully local, all components volume-backed | none beyond standard local-hardware ops (this is the mode The Citadel is designed for) |

- **Zero-cost posture per mode:** Local-Only and Hybrid both default to the `zero_cost_full` rotation chain; Cloud-Only defaults to `zero_cost_cloud` (`config/platform/infrastructure_mode.yaml`).
- **Switching modes:** `PLATFORM_INFRA_MODE` (or legacy `SYSTEM_MODE`) plus, for Hybrid, `CITADEL_LOCAL_STACK` — this is the one entity where the env var directly changes what actually gets deployed, not just which host a fixed compose block runs on.

## 8. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Reverse proxy | Traefik v3.0 | OSS, self-hosted |
| Secrets | HashiCorp Vault 1.15 (Shamir unseal) | OSS, self-hosted |
| Metrics | Prometheus v2.50.0 + Alertmanager v0.27.0 | OSS, self-hosted |
| Telemetry ingest | OpenTelemetry Collector 0.96.0 | OSS, self-hosted |
| Dashboards | Grafana 10.3.0 | OSS, self-hosted |
| Distributed storage | IPFS | OSS, self-hosted |
| Log aggregation | Loki + Promtail | OSS, self-hosted |
| Orchestration | Docker Compose (not K8s) | avoids managed-cluster cost |

## 9. Policy (POL)

- Deploy MUST run `citadel_preflight.py` and `zero_cost_audit.py` before `up -d` — enforced by
  `deploy-production.sh`'s script order, not optional. No paid-provider dependency may pass
  `zero_cost_audit.py`. Reuses platform policy (`docs/defstan/`).

## 10. Procedure (PROC)

- **Production deploy:** `cp .env.production.example .env.production` → fill secrets from The
  Void/Vault → `./deploy/citadel/deploy-production.sh` (from repo root, on the Citadel host).
- **Vault first-init:** if `vault status` reports uninitialized, run `vault operator init` and
  `vault operator unseal` per HashiCorp docs (script only warns; does not automate this — a
  deliberate manual step for a security-critical action).

## 11. Runbook (RUN)

- **Preflight blocks deploy (`REQUIRED_KEYS` missing):** fill the reported key(s) in
  `.env.production` from Vault; re-run `citadel_preflight.py` directly to verify before retrying
  the full deploy script.
- **Placeholder value detected:** the flagged key still contains `LOAD_FROM_VAULT`, `change-me`,
  or a `your-`/`your_` prefix — replace with the real secret.
- **Vault sealed post-restart:** expected after any host reboot (Vault re-seals on process
  restart); run `vault operator unseal` with the stored key shares.
- **Traefik not routing a new worker:** confirm the worker's compose service has
  `traefik.enable=true` and the correct `loadbalancer.server.port` label — see
  `scripts/port_registry_validate.py` for the port-consistency check (issue #188).

## 12. Standards (STD)

- All new workers added to `docker-compose.production.yml` MUST use the `x-worker-common` anchor
  (shared logging, network, env_file) unless there's a documented reason not to.
- Port declarations MUST be consistent across compose `PORT` env / Traefik label / `ports:` per
  `scripts/port_registry_validate.py` (issue #188 regression guard).

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-03 | Claude (session) | `docker-compose.production.yml` (infra services, worker-common anchor), `deploy/citadel/deploy-production.sh`, `scripts/citadel_preflight.py`, `deploy/runbook.md` (K8s warning) | DDD/TASD/ASD verified against code; no fabricated claims — Kubernetes section explicitly scoped out as unsupported per existing runbook warning |
