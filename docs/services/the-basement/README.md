# Service Doc-Pack — The Basement

| Field | Value |
|---|---|
| **Entity** | The Basement |
| **Lead AI** | Gary Glowman (Glow-Worm) |
| **Status** | ✅ In repo (per `CLAUDE.md` service table) — Live tier |
| **Code** | `src/basement/archive.py`, `src/basement/routes.py`; router registered in `api.py` (`app.include_router(_basement_router)`, line 790) |

> **Truthfulness:** claims cite `src/basement/archive.py` and `src/basement/routes.py` directly.
> Status is owned by the `CLAUDE.md` service table; identity by `PLATFORM_ENTITIES.md`. This pack
> supersedes the earlier charter-only placeholder (see Verification Log) once code was confirmed
> to exist and be live-wired.

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

- **Style:** single in-process module with a module-level singleton (`get_basement()`); no
  separate worker process or database — state lives in the FastAPI process's memory.
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
  archive contents. No persistence means a restart loses all non-retained history.
- **Zero-cost limits:** FAISS + sentence-transformers are optional dependencies; the service
  degrades to keyword search with zero added cost/infra when they're absent.
- **Degradation:** embedding/FAISS failures during ingest are swallowed (logged, not raised) — a
  record is still stored even if it can't be vector-indexed.

## 7. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Web framework | FastAPI `APIRouter` | mounted into the main `api.py` app |
| Vector search | FAISS `IndexFlatIP` (optional) | OSS, in-process, degrades gracefully if absent |
| Embeddings | `sentence-transformers` `all-MiniLM-L6-v2` (optional) | OSS, local |
| Storage | in-memory `dict` (no persistence) | zero infra cost, but no durability |

## 8. Policy (POL)

- No route-level auth is currently implemented (see SIM §5) — reuse platform policy
  (`POL-AI-001`, `docs/defstan/`) if/when auth is added; this pack does not assert a policy that
  isn't reflected in code.
- Security/critical Observatory events MUST remain retained (never evicted) per the hard-coded
  `retained` exemption in `ingest()`/`ingest_observatory_event()`.

## 9. Procedure (PROC)

- **Query the archive:** `GET /basement/search?q=<query>&top_k=<n>` — returns semantic matches if
  FAISS is active, else keyword-overlap matches.
- **Inspect a record:** `GET /basement/records/{record_id}` for full content; `GET
  /basement/records` for a limit-bounded preview list.
- **Add vector search:** install `faiss` and `sentence-transformers` in the runtime environment —
  no code change needed; `_try_init_faiss()` activates automatically on next process start.

## 10. Runbook (RUN)

- **`/basement/stats` shows `vector_search: false`:** `faiss`/`sentence-transformers` aren't
  installed, or FAISS init raised — check logs for `"basement: FAISS init failed"` at WARNING
  level; the service still functions via keyword search.
- **Memory growth:** watch `total_records` vs `MAX_RECORDS` (100,000); eviction only removes
  non-retained records, so a workload dominated by security/critical events won't be capped —
  this is expected behavior per the retention policy, not a bug.
- **404 on `/basement/records/{id}`:** record was evicted (non-retained, aged out) or the ID never
  existed — check `/basement/stats.total_records` and `by_source` breakdown.

## 11. Standards (STD)

- Naming: canonical name "The Basement" per `CLAUDE.md`/`PLATFORM_ENTITIES.md`; code module is
  `src/basement/` (lowercase, matches convention used by other in-repo entities).
- `ArchiveSource` enum values are the single source of truth for valid `source` query-param
  values on `/basement/records` — any change must update both the enum and this doc.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-04 | Claude (session) | `src/basement/archive.py` (251 lines), `src/basement/routes.py` (47 lines), `api.py` router registration (line 790) | Confirmed Live-tier, full pack authored — DDD/TASD/SIM/ASD grounded in actual code; no auth on routes is a genuine finding (SIM §5), not fabricated. Supersedes the prior charter-only placeholder pack (see PR #199–#201 history in `docs/services/INDEX.md`). |
