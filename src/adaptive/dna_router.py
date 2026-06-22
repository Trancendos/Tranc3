"""
src/adaptive/dna_router.py
==========================
DNA-sequence-inspired routing with mutation and crossover.

A "chromosome" is an ordered list of RouteGene objects — each represents a
provider (e.g. Ollama, Groq, Gemini) with a fitness score derived from
latency and error feedback. The genetic algorithm evolves the routing strategy
over time, naturally promoting high-fitness providers.

Compatible with the existing ACO pheromone router — wraps it with genetic
evolution.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class RouteGene:
    provider: str
    weight: float = 1.0  # routing weight (higher = more likely selected)
    fitness: float = 1.0  # 0.0 - 1.0 (updated from latency/errors)
    generation: int = 0
    total_requests: int = 0
    total_errors: int = 0
    avg_latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "weight": round(self.weight, 4),
            "fitness": round(self.fitness, 4),
            "generation": self.generation,
            "total_requests": self.total_requests,
            "total_errors": self.total_errors,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
        }


class DNARouter:
    """Genetic algorithm-based provider router."""

    MUTATION_WEIGHT_DELTA = 0.15
    TOURNAMENT_SIZE = 3
    ELITE_FRACTION = 0.2  # top 20 % survive unchanged

    def __init__(self, providers: list[str]) -> None:
        self._chromosome: list[RouteGene] = [RouteGene(provider=p) for p in providers]
        self._generation = 0
        self._rng = random.Random()

    # ------------------------------------------------------------------
    # Feedback
    # ------------------------------------------------------------------

    def record_result(self, provider: str, latency_ms: float, success: bool) -> None:
        """Update fitness for a provider based on request outcome."""
        gene = self._find_gene(provider)
        if gene is None:
            return
        gene.total_requests += 1
        if not success:
            gene.total_errors += 1
        # Exponential moving average latency
        alpha = 0.2
        if gene.avg_latency_ms == 0.0:
            gene.avg_latency_ms = latency_ms
        else:
            gene.avg_latency_ms = alpha * latency_ms + (1 - alpha) * gene.avg_latency_ms

        # Fitness: blend of success rate and inverse latency
        error_rate = gene.total_errors / max(gene.total_requests, 1)
        # Normalise latency: 0ms → 1.0, 5000ms → 0.0
        latency_fitness = max(0.0, 1.0 - gene.avg_latency_ms / 5000.0)
        gene.fitness = 0.7 * (1.0 - error_rate) + 0.3 * latency_fitness
        gene.fitness = max(0.0, min(1.0, gene.fitness))

    # ------------------------------------------------------------------
    # Genetic operators
    # ------------------------------------------------------------------

    def mutate(self, rate: float = 0.1) -> None:
        """Randomly adjust weights based on fitness (rate = mutation probability)."""
        for gene in self._chromosome:
            if self._rng.random() < rate:
                delta = self._rng.uniform(-self.MUTATION_WEIGHT_DELTA, self.MUTATION_WEIGHT_DELTA)
                gene.weight = max(0.01, gene.weight + delta * gene.fitness)

    def crossover(self, other_chromosome: list[RouteGene]) -> list[RouteGene]:
        """One-point crossover between this chromosome and another. Returns offspring."""
        n = min(len(self._chromosome), len(other_chromosome))
        if n < 2:
            return list(self._chromosome)
        point = self._rng.randint(1, n - 1)
        child_genes: list[RouteGene] = []
        providers_seen: set[str] = set()
        for i, gene in enumerate(self._chromosome):
            if gene.provider in providers_seen:
                continue
            if i < point:
                child_genes.append(
                    RouteGene(
                        provider=gene.provider,
                        weight=gene.weight,
                        fitness=gene.fitness,
                        generation=self._generation + 1,
                    )
                )
            else:
                # take from other if same provider exists there
                other_gene = next(
                    (g for g in other_chromosome if g.provider == gene.provider), gene
                )
                child_genes.append(
                    RouteGene(
                        provider=gene.provider,
                        weight=other_gene.weight,
                        fitness=other_gene.fitness,
                        generation=self._generation + 1,
                    )
                )
            providers_seen.add(gene.provider)
        return child_genes

    def select_fittest(self) -> Optional[RouteGene]:
        """Tournament selection — return winner from a random subset."""
        if not self._chromosome:
            return None
        available = [g for g in self._chromosome if g.fitness > 0]
        if not available:
            return self._chromosome[0]
        tournament = self._rng.choices(available, k=min(self.TOURNAMENT_SIZE, len(available)))
        return max(tournament, key=lambda g: g.fitness)

    def evolve(self, generation: int | None = None) -> None:
        """Run one full evolution cycle (elite survival + mutation + fitness-weighted reorder)."""
        self._generation = generation if generation is not None else self._generation + 1

        # Sort by fitness descending
        self._chromosome.sort(key=lambda g: g.fitness, reverse=True)

        elite_count = max(1, int(len(self._chromosome) * self.ELITE_FRACTION))
        # Elites survive unchanged; rest mutate
        for gene in self._chromosome[elite_count:]:
            gene.generation = self._generation
            if self._rng.random() < 0.3:
                self.mutate(rate=0.2)

        # Update weights proportional to fitness
        total_fitness = sum(g.fitness for g in self._chromosome) or 1.0
        for gene in self._chromosome:
            gene.weight = gene.fitness / total_fitness

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def route(self) -> Optional[str]:
        """Select a provider using fitness-weighted roulette selection."""
        available = [g for g in self._chromosome if g.fitness > 0 and g.weight > 0]
        if not available:
            return None
        total_weight = sum(g.weight for g in available)
        pick = self._rng.uniform(0, total_weight)
        running = 0.0
        for gene in available:
            running += gene.weight
            if running >= pick:
                return gene.provider
        return available[-1].provider

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_gene(self, provider: str) -> Optional[RouteGene]:
        return next((g for g in self._chromosome if g.provider == provider), None)

    def chromosome_state(self) -> list[dict[str, Any]]:
        return [g.to_dict() for g in self._chromosome]

    def add_provider(self, provider: str) -> None:
        if not self._find_gene(provider):
            self._chromosome.append(RouteGene(provider=provider))
