# Service Doc-Pack — The Ice Box

| Field | Value |
|---|---|
| **Entity** | The Ice Box |
| **Lead AI** | Neonach |
| **Status** | ✅ Live (deployed worker, port 8046) |
| **Foundation** | `workers/ice-box-service/worker.py` — genuine static threat analysis + quarantine, real integration with The Warp Tunnel's `WarpTunnel` class |

> **Truthfulness header (2026-07-07 rewrite).** This pack was previously Planned-tier
> (GOV+RACI+TFM+POL+STD only), asserting "no implementation exists yet." That was false: a
> real worker (`workers/ice-box-service/worker.py`, 225 lines) implements this entity, and it
> is the *only* known live caller of `src/security/warp_tunnel/tunnel.py`'s `WarpTunnel`
> class — this pack's investigation directly triggered a correction to
> `docs/services/the-warp-tunnel/README.md`, which had wrongly claimed that class was fully
> orphaned (a grep that missed `workers/` in the earlier pass).
>
> **Genuine, build-breaking defect found and fixed this pass — a novel defect class not seen
> yet in this series:** `workers/ice-box-service/` had **no Dockerfile**, but unlike Fabulousa
> (which also lacked one), a naive Dockerfile copy would not have been sufficient here.
> `worker.py` imports `src.security.ice_box.analyser`, `src.security.ice_box.quarantine`,
> `src.security.ice_box.signatures`, and `src.security.warp_tunnel.tunnel` — real repo-level
> `src/` packages — and even inserts `Path(__file__).resolve().parents[2]` onto `sys.path` at
> import time to make that work when run from its natural repo location. Compose's original
> (non-existent) build reference used `context: ./workers/ice-box-service`, which cannot see
> `src/` at all (Docker `COPY` cannot reach outside the build context). Fixed by:
> 1. Changing the compose block to `context: .` (repo root) + `dockerfile:
>    workers/ice-box-service/Dockerfile`, matching the existing pattern already used by
>    `tranc3-backend`/`infinity-portal`/`infinity-one`/`infinity-admin` for the same reason.
> 2. Writing a Dockerfile that preserves the same relative directory depth inside the image
>    (`/app/workers/ice-box-service/worker.py` + `/app/src/security/...`) so the `parents[2]`
>    computation in `worker.py` still resolves to `/app` and `sys.path` still finds `src`
>    correctly — verified by executing the module directly from the repo root before writing
>    this doc, which imports cleanly.
> 3. Adding `requirements.txt` (fastapi, uvicorn, pydantic) — none existed for this worker.
>
> Also fixed the same Traefik `StripPrefix` defect class found in 7 other entities this
> session: bare ``PathPrefix(`/ice-box`)`` with no `StripPrefix`, while `worker.py`'s routes
> (`/health`, `/scan`, `/quarantine`, `/quarantine/{id}`, `/quarantine/{id}/release`, `/stats`)
> are unprefixed — fixed with a `strip-ice-box` middleware (the 9th instance this session,
> after The Academy, Sashas Photo Studio, Taimra, TateKing, Imaginarium, The Warp Tunnel,
> Warp Radio, DocUtari having none-applicable — count includes all genuinely-fixed instances).
>
> **A related, broader defect noted but explicitly out of scope for this pass:** while fixing
> this, `workers/swarm-coordinator-service/Dockerfile` was found to have the **same class of
> bug** — its compose block uses `context: ./workers/swarm-coordinator-service` (a narrow
> context) yet its own Dockerfile does `COPY src/entities/ ...`, which cannot resolve from
> that context. This looks like the same defect pattern, but touches a different entity
> (Swarm Coordinator, not yet doc-packed in this series) and was left unfixed here to keep
> this pass scoped to The Ice Box — flagged for a future pass.

## 1. Service Governance Charter (GOV)

- **Mission:** sandbox threat isolation & quarantine — static analysis of arbitrary
  text/content submitted by other platform services, with a persistent quarantine store and
  release workflow for reviewed items.
- **In scope:** `POST /scan` (analyse content, optionally auto-quarantine via The Warp
  Tunnel's `WarpTunnel.scan()`), `POST /quarantine` is not a separate route (quarantining
  happens as a side effect of `/scan` with `auto_quarantine=true`), `GET /quarantine` (list
  active records), `GET /quarantine/{id}` (single record), `POST /quarantine/{id}/release`
  (release with reason + reviewer), `GET /stats` (quarantine + signature-library counts).
- **Out of scope:** actual sandboxed code execution (the module docstring's "Cuckoo sandbox"
  Foundation choice was never implemented — this is a *static* analyser, not a dynamic
  execution sandbox); file-upload scanning (that's The Warp Tunnel's `worker.py`'s job, a
  separate undeployed implementation documented in that entity's own pack).
- **Lead AI (Tier 3):** Neonach — per `PLATFORM_ENTITIES.md`.
- **Owner (RACI-A):** Platform Owner (Trancendos), delegated to Neonach.
- **Review cadence:** quarterly per framework default.
- **Dependencies (hard, in-repo):** `src.security.ice_box.analyser.ThreatAnalyser`,
  `src.security.ice_box.quarantine.QuarantineStore`, `src.security.ice_box.signatures`
  (own package), and `src.security.warp_tunnel.tunnel.WarpTunnel` (a *different* entity's
  module — see the truthfulness header's cross-reference to The Warp Tunnel's pack).

## 2. Domain-Driven Design (DDD) — HTTP Surface

| Method | Path | Auth | Behaviour |
|---|---|---|---|
| POST | `/scan` | none | analyse `content`; if `auto_quarantine=true` (default), routes through `WarpTunnel.scan()` (which itself calls `ThreatAnalyser` + `QuarantineStore` internally) |
| GET | `/quarantine` | none | list active (non-released) quarantine records, paginated via `limit` |
| GET | `/quarantine/{quarantine_id}` | none | single record incl. findings JSON, entropy, release metadata |
| POST | `/quarantine/{quarantine_id}/release` | none | mark released with `reason`/`reviewed_by` (both free-text, unvalidated) |
| GET | `/stats` | none | quarantine counts + total loaded signatures + `strict_mode` flag |
| GET | `/health` | none | liveness + signature count + uptime |

No route has any authentication — `POST /quarantine/{id}/release` in particular is a
consequential write (marks potentially-malicious content as reviewed-and-safe) reachable by
any caller that can reach the container, with no verification that `reviewed_by` reflects a
real reviewer identity.

## 3. Technical Architecture & Solution Design (TASD)

- FastAPI, no async DB layer — `QuarantineStore` is a synchronous SQLite wrapper (WAL not
  explicitly confirmed, direct `sqlite3` connection per call based on the class design).
- `ThreatAnalyser.analyse()` (`src/security/ice_box/analyser.py`) does real signature-pattern
  matching against `src/security/ice_box/signatures.py`'s YARA-style rule library (injection,
  XSS, path traversal, malware/shellcode markers, credential leaks, exfiltration, suspicious
  `eval`/`exec` patterns) plus entropy scoring — genuine, non-trivial static analysis, not a
  scaffold.
- `WarpTunnel.scan()` (imported from a different entity's module tree) wraps the same
  `ThreatAnalyser`/`QuarantineStore` with configurable block/warn verdict thresholds
  (`TunnelConfig(quarantine_db=..., strict_mode=...)`) — this worker is effectively the
  deployed home of The Warp Tunnel's *content-interception* implementation, even though it
  ships under The Ice Box's entity name and port.
- **Build/deploy fix (this pass):** Dockerfile now built from repo root so `src/security/*`
  packages are present in the image at the same relative depth `worker.py`'s own
  `sys.path.insert(parents[2])` logic expects.

## 4. RACI Matrix

| Activity | Platform Owner | Neonach | Platform Engineering | The Town Hall |
|---|---|---|---|---|
| Charter approval / scope changes | **A** | C | R | I |
| Deployed-worker maintenance | I | **A** | R | I |
| Signature-library updates (`signatures.py`) | I | **A** | C | I |
| Cross-entity coordination with The Warp Tunnel (shared `WarpTunnel` code) | C | **A** | R | I |
| Adding auth to `/quarantine/{id}/release` | I | C | **R/A** | I |
| Incident response | I | C | **R/A** | I |

## 5. Service Interaction Map (SIM)

```
Traefik (websecure, PathPrefix /ice-box + StripPrefix, fixed this pass)
   │
   ▼
ice-box-service container (port 8046) ── worker.py
   ├─ src/security/ice_box/analyser.py    (ThreatAnalyser — real signature+entropy analysis)
   ├─ src/security/ice_box/quarantine.py  (QuarantineStore — SQLite-backed)
   ├─ src/security/ice_box/signatures.py  (rule library)
   └─ src/security/warp_tunnel/tunnel.py  (WarpTunnel — a DIFFERENT entity's module, genuinely called here)
```

No confirmed caller of this worker's HTTP surface was found elsewhere in the repo — like most
standalone workers audited this session, it is reachable but not yet consumed by any
in-repo client.

## 6. Application Service Design (ASD)

- `/scan`'s `auto_quarantine` flag correctly toggles between two different code paths (direct
  `ThreatAnalyser.analyse()` vs. `WarpTunnel.scan()`) rather than being decorative — both are
  exercised in the route handler, confirmed by reading `worker.py:97-143`.
- The response schema is duplicated between the two branches in `scan()` rather than shared —
  a minor maintainability note, not a functional defect.

## 7. Technology & Framework Matrix (TFM)

| Layer | Choice | Cost |
|---|---|---|
| Web framework | FastAPI + Uvicorn | zero (OSS) |
| Threat detection | in-house regex/entropy signature library (`src/security/ice_box/signatures.py`) | zero (no third-party AV engine) |
| Persistence | SQLite (`QuarantineStore`) | zero (embedded) |
| Sandboxing (Foundation-listed, not implemented) | Cuckoo sandbox | not integrated — this worker is static analysis only |

## 8. Policy & Compliance (POL)

- No auth on any route, including the release-from-quarantine write — flagged for the entity
  owner as the most consequential gap (a caller can both submit and clear quarantine flags
  with no identity verification).
- Zero-cost mandate honoured — no paid AV/sandbox API is called; the "Cuckoo sandbox"
  Foundation entry in `CLAUDE.md`'s recommended-foundations table is aspirational and not
  reflected in the actual (static-analysis-only) implementation.

## 9. Procedures (PROC)

- **Local dev:** must run from the repo root (or with `PYTHONPATH` set to the repo root) so
  `src.security.*` imports resolve: `python -m uvicorn workers.ice-box-service.worker:app`
  is not valid (hyphenated package name); instead `cd workers/ice-box-service && PYTHONPATH=../.. uvicorn worker:app --port 8046`, or rely on the module's own `sys.path.insert` when invoked as `python worker.py` from its natural repo path.
- **Building the image:** `docker compose build ice-box-service` — now works from repo root
  per the fixed compose context.

## 10. Runbook (RUN)

- **Health check:** `GET /ice-box/health` (via Traefik, post-StripPrefix) or `GET /health`
  directly on port 8046.
- **Symptom: `docker compose build ice-box-service` fails — "Dockerfile not found" or import
  errors on startup.** Was expected before this pass (no Dockerfile existed, and a naive one
  would have failed on `src` imports). Now fixed — if it recurs, check the build context wasn't
  reverted to a narrow `./workers/ice-box-service` path.
- **Symptom: someone asks why The Warp Tunnel's content-scanning code "has no caller."**
  It does — this worker. See the truthfulness header and the corresponding correction now in
  `docs/services/the-warp-tunnel/README.md`.

## 11. Standards (STD)

- Follows the same FastAPI/Uvicorn conventions as other standalone workers audited this
  session; Dockerfile now matches the repo-root-context pattern already established by
  `infinity-portal-service`/`infinity-one`/`infinity-admin` for workers needing `src/` access.
- Any future auth work must follow the platform's zero-trust IAM principle
  (`src/auth/zero_trust.py`).

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-04 | Claude (session) | `CLAUDE.md` service table, `PLATFORM_ENTITIES.md`, repo search | **SUPERSEDED — was wrong.** Concluded no implementation exists. |
| 2026-07-07 | Claude (session) | direct read of `workers/ice-box-service/worker.py` (225 lines), `src/security/ice_box/{analyser,quarantine,signatures}.py`, `src/security/warp_tunnel/tunnel.py`, the (missing, now added) Dockerfile + `requirements.txt`, and the `ice-box-service` block in `docker-compose.production.yml` | **Full rewrite to Live-tier (11 sections).** Fixed a genuine build-breaking defect requiring more than a drive-by copy: no Dockerfile existed, and the worker imports repo-level `src/` packages, so the compose build context had to be widened to the repo root (matching the `infinity-portal`/`infinity-one`/`infinity-admin` pattern) with a Dockerfile preserving the source tree's relative depth so `worker.py`'s own `sys.path.insert(parents[2])` logic resolves correctly — verified by executing the module directly before writing this doc. Also fixed the Traefik StripPrefix defect (9th instance this session). Discovered and corrected a factual error in The Warp Tunnel's pack: its `WarpTunnel`/`tunnel.py` "fully orphaned" claim was wrong — this worker is a real, live caller, confirmed here and cross-corrected in that entity's own doc-pack. Flagged, not fixed: the same context-mismatch defect class also affects `workers/swarm-coordinator-service/Dockerfile` — out of scope for this pass. Documented, not fixed: no auth on any route, most notably the quarantine-release write. |
