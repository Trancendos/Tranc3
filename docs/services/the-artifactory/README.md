# Service Doc-Pack — The Artifactory

| Field | Value |
|---|---|
| **ServiceID (CMDB)** | `SRV-ARTIFACTORY-001` |
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
> **Broader gap found on 2026-07-05, mostly resolved by other work since (re-verified 2026-08-07,
> corrected 2026-08-07 round 3 — see Verification Log):** at the time this pack was authored, the
> same missing-Dockerfile defect existed in 7 other `workers/*/` directories referenced by
> `docker-compose.production.yml`. Re-checking every compose service with a `build: { context:
> ./workers/..., dockerfile: Dockerfile }` block against the filesystem: `backup-service`,
> `fabulousa-service`, `ice-box-service`, and `litellm-service` have all gained a Dockerfile in the
> intervening month of work, and `the-void` is not a `workers/` directory at all (no such path
> exists — the CF-Worker-only ambiguity noted originally turned out to mean exactly that: it was
> never meant to be a container). `cranbania` is a **different case, not a resolved one**: its
> Dockerfile exists inside the `workers/cranbania` **git submodule**'s own tree, and this checkout
> happens to have that submodule populated — but none of `.forgejo/workflows/deploy-fly.yml`,
> `deploy-self-hosted.yml`, or any other deploy workflow's `actions/checkout` step sets
> `submodules: true`/`recursive` (only the unrelated `sync-cranbania-submodule.yml` does). A fresh
> checkout via the actual deploy pipeline would leave `workers/cranbania/` empty and
> `docker compose build cranbania` would fail — so this **is** a live, previously-undocumented
> build-breaking defect, just a different one (missing submodule checkout, not a missing file) than
> the pattern this section otherwise describes. `queue-service-go`, also originally counted here,
> was separately removed entirely as dead code (never wired into compose, zero commits since
> creation) rather than given a Dockerfile — see `docs/governance/SWARM-COORDINATION-MATRIX.md`
> §3. `rate-limit-service-go` — and `monitoring-go`, found in the same 2026-08-07 systematic
> duplication sweep that turned up this section's `cranbania` submodule gap — were both **also**
> removed entirely as dead code (never wired into `docker-compose.production.yml`, dependency-bump
> commits only, same class as `queue-service-go`) rather than given Dockerfiles or built out. The
> original "missing Dockerfile *file*" gap is resolved for every plain directory; the only
> build-breaking issue remaining from this section is `cranbania`'s submodule-checkout gap in the
> deploy pipeline (new, above) — now fixed, see §10/§12/§13 below.

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
- **Documented, not fixed:** as of the 2026-08-07 round-3 re-verification, the missing-Dockerfile-
  *file* defect is resolved for every plain directory; the two remaining build-breaking issues are
  `cranbania`'s missing submodule checkout and `rate-limit-service-go`'s undeployed/dead-code
  status — see truthfulness header for the full detail.

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

## 7. Deployment Scope Matrix (DSM)

- **Mode awareness:** No — this entity's own code does not call `PlatformInfraMode` / `src/platform/infrastructure_mode.py`. (Some platform-wide, cross-cutting code *does* branch on the mode — `src/routers/adaptive.py` and `src/routers/ecosystem.py` read/set `PLATFORM_INFRA_MODE`/`SYSTEM_MODE` directly, and `Dimensional/architecture/storage_factory.py` selects a storage provider from `SYSTEM_MODE` — but none of that code is owned by this or any other one of the 43 named entities; it is shared platform infrastructure, not this service's own logic. The Citadel is the only one of the 43 named entities whose own code branches on the mode — see `docs/services/the-citadel/README.md`.) This entity's deployment scope is determined externally — by which `docker-compose.production.yml` service block runs, and where — not by in-process mode detection.
- **Runtime placement:** standalone worker with its own `docker-compose.production.yml` service block (`artifactory-service`, port 8047) and its own Traefik route — does not run inside the `tranc3-backend` monolith
- **Persistence:** **no named volume** on the `artifactory-service` compose service — any on-disk state is lost on container replace/redeploy in every mode alike
- **Note:** this entity has **two** deployment surfaces — a router mounted in the `tranc3-backend` monolith (`api.py`) *and* a separate standalone worker (`artifactory-service`, port 8047). The table below describes the standalone worker; the monolith-mounted router follows the monolith's own placement (see the monolith pattern noted across this platform's other entities) and shares its volume.

| Setup | What runs, and where | Data locality | Hard blockers / caveats |
|---|---|---|---|
| **Cloud-Only** | the `artifactory-service` compose block runs on a single cloud host; Traefik/edge in front | ephemeral — no volume means state does not survive a redeploy | if this worker writes any local file it needs to keep, that data is at risk on every mode until a volume is added |
| **Hybrid** | same `artifactory-service` compose block; per `docs/architecture/infrastructure-modes.md`'s Hybrid diagram, this worker itself still runs as a single instance (cloud or local host), with only shared persistent data (not specific to this worker) split via TrueNAS/Syncthing | as above, optionally local-synced if a volume exists | requires `CITADEL_LOCAL_STACK=true` if a local compose stack should run alongside the cloud one |
| **Local-Only** | same `artifactory-service` compose block, run entirely on local/Citadel hardware behind local Traefik | fully local (still no volume — same durability gap as Cloud-Only) | none beyond standard local-hardware ops |

- **Zero-cost posture per mode:** Cloud-Only defaults to the `zero_cost_cloud` AI-rotation chain; Hybrid/Local-Only default to `zero_cost_full` (`config/platform/infrastructure_mode.yaml`) — this only affects AI-Gateway-routed calls, not this entity's own logic
- **Switching modes:** operator-level via `PLATFORM_INFRA_MODE` (or legacy `SYSTEM_MODE`); this entity needs no code change to move between modes, only a redeploy-target change for its own compose block

## 8. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Web framework | FastAPI `APIRouter` (`src/artifactory/*`) / FastAPI app (`workers/artifactory-service/`) | mounted / standalone respectively |
| Metadata storage | in-memory `dict` (`src/artifactory/*`), no persistence | zero infra cost, no durability |
| Binary storage | Zot OCI registry (self-hosted) → Gitea packages → local filesystem | OSS, self-hosted, zero-cost fallback chain |

## 9. Environment Support Matrix (ESM)

> Grounded against `docker-compose.development.yml`, `docker-compose.uat.yml`, and `docker-compose.production.yml` — checked by exact compose service name, not assumed (see `docs/services/INDEX.md` for current platform-wide compose service totals, which change as the topology evolves).

| Environment | Covered? | What runs | Notes |
|---|---|---|---|
| **Dev** | Partial | the `api` service in `docker-compose.development.yml` runs the monolith router — the standalone `artifactory-service` worker is **not** in this compose file | standalone worker has zero Dev coverage |
| **UAT** | Partial | same monolith router via `api` in `docker-compose.uat.yml` — the standalone `artifactory-service` worker is **not** in this compose file either | standalone worker has zero UAT coverage |
| **Production** | Yes | both surfaces — full detail in the DSM above | — |

- **Gap:** the standalone `artifactory-service` worker (the more complete of this entity's two surfaces, per the DSM above) has **no Dev or UAT environment at all** — the first place it runs is Production. This is the norm for the ~90 standalone workers on this platform, not specific to this entity, but worth stating plainly rather than assuming pre-production validation exists where it doesn't.

## 10. Policy (POL)

- **Security gap, not fixed:** no route-level auth on any `src/artifactory/*` route, including the
  mutating ones — `POST /artifactory/artifacts`, `POST /artifactory/artifacts/{id}/versions`,
  `DELETE /artifactory/artifacts/{id}`, and `POST /artifactory/retention/apply` can all be called
  by any caller reaching `api.py` with no credential check. See SIM §5.
- Any Dockerfile-less worker directory referenced by `docker-compose.production.yml` MUST be
  treated as a build-breaking defect, not a cosmetic gap — see the broader-gap note in the
  truthfulness header. As of 2026-08-07 this holds for every plain directory (0 of 73 non-submodule
  compose-referenced worker build contexts are missing a Dockerfile); `cranbania`'s Dockerfile
  exists but isn't reliably fetched by the deploy pipeline (git-submodule checkout gap — see
  truthfulness header), which is the same class of defect wearing a different cause.
  `rate-limit-service-go` and `monitoring-go` — both Dockerfile-less, both not
  compose-referenced — were deleted as dead code on 2026-08-07 rather than left as an open
  decision; see the Verification Log.

## 11. Procedure (PROC)

- **Register an artifact:** `POST /artifactory/artifacts` with `{"name": "...", "type":
  "docker", "description": "..."}` — creates a metadata record only, does not upload any bytes.
- **Push a version:** `POST /artifactory/artifacts/{id}/versions` with `{"version": "1.0.0",
  "digest": "sha256:...", "size_bytes": 1234}` — `digest`/`size_bytes` are trusted caller input,
  not computed from real content.
- **Apply retention:** `POST /artifactory/retention/apply` — must be called manually or by an
  external scheduler; nothing in this repo triggers it automatically.
- **Query the real registry:** use `workers/artifactory-service/`'s `/repositories` and
  `/repositories/{repo}/tags` endpoints, which proxy to the actual Zot instance.

## 12. Runbook (RUN)

- **Artifact metadata disappears after a restart:** expected — `src/artifactory/*` has no
  persistence; only the 6 seed records reappear.
- **`workers/artifactory-service` fails to build:** was a genuine missing-Dockerfile defect —
  fixed in this pass; confirm `workers/artifactory-service/Dockerfile` exists in the deployed
  checkout if this recurs. 4 of the other directories originally flagged alongside it
  (`backup-service`, `fabulousa-service`, `ice-box-service`, `litellm-service`) have since gained
  their own Dockerfiles independently of this pack — see the truthfulness header.
  `rate-limit-service-go` and `monitoring-go` were deleted 2026-08-07 rather than left
  Dockerfile-less indefinitely.
- **`cranbania` fails to build (`Dockerfile not found`):** was previously expected on a fresh
  checkout — `workers/cranbania` is a git submodule and no deploy or CI workflow's
  `actions/checkout` step passed `submodules: true`/`recursive` (only the unrelated
  `sync-cranbania-submodule.yml` did). Fixed 2026-08-07 by adding `submodules: recursive` to the
  three checkout steps that run the `pytest tests/` suite against real submodule content
  (`.forgejo/workflows/ci.yml`'s `full-suite` job, `.github/workflows/ci.yml`'s `Pytest` job,
  `.github/workflows/test.yml`'s `Full Pytest Suite` job) — see the Verification Log. Not yet
  applied to `nightly.yml`/`benchmark-eval.yml`/`phase7-nanoservices.yml`/`phase8-trancex.yml`,
  which run the same suite on a different cadence and carry the identical gap; and not yet needed
  by `deploy-fly.yml`/`deploy-self-hosted.yml`, since neither currently builds a `cranbania` image
  (confirmed by reading `build-workers`'s job steps — if that changes, this note is stale).
- **`push_version()` accepted a bogus digest:** expected — `src/artifactory/*` never validates
  `digest`/`size_bytes` against real content; this module is metadata-only by design.

## 13. Standards (STD)

- Naming: canonical entity name "The Artifactory" per `CLAUDE.md`/`PLATFORM_ENTITIES.md`.
- Every service referenced in `docker-compose.production.yml` with a `build: { dockerfile:
  Dockerfile }` block MUST have a corresponding `Dockerfile` **reliably present in the checkout
  the build actually runs against** — a missing Dockerfile is a build-breaking defect, not a
  documentation gap, and that includes one that's missing only because a submodule wasn't
  initialized. The defect fixed here is the reason for this standard; as of 2026-08-07 the
  Dockerfile-presence gap holds for 73 of 74 checked, and `cranbania`'s submodule-checkout gap in
  the CI pytest jobs is now fixed (see Verification Log) — the same gap in the four still-unfixed
  workflows named there remains open.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-05 | Claude (session) | `src/artifactory/registry.py` (256 lines), `src/artifactory/routes.py` (100 lines), `api.py` router registration (line 871), `workers/artifactory-service/worker.py`, `docker-compose.production.yml` | Confirmed Live-tier, full pack authored. Found and fixed a genuine build-breaking defect: `workers/artifactory-service/` had no Dockerfile despite being referenced by compose's build block. Also discovered, and explicitly flagged rather than rushed-fixed, the same defect in 8 other worker directories across the repo (2 Go services, 1 submodule, 1 ambiguous CF-vs-container case, 4 plain Python workers) — a real, previously undocumented platform-wide gap. |
| 2026-07-07 | Claude (session, cubic-dev-ai review triage) | `src/artifactory/routes.py` | Elevated the "no route-level auth" POL bullet from a flat fact to an explicit security-gap callout, naming the specific unauthenticated mutation routes (`POST /artifacts`, `POST /artifacts/{id}/versions`, `DELETE /artifacts/{id}`, `POST /retention/apply`). |
| 2026-08-07 (round 1) | Claude (session, cubic-dev-ai review triage on Tranc3#493) | `docs/governance/SWARM-COORDINATION-MATRIX.md` §3, this file's §3/§10/§12/§13 | `queue-service-go` (one of the 8 directories in the 2026-07-05 row above) was deleted as dead code, dropping the live count to 7 — the truthfulness header above was updated to say 7, but §3/§10/§12/§13 and this log's older row still said 8/"2 Go services" until this pass. Fixed the four living-body references to say 7 (1 Go service — `rate-limit-service-go` only). The 2026-07-05 row is left unedited as the accurate point-in-time record of what existed on that date; this row is the reconciliation, not a rewrite of history. |
| 2026-08-07 (round 2) | Claude (session, cubic-dev-ai review triage on Tranc3#493) | `docker-compose.production.yml` parsed programmatically — every service with a `build: { context: ./workers/*, dockerfile: Dockerfile }` block checked against the filesystem (74 services) | The "7" from round 1 was itself already stale: `backup-service`, `cranbania`, `fabulousa-service`, `ice-box-service`, and `litellm-service` had each independently gained a Dockerfile since 2026-07-05, and `the-void` was never a `workers/` directory at all (confirmed non-existent path — the original "ambiguous CF-vs-container" framing was right for the wrong reason). Result: **0 of 74** compose-referenced worker build contexts are missing a Dockerfile. Only `rate-limit-service-go` remains Dockerfile-less, and it isn't referenced by compose, so it's a dead-code question (same class as the deleted `queue-service-go`), not a build defect. Rewrote the truthfulness header and §10/§12/§13 to state this rather than decrementing a number that was already wrong. |
| 2026-08-07 (round 3) | Claude (session, cubic-dev-ai review triage on Tranc3#493) | `.gitmodules`, `workers/cranbania/.git` (confirmed submodule), every `.forgejo/workflows/*.yml`'s `actions/checkout` step | Round 2's "0 of 74" was itself wrong for `cranbania`: this session's checkout happens to have the `workers/cranbania` git submodule populated (Dockerfile genuinely present on disk here), but that's an artefact of this sandbox, not of the deploy pipeline — grepped every `.forgejo/workflows/*.yml` and found no `deploy-fly.yml`/`deploy-self-hosted.yml`/etc. `actions/checkout` step sets `submodules: true` or `recursive`; only the unrelated `sync-cranbania-submodule.yml` does. A real deploy-pipeline checkout would leave `workers/cranbania/` empty, and `docker compose build cranbania` would fail on a missing Dockerfile it does have in its own repo, just not fetched. Corrected the count to **73 of 74** non-submodule contexts confirmed, with `cranbania` flagged as a distinct, still-open, previously-undocumented defect (missing `submodules: recursive` on checkout, not a missing file) rather than folded into "resolved." |
| 2026-08-07 (round 4) | Claude (session, systematic duplication sweep) | Full `workers/` (92 dirs) vs `docker-compose.production.yml` (173 services) cross-reference; every checkout step across `.forgejo/`+`.github/` workflows that runs `pytest tests/` | Deleted `rate-limit-service-go` and, newly found in this pass, `monitoring-go` — both Go, both zero compose references, both dependency-bump-only commit history (no real feature work since creation), same class as `queue-service-go`. Fixed round 3's `cranbania` submodule-checkout gap on the 3 checkout steps that actually run `pytest tests/` (which includes tests reading real `compliance/magna-carta` content): `.forgejo/workflows/ci.yml`'s `full-suite` job, `.github/workflows/ci.yml`'s `Pytest` job, `.github/workflows/test.yml`'s `Full Pytest Suite` job. NOT yet applied to `nightly.yml`/`benchmark-eval.yml`/`phase7-nanoservices.yml`/`phase8-trancex.yml`, which run the same suite on a different cadence — same gap, lower priority, left open. Separately discovered: `.github/workflows/ci.yml`'s `Pytest` job and `test.yml`'s `Full Pytest Suite` job both end their pytest invocation with `\|\| true` ("Don't block PRs on test failures yet" / "during stabilization") — neither has ever actually gated on test results, which is *why* the submodule gap was invisible on every green PR check for as long as it existed. Only `.forgejo/workflows/ci.yml`'s `full-suite` job (self-hosted) genuinely enforces pytest results. Not fixed in this pass — `docs/governance/PYTHON-3.14-UPGRADE-ASSESSMENT.md` already documents 6 known-failing `tests/test_waivers.py` cases from cross-test state leakage, so removing the masking would immediately fail CI platform-wide until triaged; flagged as an explicit decision point rather than silently unmasked. Also new in this pass, not remediated (out of scope for a "dead code" fix — these are live production services, not stubs): `rate-limit-service-rs`/`vault-service-rs`/`nexus-ws-rs` (Rust) are each deployed *concurrently* with their Python originals rather than as unwired alternates, and `bullmq-queue-service` (Node) vs `queue-service` (Python) is a genuine same-responsibility overlap with no consumer wired to either — see `docs/governance/DUPLICATE-WORKER-FINDINGS.md`. |
