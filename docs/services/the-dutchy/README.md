# Service Doc-Pack — The Dutchy

| Field | Value |
|---|---|
| **Entity** | The Dutchy |
| **Lead AI** | Predictive lore |
| **Status** | ✅ In repo (per `CLAUDE.md` service table) — Live tier |
| **Code** | `src/research/section7.py`, `src/research/routes.py`; router registered in `api.py` (`app.include_router(_section7_router)`, line 804) — **plus a separate standalone worker**, `workers/the-dutchy/worker.py` (port unverified in this pass) |

> **Truthfulness:** claims cite `src/research/section7.py`, `src/research/routes.py`,
> `src/research/bci_interface.py`, and `api.py`'s startup wiring directly. Status is owned by the
> `CLAUDE.md` service table; identity by `PLATFORM_ENTITIES.md`.
> **Naming collision (real, not a typo):** there are **two entirely unrelated things named
> "Section 7" in this codebase.** (1) `src/research/section7.py`'s `Section7` class — mounted at
> `/section7/*` via `src/research/routes.py`, `app.include_router(_section7_router)` — is **The
> Dutchy's** actual HTTP surface, per `CLAUDE.md`'s own naming note ("Section 7 — internal
> placeholder name, NOT in the canonical entity hierarchy; closest entity is The Dutchy"). (2) A
> completely separate `src/section7/` **package** (6 files: `threat_intel_loop.py`,
> `cve_ingester.py`, `information_router.py`, `intelligence_agent.py`, `scheduler.py`,
> `web_scraper.py`) implements a real, live-wired CVE/OSV/CISA threat-intelligence polling loop —
> `start_threat_intel_loop()` is called from `api.py` at startup (line ~521) and runs every
> `THREAT_INTEL_INTERVAL_SECS` (default 3600s), emitting `security.cve.*` events to the Event Bus.
> This package is **not** part of The Dutchy's code path documented below and is **not** audited
> in depth by this pack — it happens to share the "Section 7" name coincidentally (or by design
> confusion) with an unrelated live background service. Flagged here as a genuine, previously
> undocumented naming/scope hazard for anyone searching the codebase for "section7".

## 1. Service Governance Charter (GOV)

- **Mission:** intelligence & market analysis — aggregates live cross-platform signals
  (Observatory, The Town Hall, Cryptex, The Basement, The Nexus) into structured reports, and
  auto-publishes findings to The Library as KB articles.
- **Owner (RACI-A):** Predictive lore; Platform Owner Trancendos.
- **Scope:** `src/research/section7.py`'s `Section7` class — report generation and storage only.
  `bci_interface.py` (brain-computer-interface signal processing) is a co-located, self-declared
  stub in the same `src/research/` directory but is not part of The Dutchy's HTTP surface and not
  imported by `api.py` or `routes.py` — see DDD.

## 2. Detailed Design Document (DDD)

### HTTP surface (`src/research/routes.py`, prefix `/section7`)

| Method | Route | Backing |
|---|---|---|
| GET | `/section7/stats` | `Section7.stats()` — total reports, by-type counts |
| GET | `/section7/reports` | `Section7.recent()` — `limit` 1–50, optional `report_type` filter |
| GET | `/section7/reports/{id}` | `Section7.get()` — 404 `JSONResponse` if missing |
| POST | `/section7/reports/platform-health` | `Section7.generate_platform_health_report()` — pulls live stats from 5 other entities |
| POST | `/section7/reports/security` | `Section7.generate_security_report()` — pulls Cryptex + Observatory security data |

### Report generation — genuinely cross-platform, not a stub
This is one of the more substantively wired entities audited in this series:
- `generate_platform_health_report()` makes **real, live calls** to `get_observatory().stats()`,
  `get_townhall().status()`, `get_cryptex().stats()`, `get_basement().stats()`, and
  `get_nexus().status()` — each wrapped independently in `try/except`, so a single unavailable
  dependency doesn't fail the whole report; it's simply omitted from `data_sources`.
  Auto-generates `recommendations` from thresholds (e.g. CRITICAL Observatory events, Town Hall
  compliance score below 90%, HIGH/CRITICAL Cryptex signals).
- `generate_security_report()` pulls `Cryptex.recent_signals()` (MEDIUM+ severity) and
  Observatory's `SECURITY`-category events.
- `_store_and_publish()` — called after every report generation — **genuinely calls
  `Library.create()`** (`src/library/knowledge_base.py`), confirming the module header's claim
  "Feeds findings into The Library as KB articles" is real, not aspirational (unlike similar
  claims found unimplemented in other entities' code comments during this series — see The
  Library's own doc-pack for a counter-example). Also emits an Observatory `AUDIT`-category event.
  **Fixed this pass:** the `Library.create()` failure path was a bare `except Exception: pass`
  with a comment claiming "error logged upstream" that didn't actually log anything — publish
  failures were silently invisible. Fixed by adding a `logger.warning(..., exc_info=True)` call so
  failures are now diagnosable. The Observatory-emission `except` block is unchanged (a secondary,
  lower-priority telemetry path).

### `bci_interface.py` — self-declared stub, not wired
- Module header: "Stub with real interface — swap implementation when hardware available." Not
  imported by `routes.py` or `api.py` — only referenced by `src/registry/file_registry.py` (a
  file listing, not functional wiring). Honestly labeled as a stub in its own source comment, so
  this is not a discrepancy to flag as a defect — just noted for completeness.

## 3. Technical Architecture Solutions Design (TASD)

- **Style:** in-process module with a module-level singleton (`get_section7()`); in-memory
  `_reports` dict, no persistence, no external DB.
- **Decision: best-effort cross-entity aggregation.** Each data source is fetched in its own
  `try/except`, so partial platform outages degrade the report (fewer `data_sources`) rather than
  failing it outright — the same graceful-degradation philosophy used elsewhere in this codebase.
- **Not evaluated in this pass:** the separate `src/section7/` threat-intel-loop package (see
  naming-collision note above) — real and live-wired, but out of The Dutchy's scope as documented
  here; would need its own audit if a future pass wants to document it (likely under whichever
  entity, if any, is meant to own CVE/OSV/CISA ingestion — not resolved in this pass).

## 4. RACI Matrix

| Activity | Predictive lore (Lead) | Platform Owner | The Library | Platform Engineering |
|---|---|---|---|---|
| Report generation logic changes | **R** | A | I | C |
| Library auto-publish wiring | C | A | **R** | C |
| `src/section7/` threat-intel package (separate, unowned by this pack) | ? | ? | I | ? |

## 5. Solutions Integration Model (SIM)

- **Upstream:** any caller of `/section7/*` routes — no auth on any route in
  `src/research/routes.py`.
- **Downstream:** genuinely calls into The Observatory, The Town Hall, Cryptex, The Basement, The
  Nexus (read-only stats calls), and The Library (write, via `Library.create()`) — the most
  cross-entity-integrated module audited in this doc-pack series so far.
- **Not integrated:** `bci_interface.py` is not wired to any route or caller.

## 6. Architecture Scalability Document (ASD)

- **Load model:** in-memory `_reports` dict, no cap defined — unbounded growth, no eviction.
- **Bottleneck:** single-process, no persistence; a restart loses all report history (though
  reports already published to The Library persist there only as long as Library's own
  in-memory store survives — see The Library's doc-pack for its own restart-loss caveat).
- **Zero-cost limits:** no external dependency beyond the in-process calls to other platform
  modules.
- **Degradation:** each cross-entity fetch degrades independently on failure (see TASD).

## 7. Deployment Scope Matrix (DSM)

- **Mode awareness:** No — this entity's own code does not call `PlatformInfraMode` / `src/platform/infrastructure_mode.py`. (Some platform-wide, cross-cutting code *does* branch on the mode — `src/routers/adaptive.py` and `src/routers/ecosystem.py` read/set `PLATFORM_INFRA_MODE`/`SYSTEM_MODE` directly, and `Dimensional/architecture/storage_factory.py` selects a storage provider from `SYSTEM_MODE` — but none of that code is owned by this or any other one of the 43 named entities; it is shared platform infrastructure, not this service's own logic. The Citadel is the only one of the 43 named entities whose own code branches on the mode — see `docs/services/the-citadel/README.md`.) This entity's deployment scope is determined externally — by which `docker-compose.production.yml` service block runs, and where — not by in-process mode detection.
- **Runtime placement:** standalone worker with its own `docker-compose.production.yml` service block (`the-dutchy`, port 8057) and its own Traefik route — does not run inside the `tranc3-backend` monolith. **This worker's Dockerfile previously only `COPY`'d a placeholder `main.py`** (the same deployed-stub-vs-undeployed-real defect found for The Academy/The Basement/The Studio) — **fixed**: it now builds and runs the real, more complete SQLite-backed `worker.py`, with a named volume (`the-dutchy-data:/app/data`) added so its data survives redeploys.
- **Persistence:** named volume now attached to the `the-dutchy` compose service (added alongside the worker.py fix above) — state survives container restarts/redeploys in any mode
- **Note:** this entity has **two** deployment surfaces — a router mounted in the `tranc3-backend` monolith (`api.py`) *and* a separate standalone worker (`the-dutchy`, port 8057). The table below describes the standalone worker; the monolith-mounted router follows the monolith's own placement (see the monolith pattern noted across this platform's other entities) and shares its volume.

| Setup | What runs, and where | Data locality | Hard blockers / caveats |
|---|---|---|---|
| **Cloud-Only** | the `the-dutchy` compose block runs on a single cloud host, now running the real `worker.py`; Traefik/edge in front | persists via its attached volume as long as the disk is preserved on that host | none beyond standard single-host durability (no built-in cross-host replication) |
| **Hybrid** | same `the-dutchy` compose block; per `docs/architecture/infrastructure-modes.md`'s Hybrid diagram, this worker itself still runs as a single instance (cloud or local host), with only shared persistent data (not specific to this worker) split via TrueNAS/Syncthing | as above, optionally local-synced if a volume exists | requires `CITADEL_LOCAL_STACK=true` if a local compose stack should run alongside the cloud one |
| **Local-Only** | same `the-dutchy` compose block, run entirely on local/Citadel hardware behind local Traefik | fully local, volume-backed | none beyond standard local-hardware ops |

- **Zero-cost posture per mode:** Cloud-Only defaults to the `zero_cost_cloud` AI-rotation chain; Hybrid/Local-Only default to `zero_cost_full` (`config/platform/infrastructure_mode.yaml`) — this only affects AI-Gateway-routed calls, not this entity's own logic
- **Switching modes:** operator-level via `PLATFORM_INFRA_MODE` (or legacy `SYSTEM_MODE`); this entity needs no code change to move between modes, only a redeploy-target change for its own compose block

## 8. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Web framework | FastAPI `APIRouter` | mounted into the main `api.py` app |
| Report storage | in-memory `dict`, no persistence | zero infra cost, no durability |
| Cross-entity aggregation | direct in-process function calls | zero cost, tightly coupled to the entities called |

## 9. Policy (POL)

- No route-level auth on `/section7/*` routes — see SIM §5.
- Zero-cost mandate: no external dependency in this module to audit against
  `scripts/zero_cost_audit.py`.

## 10. Procedure (PROC)

- **Generate a platform health report:** `POST /section7/reports/platform-health` — pulls live
  stats from 5 platform entities, auto-publishes to The Library, returns the report.
- **Generate a security report:** `POST /section7/reports/security` — pulls Cryptex + Observatory
  security data.
- **List/inspect reports:** `GET /section7/reports` (optional `report_type` filter), `GET
  /section7/reports/{id}` for full detail.

## 11. Runbook (RUN)

- **A generated report is missing a data source:** expected if that entity was unreachable at
  generation time — check the omitted entity's own health, not this module (see TASD's
  graceful-degradation design).
- **Report not appearing in The Library:** `_store_and_publish()`'s `Library.create()` call is
  wrapped in a bare `except Exception: pass` — check The Library's own health/logs, not this
  module, per the same pattern used platform-wide.
- **Confusing "section7" search results:** remember the naming collision — `src/research/
  section7.py` (this entity, The Dutchy) is unrelated to the `src/section7/` threat-intel package
  (a separate, unaudited-by-this-pack live background loop) — see truthfulness header.

## 12. Standards (STD)

- Naming: canonical entity name "The Dutchy" per `CLAUDE.md`/`PLATFORM_ENTITIES.md`; "Section 7"
  is documented in `CLAUDE.md` as an internal placeholder mapping to this entity — but a
  **second, unrelated** `src/section7/` package also exists in this repo (see truthfulness
  header). Future work referencing "Section 7" in code, docs, or commit messages MUST disambiguate
  which of the two is meant.
- Any future doc-pack authored for the `src/section7/` threat-intel-loop package MUST NOT reuse
  or extend this pack — it is a distinct piece of code with no shared ownership established here.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-05 | Claude (session) | `src/research/section7.py` (285 lines), `src/research/routes.py` (53 lines), `src/research/bci_interface.py` (132 lines), `api.py` router registration (line 804) and startup wiring (line ~521), `src/section7/` package (6 files) | Confirmed Live-tier, full pack authored for the `src/research/*` path (the standalone `workers/the-dutchy/worker.py` was explicitly out of scope for this pass — see Code row above — so "full pack" should be read as scoped to the audited path, not entity-wide). Verified genuine cross-entity integration: `generate_platform_health_report()`/`generate_security_report()` make real calls into 5 other live entities, and `_store_and_publish()` genuinely writes to The Library (confirmed via `Library.create()` call), unlike similar "feeds into X" claims found unimplemented elsewhere in this series. Major finding: a completely separate, unrelated `src/section7/` package (CVE/OSV/CISA threat-intel polling, live-wired via `api.py` startup) shares the "Section 7" name with this entity's actual code path — a genuine naming collision, not previously documented, flagged for future disambiguation. |
| 2026-07-07 | Claude (session, cubic/CodeRabbit review triage) | `src/research/section7.py` | Fixed the bare `except Exception: pass` around `Library.create()` in `_store_and_publish()` — its comment claimed "error logged upstream" but nothing actually logged the failure, making publish errors invisible. Added `logger.warning(..., exc_info=True)`. Verified via `py_compile`/`ruff check` (both clean); no existing test covers this path to re-run. |
| 2026-07-11 | Claude (session, DSM/implementation pass) | `workers/the-dutchy/Dockerfile`, `workers/the-dutchy/main.py`, `workers/the-dutchy/worker.py` | Found, while authoring the Deployment Scope Matrix, that `workers/the-dutchy/` has the same deployed-stub-vs-undeployed-real defect previously found for The Academy/The Basement/The Studio: the Dockerfile only `COPY`'d a placeholder `main.py` (zero storage, hardcoded empty/placeholder responses) while a genuinely more complete SQLite-backed `worker.py` sat unused in the same directory. **Fixed this time** (unlike Academy's prior pass, this was caught and corrected in the same session rather than left for a follow-up): changed the Dockerfile to build/run `worker.py` and added a named volume (`the-dutchy-data:/app/data`) to `docker-compose.production.yml`. DSM rewritten to reflect the fix. Note this is independent of the `src/research/section7.py` monolith-router finding above (intelligence report generation) — two separate surfaces, two separate fixes. |
