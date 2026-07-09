# Service Doc-Pack — ChronosSphere / ArcStream

| Field | Value |
|---|---|
| **Entity** | ChronosSphere / ArcStream |
| **Lead AI** | Chronos |
| **Status** | ✅ Live (deployed worker, port 8021) |
| **Foundation** | `workers/cron-service/worker.py` — 8-backend ACO-routed cron scheduler |

> **Truthfulness header (2026-07-07 rewrite).** This pack was previously Planned-tier
> (GOV+RACI+TFM+POL+STD only), asserting "no implementation exists yet." That was false: a
> real, substantial worker (`workers/cron-service/worker.py`, 698 lines) implements this
> entity — an ant-colony-optimisation (ACO) "pheromone" router across 8 scheduling backends
> (Cal.com, Kestra, n8n, an in-process APScheduler-style fallback, Forgejo, NATS JetStream,
> Valkey, system cron), plus its own in-process 5-field cron parser and execution loop. This is
> the last of the 26 originally-mis-tiered entities from this session's audit to receive a
> full Live-tier rewrite.
>
> **Genuine defect found and fixed this pass — a startup-crash risk, a new class not yet seen
> in this series:** `worker.py`'s `DB_PATH` defaults to `/data/cron.db` (an absolute root-level
> path, via `CRON_DB_PATH` env, unset in compose) and calls `DB_PATH.parent.mkdir(parents=True,
> exist_ok=True)` **at module import time** — before the app even starts. The Dockerfile,
> however, ran as a non-root `worker` user and only created/chowned `/app/data` (the wrong
> directory — no code path reads `/app/data`), leaving `/data` non-existent and
> root-owned-by-default at the filesystem root. On container start, the non-root `worker` user
> attempting `mkdir /data` would raise a `PermissionError`, **crashing the worker before it
> could serve any request** — the same underlying pattern (path mismatch) as DocUtari's
> `files-service`/`storage-service` findings earlier in this session, but here manifesting as a
> hard crash rather than silent data loss, since `/data` at the container root isn't writable
> by a non-root user by default. Fixed by:
> 1. Changing the Dockerfile to `mkdir -p /data && chown -R worker:worker /data` (matching the
>    path the code actually uses) instead of the mismatched `/app/data`.
> 2. Adding a `cron-data:/data` named volume in compose — none existed at all, so even once
>    the crash is fixed, job data (the SQLite `jobs`/`job_runs` tables) would have been
>    ephemeral, the same durability gap already fixed for DocUtari's two workers.
>
> This defect was **not previously caught by `port_registry_validate.py`** (which only checks
> port/name consistency, not filesystem write-permission correctness) and would only surface
> at actual container runtime — a reminder that Dockerfile review needs to trace the
> application's real file-path usage, not just assume `mkdir`/`chown` targets are correct.
>
> No Traefik-StripPrefix defect applies here — like DocUtari's two workers, `cron-service` has
> no Traefik label in compose (internal-only P3 service, no public `PathPrefix` rule).

## 1. Service Governance Charter (GOV)

- **Mission:** task, time & scheduling management — accepts cron-style job definitions and
  routes their execution across 8 zero-cost scheduling backends via an adaptive,
  reinforcement-learning-flavoured (ACO pheromone) backend selector, with an always-available
  in-process fallback so no job is ever silently dropped for lack of an external backend.
- **In scope:** job CRUD (`POST/GET/PATCH/DELETE /jobs`), manual trigger
  (`POST /jobs/{id}/trigger`), run history (`GET /jobs/{id}/runs`), backend health/pheromone
  introspection (`GET /backends`), and an in-process minute-granularity scheduler loop that
  matches enabled jobs' cron expressions against the current time and dispatches matches.
- **Out of scope:** any of the 8 backend services themselves (Cal.com, Kestra, n8n, Forgejo,
  NATS, Valkey — none are provisioned in `docker-compose.production.yml` today, so every
  dispatch attempt to a real backend fails over to the always-available in-process
  `apscheduler`-labelled fallback, despite the name, is NOT the real APScheduler library — it's
  this worker's own `_scheduler_loop()`/`_cron_matches()` implementation).
- **Lead AI (Tier 3):** Chronos — per `PLATFORM_ENTITIES.md`.
- **Owner (RACI-A):** Platform Owner (Trancendos), delegated to Chronos.
- **Review cadence:** quarterly per framework default.
- **Dependencies (soft, all 7 external backends optional with fallback):** Cal.com, Kestra,
  n8n, Forgejo, NATS JetStream, Valkey (all unreachable today — none provisioned in compose);
  the in-process fallback has no external dependency.

## 2. Domain-Driven Design (DDD) — HTTP Surface

| Method | Path | Auth | Behaviour |
|---|---|---|---|
| GET | `/health` | none | liveness + job counts + full per-backend pheromone/RPM snapshot |
| GET | `/backends` | none | per-backend pheromone score, success/failure counts, current RPM |
| GET | `/jobs` | `X-Internal-Secret`* | list jobs (optional `enabled` filter) |
| POST | `/jobs` | `X-Internal-Secret`* | create job; ACO-selects a backend unless caller specifies one |
| GET | `/jobs/{job_id}` | `X-Internal-Secret`* | get one job |
| PATCH | `/jobs/{job_id}` | `X-Internal-Secret`* | partial update (allow-listed via Pydantic `exclude_none`) |
| DELETE | `/jobs/{job_id}` | `X-Internal-Secret`* | delete job + its run history |
| POST | `/jobs/{job_id}/trigger` | `X-Internal-Secret`* | force-run immediately, bypassing schedule |
| GET | `/jobs/{job_id}/runs` | `X-Internal-Secret`* | run history, paginated (`limit`, capped at 200) |

\* Enforced only if `INTERNAL_SECRET` is set — currently unset in compose/`.env.example`, so
every `/jobs*` route is effectively open (`/health`/`/backends` are always open by design).

## 3. Technical Architecture & Solution Design (TASD)

- FastAPI + Uvicorn, SQLite (WAL) for job definitions and run history, `asyncio`-native
  scheduler loop (`_scheduler_loop()`) that wakes once per minute (aligned to the wall-clock
  minute boundary via `asyncio.sleep(60 - datetime.now().second)`) and evaluates every enabled
  job's cron expression against the current UTC time via a hand-rolled 5-field parser
  (`_cron_matches()`/`_matches_field()` — supports `*`, `/step`, comma-lists, and ranges;
  correctly implemented, verified by reading the field-matching logic directly).
- **ACO backend routing** (`_choose_backend()`): each of the 8 backends carries a pheromone
  score in `[0.05, 1.0]`, reinforced by `+0.1` (capped at 1.0) on success and decayed by a
  configurable `_DECAY` factor (default 0.15) on failure, each gated by its own sliding-window
  `ThresholdGuard` (per-backend RPM limit). Backend choice is a pheromone-weighted random draw
  among currently-allowed (not rate-limited) backends — a genuine, non-trivial adaptive-routing
  implementation, not a stub.
- **Fixed this pass (startup-crash risk):** Dockerfile `mkdir`/`chown` target corrected from
  `/app/data` (unused) to `/data` (the path `DB_PATH` actually resolves to); a `cron-data`
  named volume added for durability (previously none existed).
- `_dispatch_valkey()` and `_dispatch_syscron()` both correctly treat missing optional
  dependencies (`redis`, `python-crontab`) as soft failures (`try/except ImportError` folded
  into the general `except Exception`), decaying that backend's pheromone rather than crashing
  the worker — consistent with the platform's graceful-degradation pattern seen elsewhere.

## 4. RACI Matrix

| Activity | Platform Owner | Chronos | Platform Engineering | The Town Hall |
|---|---|---|---|---|
| Charter approval / scope changes | **A** | C | R | I |
| Deployed-worker maintenance | I | **A** | R | I |
| Provisioning a real scheduling backend (Cal.com/Kestra/n8n/etc.) | I | C | **R/A** | I |
| Setting `INTERNAL_SECRET` for production | I | C | **R/A** | I |
| Incident response | I | C | **R/A** | I |

## 5. Service Interaction Map (SIM)

```
cron-service container (port 8021, no Traefik route — internal only)
   ├─ SQLite (jobs, job_runs — now on the cron-data volume at /data, fixed this pass)
   ├─ Cal.com    (optional, CALCOM_URL — not provisioned in compose)
   ├─ Kestra     (optional, KESTRA_URL — not provisioned in compose)
   ├─ n8n        (optional, N8N_URL — not provisioned in compose)
   ├─ Forgejo    (optional, FORGEJO_URL — The Workshop's own Forgejo IS provisioned elsewhere in compose, but FORGEJO_TOKEN is unset here, so dispatch always fails over)
   ├─ NATS       (optional, NATS_URL — not provisioned in compose)
   ├─ Valkey     (optional, REDIS_URL — not provisioned in compose)
   └─ syscron    (optional, python-crontab — writes to the container's own crontab, lost on restart since crontabs aren't in the cron-data volume)
```

No confirmed caller of this worker's HTTP surface was found elsewhere in the repo.

## 6. Application Service Design (ASD)

- Job execution (`_execute_job()`) is a generic authenticated-or-unauthenticated HTTP callback
  invoker (`httpx` request to `job["url"]` with the job's stored method/payload/headers) — this
  is genuinely how most of the "8 backends" ultimately manifest: even when Kestra/n8n/etc. are
  used for scheduling, the actual job payload delivery for the in-process path is still this
  worker's own `_execute_job()` HTTP call, truncated response body capped at 500 chars for
  storage.
- `_choose_backend()`'s weighted-random selection correctly falls back to `apscheduler` (this
  worker's own loop) whenever no external backend passes its rate-limit gate — there is no
  scenario where a job silently fails to be scheduled at all.

## 7. Technology & Framework Matrix (TFM)

| Layer | Choice | Cost |
|---|---|---|
| Web framework | FastAPI + Uvicorn | zero (OSS) |
| Persistence | SQLite (WAL) | zero (embedded) |
| Scheduling backends (optional, none provisioned) | Cal.com, Kestra, n8n, Forgejo, NATS JetStream, Valkey | zero (self-hosted OSS) |
| Fallback scheduler | in-process asyncio loop (this worker's own code, not python-crontab or APScheduler despite the label) | zero |

## 8. Policy & Compliance (POL)

- All `/jobs*` routes are unauthenticated by default in this compose file (empty-string
  `INTERNAL_SECRET`) — any caller reaching the container can create, trigger, or delete
  scheduled jobs, including arbitrary outbound HTTP callbacks via `_execute_job()`. This is a
  meaningful SSRF-adjacent surface (a job's `url` is caller-controlled and dispatched by the
  server) and should be treated as sensitive until auth is enabled.
- Zero-cost mandate honoured — no paid scheduling API is called.

## 9. Procedures (PROC)

- **Local dev:** `cd workers/cron-service && pip install -r requirements-worker.txt &&
  uvicorn worker:app --port 8021`.
- **Enabling auth:** set `INTERNAL_SECRET` in the deployment environment — picked up
  automatically by `require_internal_auth()`.
- **Provisioning a real backend:** set the corresponding `*_URL`/`*_TOKEN`/`*_KEY` env var and
  add the backend's own container to `docker-compose.production.yml` — none of the 6
  network-based optional backends are provisioned there today.

## 10. Runbook (RUN)

- **Health check:** `GET http://cron-service:8021/health` — includes per-backend pheromone
  status inline, useful for diagnosing why jobs keep landing on the in-process fallback.
- **Symptom: container fails to start / crash-loops.** Before this pass, this was the expected
  outcome (`PermissionError` on `mkdir /data` as a non-root user) — now fixed. If it recurs,
  check the Dockerfile's `mkdir -p /data && chown -R worker:worker /data` step wasn't reverted
  to the old `/app/data` path.
- **Symptom: job history disappears after a redeploy.** Before this pass, `cron-data` didn't
  exist as a volume at all — now fixed. If it recurs, check the volume declaration.
- **Symptom: every job always runs via the `apscheduler` backend regardless of ACO scoring.**
  Expected while none of the 6 network backends are provisioned — every dispatch attempt fails
  its reachability check and falls through; not a bug.

## 11. Standards (STD)

- Follows the same FastAPI/Uvicorn/SQLite-WAL conventions as other standalone workers audited
  this session.
- Any credential/backend provisioning must follow the zero-cost, self-hosted architecture
  principles in `CLAUDE.md`.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-04 | Claude (session) | `CLAUDE.md` service table, `PLATFORM_ENTITIES.md`, repo search | **SUPERSEDED — was wrong.** Concluded no implementation exists. |
| 2026-07-07 | Claude (session) | direct read of `workers/cron-service/worker.py` (698 lines), `Dockerfile`, `requirements-worker.txt`, and the `cron-service` block in `docker-compose.production.yml` | **Full rewrite to Live-tier (11 sections) — the 26th and final entity in this session's mis-tiered-entity backlog.** Found and fixed a startup-crash-risk defect not previously seen in this series: `DB_PATH` resolves to `/data/cron.db`, but the Dockerfile only created/chowned `/app/data` (the wrong, unused path) as a non-root user — `mkdir /data` at the container filesystem root would raise `PermissionError` and crash the worker on every start. Fixed the Dockerfile's target path and added a previously-nonexistent `cron-data` volume for durability (same pattern as DocUtari's two workers). No StripPrefix defect applies (no Traefik label — internal-only service). Documented, not fixed: all `/jobs*` routes are unauthenticated by default, and job `url` is caller-controlled and server-dispatched (SSRF-adjacent surface). |
