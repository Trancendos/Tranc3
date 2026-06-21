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
    from aeonmind.core.genetic_dna import GeneticConfig
    from aeonmind.core.rust_bridge import RustEvolutionEngine
    cfg = GeneticConfig(population_size=population_size, dna_length=dna_length)
    return RustEvolutionEngine(cfg)


@lru_cache(maxsize=1)
def get_liquid_reservoir(input_size: int = 32, reservoir_size: int = 128):
    """Return the best available liquid neural reservoir."""
    if not _AEONMIND_AVAILABLE:
        return None
    from aeonmind.core.fluidic_liquidic import ReservoirConfig
    from aeonmind.core.rust_bridge import RustLiquidReservoir
    cfg = ReservoirConfig(input_size=input_size, reservoir_size=reservoir_size)
    return RustLiquidReservoir(cfg)


@lru_cache(maxsize=1)
def get_quantum_circuit(n_qubits: int = 4):
    """Return the best available quantum decision circuit."""
    if not _AEONMIND_AVAILABLE:
        return None
    from aeonmind.core.quantum import QuantumCircuitConfig
    from aeonmind.core.rust_bridge import RustQuantumCircuit
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
# Adaptive decision loop — wires aeonmind engines to provider rotation
# ---------------------------------------------------------------------------

def adaptive_provider_score(provider_name: str, latency_ms: float, error_rate: float) -> float:
    """
    Score a provider using aeonmind's genetic fitness or Dimensional fallback.
    Returns a score in [0, 1] where 1 = ideal.
    Falls back to a simple heuristic when neither engine is available.
    """
    # Try Dimensional genetic fitness evaluator first (zero-cost, always available)
    try:
        from Dimensional.genetics.fitness import LatencyThroughputFitness
        fitness = LatencyThroughputFitness()
        return fitness.evaluate(latency_ms=latency_ms, error_rate=error_rate)
    except Exception:
        pass

    # Try aeonmind adaptive learner for meta-learning signal
    learner = get_adaptive_learner()
    if learner is not None:
        try:
            import numpy as np
            signal = np.array([latency_ms / 5000.0, error_rate], dtype=float)
            pred = learner.predict(signal)
            return float(max(0.0, min(1.0, 1.0 - float(pred.mean()))))
        except Exception:
            pass

    # Simple heuristic fallback
    latency_score = max(0.0, 1.0 - latency_ms / 5000.0)
    error_score = max(0.0, 1.0 - error_rate)
    return (latency_score + error_score) / 2.0


def quantum_rotation_decision(provider_scores: dict[str, float]) -> str | None:
    """
    Use aeonmind's quantum circuit to select the best provider when scores are
    close. Falls back to argmax when quantum engine is unavailable.
    """
    if not provider_scores:
        return None
    qc = get_quantum_circuit()
    if qc is not None:
        try:
            decision = qc.decide()
            # Map quantum decision index to provider
            providers = sorted(provider_scores.keys())
            idx = int(decision) % len(providers)
            return providers[idx]
        except Exception:
            pass
    # Deterministic fallback — highest score wins
    return max(provider_scores, key=lambda k: provider_scores[k])


# ---------------------------------------------------------------------------
# Stub (graceful degradation when aeonmind is not installed)
# ---------------------------------------------------------------------------

class _StubOrchestrator:
    """Minimal no-op orchestrator used when aeonmind is unavailable."""

    def route(self, payload: dict) -> dict:
        return {"status": "stub", "payload": payload}

    def status(self) -> dict:
        return {"mode": "stub", "aeonmind": False}
