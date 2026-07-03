# Service Doc-Pack — The Town Hall (Governance Hub)

| Field | Value |
|---|---|
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

## 7. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Policy/compliance API | FastAPI router (`src/townhall/`) | in-process |
| Frameworks registry | YAML (`config/townhall/frameworks.yaml`) | in-repo config |
| Board / ITSM / Kanban | CranBania submodule | self-hosted |
| Governance rules | Magna Carta (`src/compliance/`) | in-repo submodule |

## 8. Policy (POL)

- Reuses platform policy (`POL-AI-001`, `docs/defstan/`) and Magna Carta runtime rules. Framework
  definitions are config-driven (`frameworks.yaml`), not hard-coded.

## 9. Procedure (PROC)

- **Add a policy check:** implement in `governance.py`, expose via `routes.py` if it needs an HTTP surface;
  register any new framework in `config/townhall/frameworks.yaml`.

## 10. Runbook (RUN)

- **`/townhall/policies` empty:** check the governance store / `frameworks.yaml` loaded (`framework_registry`).
- **Board unreachable at `/townhall` (8071):** that is CranBania (submodule) — check the submodule service,
  not `src/townhall/` (the in-repo router is separate and serves `/townhall/status|policies|check`).

## 11. Standards (STD)

- Framework definitions are config-driven; compliance decisions flow through `src/compliance/middleware.py`.
- In-repo router scope is deliberately minimal; board functionality is owned by CranBania.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-03 | Claude (session) | `src/townhall/routes.py` (3 routes), module docstrings (`agile`/`itsm`/`governance`/`documents`/`rooms`/`framework_registry`), `api.py` mount | In-repo router + modules verified; CranBania submodule explicitly scoped out (not checked out here) |
