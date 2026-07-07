# Service Doc-Pack — The Artifactory

| Field | Value |
|---|---|
| **Entity** | The Artifactory |
| **Lead AI** | Lunascene |
| **Status** | ✅ In repo (per `CLAUDE.md` service table) — Live tier |
| **Code** | `src/artifactory/registry.py`, `src/artifactory/routes.py`; router registered in `api.py` (`app.include_router(_artifactory_router)`, line 871) — **plus a separate standalone worker**, `workers/artifactory-service/worker.py` (real Zot OCI registry bridge, port 8047) |

> **Truthfulness:** claims cite `src/artifactory/registry.py`, `src/artifactory/routes.py`, and
> `workers/artifactory-service/worker.py` directly. Status is owned by the `CLAUDE.md` service
> table; identity by `PLATFORM_ENTITIES.md`.
> **Scope note (established pattern):** The Artifactory has **two independent implementations**
> — the `src/artifactory/` module mounted into the main `api.py` app (documented below in full:
> a pure in-memory metadata registry with **no call to Zot, Gitea, or any binary storage
> backend**), and a separate standalone `workers/artifactory-service/worker.py` that **does**
> make real Zot v2 API calls (catalog listing, tag listing, SSRF-guarded path validation) with a
> Gitea-then-local-filesystem fallback chain. The two do not call each other.
> **Bug found and fixed while authoring this pack:** `workers/artifactory-service/` had **no
> Dockerfile at all** — `docker-compose.production.yml` references `dockerfile: Dockerfile` for
> its build context, but the directory contained only `worker.py`, `requirements.txt`, and a
> `__pycache__` directory. `docker compose build artifactory-service` would fail outright; the
> service could not be built or deployed via the documented production stack. Fixed by adding a
> Dockerfile matching the convention used by comparable single-file workers (`python:3.12-slim`,
> non-root user, port 8047 matching `WORKER_PORT = int(os.getenv("PORT", "8047"))` in
> `worker.py` and compose's `PORT=8047`/`8047:8047`/Traefik routing).
> **Broader gap found, not fixed (out of scope for this pass):** the same missing-Dockerfile
> defect exists in **8 other** `workers/*/` directories referenced by
> `docker-compose.production.yml`: `backup-service`, `cranbania` (git submodule — may be
> intentional), `fabulousa-service`, `ice-box-service`, `litellm-service`, `queue-service-go`,
> `rate-limit-service-go` (the last two are Go services requiring a different Dockerfile
> template — not verified in this pass), and `the-void` (ambiguous — may be Cloudflare-Worker-only
> per `CLAUDE.md`'s "migrating to self-hosted" note, not necessarily meant to have a container
> Dockerfile). This pack fixes only `artifactory-service`'s instance, in scope for this entity;
> the other 8 are flagged here as a real, previously-undocumented platform-wide gap for a
> dedicated follow-up pass — fixing 8 Dockerfiles across two languages and a submodule without
> individually verifying each one's runtime would risk introducing new defects.

## 1. Service Governance Charter (GOV)

- **Mission:** central artifact repository — tracks build outputs, container images, packages,
  and ML model weights with versioning and TTL-based retention.
- **Owner (RACI-A):** Lunascene; Platform Owner Trancendos.
- **Scope:** `src/artifactory/*` provides artifact/version metadata CRUD and retention-policy
  application only — no binary storage of its own. The standalone `workers/artifactory-service/`
  worker bridges to the real Zot OCI registry (with Gitea/filesystem fallback) for actual
  repository/tag listing.

## 2. Detailed Design Document (DDD)

### HTTP surface (`src/artifactory/routes.py`, prefix `/artifactory`)

| Method | Route | Backing |
|---|---|---|
| GET | `/artifactory/status` | `TheArtifactory.stats()` — total artifacts/versions, by-type counts |
| GET | `/artifactory/artifacts` | `TheArtifactory.list_artifacts()` — optional `type`/`namespace` filters; 400 on unknown type |
| POST | `/artifactory/artifacts` | `TheArtifactory.create_artifact()` — body `{"name", "type", "namespace", "description", "ttl_days"}`; 400 if `name` missing or `type` unknown |
| GET | `/artifactory/artifacts/{id}` | `TheArtifactory.get_artifact()` — 404 `JSONResponse` if missing; only endpoint returning full version list |
| POST | `/artifactory/artifacts/{id}/versions` | `TheArtifactory.push_version()` — body `{"version", "digest", "size_bytes", "tags", "metadata"}`; 400 if `version` missing, 404 if artifact missing/deleted |
| DELETE | `/artifactory/artifacts/{id}` | `TheArtifactory.delete_artifact()` — soft-delete (sets status to `DELETED`, not removed from the dict) |
| POST | `/artifactory/retention/apply` | `TheArtifactory.apply_retention()` — manually triggered only, not scheduled/cron |

### Data model (`registry.py`)
- `ArtifactType` enum: docker/python/npm/model/generic/cloudflare.
- `ArtifactStatus` enum: available/uploading/deleted/expired — `UPLOADING` and `EXPIRED` are
  defined but never set anywhere in `registry.py` (dead enum members, no upload-progress or
  auto-expiry code path exists).
- `Artifact`: `id` (uuid4), `name`, `namespace` (default `"trancendos"`), `artifact_type`,
  `status`, `versions` (`List[ArtifactVersion]`), `description`, `ttl_days` (`None` = retain
  forever).
- `ArtifactVersion`: `version`, `digest`, `size_bytes`, `created_at`, `tags`, `metadata` — all
  caller-supplied on `push_version()`; **no actual bytes are ever uploaded or stored** — `digest`
  and `size_bytes` are metadata fields trusted from the request body, not computed from real
  content.
- Seeded on startup with 6 hard-coded platform artifact records (tranc3-backend,
  tranc3-bots, tranc3-engine, tranc3-ai-worker, infinity-void-worker, trancendos-api-gateway) —
  metadata placeholders only, no real versions pushed.

### `apply_retention()` — TTL-based version pruning
- Iterates all artifacts with a non-`None` `ttl_days`, removes versions older than
  `ttl_days * 86400` seconds. Only runs when `POST /artifactory/retention/apply` is called
  manually — no scheduled/cron trigger exists in this module.

### Standalone worker (`workers/artifactory-service/worker.py`) — real Zot bridge
- Makes actual HTTP calls to a Zot OCI registry (`/v2/_catalog`, tag listing) via
  `_zot_get()`/`_zot_list_tags()`, with SSRF-guarded path validation (`_validate_zot_path()`
  restricts calls to known-safe path prefixes).
- Falls back to Gitea packages API, then local filesystem scan, when Zot is unreachable.
- Exposes a `/health` route reporting `zot_reachable` — a real connectivity probe, unlike
  `src/artifactory/*`'s `/status` which only reports in-memory metadata counts.

## 3. Technical Architecture Solutions Design (TASD)

- **Style (`src/artifactory/*` API path):** in-process module with a module-level singleton
  (`get_artifactory()`); in-memory dict storage, no persistence, no external DB, no Zot/Gitea
  call. The separate `workers/artifactory-service/` worker makes the real registry calls — see
  scope note above.
- **Decision: metadata layer ahead of storage backend.** `registry.py`'s own module header states
  "This scaffold tracks artefact metadata. Actual binary storage delegates to Zot OCI registry or
  local filesystem" — an honest, self-declared scaffold, consistent with what the code actually
  does.
- **Fixed defect:** `workers/artifactory-service/` had no Dockerfile at all, so it could not be
  built via `docker compose build` — see truthfulness header. Fixed by adding one matching the
  established single-file-worker convention.
- **Documented, not fixed:** the same missing-Dockerfile defect exists in 8 other worker
  directories — see truthfulness header for the full list and rationale for scoping the fix to
  this entity only.

## 4. RACI Matrix

| Activity | Lunascene (Lead) | Platform Owner | Platform Engineering | The Workshop |
|---|---|---|---|---|
| Artifact/version metadata CRUD changes | **R** | A | C | I |
| Zot/Gitea bridge changes (`workers/artifactory-service/`) | **R** | A | **R** | C |
| Retention policy scheduling (currently manual-only) | C | **A** | **R** | I |

## 5. Solutions Integration Model (SIM)

- **Upstream:** any caller of `/artifactory/*` routes — no auth on any route in
  `src/artifactory/routes.py`. The standalone worker's routes were not audited for auth in this
  pass (out of the in-depth scope for this pack).
- **Downstream:** best-effort Observatory `observe()` call on artifact-create and version-push,
  wrapped in bare `except Exception: pass` (`# nosec B110`).
- **Not integrated:** `src/artifactory/*` never calls the standalone `workers/artifactory-service/`
  worker, Zot, or Gitea — the "artifact repository" described in this entity's mission is real
  only in the standalone worker; the API-mounted path is metadata bookkeeping only.

## 6. Architecture Scalability Document (ASD)

- **Load model:** in-memory dict store (`_artifacts`), no cap defined — unbounded growth, no
  eviction beyond manually-triggered `apply_retention()`.
- **Bottleneck:** single-process, no persistence; a restart loses all artifact/version metadata
  except the 6 hard-coded seed records.
- **Zero-cost limits:** `src/artifactory/*` has no external dependency; the standalone worker
  targets Zot (self-hosted OCI registry, zero-cost) with Gitea/filesystem fallback.
- **Degradation:** Observatory emission failures don't block the CRUD response.

## 7. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Web framework | FastAPI `APIRouter` (`src/artifactory/*`) / FastAPI app (`workers/artifactory-service/`) | mounted / standalone respectively |
| Metadata storage | in-memory `dict` (`src/artifactory/*`), no persistence | zero infra cost, no durability |
| Binary storage | Zot OCI registry (self-hosted) → Gitea packages → local filesystem | OSS, self-hosted, zero-cost fallback chain |

## 8. Policy (POL)

- **Security gap, not fixed:** no route-level auth on any `src/artifactory/*` route, including the
  mutating ones — `POST /artifacts`, `POST /artifacts/{id}/versions`, `DELETE /artifacts/{id}`, and
  `POST /retention/apply` can all be called by any caller reaching `api.py` with no credential
  check. See SIM §5.
- Any Dockerfile-less worker directory referenced by `docker-compose.production.yml` MUST be
  treated as a build-breaking defect, not a cosmetic gap — see the broader-gap note in the
  truthfulness header; a follow-up pass should audit and fix the remaining 8.

## 9. Procedure (PROC)

- **Register an artifact:** `POST /artifactory/artifacts` with `{"name": "...", "type":
  "docker", "description": "..."}` — creates a metadata record only, does not upload any bytes.
- **Push a version:** `POST /artifactory/artifacts/{id}/versions` with `{"version": "1.0.0",
  "digest": "sha256:...", "size_bytes": 1234}` — `digest`/`size_bytes` are trusted caller input,
  not computed from real content.
- **Apply retention:** `POST /artifactory/retention/apply` — must be called manually or by an
  external scheduler; nothing in this repo triggers it automatically.
- **Query the real registry:** use `workers/artifactory-service/`'s `/repositories` and
  `/repositories/{repo}/tags` endpoints, which proxy to the actual Zot instance.

## 10. Runbook (RUN)

- **Artifact metadata disappears after a restart:** expected — `src/artifactory/*` has no
  persistence; only the 6 seed records reappear.
- **`workers/artifactory-service` fails to build:** was a genuine missing-Dockerfile defect —
  fixed in this pass; confirm `workers/artifactory-service/Dockerfile` exists in the deployed
  checkout if this recurs. Check the other 8 flagged directories (truthfulness header) for the
  same class of failure if their builds fail too.
- **`push_version()` accepted a bogus digest:** expected — `src/artifactory/*` never validates
  `digest`/`size_bytes` against real content; this module is metadata-only by design.

## 11. Standards (STD)

- Naming: canonical entity name "The Artifactory" per `CLAUDE.md`/`PLATFORM_ENTITIES.md`.
- Every service referenced in `docker-compose.production.yml` with a `build: { dockerfile:
  Dockerfile }` block MUST have a corresponding `Dockerfile` in its build context — a missing
  Dockerfile is a build-breaking defect, not a documentation gap. The defect fixed here is the
  reason for this standard; the 8 remaining instances are tracked as a known gap pending a
  dedicated follow-up.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-05 | Claude (session) | `src/artifactory/registry.py` (256 lines), `src/artifactory/routes.py` (100 lines), `api.py` router registration (line 871), `workers/artifactory-service/worker.py`, `docker-compose.production.yml` | Confirmed Live-tier, full pack authored. Found and fixed a genuine build-breaking defect: `workers/artifactory-service/` had no Dockerfile despite being referenced by compose's build block. Also discovered, and explicitly flagged rather than rushed-fixed, the same defect in 8 other worker directories across the repo (2 Go services, 1 submodule, 1 ambiguous CF-vs-container case, 4 plain Python workers) — a real, previously undocumented platform-wide gap. |
| 2026-07-07 | Claude (session, cubic-dev-ai review triage) | `src/artifactory/routes.py` | Elevated the "no route-level auth" POL bullet from a flat fact to an explicit security-gap callout, naming the specific unauthenticated mutation routes (`POST /artifacts`, `POST /artifacts/{id}/versions`, `DELETE /artifacts/{id}`, `POST /retention/apply`). |
