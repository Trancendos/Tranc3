# src/resilience/circuit_state.py
# Canonical CircuitState enum — single source of truth (TASD-001 Phase 1).
#
# Previously this three-state machine was defined 4× (src/mesh/types.py,
# src/nanoservices/circuit_breaker/, src/resilience/circuit_breaker.py,
# src/validation/loop_validator.py) with divergent base types and one divergent
# value (mesh used "half-open"). All four now re-export this definition.
#
# This module deliberately imports only `enum` so it can be re-exported from any
# subsystem without pulling in the resilience breaker (no circular imports).

from enum import Enum


class CircuitState(str, Enum):
    """Circuit breaker states — closed (healthy), open (failing), half_open (probing)."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"
