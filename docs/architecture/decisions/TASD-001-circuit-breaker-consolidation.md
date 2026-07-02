# TASD-001 — Circuit Breaker Consolidation

**Type:** Technical Architecture Solutions Design (TASD) / ADR
**Status:** PROPOSED (awaiting Platform Owner + Town Hall sign-off)
**Version:** 1.0.0 | **Owner:** Platform Engineering | **Date:** 2026-07-02
**Governed by:** `docs/framework/DESIGN-GOVERNANCE-FRAMEWORK.md`

---

## 1. Context & Problem

A repo-wide duplication audit found **three independent `circuit_breaker.py` implementations**,
plus **four separate `CircuitState` enum definitions**. This is real logic duplication of a
well-known resilience pattern and a maintenance hazard: a fix or metric added to one breaker
does not propagate to the others, and callers cannot assume a single behaviour contract.

This TASD documents the three implementations truthfully, evaluates consolidation options,
and recommends a **phased, low-risk path** rather than a big-bang merge — because each
implementation is bundled with subsystem-specific companions that are **not** duplication.

> Scope note: this is a design decision, not yet a code change. Per the governance
> framework, an architecturally significant change is documented and approved before code.

## 2. Current State (verified against `main` @ `60b3b18`)

| Implementation | Lines | Public surface | Companions (subsystem-specific) | Consumers |
|----------------|------:|----------------|--------------------------------|-----------|
| `src/mesh/circuit_breaker.py` | 151 | `CircuitBreaker` (`record_success`, `record_failure`, `state` property with auto half-open) | imports state/config from `src/mesh/types.py` (`CircuitState`, `CircuitBreakerConfig`, `CircuitBreakerState`) | `src/mesh/service_mesh.py`, `src/mesh/__init__.py` |
| `src/nanoservices/circuit_breaker/circuit_breaker.py` | 246 | `CircuitBreaker` (`record_success(duration)`, `record_failure(failure_type)`, `execute()`) | `CircuitState`, `FailureType`, `CircuitConfig`, `CircuitMetrics`, **`CircuitBreakerMesh`** | internal to nanoservices |
| `src/resilience/circuit_breaker.py` | 225 | `CircuitBreaker` (`record_success`, `record_failure`, **async `call()`**) | `CircuitState`, `CircuitBreakerConfig`, **`Bulkhead`**, **`ResilienceManager`**, `resilience` singleton | `src/gateway/adaptive_proxy.py` |

**`CircuitState` enum is defined in four places** (all agree on the values
`CLOSED="closed"`, `OPEN="open"`, `HALF_OPEN="half_open"`):
`src/mesh/types.py`, `src/nanoservices/circuit_breaker/circuit_breaker.py`,
`src/resilience/circuit_breaker.py`, `src/validation/loop_validator.py`.

### What is genuinely shared vs genuinely distinct

- **Shared (true duplication):** the three-state machine (CLOSED/OPEN/HALF_OPEN), the
  `failure_threshold` / `success_threshold` / timeout config knobs, and `record_success` /
  `record_failure` transition logic. The `CircuitState` enum is duplicated 4×.
- **Distinct (NOT duplication — keep):** `CircuitBreakerMesh` (nanoservices multi-breaker
  registry), `Bulkhead` + `ResilienceManager` (resilience concurrency isolation), the mesh
  breaker's Pydantic `CircuitBreakerState` model, and the differing call surfaces
  (sync `execute()` vs async `call()` vs record-only).

## 3. Options

### Option A — Do nothing
- ➕ Zero risk.
- ➖ Duplication persists; divergence continues; 4× enum drift risk.

### Option B — Big-bang merge into one `CircuitBreaker`
- ➕ Single implementation.
- ➖ **High risk.** Requires unifying 3 config schemas + 3 call surfaces and rewiring
  `service_mesh.py`, `adaptive_proxy.py`, and nanoservices simultaneously. Behavioural
  regressions likely; hard to review. Rejected.

### Option C — Phased consolidation on a shared core (RECOMMENDED)
Extract only what is truly shared; leave subsystem companions in place.
- **Phase 1 (low-risk, mechanical):** create one canonical `CircuitState` enum + a
  `CircuitBreakerConfig` dataclass in a single module (proposed: `src/resilience/` as the
  canonical home, since it already owns the richest resilience surface and an external
  consumer). The other three modules **re-export** it (shim pattern already used for
  `shared_core → Dimensional`). No behaviour change; enum identity unified.
- **Phase 2 (core state machine):** extract the CLOSED/OPEN/HALF_OPEN transition logic into
  a `_CircuitCore` mixin/base in the canonical module. Each subsystem breaker composes it and
  keeps its own call surface (`execute` / `call` / record-only) and companions.
- **Phase 3 (consumer migration):** migrate `service_mesh.py` and `adaptive_proxy.py` to the
  shared core behind their existing public APIs; delete now-empty duplicates.

Each phase is independently reviewable, test-gated, and revertible.

## 4. Decision (proposed)

Adopt **Option C**. Proceed with **Phase 1 only** under this PR's approval; Phases 2–3 are
separate change requests once Phase 1 is merged and soak-tested.

Rationale: unifies the one unambiguous duplication (the `CircuitState` enum, 4× → 1×) with
near-zero risk, establishes the canonical home, and preserves the subsystem-specific
companions that are legitimately distinct. It avoids the regression risk of Option B while
still stopping the drift Option A allows.

## 5. Consequences

- **Positive:** single source of truth for circuit states; future fixes to the core state
  machine propagate; reduced cognitive load; a documented home for resilience primitives.
- **Negative / cost:** re-export shims add one indirection; Phases 2–3 require careful
  consumer migration with test coverage before the duplicates can be deleted.
- **Risk controls:** each phase behind existing tests (`tests/` resilience/mesh suites);
  no public API of `ServiceMesh` or `adaptive_proxy` changes; canonical enum values are
  already identical across all four definitions, so Phase 1 is value-preserving.

## 6. Verification & Rollout

- **Phase 1 acceptance:** all four `CircuitState` usages resolve to the canonical enum;
  `import` graph shows no remaining independent enum definitions; existing tests green.
- **Automation (future):** a lint check asserting only one `class CircuitState` definition
  exists outside the canonical module (mirrors the entity-name lint pattern).
- **RACI:** Platform Eng (R) authors each phase; Platform Owner (A) approves; Town Hall (C)
  gates; SRE (I). Per `docs/framework/DESIGN-GOVERNANCE-FRAMEWORK.md` §3.

## 7. References

- `src/mesh/circuit_breaker.py`, `src/mesh/types.py`, `src/mesh/service_mesh.py`
- `src/nanoservices/circuit_breaker/circuit_breaker.py`
- `src/resilience/circuit_breaker.py`, `src/gateway/adaptive_proxy.py`
- `src/validation/loop_validator.py`
- `docs/framework/DESIGN-GOVERNANCE-FRAMEWORK.md`

## 8. Review History

| Date | Reviewer | Action |
|------|----------|--------|
| 2026-07-02 | Platform Engineering | Initial TASD — 3-implementation audit, options, phased recommendation (Option C, Phase 1) |
