# Service Doc-Pack — The Library

| Field | Value |
|---|---|
| **Entity** | The Library |
| **Lead AI** | Zimik |
| **Status** | ✅ In repo (per `CLAUDE.md` service table) — Live tier |
| **Code** | `src/library/knowledge_base.py`, `src/library/routes.py`; router registered in `api.py` (`app.include_router(_library_router)`, line 783) — **plus a separate standalone worker**, `workers/library-service/` (FastAPI + SQLite, port 8067, internal-secret auth, multi-backend wiki adapter) |

> **Truthfulness:** claims cite `src/library/knowledge_base.py`, `src/library/routes.py`,
> `src/observability/library_pipeline.py`, `workers/library-service/`, and
> `docker-compose.production.yml` directly. Status is owned by the `CLAUDE.md` service table;
> identity by `PLATFORM_ENTITIES.md`.
> **Scope note (established pattern):** The Library has **two independent implementations** —
> the `src/library/` module mounted into the main `api.py` app (documented below in full,
> in-process, no own database), and a separate standalone `workers/library-service/` (FastAPI +
> SQLite, port 8067, internal-secret-authed, `/library/documents` + `/library/search` schema
> that does **not** match `src/library`'s `/library/articles` schema) that this pack does **not**
> cover in detail beyond the port-defect fix below. Claims below that say "no persistence" or
> "no auth" refer specifically to the `src/library/*` path, not to the entity as a whole.
> **Bug found and fixed while authoring this pack:** `workers/library-service/Dockerfile`
> hardcoded `EXPOSE 8053` / `HEALTHCHECK ... localhost:8053` / `CMD ["uvicorn", ..., "--port",
> "8053"]`, while `docker-compose.production.yml` sets `LIBRARY_PORT=8067`, maps `"8067:8067"`,
> and routes Traefik to container port `8067`. Because the Dockerfile `CMD` hardcodes the uvicorn
> `--port` flag, it overrides the `LIBRARY_PORT` env var entirely — the container actually bound
> port 8053, so nothing listened on 8067. This means the compose port mapping, Traefik routing,
> **and compose's own healthcheck** (which curls `localhost:8067`) would all have failed against
> a running container — a genuine, previously unflagged production routing defect (distinct from
> the four `CLAUDE.md` §188 "routing defects" already resolved, since those all had matching
> CMD/compose ports; this one didn't). Fixed by changing the Dockerfile's `EXPOSE`, `HEALTHCHECK`,
> and `CMD --port` to `8067`, and `workers/library-service/config.py`'s `LIBRARY_PORT` default to
> `8067` for consistency when run outside the container.

## 1. Service Governance Charter (GOV)

- **Mission:** knowledge base and documentation store for platform guides, articles, and
  institutional knowledge; intended to feed The Spark's RAG pipeline and receive triggered
  articles from Observatory audit events.
- **Owner (RACI-A):** Zimik; Platform Owner Trancendos.
- **Scope:** article CRUD, tag-based retrieval, simple substring search (`src/library/*`); a
  separate standalone worker (`workers/library-service/`) additionally targets a
  multi-backend wiki adapter (Outline/BookStack/Wiki.js/Gollum/DokuWiki/MkDocs/Gitea/TiddlyWiki
  per its compose comment) — not covered in detail by this pack.

## 2. Detailed Design Document (DDD)

### HTTP surface (`src/library/routes.py`, prefix `/library`)

| Method | Route | Backing |
|---|---|---|
| GET | `/library/stats` | `Library.stats()` — total articles, by-status, by-source, tag count |
| GET | `/library/articles` | `Library.by_tag()` or `Library.recent()` — `tag` and `status` filters, `limit` 1–200, defaults to `PUBLISHED` status |
| GET | `/library/articles/search` | `Library.search()` — substring match on title/body, `limit` 1–100 |
| GET | `/library/articles/{id}` | `Library.get()` — 404 `JSONResponse` if missing; only endpoint returning full `body` |
| POST | `/library/articles` | `Library.create()` — title/body/tags/author in request body |
| DELETE | `/library/articles/{id}` | `Library.delete()` — 404 `JSONResponse` if missing |

**Gap:** `Library.update()` exists in `knowledge_base.py` (arbitrary-attribute update via
`**kwargs`) but is **not exposed via any HTTP route** — `routes.py` has no `PUT`/`PATCH`
endpoint. Articles are updatable only via direct in-process calls, not over `/library/*`.

### Data model (`Article`, `knowledge_base.py`)
- Fields: `id` (uuid4), `title`, `body`, `tags`, `status` (`ArticleStatus`: draft/published/
  archived), `author`, `created_at`, `updated_at`, `source` (`"internal"|"outline"|"observatory"`),
  `outline_id` (optional external Outline ID — see integration gap below).
- `to_dict()` truncates `body` to a 200-char `body_preview`; full `body` only returned by the
  single-article endpoint.
- Storage: in-memory `Dict[str, Article]` plus a `tag → [article_id]` index; no external DB, no
  persistence.
- Seeded on startup with 6 hard-coded platform-documentation articles (The Spark, The Digital
  Grid, The Observatory, The Void, The Workshop, Zero-Cost Architecture) via
  `_seed_platform_articles()`.

### Observatory → Library pipeline (`src/observability/library_pipeline.py`) — dead code
- Module docstring: "wires audit events to KB article triggers." `start_pipeline()` **is**
  called from `api.py` (line ~559) on startup, which registers a background `flush_loop()`
  coroutine that drains an internal `_queue` every `FLUSH_INTERVAL_SEC` (default 30s) and POSTs
  any batch to `f"{LIBRARY_URL}/kb/ingest"`.
- **However, `ingest()` — the only function that ever appends to `_queue`  — is never called
  from anywhere in this codebase.** `api.py` only imports and calls `start_pipeline()`; no
  Observatory event handler calls `library_pipeline.ingest()`. The queue is permanently empty;
  `flush_loop()` runs forever flushing nothing.
- Even if `ingest()` were wired up, `_send_batch()` POSTs to `{LIBRARY_URL}/kb/ingest` — **no
  `/kb/ingest` endpoint exists** in either `src/library/routes.py` or
  `workers/library-service/router.py`; the POST would 404.
- `LIBRARY_URL` also defaults to `http://localhost:8024` (commented `# search-service / wiki`),
  which per `CLAUDE.md`'s port table is `config-service`'s port, not `library-service`'s (8067)
  or `search-service`'s (8017) — a second latent inconsistency in this same dead path.
- **Net effect:** the "Observatory → Library" integration described in the module docstring and
  the `src/library/knowledge_base.py` header comment ("Triggered by Observatory audit events...")
  does not run in practice. Left undocumented as fixed/working in prior passes; documented here
  as a real, unwired gap rather than silently repaired, since wiring it up would mean adding new
  API surface (`/kb/ingest`) and a real Observatory event-subscriber — an architectural decision
  out of scope for this doc-pass.

### RAG / FAISS integration — not implemented
- `knowledge_base.py`'s module header claims "Feeds The Spark's RAG pipeline via The Basement's
  FAISS index" — no such call exists in `src/library/knowledge_base.py` (no `embed_article()`,
  no import of `src.basement`). This is aspirational documentation in the source comment, not
  implemented behavior.

### Outline integration — not implemented in `src/library/*`
- The `Article.outline_id` field exists but nothing in `src/library/knowledge_base.py` ever sets
  it except a direct constructor argument passed by a caller — there is no sync code that talks
  to an external Outline instance from this path. (The separate `workers/library-service/`
  worker does define `OUTLINE_URL`/`OUTLINE_API_KEY` config and depends on an `outline` compose
  service — that integration lives entirely in the standalone worker, not `src/library/*`.)

## 3. Technical Architecture Solutions Design (TASD)

- **Style (`src/library/*` API path):** in-process module with a module-level singleton
  (`get_library()`) — in-memory dict storage, no persistence, no external DB. The separate
  `workers/library-service/` worker uses SQLite (`database.py`) and internal-secret HTTP auth —
  see scope note above.
- **Decision: simple substring search over semantic search.** `Library.search()` is a plain
  case-insensitive substring match, not FAISS/embeddings — despite the module header's RAG claim
  (see DDD gap above). Zero-cost, zero-dependency, but no semantic ranking.
- **Fixed defect:** `workers/library-service/Dockerfile` hardcoded port 8053 while
  `docker-compose.production.yml` routed to 8067 — see truthfulness header. Fixed by aligning
  the Dockerfile's `EXPOSE`/`HEALTHCHECK`/`CMD --port` and `config.py`'s default to 8067.
- **Known unwired gap, not fixed:** the Observatory→Library pipeline (`library_pipeline.py`) is
  dead code — `start_pipeline()` runs but `ingest()` is never invoked, and even if it were, the
  target `/kb/ingest` endpoint doesn't exist on either implementation. See DDD.

## 4. RACI Matrix

| Activity | Zimik (Lead) | Platform Owner | The Observatory | Platform Engineering |
|---|---|---|---|---|
| Article CRUD / search logic changes | **R** | A | I | C |
| Observatory→Library pipeline wiring (future) | C | **A** | **R** | R |
| `workers/library-service` (standalone) changes | **R** | A | I | C |

## 5. Solutions Integration Model (SIM)

- **Upstream:** any caller of `/library/*` routes — no auth on any route in `src/library/routes.py`
  (the standalone `workers/library-service` worker, by contrast, requires an `X-Internal-Secret`
  header on its own routes — see scope note above).
- **Downstream:** best-effort Observatory `observe()` call and Event Bus `emit_async()` call on
  every create/update/delete, both wrapped in bare `except Exception: pass` (`# nosec B110`).
- **Not integrated:** the reverse direction (Observatory → Library, "audit events trigger KB
  articles") is present in code but never actually invoked — see DDD dead-code section. No FAISS/
  Basement RAG integration exists despite the module header's claim.

## 6. Architecture Scalability Document (ASD)

- **Load model:** in-memory dict store, no cap defined (unlike The Basement's `MAX_RECORDS`
  pattern) — unbounded growth, no eviction.
- **Bottleneck:** single-process, no persistence; a restart loses all articles except the 6
  hard-coded seed articles re-created on next `Library()` instantiation.
- **Zero-cost limits:** no external dependency in `src/library/*` — the standalone worker adds a
  SQLite file and depends on external wiki-backend services per its compose block.
- **Degradation:** Observatory/Event-Bus emission failures don't block the CRUD response.

## 7. Deployment Scope Matrix (DSM)

- **Mode awareness:** No — this entity's own code does not call `PlatformInfraMode` / `src/platform/infrastructure_mode.py`. (Some platform-wide, cross-cutting code *does* branch on the mode — `src/routers/adaptive.py` and `src/routers/ecosystem.py` read/set `PLATFORM_INFRA_MODE`/`SYSTEM_MODE` directly, and `Dimensional/architecture/storage_factory.py` selects a storage provider from `SYSTEM_MODE` — but none of that code is owned by this or any other one of the 43 named entities; it is shared platform infrastructure, not this service's own logic. The Citadel is the only one of the 43 named entities whose own code branches on the mode — see `docs/services/the-citadel/README.md`.) This entity's deployment scope is determined externally — by which `docker-compose.production.yml` service block runs, and where — not by in-process mode detection.
- **Runtime placement:** standalone worker with its own `docker-compose.production.yml` service block (`library-service`, port 8067) and its own Traefik route (`PathPrefix(/library)`) — does not run inside the `tranc3-backend` monolith. (Note: this service's Traefik labels use map-style YAML — `traefik.enable: "true"` — rather than the list-style `- "traefik.enable=true"` most other services use; both are equivalent, but worth knowing if you're grepping the compose file.)
- **Persistence:** named volume attached to the `library-service` compose service — state survives container restarts/redeploys in any mode
- **Note:** this entity has **two** deployment surfaces — a router mounted in the `tranc3-backend` monolith (`api.py`) *and* a separate standalone worker (`library-service`, port 8067). The table below describes the standalone worker; the monolith-mounted router follows the monolith's own placement (see the monolith pattern noted across this platform's other entities) and shares its volume.

| Setup | What runs, and where | Data locality | Hard blockers / caveats |
|---|---|---|---|
| **Cloud-Only** | the `library-service` compose block runs on a single cloud host; Traefik/edge in front | persists via its attached volume as long as the volume/disk is preserved on that host | none beyond standard single-host durability (no built-in cross-host replication) |
| **Hybrid** | same `library-service` compose block; per `docs/architecture/infrastructure-modes.md`'s Hybrid diagram, this worker itself still runs as a single instance (cloud or local host), with only shared persistent data (not specific to this worker) split via TrueNAS/Syncthing | as above, optionally local-synced if a volume exists | requires `CITADEL_LOCAL_STACK=true` if a local compose stack should run alongside the cloud one |
| **Local-Only** | same `library-service` compose block, run entirely on local/Citadel hardware behind local Traefik | fully local, volume-backed | none beyond standard local-hardware ops |

- **Zero-cost posture per mode:** Cloud-Only defaults to the `zero_cost_cloud` AI-rotation chain; Hybrid/Local-Only default to `zero_cost_full` (`config/platform/infrastructure_mode.yaml`) — this only affects AI-Gateway-routed calls, not this entity's own logic
- **Switching modes:** operator-level via `PLATFORM_INFRA_MODE` (or legacy `SYSTEM_MODE`); this entity needs no code change to move between modes, only a redeploy-target change for its own compose block

## 8. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Web framework | FastAPI `APIRouter` | mounted into the main `api.py` app |
| Search | Python substring match (`src/library/*`) | OSS, in-process, zero cost; not semantic |
| Storage | in-memory `dict` (`src/library/*`), no persistence | zero infra cost, no durability |
| Standalone worker | `workers/library-service/` — SQLite + multi-backend wiki adapter | self-hosted, port 8067 |

## 9. Environment Support Matrix (ESM)

> Grounded against `docker-compose.development.yml` (6 services), `docker-compose.uat.yml` (16 services), and `docker-compose.production.yml` (286 services) — checked by exact compose service name, not assumed.

| Environment | Covered? | What runs | Notes |
|---|---|---|---|
| **Dev** | Partial | the `api` service in `docker-compose.development.yml` runs the monolith router — the standalone `library-service` worker is **not** in this compose file | standalone worker has zero Dev coverage |
| **UAT** | Partial | same monolith router via `api` in `docker-compose.uat.yml` — the standalone `library-service` worker is **not** in this compose file either | standalone worker has zero UAT coverage |
| **Production** | Yes | both surfaces — full detail in the DSM above | — |

- **Gap:** the standalone `library-service` worker (the more complete of this entity's two surfaces, per the DSM above) has **no Dev or UAT environment at all** — the first place it runs is Production. This is the norm for the ~90 standalone workers on this platform, not specific to this entity, but worth stating plainly rather than assuming pre-production validation exists where it doesn't.

## 10. Policy (POL)

- **Security gap, not fixed:** `src/library/*` routes (mounted in `api.py`, including create/
  update/delete mutations) have no route-level auth at all — any caller reaching `api.py` can
  mutate the knowledge base with no credential check. See SIM §5. The standalone worker
  (`workers/library-service`) enforces `X-Internal-Secret` auth on its own routes, but that path is
  a separate, currently-unaudited implementation (see scope note above) — it does not protect
  `src/library/*`.
- Zero-cost mandate: any future Outline/BookStack/etc. backend wiring must pass
  `scripts/zero_cost_audit.py` per The Citadel's deploy gate.

## 11. Procedure (PROC)

- **Create an article:** `POST /library/articles` with `{"title": "...", "body": "...", "tags":
  [...], "author": "..."}` — status is always set to `PUBLISHED` on create (no draft-via-API path).
- **Search articles:** `GET /library/articles/search?q=<query>` — substring match only, not
  semantic.
- **Update an article:** not exposed over HTTP in `src/library/*` — see DDD gap; would require
  calling `Library.update()` in-process or adding a route.

## 12. Runbook (RUN)

- **Articles disappear after a restart:** expected — `src/library/*` has no persistence; only
  the 6 seed articles reappear.
- **Observatory events don't produce new Library articles:** expected — the pipeline is unwired
  dead code (see DDD); this is not a transient failure to troubleshoot, it never runs.
- **`workers/library-service` unreachable at port 8067:** was a genuine Dockerfile/compose port
  mismatch (container bound 8053, compose routed 8067) — fixed in this pass; confirm the fix
  (Dockerfile `EXPOSE`/`HEALTHCHECK`/`CMD` all `8067`) is present in the deployed image if this
  recurs.
- **`/library/articles/{id}` returns 404:** article ID never existed or the process restarted
  since it was created (no persistence).

## 13. Standards (STD)

- Naming: canonical entity name "The Library" per `CLAUDE.md`/`PLATFORM_ENTITIES.md`.
- Any Dockerfile that hardcodes a `--port` CLI flag MUST match the port set in
  `docker-compose.production.yml`'s `environment:`/`ports:`/Traefik block for that service — a
  mismatched hardcoded port silently breaks the container's reachability even though the app
  code reads the correct env var, because the CLI flag wins. The defect fixed here is the reason
  for this standard.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-05 | Claude (session) | `src/library/knowledge_base.py` (277 lines), `src/library/routes.py` (62 lines), `src/observability/library_pipeline.py`, `workers/library-service/` (Dockerfile, config.py, router.py), `api.py` router registration (line 783), `docker-compose.production.yml` | Confirmed Live-tier, full pack authored. Found and fixed a genuine production defect: `workers/library-service/Dockerfile` hardcoded port 8053 while compose routed to 8067, making the container unreachable at its intended port. Also documented (not fixed, architectural): the Observatory→Library pipeline is dead code (`ingest()` never called, and its target `/kb/ingest` endpoint doesn't exist anywhere); the RAG/FAISS and Outline-sync integrations claimed in source comments are not implemented in `src/library/*`; `Library.update()` has no HTTP route. |
| 2026-07-07 | Claude (session, cubic-dev-ai review triage) | `monitoring/prometheus.yml`, `docker-compose.production.yml` (this service's comment block), `src/library/routes.py` | Verified and fixed two further cubic findings. (1) The 8053→8067 port fix from the prior pass had not been propagated to `monitoring/prometheus.yml`'s scrape target (still `library-service:8053`) or to a stale "(Port 8053...)" comment on this service's compose block — both updated to 8067; `scripts/port_registry_validate.py` re-run and passes. (2) The POL section stated "no route-level auth" as a neutral fact rather than flagging it as a gap — reworded to explicitly call out the unauthenticated mutation routes as a security gap, and clarified that the standalone worker's auth does not cover `src/library/*`. |
