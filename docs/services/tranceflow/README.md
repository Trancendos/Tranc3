# Service Doc-Pack — TranceFlow

| Field | Value |
|---|---|
| **Entity** | TranceFlow |
| **Lead AI** | Junior Cesar |
| **Status** | ✅ In repo (per `CLAUDE.md` service table) — Live tier |
| **Code** | `workers/tranceflow/main.py` + `config.py`/`database.py`/`service.py`/`router.py` (the deployed implementation) — standalone worker, no `src/*` module, no `api.py` mount. `worker.py` (388 lines, separate single-file alternate) exists but is not deployed. |

> **Truthfulness:** claims cite `workers/tranceflow/main.py`, `config.py`, `router.py`,
> `Dockerfile`, and `docker-compose.production.yml` directly. Status is owned by the `CLAUDE.md`
> service table; identity by `PLATFORM_ENTITIES.md`.
> **Bug found and fixed while authoring this pack — same class as `workers/library-service` and
> `workers/lab-service` earlier in this series.** `workers/tranceflow/Dockerfile` hardcoded
> `EXPOSE 8052` / `HEALTHCHECK ... localhost:8052` / `CMD [..., "--port", "8052"]`, while
> `docker-compose.production.yml` sets `PORT: "8059"`, maps `"8059:8059"`, and routes Traefik to
> container port 8059. Compounding the defect: `config.py`'s `WORKER_PORT` read from
> `TRANCEFLOW_PORT`, not `PORT` — the exact env var name compose actually sets — so even a
> direct-run (`python main.py`) invocation would never have picked up compose's intended port.
> Both issues meant the container would bind 8052 regardless of compose's configuration, making
> it unreachable at the routed port 8059. Fixed by changing the Dockerfile's
> `EXPOSE`/`HEALTHCHECK`/`CMD --port` to 8059, and `config.py`'s `WORKER_PORT` to read `PORT`
> first (falling back to `TRANCEFLOW_PORT`, then `8059`). Verified by reloading `config.py` with
> no env override — confirms it now defaults to 8059.
> **Scope note:** `workers/tranceflow/worker.py` (388 lines) is a separate, single-file,
> genuinely real alternate implementation (own SQLite schema, its own routes) not referenced by
> the Dockerfile at all — the same "two independent implementations, one deployed" pattern found
> in Sashas Photo Studio earlier in this batch. Not audited in depth here since it isn't deployed.

## 1. Service Governance Charter (GOV)

- **Mission:** 3D modeling & games creation studio — project/asset management with a Godot Engine
  export pipeline.
- **Owner (RACI-A):** Junior Cesar; Platform Owner Trancendos.
- **Scope:** the modular `main.py`+`config.py`+`database.py`+`service.py`+`router.py` stack — the
  actually-deployed implementation. `worker.py`'s independent implementation is out of scope for
  this pack's depth (real but unused).

## 2. Detailed Design Document (DDD)

### HTTP surface (`router.py`, mounted via `main.py`)

| Method | Route | Backing |
|---|---|---|
| GET | `/health` | static worker/entity metadata, not a real dependency probe — the only route not gated by `_auth()` |
| POST | `/projects` | `create_project()` — internal-secret authed |
| GET | `/projects` | `list_projects()` — internal-secret authed |
| GET | `/projects/{id}` | `get_project()` — internal-secret authed |
| DELETE | `/projects/{id}` | `delete_project()` — internal-secret authed |
| POST | `/projects/{id}/export` | `export_asset()` — internal-secret authed — async, presumably triggers the Godot/Blender export pipeline per `config.py`'s `GODOT_BIN`/`BLENDER_BIN` settings (not traced in depth in this pass) |
| GET | `/status` | worker status — internal-secret authed |

### Auth (`_auth()`)
- Real `X-Internal-Secret` header check, matching `config.INTERNAL_SECRET`. Unlike The
  Academy/Sashas Photo Studio's `"dev-secret"` insecure-fallback pattern, `config.py` here
  **correctly leaves `INTERNAL_SECRET` empty by default and emits a `warnings.warn()`** if unset
  — a materially better security posture than the fallback-string pattern seen elsewhere in this
  series. A positive finding worth noting explicitly.

### Processing backends (`config.py`)
- `GODOT_BIN`/`GODOT_ENABLED`, `BLENDER_BIN`/`BLENDER_ENABLED`, plus optional `trimesh`/`meshio`/
  `open3d`/`pyvista` toggles — all real, self-hosted, zero-cost tooling per the module's own
  config, consistent with the platform's zero-cost mandate. Whether `export_asset()` actually
  invokes these binaries was not traced line-by-line in this pass given the fixed defect's
  priority; flagged as unverified rather than assumed working.

## 3. Technical Architecture Solutions Design (TASD)

- **Style:** standalone FastAPI worker, modular file layout (config/models/database/service/
  router/main) — a cleaner separation of concerns than most single-file workers audited in this
  series.
- **Fixed defect:** Dockerfile port hardcoding + wrong env var name in `config.py` — see
  truthfulness header. This is now the third instance of the Dockerfile-hardcoded-port defect
  class found in this doc-pack series (after `library-service` and `lab-service`), suggesting it
  may be worth a dedicated audit pass across all remaining workers rather than finding them one
  at a time.
- **Not evaluated:** whether `export_asset()`'s Godot/Blender invocation actually works in a
  real environment (neither binary confirmed present in this sandbox) — out of scope for this
  pass's priority (the port defect).

## 4. RACI Matrix

| Activity | Junior Cesar (Lead) | Platform Owner | Platform Engineering |
|---|---|---|---|
| Project/asset CRUD logic changes | **R** | A | C |
| Godot/Blender export pipeline changes | **R** | A | C |
| Deciding between `main.py`/`worker.py` as canonical (future, same open question as Sashas Photo Studio) | C | **A** | **R** |

## 5. Solutions Integration Model (SIM)

- **Upstream:** any caller with a correct `X-Internal-Secret` header — real, enforced auth.
- **Downstream:** local Godot/Blender binary invocation (per `config.py`, not traced in depth);
  SQLite via `TranceFlowDatabase`.
- **Not integrated:** `worker.py`'s independent implementation is never called from `main.py` or
  vice versa.

## 6. Architecture Scalability Document (ASD)

- **Load model:** SQLite-backed (`database.py`), single-process.
- **Bottleneck:** Godot/Blender export operations are presumably synchronous/CPU-bound subprocess
  calls (not traced in depth) — `PROCESS_TIMEOUT` (120s default) and `QUOTA_MAX_CALLS`/
  `QUOTA_WINDOW_SECONDS` config values suggest rate-limiting intent, not verified as enforced in
  this pass.
- **Zero-cost limits:** Godot, Blender, trimesh, meshio, open3d, pyvista are all free/OSS.
- **Degradation:** OTel instrumentation is optional (wrapped in `try/except`, never blocks
  startup) — a good, established pattern also seen in other entities this series.

## 7. Deployment Scope Matrix (DSM)

- **Mode awareness:** No — this entity's own code does not call `PlatformInfraMode` / `src/platform/infrastructure_mode.py`. (Some platform-wide, cross-cutting code *does* branch on the mode — `src/routers/adaptive.py` and `src/routers/ecosystem.py` read/set `PLATFORM_INFRA_MODE`/`SYSTEM_MODE` directly, and `Dimensional/architecture/storage_factory.py` selects a storage provider from `SYSTEM_MODE` — but none of that code is owned by this or any other one of the 43 named entities; it is shared platform infrastructure, not this service's own logic. The Citadel is the only one of the 43 named entities whose own code branches on the mode — see `docs/services/the-citadel/README.md`.) This entity's deployment scope is determined externally — by which `docker-compose.production.yml` service block runs, and where — not by in-process mode detection.
- **Runtime placement:** standalone worker with its own `docker-compose.production.yml` service block (`tranceflow`, port 8059) and its own Traefik route — does not run inside the `tranc3-backend` monolith
- **Persistence:** named volume attached to the `tranceflow` compose service — state survives container restarts/redeploys in any mode

| Setup | What runs, and where | Data locality | Hard blockers / caveats |
|---|---|---|---|
| **Cloud-Only** | the `tranceflow` compose block runs on a single cloud host; Traefik/edge in front | persists via its attached volume as long as the volume/disk is preserved on that host | none beyond standard single-host durability (no built-in cross-host replication) |
| **Hybrid** | same `tranceflow` compose block; per `docs/architecture/infrastructure-modes.md`'s Hybrid diagram, this worker itself still runs as a single instance (cloud or local host), with only shared persistent data (not specific to this worker) split via TrueNAS/Syncthing | as above, optionally local-synced if a volume exists | requires `CITADEL_LOCAL_STACK=true` if a local compose stack should run alongside the cloud one |
| **Local-Only** | same `tranceflow` compose block, run entirely on local/Citadel hardware behind local Traefik | fully local, volume-backed | none beyond standard local-hardware ops |

- **Zero-cost posture per mode:** Cloud-Only defaults to the `zero_cost_cloud` AI-rotation chain; Hybrid/Local-Only default to `zero_cost_full` (`config/platform/infrastructure_mode.yaml`) — this only affects AI-Gateway-routed calls, not this entity's own logic
- **Switching modes:** operator-level via `PLATFORM_INFRA_MODE` (or legacy `SYSTEM_MODE`); this entity needs no code change to move between modes, only a redeploy-target change for its own compose block

## 8. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Web framework | FastAPI, standalone (no `api.py` mount) | self-hosted, port 8059 (fixed this pass) |
| Storage | SQLite (`database.py`) | zero infra cost |
| 3D/asset processing | Godot Engine, Blender, trimesh, meshio, open3d, pyvista | all free/OSS |
| Auth | `X-Internal-Secret`, no insecure fallback | zero cost, genuinely enforced |

## 9. Environment Support Matrix (ESM)

> Grounded against `docker-compose.development.yml` (6 services), `docker-compose.uat.yml` (16 services), and `docker-compose.production.yml` (286 services) — checked by exact compose service name, not assumed.

| Environment | Covered? | What runs | Notes |
|---|---|---|---|
| **Dev** | No | not present in `docker-compose.development.yml` (only `api`, `redis`, `infinity-ws`, `infinity-auth`, `infinity-ai`, `mailhog` exist there) | no code path to validate before Production |
| **UAT** | No | not present in `docker-compose.uat.yml` either | same — first validation point is Production itself |
| **Production** | Yes | full detail in the DSM above | — |

- **Gap:** this entity has **no non-Production environment at all** — `tranceflow` only exists in `docker-compose.production.yml`. A change to this worker is validated for the first time in Production. This is the norm for most standalone workers on this platform (only The Nexus, Infinity, The Digital Grid, and The Observatory have any pre-production compose coverage), not a defect specific to this entity — stated here so it isn't assumed otherwise.

## 10. Policy (POL)

- Real internal-secret auth enforced, with a correct warn-not-fallback pattern for missing
  secrets — a positive finding relative to several other entities in this series.
- Zero-cost mandate: fully honored per `config.py`'s tool choices.

## 11. Procedure (PROC)

- **Create a project:** `POST /projects` with the required internal-secret header.
- **Export an asset:** `POST /projects/{id}/export` — presumably triggers Godot/Blender per
  config; not traced end-to-end in this pass.

## 12. Runbook (RUN)

- **The service was unreachable at port 8059 before this pass:** was a genuine Dockerfile/config
  port mismatch (container bound 8052; compose routed 8059; `config.py` also read the wrong env
  var name) — fixed in this pass; confirm the fix (Dockerfile `8059` throughout, `config.py`
  reading `PORT` first) is present in the deployed image if this recurs.
- **Startup warns `INTERNAL_SECRET is not set`:** expected if the env var genuinely isn't
  configured — set `INTERNAL_SECRET` in the deployment environment; this is correct, intentional
  behavior, not a bug.

## 13. Standards (STD)

- Naming: canonical entity name "TranceFlow" per `CLAUDE.md`/`PLATFORM_ENTITIES.md`.
- Config modules MUST read the exact environment variable name that
  `docker-compose.production.yml` sets for that service — the `TRANCEFLOW_PORT` vs. compose's
  `PORT` mismatch fixed here is the reason for this standard, compounding the already-established
  Dockerfile-hardcoded-port standard from `workers/library-service`'s doc-pack.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-05 | Claude (session) | `workers/tranceflow/main.py` (74 lines), `config.py` (38 lines), `router.py` (83 lines), `Dockerfile`, `docker-compose.production.yml` | Confirmed Live-tier, full pack authored. Found and fixed a genuine, third-instance-in-series routing defect: Dockerfile hardcoded port 8052 (compose routes 8059) AND `config.py` read the wrong env var name (`TRANCEFLOW_PORT` instead of compose's `PORT`) — a compounding double defect. Fixed both. Verified via reload that `config.py`'s default now resolves to 8059. Positive finding: real, enforced `X-Internal-Secret` auth with a correct warn-don't-fallback pattern for a missing secret, better security posture than several other entities audited in this series. |
| 2026-07-07 | Claude (session, cubic-dev-ai review triage) | `router.py` route table, `monitoring/prometheus.yml`, `docker-compose.planned-entities.yml`, `scripts/post_deploy_verify.py`, `.env.example`, `workers/imaginarium/main.py` | Verified and fixed two further cubic findings. (1) The HTTP-surface table only marked `POST /projects` as auth-required; confirmed via `grep` that `router.py` calls `_auth()` on every route except `GET /health` — table corrected to mark all six non-health routes as internal-secret authed. (2) Confirmed the 8052→8059 port fix from the prior pass had not been propagated to 5 other files that still referenced the old port: `monitoring/prometheus.yml`'s scrape target, `docker-compose.planned-entities.yml` (its own `tranceflow` service block, `TRANCEFLOW_URL`, and `THREED_URL` references), `scripts/post_deploy_verify.py`'s health-check port list, `.env.example`'s `TRANCEFLOW_PORT` default, and `workers/imaginarium/main.py`'s `CAPABILITIES` port entry. All six updated to 8059; `scripts/port_registry_validate.py` re-run and passes (73 workers). |
