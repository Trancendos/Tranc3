# Service Doc-Pack — The Studio

| Field | Value |
|---|---|
| **Entity** | The Studio |
| **Lead AI** | Voxx |
| **Status** | ✅ In repo (per `CLAUDE.md` service table) — Live tier |
| **Code** | `src/studio/hub.py`, `src/studio/routes.py`; router registered in `api.py` (`app.include_router(_studio_router)`, line 838) — **plus a separate standalone worker**, `workers/the-studio/worker.py` (SQLite: projects/assets/collaborators/time_entries/feedback) |

> **Truthfulness:** claims cite `src/studio/hub.py` and `src/studio/routes.py` directly. Status is
> owned by the `CLAUDE.md` service table (Live tier); identity by `PLATFORM_ENTITIES.md`.
> **Scope note (cubic-flagged):** The Studio has **two independent implementations** — the
> `src/studio/` module mounted into the main `api.py` app (documented below in full), and a
> separate standalone `workers/the-studio/worker.py` with its own SQLite persistence (projects,
> creative assets, collaborators, time entries, feedback) that this pack does **not** cover in
> detail. Every claim below that says "no worker" or "no persistence" refers specifically to the
> `src/studio/*` path, not to the entity as a whole.
> **Important scope note:** the code itself describes this module as a **scaffold/orchestration
> shell** — every sub-service capability manifest is self-labelled `"status": "planned"` except
> Imaginarium's own manifest entry, which is labelled `"scaffold"`. This pack documents the
> orchestration layer that genuinely exists (job submission, tracking, capability listing); it does
> **not** claim the underlying creative backends (ComfyUI, FFmpeg, Godot, Penpot) are wired in,
> because the code says they are not.

## 1. Service Governance Charter (GOV)

- **Mission:** central hub of the Creativity Center — job-submission/orchestration shell for
  Sashas Photo Studio, TateKing, TranceFlow, Fabulousa, and Imaginarium.
- **Owner (RACI-A):** Voxx; Platform Owner Trancendos.
- **Scope:** accept and track creative jobs tagged by sub-service, expose a capability manifest per
  sub-service, and (per code comments) eventually dispatch jobs to real backends once those are
  wired in. Actual dispatch/backend integration is **out of current scope** — not implemented.

## 2. Detailed Design Document (DDD)

### HTTP surface (`src/studio/routes.py`, prefix `/studio`)

| Method | Route | Backing |
|---|---|---|
| GET | `/studio/status` | `TheStudio.stats()` — total jobs, by-status counts, sub-service enum list |
| GET | `/studio/capabilities` | `TheStudio.capabilities()` — static manifest per `StudioServiceType` |
| POST | `/studio/jobs` | `TheStudio.submit_job()` — body `{"service": <enum value>, "payload": {...}}`; 400 on unknown service |
| GET | `/studio/jobs` | `TheStudio.list_jobs()` — optional `service` filter, most-recent-50 |
| GET | `/studio/jobs/{job_id}` | `TheStudio.get_job()` — 404 `JSONResponse` if not found |

### Data model
- `StudioServiceType` enum: `sashas-photo-studio`, `tatekings` (note: literal enum value is
  `"tatekings"`, plural, not `"tateking"` — a real naming inconsistency in the code, cited as-is),
  `tranceflow`, `fabulousa`, `imaginarium`.
- `StudioJob`: `id` (uuid4), `service`, `created_at`, `status` (`JobStatus`: queued/processing/
  complete/failed), `payload`, `result`, `error`.
- `_CAPABILITIES` dict: static, hard-coded manifest per service — name, description, foundation
  (e.g. "Stable Diffusion / ComfyUI"), capability list, and a `"status"` field that is
  `"planned"` for all four creative sub-services and `"scaffold"` for Imaginarium.

### Job lifecycle
- `submit_job()` creates a `StudioJob` in `QUEUED` status, stores it, fires an Observatory event
  (`studio.job.submitted`), and returns it. **There is no code path that transitions a job out of
  `QUEUED`** — no worker, dispatcher, or status-update logic exists in this module. Jobs will
  remain `queued` indefinitely unless something external updates them (nothing in this repo does).
- `_emit()` wraps the Observatory `observe()` call in a bare `except Exception: pass` (annotated
  `# nosec B110`) — event emission failures are silently swallowed by design.

## 3. Technical Architecture Solutions Design (TASD)

- **Style (`src/studio/*` API path only):** in-process orchestration shell with a module-level
  singleton (`get_studio()`) — no external queue or persistence on this path. A separate
  `workers/the-studio/worker.py` standalone service also exists for this entity and does use
  SQLite persistence — see the scope note above; this DDD/TASD does not cover it.
- **Decision: job tracking without execution.** The module intentionally models the job
  submission/tracking API ahead of backend integration — this is a legitimate scaffolding pattern,
  but it means `POST /studio/jobs` currently creates records that never progress past `queued`.
  Any caller expecting async processing will not observe status changes.
- **Decision: capability manifest as static data**, not a live backend health check — the
  `"status": "planned"` fields are literal source, not derived from probing ComfyUI/FFmpeg/Godot/
  Penpot availability.

## 4. RACI Matrix

| Activity | Voxx (Lead) | Platform Owner | Sub-service Leads (Krystal/Benji/Cesar/Von Hilton) | Platform Engineering |
|---|---|---|---|---|
| Job-tracking API changes | **R** | A | I | C |
| Backend dispatch implementation (future) | C | **A** | **R** (per sub-service) | C |
| Capability manifest updates | **R/A** | I | C | I |

## 5. Solutions Integration Model (SIM)

- **Upstream:** any caller of `POST /studio/jobs` — no auth on any route in `routes.py`.
- **Downstream:** The Observatory, via a best-effort `observe()` call on job submission (failures
  silently swallowed); **no downstream call to any creative backend** — dispatch is not
  implemented.
- **Cross-entity note:** the sub-services this module names (Sashas Photo Studio, TateKing,
  TranceFlow, Fabulousa, Imaginarium) each have their own separate `workers/<name>/worker.py`
  standalone service (see their own doc-packs) — The Studio's `hub.py` does **not** call into any
  of those workers; they are entirely independent code paths today.

## 6. Architecture Scalability Document (ASD)

- **Load model:** in-memory job dict, no cap defined (`_jobs: Dict[str, StudioJob]` grows
  unbounded — no eviction logic, unlike The Basement's `MAX_RECORDS` pattern).
- **Bottleneck:** single-process, no persistence; a restart loses all job history.
- **Zero-cost limits:** no external dependency at all in this module — the cost is entirely
  deferred to whichever backend (ComfyUI/FFmpeg/Godot/Penpot) is eventually wired in.
- **Degradation:** none needed yet — there is no live backend to degrade from.

## 7. Deployment Scope Matrix (DSM)

- **Mode awareness:** No — this entity's own code does not call `PlatformInfraMode` / `src/platform/infrastructure_mode.py`. (Some platform-wide, cross-cutting code *does* branch on the mode — `src/routers/adaptive.py` and `src/routers/ecosystem.py` read/set `PLATFORM_INFRA_MODE`/`SYSTEM_MODE` directly, and `Dimensional/architecture/storage_factory.py` selects a storage provider from `SYSTEM_MODE` — but none of that code is owned by this or any other one of the 43 named entities; it is shared platform infrastructure, not this service's own logic. The Citadel is the only one of the 43 named entities whose own code branches on the mode — see `docs/services/the-citadel/README.md`.) This entity's deployment scope is determined externally — by which `docker-compose.production.yml` service block runs, and where — not by in-process mode detection.
- **Runtime placement:** mounted in the `tranc3-backend` monolith (`api.py`); runs wherever that monolith's `docker-compose.production.yml` service block is deployed, on whatever port/host the monolith uses (compose service `tranc3-backend`)
- **Persistence:** None — this entity's own state is an in-memory `_jobs: Dict[str, StudioJob]` (per this pack's own TFM/ASD), with no persistence of its own. While the `tranc3-backend` monolith has a named volume, that volume backs *other* entities' state, not this one; this service's own state (if any) is lost on restart/redeploy in every mode alike.

| Setup | What runs, and where | Data locality | Hard blockers / caveats |
|---|---|---|---|
| **Cloud-Only** | the `tranc3-backend` compose block runs on a single cloud host (e.g. Fly.io / Oracle Free Tier); Traefik/edge in front | ephemeral — this service holds no state of its own; the monolith's volume does not apply to it | no entity-specific blocker beyond whatever applies to the monolith as a whole |
| **Hybrid** | same monolith block; per `docs/architecture/infrastructure-modes.md`'s Hybrid diagram, persistent data can sync to local TrueNAS while the monolith itself still runs wherever it's deployed | ephemeral, same as Cloud-Only — this service's own state does not benefit from the Hybrid data-locality split | requires `CITADEL_LOCAL_STACK=true` if a local compose stack should run alongside the cloud one, per `should_run_citadel_docker()` in `infrastructure_mode.py` |
| **Local-Only** | same monolith block, run entirely on local/Citadel hardware behind local Traefik | still ephemeral — local hardware does not change this service's own statelessness | none beyond standard local-hardware ops (backup, power, network) |

- **Zero-cost posture per mode:** Cloud-Only defaults to the `zero_cost_cloud` AI-rotation chain; Hybrid/Local-Only default to `zero_cost_full` (`config/platform/infrastructure_mode.yaml`) — this only affects AI-Gateway-routed calls, not this entity's own logic
- **Switching modes:** operator-level via `PLATFORM_INFRA_MODE` (or legacy `SYSTEM_MODE`); this entity needs no code change to move between modes, only a redeploy-target change for the monolith as a whole

## 8. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Web framework | FastAPI `APIRouter` | mounted into the main `api.py` app |
| Job storage | in-memory `dict`, no persistence | zero infra cost, no durability |
| Backend dispatch | **not implemented** | N/A — deferred to future ComfyUI/FFmpeg/Godot/Penpot integration |

## 9. Policy (POL)

- No route-level auth currently implemented — see SIM §5.
- Zero-cost mandate: any future backend integration (ComfyUI, FFmpeg, Godot, Penpot) must pass
  `scripts/zero_cost_audit.py` per The Citadel's deploy gate.

## 10. Procedure (PROC)

- **Submit a job:** `POST /studio/jobs` with `{"service": "sashas-photo-studio", "payload": {...}}`
  — returns a job record in `queued` status that will not currently progress further.
- **List capabilities:** `GET /studio/capabilities` — static manifest, useful for discovering
  which sub-services exist and their intended feature set (not their live availability).

## 11. Runbook (RUN)

- **Jobs stuck in `queued` forever:** expected — no dispatcher exists yet. This is not a bug to
  triage; it's the current (pre-backend-integration) state of the module.
- **`POST /studio/jobs` returns 400 "Unknown service":** the `service` value in the request body
  doesn't match a `StudioServiceType` enum value — valid values are listed in the error response.
- **Observatory events missing for a job:** `_emit()` swallows all exceptions silently
  (`# nosec B110`) — check The Observatory's own logs/health, not this module, for emission
  failures.

## 12. Standards (STD)

- Naming: canonical entity name "The Studio" per `CLAUDE.md`/`PLATFORM_ENTITIES.md`; note the
  `StudioServiceType.VIDEO` enum value is literally `"tatekings"` (plural) while the canonical
  entity name is "TateKing" (singular) — a real inconsistency in the code, flagged here rather
  than silently normalized in this doc.
- Any future dispatch implementation MUST update this pack's DDD/TASD before being considered
  part of "The Studio" per the framework's honesty gate — do not let real backend wiring land
  without a corresponding doc update.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-04 | Claude (session) | `src/studio/hub.py` (185 lines), `src/studio/routes.py` (56 lines), `api.py` router registration (line 838) | Confirmed Live-tier per `CLAUDE.md` status, full pack authored. Code-grounded finding: the orchestration shell is real and live-wired, but all sub-service backends are self-labelled "planned"/"scaffold" in the capability manifest, and no job ever transitions out of `queued` — documented explicitly rather than glossed over. `tatekings` enum-value/naming inconsistency also flagged. |
