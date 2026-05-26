"""
GeneticOptimizer — NSGA-II multi-objective genetic algorithm for worker config tuning.

Uses DEAP when available for high-quality NSGA-II with CMA-ES.
Falls back to a pure-Python tournament-selection GA that mirrors the
existing src/nanoservices/genetic_optimizer/ logic without dependencies.

Designed for async usage — evolution runs in an executor thread to avoid
blocking the FastAPI event loop.
"""

from __future__ import annotations

import asyncio
import copy
import random
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .fitness import FitnessEvaluator, LatencyThroughputFitness

Individual = Dict[str, Any]
Population = List[Individual]


def _dominates(a: Tuple[float, ...], b: Tuple[float, ...]) -> bool:
    """Return True if a Pareto-dominates b (all objectives ≤, at least one <)."""
    return all(x <= y for x, y in zip(a, b, strict=False)) and any(x < y for x, y in zip(a, b, strict=False))


def _fast_nondominated_sort(pop: List[Individual]) -> List[List[int]]:
    """Pure-Python fast non-dominated sort (NSGA-II, Deb 2002)."""
    n = len(pop)
    dom_count = [0] * n
    dom_set: List[List[int]] = [[] for _ in range(n)]
    fronts: List[List[int]] = [[]]

    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            fi = pop[i]["_fitness"]
            fj = pop[j]["_fitness"]
            if _dominates(fi, fj):
                dom_set[i].append(j)
            elif _dominates(fj, fi):
                dom_count[i] += 1
        if dom_count[i] == 0:
            pop[i]["_rank"] = 0
            fronts[0].append(i)

    current_front = 0
    while fronts[current_front]:
        next_front: List[int] = []
        for i in fronts[current_front]:
            for j in dom_set[i]:
                dom_count[j] -= 1
                if dom_count[j] == 0:
                    pop[j]["_rank"] = current_front + 1
                    next_front.append(j)
        current_front += 1
        fronts.append(next_front)

    return [f for f in fronts if f]


def _crowding_distance(front: List[int], pop: List[Individual]) -> None:
    """Assign crowding distance to individuals in a Pareto front."""
    if len(front) <= 2:
        for i in front:
            pop[i]["_crowd"] = float("inf")
        return

    n_obj = len(pop[front[0]]["_fitness"])
    for i in front:
        pop[i]["_crowd"] = 0.0

    for obj_idx in range(n_obj):
        sorted_front = sorted(front, key=lambda i: pop[i]["_fitness"][obj_idx])
        pop[sorted_front[0]]["_crowd"] = float("inf")
        pop[sorted_front[-1]]["_crowd"] = float("inf")
        f_min = pop[sorted_front[0]]["_fitness"][obj_idx]
        f_max = pop[sorted_front[-1]]["_fitness"][obj_idx]
        span = (f_max - f_min) or 1.0
        for k in range(1, len(sorted_front) - 1):
            i = sorted_front[k]
            delta = (
                pop[sorted_front[k + 1]]["_fitness"][obj_idx]
                - pop[sorted_front[k - 1]]["_fitness"][obj_idx]
            )
            pop[i]["_crowd"] += delta / span


def _nsga2_select(pop: List[Individual], mu: int, rng: random.Random) -> List[Individual]:
    """NSGA-II tournament selection for the next generation."""
    fronts = _fast_nondominated_sort(pop)
    for front in fronts:
        _crowding_distance(front, pop)

    selected: List[Individual] = []
    for front in fronts:
        if len(selected) + len(front) <= mu:
            selected.extend(pop[i] for i in front)
        else:
            remaining = mu - len(selected)
            sorted_front = sorted(
                front,
                key=lambda i: (-pop[i].get("_rank", 0), -pop[i].get("_crowd", 0.0)),
            )
            selected.extend(pop[i] for i in sorted_front[:remaining])
            break
    return selected


@dataclass
class EvolutionResult:
    best_config: Dict[str, Any]
    best_fitness: Tuple[float, ...]
    generations_run: int
    population_size: int
    pareto_front: List[Dict[str, Any]] = field(default_factory=list)


class GeneticOptimizer:
    """
    Multi-objective genetic algorithm for worker parameter optimisation.

    Attempts to import DEAP for production-grade NSGA-II; falls back to the
    built-in pure-Python implementation. Both paths produce identical interfaces.

    Example::

        optimizer = GeneticOptimizer(
            fitness=LatencyThroughputFitness(),
            gene_space={
                "concurrency": (1, 32),
                "batch_size": (1, 128),
                "cache_ttl": (30, 3600),
            },
        )
        result = await optimizer.evolve(generations=50, pop_size=40)
        print(result.best_config)
    """

    def __init__(
        self,
        fitness: Optional[FitnessEvaluator] = None,
        gene_space: Optional[Dict[str, Tuple[float, float]]] = None,
        mutation_rate: float = 0.15,
        crossover_rate: float = 0.7,
        seed: Optional[int] = None,
    ) -> None:
        self._fitness = fitness or LatencyThroughputFitness()
        self._gene_space = gene_space or {
            "concurrency": (1.0, 32.0),
            "batch_size": (1.0, 128.0),
            "cache_ttl": (30.0, 3600.0),
        }
        self._mut_rate = mutation_rate
        self._cx_rate = crossover_rate
        self._rng = random.Random(seed)
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="genetics")

        # Try importing DEAP
        self._deap_available = False
        try:
            import deap  # noqa: F401
            self._deap_available = True
        except ImportError:
            pass

    def _random_individual(self) -> Individual:
        config: Dict[str, Any] = {}
        for key, (lo, hi) in self._gene_space.items():
            if isinstance(lo, int) and isinstance(hi, int):
                config[key] = self._rng.randint(int(lo), int(hi))
            else:
                config[key] = self._rng.uniform(float(lo), float(hi))
        return config

    def _evaluate(self, config: Individual) -> Individual:
        ind = copy.copy(config)
        ind.pop("_fitness", None)
        ind.pop("_rank", None)
        ind.pop("_crowd", None)
        fitness = self._fitness.evaluate(ind)
        result = copy.copy(config)
        result["_fitness"] = fitness
        return result

    def _mutate(self, config: Individual) -> Individual:
        child = copy.copy(config)
        for key, (lo, hi) in self._gene_space.items():
            if self._rng.random() < self._mut_rate:
                if isinstance(lo, int) and isinstance(hi, int):
                    child[key] = self._rng.randint(int(lo), int(hi))
                else:
                    span = float(hi) - float(lo)
                    child[key] = max(float(lo), min(float(hi), child[key] + self._rng.gauss(0, span * 0.1)))
        child.pop("_fitness", None)
        return child

    def _crossover(self, a: Individual, b: Individual) -> Tuple[Individual, Individual]:
        keys = list(self._gene_space.keys())
        cut = self._rng.randint(1, len(keys) - 1)
        child_a = {k: (a[k] if i < cut else b[k]) for i, k in enumerate(keys)}
        child_b = {k: (b[k] if i < cut else a[k]) for i, k in enumerate(keys)}
        return child_a, child_b

    def _evolve_sync(self, generations: int, pop_size: int) -> EvolutionResult:
        """Synchronous evolution loop — runs in executor thread."""
        if self._deap_available:
            return self._evolve_deap(generations, pop_size)
        return self._evolve_pure(generations, pop_size)

    def _evolve_pure(self, generations: int, pop_size: int) -> EvolutionResult:
        """Pure-Python NSGA-II evolution."""
        pop = [self._evaluate(self._random_individual()) for _ in range(pop_size)]

        for _ in range(generations):
            # Generate offspring
            offspring: List[Individual] = []
            while len(offspring) < pop_size:
                if self._rng.random() < self._cx_rate and len(pop) >= 2:
                    a, b = self._rng.sample(pop, 2)
                    c1, c2 = self._crossover(a, b)
                    offspring.extend([self._evaluate(self._mutate(c1)), self._evaluate(self._mutate(c2))])
                else:
                    parent = self._rng.choice(pop)
                    offspring.append(self._evaluate(self._mutate(parent)))

            combined = pop + offspring
            pop = _nsga2_select(combined, pop_size, self._rng)

        # Extract Pareto front (rank 0)
        fronts = _fast_nondominated_sort(pop)
        pareto: List[Individual] = []
        if fronts:
            pareto = [
                {k: v for k, v in pop[i].items() if not k.startswith("_")}
                for i in fronts[0]
            ]

        best = min(pop, key=lambda x: x["_fitness"])
        best_clean = {k: v for k, v in best.items() if not k.startswith("_")}
        return EvolutionResult(
            best_config=best_clean,
            best_fitness=best["_fitness"],
            generations_run=generations,
            population_size=pop_size,
            pareto_front=pareto,
        )

    def _evolve_deap(self, generations: int, pop_size: int) -> EvolutionResult:
        """DEAP-backed NSGA-II with proper crowding distance."""
        from deap import algorithms, base, creator, tools  # type: ignore

        # Re-create each time to avoid DEAP's global state issues
        if not hasattr(creator, "FitnessMultiGA"):
            n_obj = len(self._fitness.evaluate(self._random_individual()))
            weights = tuple(-1.0 for _ in range(n_obj))
            creator.create("FitnessMultiGA", base.Fitness, weights=weights)
            creator.create("IndividualGA", list, fitness=creator.FitnessMultiGA)

        toolbox = base.Toolbox()
        keys = list(self._gene_space.keys())

        def make_individual():
            vals = [
                self._rng.uniform(float(lo), float(hi))
                for _, (lo, hi) in self._gene_space.items()
            ]
            return creator.IndividualGA(vals)

        def evaluate_individual(ind):
            config = dict(zip(keys, ind, strict=False))
            return self._fitness.evaluate(config)

        toolbox.register("individual", make_individual)
        toolbox.register("population", tools.initRepeat, list, toolbox.individual)
        toolbox.register("evaluate", evaluate_individual)
        toolbox.register("mate", tools.cxSimulatedBinaryBounded,
                         low=[float(lo) for _, (lo, _) in self._gene_space.items()],
                         up=[float(hi) for _, (_, hi) in self._gene_space.items()],
                         eta=20.0)
        toolbox.register("mutate", tools.mutPolynomialBounded,
                         low=[float(lo) for _, (lo, _) in self._gene_space.items()],
                         up=[float(hi) for _, (_, hi) in self._gene_space.items()],
                         eta=20.0, indpb=self._mut_rate)
        toolbox.register("select", tools.selNSGA2)

        pop = toolbox.population(n=pop_size)
        for ind in pop:
            ind.fitness.values = toolbox.evaluate(ind)

        algorithms.eaMuPlusLambda(
            pop, toolbox,
            mu=pop_size, lambda_=pop_size,
            cxpb=self._cx_rate, mutpb=self._mut_rate,
            ngen=generations,
            stats=None, halloffame=None, verbose=False,
        )

        pareto_front = tools.sortNondominated(pop, len(pop), first_front_only=True)[0]
        best = tools.selBest(pop, k=1)[0]
        best_config = dict(zip(keys, best, strict=False))

        return EvolutionResult(
            best_config=best_config,
            best_fitness=tuple(best.fitness.values),
            generations_run=generations,
            population_size=pop_size,
            pareto_front=[dict(zip(keys, ind, strict=False)) for ind in pareto_front],
        )

    async def evolve(self, generations: int = 50, pop_size: int = 40) -> EvolutionResult:
        """Async wrapper — evolution runs in thread pool to avoid blocking event loop."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self._evolve_sync,
            generations,
            pop_size,
        )
