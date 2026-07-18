# Service Doc-Pack — VRAR3D

| Field | Value |
|---|---|
| **ServiceID (CMDB)** | `SRV-VRAR3D-001` |
| **Entity** | VRAR3D |
| **Lead AI** | Entari |
| **Status** | ✅ In repo (per `CLAUDE.md` service table) — Live tier |
| **Code** | `src/vrar3d/wellbeing_centre.py`, `src/vrar3d/routes.py`; router registered in `api.py` (`app.include_router(_vrar3d_router)`, line 888) — **plus a separate standalone worker**, `workers/vrar3d/worker.py` not audited in detail by this pack |

> **Truthfulness:** claims cite `src/vrar3d/wellbeing_centre.py` and `src/vrar3d/routes.py`
> directly. Status is owned by the `CLAUDE.md` service table; identity by `PLATFORM_ENTITIES.md`.
> **Scope mismatch vs. `CLAUDE.md`'s entity description.** `CLAUDE.md`'s platform table describes
> VRAR3D as a "standalone 3D / VR immersion" layer. The actual `src/vrar3d/*` code implements
> something narrower and different: a **wellbeing scene library** (meditation, breathing, nature,
> focus, sleep, and a reserved "crisis calm" scene type) with session tracking — the module's own
> filename (`wellbeing_centre.py`) and header comment describe it as "VRAR3D — AR/VR wellbeing
> centre," not a general-purpose 3D/VR platform capability. This may simply be VRAR3D's first
> concrete use case rather than a contradiction, but it's a real, documented gap between the
> platform-level entity description and what the code actually does — flagged rather than
> silently reconciled.
> **Tranquility and Resonate integration claims are aspirational, not implemented.** The module
> header states "Integration with Tranquility (mood + break prompts trigger scenes)" and
> "Integration with Resonate (crisis support via calming environments)" — no import of or call to
> either entity exists anywhere in `src/vrar3d/wellbeing_centre.py`. `recommend_scene()` accepts a
> `sensitivity_level` string parameter that the **caller** must supply (presumably from an I-Mind
> result obtained elsewhere) — VRAR3D itself never calls I-Mind, Tranquility, or Resonate.

## 1. Service Governance Charter (GOV)

- **Mission (as coded):** AR/VR wellbeing scene library — guided meditation, breathing exercises,
  and nature-immersion environments as WebXR (Three.js/A-Frame) scenes, with session tracking and
  mood-before/after capture.
- **Owner (RACI-A):** Platform Owner Trancendos.
- **Lead AI:** Entari.
- **Scope:** `src/vrar3d/*` covers scene catalogue and session lifecycle only. Actual WebXR scene
  rendering is client-side (Three.js/A-Frame HTML referenced via `aframe_url`) and not part of
  this backend module. No cross-entity calls to Tranquility, Resonate, or I-Mind exist — see
  truthfulness header.

## 2. Detailed Design Document (DDD)

### HTTP surface (`src/vrar3d/routes.py`, prefix `/vrar3d`)

| Method | Route | Backing |
|---|---|---|
| GET | `/vrar3d/status` | `VRAR3D.stats()` — scene/session counts |
| GET | `/vrar3d/scenes` | `VRAR3D.list_scenes()` — optional `type` filter; 400 on unknown type |
| GET | `/vrar3d/scenes/{id}` | `VRAR3D.get_scene()` — 404 if missing |
| GET | `/vrar3d/recommend` | `VRAR3D.recommend_scene()` — `mood` and/or `sensitivity_level` query params, both caller-supplied |
| POST | `/vrar3d/sessions` | `VRAR3D.start_session()` — body `{"user_id", "scene_id", "mood_before"}`; 400 if `user_id`/`scene_id` missing, 404 if scene unknown |
| POST | `/vrar3d/sessions/{id}/end` | `VRAR3D.end_session()` — body `{"mood_after"}`; 404 if session missing/already ended |

### Scene catalogue and session tracking — real, self-contained
- `WellbeingScene`: 6 hard-coded seed scenes across 5 `SceneType`s (meditation/breathing/nature/
  focus/sleep) plus a reserved `CRISIS_CALM` type — genuinely present in the seed data ("Crisis
  Calm" scene, tagged `["crisis", "safety"]`), though nothing in this module actually triggers it
  based on a real I-Mind CRITICAL signal (see recommendation logic below).
- `VRSession`: tracks `mood_before`/`mood_after` and computed `duration_seconds`; `end_session()`
  correctly guards against double-ending (`if not session or session.ended_at: return None`).

### `recommend_scene()` — caller-driven, not self-triggered
- Recommends the `CRISIS_CALM` scene only if the caller passes `sensitivity_level="critical"` in
  the request — VRAR3D does not call I-Mind itself to determine this; the caller (some other
  service, presumably, or a manual client) is responsible for obtaining and forwarding that value.
  If nothing calls `/vrar3d/recommend?sensitivity_level=critical` with a real I-Mind result, the
  crisis-calm scene is never actually reached in practice — this is architecturally sound (loose
  coupling) but means the "integration" is really "an optional parameter", not a wired pipeline.
- Falls back to a nature scene for `mood <= 2`, else a breathing scene by default. Simple,
  deterministic, no ML/heuristic beyond these two branches.

## 3. Technical Architecture Solutions Design (TASD)

- **Style:** in-process module with a module-level singleton (`get_vrar3d()`); in-memory `_scenes`
  and `_sessions` dicts, no persistence, no external DB.
- **Decision: client-side WebXR rendering, backend-only scene/session bookkeeping.** Scene content
  itself (`aframe_url`) is not stored or served by this module — it's a reference to a
  presumably-static asset elsewhere; not verified in this pass whether those A-Frame HTML assets
  actually exist in the repo.
- **Not evaluated:** whether `aframe_url`-referenced scene assets exist — none of the 6 seed
  scenes populate `aframe_url` (it defaults to `None` in every seed entry), meaning the scene
  catalogue currently has **no actual renderable content wired up** — every seed scene's
  `aframe_url` and `thumbnail_url` are unset. This is a real gap: the catalogue is fully
  metadata-only right now.

## 4. RACI Matrix

| Activity | Entari (Lead) | Platform Owner | Tranquility | Resonate | I-Mind |
|---|---|---|---|---|---|
| Scene catalogue / session logic changes | **R** | A | I | I | I |
| Wiring real Tranquility/Resonate/I-Mind integration (future) | C | **A** | **R** | **R** | **R** |
| Populating `aframe_url` with real WebXR assets (future) | **R** | A | I | I | I |

## 5. Solutions Integration Model (SIM)

- **Upstream:** any caller of `/vrar3d/*` routes — no auth on any route, including starting a
  session for an arbitrary `user_id`.
- **Downstream:** best-effort Observatory `observe()` on session start/complete. **No call to
  Tranquility, Resonate, or I-Mind** despite the module header naming all three as integrations.
- **Not integrated:** the reverse direction (Tranquility's break prompts or Resonate's crisis flow
  triggering a VRAR3D scene) also does not exist — verified absent from both this module and (per
  their own doc-packs in this series) Tranquility's code.

## 6. Architecture Scalability Document (ASD)

- **Load model:** in-memory `_scenes`/`_sessions` dicts, no cap defined — unbounded session
  growth, no eviction.
- **Bottleneck:** single-process, no persistence; a restart loses all session history (scene
  catalogue re-seeds from the hard-coded list, so that part is stable across restarts).
- **Zero-cost limits:** Three.js/A-Frame are OSS, browser-based, no native install — consistent
  with the zero-cost mandate; no scene-asset hosting cost is incurred by this backend module
  since `aframe_url` is currently unset for all seed scenes.
- **Degradation:** Observatory emission failures don't block session start/end.

## 7. Deployment Scope Matrix (DSM)

- **Mode awareness:** No — this entity's own code does not call `PlatformInfraMode` / `src/platform/infrastructure_mode.py`. (Some platform-wide, cross-cutting code *does* branch on the mode — `src/routers/adaptive.py` and `src/routers/ecosystem.py` read/set `PLATFORM_INFRA_MODE`/`SYSTEM_MODE` directly, and `Dimensional/architecture/storage_factory.py` selects a storage provider from `SYSTEM_MODE` — but none of that code is owned by this or any other one of the 43 named entities; it is shared platform infrastructure, not this service's own logic. The Citadel is the only one of the 43 named entities whose own code branches on the mode — see `docs/services/the-citadel/README.md`.) This entity's deployment scope is determined externally — by which `docker-compose.production.yml` service block runs, and where — not by in-process mode detection.
- **Runtime placement:** **two deployment surfaces**, corrected 2026-07-11 (this pack previously
  said the standalone worker was the only surface): `src/vrar3d/routes.py` is unconditionally
  mounted into the `tranc3-backend` monolith (`api.py`, `app.include_router(_vrar3d_router)`) *and*
  there is a separate standalone worker with its own `docker-compose.production.yml` service block
  (`vrar3d`, port 8060) and its own Traefik route. The table below describes the standalone
  worker; the monolith-mounted router follows the monolith's own placement and shares its volume.
- **Persistence:** named volume attached to the `vrar3d` compose service — state survives container restarts/redeploys in any mode

| Setup | What runs, and where | Data locality | Hard blockers / caveats |
|---|---|---|---|
| **Cloud-Only** | the `vrar3d` compose block runs on a single cloud host; Traefik/edge in front | persists via its attached volume as long as the volume/disk is preserved on that host | none beyond standard single-host durability (no built-in cross-host replication) |
| **Hybrid** | same `vrar3d` compose block; per `docs/architecture/infrastructure-modes.md`'s Hybrid diagram, this worker itself still runs as a single instance (cloud or local host), with only shared persistent data (not specific to this worker) split via TrueNAS/Syncthing | as above, optionally local-synced if a volume exists | requires `CITADEL_LOCAL_STACK=true` if a local compose stack should run alongside the cloud one |
| **Local-Only** | same `vrar3d` compose block, run entirely on local/Citadel hardware behind local Traefik | fully local, volume-backed | none beyond standard local-hardware ops |

- **Zero-cost posture per mode:** Cloud-Only defaults to the `zero_cost_cloud` AI-rotation chain; Hybrid/Local-Only default to `zero_cost_full` (`config/platform/infrastructure_mode.yaml`) — this only affects AI-Gateway-routed calls, not this entity's own logic
- **Switching modes:** operator-level via `PLATFORM_INFRA_MODE` (or legacy `SYSTEM_MODE`); this entity needs no code change to move between modes, only a redeploy-target change for its own compose block

## 8. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Web framework | FastAPI `APIRouter` | mounted into the main `api.py` app |
| Storage | in-memory `dict`, no persistence | zero infra cost, no durability |
| Client rendering (referenced, not implemented here) | Three.js / A-Frame WebXR | OSS, browser-based |

## 9. Environment Support Matrix (ESM)

> Grounded against `docker-compose.development.yml`, `docker-compose.uat.yml`, and `docker-compose.production.yml` — checked by exact compose service name, not assumed (see `docs/services/INDEX.md` for current platform-wide compose service totals, which change as the topology evolves).

| Environment | Covered? | What runs | Notes |
|---|---|---|---|
| **Dev** | Partial | the `api` service in `docker-compose.development.yml` runs the monolith router — the standalone `vrar3d` worker is **not** in this compose file | standalone worker has zero Dev coverage; monolith router is present and exercisable |
| **UAT** | Partial | same monolith router via `api` in `docker-compose.uat.yml` — the standalone `vrar3d` worker is **not** in this compose file either | standalone worker has zero UAT coverage; monolith router is present and exercisable |
| **Production** | Yes | both surfaces — full detail in the DSM above | — |

- **Gap:** the standalone `vrar3d` worker has **no Dev or UAT environment at all** — the first place it runs is Production. This is the norm for the ~90 standalone workers on this platform, not specific to this entity. The monolith-mounted router, however, **is** present in Dev/UAT via the `api` service — corrected 2026-07-11 after review flagged the earlier version of this table for missing that surface entirely.

## 10. Policy (POL)

- No route-level auth on any `/vrar3d/*` route — anyone can start/end a wellbeing session for
  any `user_id`.
- Zero-cost mandate: Three.js/A-Frame are free/OSS; no paid asset-hosting dependency introduced.

## 11. Procedure (PROC)

- **List available scenes:** `GET /vrar3d/scenes?type=meditation` (optional filter).
- **Get a recommendation:** `GET /vrar3d/recommend?mood=2&sensitivity_level=critical` — caller
  must supply both values; VRAR3D does not compute them itself.
- **Track a session:** `POST /vrar3d/sessions` to start, `POST /vrar3d/sessions/{id}/end` to end
  and record `mood_after`.

## 12. Runbook (RUN)

- **The crisis-calm scene never gets recommended in practice:** expected unless some other
  service explicitly calls `/vrar3d/recommend` with `sensitivity_level="critical"` sourced from a
  real I-Mind assessment — no such caller currently exists in this repo (see SIM).
- **Scenes have no visible content client-side:** expected — every seed scene's `aframe_url` is
  unset (`None`); the catalogue is metadata-only until real WebXR assets are wired up.
- **Session data disappears after a restart:** expected — no persistence; the scene catalogue
  itself re-seeds from the hard-coded list, so only session/mood history is lost.

## 13. Standards (STD)

- Naming: canonical entity name "VRAR3D" per `CLAUDE.md`/`PLATFORM_ENTITIES.md`. Note the
  platform-level entity description ("standalone 3D/VR immersion") is broader than what the
  current code implements (a wellbeing scene library specifically) — future work expanding
  VRAR3D beyond wellbeing use cases should either update `CLAUDE.md`'s description to scope it
  down, or genuinely broaden the code to match.
- **Doc-pack authoring note, not a platform-wide code standard:** when a module header claims
  integration with another named entity (here: Tranquility, Resonate, I-Mind), this doc-pack
  should verify a real call path exists before describing that integration as implemented, rather
  than repeating the header's claim at face value — the gap documented here is a repeat instance
  of the same authoring discipline applied in Tranquility's and tAimra's doc-packs this session.
  (A stricter "same module" requirement isn't appropriate as a codebase rule — legitimate
  cross-module integration patterns in FastAPI, e.g. a caller supplying an upstream result rather
  than the callee re-fetching it itself, are not inherently defects.)

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-05 | Claude (session) | `src/vrar3d/wellbeing_centre.py` (237 lines), `src/vrar3d/routes.py` (76 lines), `api.py` router registration (line 888) | Confirmed Live-tier, full pack authored. Major finding: `CLAUDE.md`'s "standalone 3D/VR immersion" entity description is broader than the actual code, which implements a wellbeing-scene library specifically (per the module's own filename and header). Also confirmed the Tranquility/Resonate/I-Mind integrations named in the module header are unimplemented — `recommend_scene()` takes a caller-supplied `sensitivity_level` string rather than calling I-Mind itself, and no code path currently supplies a real "critical" value in practice. Additionally found all 6 seed scenes have an unset `aframe_url`, meaning the catalogue currently has no renderable WebXR content wired up. |
| 2026-07-07 | Claude (session, cubic-dev-ai review triage) | GOV §1 vs. RACI §4; STD §11 | Fixed two findings. (1) RACI contradiction: GOV named both Entari and Platform Owner as "RACI-A"; reworded to a single Accountable party (Platform Owner) with Entari as Lead AI, matching the table — also added a missing I-Mind column to the RACI table itself (an I-Mind-relevant activity row existed with no I-Mind column). (2) The STD section's "MUST have a corresponding import/call in the same module" wording was overly prescriptive as a codebase-wide rule and misplaced in a service README; reworded as a doc-pack authoring note (verify integration claims before repeating them) rather than a binding code standard, and noted that legitimate cross-module call patterns (e.g. caller-supplied results) aren't inherently defects. |
