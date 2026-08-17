# Shared Functional Services Core (SFSC) — the `Dimensional` package

**Status:** Findings + remediation, 2026-08-17
**Scope:** what the shared core is, what actually reaches the services that need it,
and what should be promoted into it.

---

## 1. What a Dimensional is

A **Dimensional** is a Shared Functional Services Core (SFSC) capability: cross-cutting
code that many Locations need and none of them should own. It is **not** a tier in the
`PLATFORM_ENTITIES.md` hierarchy (Sovereign → Primes → Lead AI → Agents → Bots) and it is
not a Location. Locations are *who does the work*; Dimensionals are *what every worker
needs regardless of the work*.

The package is `Dimensional/` at the repo root — 101 Python modules across 17 subpackages:

| Subpackage | Role |
|---|---|
| `sanitize`, `log_sanitize` | log injection / PII redaction (`sanitize_for_log`, `SafeLogger`) |
| `path_validation`, `url_validation` | traversal and SSRF guards |
| `security`, `security_automation` | JWT/password primitives; the 6-layer scanner–remediator–telemetry framework |
| `error_handlers` | `SafeHTTPException`, `safe_error_detail` |
| `bus`, `models`, `registry` | EventBus, shared Pydantic models, ServiceRegistry |
| `cors`, `middleware` | request-boundary defaults |
| `infinity`, `nexus`, `hive`, `orchestration`, `architecture` | subsystem cores (auth nomenclature/RBAC/ABAC, sentinel bridges, storage factory, audit ledger) |
| `dimensionals` | the registry of Dimensionals themselves (`registry.py`, `service_bus.py`, `underverse.py`) |
| `cellular`, `gas`, `genetics`, `liquid`, `quantum`, `reservoir`, `swarm`, `pillars` | modelling primitives |

314 files across the repo import from `Dimensional.*`. Heaviest: `infinity` (161),
`sanitize` (128), `architecture` (73), `security_automation` (61), `path_validation` (56).

## 2. `shared_core/` is the old name — and the rename is incomplete

`shared_core/__init__.py` states: *"All functionality has moved to Dimensional. This module
re-exports everything so existing imports continue to work unchanged."*

67 of its 77 files are honest one-line shims. **Eight are not**, and six of those are stale
full copies of modules `Dimensional` has since moved on from:

| File | State |
|---|---|
| `architecture/audit_ledger.py` | diverged — `Dimensional` gained persistent HMAC signing keys; this copy still uses ephemeral keys |
| `architecture/storage_factory.py` | diverged (629 vs 643 lines) |
| `infinity/sentinel_station.py` | diverged (797 vs 817) |
| `security_automation/adaptive_scanner.py` | diverged (579 vs 601) |
| `security.py` | diverged (127 vs 121) |
| `middleware/rate_limiter.py` | diverged (201 vs 10) |
| `security_automation/rule_catalog.py` | **orphan** — no canonical counterpart, 184 lines |
| `security_automation/security_reporter.py` | **orphan** — no canonical counterpart, 378 lines |

All eight date from the same rename commit: the migration converted most files to shims and
left these behind. **Nothing imports any of the eight** (verified by reference count), and
`shared_core/security_automation/__init__.py` is itself a shim to a `Dimensional` package
that does not export the two orphans — so they are unreachable even by package import.

The live surface is small: only 8 files outside `shared_core/` import it at all, and they
pull `sanitize`, `infinity.nomenclature`, and `infinity.worker_integration` — all genuine
shims that resolve to `Dimensional`.

**Decision needed:** convert the six diverged copies to shims (they are dead, so this is
safe), and either move the two orphans into `Dimensional.security_automation` and export
them, or delete them. Leaving them is the worst option — a future caller reaching for
`shared_core.architecture.audit_ledger` gets the weaker signing behaviour, silently, from a
module whose own package docstring promises it is a re-export.

## 3. The reachability problem — the real finding

**74 of the 174 compose services build from their own directory** (`context: ./workers/<x>`).
Nothing at the repo root is in those images: not `src/`, not `Dimensional/`, not
`shared_core/`. A worker that does `from src.… import …` resolves fine locally (repo root is
on `sys.path`) and raises ImportError in the container.

Two legitimate routes exist, and both are in use:

1. **Guard it** — `try: … except Exception: pass`. The worker degrades. 27 workers do this.
2. **Vendor it** — copy the modules into the build context and `COPY` them in the
   Dockerfile. `hive-service` and `dimensional-nexus-service` do this; every substantive
   vendored file is currently byte-identical to its canonical source.

### 3.1 Seven workers were doing neither (fixed)

`infinity-void`, `mlflow-service`, `queue-service`, `search-service`, `triposr-worker`,
`turings-hub-service`, `vault-service` each imported `src.observability.worker_setup`
**unguarded, inside `lifespan()`**. The ImportError escapes the startup context manager, so
those seven containers **fail to start** — optional telemetry taking down the service it was
meant to observe. All seven now use the guarded pattern the other 27 use.

### 3.2 Telemetry is off in every own-context worker

The guard is the correct fix for startup, but it does not make the import succeed. 34
own-context workers import `src.observability.worker_setup`; none of them vendor it and no
requirements file packages it. So `instrument_worker()` — Prometheus route metrics, OTel
tracing, `/metrics` — **never runs in any of them**.

`CLAUDE.md`'s Observability Stack section claims "W3C TraceContext propagation across all
workers". That holds for the 14 root-context services and is false for the other 74. The
tracing code is real; it is on the wrong side of the build boundary.

**This is the clearest SFSC promotion candidate on the platform:** `src/observability/`'s
worker-facing surface is cross-cutting, needed by ~34 services, and currently reaches none
of them. Moving `worker_setup` (and the tracing/health helpers it pulls) to
`Dimensional/observability/` and vendoring or packaging `Dimensional` into worker images
turns platform-wide telemetry from documented to actual.

### 3.3 The circuit breaker sits in the same trap

`TASD-001` consolidated four `CircuitBreaker` implementations onto a shared core at
`src/resilience/` (Phases 1–2 merged). §3.1 of that ADR chose `src/resilience/` over a
"`shared_core`-style home", noting the variant but not the build boundary. The consequence
showed up immediately: `workers/chaos-party/observatory_bridge.py` needed a breaker, could
not import `src.mesh.circuit_breaker`, and duplicated one locally — a **fifth**
implementation, created *after* the consolidation that was meant to stop exactly that.

`Dimensional/` is the boundary-correct home for `circuit_state.py` and `circuit_core.py`.
Recommend amending TASD-001 §3.1 accordingly before Phase 3 migrates consumers onto a home
that a third of the estate cannot import.

## 4. Enforcement added

`scripts/check_worker_build_context.py` (wired into `.github/workflows/ci.yml` as the
Service Topology job, alongside `check_service_urls.py`) fails the build on:

- an unguarded import of `src` / `Dimensional` / `shared_core` from an own-context worker;
- a vendored file that has drifted from its canonical source (the Dockerfiles promise
  "keep in sync"; nothing was checking).

A vendored `__init__.py` that has been deliberately emptied passes — a worker vendoring only
`Dimensional.hive` cannot execute the real package `__init__`.

Current state: 42 cross-boundary imports and 10 vendored files across 74 services,
0 errors.

## 5. Orphaned worker directories

Three `workers/` directories have real code and a Dockerfile but **no compose service builds
them**:

| Directory | Port claimed | Likely overlap |
|---|---|---|
| `dimensional-nexus-service` | 8050 (listed as deployed in `CLAUDE.md`) | `nexus-ws-rs` (:8004, Rust) |
| `gateway-service` | 8040 | `api-gateway` (root context) |
| `optional-services-health` | 8094 | `health-aggregator` (:8029) |

Each needs a keep-or-delete decision of the kind the #56/#57 duplication sweep applied
elsewhere. `CLAUDE.md`'s worker map lists `dimensional-nexus-service` as a deployed P3
service, which is not true today.

## 6. Promotion shortlist — what else should become a Dimensional

Ranked by (services affected) × (currently broken or duplicated):

1. **`observability.worker_setup` + tracing/health helpers** — 34 services, telemetry
   currently dead in all of them. §3.2.
2. **Circuit breaker (`circuit_state`, `circuit_core`)** — 5 implementations; the
   consolidation home is unreachable from workers. §3.3.
3. **`src/errors/error_catalog.py`** — already vendored by `hive-service` because workers
   need canonical error codes. Vendoring one copy is a workaround; a second worker needing
   it makes it a Dimensional.
4. **Internal-secret / service-auth header handling** — every worker re-implements the
   `X-Internal-Secret` check inline.

Items 1–2 are the ones with evidence of active harm. 3–4 are pattern duplication without a
current outage and can follow.
