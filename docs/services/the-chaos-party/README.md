# Service Doc-Pack — The Chaos Party (Central Testing Platform)

| Field | Value |
|---|---|
| **Entity** | The Chaos Party (`PID-TCP`) — Alice-in-Wonderland themed |
| **Lead AI** | The Mad Hatter (`AID-TCP-01`); Prime: The Doctor (Nikolai O'denhim) |
| **Status** | 🔧 Partial (per `CLAUDE.md` service table) |
| **Code** | `tests/test_chaos.py` (fault-injection suite). A `workers/chaos-party/` worker also exists — see the port note below |

> **Worker port — real inconsistency (flagged, not resolved here).** `workers/chaos-party/worker.py`
> **hardcodes `WORKER_PORT = 8063`** and binds it (`uvicorn.run(..., port=WORKER_PORT)`), **ignoring** the
> compose `PORT=8079` env; the Dockerfile `EXPOSE`s **8065**; while `docker-compose.production.yml`
> (Traefik + `ports`) and `CLAUDE.md` use **8079**. So the app listens on 8063 while deployment routes
> 8079 — a genuine defect (routing would not reach the app). Tracked in issue #188.
| **Gate tier** | Partial → GOV + RACI + TFM + POL + STD + DDD scoped to the suite that exists |

> **Truthfulness:** claims cite `tests/test_chaos.py`. The Chaos Party's in-repo foundation is a
> **fault-injection test suite**, not a running HTTP service — the pack documents what it actually
> exercises. Status owned by the `CLAUDE.md` service table; identity by `PLATFORM_ENTITIES.md`.

## 1. Service Governance Charter (GOV)

- **Mission:** central testing / validation & compliance — deliberately inject failures to verify the
  platform degrades gracefully (resilience proof).
- **Owner (RACI-A):** The Mad Hatter (Lead AI); Prime The Doctor (Nikolai O'denhim).
- **Scope (in-repo):** `pytest` chaos suite covering circuit-breaker, workflow, event-bus, and tool-timeout
  fault paths. The dedicated `chaos-party` worker is the service-form of this capability (see the port
  note above — code binds 8063, deployment expects 8079).

## 2. Detailed Design Document (DDD) — scoped to `tests/test_chaos.py`

The suite deliberately introduces failures and asserts graceful degradation:

| Test class | What it injects / verifies |
|---|---|
| `TestCircuitBreakerChaos` | `CircuitBreaker` opens after the failure threshold; fallback invoked when OPEN; recovers after timeout; `LoopValidator` breaks at its limit |
| `TestWorkflowChaos` | a failing node aborts the workflow (fail-fast); in-flight execution cancellation; concurrent executions stay isolated (no shared-state corruption); cyclic workflow fails gracefully |
| `TestEventBusChaos` | a subscriber error does **not** crash the bus; wildcard subscriber receives all events |
| `TestSparkToolNodeChaos` | a hanging tool is bounded by timeout |

- Run: `pytest tests/test_chaos.py -v` (per `CLAUDE.md`). Uses `caplog` to assert on log signals.

## 3. Technical Architecture Solutions Design (TASD)

- **Style:** black-box + white-box fault injection against real platform primitives (`CircuitBreaker`,
  `WorkflowExecutor`, event bus, `SparkToolNode`) — no mocks of the units under test.
- **Decision:** prove resilience by exercising the *actual* resilience code (the same `CircuitBreaker`
  unified in TASD-001), not by simulating it.

## 4. RACI Matrix

| Activity | The Mad Hatter (Lead) | The Doctor (Prime) | Platform Owner | Owning teams |
|---|---|---|---|---|
| Chaos suite maintenance | **R/A** | C | I | C |
| Resilience regressions triage | **R** | **A** | I | R |

## 5. Solutions Integration Model (SIM)

- **Upstream:** CI runs the suite (`.forgejo/`/GitHub Actions Pytest job) on every change.
- **Downstream:** failures block merges; results feed the platform's quality signal.
- **Targets under test:** `src/resilience`/`src/mesh` circuit breakers, `src/workflow` executor,
  `src/event_bus`, `src/mcp` tool nodes.

## 6. Architecture Scalability Document (ASD)

- **Load model:** a bounded, fast `pytest` suite; not a runtime service.
- **Zero-cost limits & hard stops:** pure `pytest`/asyncio; no paid chaos tooling.
- **Growth path:** the `chaos-party` worker (deployment port 8079; code currently binds 8063 — see the
  port note) can expose chaos runs as a service (out of scope of the
  in-repo suite documented here).

## 7. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Test runner | `pytest` + `pytest-asyncio` | OSS |
| Fault injection | in-test exceptions/timeouts/cancellation | in-process |
| Assertions on behaviour | `caplog` + state checks | in-process |

## 8. Policy (POL)

- Chaos tests must exercise **real** platform primitives (no mocking the unit under test) and assert
  graceful degradation, not just failure. Reuses platform test standards.

## 9. Procedure (PROC)

- **Add a chaos scenario:** add a test to the relevant `Test*Chaos` class, inject a concrete fault
  (exception / timeout / cancellation), and assert the system degrades gracefully (state + log signal).

## 10. Runbook (RUN)

- **A chaos test fails in CI:** a resilience guarantee regressed — inspect which class
  (circuit-breaker / workflow / event-bus / tool-timeout) and treat as a real defect, not flakiness.
- **`test_concurrent_executions_isolated` failing:** historically a `NodeType.OUTPUT` workflow-executor
  issue — verify against the workflow executor, not the chaos harness.

## 11. Standards (STD)

- Deterministic fault injection; assertions on both state and log output; no mocking the SUT.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-03 | Claude (session) | `tests/test_chaos.py` (module docstring + `TestCircuitBreakerChaos`/`TestWorkflowChaos`/`TestEventBusChaos`/`TestSparkToolNodeChaos`) | Test classes and injected fault scenarios verified against the suite |
