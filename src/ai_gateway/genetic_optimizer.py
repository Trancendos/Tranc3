"""
Genetic provider optimizer for the AI gateway.

Uses an evolutionary algorithm to continuously evolve the provider priority
weights based on observed success rates, latency, and cost efficiency.

No external dependencies — pure Python stdlib only.

Architecture:
  - Population of weight vectors (chromosomes), one per provider
  - Fitness = success_rate * (1 / avg_latency_s) — rewards fast, reliable providers
  - Tournament selection → single-point crossover → Gaussian mutation
  - Elitism: top 10% always survive unchanged
  - Runs synchronously on demand (call evolve() after each generation period)
"""

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple
import sqlite3
import os

_DB_PATH = Path(
    os.getenv("AI_GATEWAY_DB", str(Path(__file__).parent / "data" / "ai_gateway_limits.db"))
)


@dataclass
class ProviderGene:
    name: str
    weight: float = 1.0  # selection probability multiplier
    success_count: int = 0
    failure_count: int = 0
    total_latency_ms: float = 0.0

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.5

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / self.success_count if self.success_count > 0 else 5000.0

    def fitness(self) -> float:
        """Higher is better: fast and reliable providers score highest."""
        latency_s = max(self.avg_latency_ms / 1000.0, 0.001)
        return self.success_rate * (1.0 / latency_s)


@dataclass
class GeneticOptimizer:
    providers: List[str]
    population_size: int = 20
    mutation_rate: float = 0.15
    mutation_sigma: float = 0.2
    tournament_k: int = 3
    generation: int = 0
    _genes: Dict[str, ProviderGene] = field(default_factory=dict)
    _population: List[Dict[str, float]] = field(default_factory=list)

    def __post_init__(self) -> None:
        for p in self.providers:
            self._genes[p] = ProviderGene(name=p)
        self._load_stats()
        self._init_population()

    def _load_stats(self) -> None:
        """Seed fitness data from the LimitMonitor SQLite database."""
        if not _DB_PATH.exists():
            return
        try:
            with sqlite3.connect(_DB_PATH) as conn:
                rows = conn.execute(
                    "SELECT provider, consecutive_errors FROM provider_usage"
                ).fetchall()
            for provider, errors in rows:
                if provider in self._genes:
                    gene = self._genes[provider]
                    gene.failure_count = errors
                    gene.success_count = max(1, 100 - errors * 10)
        except Exception:  # noqa: BLE001
            pass

    def _init_population(self) -> None:
        self._population = []
        for _ in range(self.population_size):
            chromosome: Dict[str, float] = {}
            for p in self.providers:
                base = self._genes[p].fitness()
                chromosome[p] = max(0.01, base + random.gauss(0, 0.3))
            self._population.append(chromosome)

    def record_outcome(self, provider: str, success: bool, latency_ms: float) -> None:
        if provider not in self._genes:
            return
        gene = self._genes[provider]
        if success:
            gene.success_count += 1
            gene.total_latency_ms += latency_ms
        else:
            gene.failure_count += 1

    def _tournament_select(self) -> Dict[str, float]:
        contestants = random.sample(self._population, min(self.tournament_k, len(self._population)))
        return max(contestants, key=lambda c: sum(c.values()))

    def _crossover(self, a: Dict[str, float], b: Dict[str, float]) -> Dict[str, float]:
        keys = list(a.keys())
        pivot = random.randint(1, len(keys) - 1)
        child: Dict[str, float] = {}
        for i, k in enumerate(keys):
            child[k] = a[k] if i < pivot else b[k]
        return child

    def _mutate(self, chromosome: Dict[str, float]) -> Dict[str, float]:
        return {
            k: max(0.01, v + random.gauss(0, self.mutation_sigma))
            if random.random() < self.mutation_rate
            else v
            for k, v in chromosome.items()
        }

    def evolve(self) -> None:
        """Run one generation of evolution and update provider weights."""
        self.generation += 1
        fitness_scores: List[Tuple[float, Dict[str, float]]] = []
        for chrom in self._population:
            score = sum(chrom.get(p, 0.01) * self._genes[p].fitness() for p in self.providers)
            fitness_scores.append((score, chrom))

        fitness_scores.sort(key=lambda x: x[0], reverse=True)
        elite_count = max(1, self.population_size // 10)
        new_pop = [chrom for _, chrom in fitness_scores[:elite_count]]

        while len(new_pop) < self.population_size:
            parent_a = self._tournament_select()
            parent_b = self._tournament_select()
            child = self._crossover(parent_a, parent_b)
            child = self._mutate(child)
            new_pop.append(child)

        self._population = new_pop

        # Update weights from best chromosome
        best = fitness_scores[0][1]
        total = sum(best.values())
        for p in self.providers:
            if p in self._genes:
                self._genes[p].weight = best.get(p, 0.01) / total

    def ranked_providers(self) -> List[str]:
        """Return providers sorted by evolved weight, highest first."""
        return sorted(
            self.providers,
            key=lambda p: self._genes[p].weight,
            reverse=True,
        )

    def weights(self) -> Dict[str, float]:
        return {p: self._genes[p].weight for p in self.providers}
