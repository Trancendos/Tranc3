# Service Doc-Pack — The Basement

| Field | Value |
|---|---|
| **Entity** | The Basement |
| **Lead AI** | Gary Glowman (Glow-Worm) |
| **Status** | ✅ In repo (per `CLAUDE.md` service table) — Live tier |
| **Code** | `src/basement/archive.py`, `src/basement/routes.py`; router registered in `api.py` (`app.include_router(_basement_router)`, line 790) — **plus a separate standalone worker**, `workers/basement/worker.py` (SQLite + FTS5, port 8088) |

> **Truthfulness:** claims cite `src/basement/archive.py` and `src/basement/routes.py` directly.
> Status is owned by the `CLAUDE.md` service table; identity by `PLATFORM_ENTITIES.md`. This pack
> supersedes the earlier charter-only placeholder (see Verification Log) once code was confirmed
> to exist and be live-wired.
> **Scope note (cubic-flagged):** The Basement has **two independent implementations** — the
> `src/basement/` module mounted into the main `api.py` app (documented below in full), and a
> separate standalone `workers/basement/worker.py` (FastAPI + SQLite/FTS5, port 8088) that this
> pack does **not** cover in detail. Every claim below that says "no worker" or "no database"
> refers specifically to the `src/basement/*` path, not to the entity as a whole — the standalone
> worker genuinely has both.

## 1. Service Governance Charter (GOV)

- **Mission:** archived intelligence layer — retains records that age out of The Observatory's
  active ring buffer, plus anything flagged for long-term retention, with semantic search over the
  archive.
- **Owner (RACI-A):** Gary Glowman (Glow-Worm); Platform Owner Trancendos.
- **Scope:** ingest archived records from four upstream sources (Observatory overflow, retired
  Library articles, completed workflow runs, inference logs), always retain SECURITY/CRITICAL
  events regardless of TTL, and expose read/search endpoints.

## 2. Detailed Design Document (DDD)

### HTTP surface (`src/basement/routes.py`, prefix `/basement`)

| Method | Route | Backing |
|---|---|---|
| GET | `/basement/stats` | `Basement.stats()` — record counts, retained count, by-source breakdown, vector-search availability |
| GET | `/basement/records` | `Basement.by_source()` / `Basement.recent()` — limit-bounded listing, `limit` 1–500, optional `source` filter |
| GET | `/basement/search` | `Basement.search()` — semantic (FAISS) or keyword fallback, `top_k` 1–50 |
| GET | `/basement/records/{record_id}` | `Basement.get()` — single record incl. full content; 404 `JSONResponse` if missing |

### Data model (`ArchiveRecord`, `archive.py`)
- Fields: `id` (uuid4), `timestamp`, `source` (`ArchiveSource` enum: `observatory`, `library`,
  `workflow`, `inference`, `security`), `event_type`, `content`, `metadata`, `embedding`
  (optional, not serialized to dict), `retained` (bool — never auto-purged).
- `to_dict()` truncates `content` to a 200-char `content_preview`; full `content` only returned by
  the single-record endpoint.

### Ingest paths
- `Basement.ingest()` — generic entry point; auto-sets `retained=True` if `source ==
  ArchiveSource.SECURITY` or `"security" in event_type`.
- `Basement.ingest_observatory_event()` — accepts an Observatory `AuditEvent` object, builds a
  content string (`"{event_type} | actor={actor} | target={target} | outcome={outcome}"`), and
  retains it if `event.severity in ("critical", "security")`.
- On ingest, if the embedder is available, the record is encoded and added to the FAISS index;
  embedding failures are caught and logged at debug level (ingest never fails on embedding error).

### Storage & eviction
- In-memory `Dict[str, ArchiveRecord]` plus a `source → [record_id]` index; no external DB.
- `MAX_RECORDS = 100_000`; `_evict()` removes the oldest **non-retained** records down to 90% of
  the cap when exceeded — retained (security/critical) records are never evicted by this path.

### Search (`Basement.search()`)
- If an embedder + FAISS index are active: `_faiss_search()` encodes the query, does a cosine
  (`IndexFlatIP`) top-k lookup, and returns `[(record, score)]` sorted by the index's own ordering.
- Fallback `_keyword_search()`: token-overlap scoring (`hits / len(terms)`), used whenever
  `faiss`/`sentence-transformers` aren't installed or FAISS init failed.

## 3. Technical Architecture Solutions Design (TASD)

- **Style (`src/basement/*` API path only):** in-process module with a module-level singleton
  (`get_basement()`) — this path stores state in the main FastAPI process's memory, with no
  database of its own. A separate `workers/basement/worker.py` standalone service also exists for
  this entity and does use SQLite/FTS5 — see the scope note above; this DDD/TASD does not cover it.
- **Decision: graceful vector-search degradation.** `_try_init_faiss()` wraps `import faiss` /
  `sentence-transformers` in a `try/except ImportError`; if unavailable, the module logs at debug
  level and falls back to keyword search rather than failing to start. This is a deliberate
  zero-cost/zero-hard-dependency choice.
- **Decision: retention overrides eviction.** Security/critical events are exempted from the
  `MAX_RECORDS` eviction path — trades memory growth risk for never silently losing an audit trail
  event, consistent with the entity's stated mission.
- **Rejected/deferred:** persistent storage (SQLite/disk) — current implementation is in-memory
  only and does not survive a process restart; this is a known gap, not yet addressed.

## 4. RACI Matrix

| Activity | Gary Glowman (Lead) | Platform Owner | The Observatory | Platform Engineering |
|---|---|---|---|---|
| Archive ingest logic changes | **R** | A | C | C |
| Retention policy (security/critical exemption) | **R/A** | C | C | I |
| Vector search / FAISS dependency changes | **R** | A | I | C |
| Persistence (in-memory → disk) migration | C | **A** | I | **R** |

## 5. Solutions Integration Model (SIM)

- **Upstream:** The Observatory (overflow events beyond its ring buffer, via
  `ingest_observatory_event()`); no other confirmed caller of `ingest()` in this codebase pass.
- **Downstream:** none — this is a terminal archive/read layer.
- **Auth boundary:** none of the 4 routes in `routes.py` carry an auth dependency — all are
  currently open on the mounted `/basement` prefix. This is a real, code-grounded finding, not a
  claim about intended behavior — if authentication is expected here, it is not yet implemented.

## 6. Architecture Scalability Document (ASD)

- **Load model:** read/search-heavy, low-write; single-process in-memory store with a hard cap
  (`MAX_RECORDS = 100_000`).
- **Bottleneck:** no horizontal scaling — state is process-local; a second replica would not share
  archive contents. No persistence in this in-process store means a restart loses **all** of its
  records, including retained security/critical events — `retained` only exempts a record from
  the `_evict()` eviction path, not from process-restart loss.
- **Zero-cost limits:** FAISS + sentence-transformers are optional dependencies; the service
  degrades to keyword search with zero added cost/infra when they're absent.
- **Degradation:** embedding/FAISS failures during ingest are swallowed (logged, not raised) — a
  record is still stored even if it can't be vector-indexed.

## 7. Deployment Scope Matrix (DSM)

- **Mode awareness:** No — this entity's own code does not call `PlatformInfraMode` / `src/platform/infrastructure_mode.py` (repo-wide grep confirms none of the 43 named platform entities branch on `PLATFORM_INFRA_MODE`/`SYSTEM_MODE` directly). Its deployment scope is determined externally — by which `docker-compose.production.yml` service block runs, and where — not by in-process mode detection.
- **Runtime placement:** mounted in the `tranc3-backend` monolith (`api.py`); runs wherever that monolith's `docker-compose.production.yml` service block is deployed, on whatever port/host the monolith uses (compose service `tranc3-backend`)
- **Persistence:** SQLite/volume shared with the rest of the monolith (`tranc3-backend` has a named volume in compose)

| Setup | What runs, and where | Data locality | Hard blockers / caveats |
|---|---|---|---|
| **Cloud-Only** | the `tranc3-backend` compose block runs on a single cloud host (e.g. Fly.io / Oracle Free Tier); Traefik/edge in front | backed by the monolith's attached volume — persists across redeploys as long as the volume is preserved | no entity-specific blocker beyond whatever applies to the monolith as a whole |
| **Hybrid** | same monolith block; per `docs/architecture/infrastructure-modes.md`'s Hybrid diagram, persistent data can sync to local TrueNAS while the monolith itself still runs wherever it's deployed | monolith volume, optionally mirrored to local TrueNAS via Syncthing | requires `CITADEL_LOCAL_STACK=true` if a local compose stack should run alongside the cloud one, per `should_run_citadel_docker()` in `infrastructure_mode.py` |
| **Local-Only** | same monolith block, run entirely on local/Citadel hardware behind local Traefik | fully local, volume-backed | none beyond standard local-hardware ops (backup, power, network) |

- **Zero-cost posture per mode:** Cloud-Only defaults to the `zero_cost_cloud` AI-rotation chain; Hybrid/Local-Only default to `zero_cost_full` (`config/platform/infrastructure_mode.yaml`) — this only affects AI-Gateway-routed calls, not this entity's own logic
- **Switching modes:** operator-level via `PLATFORM_INFRA_MODE` (or legacy `SYSTEM_MODE`); this entity needs no code change to move between modes, only a redeploy-target change for the monolith as a whole

## 8. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Web framework | FastAPI `APIRouter` | mounted into the main `api.py` app |
| Vector search | FAISS `IndexFlatIP` (optional) | OSS, in-process, degrades gracefully if absent |
| Embeddings | `sentence-transformers` `all-MiniLM-L6-v2` (optional) | OSS, local |
| Storage | in-memory `dict` (no persistence) | zero infra cost, but no durability |

## 9. Policy (POL)

- No route-level auth is currently implemented (see SIM §5) — reuse platform policy
  (`POL-AI-001`, `docs/defstan/`) if/when auth is added; this pack does not assert a policy that
  isn't reflected in code.
- Security/critical Observatory events MUST remain retained (never evicted) per the hard-coded
  `retained` exemption in `ingest()`/`ingest_observatory_event()`.

## 10. Procedure (PROC)

- **Query the archive:** `GET /basement/search?q=<query>&top_k=<n>` — returns semantic matches if
  FAISS is active, else keyword-overlap matches.
- **Inspect a record:** `GET /basement/records/{record_id}` for full content; `GET
  /basement/records` for a limit-bounded preview list.
- **Add vector search:** install `faiss` and `sentence-transformers` in the runtime environment —
  no code change needed; `_try_init_faiss()` activates automatically on next process start.

## 11. Runbook (RUN)

- **`/basement/stats` shows `vector_search: false`:** `faiss`/`sentence-transformers` aren't
  installed, or FAISS init raised — check logs for `"basement: FAISS init failed"` at WARNING
  level; the service still functions via keyword search.
- **Memory growth:** watch `total_records` vs `MAX_RECORDS` (100,000); eviction only removes
  non-retained records, so a workload dominated by security/critical events won't be capped —
  this is expected behavior per the retention policy, not a bug.
- **404 on `/basement/records/{id}`:** record was evicted (non-retained, aged out) or the ID never
  existed — check `/basement/stats.total_records` and `by_source` breakdown.

## 12. Standards (STD)

- Naming: canonical name "The Basement" per `CLAUDE.md`/`PLATFORM_ENTITIES.md`; code module is
  `src/basement/` (lowercase, matches convention used by other in-repo entities).
- `ArchiveSource` enum values are the single source of truth for valid `source` query-param
  values on `/basement/records` — any change must update both the enum and this doc.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-04 | Claude (session) | `src/basement/archive.py` (251 lines), `src/basement/routes.py` (47 lines), `api.py` router registration (line 790) | Confirmed Live-tier, full pack authored — DDD/TASD/SIM/ASD grounded in actual code; no auth on routes is a genuine finding (SIM §5), not fabricated. Supersedes the prior charter-only placeholder pack (see PR #199–#201 history in `docs/services/INDEX.md`). |
