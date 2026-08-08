# Monolith Extraction Findings — 2026-08-08 systematic sweep

**Status:** 7 confirmed-safe removals shipped in this pass. An 8th (`src/resonate/`) was reverted
after review — see below. 7 candidates now need a deliberate design decision (HTTP bridge, or
leave in-process on purpose), not a mechanical fix. Nothing below was silently resolved.
`scripts/check_duplicate_routers.py` (wired into `production-gate.yml` in both `.github/workflows/`
and `.forgejo/workflows/`) now guards against this pattern recurring — see its module docstring for
what it does and, importantly, does not do (it cannot verify HTTP-route equivalence, only flag
routers that look like the pattern for a human/agent to investigate).

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
- **`src/imind/`** — `workers/imind/` (542 lines, in compose) exists, but `src/tranquility/wellbeing.py`
  imports `src.imind.protocol` directly at the class level (not just the router) for
  in-process logic. The *router* mount could still be removed safely (only `api.py` imports the
  router object) — Tranquility's own dependency is on the underlying module, not the HTTP layer —
  but flagging this one for a second pass rather than bundling it into the batch above, since it's
  the one candidate where "safe to unmount" and "safe to eventually delete the file" diverge and
  that distinction is easy to lose track of later.
- **`src/cryptex/`** — real in-process callers: `section7/information_router.py`,
  `mcp/server.py`, `security/middleware.py`. `workers/cryptex/` (1078 lines, in compose) exists.
  Security-tooling code with multiple live callers — needs the same careful HTTP-bridge treatment
  as Basement, not a mechanical unmount.
- **`src/library/`** — real in-process callers: `section7/information_router.py`,
  `observability/library_pipeline.py`, `models/knowledge.py`, `event_bus/wiring.py`.
  `workers/library-service/` (936 lines, in compose) exists. Four separate in-process
  dependents — the widest fan-in of anything checked in this pass.
- **`src/routers/search_api.py`** — real in-process caller: nothing else found calling the
  underlying search logic directly by name, but the router itself needs re-checking against
  `workers/search-service/` (392 lines, in compose) for behavioral equivalence before any removal
  — not done in this pass.
- **`src/personality/turingshub/`** — deep in-process fan-in across the core AI response pipeline
  (`src/dependencies.py`, `src/workers/inference_worker.py`, `src/routers/enhanced_capabilities.py`,
  plus several top-level scripts). This one reads as intentionally core/load-bearing, not a stray
  duplicate — did not investigate further, flagging only so it isn't mistaken for an oversight.

## Not checked in this pass

`src/nexus/`, `src/observability/` (Observatory itself), `src/townhall/`, `src/admin_os/`,
`src/section7/`, `src/apimarket/`, `src/roles/`, `src/deployment_modes/`, `src/notebooks/`,
`src/relations/`, `src/access/`, `src/citadel/`, `src/bio_neural/` (Luminous), `src/quantum/`
(Think Tank), and the `enhanced_capabilities`/`ecosystem`/`aeonmind`/`t2ance`/`trance_one`/
`tranc3ts_bridge`/`monetisation`/`models` routers at the bottom of `api.py`. Some of these
(`apimarket`, `lab` — done) had zero external in-process callers when spot-checked earlier in this
sweep; most were not checked at all. Given the pattern found here, several are worth the same
grep-and-verify treatment as a follow-up — this doc doesn't claim the sweep is complete.
