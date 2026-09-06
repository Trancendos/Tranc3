# src/resilience/circuit_state.py
# Re-export of the canonical CircuitState, which now lives in Dimensional/.
#
# TASD-001 Phase 1 made this module canonical for the four implementations under
# src/. It stays as the import path those four use — nothing about them changes
# — but the definition moved to Dimensional/circuit_state.py so that own-context
# workers, which cannot import src/, can reach it too. See that module for the
# full reasoning and for the three further copies inside Dimensional/ that
# TASD-001 §6 wrongly scoped out as "unrelated".
#
# Direction of dependency: src/ imports Dimensional/, never the reverse.

from Dimensional.circuit_state import CircuitState  # noqa: F401

__all__ = ["CircuitState"]
