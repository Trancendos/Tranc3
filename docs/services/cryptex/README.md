# Service Doc-Pack — Cryptex

| Field | Value |
|---|---|
| **Entity** | Cryptex |
| **Lead AI** | Renik |
| **Status** | ✅ In repo (per `CLAUDE.md` service table) — Live tier |
| **Code** | `src/cryptex/*` (9 files, 2,806 lines); router registered in `api.py` (`app.include_router(_cryptex_router)`, line 797) — **plus a separate standalone worker**, `workers/cryptex/worker.py` (port 8053) not covered in detail by this pack |

> **Truthfulness:** claims cite `src/cryptex/threat_detector.py`, `bounty_hunter.py`, and
> `routes.py` directly, plus grep-verified import analysis of the other 6 files in `src/cryptex/`.
> Status is owned by the `CLAUDE.md` service table; identity by `PLATFORM_ENTITIES.md`.
> **Major finding: most of this module is orphaned, unreachable code.** Of the 9 files in
> `src/cryptex/` (2,806 lines total), only **2 are wired into the live `/cryptex/*` API surface**:
> `threat_detector.py` (351 lines — the core regex-rule engine, mounted via `routes.py`) and
> `bounty_hunter.py` (413 lines — a real nuclei/pip-audit scanner, also mounted via `routes.py`).
> The remaining **6 files — `misp_connector.py` (476 lines), `wazuh_connector.py` (517 lines),
> `cve_scanner.py` (249 lines), `genetic_rules.py` (260 lines), `graph_anomaly.py` (203 lines),
> and `ml_detector.py` (232 lines) — total ~1,940 lines (≈69% of the module) and are never
> imported by `routes.py`, `threat_detector.py`, `bounty_hunter.py`, or `api.py`.** `cve_scanner.py`
> is imported only by `tests/test_section7.py` (as "Section 7" — see `CLAUDE.md`'s naming note
> that "Section 7" maps to The Dutchy, not Cryptex — a further cross-entity naming ambiguity, not
> resolved in this pass). This is real, substantial code — not stubs — but it is dead weight from
> the live platform's perspective: none of it runs unless something outside this repo imports it
> directly, which nothing currently does.
> **Scope note:** the standalone `workers/cryptex/worker.py` (port 8053) is a separate
> implementation not audited in depth by this pack.

## 1. Service Governance Charter (GOV)

- **Mission:** cyber defense — real-time threat detection against incoming requests/context,
  IP/actor blocking, and CVE/bug-bounty scanning.
- **Owner (RACI-A):** Renik; Platform Owner Trancendos.
- **Scope (as actually wired):** regex-rule-based threat signal detection (`threat_detector.py`)
  and subprocess-based nuclei/pip-audit vulnerability scanning (`bounty_hunter.py`). MISP threat-
  intel integration, Wazuh SIEM integration, CVE scanning (beyond the bounty scanner), genetic
  rule evolution, graph-based anomaly detection, and ML-based detection all have real
  implementations in this directory but are **not reachable from any live code path** — see
  truthfulness header.

## 2. Detailed Design Document (DDD)

### HTTP surface (`src/cryptex/routes.py`, prefix `/cryptex`)

| Method | Route | Backing |
|---|---|---|
| GET | `/cryptex/stats` | `Cryptex.stats()` — signal counts by category/severity, blocked-IP/actor counts, active rule count |
| GET | `/cryptex/signals` | `Cryptex.recent_signals()` — `limit` 1–200, optional `min_severity` filter |
| POST | `/cryptex/analyse` | `Cryptex.analyse()` — runs all rules against an arbitrary caller-supplied context dict |
| POST | `/cryptex/analyse/request` | `Cryptex.analyse_request()` — analyses the calling HTTP request itself (path/body/headers/IP) |
| POST | `/cryptex/block/{ip}` | `Cryptex.block_ip()` — adds IP to an in-memory blocklist set; admin-only |
| DELETE | `/cryptex/block/{ip}` | `Cryptex.unblock_ip()`; admin-only |
| POST | `/cryptex/bounty/scan` | Triggers `bounty_hunter.run_full_scan()` (fixed server-side target, no caller override) as a FastAPI `BackgroundTask`; admin-only |
| GET | `/cryptex/bounty/candidates` | `bounty_hunter.get_bounty_candidates()`; admin-only |
| GET | `/cryptex/bounty/summary` | `bounty_hunter.get_summary()`; admin-only |

### Threat detection (`threat_detector.py`) — real, but opt-in only
- `Cryptex.analyse()` runs a fixed list of `ThreatRule`s (registered in `_register_default_rules()`)
  against a caller-supplied context dict, emits a `ThreatSignal` per match, and applies
  mitigations (adds IP/actor to an in-memory blocklist if the rule's mitigation includes `BLOCK`).
- **Correction to a prior claim in this pack: `is_blocked()` IS consulted by request-handling
  middleware.** `src/security/middleware.py`'s `RBACMiddleware` (wired via
  `app.add_middleware(RBACMiddleware)` in `api.py`) calls `cx.is_blocked(ip=ip)` on every
  POST/PUT/PATCH to a non-exempt path and returns `403` if blocked — verified by direct code read.
  Blocking an IP via `POST /cryptex/block/{ip}` (now admin-gated, see below) does have a real
  enforcement effect on platform traffic.
- `/cryptex/block/{ip}`, `/cryptex/bounty/*` now require `Depends(get_current_user)` plus an
  admin-role check (`current_user.get("role") == "admin"`) — see DDD below. `/cryptex/analyse*`
  remain unauthenticated by design (they analyse caller-supplied or the calling request's own
  context; there is no meaningful "ownership" to check, and the unbounded `_signals` list flood
  risk from repeated calls is a separate, unaddressed rate-limiting concern).

### Bug bounty / CVE scanning (`bounty_hunter.py`) — real subprocess execution
- `run_nuclei_scan()` shells out to the `nuclei` CLI (list-form `subprocess`, **not** `shell=True`
  — no shell-injection vector) plus a `pip-audit` dependency scan; findings persisted to SQLite.
- **Fixed:** `POST /cryptex/bounty/scan` no longer accepts a caller-supplied `target` at all — the
  route now calls `run_full_scan()` with no argument, so the scan always targets the server-side
  `BOUNTY_TARGET_URL` default, consistent with the module's own "own infrastructure only, never
  scan third parties" header comment. The route also now requires admin auth (see DDD above).

### Orphaned modules — real code, zero live wiring
The following exist as complete, non-trivial implementations but are imported by nothing in the
live application (verified via `grep -rl` against `src/`, `api.py`, and `workers/`):
- `misp_connector.py` (476 lines) — MISP threat-intel integration.
- `wazuh_connector.py` (517 lines) — Wazuh SIEM integration.
- `cve_scanner.py` (249 lines) — CVE scanning, distinct from `bounty_hunter.py`'s scan path;
  imported only by `tests/test_section7.py`.
- `genetic_rules.py` (260 lines) — rule evolution.
- `graph_anomaly.py` (203 lines) — graph-based anomaly detection.
- `ml_detector.py` (232 lines) — ML-based detection.

## 3. Technical Architecture Solutions Design (TASD)

- **Style:** in-process module with a module-level singleton (`get_cryptex()`); in-memory storage
  only (`_signals`, `_blocked_ips`, `_blocked_actors`), no persistence for the threat-detection
  path. `bounty_hunter.py` uses SQLite for finding persistence.
- **Decision: opt-in analysis, not passive interception.** Cryptex does not sit in the request
  pipeline as middleware — every `/cryptex/*` caller must explicitly submit content for analysis.
  This is a real architectural gap relative to the entity's "cyber defense" mission if the intent
  was platform-wide automatic protection; documented as-is, not assumed to be intentional or not.
- **Not evaluated in this pass:** the correctness/quality of the 6 orphaned modules' internal
  logic — since none of it executes in the live app, auditing their internals wasn't prioritized
  over documenting their orphaned status accurately.

## 4. RACI Matrix

| Activity | Renik (Lead) | Platform Owner | Platform Engineering | The Observatory |
|---|---|---|---|---|
| Threat rule / detection logic changes | **R** | A | C | I |
| Wiring the 6 orphaned modules into a live path (future) | **R** | A | **R** | I |

## 5. Solutions Integration Model (SIM)

- **Upstream:** `/cryptex/analyse*` and `/cryptex/stats`/`signals` remain unauthenticated by
  design (see DDD). `/cryptex/block/{ip}` and `/cryptex/bounty/*` now require
  `Depends(get_current_user)` plus an admin-role check.
- **Downstream:** best-effort Observatory `observe()` call on signal emission (pattern consistent
  with other entities in this series, not individually re-verified here). `RBACMiddleware`
  genuinely consults `is_blocked()` on every POST/PUT/PATCH to a non-exempt path.
- **Not integrated:** the 6 orphaned modules are not integrated with anything.

## 6. Architecture Scalability Document (ASD)

- **Load model:** in-memory `_signals` list, no cap — unbounded growth under sustained
  `/analyse` calls, unlike The Basement's `MAX_RECORDS` pattern.
- **Bottleneck:** single-process, no persistence for threat signals; a restart loses all signal
  history and the in-memory blocklist, which `RBACMiddleware` genuinely consults for enforcement
  (see DDD) — a restart silently drops active blocks.
- **Zero-cost limits:** `nuclei` and `pip-audit` are free/OSS CLI tools; MISP/Wazuh (unwired) are
  self-hosted per `CLAUDE.md`'s Recommended Open Source Foundations table.
- **Degradation:** none needed for the wired paths beyond standard Observatory best-effort emission.

## 7. Deployment Scope Matrix (DSM)

- **Mode awareness:** No — this entity's own code does not call `PlatformInfraMode` / `src/platform/infrastructure_mode.py`. (Some platform-wide, cross-cutting code *does* branch on the mode — `src/routers/adaptive.py` and `src/routers/ecosystem.py` read/set `PLATFORM_INFRA_MODE`/`SYSTEM_MODE` directly, and `Dimensional/architecture/storage_factory.py` selects a storage provider from `SYSTEM_MODE` — but none of that code is owned by this or any other one of the 43 named entities; it is shared platform infrastructure, not this service's own logic. The Citadel is the only one of the 43 named entities whose own code branches on the mode — see `docs/services/the-citadel/README.md`.) This entity's deployment scope is determined externally — by which `docker-compose.production.yml` service block runs, and where — not by in-process mode detection.
- **Runtime placement:** standalone worker with its own `docker-compose.production.yml` service block (`cryptex`, port 8053) and its own Traefik route — does not run inside the `tranc3-backend` monolith
- **Persistence:** named volume attached to the `cryptex` compose service — state survives container restarts/redeploys in any mode
- **Note:** this entity has **two** deployment surfaces — a router mounted in the `tranc3-backend` monolith (`api.py`) *and* a separate standalone worker (`cryptex`, port 8053). The table below describes the standalone worker; the monolith-mounted router follows the monolith's own placement (see the monolith pattern noted across this platform's other entities) and shares its volume.

| Setup | What runs, and where | Data locality | Hard blockers / caveats |
|---|---|---|---|
| **Cloud-Only** | the `cryptex` compose block runs on a single cloud host; Traefik/edge in front | persists via its attached volume as long as the volume/disk is preserved on that host | none beyond standard single-host durability (no built-in cross-host replication) |
| **Hybrid** | same `cryptex` compose block; per `docs/architecture/infrastructure-modes.md`'s Hybrid diagram, this worker itself still runs as a single instance (cloud or local host), with only shared persistent data (not specific to this worker) split via TrueNAS/Syncthing | as above, optionally local-synced if a volume exists | requires `CITADEL_LOCAL_STACK=true` if a local compose stack should run alongside the cloud one |
| **Local-Only** | same `cryptex` compose block, run entirely on local/Citadel hardware behind local Traefik | fully local, volume-backed | none beyond standard local-hardware ops |

- **Zero-cost posture per mode:** Cloud-Only defaults to the `zero_cost_cloud` AI-rotation chain; Hybrid/Local-Only default to `zero_cost_full` (`config/platform/infrastructure_mode.yaml`) — this only affects AI-Gateway-routed calls, not this entity's own logic
- **Switching modes:** operator-level via `PLATFORM_INFRA_MODE` (or legacy `SYSTEM_MODE`); this entity needs no code change to move between modes, only a redeploy-target change for its own compose block

## 8. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Web framework | FastAPI `APIRouter` | mounted into the main `api.py` app |
| Threat detection | Python regex rules (`threat_detector.py`) | OSS, in-process, zero cost |
| Vulnerability scanning | `nuclei` CLI + `pip-audit` (`bounty_hunter.py`) | OSS, subprocess, zero cost |
| Finding storage | SQLite (`bounty_hunter.py` only) | zero infra cost |
| Threat intel (unwired) | MISP (`misp_connector.py`) | self-hosted, not live-wired |
| SIEM (unwired) | Wazuh (`wazuh_connector.py`) | self-hosted, not live-wired |

## 9. Environment Support Matrix (ESM)

> Grounded against `docker-compose.development.yml` (6 services), `docker-compose.uat.yml` (16 services), and `docker-compose.production.yml` (286 services) — checked by exact compose service name, not assumed.

| Environment | Covered? | What runs | Notes |
|---|---|---|---|
| **Dev** | Partial | the `api` service in `docker-compose.development.yml` runs the monolith router — the standalone `cryptex` worker is **not** in this compose file | standalone worker has zero Dev coverage |
| **UAT** | Partial | same monolith router via `api` in `docker-compose.uat.yml` — the standalone `cryptex` worker is **not** in this compose file either | standalone worker has zero UAT coverage |
| **Production** | Yes | both surfaces — full detail in the DSM above | — |

- **Gap:** the standalone `cryptex` worker (the more complete of this entity's two surfaces, per the DSM above) has **no Dev or UAT environment at all** — the first place it runs is Production. This is the norm for the ~90 standalone workers on this platform, not specific to this entity, but worth stating plainly rather than assuming pre-production validation exists where it doesn't.

## 10. Policy (POL)

- `POST /cryptex/block/{ip}`, `DELETE /cryptex/block/{ip}`, and every `/cryptex/bounty/*` route
  require admin auth — see DDD/SIM. `/cryptex/analyse*` remain intentionally unauthenticated.
- Zero-cost mandate: `nuclei`/`pip-audit` scanning must stay within `scripts/zero_cost_audit.py`'s
  gate.

## 11. Procedure (PROC)

- **Analyse content for threats:** `POST /cryptex/analyse` with `{"context": {...}, "actor":
  "..."}` — returns matched signals; a `BLOCK` mitigation genuinely affects future traffic via
  `RBACMiddleware`'s `is_blocked()` check (see DDD).
- **Trigger a bounty scan:** `POST /cryptex/bounty/scan` (as an admin) — runs in the background
  against the fixed `BOUNTY_TARGET_URL`; no caller-supplied target is accepted.
- **Wire an orphaned module into the live path:** import it from `threat_detector.py` or add a
  new route in `routes.py` — no orphaned module currently has any caller in this repo.

## 12. Runbook (RUN)

- **Blocking an IP via `/cryptex/block/{ip}` doesn't stop its traffic:** check whether the
  request path is in `RBACMiddleware._SCAN_SKIP` or `ENVIRONMENT=test` is set — both bypass the
  `is_blocked()` check by design; otherwise this would be a real bug, not expected behavior.
- **A non-admin caller gets `403` on `/cryptex/block/{ip}` or `/cryptex/bounty/*`:** expected —
  see POL §9.
- **Signal history disappears after a restart:** expected — `_signals` is in-memory only.

## 13. Standards (STD)

- Naming: canonical entity name "Cryptex" per `CLAUDE.md`/`PLATFORM_ENTITIES.md`. Note
  `cve_scanner.py` is imported by a test file named `test_section7.py` — "Section 7" is a
  documented internal placeholder name (`CLAUDE.md`) mapped to The Dutchy, not Cryptex; this
  cross-reference is flagged as a naming ambiguity, not resolved in this pass.
- Any module added to `src/cryptex/` MUST be imported from a live code path (route, rule
  registration, or scheduled task) before being described as "implemented" in future doc-pack
  updates — the 6-orphaned-module finding here is the reason for this standard.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-05 | Claude (session) | `src/cryptex/threat_detector.py` (351 lines), `bounty_hunter.py` (413 lines), `routes.py` (105 lines), `api.py` router registration (line 797), plus grep-verified import analysis of the remaining 6 files in `src/cryptex/` (2,806 lines total across all 9 files) | Confirmed Live-tier, full pack authored. Major finding: ~69% of this module's code (6 of 9 files) is never imported by any live code path — real, substantial implementations (MISP, Wazuh, CVE scanning, genetic rules, graph anomaly detection, ML detection) that simply don't run. Also flagged, not fixed: `is_blocked()` is never consulted by request-handling middleware (blocking has no real enforcement effect), and the unauthenticated bounty-scan endpoint accepts an arbitrary caller-supplied target with no allowlist. |
| 2026-07-08 | Claude (session) | `src/cryptex/routes.py` (post-fix), `src/security/middleware.py` | Two fixes plus one correction. **Corrected a factual error in this pack:** `is_blocked()` IS consulted — `RBACMiddleware` (wired via `app.add_middleware(RBACMiddleware)` in `api.py`) calls `cx.is_blocked(ip=ip)` on every POST/PUT/PATCH to a non-exempt path, returning `403` if blocked; the prior claim that blocking had "zero effect on real platform traffic" was wrong. **Fixed:** `POST`/`DELETE /cryptex/block/{ip}` and every `/cryptex/bounty/*` route now require `Depends(get_current_user)` plus an admin-role check; `POST /cryptex/bounty/scan` no longer accepts any caller-supplied `target` — it always scans the fixed `BOUNTY_TARGET_URL`, closing the scan-abuse/SSRF-adjacent gap. Verified via `tests/test_cryptex_auth.py`. `/cryptex/analyse*` remain intentionally unauthenticated (no meaningful ownership to check). The 6-orphaned-module finding is unrelated and remains open. |
