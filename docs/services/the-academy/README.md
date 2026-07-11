# Service Doc-Pack — The Academy

| Field | Value |
|---|---|
| **Entity** | The Academy |
| **Lead AI** | Shimshi |
| **Status** | ✅ In repo (per `CLAUDE.md` service table) — Live tier |
| **Code** | `workers/the-academy/worker.py` (391 lines, real SQLite-backed LMS, port 8056) — standalone worker, no `src/*` module, no `api.py` mount |

> **Truthfulness:** claims cite `workers/the-academy/worker.py`, `workers/the-academy/main.py`,
> `workers/the-academy/Dockerfile`, and `docker-compose.production.yml` directly. Status is owned
> by the `CLAUDE.md` service table; identity by `PLATFORM_ENTITIES.md`.
> **The most severe defect found in this doc-pack series — the real implementation was never
> deployed.** `workers/the-academy/` contains two files with an `app = FastAPI(...)` object:
> `worker.py` (391 lines — a genuine, working SQLite-backed LMS with courses, lessons,
> enrolments, and progress tracking, internal-secret auth on every write route, and completion-
> percentage logic) and `main.py` (52 lines — a placeholder stub whose `/courses` route always
> returns `{"courses": [], "message": "No courses available yet."}` and whose `/enroll` route
> always returns `{"enrolled": false, "message": "Enrollment not yet open."}`, both hard-coded).
> **The Dockerfile's `COPY main.py .` and `CMD ["python", "main.py"]` meant only the placeholder
> was ever built into the container image and run — `worker.py` was never copied in at all**,
> despite compose's `PORT=8056` env var (which only `worker.py`, not `main.py`, defaults to) and
> the `/the-academy` Traefik route being configured as if the real service were live. In
> production, every request to The Academy would have been served entirely fabricated "coming
> soon" responses, while a complete, working LMS sat unused in the same directory. **Fixed** by
> changing the Dockerfile to copy and run `worker.py` instead of `main.py`, and aligning
> `EXPOSE`/`HEALTHCHECK` to port 8056 (`worker.py`'s real default, matching compose) instead of
> 8040 (`main.py`'s default). Verified the fix by importing `worker.py` directly — it loads
> cleanly and registers its full route set.
> **Blocking finding, not yet fixed — confirmed live in production, not merely speculative.**
> `worker.py`'s `_auth()` dependency falls back to a hard-coded default
> `INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", "dev-secret")`. Checked this service's own
> `docker-compose.production.yml` block directly: unlike most other workers in this series, its
> `environment:` only sets `PORT=8056` — there is no `INTERNAL_SECRET: ${INTERNAL_SECRET:?required}`
> entry, and `worker-common` does not inject one either. **The fallback is therefore live**: every
> write route on the deployed service currently accepts the literal string `"dev-secret"` as valid
> auth. This should be treated as a pre-existing production auth bypass, not a caveat — fix by
> adding `INTERNAL_SECRET: ${INTERNAL_SECRET:?required}` to this service's compose `environment:`
> block (matching the pattern most other workers already use) as soon as a real secret value is
> provisioned for it.
> **Second infra defect found and fixed this pass:** compose's Traefik rule for this service was
> ``PathPrefix(`/the-academy`)`` with **no StripPrefix middleware**, while `worker.py`'s routes are
> all unprefixed (`/health`, `/courses`, `/enrolments`, `/progress`, …). Unlike several other
> path-prefixed services in the same compose file (`cranbania`/`/townhall`, `/prefect`, `/temporal`,
> `/dagster`, `/kestra`, `/jaeger`, `/netdata` — each of which defines its own
> `stripprefix` middleware), The Academy's router had none, so every external request to
> `/the-academy/<anything>` would have been forwarded to the container with the prefix intact,
> which `worker.py` does not understand — a real 404 on every route in production. Fixed by adding
> `traefik.http.routers.the-academy.middlewares=strip-the-academy@docker` and
> `traefik.http.middlewares.strip-the-academy.stripprefix.prefixes=/the-academy` to the compose
> labels, matching the established pattern used elsewhere in the same file.

## 1. Service Governance Charter (GOV)

- **Mission:** learning management system — course/lesson authoring, enrolment, and progress
  tracking with automatic course-completion detection.
- **Owner (RACI-A):** Shimshi; Platform Owner Trancendos.
- **Scope:** `workers/the-academy/worker.py` — the only real implementation. `main.py` is a
  placeholder that, per this pass's fix, is no longer what's deployed.

## 2. Detailed Design Document (DDD)

### HTTP surface (`worker.py`, no route prefix)

| Method | Route | Backing |
|---|---|---|
| GET | `/health` | live course/enrolment counts from SQLite — a real health probe, not static |
| GET | `/metrics` | Prometheus-format `requests_total`/`errors_total`/`uptime_seconds` counters |
| POST | `/courses` | create a course; internal-secret authed |
| GET | `/courses` | list with `category`/`difficulty`/`published` filters, pagination |
| GET | `/courses/{id}` | course detail including its ordered lessons; 404 if missing |
| PATCH | `/courses/{id}/publish` | sets `published=1` |
| POST | `/courses/{id}/lessons` | add a lesson; 404 if course missing |
| POST | `/enrolments` | enrol a user; idempotent — returns the existing row with `already_enrolled: true` on a duplicate (`UNIQUE(user_id, course_id)` constraint) rather than erroring |
| GET | `/enrolments` | filter by `user_id`/`course_id` |
| POST | `/progress` | mark a lesson complete; **auto-detects course completion** by comparing completed-lesson count to total-lesson count, and stamps `enrolments.completed_at` when the course is finished |
| GET | `/progress/{user_id}` | per-user progress, optional `course_id` filter |

### Auth (`_auth()`)
- Every write route (and most read routes) requires `X-Internal-Secret` matching `INTERNAL_SECRET`
  — real, functioning auth, unlike the majority of `src/*`-mounted entities audited earlier in
  this series which had none at all. See the `dev-secret` fallback caveat in the truthfulness
  header.
- `_auth()` also increments module-level `_req_count`/`_err_count` counters, feeding `/metrics`.

### Data model (SQLite, `init_db()`)
- 4 tables: `courses`, `lessons` (FK → courses), `enrolments` (FK → courses, unique per user+course),
  `progress` (FK → lessons, unique per user+lesson). WAL journal mode + `synchronous=NORMAL` — a
  reasonable, real durability/performance tradeoff for a single-writer SQLite workload.
- Indexes on `lessons.course_id`, `enrolments.user_id`, `progress.user_id` — real, sensible schema
  design, not a scaffold.

## 3. Technical Architecture Solutions Design (TASD)

- **Style:** standalone FastAPI + SQLite worker, no shared state with the main `api.py` app or
  any `src/*` module — genuinely self-contained.
- **Fixed defect:** the deployed container ran the placeholder `main.py` instead of the real
  `worker.py` — see truthfulness header. This is categorically the most severe class of defect in
  this doc-pack series: not a broken endpoint or a missing feature, but the entire real service
  being unreachable while a fake one served all traffic under the same name and route.
- **Not fixed:** the `INTERNAL_SECRET` default-fallback risk — verifying and enforcing that the
  compose deployment actually sets a real secret (rather than relying on the code-level fallback)
  is an infrastructure/ops verification task, not a code change, and wasn't confirmed either way
  in this pass.

## 4. RACI Matrix

| Activity | Shimshi (Lead) | Platform Owner | Platform Engineering |
|---|---|---|---|
| Course/lesson/enrolment/progress logic changes | **R** | A | C |
| Deployment/Dockerfile correctness (fixed this pass) | C | **A** | **R** |
| `INTERNAL_SECRET` provisioning verification (future) | I | **A** | **R** |

## 5. Solutions Integration Model (SIM)

- **Upstream:** any caller with the correct `X-Internal-Secret` header — genuinely authed, unlike
  most entities in this series.
- **Downstream:** none — self-contained SQLite worker with no calls to other platform entities.
- **Deployment:** Traefik routes `/the-academy` (per compose labels) to this worker's port 8056 —
  now correctly serving the real implementation post-fix.

## 6. Architecture Scalability Document (ASD)

- **Load model:** SQLite with WAL mode — suitable for the platform's stated low/moderate LMS load;
  not designed for high-concurrency writes.
- **Bottleneck:** single SQLite file, single container — no read replicas or horizontal scaling.
- **Zero-cost limits:** SQLite is zero-cost, self-hosted, no external dependency.
- **Degradation:** none needed — no external calls exist to degrade from.

## 7. Deployment Scope Matrix (DSM)

- **Mode awareness:** No — this entity's own code does not call `PlatformInfraMode` / `src/platform/infrastructure_mode.py` (repo-wide grep confirms none of the 43 named platform entities branch on `PLATFORM_INFRA_MODE`/`SYSTEM_MODE` directly). Its deployment scope is determined externally — by which `docker-compose.production.yml` service block runs, and where — not by in-process mode detection.
- **Runtime placement:** standalone worker with its own `docker-compose.production.yml` service block (`the-academy`, port 8056) and its own Traefik route — does not run inside the `tranc3-backend` monolith
- **Persistence:** **no named volume** on the `the-academy` compose service — any on-disk state is lost on container replace/redeploy in every mode alike

| Setup | What runs, and where | Data locality | Hard blockers / caveats |
|---|---|---|---|
| **Cloud-Only** | the `the-academy` compose block runs on a single cloud host; Traefik/edge in front | ephemeral — no volume means state does not survive a redeploy | if this worker writes any local file it needs to keep, that data is at risk on every mode until a volume is added |
| **Hybrid** | same `the-academy` compose block; per `docs/architecture/infrastructure-modes.md`'s Hybrid diagram, this worker itself still runs as a single instance (cloud or local host), with only shared persistent data (not specific to this worker) split via TrueNAS/Syncthing | as above, optionally local-synced if a volume exists | requires `CITADEL_LOCAL_STACK=true` if a local compose stack should run alongside the cloud one |
| **Local-Only** | same `the-academy` compose block, run entirely on local/Citadel hardware behind local Traefik | fully local (still no volume — same durability gap as Cloud-Only) | none beyond standard local-hardware ops |

- **Zero-cost posture per mode:** Cloud-Only defaults to the `zero_cost_cloud` AI-rotation chain; Hybrid/Local-Only default to `zero_cost_full` (`config/platform/infrastructure_mode.yaml`) — this only affects AI-Gateway-routed calls, not this entity's own logic
- **Switching modes:** operator-level via `PLATFORM_INFRA_MODE` (or legacy `SYSTEM_MODE`); this entity needs no code change to move between modes, only a redeploy-target change for its own compose block

## 8. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Web framework | FastAPI, standalone (no `api.py` mount) | self-hosted, port 8056 |
| Storage | SQLite (WAL mode) | zero infra cost, durable |
| Auth | `X-Internal-Secret` header check | zero cost, real enforcement (with the fallback caveat above) |

## 9. Policy (POL)

- Auth is real and enforced on write routes — a positive finding relative to most entities in
  this series.
- **Deployment policy gap (fixed):** a Dockerfile that copies and runs the wrong source file is a
  deploy-breaking class of defect that should be caught by an integration/smoke test hitting real
  routes post-deploy (e.g. confirming `/courses` returns real data, not a hard-coded "coming
  soon" stub) — no such test currently exists for this worker.

## 10. Procedure (PROC)

- **Create and publish a course:** `POST /courses`, then `POST /courses/{id}/lessons` per lesson,
  then `PATCH /courses/{id}/publish`.
- **Enrol and track progress:** `POST /enrolments`, then `POST /progress` per completed lesson —
  course completion is detected automatically once all lessons are marked complete.

## 11. Runbook (RUN)

- **`/courses` always returns an empty list / `/enroll` always says "not yet open":** this was
  the exact symptom of the pre-fix defect (the placeholder `main.py` being deployed instead of
  `worker.py`) — confirm the Dockerfile's `COPY`/`CMD` reference `worker.py` if this recurs.
- **A write route returns 401:** confirm the caller sends a correct `X-Internal-Secret` header
  matching the deployed `INTERNAL_SECRET` env var. **Until `INTERNAL_SECRET` is added to this
  service's compose `environment:` block, the literal string `dev-secret` is currently accepted in
  production — this is a known, unfixed auth bypass, not acceptable-by-design behavior.**
- **Every route 404s in production despite the container being healthy:** was the exact symptom of
  the pre-fix Traefik defect (``PathPrefix(`/the-academy`)`` with no `StripPrefix` middleware,
  while `worker.py`'s routes are unprefixed) — fixed this pass by adding a `strip-the-academy`
  middleware to the compose labels; confirm it's still present if this recurs.
- **Course completion isn't detected:** check that every lesson under the course has a
  corresponding `progress` row with `completed=1` for that user — completion is computed by
  comparing counts, not a stored flag.

## 12. Standards (STD)

- Naming: canonical entity name "The Academy" per `CLAUDE.md`/`PLATFORM_ENTITIES.md`.
- Any worker directory containing more than one file with an `app = FastAPI(...)` object MUST have
  its Dockerfile's `COPY`/`CMD` reviewed explicitly to confirm which one is actually deployed —
  the defect fixed here (a placeholder silently shipped instead of the real implementation) is
  the reason for this standard. A basic post-deploy smoke test asserting non-placeholder responses
  would have caught this immediately.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-05 | Claude (session) | `workers/the-academy/worker.py` (391 lines), `main.py` (52 lines), `Dockerfile`, `docker-compose.production.yml` | Confirmed Live-tier, full pack authored. Found and fixed the most severe defect in this doc-pack series: the Dockerfile only copied and ran the placeholder `main.py` (hard-coded "coming soon" responses), never the real, fully-functional SQLite-backed LMS in `worker.py` — meaning the deployed service served fabricated stub responses while a complete implementation sat unused in the same directory. Fixed by changing the Dockerfile to copy/run `worker.py` and aligning its port to 8056 (matching compose and `worker.py`'s own default). Verified the fix by importing `worker.py` directly — loads cleanly, registers its full route set. Import-only verification does not confirm the Docker build, container `CMD`, healthcheck, or Traefik routing actually work end-to-end in a real deployment — flagged as a scope limit of this check, not claimed as full E2E verification. |
| 2026-07-07 | Claude (session, cubic-dev-ai review triage) | `docker-compose.production.yml` (this service's block), `workers/the-academy/worker.py` route table | Verified and fixed two further defects raised by cubic. (1) Confirmed via `grep` that compose's `the-academy` block set only `PORT=8056` in `environment:`, with no `INTERNAL_SECRET` entry and no injection from `worker-common` — the `"dev-secret"` fallback in `worker.py`'s `_auth()` is therefore live in production, not speculative; re-classified from "secondary finding" to a blocking, unfixed auth bypass (fix requires provisioning a real secret and adding `INTERNAL_SECRET: ${INTERNAL_SECRET:?required}` to this service's environment block — not done in this pass since it requires a real secret value). (2) Confirmed compose's Traefik rule used ``PathPrefix(`/the-academy`)`` with no `StripPrefix` middleware, while `worker.py`'s routes (`/health`, `/courses`, `/enrolments`, `/progress`, …) are unprefixed — cross-checked against `worker-common`'s shared labels (confirmed it defines no middleware at all) and against other path-prefixed services in the same file (`cranbania`, `prefect`, `temporal`, `dagster`, `kestra`, `jaeger`, `netdata` — each defines its own `stripprefix` middleware), confirming The Academy was the outlier and every route would 404 in production. Fixed by adding a `strip-the-academy` middleware to the compose labels. |
