# Service Doc-Pack — DocUtari

| Field | Value |
|---|---|
| **Entity** | DocUtari |
| **Lead AI** | To be Defined |
| **Status** | ✅ Live (two deployed workers: `files-service` port 8014, `storage-service` port 8020) |
| **Foundation** | `workers/files-service/worker.py` (Paperless-ngx/Stirling PDF/Gotenberg/Tika bridge) + `workers/storage-service/worker.py` (8-backend ACO object store) |

> **Truthfulness header (2026-07-07 rewrite).** This pack was previously Planned-tier
> (GOV+RACI+TFM+POL+STD only), asserting "no implementation exists yet." That was false: two
> substantial, real, deployed workers implement this entity's scope, confirmed via
> `docker-compose.production.yml`'s `files-service` (port 8014) and `storage-service`
> (port 8020) blocks and their Dockerfiles' `CMD ["uvicorn", "worker:app", ...]` invocations
> (both build directly from `worker.py`, unlike most other entities in this series — there is
> no separate `main.py` stub for DocUtari; `worker.py` is the deployed file in both cases).
>
> **DocUtari is unusual among the entities in this series: it maps to two separate compose
> services, not one.** `files-service` (`workers/files-service/worker.py`, 733 lines) is a
> document-management bridge (Paperless-ngx ingest, Tika parsing, Stirling PDF→Gotenberg
> fallback chain). `storage-service` (`workers/storage-service/worker.py`, 719 lines) is a
> separate, unrelated-in-code 8-backend object store with an ACO (ant-colony-optimisation)
> "pheromone" backend-selection algorithm (local → MinIO → IPFS → Valkey → DuckDB → SeaweedFS →
> Garage → offline). Both self-identify as DocUtari in their `/health` response bodies
> (`"entity": "DocUtari"`), but neither calls the other — they are two independent workers
> sharing one platform-entity name, not a single service split across ports.
>
> **Genuine defect found and fixed this pass (data-loss risk, not a routing/port defect like
> the rest of this series):** both workers write persistent state to disk paths that were
> **not durable** in `docker-compose.production.yml`:
> - `files-service`: `worker.py`'s `DB_PATH`/`UPLOAD_DIR` resolve to `/app/data/...`
>   (`Path(__file__).parent / "data"`), but the compose volume was mounted at `/data` — a
>   directory the app never writes to. The named volume `files-data` was therefore silently
>   unused; every container recreation would lose all uploaded documents and the SQLite
>   metadata database. Fixed by re-pointing the mount to `files-data:/app/data`.
> - `storage-service`: `worker.py`'s `STORAGE_DB_PATH`/`STORAGE_LOCAL_ROOT` both default to
>   `/data/...`, but **no volume was declared for this service at all** in compose — every
>   object stored via the (correctly-working) `local` backend, plus the SQLite bucket/object
>   metadata, was fully ephemeral, lost on every container restart. Fixed by adding a new
>   `storage-data:/data` named volume (declared in the compose `volumes:` top-level block).
>
> This is a different defect class than the Dockerfile-port-mismatch / Traefik-StripPrefix
> pattern found in every prior entity this session (The Academy, Sashas Photo Studio, Taimra,
> TateKing, Imaginarium, The Warp Tunnel, Warp Radio) — DocUtari's Dockerfile `EXPOSE`/
> `CMD --port` values (8014, 8020) already matched compose exactly, and neither service has a
> Traefik label at all (both are internal P2 services with no `PathPrefix` rule, so no
> StripPrefix gap was possible). The defect here is a volume-mount/write-path mismatch, unique
> to this entity in the series so far.
>
> **Documented, not fixed (needs an owner decision, same as other entities this session):**
> both workers' internal-auth header checks (`files-service`'s `INTERNAL_SERVICE_TOKEN`,
> `storage-service`'s `INTERNAL_SECRET`) default to an **empty string**, which both workers'
> `_auth()` dependencies treat as "auth disabled" (`if INTERNAL_TOKEN and x_internal_token !=
> INTERNAL_TOKEN: raise ...` — empty means the `and` short-circuits to allow every request).
> This is a different, arguably safer failure mode than the `"dev-secret"` hardcoded-fallback
> pattern found in several other entities' undeployed alternates this session (an attacker
> can't guess a fixed default value — there simply is no auth unless an operator sets one) but
> it means **both DocUtari workers are unauthenticated by default in this compose file**, since
> neither `INTERNAL_SERVICE_TOKEN` nor `INTERNAL_SECRET` is set in `docker-compose.production.yml`
> or `.env.example` for these two services. Flagged for the entity owner; not changed here since
> setting a real secret is a deployment-config decision, not a code fix.

## 1. Service Governance Charter (GOV)

- **Mission:** document management hub (ingestion, OCR, PDF operations, retrieval) plus a
  separate multi-backend zero-cost object storage layer, both operating under the DocUtari name.
- **In scope (`files-service`, port 8014):** document upload/list/get/update/soft-delete/
  download; async PDF job queue (compress/merge/split/rotate/watermark/remove-pages/
  extract-images/pdf-to-word/word-to-pdf/img-to-pdf/pdf-to-img/ocr) via Stirling PDF with
  Gotenberg fallback; Tika-based metadata/text extraction with a basic-mime-detection fallback;
  Paperless-ngx ingest + search/tags proxy; per-operation rate-limit "hard stop" thresholds
  (in-memory sliding window, configurable via env).
- **In scope (`storage-service`, port 8020):** bucket CRUD; object put/get/delete/list with
  metadata; time-limited download tokens; an 8-backend adaptive router (local filesystem,
  MinIO, IPFS, Valkey, DuckDB, SeaweedFS, Garage, offline stub) selected via a pheromone-score
  heuristic that reinforces successful backends and decays failing ones.
- **Out of scope:** DRM; paid cloud storage APIs (explicitly zero-cost per both workers'
  own module docstrings); any UI (this is an API-only backend pair).
- **Lead AI (Tier 3):** To be Defined — per `PLATFORM_ENTITIES.md`, this entity has not yet
  been assigned a Lead AI persona, despite having real, substantial code.
- **Owner (RACI-A):** Platform Owner (Trancendos), delegated to Platform Engineering pending
  Lead AI assignment.
- **Review cadence:** quarterly per framework default, or immediately if auth is enabled for
  either service.
- **Dependencies (soft, all optional with fallback/offline behaviour):** Paperless-ngx,
  Stirling PDF, Gotenberg, Apache Tika (none present in `docker-compose.production.yml` —
  `files-service` degrades gracefully when each is unreachable); MinIO, IPFS, Valkey, DuckDB,
  SeaweedFS, Garage (same — `storage-service`'s pheromone router falls through to `local` or
  `offline` when a backend is disabled/unreachable).

## 2. Domain-Driven Design (DDD) — HTTP Surface

### 2.1 `files-service` (`workers/files-service/worker.py`, port 8014)

| Method | Path | Auth | Behaviour |
|---|---|---|---|
| GET | `/health` | none | liveness + live backend-reachability probe (paperless/stirling/gotenberg/tika) |
| POST | `/api/documents/upload` | `X-Internal-Token`* | upload, store locally, background Tika parse + Paperless ingest |
| GET | `/api/documents` | `X-Internal-Token`* | list (filter by owner/status, paginated) |
| GET | `/api/documents/{doc_id}` | `X-Internal-Token`* | get one document |
| PATCH | `/api/documents/{doc_id}` | `X-Internal-Token`* | partial update (allow-listed fields) |
| DELETE | `/api/documents/{doc_id}` | `X-Internal-Token`* | soft delete |
| GET | `/api/documents/{doc_id}/download` | `X-Internal-Token`* | stream original file |
| POST | `/api/pdf/jobs` | `X-Internal-Token`* | queue async PDF operation |
| GET | `/api/pdf/jobs/{job_id}` | `X-Internal-Token`* | poll job status |
| GET | `/api/pdf/jobs/{job_id}/download` | `X-Internal-Token`* | stream completed result |
| GET | `/api/paperless/search` | `X-Internal-Token`* | proxy search to Paperless-ngx (503 if not configured) |
| GET | `/api/paperless/tags` | `X-Internal-Token`* | proxy tag list |
| GET | `/api/stirling/status` | `X-Internal-Token`* | Stirling PDF reachability |
| GET | `/api/stats` | `X-Internal-Token`* | document/job counts + configured thresholds |

\* Enforced only if `INTERNAL_SERVICE_TOKEN` is set — currently unset in compose/`.env.example`,
so every `/api/*` route is effectively open.

### 2.2 `storage-service` (`workers/storage-service/worker.py`, port 8020)

| Method | Path | Auth | Behaviour |
|---|---|---|---|
| GET | `/health` | none | liveness + per-backend enabled/healthy/pheromone snapshot |
| GET | `/storage/buckets` | `X-Internal-Secret`* | list buckets |
| POST | `/storage/buckets` | `X-Internal-Secret`* | create bucket (409 if exists) |
| DELETE | `/storage/buckets/{bucket}` | `X-Internal-Secret`* | delete bucket (409 if non-empty) |
| GET | `/storage/buckets/{bucket}/objects` | `X-Internal-Secret`* | list objects (prefix filter, paginated) |
| PUT | `/storage/buckets/{bucket}/objects/{key}` | `X-Internal-Secret`* | upload — routed to the pheromone-selected backend with local fallback |
| GET | `/storage/buckets/{bucket}/objects/{key}/meta` | `X-Internal-Secret`* | object metadata |
| GET | `/storage/buckets/{bucket}/objects/{key}` | `X-Internal-Secret`* | download (redirects to IPFS gateway for `ipfs` backend) |
| DELETE | `/storage/buckets/{bucket}/objects/{key}` | `X-Internal-Secret`* | delete object |
| POST | `/storage/buckets/{bucket}/objects/{key}/token` | `X-Internal-Secret`* | issue a time-limited download token |
| GET | `/storage/download/{token}` | none (token is the credential) | download via token |
| GET | `/storage/status` | `X-Internal-Secret`* | per-backend quota/pheromone snapshot + bucket totals |

\* Enforced only if `INTERNAL_SECRET` is set — currently unset in compose/`.env.example`, so
every `/storage/*` route is effectively open.

## 3. Technical Architecture & Solution Design (TASD)

- **`files-service`:** FastAPI + Uvicorn, SQLite (WAL) for document/job metadata, local
  filesystem for uploaded bytes, `httpx.AsyncClient` calls to 4 external OSS backends — every
  external call is wrapped in `try/except` with an explicit fallback (Stirling→Gotenberg) or a
  soft-degrade (Tika→basic mime detection, Paperless→skip). In-memory sliding-window rate
  guards (`_ThresholdGuard`) enforce per-operation hard stops (`DOCUTARI_PDF_THRESHOLD` etc.).
- **`storage-service`:** FastAPI + Uvicorn, SQLite (WAL) for bucket/object metadata, an
  ACO-inspired adaptive backend router (`ThresholdGuard` per backend tracks a quota window +
  a reinforcement/decay "pheromone" score; `_select_backend()` picks the healthiest-scoring
  enabled backend, always falling through to `local` then `offline`). Optional OpenTelemetry
  instrumentation is wired via `lifespan()` if `OTEL_EXPORTER_OTLP_ENDPOINT` is set.
- **Persistence (fixed this pass):** both services now have a durable named volume correctly
  aligned to their actual write path (`files-data:/app/data`, `storage-data:/data`).
- **Routing:** neither service has a Traefik label in `docker-compose.production.yml` — both
  are internal-only P2 services reached directly by container DNS name + port, not via the
  public reverse proxy. No StripPrefix defect class applies here (there is no `PathPrefix` rule
  to be missing a middleware for).

## 4. RACI Matrix

| Activity | Platform Owner | Platform Engineering | The Town Hall |
|---|---|---|---|
| Charter approval / scope changes | **A** | R | I |
| `files-service` maintenance | I | **R/A** | I |
| `storage-service` maintenance | I | **R/A** | I |
| Setting `INTERNAL_SERVICE_TOKEN`/`INTERNAL_SECRET` for production | I | **R/A** | I |
| Provisioning optional backends (Paperless-ngx, Stirling PDF, Gotenberg, Tika, MinIO, IPFS, Valkey, SeaweedFS, Garage) | I | **R/A** | I |
| Incident response | I | **R/A** | I |

## 5. Service Interaction Map (SIM)

```
files-service (8014, no Traefik route, internal only)
   ├─ SQLite (docutari.db, now on files-data volume at /app/data)
   ├─ local uploads (/app/data/uploads, now durable)
   ├─ Paperless-ngx (optional, PAPERLESS_INTERNAL_URL — not in compose)
   ├─ Stirling PDF (optional, STIRLING_PDF_URL — not in compose) ──▶ Gotenberg (fallback)
   └─ Apache Tika (optional, TIKA_URL — not in compose)

storage-service (8020, no Traefik route, internal only)
   ├─ SQLite (storage.db, now on storage-data volume, was ephemeral before this pass)
   ├─ local objects (/data/objects, now durable)
   ├─ MinIO (optional, not in compose) / IPFS (optional, not in compose)
   ├─ Valkey (optional, not in compose) / DuckDB (in-process, /data/storage.duckdb)
   └─ SeaweedFS / Garage (both disabled by default env flags)
```

No confirmed caller of either service was found elsewhere in the repo (`grep`-checked for
`files-service`/`storage-service`/`docutari` cross-references in `src/` and `api.py` — none) —
both are reachable only directly by whatever external client knows their container DNS name.

## 6. Application Service Design (ASD)

- `files-service`'s PDF job queue is fire-and-forget via FastAPI `BackgroundTasks` — job state
  transitions (`queued`→`done`/`failed`) are only visible via polling `GET /api/pdf/jobs/{id}`;
  there is no webhook/callback notification.
- `storage-service`'s backend selection is stateful in-process only (the `ThresholdGuard`
  pheromone scores reset on every restart) — this is a reasonable simplification for a
  single-instance deployment but would need shared state (e.g. Redis) to work correctly if
  ever horizontally scaled to multiple replicas.

## 7. Technology & Framework Matrix (TFM)

| Layer | Choice | Cost |
|---|---|---|
| Web framework (both) | FastAPI + Uvicorn | zero (OSS) |
| Metadata store (both) | SQLite (WAL) | zero (embedded) |
| Document backends (optional) | Paperless-ngx, Stirling PDF, Gotenberg, Apache Tika | zero (self-hosted OSS, none provisioned in compose today) |
| Object backends (optional) | MinIO, IPFS (kubo), Valkey, DuckDB, SeaweedFS, Garage | zero (self-hosted OSS/embedded, only `local`+`duckdb` guaranteed available) |

## 8. Policy & Compliance (POL)

- Both services currently run **unauthenticated by default** in this compose file (see
  truthfulness header). Any document or object handled by either service should be treated as
  accessible to anything that can reach the container network until an operator sets
  `INTERNAL_SERVICE_TOKEN` / `INTERNAL_SECRET`.
- Uploaded document content and object bytes are not scanned for malware/PII by either
  service — no integration with Cryptex or The Warp Tunnel/The Ice Box exists.

## 9. Procedures (PROC)

- **Local dev:** `cd workers/files-service && pip install -r requirements-worker.txt && uvicorn
  worker:app --port 8014` (and equivalently for `storage-service` on 8020).
- **Enabling auth:** set `INTERNAL_SERVICE_TOKEN` (files-service) / `INTERNAL_SECRET`
  (storage-service) in the deployment environment; both `_auth()` dependencies pick this up
  with no code change required.
- **Enabling an optional backend:** set the corresponding `*_URL`/`*_ENABLED` env var and add
  the backend's own container to `docker-compose.production.yml` (none of the 9 optional
  backends across both services are provisioned there today).

## 10. Runbook (RUN)

- **Health check:** `GET http://files-service:8014/health` / `GET http://storage-service:8020/health`.
- **Symptom: uploaded documents/objects disappear after a redeploy.** Before this pass, this
  was expected for both services (dead/missing volume mounts). Now fixed — if it recurs, check
  the `files-data`/`storage-data` volume declarations weren't reverted or the compose file
  wasn't run with `--volumes` on a `down`.
- **Symptom: `/api/paperless/search` returns 503.** Expected — `PAPERLESS_API_TOKEN` is unset;
  not a bug.

## 11. Standards (STD)

- Follows the same FastAPI/Uvicorn/SQLite-WAL conventions as other standalone workers audited
  this session.
- Any credential/backend provisioning must follow the zero-cost, self-hosted architecture
  principles in `CLAUDE.md`.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-04 | Claude (session) | `CLAUDE.md` service table, `PLATFORM_ENTITIES.md`, repo search | **SUPERSEDED — was wrong.** Concluded no implementation exists. |
| 2026-07-07 | Claude (session) | direct reads of `workers/files-service/worker.py` (733 lines), `workers/storage-service/worker.py` (719 lines), both Dockerfiles, and the `files-service`/`storage-service` blocks in `docker-compose.production.yml` | **Full rewrite to Live-tier (11 sections).** Found and fixed a genuine data-durability defect unique to this entity in the series: `files-service`'s volume was mounted at `/data` while the app writes to `/app/data` (dead mount, fixed by re-pointing the mount); `storage-service` had **no volume at all** despite writing to `/data` (fixed by adding a new `storage-data` volume). Documented, not fixed: both services are unauthenticated by default in this compose file (empty-string auth-token defaults, no `INTERNAL_SERVICE_TOKEN`/`INTERNAL_SECRET` set anywhere) — an owner decision, not a docs-pass fix. |
