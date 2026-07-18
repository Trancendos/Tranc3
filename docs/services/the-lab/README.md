# Service Doc-Pack — The Lab

| Field | Value |
|---|---|
| **ServiceID (CMDB)** | `SRV-LAB-001` |
| **Entity** | The Lab |
| **Lead AI** | The Dr. & Slime |
| **Status** | ✅ In repo (per `CLAUDE.md` service table) — Live tier |
| **Code** | `src/lab/code_lab.py`, `src/lab/routes.py`; router registered in `api.py` (`app.include_router(_lab_router)`, line 843) — **plus two separate standalone workers**: `workers/the-lab/worker.py` (SQLite, sandboxed subprocess code execution, port 8055) and `workers/lab-service/` (SQLite, Ollama/Tabby/HuggingFace/OpenRouter code-model backend, port 8066) |

> **Truthfulness:** claims cite `src/lab/code_lab.py` and `src/lab/routes.py` directly. Status is
> owned by the `CLAUDE.md` service table; identity by `PLATFORM_ENTITIES.md`.
> **Scope note (established pattern, three-way this time):** The Lab has **three independent
> implementations** — the `src/lab/` module mounted into the main `api.py` app (documented below
> in full: an in-memory session/message store with **no AI generation call anywhere in it**),
> `workers/the-lab/worker.py` (a standalone sandboxed-subprocess code-execution service — real
> `python3`/`node`/`bash` execution behind an allowlist and internal-secret auth), and
> `workers/lab-service/` (a standalone worker that talks to Ollama/Tabby/HuggingFace/OpenRouter
> code models — the actual "AI code generation" backend). None of the three call into each other;
> they are entirely separate code paths sharing only the "The Lab" name. This pack documents the
> `src/lab/*` path in full and the other two only at the level needed for the port-defect fix
> below — claims about "no AI generation" refer specifically to `src/lab/*`.
> **Bug found and fixed while authoring this pack:** `workers/lab-service/Dockerfile` hardcoded
> `EXPOSE 8039` / `HEALTHCHECK ... localhost:8039` / `CMD ["uvicorn", ..., "--port", "8039"]`,
> while `docker-compose.production.yml` maps `"8066:8066"` and healthchecks `localhost:8066` for
> this service (compose sets no `LAB_PORT` env var, so `config.py`'s own default was the only
> thing that could have aligned it, and it also defaulted to 8039). Same class of defect as
> `workers/library-service` fixed in the prior pass in this series: the Dockerfile `CMD`'s
> hardcoded `--port` flag wins, so the container actually bound 8039 while compose routed to
> 8066 — meaning the port mapping, Traefik implications, and compose's own healthcheck would all
> have failed. Fixed by changing the Dockerfile's `EXPOSE`/`HEALTHCHECK`/`CMD --port` and
> `config.py`'s `LAB_PORT` default to `8066`. (`workers/the-lab/worker.py`'s compose block, by
> contrast, consistently uses `PORT=8055` everywhere — no defect there.)

## 1. Service Governance Charter (GOV)

- **Mission:** in-platform code creation — a Claude Code-style coding assistant surface for
  session-based, multi-turn code generation, review, and scaffolding tasks.
- **Owner (RACI-A):** The Dr. & Slime; Platform Owner Trancendos.
- **Scope:** `src/lab/*` provides session/message/context-file/artifact CRUD only — it is a
  storage and bookkeeping layer, not a code-generation engine. Actual AI code generation (against
  Ollama/Tabby/HuggingFace/OpenRouter code models) and actual sandboxed code execution live
  entirely in the two separate standalone workers named above, not in this module.

## 2. Detailed Design Document (DDD)

### HTTP surface (`src/lab/routes.py`, prefix `/lab`)

| Method | Route | Backing |
|---|---|---|
| GET | `/lab/status` | `TheLab.stats()` — total sessions, by-status counts |
| POST | `/lab/sessions` | `TheLab.create_session()` — body `{"user_id", "language", "task_type"}`; 400 on unknown `task_type` |
| GET | `/lab/sessions` | `TheLab.list_sessions()` — optional `user_id` filter, most-recent-100 |
| GET | `/lab/sessions/{id}` | `TheLab.get_session()` — 404 `JSONResponse` if not found |
| POST | `/lab/sessions/{id}/messages` | `TheLab.send_message()` — 400 if `content` missing, 404 if session missing/inactive |
| POST | `/lab/sessions/{id}/context` | `TheLab.add_context_file()` — stores a client-supplied `filename`/`content` pair |
| POST | `/lab/sessions/{id}/artifacts` | `TheLab.save_artifact()` — stores a client-supplied `filename`/`content` pair |
| POST | `/lab/sessions/{id}/close` | `TheLab.close_session()` — sets status to `COMPLETE` |
| DELETE | `/lab/sessions/{id}` | `TheLab.delete_session()` — 404 if missing |

### Data model
- `LabSession`: `id` (uuid4), `user_id`, `status` (`LabSessionStatus`: active/paused/complete/
  archived), `language`, `task_type` (`TaskType`: generate/refactor/review/debug/scaffold/test),
  `messages` (`List[LabMessage]`), `context_files` (`Dict[filename, content]`),
  `generated_artifacts` (`Dict[filename, content]`).
- `LabMessage`: `role`, `content`, `timestamp`, `metadata`.

### No AI generation in this module — a real gap, not an oversight
- The module docstring states "Generation delegates to the active inference tier (Tranc3Engine →
  Ollama → OpenRouter → stub) via the Spark MCP or direct engine call," and `TheLab`'s class
  docstring repeats this. **No such call exists anywhere in `src/lab/code_lab.py` or
  `routes.py`.** `send_message()` only appends the given `content` as a stored message and
  returns it verbatim — there is no assistant-generated reply, no call to any inference tier, no
  Spark MCP tool invocation.
- `save_artifact()` / `generated_artifacts` are similarly misnamed: the endpoint stores whatever
  `filename`/`content` the **caller** supplies directly — nothing in this module generates that
  content. A client could call `POST /lab/sessions/{id}/artifacts` with arbitrary text and it
  would be accepted and stored as if it were AI-generated.
- **Conclusion:** `src/lab/*` is a session/message/artifact bookkeeping CRUD layer only. The
  "AI-powered code creation" behavior described in its own comments and this entity's mission
  is implemented, if at all, in the separate `workers/the-lab/` (sandboxed execution) and
  `workers/lab-service/` (AI code-model backend) workers — not here.

### Observatory emission (`_emit()`)
- Fires on session creation and artifact save only (not on message send, context-file add,
  close, or delete).
- Wrapped in a bare `except Exception: pass` (`# nosec B110`) — same graceful-degradation pattern
  as other entities in this series.

## 3. Technical Architecture Solutions Design (TASD)

- **Style (`src/lab/*` API path):** in-process module with a module-level singleton
  (`get_lab()`); in-memory dict storage, no persistence, no external DB, no AI backend call.
- **Decision (implicit, undocumented in code):** the split between bookkeeping (`src/lab/*`),
  execution (`workers/the-lab/`), and generation (`workers/lab-service/`) is not explained
  anywhere in comments or this repo's docs — whether `src/lab/*` is meant to orchestrate calls to
  the other two workers (and simply hasn't been wired up yet) or is an independent, obsolete
  scaffold is unverified. Documented as an honest unknown rather than assumed either way.
- **Fixed defect:** `workers/lab-service/Dockerfile` hardcoded port 8039 while compose routed to
  8066 — see truthfulness header. Fixed by aligning the Dockerfile and `config.py`'s default to
  8066.

## 4. RACI Matrix

| Activity | The Dr. & Slime (Lead) | Platform Owner | Platform Engineering | The Observatory |
|---|---|---|---|---|
| Session/message CRUD changes (`src/lab/*`) | **R** | A | C | I |
| AI generation wiring (connecting `src/lab/*` to `workers/lab-service/`) | C | **A** | **R** | I |
| Sandboxed execution changes (`workers/the-lab/`) | **R** | A | **R** | I |

## 5. Solutions Integration Model (SIM)

- **Upstream:** any caller of `/lab/*` routes — no auth on any route in `src/lab/routes.py`. Both
  standalone workers require `X-Internal-Secret` on their functional routes, but **not** on
  `/health` (both workers) or `/metrics` (`workers/the-lab/worker.py` only) — confirmed via
  `grep` that neither route calls `_auth()`. This is a common, low-risk pattern (health/metrics
  endpoints are typically probe targets, not data-mutating), but the blanket claim "require
  X-Internal-Secret auth" overstated actual coverage and is corrected here.
- **Downstream:** best-effort Observatory `observe()` call on session-create and artifact-save
  only; **no call to any AI inference tier, MCP tool, or the other two Lab workers** — despite
  the module's own docstring describing such delegation.
- **Not integrated:** `src/lab/*`, `workers/the-lab/`, and `workers/lab-service/` do not call
  into each other — three independent implementations under one entity name, per the scope note
  above.

## 6. Architecture Scalability Document (ASD)

- **Load model:** in-memory dict store (`_sessions`), no cap defined — unbounded growth, no
  eviction, unlike The Basement's `MAX_RECORDS` pattern.
- **Bottleneck:** single-process, no persistence; a restart loses all sessions, messages, context
  files, and artifacts stored via `src/lab/*`.
- **Zero-cost limits:** `src/lab/*` has no external dependency; `workers/lab-service/` targets
  free-tier/self-hosted code models (Ollama primary, Tabby/HuggingFace/OpenRouter fallback) per
  its `config.py`.
- **Degradation:** Observatory emission failures don't block the CRUD response.

## 7. Deployment Scope Matrix (DSM)

- **Mode awareness:** No — this entity's own code does not call `PlatformInfraMode` / `src/platform/infrastructure_mode.py`. (Some platform-wide, cross-cutting code *does* branch on the mode — `src/routers/adaptive.py` and `src/routers/ecosystem.py` read/set `PLATFORM_INFRA_MODE`/`SYSTEM_MODE` directly, and `Dimensional/architecture/storage_factory.py` selects a storage provider from `SYSTEM_MODE` — but none of that code is owned by this or any other one of the 43 named entities; it is shared platform infrastructure, not this service's own logic. The Citadel is the only one of the 43 named entities whose own code branches on the mode — see `docs/services/the-citadel/README.md`.) This entity's deployment scope is determined externally — by which `docker-compose.production.yml` service block runs, and where — not by in-process mode detection.
- **Runtime placement:** three surfaces — a router mounted in the `tranc3-backend` monolith (`src/lab/`) plus **two** separate standalone workers: `the-lab` (port 8055, sandboxed execution, **has** a Traefik label) and `lab-service` (port 8066, code generation, **no** Traefik label — internal-only, reached by container DNS name + port) — confirmed as two independently-deployed compose services, not one.
- **Persistence:** monolith side (`src/lab/*`) is an in-memory `dict` store (`_sessions`) with **no persistence of its own** (per this pack's own TFM) — the `tranc3-backend` volume backs *other* entities' state, not this one; `lab-service` has a named volume; `the-lab` (execution sandbox) has **no** volume.

| Setup | What runs, and where | Data locality | Hard blockers / caveats |
|---|---|---|---|
| **Cloud-Only** | all three surfaces run their own compose block on a single cloud host; `the-lab` gets a Traefik route, `lab-service` and the monolith do not (internal-only) | monolith ephemeral (in-memory); `lab-service` volume-backed; `the-lab` execution sandbox ephemeral by design (arguably correct for a sandbox) | no entity-specific blocker beyond the sandbox's inherent statelessness and the monolith router's statelessness |
| **Hybrid** | same three surfaces; per the Hybrid diagram, monolith/`lab-service` data can sync to local TrueNAS | as above, local-syncable where a volume exists | requires `CITADEL_LOCAL_STACK=true` for a local stack alongside the cloud one |
| **Local-Only** | same three surfaces, entirely on local/Citadel hardware | monolith still ephemeral; `lab-service` fully local, volume-backed; `the-lab` sandbox still stateless | none beyond standard local-hardware ops |

- **Zero-cost posture per mode:** Cloud-Only defaults to the `zero_cost_cloud` AI-rotation chain; Hybrid/Local-Only default to `zero_cost_full` (`config/platform/infrastructure_mode.yaml`) — this only affects AI-Gateway-routed calls, not this entity's own logic
- **Switching modes:** operator-level via `PLATFORM_INFRA_MODE` (or legacy `SYSTEM_MODE`); no code change needed for any of the three surfaces.

## 8. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Web framework | FastAPI `APIRouter` | mounted into the main `api.py` app |
| Storage (`src/lab/*`) | in-memory `dict`, no persistence | zero infra cost, no durability |
| Code execution (`workers/the-lab/`) | sandboxed `subprocess` (python3/node/bash allowlist) | self-hosted, port 8055 |
| Code generation (`workers/lab-service/`) | Ollama → Tabby → HuggingFace → OpenRouter fallback | self-hosted-first, free-tier fallback, port 8066 |

## 9. Environment Support Matrix (ESM)

> Grounded against `docker-compose.development.yml`, `docker-compose.uat.yml`, and `docker-compose.production.yml` — checked by exact compose service name, not assumed (see `docs/services/INDEX.md` for current platform-wide compose service totals, which change as the topology evolves).

| Environment | Covered? | What runs | Notes |
|---|---|---|---|
| **Dev** | Partial | the `api` service in `docker-compose.development.yml` runs the monolith router — the two standalone workers, `the-lab` and `lab-service`, are **not** in this compose file | both standalone workers have zero Dev coverage |
| **UAT** | Partial | same monolith router via `api` in `docker-compose.uat.yml` — `the-lab` and `lab-service` are **not** in this compose file either | both standalone workers have zero UAT coverage |
| **Production** | Yes | all three surfaces — full detail in the DSM above | — |

- **Gap:** the two standalone workers, `the-lab` and `lab-service` (per the DSM above), have **no Dev or UAT environment at all** — the first place either runs is Production. This is the norm for the ~90 standalone workers on this platform, not specific to this entity, but worth stating plainly rather than assuming pre-production validation exists where it doesn't.

## 10. Policy (POL)

- No route-level auth on `src/lab/*` routes — see SIM §5. Both standalone workers enforce
  `X-Internal-Secret` auth on their functional routes, but not on `/health`/`/metrics` — see SIM §5.
- Zero-cost mandate: `workers/lab-service/`'s free-tier fallback chain (HuggingFace/OpenRouter)
  must stay within `scripts/zero_cost_audit.py`'s gate per The Citadel's deploy policy.

## 11. Procedure (PROC)

- **Create a session:** `POST /lab/sessions` with `{"language": "python", "task_type":
  "generate"}` — returns a session record; no AI response is generated by this call.
- **Send a message:** `POST /lab/sessions/{id}/messages` with `{"content": "..."}` — stores the
  message only; does not produce an assistant reply (see DDD gap).
- **Run real code:** use `workers/the-lab/`'s execution endpoints directly (internal-secret
  authed) — not reachable via `src/lab/*`.

## 12. Runbook (RUN)

- **`/lab/sessions/{id}/messages` never returns an AI-generated reply:** expected — `src/lab/*`
  has no generation call at all (see DDD). Do not treat this as a broken inference pipeline; it
  is a scope gap in this specific module.
- **`workers/lab-service` unreachable at port 8066:** was a genuine Dockerfile/compose port
  mismatch (container bound 8039, compose routed 8066) — fixed in this pass; confirm the fix is
  present in the deployed image if this recurs.
- **Sessions/messages disappear after a restart:** expected — `src/lab/*` has no persistence.

## 13. Standards (STD)

- Naming: canonical entity name "The Lab" per `CLAUDE.md`/`PLATFORM_ENTITIES.md`; be precise in
  code reviews about which of the three implementations (`src/lab/*`, `workers/the-lab/`,
  `workers/lab-service/`) a change targets — they do not share code or state.
- Any Dockerfile that hardcodes a `--port` CLI flag MUST match the port routed in
  `docker-compose.production.yml` for that service — see The Library's doc-pack (`docs/services/
  the-library/`) for the first instance of this standard; this pack's fix is the second.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-05 | Claude (session) | `src/lab/code_lab.py` (203 lines), `src/lab/routes.py` (111 lines), `api.py` router registration (line 843), `workers/the-lab/worker.py`, `workers/lab-service/` (Dockerfile, config.py), `docker-compose.production.yml` | Confirmed Live-tier, full pack authored. Found and fixed a genuine production defect: `workers/lab-service/Dockerfile` hardcoded port 8039 while compose routed to 8066 (same class of bug as The Library's, fixed in the prior pass). Documented a significant, code-grounded finding: `src/lab/*` has no AI-generation call anywhere despite its own docstring claiming delegation to Tranc3Engine/Ollama/OpenRouter/Spark MCP — it is a pure session/message/artifact CRUD layer; real code generation and execution live in two entirely separate standalone workers that do not call into it. |
| 2026-07-07 | Claude (session, cubic-dev-ai review triage) | `workers/the-lab/worker.py`, `workers/lab-service/main.py`, `.env.example`, `monitoring/prometheus.yml` | Verified and fixed two further cubic findings. (1) Confirmed via `grep` that neither worker's `_auth()` is called on `/health` (both workers) or `/metrics` (`workers/the-lab/worker.py`) — the blanket "both standalone workers require X-Internal-Secret auth" claim overstated coverage; corrected in SIM §5 and POL. (2) The 8039→8066 port fix from the prior pass had not been propagated to `.env.example`'s `LAB_PORT` default or `monitoring/prometheus.yml`'s scrape target — both updated to 8066; `scripts/port_registry_validate.py` re-run and passes. |
