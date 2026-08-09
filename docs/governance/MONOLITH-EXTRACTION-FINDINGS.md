# Monolith Extraction Findings — 2026-08-08 systematic sweep

**Status:** 7 confirmed-safe removals shipped in this pass. An 8th (`src/resonate/`) was reverted
after review — see below. A second-pass sweep classified every remaining module that was still
mounted in `api.py`, and a follow-up pass then resolved 3 of those from open questions into
decided pairings, followed by a remediation pass (2026-08-08, after the owner made an explicit
fail-open call — see `BRIDGES_IMPLEMENTED` below) that built working HTTP bridges for 4 more:
**only 2 still need a deliberate product decision** (Resonate/I-Mind — down from 11, and both are
"does the worker need to gain a missing feature" calls, not engineering work), **5 are bridged**
(`src/nexus/` was found already-bridged while starting this pass — see `BRIDGED` — and
`src/basement/`, `src/cryptex/`, `src/monetisation/` (billing), `src/library/` were newly bridged
this same pass, all fail-open by the owner's explicit 2026-08-08 decision — see
`BRIDGES_IMPLEMENTED`), **4 are confirmed permanently-separate features** with zero risk either way
(`search_api`, `admin_os`, `section7` reports, `townhall` — see `CONFIRMED_SEPARATE_FEATURES`), 10
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
- **`src/basement/`** — **BRIDGED 2026-08-08, see `BRIDGES_IMPLEMENTED`.** Real in-process caller
  (`observatory.py`, security-critical path, see above). `workers/basement/` (427 lines, in
  compose) exists and is presumably the intended target, but wiring Observatory to it needs an
  actual HTTP client call with retry/circuit-breaker (the platform already has `src/mesh/` Service
  Mesh for exactly this) plus a decision on what happens to a SECURITY event if that call fails —
  buffer-and-retry, local fallback write, or accept the small window. Not something to change
  without that design call made explicitly.
- **`src/imind/`** — **CORRECTED after the second-pass sweep below: NOT safe to unmount, in any
  form.** `workers/imind/` (542 lines, in compose) does generic sentiment/emotion scoring
  (`dominant_emotion`, `polarity`, `confidence`). `src/imind/protocol.py`'s `assess()` — what
  this router actually calls — is a regex-driven **crisis/self-harm/suicide detector** with
  SECURITY-severity human escalation. The worker has no equivalent logic at all; unmounting the
  router would silently remove a safeguarding feature, not delete a duplicate. This is the same
  mistake class as Resonate, on a feature where the stakes are much higher. `src/tranquility/wellbeing.py`
  also imports `src.imind.protocol` directly, independent of the router.
- **`src/cryptex/`** — **BRIDGED 2026-08-08, see `BRIDGES_IMPLEMENTED`.** Real in-process callers:
  `section7/information_router.py`, `mcp/server.py`, `security/middleware.py`.
  `workers/cryptex/` (1078 lines, in compose) exists. Security-tooling code with multiple live
  callers — needs the same careful HTTP-bridge treatment as Basement, not a mechanical unmount.
- **`src/library/`** — **BRIDGED 2026-08-08 (write-path only — see `BRIDGES_IMPLEMENTED`).** Real
  in-process callers (synchronous `.create()`/`.by_tag()` writes/reads on
  the singleton, not just imports of the router): `section7/information_router.py`,
  `observability/library_pipeline.py`, `models/knowledge.py`, `event_bus/wiring.py`. Four separate
  in-process dependents — the widest fan-in of anything checked in this pass. `workers/library-service/`
  (936 lines, in compose) exists, but **remediation-pass check found it is not a safe bridge target
  as-is**: `src/library/knowledge_base.py`'s `Article` carries a `DataClassification`
  (PUBLIC/INTERNAL/CONFIDENTIAL/RESTRICTED/TOP_SECRET) enforced by `routes.py`'s `_can_read()` —
  RESTRICTED/TOP_SECRET articles require the caller to be an admin or the article's own author —
  plus per-article `author` and `retention_days`. `workers/library-service/` is a generic pluggable
  wiki-backend facade (Outline/BookStack/WikiJS/Gollum/DokuWiki/MkDocs/Gitea/TiddlyWiki) with no
  classification, author, or retention concept, and no per-caller authorization at all — only a
  shared `X-Internal-Secret` that authenticates the *bridge*, not the end caller. Bridging the
  in-process writes to it as-is would silently drop the access-control layer, the same failure
  class as the reverted Resonate removal. Needs a decision — extend the worker's model with
  classification/author/retention and per-caller authorization first, or accept these stay
  separate the way `search_api`/`admin_os`/`section7` were — before any bridge is built, not a
  plain client wrapper. Grouped with basement/cryptex/billing as needing the user's input before
  writing bridge code, since it's a security-classification question, not a plumbing one.
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

Only `resonate` and `imind` remain here — both need a *product* decision (does the worker need to
gain a missing feature, or does the monolith router stay the long-term home for that feature),
not an engineering bridge. Everything else that was here — `basement`, `cryptex`, `monetisation`
(billing), and `library` — was resolved this pass; see `BRIDGES_IMPLEMENTED` below.

- **`src/resonate/`**, **`src/imind/`** — carried forward from the first pass above (see corrected
  bullets there): both have a same-named worker that is missing a distinct feature (empathy
  escalation vs. scoring; crisis/self-harm detection vs. generic sentiment scoring), not a partial
  gap a client wrapper can paper over. Unlike the four bridged this pass, there's no fail-open/
  fail-closed axis that applies here — the question is whether to build the missing feature into
  the worker at all, which is a product call, not a reachability-handling one.

### BRIDGED (2026-08-08, remediation pass — genuinely coupled, and already wired correctly)

- **`src/nexus/`** (`_nexus_router`, prefix `/nexus`) — `src.nexus.hub.get_nexus()` (the
  in-process pub/sub singleton, not just the router) is called directly by `section7.py`,
  `cryptex/threat_detector.py`, and `research/section7.py`, so the mount is genuinely load-bearing
  and cannot simply be unmounted like the confirmed-separate-features cases above. But unlike
  `basement`/`cryptex`/`billing` below, the coupling to its worker is **not open** — it's already
  built, correctly, with exactly the semantics this doc's other bullets ask for:
  `NexusHub.publish()` calls `_forward_to_ws_hub()`, which fires a capped-concurrency
  (`NEXUS_WS_FORWARD_CONCURRENCY`, default 10), fire-and-forget `asyncio.create_task()` that POSTs
  to `{INFINITY_WS_URL}/broadcast` with a 2s timeout — never blocks `publish()`, never raises, logs
  and drops on failure. `workers/infinity-ws/worker.py` has a matching `POST /broadcast` route
  (fail-closed `X-Internal-Secret` auth, `require_internal_auth` — 503 if unset, 401 on mismatch)
  that delivers the message to that channel's WebSocket subscribers via the existing
  `ConnectionManager._broadcast_to_channel()`. Internal cross-module signaling fans out to external
  WS clients today; there is no remaining engineering gap. This was wrongly filed as
  `NEEDS_MODULARIZATION` in the original second-pass sweep — that pass apparently checked
  `workers/infinity-ws/worker.py` only for `/health` and the raw `/ws` handler and missed the
  `_router` (with its own auth dependency) mounted separately at the bottom of the file, and never
  read `hub.py` past the `publish`/`_fan_out` methods to see `_forward_to_ws_hub`. Caught while
  starting remediation on this backlog, verified by reading both sides end to end rather than
  trusting the prior write-up. `scripts/build_topology_map.py` classifies this as `bridged`
  (distinct from both `needs_modularization` and `confirmed_separate_features`) so the map shows it
  as resolved infrastructure, not an open question.

### BRIDGES_IMPLEMENTED (2026-08-08, remediation pass — owner decision: fail-open)

The owner's explicit direction, once shown the fail-open/fail-closed question for
basement/cryptex/billing (and library, once its access-control gap surfaced): **mark them all
fail-open for now**, then audit afterwards for hardening/adaptive opportunities (see the
`Post-implementation hardening audit` item this unblocks). All four bridges below share the same
shape: the worker being unreachable never blocks, delays, or fails the request/action that
triggered it — it only means that one write/check didn't also land durably/globally, and every one
of them logs that at `debug` level rather than raising.

- **`src/basement/`** — `src/basement/bridge.py` (new). `Observatory.record()` already called
  `get_basement().ingest_observatory_event(event)` in-process on SECURITY/CRITICAL/retention-
  tagged/legal-hold events; that stayed unchanged (still the fast, always-available path within
  this process's lifetime). Added alongside it: a fire-and-forget POST to
  `workers/basement/`'s `POST /archive` (its SQLite+FTS5-backed durable store), so those events
  survive a process restart — which the in-memory `Basement` singleton alone cannot do. Same
  capped-in-flight-concurrency, `asyncio.create_task()`, never-raises pattern as `src/nexus/hub.py`.
- **`src/cryptex/`** — `src/cryptex/bridge.py` (new). The actual gap here wasn't the *failure*
  semantics — `security/middleware.py`'s Cryptex scan was already wrapped in a catch-all
  `except Exception: pass  # never block on Cryptex failure`, i.e. already fail-open at the
  exception-handling level. The real gap: `Cryptex._blocked_ips` is a plain Python `set()`, private
  to whichever single backend process handled the request that triggered the block — in a
  multi-process/multi-replica deployment, a block set by one process was invisible to every other
  one. Fixed with two mechanisms, both deliberately kept **off** the hot request path so no request
  latency depends on the worker: (1) a background loop (`start_background_sync()`, started at
  `api.py` startup) pulls `workers/cryptex/`'s `GET /intel?ioc_type=ip` list into the local
  `_blocked_ips` set every 30s — a failed pull just skips that cycle, never evicts what's already
  blocked locally; (2) `Cryptex.block_ip()` (and the auto-mitigation path in `_apply_mitigations()`,
  now routed through `block_ip()` instead of writing the set directly, so it gets the same
  treatment) fire-and-forget POSTs the block to `workers/cryptex/`'s `POST /intel/ingest` so every
  other process picks it up on its next sync. `is_blocked()` itself was **not** changed to make a
  network call — it stays a pure in-memory lookup, so per-request latency is unaffected either way.
- **`src/monetisation/`** (billing) — `src/monetisation/bridge.py` (new). **Also corrects a wrong
  target from the earlier passes of this doc**: `workers/payments-service/` was never a
  rate-limiting stub waiting to be built out — reading its actual code (`Royal Bank of Arcadia` —
  accounts/ledger/transfers/deposits/AUM) shows it's a full double-entry banking ledger, a
  completely different concern from tier/rate-limit enforcement, and was never going to become one.
  The actual right target was already deployed and fully built: `workers/rate-limit-service/`
  (a token-bucket policy engine, `POST /check`, named policies via `POST /policies`). Bridge design:
  `ensure_tier_policies()` seeds one named policy per billing tier at startup (capacity = the
  tier's `req_per_hour`, refill_rate = that ÷ 3600 — continuous refill, smoother than the
  in-process fixed-window counter); `check_and_increment_durable()` tries the worker's `POST
  /check` first with a tight 0.5s timeout — a real `await`, not fire-and-forget, since the caller
  needs an actual allow/deny answer — and only on an exception/timeout falls through to the
  pre-existing, purely local `TierEnforcer.check_and_increment()`. A reachable worker returning 429
  is honored as a real "no" (that's the worker doing its job, not a failure); only
  unreachability/errors trigger the fail-open fallback. Both `api.py` call sites
  (`/chat`, `/chat/stream`) now `await check_and_increment_durable(...)` instead of calling the
  enforcer directly. Unlimited tiers (`req_per_hour == -1`, e.g. enterprise) skip the remote call
  entirely.
- **`src/library/`** — `src/library/bridge.py` (new), **write-path only, by design**. The
  access-control gap found in the earlier pass (`workers/library-service/` has no
  classification/author/retention concept) is real and unchanged — so this bridge never routes
  reads through the worker, and it only forwards articles at PUBLIC/INTERNAL/CONFIDENTIAL
  classification; RESTRICTED/TOP_SECRET content is never sent to the worker, full stop, regardless
  of reachability. `Library.create()` now also fire-and-forget POSTs forwardable articles to
  `workers/library-service/`'s `POST /library/documents` for durability. `src/library/routes.py`'s
  in-process `Library` singleton (with its `_can_read()` classification gate) remains the sole
  authoritative read path for every classification level — nothing about reads changed.

All four register their own `URL`/`INTERNAL_SECRET` pair on `tranc3-backend`'s environment block in
`docker-compose.production.yml` (`BASEMENT_URL`/`BASEMENT_INTERNAL_SECRET`,
`CRYPTEX_URL`/`CRYPTEX_INTERNAL_SECRET`,
`RATE_LIMIT_SERVICE_URL`/`RATE_LIMIT_SERVICE_INTERNAL_SECRET`,
`LIBRARY_SERVICE_URL`/`LIBRARY_SERVICE_INTERNAL_SECRET`), each sourced from the same shared
`${INTERNAL_SECRET}` — the same pattern `INFINITY_WS_URL`/`INFINITY_WS_INTERNAL_SECRET` already
established for the nexus bridge.

**Hardening pass, same session, before merge.** The owner's follow-up ask after "mark them all
fail-open" was to then audit for hardening/adaptive opportunities rather than leave a bare
try/except. One gap stood out on inspection: every bridge above retried the worker on every single
call, with no memory of recent failures — for `monetisation`/billing specifically (by far the
highest-request-volume of the four, since it runs on `/chat` and `/chat/stream`), that means a
sustained `rate-limit-service` outage would cost every request the full request timeout before
falling back, for as long as the outage lasted. Fixed by giving each bridge its own
`src/mesh/circuit_breaker.py` `CircuitBreaker` instance (the platform's existing, already-available
primitive for exactly this — zero-cost, pure Python, no new dependency): after a run of consecutive
failures the breaker opens and the bridge stops even attempting the network call — straight to the
local fallback — until a reset timeout elapses, then it self-probes back to closed. Billing uses a
tightened 15s reset (default is 30s) since it gates live request latency and should recover fast;
the other three use the mesh default. This is additive hardening only — the fail-open contract
itself (worker down never blocks/delays/fails the triggering action) is unchanged; a request during
an open circuit now just skips the network attempt instead of waiting out a timeout to reach the
same fallback.

### CONFIRMED_SEPARATE_FEATURES (2026-08-08, follow-up pass — decided, not open questions)

Same "two sources of truth by name only" trap as Resonate/I-Mind, but resolved rather than left
open: each pair below has a gap to its same-named worker too large to call "the worker just needs
finishing" — an entire vector-DB stack, a different tech stack entirely, or a wholly different
subsystem, not a handful of missing endpoints. Three of the four (`search_api`, `admin_os`,
`section7`) also have **zero live in-process caller** on the monolith side, so there's genuinely no
risk to weigh either way. `townhall` is the exception: it does have a real in-process caller
(`research/section7.py`), but that call is already wrapped in try/except with graceful
degradation and involves no network hop — so it doesn't carry the fail-open/fail-closed question
that a genuine HTTP-bridge candidate (basement/cryptex/billing) would. In every case the only real
action was to stop treating a same-name coincidence as an unresolved duplicate question. All
routers/workers stay exactly as deployed today — revisit only if a real requirement emerges to
unify them. `scripts/build_topology_map.py` classifies these as `confirmed_separate_features`
(distinct from `needs_modularization`) so the topology map doesn't keep flagging them as pending.

- **`src/routers/search_api.py`** vs. **`workers/search-service/`** — the router is a hybrid
  BM25+vector RAG pipeline (Meilisearch/Qdrant/Weaviate/Chroma); the worker is SQLite FTS5
  full-text only, with no vector/embedding/RAG capability at all. Decided: `search_api` is the
  platform's RAG surface, `search-service` is a separate, simpler full-text search service.
- **`src/townhall/`** (`_townhall_router`) vs. **`workers/cranbania/`** — the router is a
  policy/compliance check engine (`GDPR`/`UK-GDPR`/`PRINCE2`/`ITIL4`/`Zero-Cost` policies,
  `governance.get_townhall().check(...)`); `workers/cranbania/` (the submodule, port 8071) is a
  Next.js/TypeScript Kanban/ITSM board with 40+ MCP tools and zero policy-check endpoints — not
  even the same language/runtime to bridge to, let alone the same feature. Real in-process caller:
  `research/section7.py`, already wrapped in `try/except` that logs and continues on
  `townhall unavailable` rather than failing the request — so, unlike basement/cryptex/billing
  below, there's no fail-open/fail-closed call to make here; it already degrades gracefully and
  always has. Decided: "Town Hall governance" and "CranBania" are permanently separate features
  sharing an entity table row, not a migration target. Building a compliance-check REST API into a
  Kanban board app would be the wrong direction to take this even if it were free.
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
