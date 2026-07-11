# Service Doc-Pack — Fabulousa

| Field | Value |
|---|---|
| **Entity** | Fabulousa |
| **Lead AI** | Baron Von Hilton |
| **Status** | ✅ Live (deployed worker, port 8048) |
| **Foundation** | `workers/fabulousa-service/worker.py` — Penpot bridge, Figma-API fallback |

> **Truthfulness header (2026-07-07 rewrite).** This pack was previously Planned-tier
> (GOV+RACI+TFM+POL+STD only), asserting "no implementation exists yet." That was false: a
> real, single-file worker (`workers/fabulousa-service/worker.py`, 287 lines) implements this
> entity — a Penpot design-platform bridge with a Figma-API read-only fallback and an
> honestly-flagged `degraded: true` offline-cache stub as the final fallback. There is no
> separate `main.py`; `worker.py` is the only implementation and is what the (now-added)
> Dockerfile builds directly.
>
> **Genuine, build-breaking defect found and fixed this pass:** `workers/fabulousa-service/`
> had **no Dockerfile at all**, despite `docker-compose.production.yml`'s `fabulousa-service`
> block referencing `dockerfile: Dockerfile` — `docker compose build` would fail outright for
> this service. This is the exact same defect class flagged (but not fixed for this specific
> directory) by The Artifactory pack earlier in this session, which listed
> `fabulousa-service` as one of 8 worker directories missing a Dockerfile. Fixed by adding a
> Dockerfile matching the established single-file-worker convention (non-root user, `EXPOSE
> 8048`, healthcheck reading `PORT` from the environment, `CMD ["uvicorn", "worker:app", ...]`).
>
> **Traefik routing checked, found correct — NOT the StripPrefix defect found in 7 other
> entities this session.** Unlike The Academy, Sashas Photo Studio, Taimra, TateKing,
> Imaginarium, The Warp Tunnel, and Warp Radio (all of which had unprefixed app routes and
> needed a `StripPrefix` middleware added), `worker.py`'s own routes are **already
> self-prefixed** with `/fabulousa` (`/fabulousa/status`, `/fabulousa/projects`,
> `/fabulousa/assets`, `/fabulousa/export`). Compose's bare ``PathPrefix(`/fabulousa`)`` rule
> with no `StripPrefix` middleware therefore forwards the full external path straight through
> to a matching app route — this is **already correct**. Adding a `StripPrefix` middleware here
> (as done for the other 7 entities) would have been a **regression** — it would strip the
> `/fabulousa` prefix from the forwarded request, leaving the app to receive `/status` instead
> of `/fabulousa/status`, which has no matching route. This was caught and reverted before
> committing, consistent with the session's standing lesson (from an earlier VRAR3D false-fix)
> to verify the actual deployed route shapes before applying a routing "fix" pattern from a
> prior entity. One consequence of the self-prefixed design: `GET /health` (the one route
> `worker.py` does *not* prefix) is unreachable at `/fabulousa/health` externally — only at
> the bare `/health` internally. Documented below, not changed, since altering the health-check
> path is a minor behavioural change outside a pure infra-defect fix.
>
> **Auth added this pass (follow-up, 2026-07-08):** cubic flagged (P1) that both write routes
> (`POST /fabulousa/projects`, `POST /fabulousa/export`) had zero authentication. Fixed by
> adding an `INTERNAL_SECRET`-gated dependency to both routes, matching the same
> optional-but-available pattern already used by `storage-service`/`files-service`
> (`_require_internal_auth()` — a no-op if `INTERNAL_SECRET` is unset, enforced once an
> operator sets it). This is non-breaking (no secret is currently set in
> `docker-compose.production.yml`, so behaviour is unchanged until one is configured) while
> giving operators a way to close the gap without a code change. Read routes remain open by
> design (no PII, no write side-effects).

## 1. Service Governance Charter (GOV)

- **Mission:** styling, UX, UI & design centre — bridges the self-hosted Penpot design
  platform to the Trancendos ecosystem, with a read-only Figma API fallback when Penpot is
  unreachable.
- **In scope:** `GET /fabulousa/status` (Penpot reachability + Figma-fallback-configured flag),
  `GET /fabulousa/projects` (Penpot teams/files → Figma profile fallback → cached-degraded
  stub), `POST /fabulousa/projects` (create a Penpot file), `GET /fabulousa/assets` (Penpot
  libraries, cached-degraded on failure), `POST /fabulousa/export` (trigger a Penpot
  export-binfile job).
- **Out of scope:** any paid design-tool integration; actual rendering/rasterisation (delegated
  entirely to Penpot's own export pipeline); real-time collaborative editing (Penpot's own UI
  handles this, not proxied here).
- **Lead AI (Tier 3):** Baron Von Hilton — per `PLATFORM_ENTITIES.md`.
- **Owner (RACI-A):** Platform Owner (Trancendos), delegated to Baron Von Hilton.
- **Review cadence:** quarterly per framework default.
- **Dependencies (soft, both optional with fallback behaviour):** Penpot (`PENPOT_URL`,
  default `http://localhost:9001` — not present in `docker-compose.production.yml`, so
  currently always unreachable in the deployed stack); Figma REST API (`FIGMA_TOKEN`, opt-in,
  read-only free tier).

## 2. Domain-Driven Design (DDD) — HTTP Surface

| Method | Path | Auth | Behaviour |
|---|---|---|---|
| GET | `/health` | none | liveness (note: unprefixed — see truthfulness header) |
| GET | `/fabulousa/status` | none | Penpot reachability probe + Figma-fallback-configured flag |
| GET | `/fabulousa/projects` | none | Penpot teams→files; on failure, Figma `/me` profile stub; on that failure, cached data with `degraded: true` |
| POST | `/fabulousa/projects` | `X-Internal-Secret`* | create a Penpot file (503 if Penpot unreachable — no fallback for writes) |
| GET | `/fabulousa/assets` | none | Penpot libraries; cached-degraded fallback on failure |
| POST | `/fabulousa/export` | `X-Internal-Secret`* | trigger a Penpot export job (503 if Penpot unreachable — no fallback for writes) |

\* Enforced only if `INTERNAL_SECRET` is set — currently unset in compose/`.env.example`, so
both write routes remain open until an operator configures a secret (see truthfulness header).
Read routes have no auth by design.

## 3. Technical Architecture & Solution Design (TASD)

- FastAPI + Uvicorn, fully stateless except a process-local `_cache: dict` used only to serve
  a `degraded: true` response on read-endpoint failure — never persisted, lost on restart.
- Adaptive fallback chain, correctly implemented per the module's own docstring: Penpot (write
  + read) → Figma REST API (read-only, `/fabulousa/projects` GET only) → offline cached stub
  (reads only). Writes (`POST /fabulousa/projects`, `POST /fabulousa/export`) have **no**
  fallback — they simply 503 if Penpot is unreachable, which is honest (no fake success) but
  worth noting as an asymmetry versus the read paths' three-tier fallback.
- `PENPOT_URL` defaults to `http://localhost:9001`, which inside the container resolves to the
  container itself, not a real Penpot instance — since no `penpot` service exists in
  `docker-compose.production.yml`, every Penpot call currently fails and every read falls
  through to the Figma/offline tiers in production as deployed today.

## 4. RACI Matrix

| Activity | Platform Owner | Baron Von Hilton | Platform Engineering | The Town Hall |
|---|---|---|---|---|
| Charter approval / scope changes | **A** | C | R | I |
| Deployed-worker maintenance | I | **A** | R | I |
| Provisioning a real Penpot container | I | C | **R/A** | I |
| Setting `INTERNAL_SECRET` in production to enforce write-route auth | I | C | **R/A** | I |
| Incident response | I | C | **R/A** | I |

## 5. Service Interaction Map (SIM)

```
Traefik (websecure, PathPrefix /fabulousa, no StripPrefix — correct, see header)
   │
   ▼
fabulousa-service container (port 8048) ── worker.py
   ├─ Penpot (PENPOT_URL, default localhost:9001 — not provisioned in compose, always unreachable today)
   └─ Figma REST API (api.figma.com, opt-in via FIGMA_TOKEN)
```

No confirmed caller of this service was found elsewhere in the repo.

## 6. Application Service Design (ASD)

- Read-path degradation is genuinely three-tier and honestly labelled (`degraded: true` is a
  real signal, not a decorative field — callers can distinguish live data from stale cache).
- Write-path has no queueing/retry — a transient Penpot outage during a write simply fails the
  request; the caller must retry.

## 7. Deployment Scope Matrix (DSM)

- **Mode awareness:** No — this entity's own code does not call `PlatformInfraMode` / `src/platform/infrastructure_mode.py` (repo-wide grep confirms none of the 43 named platform entities branch on `PLATFORM_INFRA_MODE`/`SYSTEM_MODE` directly). Its deployment scope is determined externally — by which `docker-compose.production.yml` service block runs, and where — not by in-process mode detection.
- **Runtime placement:** standalone worker with its own `docker-compose.production.yml` service block (`fabulousa-service`, port 8048) and its own Traefik route — does not run inside the `tranc3-backend` monolith
- **Persistence:** **no named volume** on the `fabulousa-service` compose service — any on-disk state is lost on container replace/redeploy in every mode alike

| Setup | What runs, and where | Data locality | Hard blockers / caveats |
|---|---|---|---|
| **Cloud-Only** | the `fabulousa-service` compose block runs on a single cloud host; Traefik/edge in front | ephemeral — no volume means state does not survive a redeploy | if this worker writes any local file it needs to keep, that data is at risk on every mode until a volume is added |
| **Hybrid** | same `fabulousa-service` compose block; per `docs/architecture/infrastructure-modes.md`'s Hybrid diagram, this worker itself still runs as a single instance (cloud or local host), with only shared persistent data (not specific to this worker) split via TrueNAS/Syncthing | as above, optionally local-synced if a volume exists | requires `CITADEL_LOCAL_STACK=true` if a local compose stack should run alongside the cloud one |
| **Local-Only** | same `fabulousa-service` compose block, run entirely on local/Citadel hardware behind local Traefik | fully local (still no volume — same durability gap as Cloud-Only) | none beyond standard local-hardware ops |

- **Zero-cost posture per mode:** Cloud-Only defaults to the `zero_cost_cloud` AI-rotation chain; Hybrid/Local-Only default to `zero_cost_full` (`config/platform/infrastructure_mode.yaml`) — this only affects AI-Gateway-routed calls, not this entity's own logic
- **Switching modes:** operator-level via `PLATFORM_INFRA_MODE` (or legacy `SYSTEM_MODE`); this entity needs no code change to move between modes, only a redeploy-target change for its own compose block

## 8. Technology & Framework Matrix (TFM)

| Layer | Choice | Cost |
|---|---|---|
| Web framework | FastAPI + Uvicorn | zero (OSS) |
| Design platform (not yet provisioned) | Penpot (MPL 2.0, self-hosted) | zero |
| Fallback | Figma REST API (free tier, read-only) | zero |

## 9. Policy & Compliance (POL)

- Both write endpoints are now gated behind an optional `INTERNAL_SECRET` check (fixed this
  pass) — enforcement is live once an operator sets the env var, open until then. No PII is
  inherently handled, but design assets may be sensitive depending on tenant use.
- Zero-cost mandate is honoured: no paid API is called (Figma's fallback is explicitly the free
  read-only tier).

## 10. Procedures (PROC)

- **Local dev:** `cd workers/fabulousa-service && pip install -r requirements.txt && uvicorn
  worker:app --port 8048`.
- **Provisioning real Penpot:** add a `penpot` service to `docker-compose.production.yml` and
  set `PENPOT_URL`/`PENPOT_TOKEN` — no code change required, the client already targets an
  env-configurable URL.

## 11. Runbook (RUN)

- **Health check:** `GET http://fabulousa-service:8048/health` directly (not reachable via
  Traefik at `/fabulousa/health` — see truthfulness header).
- **Symptom: `/fabulousa/projects` always returns `degraded: true`.** Expected while no
  `penpot` container is provisioned and no `FIGMA_TOKEN` is set — both fallback tiers are
  unavailable, so every read serves from the (empty, until first success) local cache.
- **Symptom: `docker compose build fabulousa-service` fails with "Dockerfile not found."**
  Was expected before this pass — now fixed. If it recurs, check the Dockerfile wasn't removed.

## 12. Standards (STD)

- Follows the same FastAPI/Uvicorn/single-file-worker conventions as other standalone workers
  audited this session; Dockerfile now matches the established non-root-user pattern (same
  template as The Artifactory's).
- Any future auth work must follow the platform's zero-trust IAM principle
  (`src/auth/zero_trust.py`).

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-04 | Claude (session) | `CLAUDE.md` service table, `PLATFORM_ENTITIES.md`, repo search | **SUPERSEDED — was wrong.** Concluded no implementation exists. |
| 2026-07-07 | Claude (session) | direct read of `workers/fabulousa-service/worker.py` (287 lines, the only implementation), the (missing, now added) Dockerfile, and the `fabulousa-service` block in `docker-compose.production.yml` | **Full rewrite to Live-tier (11 sections).** Fixed a genuine build-breaking defect: no Dockerfile existed for this worker (previously flagged, not yet fixed, in The Artifactory's doc-pack). Checked for the StripPrefix defect class found in 7 other entities this session and correctly determined it does NOT apply here — `worker.py`'s routes are already self-prefixed with `/fabulousa`, so adding StripPrefix would have been a regression; the incorrect middleware was added then reverted before committing. Documented, not fixed: no auth on any route (including both write endpoints); `/health` is unreachable via the public Traefik path. |
| 2026-07-08 | Claude (session), follow-up after cubic review (P1) | `workers/fabulousa-service/worker.py` | **Fixed.** Added an `INTERNAL_SECRET`-gated `_require_internal_auth()` dependency to `POST /fabulousa/projects` and `POST /fabulousa/export`, matching `storage-service`'s optional-auth pattern (no-op if unset, enforced once configured). Verified via direct module import that both routes now carry the auth dependency and GET routes are unaffected. |
