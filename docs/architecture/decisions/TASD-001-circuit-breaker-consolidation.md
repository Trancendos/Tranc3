# TASD-001 — Circuit Breaker Consolidation

**Type:** Technical Architecture Solutions Design (TASD) / ADR
**Status:** PROPOSED (awaiting Platform Owner + The Town Hall sign-off)
**Version:** 1.0.0 | **Owner:** Platform Engineering | **Date:** 2026-07-02
**Governed by:** `docs/framework/DESIGN-GOVERNANCE-FRAMEWORK.md` (introduced in PR #185, pending
merge to `main`; until then the operative change gate is
`docs/procedures/PROC-CHG-001-Change-Request.md`)

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

## 4. Decision (proposed)

Adopt **Option C**. Proceed with **Phase 1 only** under this PR's approval; Phases 2–3 are
separate change requests once Phase 1 is merged and soak-tested.

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
  string usage after the mesh value migration; existing tests green.
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
- `docs/framework/DESIGN-GOVERNANCE-FRAMEWORK.md`

## 8. Review History

| Date | Reviewer | Action |
|------|----------|--------|
| 2026-07-02 | Platform Engineering | Initial TASD — 3-implementation audit, options, phased recommendation (Option C, Phase 1) |
| 2026-07-02 | Platform Engineering (review response) | Corrected the CircuitState claim: the four definitions differ in base type and in `HALF_OPEN` value (mesh `"half-open"`); documented config-schema incompatibility (Pydantic/ms vs dataclass/s); narrowed Phase 1 to enum-only with an explicit value-migration decision (not a pure no-op); added §3.1 canonical-home justification + concrete shim pattern. |
| 2026-07-02 | Platform Engineering (review response) | Canonical name "The Town Hall"; scoped the proposed lint to the circuit-breaker surface (unrelated `CircuitState` types exist in `Dimensional/*`); noted the governance framework is introduced in PR #185 (pending merge), with `PROC-CHG-001` as the interim change gate. |
