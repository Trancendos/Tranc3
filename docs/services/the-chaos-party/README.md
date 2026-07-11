# Service Doc-Pack — The Chaos Party (Central Testing Platform)

| Field | Value |
|---|---|
| **Entity** | The Chaos Party (`PID-TCP`) — Alice-in-Wonderland themed |
| **Lead AI** | The Mad Hatter (`AID-TCP-01`); Prime: The Doctor (Nikolai O'denhim) |
| **Status** | 🔧 Partial (per `CLAUDE.md` service table) |
| **Code** | `tests/test_chaos.py` (fault-injection suite) **and** a real, deployable standalone worker, `workers/chaos-party/worker.py` (SQLite-backed test-suite/chaos-experiment tracking API, port 8079) |

> **Worker port defect — resolved, and a second defect found and fixed in this pass.** The prior
> version of this note (2026-07-03) flagged `workers/chaos-party/worker.py` for hardcoding
> `WORKER_PORT = 8063` and ignoring the compose `PORT=8079` env. That was true at the time but is
> **now stale** — commit `a5c74c8` ("honor PORT env in 36 workers") already fixed this across the
> platform; `worker.py` now correctly reads `int(os.getenv("PORT") or "8063")`. Separately, this
> pass found and fixed a **second, independent** defect in the same class as The Academy/The
> Basement/The Studio: the Dockerfile only `COPY`'d a placeholder `main.py` (zero storage, always
> returns empty/404 responses) while this real, SQLite-backed, auth-gated `worker.py` sat unused in
> the same directory. Fixed — the Dockerfile now builds and runs `worker.py`, with a named volume
> added. Issue #188 can be considered closed for this entity.
| **Gate tier** | Partial → GOV + RACI + TFM + DSM + POL + STD + DDD scoped to the suite that exists |

> **Truthfulness:** claims cite `tests/test_chaos.py`. The Chaos Party's in-repo foundation is a
> **fault-injection test suite**, not a running HTTP service — the pack documents what it actually
> exercises. Status owned by the `CLAUDE.md` service table; identity by `PLATFORM_ENTITIES.md`.

## 1. Service Governance Charter (GOV)

- **Mission:** central testing / validation & compliance — deliberately inject failures to verify the
  platform degrades gracefully (resilience proof).
- **Owner (RACI-A):** The Mad Hatter (Lead AI); Prime The Doctor (Nikolai O'denhim).
- **Scope (in-repo):** `pytest` chaos suite covering circuit-breaker, workflow, event-bus, and tool-timeout
  fault paths, **plus** a real deployed worker (`workers/chaos-party/`) that tracks test suites, test
  runs, and chaos experiments over a SQLite-backed, auth-gated HTTP API — this is a genuine second
  capability, not just "the service-form" of the pytest suite; the two are separate code paths that
  happen to share a theme.

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
- **Growth path:** already realized, not just planned — the `chaos-party` worker (port 8079) already
  exposes chaos-experiment tracking as a real, deployed service (see the DSM below); it is out of
  scope of the `pytest` suite documented in this ASD/DDD, which covers only `tests/test_chaos.py`.

## 7. Deployment Scope Matrix (DSM)

- **Mode awareness:** No — this entity's own code does not call `PlatformInfraMode` / `src/platform/infrastructure_mode.py`. (Some platform-wide, cross-cutting code *does* branch on the mode — `src/routers/adaptive.py` and `src/routers/ecosystem.py` read/set `PLATFORM_INFRA_MODE`/`SYSTEM_MODE` directly, and `Dimensional/architecture/storage_factory.py` selects a storage provider from `SYSTEM_MODE` — but none of that code is owned by this or any other one of the 43 named entities; it is shared platform infrastructure, not this service's own logic. The Citadel is the only one of the 43 named entities whose own code branches on the mode — see `docs/services/the-citadel/README.md`.) This entity's deployment scope is determined externally — by which `docker-compose.production.yml` service block runs, and where — not by in-process mode detection.
- **Runtime placement:** **two genuinely separate things, previously conflated in this DSM.** (1) `tests/test_chaos.py` is a test suite executed by CI (Forgejo runner, per `CLAUDE.md`'s "All CI/CD runs through Forgejo — NO GitHub Actions"), not a long-running service. (2) `workers/chaos-party/` **is** a real, deployable standalone worker with its own `docker-compose.production.yml` service block (`chaos-party`, port 8079) and its own Traefik route (`PathPrefix(/chaos-party)`) — the earlier version of this DSM incorrectly said no compose block exists for this entity at all. **Its Dockerfile previously only `COPY`'d a placeholder `main.py`** (the same deployed-stub-vs-undeployed-real defect found for The Academy/The Basement/The Studio) — **fixed**: it now builds and runs the real, SQLite-backed `worker.py`, with a named volume (`chaos-party-data:/app/data`) added.
- **Persistence:** the `pytest` suite is stateless (results go to `logs/test_results.jsonl` on whatever runner executes it, not a dedicated volume for this entity). The **separate** `chaos-party` worker now has genuine SQLite persistence backed by a named volume, surviving redeploys in every mode.

| Setup | What runs, and where | Data locality | Hard blockers / caveats |
|---|---|---|---|
| **Cloud-Only** | the `pytest` suite runs on a Forgejo CI runner hosted on a cloud VM (see The Workshop's own DSM); separately, the `chaos-party` worker's compose block runs on a single cloud host, now running the real `worker.py` | CI output n/a; worker persists via its attached volume as long as the disk is preserved | worker: none beyond standard single-host durability; suite: depends entirely on The Workshop's Cloud-Only deployment |
| **Hybrid** | suite runs on whichever Forgejo runner (cloud or local) picks up the job; worker runs as a single instance (cloud or local host) | worker's SQLite volume local-syncable per `docs/architecture/infrastructure-modes.md`'s Hybrid diagram | requires `CITADEL_LOCAL_STACK=true` if a local compose stack should run alongside the cloud one |
| **Local-Only** | suite runs on a local Forgejo runner; worker runs entirely on local/Citadel hardware behind local Traefik | worker fully local, volume-backed | none beyond standard local-hardware ops |

- **Zero-cost posture per mode:** the `pytest` suite has no AI-Gateway or paid-dependency exposure; the `chaos-party` worker's zero-cost posture follows the platform-wide `zero_cost_cloud`/`zero_cost_full` split (`config/platform/infrastructure_mode.yaml`).
- **Switching modes:** the suite inherits whatever mode The Workshop's CI runners are deployed under; the `chaos-party` worker needs no code change to move between modes, only a redeploy-target change for its own compose block.

## 8. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Test runner | `pytest` + `pytest-asyncio` | OSS |
| Fault injection | in-test exceptions/timeouts/cancellation | in-process |
| Assertions on behaviour | `caplog` + state checks | in-process |

## 9. Policy (POL)

- Chaos tests must exercise **real** platform primitives (no mocking the unit under test) and assert
  graceful degradation, not just failure. Reuses platform test standards.

## 10. Procedure (PROC)

- **Add a chaos scenario:** add a test to the relevant `Test*Chaos` class, inject a concrete fault
  (exception / timeout / cancellation), and assert the system degrades gracefully (state + log signal).

## 11. Runbook (RUN)

- **A chaos test fails in CI:** a resilience guarantee regressed — inspect which class
  (circuit-breaker / workflow / event-bus / tool-timeout) and treat as a real defect, not flakiness.
- **`test_concurrent_executions_isolated` failing:** historically a `NodeType.OUTPUT` workflow-executor
  issue — verify against the workflow executor, not the chaos harness.

## 12. Standards (STD)

- Deterministic fault injection; assertions on both state and log output; no mocking the SUT.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-03 | Claude (session) | `tests/test_chaos.py` (module docstring + `TestCircuitBreakerChaos`/`TestWorkflowChaos`/`TestEventBusChaos`/`TestSparkToolNodeChaos`) | Test classes and injected fault scenarios verified against the suite |
| 2026-07-11 | Claude (session, DSM/implementation pass) | `workers/chaos-party/worker.py`, `Dockerfile`, `docker-compose.production.yml` | Major correction: this pack previously claimed The Chaos Party "is not a deployable service" — false. `workers/chaos-party/` has a real `docker-compose.production.yml` service block, Traefik route, and a genuine SQLite-backed test-suite/chaos-experiment tracking API (`worker.py`, auth-gated). Also found the port-hardcode defect this pack had flagged (2026-07-03) as "not resolved" was actually already fixed platform-wide by commit `a5c74c8` — stale documentation, not a live bug. Separately found and fixed a genuinely new defect: the Dockerfile only `COPY`'d a placeholder `main.py` (zero storage) instead of the real `worker.py` — same class as The Academy/The Basement/The Studio. Fixed the Dockerfile and added a named volume. GOV, ASD, and DSM sections rewritten to describe both the `pytest` suite and the worker as two separate, both-real capabilities. |
