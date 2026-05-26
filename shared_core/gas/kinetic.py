"""
Maxwell-Boltzmann distribution for probabilistic worker selection.

In a real gas, particle speeds follow the Maxwell-Boltzmann distribution.
Here, request routing follows the same distribution: workers with higher
kinetic energy (throughput) are selected more often, but with stochastic
variation — preventing hot-spotting and allowing natural load redistribution.

Pure Python — no external dependencies.
"""

from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple


def _maxwell_boltzmann_pdf(v: float, T: float) -> float:
    """
    Maxwell-Boltzmann speed distribution PDF.

    P(v) ∝ v² × exp(-v²/(2T))
    T = kT/m analogue (temperature / mass = throughput scale factor)
    """
    if T <= 0 or v < 0:
        return 0.0
    return (v ** 2) * math.exp(-v ** 2 / (2.0 * T))


class MaxwellBoltzmannSelector:
    """
    Selects workers using MB-distributed probability.

    Higher kinetic energy workers are weighted more heavily but selection
    is stochastic — mimicking thermal motion for natural load distribution.

    Usage::

        selector = MaxwellBoltzmannSelector(temperature=100.0)
        selected = selector.select(
            workers=["w1", "w2", "w3"],
            velocities={"w1": 120.0, "w2": 45.0, "w3": 80.0},
        )
    """

    def __init__(self, temperature: float = 100.0, rng: Optional[random.Random] = None) -> None:
        self._temperature = temperature
        self._rng = rng or random.Random()

    def probabilities(self, workers: List[str], velocities: Dict[str, float]) -> Dict[str, float]:
        """Compute MB-distributed selection probabilities."""
        probs: Dict[str, float] = {}
        for w in workers:
            v = max(0.001, velocities.get(w, 1.0))
            probs[w] = _maxwell_boltzmann_pdf(v, self._temperature)

        total = sum(probs.values()) or 1.0
        return {w: p / total for w, p in probs.items()}

    def select(self, workers: List[str], velocities: Dict[str, float]) -> str:
        """Weighted random selection following MB distribution."""
        if not workers:
            raise ValueError("No workers available for selection")
        probs = self.probabilities(workers, velocities)
        r = self._rng.random()
        cumulative = 0.0
        for w, p in probs.items():
            cumulative += p
            if r <= cumulative:
                return w
        return workers[-1]

    def update_temperature(self, avg_latency_ms: float) -> None:
        """Adapt temperature to system average latency (thermal equilibrium)."""
        # Higher latency → higher temperature → more random selection (spread load)
        self._temperature = max(1.0, avg_latency_ms)


@dataclass
class KineticEnergyTracker:
    """
    EWMA tracker for worker kinetic energy (½mv²).

    Maintains rolling window of throughput observations for stable velocity estimates.
    Used by PressureBalancer to feed accurate velocities to MaxwellBoltzmannSelector.
    """

    worker: str
    window_size: int = 20
    mass: float = 1.0
    _velocities: Deque[float] = field(default_factory=deque)

    def record(self, rps: float) -> None:
        """Record a new RPS observation."""
        self._velocities.append(max(0.0, rps))
        if len(self._velocities) > self.window_size:
            self._velocities.popleft()

    @property
    def velocity(self) -> float:
        """Current smoothed velocity (RPS)."""
        if not self._velocities:
            return 0.0
        return sum(self._velocities) / len(self._velocities)

    @property
    def kinetic_energy(self) -> float:
        """½mv² — routing priority metric."""
        v = self.velocity
        return 0.5 * self.mass * v * v

    @property
    def peak_velocity(self) -> float:
        return max(self._velocities, default=0.0)

    @property
    def p95_velocity(self) -> float:
        """95th percentile velocity over observation window."""
        if not self._velocities:
            return 0.0
        sorted_v = sorted(self._velocities)
        idx = int(len(sorted_v) * 0.95)
        return sorted_v[min(idx, len(sorted_v) - 1)]
