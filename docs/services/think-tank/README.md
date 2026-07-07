# Service Doc-Pack — Think Tank

| Field | Value |
|---|---|
| **Entity** | Think Tank |
| **Lead AI** | Trancendos |
| **Status** | ✅ In repo (per `CLAUDE.md` service table) — Live tier |
| **Code** | `src/quantum/routes.py` (mounted `/thinktank`), `src/quantum/quantum_core.py`, `quantum_engine.py`, `quantum_inference.py`; `src/deepmind/planning.py`, `mcts.py`, `world_model.py`, `gemini_multimodal.py`; router registered in `api.py` (`app.include_router(_thinktank_router)`, line 910) |

> **Truthfulness:** claims cite `src/quantum/routes.py` and `src/deepmind/planning.py` directly,
> plus grep-verified import analysis of the rest of `src/quantum/` and `src/deepmind/`. Status is
> owned by the `CLAUDE.md` service table; identity by `PLATFORM_ENTITIES.md`.
> **Bug found and fixed while authoring this pack:** `POST /thinktank/deepmind/plan` imported
> `from src.deepmind.planning import PlanningEngine` — **no class named `PlanningEngine` exists
> anywhere in this codebase.** `planning.py` defines `BeamSearchPlanner`, `ChainOfThoughtReasoner`,
> and `StrategicPlanner`, none of which are named `PlanningEngine`. This import raised
> `ImportError` on every single call, caught by the route's own `except Exception`, meaning
> **this endpoint always returned an error response, 100% of the time, regardless of input** —
> a genuine, fully-broken endpoint, not a partial degradation. Compounding the bug: even had the
> import succeeded, the code called `engine.plan(problem, depth=depth)` without `await`, and
> `StrategicPlanner`'s real entry point (`plan_action`) is `async def` with a `(goal, state,
> constraints)` signature — `depth` isn't a valid parameter. Fixed by switching to the real
> `StrategicPlanner`/`PlanningConfig` classes, calling `await engine.plan_action(problem,
> state={}, constraints=[])`, and passing `depth` through as `PlanningConfig(horizon=depth)`.
> Verified the fix compiles and lints cleanly; full runtime verification blocked in this session
> by `torch` (a real, declared `requirements.txt` dependency) not being installed in this
> sandbox — `src/deepmind/__init__.py` eagerly imports `world_model.py`, which requires `torch`,
> as a side effect of importing anything from the `deepmind` package at all.
> **Major finding: most of Think Tank's code is orphaned from the live `/thinktank/*` API.** Of
> the ~2,187 lines across `src/quantum/*` and `src/deepmind/*`, only `quantum_simulate()` (uses
> `qiskit`/`qiskit_aer` directly, not `quantum_core.py`) and the now-fixed `deepmind_plan()` (uses
> `planning.py`) are reachable from `routes.py`. `quantum_core.py`, `quantum_engine.py`,
> `quantum_inference.py`, `mcts.py`, `world_model.py`, and `gemini_multimodal.py` (6 of 8 files,
> ~1,740 lines) are referenced only from `src/dependencies.py` (a DI container never imported by
> `api.py`) and `src/main_enhanced.py` (an alternate entrypoint not used by the live app,
> `Makefile`, or any Procfile) — the same "real code, zero live wiring" pattern documented for
> Cryptex earlier in this series.

## 1. Service Governance Charter (GOV)

- **Mission (as coded):** R&D centre merging quantum circuit simulation (Qiskit) and deep-agent
  planning under one HTTP surface. The live `deepmind_plan` route only exercises beam search +
  chain-of-thought reasoning (`StrategicPlanner.plan_action()`); MCTS and world-model planning
  exist as real code (`src/deepmind/mcts.py`, `world_model.py`) but are never called from
  `plan_action()` — `PlanningConfig.mcts_simulations`/`use_world_model` are dead fields. "MCTS-
  guided world-model planning" is therefore not a live capability of this endpoint.
- **Owner (RACI-A):** Trancendos; Platform Owner Trancendos.
- **Scope:** `src/quantum/routes.py`'s three live endpoints only. The bulk of `src/quantum/*` and
  `src/deepmind/*` (quantum_core, quantum_engine, quantum_inference, MCTS, world model, Gemini
  multimodal) exists as real code but is not reachable from the live app — see truthfulness
  header.

## 2. Detailed Design Document (DDD)

### HTTP surface (`src/quantum/routes.py`, prefix `/thinktank`)

| Method | Route | Backing |
|---|---|---|
| GET | `/thinktank/status` | `_quantum_status()`/`_deepmind_status()` — fixed this pass to perform real import checks, see below |
| POST | `/thinktank/quantum/simulate` | Real Qiskit Aer circuit simulation; 503 if qiskit unavailable |
| POST | `/thinktank/deepmind/plan` | `StrategicPlanner.plan_action()` — fixed in this pass, see truthfulness header |

### `/thinktank/status` — fixed: now performs real import checks
- **Fixed this pass.** `_quantum_status()` and `_deepmind_status()` previously wrapped a
  hard-coded return value (`{"quantum_core": "available", ...}`) in a `try/except` whose `try`
  block contained no code that could actually fail — the "degraded" branch was dead code and the
  probe structurally could not detect a real outage. Fixed by having each function attempt a real
  import (`qiskit_aer` for quantum; `src.deepmind.planning.StrategicPlanner` for deepmind) inside
  the `try` block, so a genuinely missing/broken dependency now surfaces as `"degraded"` with the
  real exception message in `note`. Verified in this sandbox (`qiskit_aer` not installed here):
  the endpoint now correctly reports `{"quantum_core": "degraded", "note": "No module named
  'qiskit_aer'"}` instead of falsely claiming "available".

### `/thinktank/quantum/simulate` — real, but `circuit_type` is a dead parameter
- Genuinely builds and runs a Qiskit `QuantumCircuit` via `AerSimulator`, returning real measurement
  counts. `qubits`/`shots` from the request body are honored. **`circuit_type` is documented in the
  route's own docstring (`Body: { qubits, shots, circuit_type }`) but never read from the request
  body or used anywhere in the function** — every call builds the same hard-coded
  Hadamard+CNOT-chain circuit regardless of what `circuit_type` value is sent.

### `/thinktank/deepmind/plan` — fixed in this pass
- See truthfulness header for the full defect and fix. Post-fix, this calls the real
  `StrategicPlanner.plan_action()`, which itself runs `BeamSearchPlanner` and
  `ChainOfThoughtReasoner` concurrently via `asyncio.gather` and fuses their outputs — genuine,
  non-trivial planning logic, now actually reachable.

## 3. Technical Architecture Solutions Design (TASD)

- **Style:** stateless route handlers; `StrategicPlanner` is instantiated fresh per request (no
  module-level singleton, unlike most other entities in this series).
- **Fixed defect:** `PlanningEngine` import — see truthfulness header.
- **Fixed this pass:** the always-"available" health checks in `/thinktank/status` now attempt a
  real qiskit/deepmind import and report failure genuinely — see DDD above.
- **Not fixed:** `circuit_type`'s dead-parameter status — implementing real circuit-type selection
  is a feature addition, not a bug fix, out of scope for this pass.

## 4. RACI Matrix

| Activity | Trancendos (Lead) | Platform Owner | Platform Engineering |
|---|---|---|---|
| `/thinktank/*` route logic changes | **R** | A | C |
| Wiring the 6 orphaned quantum/deepmind modules into a live path (future) | **R** | A | **R** |

## 5. Solutions Integration Model (SIM)

- **Upstream:** any caller of `/thinktank/*` — no auth on any route.
- **Downstream:** `quantum_simulate()` calls real Qiskit Aer; `deepmind_plan()` (post-fix) calls
  real `StrategicPlanner` logic, which transitively depends on `torch` per `src/deepmind/
  __init__.py`'s eager import of `world_model.py`.
- **Not integrated:** `quantum_core.py`, `quantum_engine.py`, `quantum_inference.py`, `mcts.py`,
  `world_model.py` (beyond the transitive import), `gemini_multimodal.py` — none are called from
  `routes.py`; only reachable via a DI container and an alternate entrypoint that the live `api.py`
  app never imports.

## 6. Architecture Scalability Document (ASD)

- **Load model:** stateless per-request; no shared state across calls.
- **Bottleneck:** Qiskit Aer simulation cost scales with `qubits`/`shots`, both caller-controlled
  with no upper bound enforced in `quantum_simulate()` — a potential resource-exhaustion vector
  given no auth exists on the route (flagged, not fixed — a rate-limit/auth decision out of scope
  for this pass).
- **Zero-cost limits:** Qiskit Aer is OSS/local; `StrategicPlanner`'s `torch` dependency runs
  locally, no paid inference API involved per this module's own code.
- **Degradation:** `quantum_simulate()` returns 503 if qiskit isn't installed; `deepmind_plan()`
  (post-fix) returns a structured error via `safe_error_detail()` on any exception, including a
  missing `torch` install.

## 7. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Web framework | FastAPI `APIRouter` | mounted into the main `api.py` app |
| Quantum simulation | Qiskit + Qiskit Aer | OSS, local, zero cost |
| Planning | Beam search + chain-of-thought + (transitively) `torch`-based world model | OSS, local, zero cost |

## 8. Policy (POL)

- No route-level auth on any `/thinktank/*` route — combined with unbounded `qubits`/`shots` on
  the simulate endpoint, this is a real resource-exhaustion exposure worth prioritizing alongside
  the auth gaps found elsewhere in this doc-pack series.
- Zero-cost mandate: both Qiskit and the planning stack run locally with no paid API calls, per
  code inspection in this pass.

## 9. Procedure (PROC)

- **Run a quantum simulation:** `POST /thinktank/quantum/simulate` with `{"qubits": 3, "shots":
  1024}` — `circuit_type` is currently ignored.
- **Generate a plan:** `POST /thinktank/deepmind/plan` with `{"problem": "...", "depth": 3}` —
  now functional post-fix; requires `torch` to be installed in the runtime environment (declared
  in `requirements.txt`).

## 10. Runbook (RUN)

- **`/thinktank/deepmind/plan` always returned an error before this pass:** this was the exact
  bug fixed here (`PlanningEngine` didn't exist) — confirm the fix (import of `StrategicPlanner`/
  `PlanningConfig`, `await`ed `plan_action()` call) is present in the deployed version if this
  recurs.
- **`/thinktank/status` reports "degraded" for `quantum_core`:** expected if `qiskit_aer` isn't
  installed in the running environment — the health check now performs a real import (fixed this
  pass) and will correctly reflect real outages; check the `note` field for the actual exception.
- **`deepmind_plan` fails with `ModuleNotFoundError: No module named 'torch'`:** `torch` is a
  declared `requirements.txt` dependency (`torch==2.12.1`) — ensure it's actually installed in
  the running environment; this is an install/environment issue, not a code defect.

## 11. Standards (STD)

- Naming: canonical entity name "Think Tank" per `CLAUDE.md`/`PLATFORM_ENTITIES.md`.
- Any route wrapping a call in `try/except` for health-check purposes MUST have code inside the
  `try` block capable of actually failing (a real import, connectivity probe, or method call) —
  the always-"available" defect documented here is the reason for this standard.
- Class names referenced in `import` statements MUST be verified to exist before merging — the
  `PlanningEngine` defect (a name that never existed anywhere in the codebase) went undetected
  because the route's own `except Exception` silently absorbed the resulting `ImportError` on
  every call, masking a 100%-broken endpoint as a "sometimes returns an error" one.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-05 | Claude (session) | `src/quantum/routes.py` (101 lines), `src/deepmind/planning.py` (580 lines), grep-verified import analysis of `src/quantum/quantum_core.py`/`quantum_engine.py`/`quantum_inference.py` and `src/deepmind/mcts.py`/`world_model.py`/`gemini_multimodal.py`, `api.py` router registration (line 910) | Confirmed Live-tier, full pack authored. Found and fixed a genuine, fully-broken endpoint: `POST /thinktank/deepmind/plan` imported a class (`PlanningEngine`) that does not exist anywhere in the codebase, so it always errored; fixed by switching to the real `StrategicPlanner`/`PlanningConfig` API with proper `await`. Verified the fix via `py_compile` and `ruff check` (both clean); full runtime verification blocked by `torch` not being installed in this sandbox (a real, declared dependency — not a code issue). Also found: `/thinktank/status`'s health checks structurally cannot detect failure (always report "available"); `circuit_type` is a dead parameter on the simulate endpoint; and 6 of 8 files in `src/quantum/`+`src/deepmind/` are orphaned from the live app, reachable only via an unused DI container and an unused alternate entrypoint. |
| 2026-07-07 | Claude (session, cubic/CodeRabbit review triage) | `src/quantum/routes.py`, `src/deepmind/planning.py` (`mcts_simulations`/`use_world_model` fields, no corresponding usage) | Fixed three findings, all verified by installing dependencies and running the test suite. (1) `/thinktank/status`'s health checks were structurally incapable of detecting failure — fixed by having `_quantum_status()`/`_deepmind_status()` attempt real imports (`qiskit_aer`, `src.deepmind.planning.StrategicPlanner`); confirmed via direct call that a missing `qiskit_aer` now correctly reports `"degraded"` with the real exception in `note`. (2) `deepmind_plan`'s `depth` parameter was unbounded, allowing arbitrarily expensive beam-search/chain-of-thought computation on the request thread — clamped to `[1, 10]`. (3) GOV's mission statement claimed live "MCTS-guided world-model planning"; confirmed via `grep` that `PlanningConfig.mcts_simulations`/`use_world_model` have no reads anywhere in `planning.py` and `plan_action()` never imports `mcts.py`/`world_model.py` — reworded to state only beam search + chain-of-thought are actually live. Also marked the no-mocking end-to-end test with `@pytest.mark.integration` per a CodeRabbit nitpick, separating it from the two mocked unit tests. All 3 tests in `tests/test_thinktank_routes.py` re-run and pass; `ruff check` clean. |
| 2026-07-07 | Claude (session, second cubic pass) | `src/quantum/routes.py`, GOV §1, RACI §4 | Fixed two further findings. (1) `_quantum_status()`/`_deepmind_status()`'s `except` branches returned raw `str(exc)` to unauthenticated callers of `/thinktank/status` — a CWE-209 information-exposure risk (this module already imports `safe_error_detail()` and uses it on every other error path). Switched both to `safe_error_detail(exc, 503)`; updated `tests/test_thinktank_routes.py`'s degraded-path assertions to check for a non-empty sanitized string rather than the exact raw exception text (which `safe_error_detail` no longer returns verbatim). Re-ran all 5 tests — pass. (2) GOV said "two live endpoints" and RACI still listed "Making `/thinktank/status` a real health probe" as a future activity, both stale after the status-probe fix in the entry above — GOV now says "three live endpoints" and the now-completed RACI row was removed. |
