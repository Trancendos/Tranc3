# Dimensional/circuit_state.py
# Canonical CircuitState for the whole platform (SFSC).
#
# WHY THIS LIVES HERE AND NOT IN src/resilience/
#
# TASD-001 Phase 1 made src/resilience/circuit_state.py canonical for the four
# implementations under src/, and §3.1 explicitly considered "a shared_core-style
# home" before choosing src/. That choice did not weigh the build boundary, and
# the boundary is decisive:
#
#   * 74 of 174 compose services build from their own directory, so `src/` is
#     absent from those images. A Dimensional module importing from src/ would
#     break every worker that vendors it — hive-service and
#     dimensional-nexus-service copy Dimensional/ subtrees into their build
#     contexts precisely because src/ is unreachable.
#   * `Dimensional/` is reachable from both sides: services built from the repo
#     root get it on sys.path, and own-context workers vendor it.
#
# So the dependency runs one way — src/ may import Dimensional, never the
# reverse — and the canonical definition belongs on the reachable side.
#
# The consequence of getting this wrong is already on the record: after TASD-001
# consolidated four breakers onto an src/-only home, workers/chaos-party/
# needed a breaker, could not import it, and wrote a fifth. Counting the three
# that were sitting inside Dimensional/ all along, the platform reached eight.
#
# §6 of TASD-001 dismissed those three as "unrelated CircuitState types … out of
# scope for this consolidation". They were not unrelated: all three were
# `(str, Enum)` with exactly CLOSED/OPEN/HALF_OPEN and the same values as the
# canonical one. That scoping error is what this module corrects.
#
# Imports only `enum`, so any subsystem can re-export it without pulling in a
# breaker implementation and without risking a circular import.

from enum import Enum


class CircuitState(str, Enum):
    """Circuit breaker states — closed (healthy), open (failing), half_open (probing)."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    @classmethod
    def _missing_(cls, value: object) -> "CircuitState | None":
        # Backward compatibility: mesh formerly serialised HALF_OPEN as the
        # hyphenated "half-open". Accept it on lookup/Pydantic validation so
        # data serialised by an older instance (e.g. a ServiceCallResult in
        # flight during a rolling deploy) still resolves. See TASD-001 Phase 1.
        if value == "half-open":
            return cls.HALF_OPEN
        return None


__all__ = ["CircuitState"]
