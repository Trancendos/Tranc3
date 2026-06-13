"""
Genetic + ACO Router — Evolutionary Route Fitness
==================================================
Combines two bio-inspired techniques:

1. Ant Colony Optimization (ACO) — pheromone trails guide route selection.
   Fast ants (low-latency routes) deposit more pheromone; trails evaporate
   over time so routes that degrade lose preference automatically.

2. Genetic fitness — routes accumulate a fitness score that evolves based
   on success/failure/latency, with periodic "mutation" that injects small
   random exploration to prevent convergence on a stale best route.

Both are proven lightweight algorithms; this implementation is pure stdlib.
"""

from __future__ import annotations

import logging
import math
import random
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("tranc3.mesh.genetic_router")

# ── Configuration ──────────────────────────────────────────────────────────────

EVAPORATION_RATE = 0.05  # Pheromone evaporation per tick (0-1)
ALPHA = 1.0  # Pheromone influence weight
BETA = 2.0  # Heuristic (inverse latency) influence weight
MUTATION_RATE = 0.02  # Probability of random weight mutation per selection
MUTATION_MAGNITUDE = 0.1  # Max mutation delta


# ── Route gene ─────────────────────────────────────────────────────────────────


@dataclass
class RouteGene:
    """
    A route with ACO pheromone trail + genetic fitness.
    Analogous to a gene in an evolutionary algorithm.
    """

    name: str
    pheromone: float = 1.0  # ACO: accumulated positive signal
    fitness: float = 1.0  # Genetic: composite health score
    heuristic: float = 1.0  # 1/avg_latency (set from observation)

    # Observed stats
    success_count: int = 0
    failure_count: int = 0
    total_latency_ms: float = 0.0
    last_deposit_at: float = field(default_factory=time.monotonic)

    @property
    def total_calls(self) -> int:
        return self.success_count + self.failure_count

    @property
    def success_rate(self) -> float:
        return self.success_count / max(self.total_calls, 1)

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / max(self.success_count, 1)

    @property
    def desirability(self) -> float:
        """ACO desirability = pheromone^α × heuristic^β."""
        return (max(self.pheromone, 1e-6) ** ALPHA) * (max(self.heuristic, 1e-6) ** BETA)

    def deposit_pheromone(self, quality: float) -> None:
        """Ant deposits pheromone; quality ~ 1/latency × success_rate."""
        self.pheromone += quality
        self.last_deposit_at = time.monotonic()

    def evaporate(self) -> None:
        """Time-based evaporation ensures stale routes lose preference."""
        self.pheromone = max(self.pheromone * (1.0 - EVAPORATION_RATE), 0.01)

    def evolve_fitness(self) -> None:
        """Genetic update: fitness = weighted combination of success rate and latency."""
        sr = self.success_rate
        # Latency score: <50ms=1.0, 500ms=0.5, >2s=0.1
        lat_score = math.exp(-self.avg_latency_ms / 500.0) if self.avg_latency_ms > 0 else 1.0
        self.fitness = 0.6 * sr + 0.4 * lat_score
        # Update heuristic (inverse latency)
        if self.avg_latency_ms > 0:
            self.heuristic = 1000.0 / self.avg_latency_ms
        else:
            self.heuristic = 10.0  # Default high (unknown, assume fast)

    def mutate(self) -> None:
        """Random perturbation — genetic exploration to escape local optima."""
        delta = random.uniform(-MUTATION_MAGNITUDE, MUTATION_MAGNITUDE)  # nosec B311
        self.pheromone = max(self.pheromone + delta, 0.01)

    def record_success(self, latency_ms: float) -> None:
        self.success_count += 1
        self.total_latency_ms += latency_ms
        # Quality proportional to speed: faster = more pheromone
        quality = max(1.0 - (latency_ms / 2000.0), 0.1)
        self.deposit_pheromone(quality)
        self.evolve_fitness()

    def record_failure(self) -> None:
        self.failure_count += 1
        self.evaporate()  # Failure triggers immediate evaporation
        self.evolve_fitness()

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "pheromone": round(self.pheromone, 4),
            "fitness": round(self.fitness, 4),
            "heuristic": round(self.heuristic, 4),
            "desirability": round(self.desirability, 4),
            "success_rate": round(self.success_rate, 3),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "calls": self.total_calls,
        }


# ── Genetic ACO Router ─────────────────────────────────────────────────────────


class GeneticRouter:
    """
    ACO + genetic algorithm route selection.

    Ants discover good routes by following pheromone trails.
    Genetic evolution improves fitness scores over time.
    Periodic evaporation prevents lock-in on stale best routes.

    Usage::

        router = GeneticRouter()
        router.add_route("ollama")
        router.add_route("groq")
        router.add_route("gemini")

        route = router.select()
        try:
            result = await dispatch(route)
            router.record_success(route, latency_ms=45.0)
        except:
            router.record_failure(route)
    """

    def __init__(self) -> None:
        self._genes: dict[str, RouteGene] = {}
        self._tick_count: int = 0
        self._evaporation_interval: int = 10  # Evaporate every N selections

    def add_route(self, name: str, initial_pheromone: float = 1.0) -> RouteGene:
        gene = RouteGene(name=name, pheromone=initial_pheromone)
        self._genes[name] = gene
        logger.debug("genetic_router: added route %s", name)
        return gene

    def _evaporate_all(self) -> None:
        """Periodic global evaporation."""
        for gene in self._genes.values():
            gene.evaporate()

    def _maybe_mutate(self) -> None:
        """Random mutation for exploration."""
        for gene in self._genes.values():
            if random.random() < MUTATION_RATE:  # nosec B311
                gene.mutate()

    def select(self, exclude: Optional[list[str]] = None) -> Optional[str]:
        """
        ACO-based route selection: probabilistic choice weighted by desirability.
        Routes with higher pheromone × heuristic are exponentially more likely.
        """
        self._tick_count += 1
        if self._tick_count % self._evaporation_interval == 0:
            self._evaporate_all()
            self._maybe_mutate()

        exclude = set(exclude or [])
        candidates = [g for g in self._genes.values() if g.name not in exclude]
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0].name

        total = sum(g.desirability for g in candidates)
        if total <= 0:
            return random.choice(candidates).name  # nosec B311

        r = random.uniform(0, total)  # nosec B311
        cumulative = 0.0
        for gene in candidates:
            cumulative += gene.desirability
            if r <= cumulative:
                return gene.name

        return candidates[-1].name

    def record_success(self, name: str, latency_ms: float = 0.0) -> None:
        gene = self._genes.get(name)
        if gene:
            gene.record_success(latency_ms)

    def record_failure(self, name: str) -> None:
        gene = self._genes.get(name)
        if gene:
            gene.record_failure()

    def ranked(self) -> list[RouteGene]:
        """Return routes sorted by fitness × desirability."""
        return sorted(
            self._genes.values(),
            key=lambda g: g.fitness * g.desirability,
            reverse=True,
        )

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "genes": {name: g.stats for name, g in self._genes.items()},
            "tick_count": self._tick_count,
            "top_route": self.ranked()[0].name if self._genes else None,
        }


# ── Singleton ──────────────────────────────────────────────────────────────────

_genetic_router: Optional[GeneticRouter] = None


def get_genetic_router() -> GeneticRouter:
    global _genetic_router
    if _genetic_router is None:
        _genetic_router = GeneticRouter()
        # Wire up default provider chain
        chain = [
            ("ollama", 2.0),
            ("groq", 1.8),
            ("cerebras", 1.6),
            ("sambanova", 1.2),
            ("openrouter", 1.3),
            ("gemini", 1.5),
            ("huggingface", 1.0),
            ("github_models", 0.8),
            ("offline", 0.5),
        ]
        for name, pheromone in chain:
            _genetic_router.add_route(name, initial_pheromone=pheromone)
    return _genetic_router


__all__ = ["RouteGene", "GeneticRouter", "get_genetic_router"]
