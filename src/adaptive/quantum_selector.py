"""
src/adaptive/quantum_selector.py
=================================
Quantum superposition-inspired provider selection.

Providers exist in superposition until a request "observes" (collapses) the
state. Entanglement links pairs of providers so failures are correlated.
Decoherence detection identifies when the system is too noisy to make a
reliable selection.

Pure Python + numpy, zero-cost.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional

try:
    import numpy as np  # type: ignore
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False


@dataclass
class QuantumState:
    """Quantum state amplitude for a single provider."""
    provider: str
    amplitude: float = 1.0  # probability amplitude (not normalised)
    phase: float = 0.0      # phase angle in radians
    collapsed: bool = False  # True after observation (this request)

    @property
    def probability(self) -> float:
        return self.amplitude ** 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "amplitude": round(self.amplitude, 4),
            "probability": round(self.probability, 4),
            "phase": round(self.phase, 4),
            "collapsed": self.collapsed,
        }


class QuantumSelector:
    """Quantum superposition-inspired provider selection engine."""

    DECOHERENCE_THRESHOLD = 0.3  # below this average amplitude → decoherent

    def __init__(self) -> None:
        self._states: dict[str, QuantumState] = {}
        self._entanglements: list[tuple[str, str]] = []  # pairs of linked providers
        self._error_history: dict[str, list[float]] = {}

    # ------------------------------------------------------------------
    # Superposition
    # ------------------------------------------------------------------

    def superpose(self, providers: list[str]) -> None:
        """Create equal superposition across all providers."""
        n = len(providers)
        if n == 0:
            return
        amplitude = 1.0 / math.sqrt(n)
        for p in providers:
            self._states[p] = QuantumState(provider=p, amplitude=amplitude)

    # ------------------------------------------------------------------
    # Collapse
    # ------------------------------------------------------------------

    def collapse(self, request_context: dict[str, Any] | None = None) -> Optional[str]:
        """Collapse superposition to best provider based on probability amplitudes."""
        if not self._states:
            return None

        available = [s for s in self._states.values() if s.amplitude > 0]
        if not available:
            return None

        # Normalise probabilities
        total = sum(s.probability for s in available)
        if total == 0:
            return available[0].provider

        if _HAS_NUMPY:
            probs = np.array([s.probability / total for s in available])
            indices = np.arange(len(available))
            chosen_idx = int(np.random.choice(indices, p=probs))
            chosen = available[chosen_idx]
        else:
            import random
            weights = [s.probability / total for s in available]
            chosen = random.choices(available, weights=weights, k=1)[0]

        # Collapse — reduce amplitude of others slightly (observation effect)
        chosen.collapsed = True
        for s in available:
            if s.provider != chosen.provider:
                s.amplitude = max(0.0, s.amplitude * 0.95)

        return chosen.provider

    # ------------------------------------------------------------------
    # Entanglement
    # ------------------------------------------------------------------

    def entangle(self, provider_a: str, provider_b: str) -> None:
        """Link two providers so failures in one affect the other."""
        if (provider_a, provider_b) not in self._entanglements and (
            provider_b, provider_a
        ) not in self._entanglements:
            self._entanglements.append((provider_a, provider_b))

    def record_failure(self, provider: str, severity: float = 0.5) -> list[str]:
        """Record a failure and propagate to entangled providers."""
        if provider in self._states:
            self._states[provider].amplitude = max(0.0, self._states[provider].amplitude - severity)

        propagated: list[str] = []
        for pa, pb in self._entanglements:
            partner = None
            if pa == provider:
                partner = pb
            elif pb == provider:
                partner = pa
            if partner and partner in self._states:
                self._states[partner].amplitude = max(
                    0.0, self._states[partner].amplitude - severity * 0.5
                )
                propagated.append(partner)

        return propagated

    # ------------------------------------------------------------------
    # Decoherence
    # ------------------------------------------------------------------

    def measure_coherence(self) -> float:
        """Return average amplitude (0.0 = fully decoherent, 1.0 = fully coherent)."""
        if not self._states:
            return 0.0
        return sum(s.amplitude for s in self._states.values()) / len(self._states)

    def is_decoherent(self) -> bool:
        return self.measure_coherence() < self.DECOHERENCE_THRESHOLD

    def renormalise(self) -> None:
        """Renormalise amplitudes after failures."""
        total = math.sqrt(sum(s.amplitude ** 2 for s in self._states.values()))
        if total == 0:
            # Reset all providers equally
            n = len(self._states)
            amp = 1.0 / math.sqrt(n) if n else 0.0
            for s in self._states.values():
                s.amplitude = amp
        else:
            for s in self._states.values():
                s.amplitude /= total

    def state_snapshot(self) -> dict[str, Any]:
        return {
            "coherence": round(self.measure_coherence(), 4),
            "decoherent": self.is_decoherent(),
            "states": {p: s.to_dict() for p, s in self._states.items()},
            "entanglements": [{"a": a, "b": b} for a, b in self._entanglements],
        }
