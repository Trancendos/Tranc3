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
| POST | `/cryptex/block/{ip}` | `Cryptex.block_ip()` — adds IP to an in-memory blocklist set |
| DELETE | `/cryptex/block/{ip}` | `Cryptex.unblock_ip()` |
| POST | `/cryptex/bounty/scan` | Triggers `bounty_hunter.run_full_scan()` as a FastAPI `BackgroundTask` |
| GET | `/cryptex/bounty/candidates` | `bounty_hunter.get_bounty_candidates()` |
| GET | `/cryptex/bounty/summary` | `bounty_hunter.get_summary()` |

### Threat detection (`threat_detector.py`) — real, but opt-in only
- `Cryptex.analyse()` runs a fixed list of `ThreatRule`s (registered in `_register_default_rules()`)
  against a caller-supplied context dict, emits a `ThreatSignal` per match, and applies
  mitigations (adds IP/actor to an in-memory blocklist if the rule's mitigation includes `BLOCK`).
- **`is_blocked()` is never consulted by anything outside this module.** No middleware in `api.py`
  calls `Cryptex.is_blocked()` before routing a request — blocking an IP via
  `POST /cryptex/block/{ip}` (or via a rule's `BLOCK` mitigation) has **zero effect on real
  platform traffic**. It only updates an in-memory set that `GET /cryptex/stats` and
  `is_blocked()`'s own return value in `/cryptex/analyse/request`'s response expose — nothing
  enforces it. Threat "detection" only happens when a caller explicitly POSTs a context to
  `/analyse` or `/analyse/request`; Cryptex does not passively inspect platform traffic.
- No auth on `/cryptex/block/{ip}`, `/cryptex/analyse*`, or `/cryptex/bounty/scan` — any caller
  can flood the unbounded `_signals` list (no cap, unlike The Basement's `MAX_RECORDS`), or (see
  below) trigger a scan against an arbitrary caller-chosen target.

### Bug bounty / CVE scanning (`bounty_hunter.py`) — real subprocess execution
- `run_nuclei_scan()` shells out to the `nuclei` CLI (list-form `subprocess`, **not** `shell=True`
  — no shell-injection vector) plus a `pip-audit` dependency scan; findings persisted to SQLite.
- `POST /cryptex/bounty/scan?target=<url>` accepts a **caller-supplied, unauthenticated** `target`
  parameter that is passed straight to the nuclei scan. There is no allowlist restricting which
  hosts can be scanned. This means an unauthenticated caller can direct the platform's own
  scanning infrastructure at an arbitrary third-party target — a real scan-abuse/SSRF-adjacent
  risk, not fixed in this pass (would require adding auth and/or a target allowlist, an
  architectural/policy decision out of scope for a docs pass). Flagged here rather than silently
  accepted.

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
| Wiring `is_blocked()` into real request middleware (future) | C | **A** | **R** | I |
| Bounty/CVE scan target authorization (future) | C | **A** | **R** | C |
| Wiring the 6 orphaned modules into a live path (future) | **R** | A | **R** | I |

## 5. Solutions Integration Model (SIM)

- **Upstream:** any caller of `/cryptex/*` — no auth on any route.
- **Downstream:** best-effort Observatory `observe()` call on signal emission (pattern consistent
  with other entities in this series, not individually re-verified here).
- **Not integrated:** `is_blocked()` is not consulted by any request-handling code path; the 6
  orphaned modules are not integrated with anything.

## 6. Architecture Scalability Document (ASD)

- **Load model:** in-memory `_signals` list, no cap — unbounded growth under sustained
  `/analyse` calls, unlike The Basement's `MAX_RECORDS` pattern.
- **Bottleneck:** single-process, no persistence for threat signals; a restart loses all signal
  history and the in-memory blocklists (which, per the finding above, don't enforce anything
  regardless).
- **Zero-cost limits:** `nuclei` and `pip-audit` are free/OSS CLI tools; MISP/Wazuh (unwired) are
  self-hosted per `CLAUDE.md`'s Recommended Open Source Foundations table.
- **Degradation:** none needed for the wired paths beyond standard Observatory best-effort emission.

## 7. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Web framework | FastAPI `APIRouter` | mounted into the main `api.py` app |
| Threat detection | Python regex rules (`threat_detector.py`) | OSS, in-process, zero cost |
| Vulnerability scanning | `nuclei` CLI + `pip-audit` (`bounty_hunter.py`) | OSS, subprocess, zero cost |
| Finding storage | SQLite (`bounty_hunter.py` only) | zero infra cost |
| Threat intel (unwired) | MISP (`misp_connector.py`) | self-hosted, not live-wired |
| SIEM (unwired) | Wazuh (`wazuh_connector.py`) | self-hosted, not live-wired |

## 8. Policy (POL)

- No route-level auth on any `/cryptex/*` route — see SIM §5. This is a materially higher-risk
  gap for a security-mission entity than for most others in this series, given the unauthenticated
  arbitrary-target bounty-scan finding above.
- Zero-cost mandate: `nuclei`/`pip-audit` scanning must stay within `scripts/zero_cost_audit.py`'s
  gate.

## 9. Procedure (PROC)

- **Analyse content for threats:** `POST /cryptex/analyse` with `{"context": {...}, "actor":
  "..."}` — returns matched signals; does not block anything automatically in a way that affects
  real traffic (see DDD).
- **Trigger a bounty scan:** `POST /cryptex/bounty/scan?target=<url>` — runs in the background;
  no auth, no target allowlist currently enforced.
- **Wire an orphaned module into the live path:** import it from `threat_detector.py` or add a
  new route in `routes.py` — no orphaned module currently has any caller in this repo.

## 10. Runbook (RUN)

- **Blocking an IP via `/cryptex/block/{ip}` doesn't actually stop its traffic:** expected —
  `is_blocked()` is never consulted by any middleware; this is a real, documented gap, not a bug
  to troubleshoot as if enforcement were intended to already work.
- **`POST /cryptex/bounty/scan` was called against an unexpected target:** expected given no
  auth/allowlist exists — see POL §8; this is a genuine security gap, not a misconfiguration.
- **Signal history disappears after a restart:** expected — `_signals` is in-memory only.

## 11. Standards (STD)

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
