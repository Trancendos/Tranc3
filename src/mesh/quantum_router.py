"""
Quantum-Inspired Router — Superposition & Probabilistic Route Collapse
=======================================================================
Inspired by quantum superposition: hold N candidate routes in a
probability distribution simultaneously, "collapse" to the best on
measurement (request dispatch).

Techniques:
  - Superposition: N candidates weighted by performance beliefs
  - Interference: reinforce successful routes, cancel failed ones
  - Entanglement: correlated route pairs for failover
  - Amplitude amplification: boost high-performing routes faster
    (analogous to Grover's algorithm applied to weighted selection)

This is NOT a real quantum circuit — it's classical code that borrows
probabilistic reasoning from quantum mechanics. Zero-cost: stdlib only.
"""

from __future__ import annotations

import logging
import math
import random
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("tranc3.mesh.quantum_router")


# ── Quantum amplitude state ────────────────────────────────────────────────────


@dataclass
class QuantumRoute:
    """
    A route in quantum superposition.
    Amplitude is the complex-valued weight (we use real amplitude²=probability).
    """

    name: str
    amplitude: float = 1.0  # sqrt(probability)
    phase: float = 0.0  # Phase angle (radians) — models interference
    entangled_with: Optional[str] = None  # Partner route for correlated failover

    # Classical performance tracking
    success_count: int = 0
    failure_count: int = 0
    total_latency_ms: float = 0.0
    last_used: float = field(default_factory=time.monotonic)

    @property
    def probability(self) -> float:
        """P(route selected) = amplitude²"""
        return max(self.amplitude**2, 1e-9)

    @property
    def fidelity(self) -> float:
        """Route health — 1.0 = perfect, 0.0 = broken."""
        total = self.success_count + self.failure_count
        if total == 0:
            return 1.0
        return self.success_count / total

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / max(self.success_count, 1)

    def amplify(self, factor: float = 1.05) -> None:
        """Amplitude amplification — increase probability after success."""
        self.amplitude = min(self.amplitude * factor, 3.0)
        self._normalize_phase()

    def interfere(self, factor: float = 0.9) -> None:
        """Destructive interference — decrease probability after failure."""
        self.amplitude = max(self.amplitude * factor, 0.01)

    def _normalize_phase(self) -> None:
        self.phase = self.phase % (2 * math.pi)

    def record_success(self, latency_ms: float) -> None:
        self.success_count += 1
        self.total_latency_ms += latency_ms
        self.last_used = time.monotonic()
        self.amplify(1.0 + 0.1 * (1.0 - min(latency_ms / 1000.0, 1.0)))

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_used = time.monotonic()
        self.interfere(0.85)

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "amplitude": round(self.amplitude, 4),
            "probability": round(self.probability, 4),
            "fidelity": round(self.fidelity, 3),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "successes": self.success_count,
            "failures": self.failure_count,
            "entangled_with": self.entangled_with,
        }


# ── Quantum Router ─────────────────────────────────────────────────────────────


class QuantumRouter:
    """
    Quantum-inspired route selection.

    Routes are held in superposition (probability distribution) and
    collapsed to a single route on each request via measurement.

    On success: amplitude amplification (Grover-inspired) boosts route.
    On failure: destructive interference reduces route probability.
    Entangled pairs: if primary fails, entangled partner auto-promoted.

    Usage::

        router = QuantumRouter()
        router.add_route("ollama", entangled_with="groq")
        router.add_route("groq", entangled_with="ollama")
        router.add_route("cerebras")

        route = router.collapse()          # select route
        try:
            result = await dispatch(route)
            router.record_success(route, latency_ms=45.0)
        except Exception:
            router.record_failure(route)   # destructive interference
    """

    def __init__(self) -> None:
        self._routes: dict[str, QuantumRoute] = {}

    def add_route(
        self,
        name: str,
        initial_amplitude: float = 1.0,
        entangled_with: Optional[str] = None,
    ) -> QuantumRoute:
        route = QuantumRoute(
            name=name,
            amplitude=initial_amplitude,
            entangled_with=entangled_with,
        )
        self._routes[name] = route
        logger.debug("quantum_router: added route %s (amp=%.2f)", name, initial_amplitude)
        return route

    def _normalize(self) -> None:
        """Normalize amplitudes so probabilities sum to 1."""
        total_sq = sum(r.amplitude**2 for r in self._routes.values())
        if total_sq > 0:
            norm = math.sqrt(total_sq)
            for r in self._routes.values():
                r.amplitude /= norm
                r.amplitude = max(r.amplitude, 0.01)

    def collapse(self, exclude: Optional[list[str]] = None) -> Optional[str]:
        """
        Measurement — collapse superposition to single route.
        Uses probability-weighted random selection.
        Returns None if no routes registered.
        """
        exclude = set(exclude or [])
        candidates = [r for r in self._routes.values() if r.name not in exclude]
        if not candidates:
            return None

        # Compute probabilities
        total = sum(r.probability for r in candidates)
        if total <= 0:
            return random.choice(candidates).name  # nosec B311

        r_val = random.uniform(0, total)  # nosec B311
        cumulative = 0.0
        for route in candidates:
            cumulative += route.probability
            if r_val <= cumulative:
                return route.name

        return candidates[-1].name

    def record_success(self, name: str, latency_ms: float = 0.0) -> None:
        """Record success → amplify route + suppress entangled partner."""
        route = self._routes.get(name)
        if route:
            route.record_success(latency_ms)
            # Gentle interference on entangled partner (correlated routing)
            if route.entangled_with and route.entangled_with in self._routes:
                partner = self._routes[route.entangled_with]
                partner.interfere(0.98)  # Very mild — just slight preference shift
            self._normalize()

    def record_failure(self, name: str) -> None:
        """Record failure → destructive interference + amplify entangled partner."""
        route = self._routes.get(name)
        if route:
            route.record_failure()
            # Amplify entangled partner on failure (quantum teleportation-inspired)
            if route.entangled_with and route.entangled_with in self._routes:
                partner = self._routes[route.entangled_with]
                partner.amplify(1.15)  # Boost failover partner
                logger.debug(
                    "quantum_router: entanglement failover %s → %s",
                    name,
                    route.entangled_with,
                )
            self._normalize()

    def top_k(self, k: int = 3) -> list[str]:
        """Return top-k routes by probability for parallel dispatch."""
        sorted_routes = sorted(
            self._routes.values(),
            key=lambda r: r.probability,
            reverse=True,
        )
        return [r.name for r in sorted_routes[:k]]

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "routes": {name: r.stats for name, r in self._routes.items()},
            "total_routes": len(self._routes),
        }


# ── Singleton ──────────────────────────────────────────────────────────────────

_quantum_router: Optional[QuantumRouter] = None


def get_quantum_router() -> QuantumRouter:
    global _quantum_router
    if _quantum_router is None:
        _quantum_router = QuantumRouter()
        # Wire up default provider chain with entanglement pairs
        _quantum_router.add_route("ollama", initial_amplitude=2.0, entangled_with="groq")
        _quantum_router.add_route("groq", initial_amplitude=1.5, entangled_with="cerebras")
        _quantum_router.add_route("cerebras", initial_amplitude=1.4, entangled_with="sambanova")
        _quantum_router.add_route("sambanova", initial_amplitude=1.2)
        _quantum_router.add_route("openrouter", initial_amplitude=1.1)
        _quantum_router.add_route("gemini", initial_amplitude=1.3, entangled_with="openrouter")
        _quantum_router.add_route("huggingface", initial_amplitude=1.0)
        _quantum_router.add_route("github_models", initial_amplitude=0.8)
        _quantum_router.add_route("offline", initial_amplitude=0.5)
    return _quantum_router


__all__ = ["QuantumRoute", "QuantumRouter", "get_quantum_router"]
