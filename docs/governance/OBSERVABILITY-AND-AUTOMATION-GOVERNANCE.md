# Observability and Automation Governance

> **What this is.** An honest accounting of what proactive/automated monitoring already exists on
> this platform, what's now been built to give it somewhere structured to write to, and what
> "trend detection, foresight, probability factors, predictive analytics" would actually require
> beyond that — not a claim that predictive analytics exists today. It doesn't. This document says
> exactly what's real.

**Code:** `src/observability/proactive_health.py` (`ProactiveHealthMonitor`), `self_healer.py`
(`SelfHealer`), `src/errors/error_catalog.py` (`ErrorCode`), `src/event_bus/`, `src/cmdb/`
(`models.py`, `loader.py`, `health_sync.py`), `scripts/build_cmdb.py`,
`scripts/sync_health_aggregator.py`.
**Owner:** The Observatory (Norman Hawkins) · **Version:** 1.1.0 · **Created:** 2026-07-18 ·
**Updated:** 2026-07-18 (health-aggregator sync built)

---

## 1. What already exists (same pattern as RBAC/ABAC and the zero-cost registry: built, barely wired)

- **`ProactiveHealthMonitor`** (`src/observability/proactive_health.py`) already implements rolling
  EWMA health scoring, SWOT threat escalation, **3-sample predictive degradation detection**, and a
  SQLite-backed alert history. This is real trend-detection infrastructure. It is wired into `api.py`
  only — no standalone worker feeds it a health sample.
- **`SelfHealer`** (`self_healer.py`) exists alongside it — not audited in this pass.
- **`ErrorCode`/`ErrorDefinition`** (`src/errors/error_catalog.py`, 538 lines) is a real, structured
  error-code catalogue — the "error handling and error code management" asked about already exists
  as a design; whether every service actually raises through it (vs. ad-hoc `HTTPException`) was not
  checked in this pass.
- **Vulnerability/dependency management** already has five dedicated CI workflows:
  `.forgejo/workflows/security-scan.yml`, `dependency-audit.yml`, `dependency-scanner.yml`,
  `proactive-security.yml`, `security-baseline.yml`. Not individually reviewed in this pass — flagged
  as already-existing rather than re-built.
- **`src/event_bus/`** (pattern-based routing, SQLite persistence) is real infrastructure for
  service-to-service event flow — a natural transport for the "live traffic, data, knowledge"
  capture the request describes, not yet wired to the CMDB below.

## 2. What was built this session: a real relational domain model

`docs/architecture/ea-workbook/*.csv` (19 files) is now also loadable into `data/cmdb.db`, a real
SQLite database with actual foreign keys — `src/cmdb/models.py` (`Service`, `Application`,
`Deployment`, `CostReview`, `AccessControlReview`, all FK-linked) and `src/cmdb/loader.py`. Rebuild
with `python scripts/build_cmdb.py` after the CSVs change — same "CSVs are the source of truth,
this is a derived artifact" convention as `Trancendos_Master_Service_Matrix.xlsx`. `data/cmdb.db`
is gitignored (`*.db`), not committed.

This turns things that previously needed grep + manual cross-referencing (e.g. "which
Confidential-classified services have no auth mechanism," found by hand while writing
`ACCESS-CONTROL-GOVERNANCE.md`) into one real SQL join — verified in `tests/test_cmdb.py`, including
a regression test that the join still finds the known `infinity-shards-service` gap.

A sixth table, **`HealthObservation`**, is also defined — `service_id`, `observed_at`,
`health_score`, `status`, `error_count`, `response_time_ms`, `source`. It is **empty**. Nothing
writes to it yet. It exists because "capture live traffic/health data so trend detection has
something to detect trends in" needs a destination before it needs an algorithm, and this is that
destination, modelled on `ProactiveHealthMonitor`'s own `HealthSample` shape so wiring it in later
is a straight mapping, not a redesign.

## 2b. Built this pass: the health-aggregator → `HealthObservation` sync

`src/cmdb/health_sync.py` reads `health-aggregator`'s own SQLite DB (`health_checks` table —
`id, service, port, url, status, latency_ms, checked_at, error`, schema confirmed by reading
`workers/health-aggregator/worker.py` directly) and writes one `HealthObservation` row per check
into `data/cmdb.db`, mapped to a real `ServiceID`.

**The mapping problem and how it was solved.** health-aggregator identifies services by compose
service name (`"infinity-portal"`); CMDB identifies them by `ServiceID` (`"SRV-PORTAL-001"`) — no
shared key exists in either dataset. Two name-based approaches were tried and rejected before
landing on a port join:

1. Fuzzy name-matching — rejected earlier this session: it produced two confirmed wrong matches
   (`blender-worker`, `tranc3-ai`) where an unrelated row's Notes text happened to *mention* the
   name in a cross-reference (e.g. a port-conflict note), not because it was that service.
2. Joining on `health_checks.service` against a static copy of health-aggregator's registry names —
   rejected on PR review (#223): health-aggregator also accepts *dynamic* registrations via
   `POST /services` (`scripts/register_ea_workbook_services.py`), which register under the CSV's
   `ServiceName` (e.g. `"MCP Server"`), not the compose name. Those rows would never match a static
   name list, and worse, `since_id` would still advance past them, making them unrecoverable
   without manually rewinding the marker file.

The join actually used: **port number**, read directly from `health_checks.port` — which
health-aggregator populates for both static *and* dynamic targets (`_dynamic_poll_targets()`
derives a real port from the registered URL). Every CMDB `Service.notes` field that documents a
verified port states it as the first `port NNNN` mention (later mentions in the same field are
cross-references to *other* services). Verified by hand against the 7 services in this session's
audit that had multiple port mentions in their Notes — first-mention was correct in all 7. The
static `HEALTH_AGGREGATOR_REGISTRY` name list is kept only as a coverage cross-check and a drift
regression test, not as the sync's actual join key: **all 42 of its entries resolve to a
ServiceID, 0 ambiguous, 0 unmapped.**

**Two real producer-side bugs found and fixed during PR review**, both in
`workers/health-aggregator/worker.py`, pre-dating this sync and previously silent because nothing
read the affected columns:
- `_persist_check()` read `result.get("latency_ms")` and `result.get("error")`, but `_check_one()`
  actually returns `"response_ms"` (top-level) and puts a failure message under
  `"details"."error"` — so `health_checks.latency_ms` and `.error` were always `NULL` for every
  real poll. Fixed to read the correct keys.
- The consumer side (`_STATUS_TO_SCORE` in `health_sync.py`) had invented a status vocabulary
  (`healthy`/`degraded`/`unhealthy`/`unreachable`/`timeout`/`error`/`unknown`) that didn't match
  what `_check_one()` actually writes (`healthy`/`degraded`/`down`). Every failed probe would have
  synced with `status="down"` unmapped to any score. Fixed to the real 3-value vocabulary, with
  `unknown` kept only as a defensive fallback for a future/unrecognised value.

`scripts/sync_health_aggregator.py` is the runnable entry point — reads `health-aggregator`'s DB
(default `/data/health_aggregator.db`, matching its own `DB_PATH` default) and `data/cmdb.db`,
writes new `HealthObservation` rows incrementally (tracks the last-synced `health_checks.id` in a
marker file next to the CMDB db, so repeat runs only pick up new rows). Not a daemon — intended to
run on a schedule (cron, ChronosSphere) once deployed. Each write is deduplicated against an
existing `(service_id, observed_at, source)` row, so re-running after a crash between the CMDB
commit and the marker-file update doesn't insert duplicates — this does not extend to genuinely
concurrent runs from multiple processes, which the script is documented as not supporting.

**What is and isn't proven here.** `tests/test_cmdb_health_sync.py` (9 tests, all passing) proves
the join and write logic are correct against a synthetic SQLite DB built with health-aggregator's
exact schema, including a real known-good case (`infinity-ws` → `SRV-WS-001` via port 8004), a
dynamic-registration case (a row named `"MCP Server"` still resolving via its port), a
crash-recovery/dedupe case, and a registry-drift regression test. It does **not** prove this has
run against a live production
`health_aggregator.db` — no such file exists in this sandbox. That is real, live verification still
outstanding, not done.

## 3. What this does NOT do yet — named explicitly, not glossed over

- **No live data has actually flowed into `HealthObservation` yet** — the sync exists and is tested
  against synthetic data (§2b), but has not been run against a real, running `health-aggregator`
  instance. That's the next concrete unblocking step, not a redesign.
- **No trend detection runs against this data**, because there is no live data yet. `ProactiveHealthMonitor`
  already has a 3-sample predictive-degradation algorithm — once `HealthObservation` has real rows,
  wiring that algorithm to read from SQL instead of its own in-memory state is the concrete next
  step, not a new algorithm to invent.
- **"Foresight, probability factors, predictive analytics"** — none of this exists today in any
  form beyond `ProactiveHealthMonitor`'s EWMA/3-sample trend logic. A real probability-based
  forecast (e.g. "this service has an N% chance of degrading in the next hour") needs weeks of
  real observation history before it means anything — claiming otherwise here would be exactly the
  kind of overclaim this platform's own governance docs have repeatedly corrected themselves out of
  (see `COST-AND-REVENUE-GOVERNANCE.md`, `ACCESS-CONTROL-GOVERNANCE.md`'s self-corrections).
- **No automated remediation ("implement fixes to services in a positive manner") exists** beyond
  `SelfHealer`, which wasn't audited this pass. Automated fixes to production services are also a
  materially higher-risk category than documentation or dead-code fixes — any such automation needs
  explicit scope, approval gates, and rollback design before being built, not just wiring.

## 4. Proposed next steps, in order

1. ~~Wire `health-aggregator` (or a new adapter) to write one `HealthObservation` row per check~~ —
   **built and unit-tested this pass** (§2b). Still needed: deploy `scripts/sync_health_aggregator.py`
   on a real schedule against a live `health-aggregator` instance and confirm rows actually land.
2. Once real observations accumulate (days, not minutes), point `ProactiveHealthMonitor`'s existing
   EWMA/trend logic at that table instead of its own per-process memory, so the trend detection that
   already exists gets real, cross-restart data to work with.
3. Only after (1) and (2) have run for long enough to have real signal: revisit whether genuine
   predictive/probability modelling is warranted, and what human review gate any automated action
   based on it should have — this is a product decision, not a technical one, and not this
   document's to make unilaterally.
4. Audit `SelfHealer` and the five security-scan workflows individually with the same
   code-verification rigor applied elsewhere this session, rather than assuming they work because
   they exist.

## 5. Open items

- `HealthObservation` has zero rows in any real deployment — the sync logic is built and tested
  against synthetic data, but has not been run against a live `health_aggregator.db`. That's the
  actual remaining unblocking work.
- `ErrorCode` usage coverage across the 92 services was not audited — unknown how many services
  actually raise through the catalogue vs. ad-hoc error handling.
- The five security-scan CI workflows were not individually reviewed for correctness this pass.
- `src/cmdb/models.py`'s `DependsOnServices`/`DependsOnInfrastructure` columns stay semicolon-
  separated text rather than a real many-to-many association table, because the underlying CSV data
  mixes service IDs and free-text infrastructure names inconsistently — cleaning that up is a
  prerequisite for a real dependency graph, not something to paper over with a fragile parser.
