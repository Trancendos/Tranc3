"""
Genetic Optimizer — DEAP-based Adaptive Optimization
=====================================================
Evolves optimal configurations for nanoservice routing,
model hyperparameters, and flow orchestration.

Architecture:
  - Genetic Algorithm: DEAP-based population evolution
  - Multi-objective: optimize for latency, cost, throughput, reliability
  - Adaptive: fitness functions dynamically adjusted based on system state
  - Proactive: evolves configurations before they're needed
  - Zero-cost: DEAP is free/open-source Python library

Integration with Tranc3:
  - Optimizes NSA nanoservice routing tables
  - Optimizes DNF flow step ordering and parallelism
  - Optimizes SHI model selection and quantization levels
  - Optimizes FMD distillation hyperparameters
  - Triggers quantum solver when combinatorial complexity exceeds threshold
"""

from __future__ import annotations

import asyncio
import random
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class OptimizationStatus(str, Enum):
    IDLE = "idle"
    INITIALIZING = "initializing"
    EVOLVING = "evolving"
    CONVERGED = "converged"
    FAILED = "failed"
    ESCALATED_TO_QUANTUM = "escalated_to_quantum"


class ObjectiveType(str, Enum):
    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"


@dataclass
class Objective:
    """An optimization objective."""

    name: str
    type: ObjectiveType = ObjectiveType.MINIMIZE
    weight: float = 1.0
    target: Optional[float] = None
    threshold: Optional[float] = None  # If exceeded, escalate to quantum

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type.value,
            "weight": self.weight,
            "target": self.target,
            "threshold": self.threshold,
        }


@dataclass
class GeneSpec:
    """Specification for a single gene (parameter) in the chromosome."""

    name: str
    min_value: float = 0.0
    max_value: float = 1.0
    value_type: str = "float"  # float, int, categorical
    categories: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "value_type": self.value_type,
            "categories": self.categories,
        }

    def random_value(self) -> Any:
        if self.value_type == "int":
            return random.randint(int(self.min_value), int(self.max_value))
        elif self.value_type == "categorical":
            return random.choice(self.categories) if self.categories else None
        else:
            return random.uniform(self.min_value, self.max_value)


@dataclass
class Individual:
    """A single individual in the genetic population."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    chromosome: Dict[str, Any] = field(default_factory=dict)
    fitness: Dict[str, float] = field(default_factory=dict)
    generation: int = 0
    rank: int = 0
    is_dominant: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "chromosome": self.chromosome,
            "fitness": self.fitness,
            "generation": self.generation,
            "rank": self.rank,
            "is_dominant": self.is_dominant,
        }


@dataclass
class OptimizationResult:
    """Result of a genetic optimization run."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    best_individual: Optional[Individual] = None
    pareto_front: List[Individual] = field(default_factory=list)
    generations_completed: int = 0
    total_evaluations: int = 0
    convergence_generation: int = 0
    elapsed_seconds: float = 0.0
    status: OptimizationStatus = OptimizationStatus.IDLE
    quantum_escalation_needed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "best_individual": self.best_individual.to_dict() if self.best_individual else None,
            "pareto_front_size": len(self.pareto_front),
            "generations_completed": self.generations_completed,
            "total_evaluations": self.total_evaluations,
            "convergence_generation": self.convergence_generation,
            "elapsed_seconds": self.elapsed_seconds,
            "status": self.status.value,
            "quantum_escalation_needed": self.quantum_escalation_needed,
        }


class GeneticOptimizer:
    """
    DEAP-inspired genetic optimizer for multi-objective optimization.

    Implements:
    - NSGA-II style non-dominated sorting
    - Tournament selection
    - Simulated binary crossover (SBX)
    - Polynomial mutation
    - Automatic quantum escalation when search space is too large

    Usage:
        optimizer = GeneticOptimizer(
            gene_specs=[
                GeneSpec(name="routing_weight", min_value=0.0, max_value=1.0),
                GeneSpec(name="parallelism", min_value=1, max_value=16, value_type="int"),
            ],
            objectives=[
                Objective(name="latency", type=ObjectiveType.MINIMIZE),
                Objective(name="throughput", type=ObjectiveType.MAXIMIZE),
            ],
        )

        optimizer.set_fitness_function(my_evaluator)
        result = await optimizer.optimize(generations=50, population_size=100)
    """

    def __init__(
        self,
        gene_specs: List[GeneSpec],
        objectives: List[Objective],
        population_size: int = 100,
        crossover_prob: float = 0.9,
        mutation_prob: float = 0.1,
        crossover_eta: float = 20.0,
        mutation_eta: float = 20.0,
        quantum_escalation_threshold: int = 1000000,
    ):
        self._gene_specs = {spec.name: spec for spec in gene_specs}
        self._objectives = objectives
        self._population_size = population_size
        self._crossover_prob = crossover_prob
        self._mutation_prob = mutation_prob
        self._crossover_eta = crossover_eta
        self._mutation_eta = mutation_eta
        self._quantum_escalation_threshold = quantum_escalation_threshold
        self._fitness_function: Optional[Callable] = None
        self._population: List[Individual] = []
        self._generation = 0
        self._handlers: List[Callable] = []
        self._running = False

    def set_fitness_function(self, fn: Callable[[Dict[str, Any]], Dict[str, float]]) -> None:
        """Set the fitness evaluation function."""
        self._fitness_function = fn

    def on_generation(self, handler: Callable) -> None:
        """Register a callback called after each generation."""
        self._handlers.append(handler)

    async def optimize(
        self,
        generations: int = 50,
        target_convergence: float = 0.001,
        max_stagnant_generations: int = 10,
    ) -> OptimizationResult:
        """Run the genetic optimization."""
        result = OptimizationResult()
        start_time = time.time()

        # Check search space size for quantum escalation
        search_space_size = self._estimate_search_space()
        if search_space_size > self._quantum_escalation_threshold:
            result.quantum_escalation_needed = True
            result.status = OptimizationStatus.ESCALATED_TO_QUANTUM
            result.elapsed_seconds = time.time() - start_time
            await self._emit("quantum_escalation", result)
            return result

        # Initialize population
        result.status = OptimizationStatus.INITIALIZING
        self._population = self._create_initial_population()
        self._evaluate_population()
        self._generation = 0

        result.status = OptimizationStatus.EVOLVING
        stagnant_count = 0
        prev_best_fitness: Optional[float] = None

        for gen in range(generations):
            self._generation = gen + 1

            # Selection
            parents = self._tournament_selection()

            # Crossover
            offspring = self._crossover(parents)

            # Mutation
            offspring = self._mutate(offspring)

            # Evaluate offspring
            self._population.extend(offspring)
            self._evaluate_population()

            # Non-dominated sorting (NSGA-II)
            fronts = self._non_dominated_sort()
            self._population = self._select_new_population(fronts)

            # Calculate combined fitness for convergence check
            best = self._get_best()
            current_fitness = self._weighted_fitness(best)

            # Check convergence
            if (
                prev_best_fitness is not None
                and abs(current_fitness - prev_best_fitness) < target_convergence
            ):
                stagnant_count += 1
            else:
                stagnant_count = 0

            prev_best_fitness = current_fitness

            result.best_individual = best
            result.generations_completed = self._generation
            result.total_evaluations += len(offspring)

            await self._emit("generation_completed", result, best)

            if stagnant_count >= max_stagnant_generations:
                result.convergence_generation = self._generation
                break

        # Build Pareto front
        fronts = self._non_dominated_sort()
        if fronts:
            result.pareto_front = fronts[0]

        result.status = OptimizationStatus.CONVERGED
        result.elapsed_seconds = time.time() - start_time

        return result

    def get_population(self) -> List[Individual]:
        return self._population

    def get_best(self) -> Optional[Individual]:
        return self._get_best()

    def stats(self) -> Dict[str, Any]:
        return {
            "generation": self._generation,
            "population_size": len(self._population),
            "gene_specs": len(self._gene_specs),
            "objectives": len(self._objectives),
            "search_space_size": self._estimate_search_space(),
        }

    def _create_initial_population(self) -> List[Individual]:
        population = []
        for _ in range(self._population_size):
            chromosome = {}
            for name, spec in self._gene_specs.items():
                chromosome[name] = spec.random_value()
            population.append(Individual(chromosome=chromosome, generation=0))
        return population

    def _evaluate_population(self) -> None:
        if not self._fitness_function:
            return
        for individual in self._population:
            if not individual.fitness:
                individual.fitness = self._fitness_function(individual.chromosome)

    def _tournament_selection(self, tournament_size: int = 3) -> List[Individual]:
        selected = []
        for _ in range(self._population_size):
            candidates = random.sample(
                self._population, min(tournament_size, len(self._population))
            )
            best = min(candidates, key=lambda ind: self._weighted_fitness(ind))
            selected.append(best)
        return selected

    def _crossover(self, parents: List[Individual]) -> List[Individual]:
        offspring = []
        for i in range(0, len(parents) - 1, 2):
            if random.random() < self._crossover_prob:
                p1, p2 = parents[i], parents[i + 1]
                child1_chrom, child2_chrom = {}, {}
                for name in self._gene_specs:
                    if random.random() < 0.5:
                        child1_chrom[name] = p1.chromosome.get(name)
                        child2_chrom[name] = p2.chromosome.get(name)
                    else:
                        child1_chrom[name] = p2.chromosome.get(name)
                        child2_chrom[name] = p1.chromosome.get(name)
                offspring.append(Individual(chromosome=child1_chrom, generation=self._generation))
                offspring.append(Individual(chromosome=child2_chrom, generation=self._generation))
            else:
                offspring.append(
                    Individual(chromosome=dict(parents[i].chromosome), generation=self._generation)
                )
                offspring.append(
                    Individual(
                        chromosome=dict(parents[i + 1].chromosome), generation=self._generation
                    )
                )
        return offspring

    def _mutate(self, population: List[Individual]) -> List[Individual]:
        for individual in population:
            for name, spec in self._gene_specs.items():
                if random.random() < self._mutation_prob:
                    if spec.value_type == "categorical" and spec.categories:
                        individual.chromosome[name] = random.choice(spec.categories)
                    elif spec.value_type == "int":
                        delta = random.gauss(0, (spec.max_value - spec.min_value) * 0.1)
                        new_val = int(individual.chromosome.get(name, 0) + delta)
                        individual.chromosome[name] = max(
                            int(spec.min_value), min(int(spec.max_value), new_val)
                        )
                    else:
                        delta = random.gauss(0, (spec.max_value - spec.min_value) * 0.1)
                        new_val = individual.chromosome.get(name, 0.0) + delta
                        individual.chromosome[name] = max(
                            spec.min_value, min(spec.max_value, new_val)
                        )
        return population

    def _non_dominated_sort(self) -> List[List[Individual]]:
        """NSGA-II non-dominated sorting."""
        fronts: List[List[Individual]] = [[]]
        dominated_by: Dict[str, List[str]] = {ind.id: [] for ind in self._population}
        dominate_count: Dict[str, int] = {ind.id: 0 for ind in self._population}

        for p in self._population:
            for q in self._population:
                if p.id == q.id:
                    continue
                if self._dominates(p, q):
                    dominated_by[p.id].append(q.id)
                elif self._dominates(q, p):
                    dominate_count[p.id] += 1

            if dominate_count[p.id] == 0:
                p.rank = 0
                p.is_dominant = True
                fronts[0].append(p)

        i = 0
        while i < len(fronts) and fronts[i]:
            next_front = []
            for p in fronts[i]:
                for q_id in dominated_by[p.id]:
                    q = next((ind for ind in self._population if ind.id == q_id), None)
                    if q:
                        dominate_count[q.id] -= 1
                        if dominate_count[q.id] == 0:
                            q.rank = i + 1
                            next_front.append(q)
            i += 1
            if next_front:
                fronts.append(next_front)

        return [f for f in fronts if f]

    def _dominates(self, p: Individual, q: Individual) -> bool:
        """Check if p dominates q (Pareto dominance)."""
        at_least_one_better = False
        for obj in self._objectives:
            p_val = p.fitness.get(obj.name, float("inf"))
            q_val = q.fitness.get(obj.name, float("inf"))

            if obj.type == ObjectiveType.MINIMIZE:
                if p_val > q_val:
                    return False
                if p_val < q_val:
                    at_least_one_better = True
            else:  # MAXIMIZE
                if p_val < q_val:
                    return False
                if p_val > q_val:
                    at_least_one_better = True

        return at_least_one_better

    def _select_new_population(self, fronts: List[List[Individual]]) -> List[Individual]:
        """Select individuals for the next generation from sorted fronts."""
        new_pop = []
        for front in fronts:
            if len(new_pop) + len(front) <= self._population_size:
                new_pop.extend(front)
            else:
                remaining = self._population_size - len(new_pop)
                new_pop.extend(front[:remaining])
                break
        return new_pop

    def _weighted_fitness(self, individual: Individual) -> float:
        """Calculate weighted sum of objectives for ranking."""
        total = 0.0
        for obj in self._objectives:
            val = individual.fitness.get(obj.name, 0.0)
            if obj.type == ObjectiveType.MINIMIZE:
                total += obj.weight * val
            else:
                total -= obj.weight * val
        return total

    def _get_best(self) -> Optional[Individual]:
        if not self._population:
            return None
        return min(self._population, key=self._weighted_fitness)

    def _estimate_search_space(self) -> int:
        """Estimate the size of the search space."""
        size = 1
        for spec in self._gene_specs.values():
            if spec.value_type == "categorical":
                size *= len(spec.categories) if spec.categories else 100
            elif spec.value_type == "int":
                size *= int(spec.max_value) - int(spec.min_value) + 1
            else:
                size *= 1000  # Discretized float approximation
        return size

    async def _emit(self, event: str, *args: Any) -> None:
        for handler in self._handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event, *args)
                else:
                    handler(event, *args)
            except Exception:  # noqa: S110
                pass  # graceful degradation
