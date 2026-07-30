# TASD-001 — Circuit Breaker Consolidation

**Type:** Technical Architecture Solutions Design (TASD) / ADR
**Status:** Phase 1 + Phase 2 MERGED (Platform Owner sign-off via direct approval, 2026-07-30) — Phase 3 remains PROPOSED
**Version:** 1.1.0 | **Owner:** Platform Engineering | **Date:** 2026-07-02 (Phase 2 addendum: 2026-07-30)
**Governed by:** `docs/framework/DESIGN-GOVERNANCE-FRAMEWORK.md` (introduced in PR #185, pending
merge to `main`; until then the operative change gate is
`docs/procedures/PROC-CHG-001-Change-Request.md`)

---

## 1. Context & Problem

> **Correction (2026-07-30):** the original audit undercounted by one. There are **four**
> independent `CircuitBreaker` classes, not three — §2's table below only listed
> `src/mesh/`, `src/nanoservices/`, and `src/resilience/circuit_breaker.py` as breaker
> implementations, but `src/validation/loop_validator.py`'s `CircuitBreaker` dataclass is a
> fourth, genuinely independent one (it was discussed extensively in the `CircuitState` enum
> table below, but never added as its own row in the implementation table). All four are
> covered by Phase 1 and Phase 2 (see addendum, §3.2).

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
| `src/validation/loop_validator.py` (added to this table 2026-07-30 — see correction above) | 271 (whole module) | `CircuitBreaker` (dataclass, sync `call()`/async `async_call()`, `record_success`/`record_failure` internal via `_on_success`/`_on_failure`) | `LoopValidator`, `SelfHealer`, `with_retry`, module-level `CIRCUITS` dict of 7 pre-configured breakers | `api.py`, evolution/consciousness/swarm subsystems |

**`CircuitState` is defined in four places, and they do NOT all agree** — the
definitions differ in both base type and one value (verified against `main`):

| Location | Base type | `HALF_OPEN` value | Note |
|----------|-----------|-------------------|------|
| `src/mesh/types.py` | `str, enum.Enum` | **`"half-open"` (hyphen)** | value differs from the others |
| `src/nanoservices/circuit_breaker/circuit_breaker.py` | `Enum` (**not** `str`) | `"half_open"` | not a `str` enum |
| `src/resilience/circuit_breaker.py` | `str, Enum` | `"half_open"` | |
| `src/validation/loop_validator.py` | **plain class** (not an `Enum`) | `"half_open"` | class constants |

`CLOSED="closed"` and `OPEN="open"` are consistent across all four; only `HALF_OPEN`
diverges (mesh uses a hyphen). **This means unifying the enum is NOT purely
value-preserving** — mesh's serialized `"half-open"` would change unless explicitly
preserved or migrated. (Credit: caught in review; an earlier draft of this TASD
incorrectly claimed all four agreed on values and types.)

**The config schemas are also mutually incompatible** (not just cosmetically):

| Location | Type | Timeout field / unit | Distinct fields |
|----------|------|----------------------|-----------------|
| `src/mesh/types.py` `CircuitBreakerConfig` | **Pydantic `BaseModel`** (frozen) | `reset_timeout_ms` (**ms**) | `half_open_request_percentage`, `request_timeout_ms` |
| `src/resilience/…` `CircuitBreakerConfig` | dataclass | `recovery_timeout` (**seconds**) | `half_open_max_calls`, `success_threshold` |
| `src/nanoservices/…` `CircuitConfig` | dataclass | `timeout_seconds` (**seconds**) | `window_seconds`, `slow_call_duration_seconds`, `slow_call_rate_threshold` |

### What is genuinely shared vs genuinely distinct

- **Shared (true duplication):** the three-state machine (CLOSED/OPEN/HALF_OPEN) and the
  `record_success` / `record_failure` transition logic. The `CircuitState` **concept** is
  duplicated 4× (though with the value/type differences noted above).
- **Distinct (NOT duplication — keep):** `CircuitBreakerMesh` (nanoservices multi-breaker
  registry), `Bulkhead` + `ResilienceManager` (resilience concurrency isolation), the mesh
  breaker's Pydantic `CircuitBreakerState` model, the differing call surfaces
  (sync `execute()` vs async `call()` vs record-only), and — importantly — the **config
  classes**, which have incompatible fields, units (ms vs s), and base types (Pydantic vs
  dataclass) and must NOT be naively merged.

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
- **Phase 1 (enum only — low-risk but NOT purely mechanical):** create one canonical
  `CircuitState` (a `str, Enum`) in a single module (proposed: `src/resilience/` as the
  canonical home — see §3.1). The other three modules **re-export** it (shim pattern used
  for `shared_core → Dimensional`). **`CircuitBreakerConfig` is explicitly out of scope for
  Phase 1** — the three config schemas have incompatible fields, units (ms vs s), and base
  types (Pydantic vs dataclass) and require an adapter, deferred to a later phase.
  - **Value-migration decision required:** mesh's `HALF_OPEN="half-open"` differs from the
    canonical `"half_open"`. Phase 1 must either (a) canonicalize to `"half_open"` and update
    mesh + any persisted/serialized consumers of the old value in the same change (preferred,
    with a grep for `"half-open"` string usage first), or (b) keep mesh's re-export aliased
    to preserve its wire value. Option (a) is recommended but makes Phase 1 a small
    *behavioural* change, not a no-op — it must be test-gated, not assumed value-preserving.
  - `src/validation/loop_validator.py`'s `CircuitState` is a plain class (not an `Enum`);
    converting it to re-export the enum is a minor but real change and is included in Phase 1.
- **Phase 2 (core state machine):** extract the CLOSED/OPEN/HALF_OPEN transition logic into
  a `_CircuitCore` mixin/base in the canonical module. Each subsystem breaker composes it and
  keeps its own call surface (`execute` / `call` / record-only) and companions.
- **Phase 3 (consumer migration):** migrate `service_mesh.py` and `adaptive_proxy.py` to the
  shared core behind their existing public APIs; delete now-empty duplicates.

Each phase is independently reviewable, test-gated, and revertible.

### 3.1 Canonical home & concrete shim pattern

**Why `src/resilience/`** (over `src/mesh/` or `src/nanoservices/`): it already owns the
broadest resilience surface (`Bulkhead`, `ResilienceManager`, the `resilience` singleton) and
the only *cross-package* external consumer (`src/gateway/adaptive_proxy.py`). Dependency
direction favours it as the leaf primitive: mesh and nanoservices are subsystem layers that
may depend on a shared resilience primitive, but resilience should not depend on them.
(If the org prefers strict subsystem-neutrality, an alternative is a dedicated
`src/resilience/primitives.py` or a `shared_core`-style home — noted as a variant, but the
re-export strategy is identical either way.)

**Concrete Phase 1 shape** (illustrative, subject to the value-migration decision above):

```python
# src/resilience/circuit_state.py  (canonical)
from enum import Enum
class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"   # canonicalized (mesh migrates off "half-open")

# src/mesh/types.py            → from src.resilience.circuit_state import CircuitState  # noqa: F401
# src/nanoservices/…           → from src.resilience.circuit_state import CircuitState  # noqa: F401
# src/validation/loop_validator.py → from src.resilience.circuit_state import CircuitState  # noqa: F401
```

To avoid a circular import, the canonical enum lives in its own tiny module
(`circuit_state.py`), imported by `src/resilience/circuit_breaker.py` rather than defined in
it — so mesh/nanoservices re-exporting it never pull in the full resilience breaker.

### 3.2 Phase 2 addendum (2026-07-30) — what was actually extracted

Phase 2 was scoped, on inspection, more narrowly than §3's illustrative `_CircuitCore`
mixin implied. Reading all four implementations end-to-end (not just their public
surface) showed their half-open **admission** strategies are genuinely different —
mesh admits a random percentage of requests, nanoservices and resilience/loop_validator
gate on a fixed half-open call count, and nanoservices additionally trips on a
sliding-window slow-call rate the other three don't have at all. Forcing those into one
shared state object would either require touching the config schemas (explicitly
deferred, see §2) or silently changing behaviour — exactly what §3 Option B was
rejected for.

What genuinely is identical across all four, byte-for-byte, once read carefully:

1. **The "has an OPEN circuit waited long enough to probe recovery" comparison** —
   every implementation does `elapsed >= timeout` (loop_validator alone used strict
   `>`; harmonised to `>=` to match the majority, a bounded behavioural change of the
   same kind Phase 1 made for mesh's `"half-open"` value).
2. **The structured "state transition occurred" log line** — mesh's version
   (`logger.info("circuit_breaker_state_transition", extra={...})`) was already the
   most Observatory-friendly shape; the other three had their own richer per-transition
   messages (failure counts, etc.), so the shared log call was added **additively**
   alongside each subsystem's existing message rather than replacing it.

Implemented as `src/resilience/circuit_core.py` (`should_recover()`,
`log_circuit_transition()`) — a tiny module, not a class, kept separate from
`circuit_breaker.py` for the same circular-import reason `circuit_state.py` is. All
four breakers (`src/mesh/circuit_breaker.py`, `src/resilience/circuit_breaker.py`,
`src/nanoservices/circuit_breaker/circuit_breaker.py`,
`src/validation/loop_validator.py`) now call it. Success/failure counting semantics,
half-open admission strategy, config schema, and public call surface are **unchanged**
in all four — verified by the full existing test suites for each
(`tests/test_mesh.py`, `tests/test_service_mesh_advanced.py`, `tests/test_resilience.py`,
`tests/test_worker_mesh_integration.py`, `tests/test_chaos.py`, `tests/test_full_suite.py`)
passing unmodified, plus new coverage in `tests/test_circuit_core.py`.

A genuine `_CircuitCore` mixin holding shared *state* (not just shared *functions*)
remains out of scope pending a decision on whether to unify the config schemas first —
that would be Phase 3, and is not attempted here.

## 4. Decision

Adopted **Option C**, Phases 1 and 2. Phase 3 (consumer migration — deleting the
duplicate classes entirely behind a unified config) remains a separate, future change
request per the original plan below.

Rationale: unifies the `CircuitState` concept (4× → 1×), establishes the canonical home, and
preserves the subsystem-specific companions and config classes that are legitimately distinct.
It avoids the regression risk of Option B while still stopping the drift Option A allows.
Phase 1 is small but — because of the mesh `"half-open"` value — carries a bounded, test-gated
behavioural change rather than being a pure no-op.

## 5. Consequences

- **Positive:** single source of truth for circuit states; future fixes to the core state
  machine propagate; reduced cognitive load; a documented home for resilience primitives.
- **Negative / cost:** re-export shims add one indirection; the mesh `"half-open"` → `"half_open"`
  migration must sweep any string comparisons/serialization of the old value; config unification
  is deferred and Phases 2–3 require careful consumer migration with test coverage before the
  duplicates can be deleted.
- **Risk controls:** each phase behind existing tests (`tests/` resilience/mesh suites); no
  public API changes to `ServiceMesh` or `adaptive_proxy`. Phase 1 is **not** assumed
  value-preserving — the mesh `HALF_OPEN` value change is treated as a behavioural change,
  gated by a pre-change grep for `"half-open"` usages and green tests. `CircuitBreakerConfig`
  is untouched in Phase 1, so no config-schema/Pydantic breakage.

## 6. Verification & Rollout

- **Phase 1 acceptance:** all four `CircuitState` usages resolve to the canonical enum
  (`loop_validator`'s plain class replaced by a re-export); `import` graph shows no remaining
  independent enum definitions; a repo-wide grep confirms no lingering `"half-open"` (hyphen)
  string usage after the mesh value migration; existing tests green. **Done** (verified
  present in `src/resilience/circuit_state.py` and all four re-exports, 2026-07-30).
- **Phase 2 acceptance:** all four breakers call `should_recover()` for their OPEN→HALF_OPEN
  timeout check and `log_circuit_transition()` on every state change; no change to any
  breaker's public method signatures, config schema, or half-open admission strategy; full
  existing test suites for all four subsystems pass unmodified; new
  `tests/test_circuit_core.py` covers the shared module directly. **Done** (2026-07-30).
- **Automation (future):** a lint check asserting no duplicate `CircuitState` definition
  exists **within the circuit-breaker consolidation surface** — scoped to
  `src/mesh/`, `src/resilience/`, `src/nanoservices/`, `src/validation/` (or keyed off the
  canonical import path). It must **not** be a global `class CircuitState` check: unrelated
  `CircuitState` types exist elsewhere (e.g. `Dimensional/orchestration/health_monitor.py`,
  `Dimensional/infinity/sentinel_station.py`, `Dimensional/architecture/oci_adaptive_provider.py`)
  and are out of scope for this consolidation.
- **RACI:** Platform Eng (R) authors each phase; Platform Owner (A) approves; The Town Hall (C)
  gates; SRE (I). Per `docs/framework/DESIGN-GOVERNANCE-FRAMEWORK.md` §3.

## 7. References

- `src/mesh/circuit_breaker.py`, `src/mesh/types.py`, `src/mesh/service_mesh.py`
- `src/nanoservices/circuit_breaker/circuit_breaker.py`
- `src/resilience/circuit_breaker.py`, `src/gateway/adaptive_proxy.py`
- `src/validation/loop_validator.py`
- `src/resilience/circuit_state.py` (Phase 1), `src/resilience/circuit_core.py` (Phase 2)
- `tests/test_circuit_core.py`
- `docs/framework/DESIGN-GOVERNANCE-FRAMEWORK.md`

## 8. Review History

| Date | Reviewer | Action |
|------|----------|--------|
| 2026-07-02 | Platform Engineering | Initial TASD — 3-implementation audit, options, phased recommendation (Option C, Phase 1) |
| 2026-07-02 | Platform Engineering (review response) | Corrected the CircuitState claim: the four definitions differ in base type and in `HALF_OPEN` value (mesh `"half-open"`); documented config-schema incompatibility (Pydantic/ms vs dataclass/s); narrowed Phase 1 to enum-only with an explicit value-migration decision (not a pure no-op); added §3.1 canonical-home justification + concrete shim pattern. |
| 2026-07-02 | Platform Engineering (review response) | Canonical name "The Town Hall"; scoped the proposed lint to the circuit-breaker surface (unrelated `CircuitState` types exist in `Dimensional/*`); noted the governance framework is introduced in PR #185 (pending merge), with `PROC-CHG-001` as the interim change gate. |
| 2026-07-30 | Platform Engineering | Corrected the implementation count to 4 (§1); executed Phase 2 per direct Platform Owner approval — added §3.2 addendum documenting the narrower-than-planned safe extraction (`should_recover()` + `log_circuit_transition()` in `src/resilience/circuit_core.py`), wired into all four breakers, verified against full existing test suites plus new `tests/test_circuit_core.py`. Phase 3 (config unification + duplicate deletion) remains future work. |
