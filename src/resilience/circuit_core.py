# src/resilience/circuit_core.py
# Circuit Breaker Core — shared transition primitives (TASD-001 Phase 2).
#
# Four independent CircuitBreaker classes exist (src/mesh/circuit_breaker.py,
# src/resilience/circuit_breaker.py, src/nanoservices/circuit_breaker/circuit_breaker.py,
# src/validation/loop_validator.py). TASD-001 Phase 1 already unified their CircuitState
# enum (src/resilience/circuit_state.py). This module extracts the one piece of logic
# that is genuinely identical across all four: the "has an OPEN circuit waited long
# enough to probe recovery" check, and a canonical structured log line for state
# transitions. Each subsystem's failure/success counting semantics, half-open admission
# strategy (random-% vs fixed-call-count vs sliding-window), and config schema remain
# genuinely distinct per TASD-001 §2 and are deliberately NOT touched here — config-schema
# unification is explicitly deferred to a later phase, not this one.
#
# Kept in its own tiny module (not circuit_breaker.py) for the same reason
# circuit_state.py is: any of the four subsystems can import it without pulling in
# src/resilience/circuit_breaker.py's Bulkhead/ResilienceManager machinery.

from __future__ import annotations

import logging

from src.resilience.circuit_state import CircuitState

logger = logging.getLogger("tranc3.resilience.circuit_core")


def should_recover(elapsed_seconds: float, recovery_timeout_seconds: float) -> bool:
    """True once an OPEN circuit has waited at least `recovery_timeout_seconds`.

    Units are the caller's responsibility — pass both arguments in the same unit
    (seconds, ms, etc.) and the comparison is unit-invariant.
    """
    return elapsed_seconds >= recovery_timeout_seconds


def log_circuit_transition(
    service_name: str, old_state: CircuitState, new_state: CircuitState
) -> None:
    """Canonical structured log line for a circuit breaker state transition.

    Additive alongside each subsystem's own (often more detailed, e.g. failure counts)
    logging — this does not replace subsystem-specific messages, it gives The
    Observatory/any log consumer one consistent event name and shape across all four
    breakers.
    """
    old_value = old_state.value if hasattr(old_state, "value") else str(old_state)
    new_value = new_state.value if hasattr(new_state, "value") else str(new_state)
    logger.info(
        "circuit_breaker_state_transition",
        extra={
            "service": service_name,
            "from_state": old_value,
            "to_state": new_value,
        },
    )
