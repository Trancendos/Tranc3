# Service Doc-Pack — TateKing

| Field | Value |
|---|---|
| **Entity** | TateKing |
| **Lead AI** | Benji Tate & Sam King |
| **Status** | ✅ In repo (per `CLAUDE.md` service table) — Live tier |
| **Code** | `workers/tateking/main.py` (505 lines, real FFmpeg + Remotion video pipeline) — standalone worker, no `src/*` module, no `api.py` mount. `worker.py` (459 lines, separate implementation with real `X-Internal-Secret` auth) exists but is not deployed. |

> **Truthfulness:** claims cite `workers/tateking/main.py`, `worker.py`, `Dockerfile`, and
> `docker-compose.production.yml` directly. Status is owned by the `CLAUDE.md` service table;
> identity by `PLATFORM_ENTITIES.md`.
> **Two defects found and fixed this pass, the same classes found repeatedly across this
> doc-pack series.** (1) `workers/tateking/Dockerfile` hardcoded `EXPOSE 8053` /
> `HEALTHCHECK ... localhost:8053`, while `docker-compose.production.yml` sets `PORT: "8061"` and
> routes Traefik to container port 8061. `main.py`'s own `PORT` default also fell back to `8053`.
> Since `main.py` is invoked via bare `python main.py` (not a hardcoded `uvicorn --port` CLI
> flag), the app itself correctly reads the `PORT` env var at runtime and compose's own
> `healthcheck:` override targets 8061 — so per `CLAUDE.md`'s §188 precedent this was **not** a
> live routing defect, only a cosmetic/robustness gap (a bare `docker run` without compose's
> override would still be flagged unhealthy). Fixed anyway, consistent with recent practice on
> this same defect class (Sashas Photo Studio): Dockerfile `EXPOSE`/embedded `HEALTHCHECK` now
> target 8061 (healthcheck reads `PORT` at check time), and `main.py`'s `PORT` default now
> matches. (2) **Genuine, live routing defect:** compose's Traefik rule was bare
> ``PathPrefix(`/tateking`)`` with **no `StripPrefix` middleware**, while every route in
> `main.py` (`/health`, `/video/create`, `/projects`, etc.) is unprefixed — the same class of bug
> already found and fixed for The Academy, Sashas Photo Studio, and Taimra earlier in this
> series. Every external request to `/tateking/<anything>` would have been forwarded with the
> prefix intact, 404ing against `main.py`'s unprefixed routes. Fixed by adding a
> `strip-tateking` middleware to the compose labels.
> **No auth on any route in the deployed `main.py`**, combined with a wildcard CORS policy
> (`allow_origins=["*"]`) and internet-facing `websecure` Traefik routing — any caller can trigger
> video-generation jobs against this service's FFmpeg/Remotion backends with no credential check.
> A second, real, currently-undeployed implementation (`worker.py`, 459 lines) exists with genuine
> `X-Internal-Secret` auth (`_auth()`), but uses the same insecure `"dev-secret"` fallback pattern
> already flagged for The Academy/Sashas Photo Studio (`INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", "dev-secret")`)
> — not deployed, so not a live issue, but worth noting it isn't a strictly better alternative on
> the auth-fallback front even if it were adopted as-is.

## 1. Service Governance Charter (GOV)

- **Mission:** video creation & editing platform — FFmpeg-based composition/thumbnail/subtitle
  operations with an optional Remotion serverless render backend.
- **Owner (RACI-A):** Platform Owner Trancendos.
- **Lead AI:** Benji Tate & Sam King.
- **Scope:** `workers/tateking/main.py` — the only deployed implementation. `worker.py`'s
  independent project/clip/ffmpeg-job implementation is real but out of scope for this pack's
  depth (real but unused).

## 2. Detailed Design Document (DDD)

### HTTP surface (`main.py`, no route prefix)

| Method | Route | Backing |
|---|---|---|
| GET | `/health` | static uptime/version — not a real dependency probe |
| GET | `/status` | reports `ffmpeg_available` (via `shutil.which`), `remotion_configured` (via `REMOTION_SERVE_URL` truthiness) — genuinely reflects real backend availability |
| POST | `/video/create` | creates a video job — tries Remotion first (if configured), falls back to FFmpeg; both real |
| POST | `/video/compose` | concatenates prior job outputs by ID, resolved server-side from `_jobs` (not caller-supplied paths — a real, correct trust-boundary decision) |
| POST | `/video/thumbnail` | extracts a thumbnail frame via FFmpeg |
| GET | `/video/status/{job_id}` | in-memory job status lookup |
| GET | `/video/result/{job_id}` | fetches the generated output file |
| POST | `/video/subtitle` | burns in subtitles via FFmpeg |
| GET | `/projects` | lists all jobs from the in-memory `_jobs` dict |
| POST | `/render` | legacy alias, delegates to `/video/create` |

### Generation logic — real, two-backend design
- `_remotion_render()` makes a genuine HTTP POST to `REMOTION_SERVE_URL`/render (the
  `remotion-render-service` compose service, port 8093) when configured; on any failure or if
  unconfigured, falls through to direct FFmpeg invocation via `_run_ffmpeg()` (`subprocess.run`
  against a resolved `ffmpeg` binary, with a 120s default timeout). This is a real, working
  2-tier design, not a stub.
- Input URL validation (`_ALLOWED_INPUT_SCHEMES` check, `urllib.parse.urlparse`) exists for
  `/video/create` — a real, if basic, SSRF-adjacent guard on caller-supplied source URLs.

### `worker.py` — real, unused alternate implementation
- Project/clip/ffmpeg-job model (not traced to file-level persistence detail in this pass —
  flagged as real but not deeply audited, consistent with the "second implementation" scope note
  pattern used throughout this series). Enforces `X-Internal-Secret` via `_auth()`, with the
  same `"dev-secret"` insecure-fallback default already documented for The Academy/Sashas Photo
  Studio. Not deployed — the Dockerfile never references it.

## 3. Technical Architecture Solutions Design (TASD)

- **Style:** standalone FastAPI worker, fully in-memory (`_jobs` dict), no persistence.
- **Fixed defects:** Dockerfile port mismatch (cosmetic, per §188 precedent, fixed anyway) +
  Traefik `StripPrefix` missing (genuine, live routing defect) — see truthfulness header.
- **Not fixed:** no auth on any route; wildcard CORS (`allow_origins=["*"]`); no persistence (job
  history lost on restart) — each requires an architectural decision out of scope for this pass.

## 4. RACI Matrix

| Activity | Benji Tate & Sam King (Lead) | Platform Owner | Platform Engineering |
|---|---|---|---|
| Video generation pipeline changes | **R** | A | C |
| Deciding between `main.py`/`worker.py` as canonical (future) | C | **A** | **R** |
| Adding route-level auth (future) | **R** | A | C |

## 5. Solutions Integration Model (SIM)

- **Upstream:** any caller of `/*` routes on this worker — no auth on any route, wildcard CORS,
  internet-facing via Traefik `websecure`.
- **Downstream:** `remotion-render-service` (real HTTP calls, port 8093, self-hosted); local
  `ffmpeg` binary (self-hosted, zero-cost).
- **Not integrated:** `worker.py`'s independent implementation is never called from `main.py` or
  vice versa.

## 6. Architecture Scalability Document (ASD)

- **Load model:** in-memory `_jobs` dict, no cap, no persistence — a restart loses all job
  history (generated files on disk under `OUTPUT_DIR` may survive, not verified in this pass).
- **Bottleneck:** FFmpeg invocations are synchronous subprocess calls with a 120s timeout;
  Remotion offloads rendering to a separate service when configured.
- **Zero-cost limits:** FFmpeg and Remotion (self-hosted `remotion-render-service`) are both
  free/OSS, consistent with the platform's zero-cost mandate.
- **Degradation:** Remotion failures fall through to FFmpeg automatically — a genuine, working
  degradation path, not merely documented intent.

## 7. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Web framework | FastAPI, standalone (no `api.py` mount) | self-hosted, port 8061 (fixed this pass) |
| Video processing | FFmpeg (local subprocess) → Remotion (self-hosted serverless) fallback chain | all free/OSS |
| Storage | in-memory `_jobs` dict, no persistence | zero infra cost, no durability |
| Auth | none in deployed `main.py`; `worker.py`'s unused alt has `X-Internal-Secret` with an insecure fallback | zero cost, currently unenforced |

## 8. Policy (POL)

- **Security gap, not fixed:** no route-level auth on any route, wildcard CORS
  (`allow_origins=["*"]`), and internet-facing routing via Traefik `websecure` — any caller can
  trigger video-generation jobs with no credential check.
- Zero-cost mandate: fully honored — FFmpeg and Remotion are both self-hosted/OSS, matching
  `CLAUDE.md`'s Recommended Open Source Foundations table.

## 9. Procedure (PROC)

- **Create a video:** `POST /video/create` — tries Remotion, falls back to FFmpeg automatically.
- **Compose from prior jobs:** `POST /video/compose` with a list of prior job IDs — paths are
  resolved server-side, not caller-supplied.
- **Check job status:** `GET /video/status/{job_id}` — in-memory only, lost on restart.

## 10. Runbook (RUN)

- **Every route 404s in production despite the container being healthy:** was the exact symptom
  of the pre-fix Traefik defect (``PathPrefix(`/tateking`)`` with no `StripPrefix` middleware,
  while `main.py`'s routes are unprefixed) — fixed this pass by adding a `strip-tateking`
  middleware to the compose labels; confirm it's still present if this recurs.
- **`/status` reports `ffmpeg_available: false`:** expected if the `ffmpeg` binary isn't on
  `PATH` in the container — this is a real check, not a stub.
- **`/video/create` always falls back to FFmpeg, never uses Remotion:** expected if
  `REMOTION_SERVE_URL` isn't set, or if `remotion-render-service` is unreachable — check that
  service's own health, not this module's logic.

## 11. Standards (STD)

- Naming: canonical entity name "TateKing" per `CLAUDE.md`/`PLATFORM_ENTITIES.md`.
- Config modules invoked via bare `python <file>.py` (not a hardcoded `uvicorn --port` CLI flag)
  correctly read `PORT` from the environment at runtime; Dockerfile `EXPOSE`/embedded
  `HEALTHCHECK` mismatches against compose's routed port are cosmetic in that case (per
  `CLAUDE.md`'s §188 precedent) but SHOULD still be kept in sync for robustness against
  non-compose deployment paths — fixed here as a matter of consistency with recent practice, not
  because it was a live defect.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-04 | Claude (session) | `CLAUDE.md` service table (status, Lead AI, Foundation), `PLATFORM_ENTITIES.md` (identity), initial repo search | **SUPERSEDED — was wrong.** Initial search incorrectly concluded no implementation exists. |
| 2026-07-04 | Claude (session), corrected after cubic PR review | actual repo contents (`src/*`, `workers/*/worker.py` — see correction blockquote above) | **Correction: code DOES exist.** `CLAUDE.md`'s Planned label is stale. Pack remains charter-only as an interim, honestly-flagged gap pending a real Partial/Live-tier rewrite — not a valid Planned-tier no-code determination. |
| 2026-07-07 | Claude (session) | `workers/tateking/main.py` (505 lines), `worker.py` (459 lines), `Dockerfile`, `docker-compose.production.yml` | Confirmed Live-tier, full pack authored. Found and fixed two defects: (1) Dockerfile port mismatch (8053 vs compose's 8061) — cosmetic per `CLAUDE.md`'s §188 precedent since `main.py` is invoked via bare `python main.py` and correctly reads `PORT` at runtime, but fixed anyway for robustness (Dockerfile `EXPOSE`/healthcheck + `main.py`'s `PORT` default all aligned to 8061). (2) Genuine, live routing defect: compose's Traefik rule used `PathPrefix` with no `StripPrefix` middleware, while `main.py`'s routes are unprefixed — same class of bug already fixed for The Academy, Sashas Photo Studio, and Taimra; fixed by adding a `strip-tateking` middleware. Verified real FFmpeg→Remotion fallback logic and a real, if basic, input-URL scheme allowlist. Confirmed no auth on any route, wildcard CORS, and a real-but-undeployed alternate implementation (`worker.py`) with genuine `X-Internal-Secret` auth (using the same insecure `"dev-secret"` fallback pattern already flagged elsewhere in this series). `scripts/port_registry_validate.py` re-run and passes (73 workers). |
