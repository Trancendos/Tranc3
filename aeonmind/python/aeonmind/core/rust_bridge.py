"""
AeonMind Rust Bridge — Conditional Rust Bindings with Python Fallbacks.

When the Rust extension module (_aeonmind_rust) is available via
PyO3/maturin, it will be used for performance-critical operations.
Otherwise, the pure Python implementations are used.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from .definitions import Tier, TIER_NAMES
from .adaptive import AdaptiveMetaLearner, AdaptiveConfig
from .genetic_dna import DNAEvolutionEngine, GeneticConfig
from .fluidic_liquidic import LiquidReservoir, ReservoirConfig
from .quantum import QuantumDecisionCircuit, QuantumCircuitConfig


def has_rust_bindings() -> bool:
    """Check if the Rust extension module is available."""
    try:
        import _aeonmind_rust  # noqa: F401

        return True
    except ImportError:
        return False


def rust_version() -> Optional[str]:
    """Get the Rust extension module version, if available."""
    try:
        import _aeonmind_rust

        return getattr(_aeonmind_rust, "__version__", None)
    except ImportError:
        return None


def tier_hierarchy() -> str:
    """Return the tier hierarchy as a formatted string."""
    lines = ["═" * 60, "  TRANC3 INFINITY — TIER HIERARCHY", "═" * 60]
    for tier in Tier:
        lines.append(f"\n  Tier {tier.value}: {TIER_NAMES[tier]}")
    lines.append("\n" + "═" * 60)
    return "\n".join(lines)


class RustLiquidReservoir:
    """Wrapper for the Rust LiquidReservoir with Python fallback."""

    def __init__(self, config: Optional[ReservoirConfig] = None):
        self.config = config or ReservoirConfig()
        self._rust_impl = None

        if has_rust_bindings():
            try:
                import _aeonmind_rust

                self._rust_impl = _aeonmind_rust.RustLiquidReservoir(
                    input_size=self.config.input_size,
                    reservoir_size=self.config.reservoir_size,
                    spectral_radius=self.config.spectral_radius,
                    leaking_rate=self.config.leaking_rate,
                )
            except Exception:
                self._rust_impl = None

        self._python_impl = LiquidReservoir(self.config)

    def step(self, input_data: np.ndarray) -> np.ndarray:
        if self._rust_impl is not None:
            result = self._rust_impl.step(input_data.tolist())
            return np.array(result)
        return self._python_impl.step(input_data)

    def reset(self) -> None:
        if self._rust_impl is not None:
            self._rust_impl.reset()
        else:
            self._python_impl.reset()

    def warmup(self, n_steps: int = 50) -> None:
        if self._rust_impl is not None:
            self._rust_impl.warmup(n_steps)
        else:
            self._python_impl.warmup(n_steps)


class RustEvolutionEngine:
    """Wrapper for the Rust EvolutionEngine with Python fallback."""

    def __init__(self, config: Optional[GeneticConfig] = None):
        self.config = config or GeneticConfig()
        self._rust_impl = None

        if has_rust_bindings():
            try:
                import _aeonmind_rust

                self._rust_impl = _aeonmind_rust.RustEvolutionEngine(
                    population_size=self.config.population_size,
                    dna_length=self.config.dna_length,
                    mutation_rate=self.config.mutation_rate,
                    crossover_rate=self.config.crossover_rate,
                )
            except Exception:
                self._rust_impl = None

        self._python_impl = DNAEvolutionEngine(self.config)

    def evolve(self, fitness_fn, generations: int = 10):
        if self._rust_impl is not None:
            return self._rust_impl.evolve(fitness_fn)
        return self._python_impl.evolve(fitness_fn, generations=generations)

    def best_dna(self) -> np.ndarray:
        if self._rust_impl is not None:
            return np.array(self._rust_impl.best_dna())
        best = self._python_impl.best_ever()
        return best.dna if best is not None else np.array([])


class RustQuantumCircuit:
    """Wrapper for the Rust QuantumCircuit with Python fallback."""

    def __init__(self, config: Optional[QuantumCircuitConfig] = None):
        self.config = config or QuantumCircuitConfig()
        self._rust_impl = None

        if has_rust_bindings():
            try:
                import _aeonmind_rust

                self._rust_impl = _aeonmind_rust.RustQuantumCircuit(
                    n_qubits=self.config.n_qubits,
                    n_layers=self.config.n_layers,
                    rotations_per_layer=self.config.rotations_per_layer,
                )
            except Exception:
                self._rust_impl = None

        self._python_impl = QuantumDecisionCircuit(self.config)

    def execute(self) -> np.ndarray:
        if self._rust_impl is not None:
            return np.array(self._rust_impl.execute())
        return self._python_impl.execute(use_pennylane=False)

    def decide(self) -> int:
        if self._rust_impl is not None:
            return self._rust_impl.decide()
        return self._python_impl.decide(use_pennylane=False)


class RustAdaptiveLearner:
    """Wrapper for the Rust AdaptiveLearner with Python fallback."""

    def __init__(self, n_params: int = 32, config: Optional[AdaptiveConfig] = None):
        self.config = config or AdaptiveConfig()
        self._rust_impl = None

        if has_rust_bindings():
            try:
                import _aeonmind_rust

                self._rust_impl = _aeonmind_rust.RustAdaptiveLearner(
                    n_params=n_params,
                    learning_rate=self.config.learning_rate,
                    memory_size=self.config.memory_size,
                )
            except Exception:
                self._rust_impl = None

        self._python_impl = AdaptiveMetaLearner(n_params, self.config)

    def step(self, gradient: np.ndarray) -> np.ndarray:
        if self._rust_impl is not None:
            return np.array(self._rust_impl.step(gradient.tolist()))
        self._python_impl.step(gradient)
        return self._python_impl.parameters

    def parameters(self) -> np.ndarray:
        if self._rust_impl is not None:
            return np.array(self._rust_impl.parameters())
        return self._python_impl.parameters_array()
