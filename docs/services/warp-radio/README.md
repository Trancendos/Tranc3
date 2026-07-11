# Service Doc-Pack — Warp Radio

| Field | Value |
|---|---|
| **Entity** | Warp Radio |
| **Lead AI** | Rocking Ricki |
| **Status** | ✅ Live (deployed worker, port 8073) |
| **Foundation** | `workers/warp-radio/main.py` (deployed) + `workers/warp-radio/worker.py` + `src/warp_radio/station.py` (both undeployed alternates) |

> **Truthfulness header (2026-07-07 rewrite).** This entity was previously charter-only
> (GOV+RACI+TFM+POL+STD) with an explicit note that its "no implementation exists" claim was
> false. This rewrite replaces that pack with a full, code-grounded Live-tier pack, verified
> against the actually-deployed file (`workers/warp-radio/Dockerfile`'s `CMD ["python", "main.py"]`
> confirms `main.py` — not `worker.py` — is what runs in production), consistent with the
> lesson learned earlier in this doc-pack series (a prior VRAR3D fix regressed because the wrong
> file was checked).
>
> **Three independent, non-communicating implementations exist for this one entity:**
> 1. `workers/warp-radio/main.py` (54 lines) — **the deployed one.** An honest stub: every route
>    that would need real streaming/library state returns an explicit "nothing configured /
>    nothing playing" message rather than fabricated data. Never fakes success.
> 2. `workers/warp-radio/worker.py` (362 lines) — a real, undeployed alternate implementation
>    with SQLite-backed playlist/track/play-event management and `X-Internal-Secret` auth on
>    write routes. Not wired into the Dockerfile `CMD`, so none of its routes are reachable in
>    production.
> 3. `src/warp_radio/station.py` (143 lines) — a second, orphaned alternate implementation: a
>    `WarpRadio` class modelling Icecast stream sources (`register_source()`, `list_sources()`,
>    `status()`, `listener_count()`, `summary()`, `get_warp_radio()` factory). Confirmed via
>    repo-wide grep (`grep -rn "WarpRadio\|warp_radio" --include="*.py" src/ api.py | grep -v
>    "src/warp_radio/"`) to have **zero callers anywhere in the repository** — it is not
>    imported by `api.py`, not imported by either `main.py` or `worker.py`, and not referenced
>    by any router registration. This is the same "real code, zero callers" pattern already
>    documented for The Warp Tunnel's `src/security/warp_tunnel/tunnel.py`.
>
>    This is the **safe direction** of the two possible "doc vs. code" mismatches identified
>    this session (contrast with The Academy, where a FAKE implementation was deployed over a
>    real one — the most severe defect in this series). Here, the deployed code is the honest
>    stub; the more-complete alternates simply aren't wired up. No user-facing harm results from
>    the current state, but it does mean playlist/track/station data submitted via `worker.py`'s
>    routes (if ever manually run) or `station.py`'s stream-source registry would be invisible
>    to the deployed app, and vice versa — there is no shared storage between the three files.
>
> **Fixed this pass (2 defect classes, matching every prior entity in this series):**
> - `workers/warp-radio/Dockerfile`: `EXPOSE 8057` → `8073`; healthcheck hardcoded `localhost:8057`
>   → reads `PORT` env at check time (was cosmetic per the `CLAUDE.md` §188 precedent since the
>   Dockerfile `CMD` is a bare `python main.py` invocation and compose's own healthcheck override
>   takes precedence in the deployed path — fixed anyway for defence against non-compose
>   deployment).
> - `workers/warp-radio/main.py`: `PORT` env default and module docstring header both said
>   `8057`; corrected to `8073` to match `docker-compose.production.yml`'s routed port.
> - `docker-compose.production.yml`: Traefik router had a bare ``PathPrefix(`/warp-radio`)``
>   rule with **no `StripPrefix` middleware** — a genuine, live routing defect. Every external
>   request to `/warp-radio/<anything>` was forwarded to the container with the `/warp-radio`
>   prefix intact, and `main.py`'s routes (`/health`, `/status`, `/now-playing`, `/stations`) are
>   unprefixed, so every proxied request would 404. Fixed by adding
>   `traefik.http.routers.warp-radio.middlewares=strip-warp-radio@docker` +
>   `traefik.http.middlewares.strip-warp-radio.stripprefix.prefixes=/warp-radio` labels, matching
>   the pattern already used elsewhere in the same compose file. **This is the 7th instance of
>   this exact defect class fixed this session** (after The Academy, Sashas Photo Studio,
>   Taimra, TateKing, Imaginarium, The Warp Tunnel).
>
> **Documented but NOT fixed (needs an architectural decision, not a drive-by patch):**
> - `workers/warp-radio/worker.py` line 31: `INTERNAL_SECRET = os.getenv("INTERNAL_SECRET",
>   "dev-secret")` — an insecure hardcoded fallback, identical in shape to the same pattern found
>   in TateKing's, Imaginarium's, and The Warp Tunnel's undeployed `worker.py` files this
>   session. Must be fixed (fail fast if `INTERNAL_SECRET` is unset, no default) before any
>   promotion of `worker.py` to deployed status.
>   `src/warp_radio/station.py`'s `WarpRadioConfig.icecast_admin_password` also defaults to the
>   literal string `"hackme"` — same class of issue, same fix requirement, if this module is
>   ever wired up.
> - Which of the three implementations should actually be deployed (or whether they should be
>   merged into one) is a product/architecture decision for the Rocking Ricki / Platform
>   Engineering owners, not something this pass decides unilaterally.

## 1. Service Governance Charter (GOV)

- **Mission:** zero-cost music & audio streaming integration for the platform — playlist/track
  metadata management and (per the undeployed `station.py`) Icecast stream-source status
  tracking. No paid streaming provider is used or planned; the zero-cost architecture principle
  applies (`station.py`'s `cost: str = "zero"` field on `StreamSource` makes this explicit).
- **In scope (as deployed today):** `GET /health`, `GET /status`, `GET /now-playing`,
  `GET /stations` — all honest-stub responses; no playlist, track, or stream state is actually
  persisted or served by the deployed `main.py`.
- **In scope (implemented but undeployed, `worker.py`):** SQLite-backed playlist CRUD, track
  CRUD, playlist↔track association, play-event recording, and aggregate stats — all gated behind
  `X-Internal-Secret` auth on write routes.
- **In scope (implemented but undeployed, `station.py`):** Icecast stream-source registration
  and status/listener-count tracking — no HTTP surface; a plain Python class with no caller.
- **Out of scope:** actual audio transcoding/relay (Icecast itself would run as a separate
  process/container — no such container exists in `docker-compose.production.yml`); DRM;
  third-party paid streaming APIs.
- **Lead AI (Tier 3):** Rocking Ricki — role per `PLATFORM_ENTITIES.md`.
- **Owner (RACI-A):** Platform Owner (Trancendos), delegated to Rocking Ricki.
- **Review cadence:** quarterly per framework default, or immediately if any of the three
  implementations is promoted/wired up.
- **Dependencies (hard):** none for the deployed stub. `worker.py` depends on local SQLite
  (`workers/warp-radio/data/radio.db`, auto-created). `station.py` would depend on a
  self-hosted Icecast instance (not present in compose) if ever wired up.

## 2. Domain-Driven Design (DDD) — HTTP Surface

### 2.1 Deployed (`workers/warp-radio/main.py`, port 8073, no auth)

| Method | Path | Behaviour |
|---|---|---|
| GET | `/health` | `{"service": "warp-radio", "status": "ok", "uptime": <float>}` |
| GET | `/status` | `{"entity": "Warp Radio", "lead_ai": "Rocking Ricki", "status": "initialising", "uptime": <float>, "navidrome_url": <str>}` |
| GET | `/now-playing` | `{"now_playing": null, "message": "Nothing playing yet."}` (always — no real playback state) |
| GET | `/stations` | `{"stations": [], "total": 0, "message": "No stations configured."}` (always — no real station registry) |

Note: `/status` references a `NAVIDROME_URL` env var (default `http://navidrome:4533`) —
Navidrome is not present in `docker-compose.production.yml`, so this value is currently
aspirational/unused beyond being echoed back.

### 2.2 Undeployed (`workers/warp-radio/worker.py`, not built into the image)

| Method | Path | Auth | Behaviour |
|---|---|---|---|
| GET | `/health` | none | liveness |
| GET | `/metrics` | none | request/error counters |
| POST | `/playlists` | `X-Internal-Secret` | create playlist |
| GET | `/playlists` | none | list playlists |
| GET | `/playlists/{playlist_id}` | none | get one playlist |
| POST | `/tracks` | `X-Internal-Secret` | create track |
| GET | `/tracks` | none | list tracks |
| POST | `/playlists/{playlist_id}/tracks` | `X-Internal-Secret` | add track to playlist |
| DELETE | `/playlists/{playlist_id}/tracks/{track_id}` | `X-Internal-Secret` | remove track from playlist |
| POST | `/plays` | `X-Internal-Secret` | record a play event |
| GET | `/stats` | `X-Internal-Secret` | aggregate stats |

### 2.3 Undeployed (`src/warp_radio/station.py`) — no HTTP surface

Plain Python class, `WarpRadio`, with no FastAPI router. Methods: `register_source()`,
`get_source()`, `list_sources()`, async `health()`, `status` (property), `listener_count()`,
`summary()`. Instantiated only via its own `get_warp_radio()` factory, which nothing else in
the repo calls.

## 3. Technical Architecture & Solution Design (TASD)

- **Deployed runtime:** FastAPI + Uvicorn, stateless, no persistence, no external calls beyond
  echoing an env var. Trivial to reason about; trivial to keep honest.
- **Undeployed `worker.py` runtime:** FastAPI + Uvicorn + local SQLite (WAL mode), lifespan-init
  schema creation, `X-Internal-Secret` header auth via a FastAPI dependency (`_auth()`).
- **Undeployed `station.py`:** in-memory dataclass registry, designed to eventually front an
  Icecast (self-hosted, GPL, zero-cost per the platform's foundation-selection table) relay —
  no such relay exists in the compose stack today.
- **Routing:** Traefik ``PathPrefix(`/warp-radio`)`` + (as of this pass) `StripPrefix`
  middleware → container port 8073 (compose) ↔ `PORT` env (now `8073`, previously mismatched at
  `8057` in code defaults).

## 4. RACI Matrix

| Activity | Platform Owner | Rocking Ricki | Platform Engineering | The Town Hall |
|---|---|---|---|---|
| Charter approval / scope changes | **A** | C | R | I |
| Deployed-stub maintenance | I | **A** | R | I |
| Deciding which implementation to promote | **A** | R | C | I |
| Fixing `INTERNAL_SECRET`/`icecast_admin_password` defaults before promotion | I | C | **R/A** | I |
| Icecast (or equivalent) container provisioning, if promoted | I | C | **R/A** | I |
| Incident response (deployed stub) | I | C | **R/A** | I |

## 5. Service Interaction Map (SIM)

```
Traefik (websecure, PathPrefix /warp-radio + StripPrefix)
   │
   ▼
warp-radio container (port 8073) ── main.py (deployed, stub) ── no downstream calls
                                  └─ worker.py (undeployed) ── local SQLite (radio.db)
src/warp_radio/station.py (undeployed, orphaned) ── would-be Icecast relay (not provisioned)
```

No other platform service calls Warp Radio today (`grep`-confirmed no cross-service HTTP
client references to `/warp-radio` outside this worker and compose/monitoring config).

## 6. Application Service Design (ASD)

- Deployed `main.py` has no service-layer logic beyond static/echo responses — nothing to
  design further until real state is introduced.
- `worker.py`'s service layer (`get_conn()`, `init_db()`, route handlers) is functionally
  complete for basic playlist/track CRUD but has not been reviewed for concurrency safety
  beyond SQLite's own WAL mode guarantees.

## 7. Deployment Scope Matrix (DSM)

- **Mode awareness:** No — this entity's own code does not call `PlatformInfraMode` / `src/platform/infrastructure_mode.py`. (Some platform-wide, cross-cutting code *does* branch on the mode — `src/routers/adaptive.py` and `src/routers/ecosystem.py` read/set `PLATFORM_INFRA_MODE`/`SYSTEM_MODE` directly, and `Dimensional/architecture/storage_factory.py` selects a storage provider from `SYSTEM_MODE` — but none of that code is owned by this or any other one of the 43 named entities; it is shared platform infrastructure, not this service's own logic. The Citadel is the only one of the 43 named entities whose own code branches on the mode — see `docs/services/the-citadel/README.md`.) This entity's deployment scope is determined externally — by which `docker-compose.production.yml` service block runs, and where — not by in-process mode detection.
- **Runtime placement:** standalone worker with its own `docker-compose.production.yml` service block (`warp-radio`, port 8073) and its own Traefik route — does not run inside the `tranc3-backend` monolith
- **Persistence:** **no named volume** on the `warp-radio` compose service — any on-disk state is lost on container replace/redeploy in every mode alike
- **Note:** see the Cloud-Only caveat on egress bandwidth — this is a genuine per-mode cost difference, not just durability.

| Setup | What runs, and where | Data locality | Hard blockers / caveats |
|---|---|---|---|
| **Cloud-Only** | the `warp-radio` compose block runs on a single cloud host; Traefik/edge in front | ephemeral — no volume means state does not survive a redeploy | Icecast-style audio streaming needs sustained outbound bandwidth — free-tier cloud egress quotas make Cloud-Only the most quota-constrained mode for this specific entity, unlike most others on this platform |
| **Hybrid** | same `warp-radio` compose block; per `docs/architecture/infrastructure-modes.md`'s Hybrid diagram, this worker itself still runs as a single instance (cloud or local host), with only shared persistent data (not specific to this worker) split via TrueNAS/Syncthing | as above, optionally local-synced if a volume exists | requires `CITADEL_LOCAL_STACK=true` if a local compose stack should run alongside the cloud one |
| **Local-Only** | same `warp-radio` compose block, run entirely on local/Citadel hardware behind local Traefik | fully local (still no volume — same durability gap as Cloud-Only) | none beyond standard local-hardware ops |

- **Zero-cost posture per mode:** Cloud-Only defaults to the `zero_cost_cloud` AI-rotation chain; Hybrid/Local-Only default to `zero_cost_full` (`config/platform/infrastructure_mode.yaml`) — this only affects AI-Gateway-routed calls, not this entity's own logic
- **Switching modes:** operator-level via `PLATFORM_INFRA_MODE` (or legacy `SYSTEM_MODE`); this entity needs no code change to move between modes, only a redeploy-target change for its own compose block

## 8. Technology Framework Matrix (TFM)

| Layer | Choice | Cost |
|---|---|---|
| Web framework | FastAPI + Uvicorn | zero (OSS) |
| Persistence (undeployed alt.) | SQLite (WAL) | zero (embedded) |
| Streaming relay (undeployed, unprovisioned) | Icecast (GPL) | zero (self-hosted, not yet deployed) |
| Reverse proxy | Traefik | zero (already in stack) |

## 9. Policy & Compliance (POL)

- No PII is handled by the deployed stub.
- If `worker.py` is ever promoted: playlist/track data is not inherently sensitive, but the
  `X-Internal-Secret` auth model must not ship with the `"dev-secret"` fallback — fail-fast on
  missing env var, per the platform's zero-trust IAM principle already applied elsewhere
  (`src/auth/zero_trust.py`).

## 10. Procedures (PROC)

- **Local dev:** `cd workers/warp-radio && pip install -r requirements.txt && python main.py`
  (runs the deployed stub) or `python worker.py` (runs the alternate — its `_auth()` check is
  always active, but falls back to the insecure hardcoded `"dev-secret"` unless `INTERNAL_SECRET`
  is set).
- **Promotion path (if approved):** (1) fix `INTERNAL_SECRET`/`icecast_admin_password` insecure
  defaults, (2) decide `worker.py` vs. `station.py` vs. a merge, (3) update Dockerfile `COPY`/
  `CMD` to build the chosen file, (4) re-run this doc-pack's DDD section against the newly
  deployed surface.

## 11. Runbook (RUN)

- **Health check:** `GET /warp-radio/health` (via Traefik, post-StripPrefix) or
  `GET /health` directly on port 8073.
- **Symptom: 404 on all `/warp-radio/*` requests.** Before this pass, this was expected —
  missing `StripPrefix`. Now fixed; if it recurs, check the Traefik middleware label wasn't
  reverted.
- **Symptom: playlist data submitted via `worker.py` doesn't show up via the deployed app.**
  Expected — `main.py` and `worker.py` share no storage. Not a bug; a consequence of the
  documented multi-implementation state above.

## 12. Standards (STD)

- Follows the same FastAPI/Uvicorn/health-endpoint conventions as every other standalone
  worker in `workers/`.
- Any future promotion must follow the zero-cost, self-hosted architecture principles in
  `CLAUDE.md` (no paid streaming APIs).

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-04 | Claude (session) | `CLAUDE.md` service table (status, Lead AI, Foundation), `PLATFORM_ENTITIES.md` (identity), initial repo search | **SUPERSEDED — was wrong.** Initial search incorrectly concluded no implementation exists. |
| 2026-07-04 | Claude (session), corrected after cubic PR review | actual repo contents | **Correction: code DOES exist.** Pack remained charter-only pending a real Partial/Live-tier rewrite. |
| 2026-07-07 | Claude (session) | direct reads of `workers/warp-radio/main.py` (deployed), `workers/warp-radio/worker.py` (undeployed), `src/warp_radio/station.py` (undeployed, confirmed orphaned via repo-wide grep), `workers/warp-radio/Dockerfile`, `docker-compose.production.yml`'s warp-radio block | **Full rewrite to Live-tier (11 sections).** Fixed: Dockerfile `EXPOSE`/healthcheck port (8057→8073); `main.py` `PORT` default + docstring header (8057→8073); added missing Traefik `StripPrefix` middleware (genuine live routing defect — 7th instance of this class fixed this session). Documented, not fixed: insecure `INTERNAL_SECRET`/`icecast_admin_password` fallback defaults in the two undeployed alternates; promotion decision left open for the entity owner. |
