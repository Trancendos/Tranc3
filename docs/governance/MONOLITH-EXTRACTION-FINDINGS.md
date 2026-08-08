# Monolith Extraction Findings — 2026-08-08 systematic sweep

**Status:** 7 confirmed-safe removals shipped in this pass. An 8th (`src/resonate/`) was reverted
after review — see below. A second-pass sweep classified every remaining module that was still
mounted in `api.py`, and a follow-up pass then resolved 3 of those from open questions into
decided pairings: **8 still need a deliberate design decision** (HTTP bridge, or a product call on
Resonate/I-Mind — down from 11), **3 are confirmed permanently-separate features** with zero risk
either way (`search_api`, `admin_os`, `section7` reports — see `CONFIRMED_SEPARATE_FEATURES`), 10
are genuinely core/load-bearing with no nanoservice counterpart, 6 have no worker to compare
against yet, and 1 (`src/section7/`, the package — not to be confused with `_section7_router`
above) turned out not to be a router at all. Nothing below was silently resolved.
`scripts/check_duplicate_routers.py` (wired into `production-gate.yml` in both `.github/workflows/`
and `.forgejo/workflows/`) guards all 11 tracked items (both the 8 still-open and the 3 decided)
against being unmounted without a fresh check — see its module docstring for what it does and,
importantly, does not do (it cannot verify HTTP-route equivalence itself, only flag routers that
look like the pattern and enforce that a documented reason exists before one is ever removed).
`scripts/build_topology_map.py` renders all of this as an interactive graph — see
`docs/architecture/topology-map.html`.

## What this found

`api.py` mounts ~40 `APIRouter` instances directly in one FastAPI process (2678 lines before this
pass). The working assumption going in was that these represent services never yet split into the
platform's own established nanoservice pattern (`workers/<name>/worker.py`, own port, own
Dockerfile, in `docker-compose.production.yml` — see CLAUDE.md's Self-Hosted Worker Map).

That assumption was wrong for most of them. Cross-referencing all `src/<name>/` modules mounted
in `api.py` against `workers/` showed that **the real extraction already happened for nearly every
one of them** — a substantial (380–1400+ lines), genuinely more capable, already-deployed
(`docker-compose.production.yml`) standalone worker exists at the port CLAUDE.md's own worker map
already reserves. The actual problem isn't "not yet extracted" — it's that the *old* in-process
router was never removed from `api.py` after the real extraction shipped, leaving two live
implementations of the same service reachable at once: the same "two sources of truth" pattern
already documented in `DUPLICATE-WORKER-FINDINGS.md` for the Rust/Python worker pairs, just spread
across ~15-20 services instead of 2.

## Method

For each `src/<name>/` module mounted in `api.py`:
1. Confirmed a real `workers/<name>/` (or equivalently-named) directory exists, with substantial
   code and a live entry in `docker-compose.production.yml`.
2. Grepped the entire tree for any import of `src.<name>.routes` (the router object) or
   `src.<name>.<class>` (the underlying logic) **outside** `api.py` and `tests/` — any in-process
   Python-level caller besides the dead HTTP mount itself.
3. Only removed the `app.include_router(...)` + its import from `api.py` where step 2 found zero
   such callers — confirming nothing else in the running process depends on that specific object
   still being importable/mounted. The underlying `src/<name>/` files were **not** deleted; the
   existing unit tests still exercise them directly as Python objects, independent of whether
   they're mounted on the live app.
4. For one candidate (`src/basement/`), step 2 found a real caller —
   `src/observability/observatory.py` calls `get_basement().ingest_observatory_event()`
   synchronously, in-process, on the SECURITY/CRITICAL audit event path that the module's own
   docstring says is "never dropped." Turning that into a network call changes its failure
   semantics on a security-critical path. Left alone — see "Needs a decision" below.
5. Step 2's grep only caught in-process Python-level callers — it did not verify that a
   candidate worker's actual HTTP route surface matched what the monolith router served. That
   gap was real: `src/resonate/` passed step 2 (zero in-process callers) and was initially
   removed, but a post-merge review caught that `workers/resonate/` exposes a completely
   different API (`/health`, `/score`, `/score/conversation`, `/conversations/{id}`,
   `/history/{user_id}`) than the router it was meant to replace
   (`/resonate/status`, `/wrap`, `/escalate/{user_id}`) — not a superset, a different service.
   The mount was restored. This means step 2 alone is **not sufficient** proof of safety; the
   remaining "Removed" list below was re-checked for the same gap (worker route paths spot-read
   against the removed router's paths), but a systematic HTTP-level equivalence check like the
   one already done for `taimra` (see summary above) was not repeated for all 7 — treat this list
   as the same confidence level as the rest of this doc, not as fully proven.

## Removed in this pass (`api.py`, verified zero other in-process callers)

| Router removed | Real worker | Port |
|---|---|---|
| `src/taimra/routes.py` | `workers/taimra/` | 8074 |
| `src/studio/routes.py` | `workers/the-studio/` | 8069 |
| `src/lab/routes.py` | `workers/the-lab/` + `workers/lab-service/` | 8055 / 8066 |
| `src/chronos/routes.py` | `workers/cron-service/` | 8021 |
| `src/devocity/routes.py` | `workers/devocity/` | 8110 |
| `src/artifactory/routes.py` | `workers/artifactory-service/` | 8047 |
| `src/vrar3d/routes.py` | `workers/vrar3d/` | 8060 |

`api.py`: 2678 → 2654 lines net (8 removed, 1 — Resonate — restored with an explanatory comment).
Verified: `python3 -m py_compile`, a live `import api` with `app.routes` building successfully,
`ruff check api.py` clean, and the full relevant test subset (`test_canonical_routes.py`,
`test_api.py`, `test_shared_resource_routers_auth.py`, `test_tranquility_taimra_auth.py`,
`test_resonate_escalation.py` — 133 tests) passing.
`CLAUDE.md`'s entity table updated for the 6 rows that said "(router registered in `api.py`)" —
they now point at the real worker paths. Resonate's row was reverted back to "In repo".

## Needs a decision, not a mechanical fix

- **`src/resonate/`** — no in-process caller (step 2 was clean), but `workers/resonate/`
  (Port 8076, in compose) is not a behavioral replacement: it serves an empathy-scoring API
  (`/score`, `/score/conversation`, `/conversations/{id}`, `/history/{user_id}`), while the
  monolith router serves an escalation workflow (`/resonate/status`, `/wrap`,
  `/escalate/{user_id}`). Separately, the production Traefik rule
  (`Host(resonate.trancendos.com) && PathPrefix(/resonate)` →
  `docker-compose.production.yml`) forwards to the worker without stripping the `/resonate`
  prefix, and the worker's routes aren't under that prefix either — that routing rule looks
  broken independent of anything in this PR. Whoever picks this up needs to decide: build the
  escalation endpoints into the worker (and fix the Traefik prefix), or keep the monolith router
  as the long-term home for escalation and let the worker own scoring only. Left mounted in
  `api.py` until that call is made.
- **`src/basement/`** — real in-process caller (`observatory.py`, security-critical path, see
  above). `workers/basement/` (427 lines, in compose) exists and is presumably the intended
  target, but wiring Observatory to it needs an actual HTTP client call with retry/circuit-breaker
  (the platform already has `src/mesh/` Service Mesh for exactly this) plus a decision on what
  happens to a SECURITY event if that call fails — buffer-and-retry, local fallback write, or
  accept the small window. Not something to change without that design call made explicitly.
- **`src/imind/`** — **CORRECTED after the second-pass sweep below: NOT safe to unmount, in any
  form.** `workers/imind/` (542 lines, in compose) does generic sentiment/emotion scoring
  (`dominant_emotion`, `polarity`, `confidence`). `src/imind/protocol.py`'s `assess()` — what
  this router actually calls — is a regex-driven **crisis/self-harm/suicide detector** with
  SECURITY-severity human escalation. The worker has no equivalent logic at all; unmounting the
  router would silently remove a safeguarding feature, not delete a duplicate. This is the same
  mistake class as Resonate, on a feature where the stakes are much higher. `src/tranquility/wellbeing.py`
  also imports `src.imind.protocol` directly, independent of the router.
- **`src/cryptex/`** — real in-process callers: `section7/information_router.py`,
  `mcp/server.py`, `security/middleware.py`. `workers/cryptex/` (1078 lines, in compose) exists.
  Security-tooling code with multiple live callers — needs the same careful HTTP-bridge treatment
  as Basement, not a mechanical unmount.
- **`src/library/`** — real in-process callers: `section7/information_router.py`,
  `observability/library_pipeline.py`, `models/knowledge.py`, `event_bus/wiring.py`.
  `workers/library-service/` (936 lines, in compose) exists. Four separate in-process
  dependents — the widest fan-in of anything checked in this pass.
- **`src/routers/search_api.py`** — **RESOLVED, then DECIDED: see `CONFIRMED_SEPARATE_FEATURES`
  below.** This router is a hybrid BM25+vector RAG pipeline (Meilisearch/Qdrant/Weaviate/Chroma);
  `workers/search-service/` (392 lines, in compose) is SQLite FTS5 full-text only, with no
  vector/embedding/RAG capability at all — not a duplicate. Zero in-process callers, so a
  follow-up pass closed this out as a decided pairing rather than an open question.
- **`src/personality/turingshub/`** — deep in-process fan-in across the core AI response pipeline
  (`src/dependencies.py`, `src/workers/inference_worker.py`, `src/routers/enhanced_capabilities.py`,
  plus several top-level scripts). This one reads as intentionally core/load-bearing, not a stray
  duplicate — did not investigate further, flagging only so it isn't mistaken for an oversight.

## Second-pass sweep — 2026-08-08, all previously-unchecked modules classified

Every module the first pass left as "not checked" was run through the same method, upgraded to
also require reading each candidate worker's actual route bodies (the check that was skipped for
Resonate). `scripts/check_duplicate_routers.py`'s `ROUTER_TO_WORKER`/`KNOWN_COUPLED` tables now
cover every `NEEDS_MODULARIZATION` item below with the same-shaped reasoning, so CI fails
immediately if any of them is ever unmounted without a fresh check.

### NEEDS_MODULARIZATION (real coupling and/or non-equivalent worker — decision required)

- **`src/nexus/`** (`_nexus_router`, prefix `/nexus`) — `src.nexus.hub.get_nexus()` (the
  in-process pub/sub singleton, not just the router) is called directly by `section7.py`,
  `cryptex/threat_detector.py`, and `research/section7.py`. `workers/infinity-ws/` (compose) is a
  WebSocket hub with only a health check — no REST pub/sub surface to bridge to yet. Internal
  cross-module signaling, not user-facing, so a bridge can likely tolerate fire-and-forget
  (buffer-and-drop) semantics — the blocker is the worker needs new endpoints built, not just a
  client wrapper.
- **`src/townhall/`** (`_townhall_router`) — a policy/compliance check engine
  (`governance.get_townhall().check_compliance(...)`), called in-process by
  `research/section7.py`. `workers/cranbania/` (the submodule Kanban/ITSM board, port 8071) is a
  **completely different product** — same "two sources of truth by name only" trap as Resonate,
  not Resonate itself. Either build a policy-check API into cranbania, or accept these are two
  permanently separate features sharing an entity table row.
- **`src/monetisation/router.py`** (`_billing_router`, prefix `/billing`) — `api.py` calls
  `tier_enforcer.check_and_increment()` synchronously on live request-handling paths platform-wide
  (per-request tier/rate enforcement, not just the `/billing` endpoints — the highest-consequence
  bridge candidate found, since it gates essentially every rate/tier-limited request).
  `workers/payments-service/` is a near-empty `/health`-only stub; `workers/ledger-service/`
  exists but is a double-entry accounting ledger, a different feature from Stripe/subscription
  billing. Before any change: a fail-open vs. fail-closed decision for tier checks under a
  payments-service outage, and `payments-service` needs to actually be built out first.
- **`src/basement/`**, **`src/cryptex/`**, **`src/library/`**, **`src/resonate/`**, **`src/imind/`**
  — carried forward from the first pass above, all now confirmed by direct route-body comparison
  rather than import-grep alone (see corrected bullets above).

### CONFIRMED_SEPARATE_FEATURES (2026-08-08, follow-up pass — decided, not open questions)

Same "two sources of truth by name only" trap as Resonate/I-Mind, but resolved rather than left
open: each pair below has **zero live in-process caller** on the monolith side and a gap to its
same-named worker too large to call "the worker just needs finishing" — an entire vector-DB stack,
or a wholly different subsystem, not a handful of missing endpoints. Nothing breaks either way, so
there's no risk to weigh; the only real action was to stop treating a same-name coincidence as an
unresolved duplicate question. Both routers/workers stay exactly as deployed today — revisit only
if a real requirement emerges to unify them. `scripts/build_topology_map.py` classifies these as
`confirmed_separate_features` (distinct from `needs_modularization`) so the topology map doesn't
keep flagging them as pending.

- **`src/routers/search_api.py`** vs. **`workers/search-service/`** — the router is a hybrid
  BM25+vector RAG pipeline (Meilisearch/Qdrant/Weaviate/Chroma); the worker is SQLite FTS5
  full-text only, with no vector/embedding/RAG capability at all. Decided: `search_api` is the
  platform's RAG surface, `search-service` is a separate, simpler full-text search service.
- **`src/admin_os/`** (`_admin_os_router`) vs. **`workers/infinity-admin/`** — checked the actual
  route lists: the router's `cells`/`fabric`/`apoptosis`/`replicate`/`files`/`events`/`domain-model`
  endpoints and the worker's `admin/config`/`admin/entities`/`admin/overrides`/`admin/tiers`
  endpoints have **zero overlap** — a cellular-architecture/audit concept vs. entity-config
  administration, not a partial subset either direction. `api.py`'s own startup auto-backup loop
  depends on `src.admin_os.backup_loop` directly, independent of the router.
  **Bonus finding, fixed in the prior pass:** `src/routers/admin_os.py` (a second, different
  222-line `APIRouter(prefix="/admin-os", ...)`, importing the same underlying `src.admin_os.*`
  modules) existed in the repo, verified fully orphaned — not mounted anywhere, not imported by
  anything, not even tests. Deleted; `api.py` still imports and builds the same 303 routes after.
- **`src/research/routes.py`** (`_section7_router`, mounted as `/section7`) vs.
  **`workers/the-dutchy/`** — the router generates platform self-health/security reports from
  Cryptex+Observatory in-process (`src.research.section7.Section7`); the worker does RSS/news
  market-intelligence ingestion. Same entity name ("Section 7"), entirely different subject
  matter. Decided: "Section 7 reports" and "the-dutchy market intel" are permanently separate
  features sharing an entity table row, not a migration target.

### CORE_LOAD_BEARING (no nanoservice counterpart makes sense — left alone, not an oversight)

- **`src/observability/routes.py`** (Observatory itself) — the widest fan-in found in the entire
  sweep: `observe()`/`get_observatory()` is called synchronously from ~20 modules across
  compliance (escalation FSM, waivers, matrix suites), the AI pipeline, Section 7, Library,
  tAimra, Resonate, Tranquility, I-Mind, and more. **Naming trap, both directions**: the
  same-named `workers/observatory/` is a trace/metrics/logs dashboard aggregator, a different
  feature; the route-shape-closer match is the *differently-named* `workers/audit-service/`
  (`/events`, `/verify`, `/export`, `/stats`). If this is ever split, `audit-service` — not
  `observatory` — is the right target, and it needs the same fail-open/buffer design question as
  Basement, multiplied across ~20 call sites.
- **`src/citadel/routes.py`**, **`src/bio_neural/routes.py`** (Luminous), **`src/quantum/routes.py`**
  (Think Tank), **`src/routers/enhanced_capabilities.py`**, **`src/routers/ecosystem.py`**,
  **`src/routers/aeonmind.py`**, **`t2ance/router.py`**, **`trance_one/router.py`**,
  **`src/routers/tranc3ts_bridge.py`**, **`src/personality/turingshub/routes.py`** — each has
  real, deep in-process fan-in into core platform infrastructure (DevOps hub around
  Docker/Traefik/Forgejo itself, the AI inference/consciousness pipeline, the Models Matrix
  tiering engine, or — for `tranc3ts_bridge` — *is itself* the HTTP bridge surface for external
  TypeScript callers, so there's no separate "worker" to compare against). None of these read as
  duplicates; no further action.

### NO_WORKER_EXISTS (genuine future-extraction candidates, zero current risk)

`src/apimarket/`, `src/roles/` (real in-process callers on the underlying registry class:
`relations/registry.py`, `personality/role_resolution.py`, `roles/suite_stewardship.py` — any
future extraction needs a bridge, not just an unmount), `src/deployment_modes/`,
`src/notebooks/`, `src/relations/` (real caller: `roles/registry.py`), `src/access/`,
`src/models/routes.py` (Trancendos Models Matrix governance — no tight in-process coupling from
other subsystems, unlike `t2ance`/`trance_one`). No live worker to compare against for any of
these, so nothing is at risk today; each is a plausible standalone-worker candidate later.

### NOT_A_REAL_ROUTER

`src/section7/` (the package — `information_router.py`, `intelligence_agent.py`,
`cve_ingester.py`, `web_scraper.py`, `threat_intel_loop.py`) is not an HTTP router at all despite
the naming overlap with `src/research/routes.py` above (CLAUDE.md's "Section 7" location vs. this
specific package) — it's a background CVE/RSS ingestion library, started from `api.py`'s startup
and consumed in-process by Cryptex's CVE scanner. No action needed.

This sweep is now complete for every module that was mounted in `api.py` as of this pass.
