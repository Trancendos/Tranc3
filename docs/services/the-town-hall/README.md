# Service Doc-Pack — The Town Hall (Governance Hub)

| Field | Value |
|---|---|
| **ServiceID (CMDB)** | `SRV-CRANBANIA-001` |
| **Entity** | The Town Hall (`PID-TWH`) |
| **Lead AI** | Tristuran (`AID-TWH-01`); Prime: Cornelius MacIntyre |
| **Status** | ✅ Integrated (per `CLAUDE.md` service table) |
| **Code** | `src/townhall/` (in-repo router + libraries); `workers/cranbania/` (git submodule, port 8071 — **not present in this checkout**); `src/compliance/middleware.py` |
| **HTTP surface** | `/townhall/*` router — mounted in `api.py` (`app.include_router(_townhall_router)`) |

> **Truthfulness:** claims about the in-repo surface cite `src/townhall/`. The full Kanban/ITSM/PRINCE2
> board is the **CranBania** submodule (`workers/cranbania/`, port 8071), which is a separate repo and is
> **not checked out here** — this pack does not document its internals. Status owned by the `CLAUDE.md`
> service table; identity by `PLATFORM_ENTITIES.md`.

## 1. Service Governance Charter (GOV)

- **Mission:** platform governance hub — policy/compliance checks in-repo, plus the full governance board
  (PRINCE2, ITIL, Agile/Kanban, ITSM, rooms, templates) delivered by the CranBania submodule.
- **Owner (RACI-A):** Tristuran (Lead AI); Prime Cornelius MacIntyre.
- **Scope (in-repo):** a `/townhall` compliance router backed by `governance.py`, plus library modules
  (`agile`, `itsm`, `rooms`, `documents`, `framework_registry`) that are **present but only partially
  exposed** via HTTP here.

## 2. Detailed Design Document (DDD)

### HTTP surface (`src/townhall/routes.py`, prefix `/townhall`)
| Method | Route | Backing |
|---|---|---|
| GET | `/townhall/status` | governance status |
| GET | `/townhall/policies?active_only=` | policy list (from `governance.py`) |
| POST | `/townhall/check` | policy/compliance check |

> The router is intentionally thin — only these three routes are exposed in-repo. The board UI + 40+ MCP
> tools live in CranBania (submodule).

### Library modules (`src/townhall/`, present; not all HTTP-exposed)
- **`governance.py`** — governance, policy, and compliance management (backs the router).
- **`agile.py`** — Agile / Kanban boards.
- **`itsm.py`** — ITSM / ITIL incident and change records.
- **`rooms.py`** — BoardRoom / WarRoom / MeetingRooms session management.
- **`documents.py`** — policy/procedural/ADDD/blueprint templates (cookbooks, bibles, guides).
- **`framework_registry.py`** — loads the framework registry from `config/townhall/frameworks.yaml`.

### Compliance middleware
- `src/compliance/middleware.py` wires Magna Carta governance rules into the request path (platform-wide).

## 3. Technical Architecture Solutions Design (TASD)

- **Style:** split surface — a lightweight in-repo compliance/policy API on the main backend, and the
  heavyweight interactive governance board as a **separate submodule service** (CranBania, 8071, Traefik
  `/townhall`).
- **Decision:** keep policy/compliance primitives in-repo (fast, testable) and delegate the full board
  (Kanban/ITSM/PRINCE2 + MCP tools) to CranBania rather than re-implement it.

## 4. RACI Matrix

| Activity | Tristuran (Lead) | Cornelius MacIntyre (Prime) | Platform Owner | The Observatory |
|---|---|---|---|---|
| Policy / compliance API (in-repo) | **R/A** | C | C | I |
| CranBania board (submodule) | **R/A** | C | C | I |
| Governance middleware wiring | **R** | A | C | I |

## 5. Solutions Integration Model (SIM)

- **Upstream:** callers hit `/townhall/check` for compliance decisions; the main app mounts the router.
- **Downstream:** CranBania (submodule) serves the board at Traefik `/townhall` on 8071; Magna Carta rules
  applied via `src/compliance/middleware.py`.
- **Auth boundary:** router auth follows the main backend's gateway; CranBania has its own.

## 6. Architecture Scalability Document (ASD)

- **Load model:** compliance checks are low-rate policy evaluations; the board is interactive (CranBania).
- **Zero-cost limits & hard stops:** in-repo modules are pure Python; no paid governance SaaS.
- **Caveat:** the board's scaling characteristics live in the CranBania repo and are out of scope here.

## 7. Deployment Scope Matrix (DSM)

- **Mode awareness:** No — this entity's own code does not call `PlatformInfraMode` / `src/platform/infrastructure_mode.py`. (Some platform-wide, cross-cutting code *does* branch on the mode — `src/routers/adaptive.py` and `src/routers/ecosystem.py` read/set `PLATFORM_INFRA_MODE`/`SYSTEM_MODE` directly, and `Dimensional/architecture/storage_factory.py` selects a storage provider from `SYSTEM_MODE` — but none of that code is owned by this or any other one of the 43 named entities; it is shared platform infrastructure, not this service's own logic. The Citadel is the only one of the 43 named entities whose own code branches on the mode — see `docs/services/the-citadel/README.md`.) This entity's deployment scope is determined externally — by which `docker-compose.production.yml` service block runs, and where — not by in-process mode detection.
- **Runtime placement:** **two deployment surfaces**, corrected 2026-07-11 (this pack previously
  described only the standalone worker): the `/townhall/*` compliance router (`src/townhall/`) is
  mounted into the `tranc3-backend` monolith (`api.py`, `app.include_router(_townhall_router)`)
  *and* there is a separate standalone worker, the CranBania submodule, with its own
  `docker-compose.production.yml` service block (`cranbania`, port 8071) and its own Traefik
  route. The table below describes the standalone worker; the monolith-mounted router follows
  the monolith's own placement and shares its volume.
- **Persistence:** named volume attached to the `cranbania` compose service — state survives container restarts/redeploys in any mode
- **Note:** `cranbania` is a git submodule (`https://github.com/Trancendos/CranBania`) — deploying it in any mode requires the submodule to be checked out, not just the parent repo.

| Setup | What runs, and where | Data locality | Hard blockers / caveats |
|---|---|---|---|
| **Cloud-Only** | the `cranbania` compose block runs on a single cloud host; Traefik/edge in front | persists via its attached volume as long as the volume/disk is preserved on that host | none beyond standard single-host durability (no built-in cross-host replication) |
| **Hybrid** | same `cranbania` compose block; per `docs/architecture/infrastructure-modes.md`'s Hybrid diagram, this worker itself still runs as a single instance (cloud or local host), with only shared persistent data (not specific to this worker) split via TrueNAS/Syncthing | as above, optionally local-synced if a volume exists | requires `CITADEL_LOCAL_STACK=true` if a local compose stack should run alongside the cloud one |
| **Local-Only** | same `cranbania` compose block, run entirely on local/Citadel hardware behind local Traefik | fully local, volume-backed | none beyond standard local-hardware ops |

- **Zero-cost posture per mode:** Cloud-Only defaults to the `zero_cost_cloud` AI-rotation chain; Hybrid/Local-Only default to `zero_cost_full` (`config/platform/infrastructure_mode.yaml`) — this only affects AI-Gateway-routed calls, not this entity's own logic
- **Switching modes:** operator-level via `PLATFORM_INFRA_MODE` (or legacy `SYSTEM_MODE`); this entity needs no code change to move between modes, only a redeploy-target change for its own compose block

## 8. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Policy/compliance API | FastAPI router (`src/townhall/`) | in-process |
| Frameworks registry | YAML (`config/townhall/frameworks.yaml`) | in-repo config |
| Board / ITSM / Kanban | CranBania submodule | self-hosted |
| Governance rules | Magna Carta (`src/compliance/`) | in-repo submodule |

## 9. Environment Support Matrix (ESM)

> Grounded against `docker-compose.development.yml`, `docker-compose.uat.yml`, and `docker-compose.production.yml` — checked by exact compose service name, not assumed (see `docs/services/INDEX.md` for current platform-wide compose service totals, which change as the topology evolves).

| Environment | Covered? | What runs | Notes |
|---|---|---|---|
| **Dev** | Partial | the `api` service in `docker-compose.development.yml` runs the `/townhall/*` monolith router — the standalone `cranbania` worker is **not** in this compose file | standalone worker has zero Dev coverage; the in-repo router (`/townhall/status`, `/townhall/policies`, `/townhall/check`) is present and exercisable |
| **UAT** | Partial | same monolith router via `api` in `docker-compose.uat.yml` — the standalone `cranbania` worker is **not** in this compose file either | standalone worker has zero UAT coverage; the in-repo router is present and exercisable |
| **Production** | Yes | both surfaces — full detail in the DSM above | — |

- **Gap:** the standalone `cranbania` worker (CranBania submodule) has **no Dev or UAT environment at all** — the first place it runs is Production. This is the norm for the ~90 standalone workers on this platform, not specific to this entity. The in-repo `/townhall/*` router, however, **is** present in Dev/UAT via the `api` service — corrected 2026-07-11 after review flagged the earlier version of this table for missing that surface entirely.

## 10. Policy (POL)

- Reuses platform policy (`POL-AI-001`, `docs/defstan/`) and Magna Carta runtime rules. Framework
  definitions are config-driven (`frameworks.yaml`), not hard-coded.

## 11. Procedure (PROC)

- **Add a policy check:** implement in `governance.py`, expose via `routes.py` if it needs an HTTP surface;
  register any new framework in `config/townhall/frameworks.yaml`.

## 12. Runbook (RUN)

- **`/townhall/policies` empty:** check the governance store / `frameworks.yaml` loaded (`framework_registry`).
- **Board unreachable at `/townhall` (8071):** that is CranBania (submodule) — check the submodule service,
  not `src/townhall/` (the in-repo router is separate and serves `/townhall/status|policies|check`).

## 13. Standards (STD)

- Framework definitions are config-driven; compliance decisions flow through `src/compliance/middleware.py`.
- In-repo router scope is deliberately minimal; board functionality is owned by CranBania.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-03 | Claude (session) | `src/townhall/routes.py` (3 routes), module docstrings (`agile`/`itsm`/`governance`/`documents`/`rooms`/`framework_registry`), `api.py` mount | In-repo router + modules verified; CranBania submodule explicitly scoped out (not checked out here) |
