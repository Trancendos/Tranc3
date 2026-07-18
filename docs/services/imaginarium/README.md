# Service Doc-Pack — Imaginarium

| Field | Value |
|---|---|
| **ServiceID (CMDB)** | `SRV-IMAGINARIUM-001` |
| **Entity** | Imaginarium |
| **Lead AI** | Voxx |
| **Status** | ✅ In repo (per `CLAUDE.md` service table) — Live tier |
| **Code** | `workers/imaginarium/main.py` (65 lines, honest stub) — the deployed implementation. `worker.py` (343 lines, real cross-service orchestrator with genuine auth) exists but is not deployed. |

> **Truthfulness:** claims cite `workers/imaginarium/main.py`, `worker.py`, `Dockerfile`, and
> `docker-compose.production.yml` directly. Status is owned by the `CLAUDE.md` service table;
> identity by `PLATFORM_ENTITIES.md`.
> **Notable pattern, distinct from most "two implementations" cases in this series: the deployed
> file is the honest stub, and the real implementation is the one sitting unused.**
> `workers/imaginarium/main.py` (the file the Dockerfile actually builds and runs) is a genuine,
> 65-line placeholder — its `/orchestrate` route returns
> `{"orchestrated": false, "message": "Orchestration not yet ready."}` verbatim, honestly labeled,
> not a silent fake. `workers/imaginarium/worker.py` (343 lines, never referenced by the
> Dockerfile) is a **fully real implementation**: `POST /create` triggers `_fan_out_creation()`,
> a background task that makes genuine HTTP calls (via `httpx.AsyncClient`, with a real
> `X-Internal-Secret: {INTERNAL_SECRET}` header) to Sashas Photo Studio, TranceFlow, TateKing, and
> Warp Radio to actually orchestrate a multi-service creative pipeline, backed by a real SQLite
> `templates`/`projects` schema. Unlike The Academy's case (where the fake was deployed and the
> real implementation sat unused, discovered as the most severe defect in this series), this is
> the inverse: the **conservative, honest** file is what's live, and the working orchestrator is
> dormant. Not fixed in this pass (swapping the deployed file is a deployment decision requiring
> owner sign-off, not a docs-pass fix) — flagged as a clear, low-risk opportunity: promoting
> `worker.py` to deployed status would give Imaginarium its actual mission capability with
> genuine auth already built in.
> **Also found and fixed this pass, the same defect class found repeatedly across this doc-pack
> series:** `workers/imaginarium/Dockerfile` hardcoded `EXPOSE 8054` / `HEALTHCHECK ...
> localhost:8054`, and `main.py`'s own `PORT` default also fell back to `8054`, while
> `docker-compose.production.yml` sets `PORT: "8064"` and routes Traefik to container port 8064.
> Not a live defect (`main.py` is invoked via bare `python main.py`, correctly reads `PORT` at
> runtime, and compose's own healthcheck overrides the Dockerfile's) but fixed for robustness,
> consistent with recent practice on this defect class. Compose's Traefik rule was also bare
> ``PathPrefix(`/imaginarium`)`` with **no `StripPrefix` middleware**, while `main.py`'s routes
> are unprefixed — the same genuinely live routing defect already found and fixed for The
> Academy, Sashas Photo Studio, Taimra, and TateKing earlier in this series; fixed with a
> `strip-imaginarium` middleware.

## 1. Service Governance Charter (GOV)

- **Mission:** omni-creative masterpiece wizard — orchestrates Sashas Photo Studio, TranceFlow,
  TateKing, The Studio, and Warp Radio into one creative pipeline. **As deployed**, this mission
  is not yet live (the deployed `main.py` is an honest stub); the code to fulfil it exists in
  `worker.py` but isn't running.
- **Owner (RACI-A):** Platform Owner Trancendos.
- **Lead AI:** Voxx.
- **Scope:** `workers/imaginarium/main.py` (deployed) + `worker.py` (real, undeployed) — both
  documented in this pack given the unusual "real implementation exists but isn't live" finding.

## 2. Detailed Design Document (DDD)

### HTTP surface, deployed (`main.py`, no route prefix)

| Method | Route | Backing |
|---|---|---|
| GET | `/health` | static uptime — not a real dependency probe |
| GET | `/status` | static `"status": "initialising"` — honestly reflects the stub state |
| POST | `/orchestrate` | **honest stub** — always returns `{"orchestrated": false, "message": "Orchestration not yet ready."}`, HTTP 202 |
| GET | `/capabilities` | static list of 5 sub-services the entity is meant to orchestrate (name/slug/port/role), for discovery purposes only |

### HTTP surface, real-but-undeployed (`worker.py`, own `_router`, mounted at app root)

| Method | Route | Backing |
|---|---|---|
| GET | `/health` | static |
| GET | `/metrics` | Prometheus-format counters |
| POST | `/create` | creates a project row, kicks off `_fan_out_creation()` as a background task — **genuinely calls out to other services**; internal-secret authed |
| GET | `/projects` | list; internal-secret authed |
| GET | `/projects/{id}` | detail; internal-secret authed |
| GET / POST | `/templates` | list/create project templates (SQLite-backed, real seed data: "Game Asset Pack", "Brand Kit", etc.); internal-secret authed |
| GET | `/services/status` | internal-secret authed |

### `_fan_out_creation()` — real, working orchestration logic
- Builds `{"X-Internal-Secret": INTERNAL_SECRET, ...}` headers and, based on `project_type`,
  makes real `httpx.AsyncClient` calls out to the sibling creative services (image generation for
  `mixed`/`music_visual`/`video_image`/`brand`/`game_assets` project types, per the code seen in
  this pass — not traced call-by-call to every branch). This is genuine cross-entity integration
  logic, not a scaffold — the kind of implementation several other entities in this series
  (Resonate, I-Mind) were found to lack despite claiming it.
- Enforces `X-Internal-Secret` via `_auth()` on its own routes, with the same insecure
  `"dev-secret"` fallback default (`INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", "dev-secret")`)
  already flagged for The Academy/Sashas Photo Studio/TateKing — a real gap if this file were
  promoted to deployed status without also fixing that default.

## 3. Technical Architecture Solutions Design (TASD)

- **Style:** standalone FastAPI worker; the deployed `main.py` is stateless and trivial, while
  the undeployed `worker.py` is a genuine SQLite-backed orchestrator.
- **Fixed defects:** Dockerfile port mismatch (cosmetic, fixed for robustness) + Traefik
  `StripPrefix` missing (genuine, live routing defect) — see truthfulness header.
- **Not fixed, flagged as an opportunity rather than a defect:** the working orchestrator
  (`worker.py`) is not what's deployed. Swapping the Dockerfile to build/run `worker.py` instead
  of `main.py` would give this entity its actual mission capability, but requires sign-off (this
  is the opposite risk profile of The Academy's case — promoting a real implementation over a
  known-honest stub, not silently replacing a fake with something that changes behavior
  unexpectedly) and fixing the `dev-secret` fallback first.

## 4. RACI Matrix

| Activity | Voxx (Lead) | Platform Owner | Platform Engineering |
|---|---|---|---|
| Orchestration pipeline logic changes (`worker.py`) | **R** | A | C |
| Deciding whether to promote `worker.py` to deployed status (future) | C | **A** | **R** |
| Fixing `worker.py`'s `dev-secret` fallback before any promotion (future) | **R** | A | C |

## 5. Solutions Integration Model (SIM)

- **Upstream (deployed `main.py`):** any caller of `/health`, `/status`, `/orchestrate`,
  `/capabilities` — no auth, but `/orchestrate` does nothing harmful since it's a stub.
- **Upstream (undeployed `worker.py`, if promoted):** callers of `/create` etc. would need a
  correct `X-Internal-Secret` header once the `dev-secret` fallback is fixed.
- **Downstream (undeployed `worker.py` only):** real HTTP calls to Sashas Photo Studio,
  TranceFlow, TateKing, Warp Radio (all self-hosted, zero-cost per their own doc-packs).
- **Not integrated:** the deployed `main.py` never calls `worker.py` or vice versa — they are
  fully independent files sharing a directory.

## 6. Architecture Scalability Document (ASD)

- **Load model (deployed):** trivial — no state, no real work performed.
- **Load model (undeployed `worker.py`):** SQLite-backed `projects`/`templates` tables, real
  background-task fan-out via `httpx`.
- **Zero-cost limits:** fully honored on both sides — no paid dependencies in either file.
- **Degradation:** N/A for the deployed stub (nothing to degrade); `worker.py`'s fan-out logic
  was not traced for its own failure-handling depth in this pass.

## 7. Deployment Scope Matrix (DSM)

- **Mode awareness:** No — this entity's own code does not call `PlatformInfraMode` / `src/platform/infrastructure_mode.py`. (Some platform-wide, cross-cutting code *does* branch on the mode — `src/routers/adaptive.py` and `src/routers/ecosystem.py` read/set `PLATFORM_INFRA_MODE`/`SYSTEM_MODE` directly, and `Dimensional/architecture/storage_factory.py` selects a storage provider from `SYSTEM_MODE` — but none of that code is owned by this or any other one of the 43 named entities; it is shared platform infrastructure, not this service's own logic. The Citadel is the only one of the 43 named entities whose own code branches on the mode — see `docs/services/the-citadel/README.md`.) This entity's deployment scope is determined externally — by which `docker-compose.production.yml` service block runs, and where — not by in-process mode detection.
- **Runtime placement:** standalone worker with its own `docker-compose.production.yml` service block (`imaginarium`, port 8064) and its own Traefik route — does not run inside the `tranc3-backend` monolith
- **Persistence:** **no named volume** on the `imaginarium` compose service — any on-disk state is lost on container replace/redeploy in every mode alike
- **Note:** the *deployed* `main.py` is an honest stub (`/orchestrate` always returns `"orchestrated": false`) regardless of mode — promoting the real, undeployed `worker.py` orchestrator (see this pack's DDD) would not by itself change this DSM, since it has no volume either.

| Setup | What runs, and where | Data locality | Hard blockers / caveats |
|---|---|---|---|
| **Cloud-Only** | the `imaginarium` compose block runs on a single cloud host; Traefik/edge in front | ephemeral — no volume means state does not survive a redeploy | if this worker writes any local file it needs to keep, that data is at risk on every mode until a volume is added |
| **Hybrid** | same `imaginarium` compose block; per `docs/architecture/infrastructure-modes.md`'s Hybrid diagram, this worker itself still runs as a single instance (cloud or local host), with only shared persistent data (not specific to this worker) split via TrueNAS/Syncthing | as above, optionally local-synced if a volume exists | requires `CITADEL_LOCAL_STACK=true` if a local compose stack should run alongside the cloud one |
| **Local-Only** | same `imaginarium` compose block, run entirely on local/Citadel hardware behind local Traefik | fully local (still no volume — same durability gap as Cloud-Only) | none beyond standard local-hardware ops |

- **Zero-cost posture per mode:** Cloud-Only defaults to the `zero_cost_cloud` AI-rotation chain; Hybrid/Local-Only default to `zero_cost_full` (`config/platform/infrastructure_mode.yaml`) — this only affects AI-Gateway-routed calls, not this entity's own logic
- **Switching modes:** operator-level via `PLATFORM_INFRA_MODE` (or legacy `SYSTEM_MODE`); this entity needs no code change to move between modes, only a redeploy-target change for its own compose block

## 8. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Web framework (deployed) | FastAPI, standalone, honest stub | self-hosted, port 8064 (fixed this pass) |
| Web framework (undeployed) | FastAPI, standalone, real orchestrator | self-hosted |
| Storage (undeployed only) | SQLite (`templates`/`projects`) | zero infra cost |
| Auth (undeployed only) | `X-Internal-Secret` via `_auth()`, insecure `dev-secret` fallback | zero cost, currently would-be-unenforced if the fallback isn't fixed first |

## 9. Environment Support Matrix (ESM)

> Grounded against `docker-compose.development.yml`, `docker-compose.uat.yml`, and `docker-compose.production.yml` — checked by exact compose service name, not assumed (see `docs/services/INDEX.md` for current platform-wide compose service totals, which change as the topology evolves).

| Environment | Covered? | What runs | Notes |
|---|---|---|---|
| **Dev** | No | not present in `docker-compose.development.yml` (only `api`, `redis`, `infinity-ws`, `infinity-auth`, `infinity-ai`, `mailhog` exist there) | no compose-defined pre-production environment, and no local run command is documented in §11 PROC either |
| **UAT** | No | not present in `docker-compose.uat.yml` either | same — no compose-defined pre-production environment either |
| **Production** | Yes | full detail in the DSM above | — |

- **Gap:** this entity has **no non-Production environment at all** — `imaginarium` only exists in `docker-compose.production.yml`. This worker is not exercised by the shared compose-orchestrated Dev/UAT stacks, nor is a local run command documented in §11 PROC — Production is genuinely the first place it runs. This is the norm for most standalone workers on this platform (only The Nexus and Infinity have full pre-production standalone-worker compose coverage, and The Observatory and The Digital Grid have UAT-only standalone-worker coverage), not a defect specific to this entity — stated here so it isn't assumed otherwise.

## 10. Policy (POL)

- No route-level auth on the deployed `main.py` — low risk given `/orchestrate` is an honest
  no-op stub.
- **If `worker.py` is ever promoted to deployed status, its `dev-secret` fallback MUST be fixed
  first** — otherwise every write route (`/create`, `/templates`) would accept the literal
  string `"dev-secret"` as valid auth, same as the already-documented pattern for The Academy,
  Sashas Photo Studio, and TateKing.
- Zero-cost mandate: fully honored on both files.

## 11. Procedure (PROC)

- **Check orchestration status (deployed):** `POST /orchestrate` — always returns "not yet
  ready", by honest design, not a bug.
- **List orchestratable sub-services:** `GET /capabilities`.
- **(Not currently reachable) Create a real multi-service project:** would be `POST /create` on
  `worker.py`, if promoted to deployed status.

## 12. Runbook (RUN)

- **`/orchestrate` always returns `"orchestrated": false`:** expected — this is the deployed
  file's honest, intentional stub behavior, not a bug to chase.
- **Every route 404s in production despite the container being healthy:** was the exact symptom
  of the pre-fix Traefik defect (``PathPrefix(`/imaginarium`)`` with no `StripPrefix`
  middleware, while `main.py`'s routes are unprefixed) — fixed this pass by adding a
  `strip-imaginarium` middleware to the compose labels; confirm it's still present if this
  recurs.
- **Someone asks "why doesn't Imaginarium actually orchestrate anything?":** the real
  orchestration logic exists (`worker.py`) but isn't deployed — see truthfulness header for the
  full finding and the owner decision this requires before promotion.

## 13. Standards (STD)

- Naming: canonical entity name "Imaginarium" per `CLAUDE.md`/`PLATFORM_ENTITIES.md`.
- Config modules invoked via bare `python <file>.py` correctly read `PORT` from the environment
  at runtime; Dockerfile `EXPOSE`/embedded `HEALTHCHECK` mismatches against compose's routed port
  are cosmetic in that case (per `CLAUDE.md`'s §188 precedent) but SHOULD still be kept in sync
  for robustness — fixed here as a matter of consistency with recent practice.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-04 | Claude (session) | `CLAUDE.md` service table (status, Lead AI, Foundation), `PLATFORM_ENTITIES.md` (identity), initial repo search | **SUPERSEDED — was wrong.** Initial search incorrectly concluded no implementation exists. |
| 2026-07-04 | Claude (session), corrected after cubic PR review | actual repo contents (`src/*`, `workers/*/worker.py` — see correction blockquote above) | **Correction: code DOES exist.** `CLAUDE.md`'s Planned label is stale. Pack remains charter-only as an interim, honestly-flagged gap pending a real Partial/Live-tier rewrite — not a valid Planned-tier no-code determination. |
| 2026-07-07 | Claude (session) | `workers/imaginarium/main.py` (65 lines), `worker.py` (343 lines), `Dockerfile`, `docker-compose.production.yml` | Confirmed Live-tier, full pack authored. Major finding, a notable inversion of the usual "two implementations" pattern in this series: the **deployed** file (`main.py`) is an honest, intentional stub, while the **undeployed** file (`worker.py`) is a genuinely real cross-service orchestrator (SQLite-backed projects/templates, real `httpx` calls with `X-Internal-Secret` auth to Sashas Photo Studio/TranceFlow/TateKing/Warp Radio). Not fixed (a deployment/promotion decision, not a docs-pass fix) but flagged as a clear opportunity, contingent on first fixing `worker.py`'s `dev-secret` auth fallback. Also fixed two defects: a cosmetic Dockerfile port mismatch (8054 vs compose's 8064, fixed anyway for robustness) and a genuine, live Traefik `PathPrefix`-without-`StripPrefix` routing bug — the fifth instance of this exact class found this session — fixed with a `strip-imaginarium` middleware. `scripts/port_registry_validate.py` re-run and passes (73 workers). |
