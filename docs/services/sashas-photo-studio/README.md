# Service Doc-Pack — Sashas Photo Studio

| Field | Value |
|---|---|
| **ServiceID (CMDB)** | `SRV-SASHASPHOTO-001` |
| **Entity** | Sashas Photo Studio |
| **Lead AI** | Madam Krystal |
| **Status** | ✅ In repo (per `CLAUDE.md` service table) — Live tier |
| **Code** | `workers/sashas-photo-studio/main.py` (370 lines — the deployed implementation, per the Dockerfile's `COPY main.py .` / `CMD ["python", "main.py"]`) — standalone worker, no `src/*` module, no `api.py` mount |

> **Truthfulness:** claims cite `workers/sashas-photo-studio/main.py`, `worker.py`, `Dockerfile`,
> and `docker-compose.production.yml` directly. Status is owned by the `CLAUDE.md` service table;
> identity by `PLATFORM_ENTITIES.md`.
> **Two genuinely independent implementations exist, unlike The Academy's placeholder-vs-real
> pattern found earlier in this batch.** `workers/sashas-photo-studio/` contains `main.py` (370
> lines — ComfyUI-primary, AUTOMATIC1111-fallback, offline-stub-last-resort image generation, no
> persistence) and `worker.py` (291 lines — a separate, real implementation using Pollinations.ai
> (zero-cost, no API key) with SQLite job storage and local image caching). **Verified this is not
> the same bug as The Academy's**: the Dockerfile's `COPY main.py .` / `CMD ["python", "main.py"]`
> correctly deploys `main.py`, which is itself a complete, real implementation (not a placeholder
> stub) — its 3-tier fallback chain (ComfyUI → A1111 → offline placeholder) is honestly documented
> in its own header and genuinely implemented with real HTTP calls to each backend. `worker.py`
> is a real but currently-unused alternate implementation, matching the "two independent
> implementations" pattern already established for several other entities in this doc-pack series
> — not a defect, just an unresolved architectural choice between two working backends.
> **No auth on any route in the deployed `main.py`** — unlike The Academy's `worker.py` (which
> does enforce `X-Internal-Secret`), nothing in `main.py` checks any header or credential on any
> route, including `/photo/generate`.
> **Dockerfile `EXPOSE`/embedded `HEALTHCHECK` referenced port 8051, while compose routes this
> service to port 8062** — `main.py` is invoked via bare `python main.py` (not a `uvicorn` CLI
> with a hardcoded `--port`), so it correctly reads `PORT` from the environment at runtime, and
> compose's own `healthcheck:` block (which overrides the Dockerfile's embedded one) correctly
> targets 8062, so this was not a live routing defect in the deployed compose stack — consistent
> with `CLAUDE.md`'s §188 precedent for this "CMD reads env var directly" pattern. **However,** the
> embedded `HEALTHCHECK` still hardcoded 8051, which would report the container unhealthy under any
> orchestrator that doesn't override it (a bare `docker run` with `PORT=8062`, for instance) — this
> part of CodeRabbit's finding was valid and is **fixed this pass**: the embedded healthcheck now
> reads `PORT` from the environment (falling back to 8051) at check time, matching how `main.py`
> itself resolves its port.

## 1. Service Governance Charter (GOV)

- **Mission:** image generation via a self-hosted-first fallback chain (ComfyUI → AUTOMATIC1111 →
  offline placeholder), per `main.py` (the actually-deployed implementation).
- **Owner (RACI-A):** Madam Krystal; Platform Owner Trancendos.
- **Scope:** `main.py` only, since that's what the Dockerfile deploys. `worker.py`'s
  Pollinations.ai-based alternate implementation is real but not covered in depth here — see
  scope note above.

## 2. Detailed Design Document (DDD)

### HTTP surface (`main.py`, no route prefix)

| Method | Route | Backing |
|---|---|---|
| GET | `/health` | static health response |
| GET | `/status` | worker metadata |
| POST | `/photo/generate` | real 3-tier generation: ComfyUI → A1111 → offline placeholder (see below) |
| POST | `/generate` | legacy alias, delegates to `/photo/generate` |
| GET | `/photo/status/{job_id}` | in-memory job status lookup |
| GET | `/photo/result/{job_id}` | fetches the generated image |
| GET | `/photo/models` | lists ComfyUI models, or a hard-coded 3-item fallback list if ComfyUI is unreachable |
| POST | `/photo/upscale` | **always returns 501** — "Upscale is not yet implemented. ComfyUI upscale pipeline coming soon." (honest, not a bug) |
| GET | `/gallery` | lists completed jobs from the in-memory `_jobs` dict |

### Generation logic — real, genuinely tiered fallback
- `/photo/generate` tries `_comfyui_generate()` first (real HTTP call to `COMFYUI_URL`); on any
  exception, falls back to `_a1111_generate()` (real HTTP call to `A1111_URL`); on any exception
  there too, falls back to an honestly-labeled offline stub (`"placeholder": True` in the
  response) rather than silently pretending success. This 3-tier design is real and matches the
  module's own documented intent — a genuine positive finding.
- In an environment with neither ComfyUI nor AUTOMATIC1111 actually running (the likely state for
  most deployments per `CLAUDE.md`'s "planned" framing of these backends elsewhere in the
  platform), **every call to `/photo/generate` falls through to the offline placeholder** — this
  is expected, documented behavior, not silent failure.

### `worker.py` — real, unused alternate implementation
- Uses Pollinations.ai (a genuinely zero-cost, no-API-key image generation service) with SQLite
  job persistence and local image file caching under `data/images/`. Enforces
  `X-Internal-Secret` auth (via `INTERNAL_SECRET` env var, same `dev-secret` fallback caveat
  noted for The Academy). Not deployed — the Dockerfile never references it.

## 3. Technical Architecture Solutions Design (TASD)

- **Style:** standalone FastAPI worker (`main.py`), fully in-memory (`_jobs` dict), no
  persistence — a real gap relative to `worker.py`'s SQLite approach, though `main.py` is what's
  actually deployed.
- **Decision (undocumented in code):** why `main.py` (ComfyUI/A1111, no persistence, no auth) was
  chosen over `worker.py` (Pollinations.ai, SQLite, real auth) for deployment is not explained
  anywhere in this repo — both are genuinely functional. Documented as an open question, not
  resolved in this pass.
- **Not fixed:** no auth on `main.py`'s routes; no persistence (job history lost on restart); the
  cosmetic Dockerfile port mismatch (see truthfulness header, matches an already-established
  non-defect precedent).

## 4. RACI Matrix

| Activity | Madam Krystal (Lead) | Platform Owner | Platform Engineering |
|---|---|---|---|
| Generation pipeline changes (`main.py`) | **R** | A | C |
| Deciding between `main.py`/`worker.py` as the canonical implementation (future) | C | **A** | **R** |
| Implementing the `/photo/upscale` pipeline (future) | **R** | A | C |

## 5. Solutions Integration Model (SIM)

- **Upstream:** any caller of `/photo/*` — no auth on any route in the deployed `main.py`.
- **Downstream:** real HTTP calls to `COMFYUI_URL` (default `localhost:8188`) and `A1111_URL`
  (default `localhost:7860`) — both self-hosted, zero-cost per the module's own header. Neither
  is confirmed running in any environment audited in this pass.
- **Not integrated:** `worker.py`'s Pollinations.ai path is a real, independent alternative not
  wired into `main.py` at all — the two never call each other.

## 6. Architecture Scalability Document (ASD)

- **Load model:** in-memory `_jobs` dict in `main.py`, no cap, no persistence — a restart loses
  all job history and generated-image references (images themselves may still exist on ComfyUI's
  own storage, not verified in this pass).
- **Bottleneck:** single-process; no queueing beyond the in-memory dict.
- **Zero-cost limits:** ComfyUI/A1111 are self-hosted OSS; the offline placeholder has zero cost
  by construction.
- **Degradation:** the 3-tier fallback chain **is** the degradation strategy — a genuinely
  well-designed pattern for this entity, in contrast to several other entities' unenforced-flag
  findings in this series.

## 7. Deployment Scope Matrix (DSM)

- **Mode awareness:** No — this entity's own code does not call `PlatformInfraMode` / `src/platform/infrastructure_mode.py`. (Some platform-wide, cross-cutting code *does* branch on the mode — `src/routers/adaptive.py` and `src/routers/ecosystem.py` read/set `PLATFORM_INFRA_MODE`/`SYSTEM_MODE` directly, and `Dimensional/architecture/storage_factory.py` selects a storage provider from `SYSTEM_MODE` — but none of that code is owned by this or any other one of the 43 named entities; it is shared platform infrastructure, not this service's own logic. The Citadel is the only one of the 43 named entities whose own code branches on the mode — see `docs/services/the-citadel/README.md`.) This entity's deployment scope is determined externally — by which `docker-compose.production.yml` service block runs, and where — not by in-process mode detection.
- **Runtime placement:** standalone worker with its own `docker-compose.production.yml` service block (`sashas-photo-studio`, port 8062) and its own Traefik route — does not run inside the `tranc3-backend` monolith
- **Persistence:** **no named volume** on the `sashas-photo-studio` compose service — any on-disk state is lost on container replace/redeploy in every mode alike
- **Note:** see the Cloud-Only caveat — this is a genuine capability difference between modes, not just a durability one.

| Setup | What runs, and where | Data locality | Hard blockers / caveats |
|---|---|---|---|
| **Cloud-Only** | the `sashas-photo-studio` compose block runs on a single cloud host; Traefik/edge in front | ephemeral — no volume means state does not survive a redeploy | ComfyUI/AUTOMATIC1111 image-generation backends are GPU-bound; free-tier cloud CPU hosts cannot realistically run them, so Cloud-Only likely degrades to this worker's third fallback tier — an honestly-labelled offline placeholder |
| **Hybrid** | same `sashas-photo-studio` compose block; per `docs/architecture/infrastructure-modes.md`'s Hybrid diagram, this worker itself still runs as a single instance (cloud or local host), with only shared persistent data (not specific to this worker) split via TrueNAS/Syncthing | as above, optionally local-synced if a volume exists | requires `CITADEL_LOCAL_STACK=true` if a local compose stack should run alongside the cloud one |
| **Local-Only** | same `sashas-photo-studio` compose block, run entirely on local/Citadel hardware behind local Traefik | fully local (still no volume — same durability gap as Cloud-Only) | the only mode where the ComfyUI/AUTOMATIC1111 tiers are realistically usable, if local GPU hardware is present |

- **Zero-cost posture per mode:** Cloud-Only defaults to the `zero_cost_cloud` AI-rotation chain; Hybrid/Local-Only default to `zero_cost_full` (`config/platform/infrastructure_mode.yaml`) — this only affects AI-Gateway-routed calls, not this entity's own logic
- **Switching modes:** operator-level via `PLATFORM_INFRA_MODE` (or legacy `SYSTEM_MODE`); this entity needs no code change to move between modes, only a redeploy-target change for its own compose block

## 8. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Web framework | FastAPI, standalone (no `api.py` mount) | self-hosted, port 8062 (per compose) |
| Generation backend | ComfyUI → AUTOMATIC1111 → offline placeholder | self-hosted-first, zero-cost fallback chain |
| Storage | in-memory `_jobs` dict, no persistence | zero infra cost, no durability |

## 9. Environment Support Matrix (ESM)

> Grounded against `docker-compose.development.yml`, `docker-compose.uat.yml`, and `docker-compose.production.yml` — checked by exact compose service name, not assumed (see `docs/services/INDEX.md` for current platform-wide compose service totals, which change as the topology evolves).

| Environment | Covered? | What runs | Notes |
|---|---|---|---|
| **Dev** | No | not present in `docker-compose.development.yml` (only `api`, `redis`, `infinity-ws`, `infinity-auth`, `infinity-ai`, `mailhog` exist there) | no compose-defined pre-production environment, and no local run command is documented in §11 PROC either |
| **UAT** | No | not present in `docker-compose.uat.yml` either | same — no compose-defined pre-production environment either |
| **Production** | Yes | full detail in the DSM above | — |

- **Gap:** this entity has **no non-Production environment at all** — `sashas-photo-studio` only exists in `docker-compose.production.yml`. This worker is not exercised by the shared compose-orchestrated Dev/UAT stacks, nor is a local run command documented in §11 PROC — Production is genuinely the first place it runs. This is the norm for most standalone workers on this platform (only The Nexus and Infinity have full pre-production standalone-worker compose coverage, and The Observatory and The Digital Grid have UAT-only standalone-worker coverage), not a defect specific to this entity — stated here so it isn't assumed otherwise.

## 10. Policy (POL)

- **Security gap, not fixed:** no route-level auth on any `/photo/*` route in the deployed
  `main.py`, and this service is routed via Traefik's `websecure` entrypoint (internet-reachable,
  not internal-only) — confirmed via `docker-compose.production.yml`. Any caller can invoke image
  generation with no credential check.
- Zero-cost mandate: fully honored — ComfyUI/A1111 are self-hosted, the final fallback is a
  zero-cost stub, matching `CLAUDE.md`'s Recommended Open Source Foundations table.

## 11. Procedure (PROC)

- **Generate an image:** `POST /photo/generate` with `{"prompt": "..."}` — tries ComfyUI, then
  A1111, then returns an honestly-labeled offline placeholder if neither backend is reachable.
- **Check job status:** `GET /photo/status/{job_id}` — in-memory only, lost on restart.
- **Attempt an upscale:** currently always 501s — not yet implemented, by design.

## 12. Runbook (RUN)

- **Every generation returns `"source": "offline", "placeholder": true`:** expected if neither
  ComfyUI nor AUTOMATIC1111 is reachable at their configured URLs — check `COMFYUI_URL`/
  `A1111_URL` connectivity, not this module's logic.
- **Job history disappears after a restart:** expected — `main.py` has no persistence
  (`worker.py`'s SQLite-backed alternative does, but isn't deployed).
- **`/photo/upscale` always returns 501:** expected, not a bug — explicitly not yet implemented.

## 13. Standards (STD)

- Naming: canonical entity name "Sashas Photo Studio" per `CLAUDE.md`/`PLATFORM_ENTITIES.md` (no
  apostrophe — see `CLAUDE.md`'s naming rules).
- When a worker directory contains two independently-real implementations (as here, contrast with
  The Academy's placeholder-vs-real pair), the choice of which one the Dockerfile deploys SHOULD
  be documented in a code comment or this doc-pack — this pack now serves as that record until a
  decision is made to consolidate or officially adopt one.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-05 | Claude (session) | `workers/sashas-photo-studio/main.py` (370 lines), `worker.py` (291 lines), `Dockerfile`, `docker-compose.production.yml` | Confirmed Live-tier, full pack authored. Verified the deployed `main.py` is a real, working implementation with a genuine 3-tier fallback chain (ComfyUI → A1111 → honestly-labeled offline placeholder) — explicitly ruled out The Academy's placeholder-vs-real defect pattern here. Found a second, real, currently-unused implementation (`worker.py`, Pollinations.ai + SQLite + real auth) with no documented rationale for why it isn't the deployed one. Also confirmed a Dockerfile port mismatch (8051 vs compose's 8062) is cosmetic only, not a live defect, per the established `CLAUDE.md` §188 precedent for workers invoked via bare `python <file>.py` (env var respected at runtime; compose's own healthcheck overrides the Dockerfile's). |
| 2026-07-07 | Claude (session, cubic/CodeRabbit review triage) | `Dockerfile`, `docker-compose.production.yml` | Fixed three findings. (1) While the compose-level port mismatch was correctly ruled a non-defect in the prior pass, CodeRabbit correctly identified that the embedded `HEALTHCHECK` itself still hardcoded 8051 — a real gap for any orchestrator that doesn't apply compose's override (bare `docker run`, alternate compose file). Fixed by having the embedded healthcheck read `PORT` from the environment at check time, matching `main.py`'s own port resolution. (2) Elevated the "no route-level auth" POL bullet to an explicit security-gap callout, noting this service is reachable via Traefik's `websecure` (internet-facing) entrypoint per compose. (3) Found and fixed the same Traefik PathPrefix-without-StripPrefix defect already fixed for The Academy — `main.py`'s routes (`/photo/generate`, `/health`, etc.) are unprefixed but compose's rule was bare `PathPrefix(\`/sashas-photo-studio\`)` with no middleware; added a matching `strip-sashas-photo-studio` middleware. |
