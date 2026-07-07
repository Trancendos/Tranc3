# Service Doc-Pack — The Warp Tunnel

| Field | Value |
|---|---|
| **Entity** | The Warp Tunnel |
| **Lead AI** | Rocking Ricki |
| **Status** | ✅ In repo (per `CLAUDE.md` service table) — Live tier |
| **Code** | `workers/warp-tunnel/main.py` (54 lines, honest stub) — the deployed implementation for this compose service. `worker.py` (334 lines, real regex-pattern file scanner with `X-Internal-Secret` auth) exists but is not built into this Dockerfile. A **third**, independent implementation, `src/security/warp_tunnel/tunnel.py` (163 lines, real Ice-Box-integrated content scanner), is genuinely wired up — but into a *different* compose service, `workers/ice-box-service/worker.py`, not into `workers/warp-tunnel/`. |

> **Truthfulness:** claims cite `workers/warp-tunnel/main.py`, `worker.py`,
> `src/security/warp_tunnel/tunnel.py`, `Dockerfile`, and `docker-compose.production.yml`
> directly. Status is owned by the `CLAUDE.md` service table; identity by `PLATFORM_ENTITIES.md`.
> **Three independent implementations of "scanning" exist for this one entity — a new pattern
> in this doc-pack series (previous entities had at most two).** (1) `workers/warp-tunnel/main.py`
> — the **deployed** file — is an honest stub: `POST /scan` always returns
> `{"scanned": false, "threat": null, "message": "Scanner not yet initialised."}`. (2)
> `workers/warp-tunnel/worker.py` (334 lines, **not deployed** — the Dockerfile only copies
> `main.py`) is a genuine, working file-upload scanner: real regex-pattern threat detection
> (`_scan_content()`, matching against `THREAT_PATTERNS` including PE-executable/PHP-webshell/
> EICAR-test signatures), SQLite-backed scan history, an actual quarantine directory for
> flagged files, and real `X-Internal-Secret` auth (same insecure `"dev-secret"` fallback
> default already flagged for The Academy/Sashas Photo Studio/TateKing). (3)
> `src/security/warp_tunnel/tunnel.py` (163 lines, a `WarpTunnel` class, not a FastAPI file at
> all) is a **third**, entirely independent implementation — genuine integration with The Ice
> Box's `ThreatAnalyser`/`QuarantineStore` for scanning arbitrary text/content (not file uploads)
> before it reaches downstream services, with configurable block/warn verdict thresholds.
>
> **Correction (2026-07-07, same day, caught while auditing The Ice Box):** an earlier version
> of this pack claimed `WarpTunnel`/`warp_tunnel` has "zero callers anywhere in the
> repository" and is "fully orphaned." That was **wrong** — the grep behind that claim only
> searched `src/` and `api.py`, and missed `workers/`. `workers/ice-box-service/worker.py`
> (a *separate* compose service, port 8046, entity "The Ice Box") directly imports and
> instantiates `WarpTunnel`/`TunnelConfig` from this exact module and calls `_tunnel.scan()` on
> every `POST /scan` request. `tunnel.py` is real, live, wired code — it is simply deployed
> under a *different* entity's worker (The Ice Box), not under `workers/warp-tunnel/` itself.
> The "orphaned" framing has been removed below; see `docs/services/the-ice-box/README.md` for
> the consuming side.
> **Also found and fixed this pass, the same defect class found repeatedly across this doc-pack
> series:** `workers/warp-tunnel/Dockerfile` hardcoded `EXPOSE 8056` / `HEALTHCHECK ...
> localhost:8056`, and `main.py`'s own `PORT` default also fell back to `8056`, while
> `docker-compose.production.yml` sets `PORT: "8072"` and routes Traefik to container port
> 8072. Not a live defect (`main.py` is invoked via bare `python main.py`, correctly reads
> `PORT` at runtime, and compose's own healthcheck overrides the Dockerfile's) but fixed for
> robustness, consistent with recent practice. Compose's Traefik rule was also bare
> ``PathPrefix(`/warp-tunnel`)`` with **no `StripPrefix` middleware**, while `main.py`'s routes
> are unprefixed — the same genuinely live routing defect already found and fixed for 5 other
> entities earlier in this series; fixed with a `strip-warp-tunnel` middleware.

## 1. Service Governance Charter (GOV)

- **Mission:** cryptographic scanner & quarantine transport for data moving between trust
  zones. **As deployed**, this mission is not live (the deployed `main.py` is an honest stub);
  two separate, real implementations of scanning logic exist (`worker.py` for file uploads,
  `src/security/warp_tunnel/tunnel.py` for text content) but neither is wired into the live
  request path.
- **Owner (RACI-A):** Platform Owner Trancendos.
- **Lead AI:** Rocking Ricki.
- **Scope:** `workers/warp-tunnel/main.py` (deployed) + `worker.py` (real, undeployed) +
  `src/security/warp_tunnel/tunnel.py` (real, orphaned) — all three documented in this pack
  given the unusual three-implementation finding.

## 2. Detailed Design Document (DDD)

### HTTP surface, deployed (`main.py`, no route prefix)

| Method | Route | Backing |
|---|---|---|
| GET | `/health` | static uptime — not a real dependency probe |
| GET | `/status` | static `"status": "initialising"` — honestly reflects the stub state |
| POST | `/scan` | **honest stub** — always returns `{"scanned": false, "threat": null, "message": "Scanner not yet initialised."}`, HTTP 202 |
| GET | `/quarantine` | **honest stub** — always returns `{"quarantined": [], "total": 0, "message": "Quarantine store empty."}` |

### HTTP surface, real-but-undeployed (`worker.py`, own `_router`)

| Method | Route | Backing |
|---|---|---|
| GET | `/health` | static |
| GET | `/metrics` | Prometheus-format counters |
| POST | `/scan` | **real** file-upload scan — SHA-256 hash, regex-pattern threat matching, quarantines matched files to disk, persists to SQLite; internal-secret authed |
| POST | `/scan/hash` | hash-only lookup variant; internal-secret authed |
| GET | `/scans` / `/scans/{id}` | scan history; internal-secret authed |
| DELETE | `/quarantine/{scan_id}` | releases/deletes a quarantined file; internal-secret authed |
| GET | `/stats` | internal-secret authed |

### `_scan_content()` — real, working pattern-based scanner
- Matches uploaded content against `THREAT_PATTERNS` (regex signatures) — confirmed patterns
  include PE-executable, PHP-webshell, and EICAR-test-string detection. Returns `"critical"`,
  `"suspicious"`, or `"clean"`. Files scored `critical`/`suspicious` are written to a real
  `QUARANTINE_DIR` on disk and logged. This is genuine, working logic — not a scaffold.

### `WarpTunnel` class (`src/security/warp_tunnel/tunnel.py`) — real, third implementation, wired into a different entity's worker
- `WarpTunnel.scan(content, source=...)` calls The Ice Box's real `ThreatAnalyser` and
  `QuarantineStore` (per its own module docstring: "Intercepts inbound content before it enters
  the main execution path"), with configurable `block_verdicts`/`warn_verdicts`/
  `max_content_bytes`/`strict_mode` via `TunnelConfig`. This is real, well-structured
  integration code, and it **is genuinely called** — `workers/ice-box-service/worker.py`
  (compose service `ice-box-service`, port 8046) imports `TunnelConfig, WarpTunnel` and
  instantiates `_tunnel = WarpTunnel(...)` at module load, then calls `_tunnel.scan()` inside
  its `POST /scan` handler. It has **no caller within `workers/warp-tunnel/`** — the compose
  service documented in this pack — which is the accurate framing: this code lives in one
  entity's `src/` tree but is deployed exclusively via a different entity's worker.

## 3. Technical Architecture Solutions Design (TASD)

- **Style:** three fully independent implementations of the same conceptual capability, none
  of which call each other.
- **Fixed defects:** Dockerfile port mismatch (cosmetic, fixed for robustness) + Traefik
  `StripPrefix` missing (genuine, live routing defect) — see truthfulness header.
- **Not fixed, flagged as an opportunity:** neither real scanner (`worker.py`'s file scanner nor
  `tunnel.py`'s content scanner) is deployed/wired. Promoting either requires an owner decision
  on which scanning model (file-upload vs. inline-content-interception) actually matches the
  entity's intended role, plus fixing `worker.py`'s `dev-secret` fallback if it's the one chosen.

## 4. RACI Matrix

| Activity | Rocking Ricki (Lead) | Platform Owner | Platform Engineering |
|---|---|---|---|
| File-scan logic changes (`worker.py`) | **R** | A | C |
| Content-interception logic changes (`tunnel.py`) | **R** | A | C |
| Deciding which implementation (if any) to deploy (future) | C | **A** | **R** |

## 5. Solutions Integration Model (SIM)

- **Upstream (deployed `main.py`):** any caller of `/health`, `/status`, `/scan`,
  `/quarantine` — no auth, but both mutating-sounding routes are stubs that do nothing.
- **Upstream (undeployed `worker.py`, if promoted):** would require `X-Internal-Secret` once the
  `dev-secret` fallback is fixed.
- **Downstream (`tunnel.py` only, if wired):** The Ice Box's `ThreatAnalyser`/`QuarantineStore`
  — a real, self-hosted, zero-cost dependency already present in this repo.
- **Not integrated within this entity's own worker:** none of the three implementations call
  each other, and none of `worker.py`/`tunnel.py` is wired into `workers/warp-tunnel/`'s
  deployed `main.py`. `tunnel.py` does have a real caller — but it's The Ice Box's worker, a
  separate compose service — not anything under `workers/warp-tunnel/`.

## 6. Architecture Scalability Document (ASD)

- **Load model (deployed):** trivial — no state, no real work performed.
- **Load model (`worker.py`):** SQLite-backed scan history, quarantine files on local disk.
- **Zero-cost limits:** fully honored across all three — no paid dependencies anywhere.
- **Degradation:** N/A for the deployed stub; the other two implementations' failure-handling
  depth was not traced in this pass.

## 7. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Web framework (deployed) | FastAPI, standalone, honest stub | self-hosted, port 8072 (fixed this pass) |
| File scanning (undeployed) | Regex-pattern signature matching (`worker.py`) | zero-cost, in-process |
| Content interception (real, deployed — but via The Ice Box's worker, not this one) | Ice Box `ThreatAnalyser`/`QuarantineStore` integration (`tunnel.py`) | zero-cost, self-hosted |
| Auth | none in deployed `main.py`; `worker.py`'s unused alt has `X-Internal-Secret` with an insecure fallback | zero cost, currently unenforced |

## 8. Policy (POL)

- No route-level auth on the deployed `main.py` — low risk given both routes are stubs.
- **If `worker.py` is ever promoted to deployed status, its `dev-secret` fallback MUST be fixed
  first** — the same pattern already documented for The Academy, Sashas Photo Studio, TateKing,
  and Imaginarium.
- Zero-cost mandate: fully honored across all three implementations.

## 9. Procedure (PROC)

- **Check scan status (deployed):** `POST /scan` — always returns "not yet initialised", by
  honest design, not a bug.
- **(Not currently reachable) Scan a file for real:** would be `POST /scan` on `worker.py`, if
  promoted to deployed status.
- **Intercept inline content:** already live — via The Ice Box's `POST /scan` (port 8046, not
  this entity's own port 8072). `WarpTunnel` has no caller *within `workers/warp-tunnel/`
  itself*, but is not dormant platform-wide.

## 10. Runbook (RUN)

- **`/scan` always returns `"scanned": false`:** expected — this is the deployed file's honest,
  intentional stub behavior, not a bug to chase.
- **Every route 404s in production despite the container being healthy:** was the exact symptom
  of the pre-fix Traefik defect (``PathPrefix(`/warp-tunnel`)`` with no `StripPrefix`
  middleware, while `main.py`'s routes are unprefixed) — fixed this pass by adding a
  `strip-warp-tunnel` middleware to the compose labels; confirm it's still present if this
  recurs.
- **Someone asks "why isn't anything actually being scanned by *this* worker?":** `worker.py`
  (file scanning) is real but not deployed here; `tunnel.py` (content scanning) is real and
  **is** deployed — but via The Ice Box's worker (port 8046), not `workers/warp-tunnel/`
  (port 8072). See truthfulness header for the full finding and the owner decision on whether
  `workers/warp-tunnel/` should also get a real implementation, or whether The Ice Box's
  coverage is considered sufficient for this platform capability.

## 11. Standards (STD)

- Naming: canonical entity name "The Warp Tunnel" per `CLAUDE.md`/`PLATFORM_ENTITIES.md`.
- Config modules invoked via bare `python <file>.py` correctly read `PORT` from the environment
  at runtime; Dockerfile `EXPOSE`/embedded `HEALTHCHECK` mismatches against compose's routed
  port are cosmetic in that case (per `CLAUDE.md`'s §188 precedent) but SHOULD still be kept in
  sync for robustness — fixed here as a matter of consistency with recent practice.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-04 | Claude (session) | `CLAUDE.md` service table (status, Lead AI, Foundation), `PLATFORM_ENTITIES.md` (identity), initial repo search | **SUPERSEDED — was wrong.** Initial search incorrectly concluded no implementation exists. |
| 2026-07-04 | Claude (session), corrected after cubic PR review | actual repo contents (`src/*`, `workers/*/worker.py` — see correction blockquote above) | **Correction: code DOES exist.** `CLAUDE.md`'s Planned label is stale. Pack remains charter-only as an interim, honestly-flagged gap pending a real Partial/Live-tier rewrite — not a valid Planned-tier no-code determination. |
| 2026-07-07 | Claude (session) | `workers/warp-tunnel/main.py` (54 lines), `worker.py` (334 lines), `src/security/warp_tunnel/tunnel.py` (163 lines), `Dockerfile`, `docker-compose.production.yml`, repo-wide `grep` for `WarpTunnel`/`warp_tunnel` usage | Confirmed Live-tier, full pack authored. Major finding: **three** independent implementations exist for this entity — an honest stub (deployed `main.py`), a real regex-pattern file scanner (`worker.py`, undeployed), and a real Ice-Box-integrated content scanner (`tunnel.py`) initially believed to be fully orphaned. Not fixed (requires an owner decision on which scanning model to deploy) but flagged clearly. Also fixed the same two defect classes found repeatedly this session: a cosmetic Dockerfile port mismatch (8056 vs compose's 8072, fixed for robustness) and a genuine, live Traefik `PathPrefix`-without-`StripPrefix` routing bug (the sixth instance this session), fixed with a `strip-warp-tunnel` middleware. `scripts/port_registry_validate.py` re-run and passes (73 workers). |
| 2026-07-07 (same day, correction) | Claude (session), while auditing The Ice Box | `workers/ice-box-service/worker.py` (225 lines) | **Corrected a factual error in this pack.** The prior entry's "fully orphaned, zero callers anywhere" claim for `WarpTunnel`/`tunnel.py` was wrong — the grep behind it only checked `src/` and `api.py`, missing `workers/`. `workers/ice-box-service/worker.py` (a separate compose service, port 8046) imports and calls `WarpTunnel` directly on every `POST /scan`. Corrected every affected section of this pack (header, DDD, SIM, TFM, PROC, RUN) to state the accurate finding: `tunnel.py` has no caller within `workers/warp-tunnel/` itself, but is genuinely live via The Ice Box's worker. |
