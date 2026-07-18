# Observability and Automation Governance

> **What this is.** An honest accounting of what proactive/automated monitoring already exists on
> this platform, what's now been built to give it somewhere structured to write to, and what
> "trend detection, foresight, probability factors, predictive analytics" would actually require
> beyond that — not a claim that predictive analytics exists today. It doesn't. This document says
> exactly what's real.

**Code:** `src/observability/proactive_health.py` (`ProactiveHealthMonitor`), `self_healer.py`
(`SelfHealer`), `src/errors/error_catalog.py` (`ErrorCode`), `src/event_bus/`, `src/cmdb/` (new —
`models.py`, `loader.py`, `service_docpack_map.py`), `scripts/build_cmdb.py`,
`scripts/link_service_docpacks.py`.
**Owner:** The Observatory (Norman Hawkins) · **Version:** 1.1.0 · **Created:** 2026-07-18 ·
**Updated:** 2026-07-18 (ServiceDocPack table + sample_from_cmdb added, still no live data)

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

A seventh table, **`ServiceDocPack`**, links the 43 per-service governance doc-packs under
`docs/services/*/README.md` (each containing numbered DDD/TASD/RACI/GOV sections per
`docs/framework/SERVICE-DOC-PACK-TEMPLATE.md`) to real CMDB `ServiceID`s. Only 34 of the 43 have an
unambiguous match — see `src/cmdb/service_docpack_map.py`'s `UNMAPPED_DOCPACKS` for the other 9 and
why each was left out rather than guessed (ambiguous owner shared across multiple CMDB rows, or no
matching row at all). `scripts/link_service_docpacks.py` inserted a `ServiceID (CMDB)` field into
each of the 34 matched READMEs so the cross-reference is visible in the doc itself, not just in the
database. Records which governance sections are actually present per doc-pack (`has_ddd`,
`has_tasd`, `has_raci`, `has_gov`) so "which services have a RACI matrix on file" is a SQL query, not
a 43-file grep.

## 3. What this does NOT do yet — named explicitly, not glossed over

- **No live data flows into `HealthObservation`.** Nothing polls the 92 services and writes health
  samples. `health-aggregator` (port 8029) already polls services for health — the natural next step
  is having it (or a new thin adapter) write into this table, not building a second poller.
- **No trend detection runs against this data**, because there is no data yet. `ProactiveHealthMonitor`
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

1. Wire `health-aggregator` (or a new adapter) to write one `HealthObservation` row per check into
   `data/cmdb.db` (or a shared Postgres instance if this needs to survive container restarts at
   scale — SQLite is fine for now, matching the zero-cost architecture). **Not done on this branch**
   — tracked separately (PR #223, blocked on an external CI check as of this writing).
2. Once real observations accumulate (days, not minutes), point `ProactiveHealthMonitor`'s existing
   EWMA/trend logic at that table instead of its own per-process memory, so the trend detection that
   already exists gets real, cross-restart data to work with. **The code-level capability now
   exists**: `ProactiveHealthMonitor.sample_from_cmdb(cmdb_db_path)` replays `HealthObservation` rows
   through the *same* `_update_ewma`/`_detect_trend`/`_raise_alert` machinery `check_all()` uses for
   live entities, keyed by `service_id`. Unit-tested against synthetic data
   (`tests/test_proactive_health_cmdb.py` — empty table, missing db, steady-healthy,
   declining-to-critical, multi-service isolation, `NULL`-score exclusion). This does **not** mean
   trend detection is live — `HealthObservation` still has zero rows in any real deployment (step 1
   is still the actual blocker), so calling this against a real `data/cmdb.db` today correctly
   returns no alerts, not a false trend.
3. Only after (1) and (2) have run for long enough to have real signal: revisit whether genuine
   predictive/probability modelling is warranted, and what human review gate any automated action
   based on it should have — this is a product decision, not a technical one, and not this
   document's to make unilaterally.
4. Audit `SelfHealer` and the five security-scan workflows individually with the same
   code-verification rigor applied elsewhere this session, rather than assuming they work because
   they exist.

## 5. Open items

- `HealthObservation` has zero rows — step 1 above is the actual unblocking work.
- `ServiceDocPack` covers 34 of 43 doc-packs — the other 9 need a human to resolve the ambiguity
  documented in `service_docpack_map.UNMAPPED_DOCPACKS` (either the CMDB needs a new Service row, or
  an existing ambiguous Owner match needs a human tie-breaker) rather than an automated guess.
- `ErrorCode` usage coverage across the 92 services was not audited — unknown how many services
  actually raise through the catalogue vs. ad-hoc error handling.
- The five security-scan CI workflows were not individually reviewed for correctness this pass.
- `src/cmdb/models.py`'s `DependsOnServices`/`DependsOnInfrastructure` columns stay semicolon-
  separated text rather than a real many-to-many association table, because the underlying CSV data
  mixes service IDs and free-text infrastructure names inconsistently — cleaning that up is a
  prerequisite for a real dependency graph, not something to paper over with a fragile parser.
