"""
src/aeonmind_bridge.py — AeonMind ↔ Tranc3 integration bridge.

Exposes aeonmind's polyglot AI engines to the main Python application with
graceful degradation when optional components (Rust/Go/WASM) are unavailable.

Public surface:
  get_orchestrator()       → LogicalOrchestrator singleton
  get_evolution_engine()   → RustEvolutionEngine (Rust if available, else pure-Python)
  get_liquid_reservoir()   → RustLiquidReservoir (Rust if available, else pure-Python)
  get_quantum_circuit()    → RustQuantumCircuit (Rust if available, else pure-Python)
  get_adaptive_learner()   → RustAdaptiveLearner (Rust if available, else pure-Python)
  aeonmind_status()        → dict with availability flags
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Availability probes
# ---------------------------------------------------------------------------

def _probe_aeonmind() -> bool:
    try:
        import aeonmind  # noqa: F401
        return True
    except ImportError:
        return False


_AEONMIND_AVAILABLE = _probe_aeonmind()


def aeonmind_status() -> dict[str, Any]:
    if not _AEONMIND_AVAILABLE:
        return {"available": False, "rust_bindings": False, "version": None}
    from aeonmind.core.rust_bridge import has_rust_bindings, rust_version
    return {
        "available": True,
        "rust_bindings": has_rust_bindings(),
        "rust_version": rust_version(),
        "version": _safe_version(),
    }


def _safe_version() -> str | None:
    try:
        import aeonmind
        return aeonmind.__version__
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Singletons
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_orchestrator():
    """Return the LogicalOrchestrator singleton (aeonmind systems layer)."""
    if not _AEONMIND_AVAILABLE:
        logger.warning("aeonmind unavailable — orchestrator stub returned")
        return _StubOrchestrator()
    from aeonmind.systems.orchestrator import LogicalOrchestrator
    return LogicalOrchestrator()


@lru_cache(maxsize=1)
def get_evolution_engine(population_size: int = 50, dna_length: int = 64):
    """Return the best available DNA evolution engine."""
    if not _AEONMIND_AVAILABLE:
        return None
    from aeonmind.core.rust_bridge import RustEvolutionEngine
    from aeonmind.core.genetic_dna import GeneticConfig
    cfg = GeneticConfig(population_size=population_size, dna_length=dna_length)
    return RustEvolutionEngine(cfg)


@lru_cache(maxsize=1)
def get_liquid_reservoir(input_size: int = 32, reservoir_size: int = 128):
    """Return the best available liquid neural reservoir."""
    if not _AEONMIND_AVAILABLE:
        return None
    from aeonmind.core.rust_bridge import RustLiquidReservoir
    from aeonmind.core.fluidic_liquidic import ReservoirConfig
    cfg = ReservoirConfig(input_size=input_size, reservoir_size=reservoir_size)
    return RustLiquidReservoir(cfg)


@lru_cache(maxsize=1)
def get_quantum_circuit(n_qubits: int = 4):
    """Return the best available quantum decision circuit."""
    if not _AEONMIND_AVAILABLE:
        return None
    from aeonmind.core.rust_bridge import RustQuantumCircuit
    from aeonmind.core.quantum import QuantumCircuitConfig
    cfg = QuantumCircuitConfig(n_qubits=n_qubits)
    return RustQuantumCircuit(cfg)


@lru_cache(maxsize=1)
def get_adaptive_learner(n_params: int = 32):
    """Return the best available adaptive meta-learner."""
    if not _AEONMIND_AVAILABLE:
        return None
    from aeonmind.core.rust_bridge import RustAdaptiveLearner
    return RustAdaptiveLearner(n_params=n_params)


# ---------------------------------------------------------------------------
# Stub (graceful degradation when aeonmind is not installed)
# ---------------------------------------------------------------------------

class _StubOrchestrator:
    """Minimal no-op orchestrator used when aeonmind is unavailable."""

    def route(self, payload: dict) -> dict:
        return {"status": "stub", "payload": payload}

    def status(self) -> dict:
        return {"mode": "stub", "aeonmind": False}
