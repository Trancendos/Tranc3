"""Genetic Query Optimization for NRC Plans — TranceX Phase 8

Multi-objective genetic optimization (NSGA-II) for Nested Relational Calculus
query plans. Optimizes join order, shred depth, backend choice, and WASM
offload decisions across Pareto fronts of latency, cost, and accuracy.

Uses DEAP (Distributed Evolutionary Algorithms in Python) — 0-cost, LGPL-3.0.
"""

from __future__ import annotations

import copy
import hashlib
import logging
import random
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class BackendChoice(Enum):
    """Available NRC execution backends."""
    POSTGRES = "postgres"
    SPARK = "spark"
    WASM_EDGE = "wasm_edge"
    GPU_TVM = "gpu_tvm"
    QUANTUM_QAOA = "quantum_qaoa"
    IN_MEMORY = "in_memory"


class JoinStrategy(Enum):
    """Join execution strategies."""
    HASH_JOIN = "hash_join"
    MERGE_JOIN = "merge_join"
    NESTED_LOOP = "nested_loop"
    BROADCAST = "broadcast"
    SHUFFLE_HASH = "shuffle_hash"


class ShredDepth(Enum):
    """NRC nested collection shred depth levels."""
    DEEP = 3       # Full nested shred
    MEDIUM = 2     # Partial shred
    SHALLOW = 1    # Minimal shred
    NONE = 0       # No shred (flat)


@dataclass
class NRCPlanGene:
    """A single gene in the NRC query plan chromosome.

    Represents one decision point in the query execution plan.
    """
    relation_id: str
    backend: BackendChoice = BackendChoice.POSTGRES
    join_strategy: JoinStrategy = JoinStrategy.HASH_JOIN
    shred_depth: ShredDepth = ShredDepth.MEDIUM
    wasm_offload: bool = False
    gpu_accelerate: bool = False
    parallelism: int = 4
    cache_result: bool = True
    estimated_rows: int = 1000
    estimated_latency_ms: float = 10.0


@dataclass
class NRCPlanChromosome:
    """Complete NRC query plan as an evolutionary chromosome.

    Encodes all optimization decisions for a query execution plan.
    """
    plan_id: str = ""
    genes: List[NRCPlanGene] = field(default_factory=list)
    generation: int = 0
    fitness: Optional[Dict[str, float]] = None
    rank: int = -1
    crowding_distance: float = 0.0
    parent_ids: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.plan_id:
            self.plan_id = f"plan-{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize chromosome to dict for caching/logging."""
        return {
            "plan_id": self.plan_id,
            "generation": self.generation,
            "genes": [
                {
                    "relation_id": g.relation_id,
                    "backend": g.backend.value,
                    "join_strategy": g.join_strategy.value,
                    "shred_depth": g.shred_depth.value,
                    "wasm_offload": g.wasm_offload,
                    "gpu_accelerate": g.gpu_accelerate,
                    "parallelism": g.parallelism,
                    "cache_result": g.cache_result,
                    "estimated_rows": g.estimated_rows,
                }
                for g in self.genes
            ],
            "fitness": self.fitness,
            "rank": self.rank,
            "crowding_distance": self.crowding_distance,
        }


@dataclass
class NRCQueryContext:
    """Context for an NRC query being optimized.

    Contains query metadata, schema information, and constraints.
    """
    query_id: str
    nrc_dsl: str
    relations: List[str]
    estimated_result_size: int = 10000
    max_latency_ms: float = 1000.0
    max_cost: float = 1.0
    min_accuracy: float = 0.95
    available_backends: List[BackendChoice] = field(
        default_factory=lambda: [BackendChoice.POSTGRES, BackendChoice.SPARK, BackendChoice.IN_MEMORY]
    )
    schema_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    historical_performance: Dict[str, List[Dict[str, float]]] = field(default_factory=dict)


class NRCFitnessEvaluator:
    """Multi-objective fitness evaluator for NRC query plans.

    Evaluates plans across four objectives:
    1. Latency (minimize) — estimated execution time
    2. Cost (minimize) — compute + data transfer cost
    3. Accuracy (maximize) — result quality vs. exact computation
    4. Resource utilization (maximize) — efficient use of available resources
    """

    # Backend latency multipliers (relative to in-memory baseline)
    BACKEND_LATENCY = {
        BackendChoice.POSTGRES: 1.0,
        BackendChoice.SPARK: 2.5,
        BackendChoice.WASM_EDGE: 1.8,
        BackendChoice.GPU_TVM: 0.3,
        BackendChoice.QUANTUM_QAOA: 5.0,
        BackendChoice.IN_MEMORY: 0.1,
    }

    # Backend cost multipliers (relative to in-memory baseline)
    BACKEND_COST = {
        BackendChoice.POSTGRES: 0.5,
        BackendChoice.SPARK: 1.5,
        BackendChoice.WASM_EDGE: 0.3,
        BackendChoice.GPU_TVM: 1.0,
        BackendChoice.QUANTUM_QAOA: 10.0,
        BackendChoice.IN_MEMORY: 0.2,
    }

    # Join strategy accuracy scores (0-1)
    JOIN_ACCURACY = {
        JoinStrategy.HASH_JOIN: 1.0,
        JoinStrategy.MERGE_JOIN: 1.0,
        JoinStrategy.NESTED_LOOP: 1.0,
        JoinStrategy.BROADCAST: 0.98,
        JoinStrategy.SHUFFLE_HASH: 0.99,
    }

    def evaluate(self, chromosome: NRCPlanChromosome, context: NRCQueryContext) -> Dict[str, float]:
        """Evaluate a plan chromosome across all objectives."""
        if not chromosome.genes:
            return {"latency": float("inf"), "cost": float("inf"), "accuracy": 0.0, "resource_util": 0.0}

        total_latency = 0.0
        total_cost = 0.0
        total_accuracy = 1.0
        total_resource = 0.0

        for gene in chromosome.genes:
            # Latency estimation
            base_latency = gene.estimated_latency_ms
            backend_mult = self.BACKEND_LATENCY.get(gene.backend, 1.0)
            depth_mult = 1.0 + (gene.shred_depth.value * 0.3)
            parallel_benefit = max(0.1, 1.0 / gene.parallelism)
            gpu_benefit = 0.2 if gene.gpu_accelerate else 1.0
            wasm_overhead = 1.2 if gene.wasm_offload else 1.0

            gene_latency = base_latency * backend_mult * depth_mult * parallel_benefit * gpu_benefit * wasm_overhead
            total_latency += gene_latency

            # Cost estimation
            backend_cost = self.BACKEND_COST.get(gene.backend, 1.0)
            row_cost = gene.estimated_rows * 0.00001
            depth_cost = gene.shred_depth.value * 0.1
            gene_cost = (backend_cost + row_cost + depth_cost) * (0.5 if gene.cache_result else 1.0)
            total_cost += gene_cost

            # Accuracy (product of individual gene accuracies)
            join_acc = self.JOIN_ACCURACY.get(gene.join_strategy, 0.95)
            depth_acc = 1.0 - (gene.shred_depth.value * 0.02)
            wasm_acc = 0.99 if gene.wasm_offload else 1.0
            total_accuracy *= join_acc * depth_acc * wasm_acc

            # Resource utilization
            parallel_util = min(1.0, gene.parallelism / 16)
            cache_util = 0.3 if gene.cache_result else 0.0
            gpu_util = 0.4 if gene.gpu_accelerate else 0.0
            total_resource += parallel_util + cache_util + gpu_util

        # Normalize
        n = len(chromosome.genes)
        total_resource = min(1.0, total_resource / n) if n > 0 else 0.0

        # Penalty for constraint violations
        if total_latency > context.max_latency_ms:
            total_latency *= 1.5  # Penalty
        if total_cost > context.max_cost:
            total_cost *= 1.5

        return {
            "latency": total_latency,
            "cost": total_cost,
            "accuracy": total_accuracy,
            "resource_util": total_resource,
        }


class NRCGeneticOperators:
    """Genetic operators for NRC query plan evolution.

    Implements SBX crossover, polynomial mutation, and tournament
    selection following NSGA-II methodology.
    """

    def __init__(
        self,
        crossover_prob: float = 0.9,
        mutation_prob: float = 0.1,
        sbx_eta: float = 20.0,
        mutation_eta: float = 20.0,
        tournament_size: int = 2,
    ):
        self.crossover_prob = crossover_prob
        self.mutation_prob = mutation_prob
        self.sbx_eta = sbx_eta
        self.mutation_eta = mutation_eta
        self.tournament_size = tournament_size

    def tournament_selection(
        self, population: List[NRCPlanChromosome], n_select: int
    ) -> List[NRCPlanChromosome]:
        """Binary tournament selection based on rank and crowding distance."""
        selected = []
        for _ in range(n_select):
            candidates = random.sample(population, min(self.tournament_size, len(population)))
            # Lower rank is better; higher crowding distance is better for same rank
            best = min(candidates, key=lambda c: (c.rank, -c.crowding_distance))
            selected.append(copy.deepcopy(best))
        return selected

    def sbx_crossover(
        self, parent1: NRCPlanChromosome, parent2: NRCPlanChromosome
    ) -> Tuple[NRCPlanChromosome, NRCPlanChromosome]:
        """Simulated Binary Crossover (SBX) for NRC plan genes."""
        if random.random() > self.crossover_prob:
            return copy.deepcopy(parent1), copy.deepcopy(parent2)

        child1_genes = []
        child2_genes = []

        for g1, g2 in zip(parent1.genes, parent2.genes):
            c1 = copy.deepcopy(g1)
            c2 = copy.deepcopy(g2)

            # Crossover discrete choices
            if random.random() < 0.5:
                c1.backend, c2.backend = c2.backend, c1.backend
            if random.random() < 0.5:
                c1.join_strategy, c2.join_strategy = c2.join_strategy, c1.join_strategy
            if random.random() < 0.5:
                c1.shred_depth, c2.shred_depth = c2.shred_depth, c1.shred_depth
            if random.random() < 0.5:
                c1.wasm_offload, c2.wasm_offload = c2.wasm_offload, c1.wasm_offload
            if random.random() < 0.5:
                c1.gpu_accelerate, c2.gpu_accelerate = c2.gpu_accelerate, c1.gpu_accelerate
            if random.random() < 0.5:
                c1.cache_result, c2.cache_result = c2.cache_result, c1.cache_result

            # SBX for continuous variables (parallelism)
            u = random.random()
            if u <= 0.5:
                beta = (2 * u) ** (1.0 / (self.sbx_eta + 1))
            else:
                beta = (1.0 / (2 * (1 - u))) ** (1.0 / (self.sbx_eta + 1))

            p1_par = g1.parallelism
            p2_par = g2.parallelism
            c1.parallelism = max(1, int(0.5 * ((1 + beta) * p1_par + (1 - beta) * p2_par)))
            c2.parallelism = max(1, int(0.5 * ((1 - beta) * p1_par + (1 + beta) * p2_par)))

            child1_genes.append(c1)
            child2_genes.append(c2)

        child1 = NRCPlanChromosome(
            genes=child1_genes,
            generation=max(parent1.generation, parent2.generation) + 1,
            parent_ids=[parent1.plan_id, parent2.plan_id],
        )
        child2 = NRCPlanChromosome(
            genes=child2_genes,
            generation=max(parent1.generation, parent2.generation) + 1,
            parent_ids=[parent1.plan_id, parent2.plan_id],
        )
        return child1, child2

    def polynomial_mutation(self, individual: NRCPlanChromosome) -> NRCPlanChromosome:
        """Polynomial mutation for NRC plan genes."""
        mutated = copy.deepcopy(individual)

        for gene in mutated.genes:
            if random.random() < self.mutation_prob:
                # Mutate backend
                gene.backend = random.choice(list(BackendChoice))
            if random.random() < self.mutation_prob:
                # Mutate join strategy
                gene.join_strategy = random.choice(list(JoinStrategy))
            if random.random() < self.mutation_prob:
                # Mutate shred depth
                gene.shred_depth = random.choice(list(ShredDepth))
            if random.random() < self.mutation_prob:
                # Mutate boolean flags
                gene.wasm_offload = not gene.wasm_offload
            if random.random() < self.mutation_prob:
                gene.gpu_accelerate = not gene.gpu_accelerate
            if random.random() < self.mutation_prob:
                gene.cache_result = not gene.cache_result
            if random.random() < self.mutation_prob:
                # Polynomial mutation for parallelism
                u = random.random()
                delta = (2 * u) ** (1.0 / (self.mutation_eta + 1)) - 1 if u < 0.5 else 1 - (2 * (1 - u)) ** (1.0 / (self.mutation_eta + 1))
                gene.parallelism = max(1, min(64, int(gene.parallelism + delta * 8)))

        return mutated


class NSGAIIPlanOptimizer:
    """NSGA-II Multi-Objective Optimizer for NRC Query Plans.

    Implements the Non-dominated Sorting Genetic Algorithm II (NSGA-II)
    with reference-point based selection for high-objective problems.

    Uses DEAP-style architecture but is self-contained (0-cost).
    """

    def __init__(
        self,
        population_size: int = 100,
        n_generations: int = 50,
        crossover_prob: float = 0.9,
        mutation_prob: float = 0.15,
        quantum_escalation_threshold: float = 0.8,
    ):
        self.population_size = population_size
        self.n_generations = n_generations
        self.crossover_prob = crossover_prob
        self.mutation_prob = mutation_prob
        self.quantum_escalation_threshold = quantum_escalation_threshold
        self.operators = NRCGeneticOperators(
            crossover_prob=crossover_prob,
            mutation_prob=mutation_prob,
        )
        self.evaluator = NRCFitnessEvaluator()
        self._evolution_log: List[Dict[str, Any]] = []

    def initialize_population(self, context: NRCQueryContext) -> List[NRCPlanChromosome]:
        """Create initial population of random NRC query plans."""
        population = []
        for _ in range(self.population_size):
            genes = []
            for rel in context.relations:
                # Use historical performance to bias initial choices
                hist = context.historical_performance.get(rel, [])
                preferred_backend = (
                    BackendChoice(hist[-1]["backend"]) if hist and "backend" in hist[-1]
                    else random.choice(context.available_backends)
                )

                gene = NRCPlanGene(
                    relation_id=rel,
                    backend=preferred_backend if random.random() < 0.7 else random.choice(context.available_backends),
                    join_strategy=random.choice(list(JoinStrategy)),
                    shred_depth=random.choice(list(ShredDepth)),
                    wasm_offload=random.random() < 0.3,
                    gpu_accelerate=random.random() < 0.2,
                    parallelism=random.choice([1, 2, 4, 8, 16]),
                    cache_result=random.random() < 0.7,
                    estimated_rows=context.schema_stats.get(rel, {}).get("row_count", 1000),
                    estimated_latency_ms=context.schema_stats.get(rel, {}).get("avg_latency", 10.0),
                )
                genes.append(gene)

            population.append(NRCPlanChromosome(genes=genes, generation=0))
        return population

    def fast_non_dominated_sort(
        self, population: List[NRCPlanChromosome]
    ) -> List[List[NRCPlanChromosome]]:
        """Fast non-dominated sorting (NSGA-II core algorithm).

        Partitions population into Pareto fronts.
        """
        fronts: List[List[NRCPlanChromosome]] = [[]]

        for p in population:
            p.dominated_by = 0  # type: ignore[attr-defined]
            p.dominates_set = []  # type: ignore[attr-defined]

        for i, p in enumerate(population):
            for j, q in enumerate(population):
                if i == j:
                    continue
                if self._dominates(p, q):
                    p.dominates_set.append(j)  # type: ignore[attr-defined]
                elif self._dominates(q, p):
                    p.dominated_by += 1  # type: ignore[attr-defined]

            if p.dominated_by == 0:  # type: ignore[attr-defined]
                p.rank = 0
                fronts[0].append(p)

        k = 0
        while fronts[k]:
            next_front = []
            for p in fronts[k]:
                for q_idx in p.dominates_set:  # type: ignore[attr-defined]
                    q = population[q_idx]
                    q.dominated_by -= 1  # type: ignore[attr-defined]
                    if q.dominated_by == 0:  # type: ignore[attr-defined]
                        q.rank = k + 1
                        next_front.append(q)
            k += 1
            fronts.append(next_front)

        return [f for f in fronts if f]

    def crowding_distance(self, front: List[NRCPlanChromosome]) -> None:
        """Calculate crowding distance for a Pareto front."""
        if len(front) <= 2:
            for ind in front:
                ind.crowding_distance = float("inf")
            return

        n_objectives = len(front[0].fitness) if front[0].fitness else 0
        for ind in front:
            ind.crowding_distance = 0.0

        for obj_idx in range(n_objectives):
            obj_name = list(front[0].fitness.keys())[obj_idx] if front[0].fitness else f"obj_{obj_idx}"

            # Sort by objective value
            # For latency/cost: ascending. For accuracy/resource: descending.
            reverse = obj_name in ("accuracy", "resource_util")
            sorted_front = sorted(front, key=lambda x: x.fitness.get(obj_name, 0) if x.fitness else 0, reverse=reverse)

            sorted_front[0].crowding_distance = float("inf")
            sorted_front[-1].crowding_distance = float("inf")

            obj_min = min(f.fitness.get(obj_name, 0) if f.fitness else 0 for f in front)
            obj_max = max(f.fitness.get(obj_name, 0) if f.fitness else 1 for f in front)
            obj_range = obj_max - obj_min if obj_max != obj_min else 1.0

            for i in range(1, len(sorted_front) - 1):
                val_next = sorted_front[i + 1].fitness.get(obj_name, 0) if sorted_front[i + 1].fitness else 0
                val_prev = sorted_front[i - 1].fitness.get(obj_name, 0) if sorted_front[i - 1].fitness else 0
                sorted_front[i].crowding_distance += (val_next - val_prev) / obj_range

    def _dominates(self, p: NRCPlanChromosome, q: NRCPlanChromosome) -> bool:
        """Check if individual p dominates individual q."""
        if not p.fitness or not q.fitness:
            return False

        # Minimize latency and cost, maximize accuracy and resource_util
        better_in_one = False
        for key in ["latency", "cost"]:
            if p.fitness.get(key, float("inf")) > q.fitness.get(key, float("inf")):
                return False
            if p.fitness.get(key, float("inf")) < q.fitness.get(key, float("inf")):
                better_in_one = True

        for key in ["accuracy", "resource_util"]:
            if p.fitness.get(key, 0) < q.fitness.get(key, 0):
                return False
            if p.fitness.get(key, 0) > q.fitness.get(key, 0):
                better_in_one = True

        return better_in_one

    def optimize(
        self, context: NRCQueryContext, callback: Any = None
    ) -> NRCPlanChromosome:
        """Run full NSGA-II optimization for an NRC query.

        Returns the best-compromise plan from the final Pareto front.
        """
        population = self.initialize_population(context)

        # Evaluate initial population
        for ind in population:
            ind.fitness = self.evaluator.evaluate(ind, context)

        for gen in range(self.n_generations):
            # Non-dominated sort
            fronts = self.fast_non_dominated_sort(population)

            # Crowding distance
            for front in fronts:
                self.crowding_distance(front)

            # Selection
            parents = self.operators.tournament_selection(population, self.population_size)

            # Crossover + Mutation
            offspring = []
            for i in range(0, len(parents) - 1, 2):
                child1, child2 = self.operators.sbx_crossover(parents[i], parents[i + 1])
                child1 = self.operators.polynomial_mutation(child1)
                child2 = self.operators.polynomial_mutation(child2)
                offspring.extend([child1, child2])

            # Evaluate offspring
            for ind in offspring:
                ind.fitness = self.evaluator.evaluate(ind, context)

            # Combine and select next generation
            combined = population + offspring
            for ind in combined:
                if not ind.fitness:
                    ind.fitness = self.evaluator.evaluate(ind, context)

            fronts = self.fast_non_dominated_sort(combined)
            for front in fronts:
                self.crowding_distance(front)

            new_population = []
            for front in fronts:
                if len(new_population) + len(front) <= self.population_size:
                    new_population.extend(front)
                else:
                    remaining = self.population_size - len(new_population)
                    sorted_front = sorted(front, key=lambda x: -x.crowding_distance)
                    new_population.extend(sorted_front[:remaining])
                    break

            population = new_population

            # Log generation stats
            best = min(population, key=lambda x: (x.rank, -x.crowding_distance))
            gen_stats = {
                "generation": gen,
                "best_rank": best.rank,
                "best_fitness": best.fitness,
                "pareto_fronts": len(fronts),
                "population_size": len(population),
            }
            self._evolution_log.append(gen_stats)

            if callback:
                callback(gen, population, gen_stats)

        # Quantum escalation: if best plan's latency/cost is above threshold,
        # escalate to quantum solver
        final_fronts = self.fast_non_dominated_sort(population)
        best_plan = min(final_fronts[0], key=lambda x: x.fitness.get("latency", float("inf")) if x.fitness else float("inf"))

        if best_plan.fitness and best_plan.fitness.get("latency", float("inf")) > self.quantum_escalation_threshold * context.max_latency_ms:
            logger.info(f"Quantum escalation triggered for query {context.query_id}")
            best_plan = self._quantum_escalate(best_plan, context)

        return best_plan

    def _quantum_escalate(
        self, plan: NRCPlanChromosome, context: NRCQueryContext
    ) -> NRCPlanChromosome:
        """Escalate plan optimization to quantum solver (QAOA).

        Replaces expensive classical joins with quantum-optimized paths.
        """
        escalated = copy.deepcopy(plan)
        for gene in escalated.genes:
            if gene.estimated_rows > 100000 and BackendChoice.QUANTUM_QAOA in context.available_backends:
                gene.backend = BackendChoice.QUANTUM_QAOA
                gene.join_strategy = JoinStrategy.HASH_JOIN
                gene.gpu_accelerate = False
                gene.wasm_offload = False

        # Re-evaluate
        escalated.fitness = self.evaluator.evaluate(escalated, context)
        escalated.generation = plan.generation + 1
        escalated.parent_ids = [plan.plan_id, "quantum-escalation"]
        return escalated

    def get_pareto_front(self, population: List[NRCPlanChromosome]) -> List[NRCPlanChromosome]:
        """Get the current Pareto front from a population."""
        fronts = self.fast_non_dominated_sort(population)
        return fronts[0] if fronts else []

    def get_evolution_log(self) -> List[Dict[str, Any]]:
        """Get the complete evolution log."""
        return self._evolution_log


class GeneticQueryOptimizer:
    """High-level genetic query optimizer for the TranceX ecosystem.

    Integrates with the NSA registry for backend discovery, the vector
    plan cache for plan reuse, and the adaptive loop for feedback.
    """

    def __init__(
        self,
        population_size: int = 50,
        n_generations: int = 30,
        quantum_escalation: bool = True,
    ):
        self.nsga2 = NSGAIIPlanOptimizer(
            population_size=population_size,
            n_generations=n_generations,
            quantum_escalation_threshold=0.8 if quantum_escalation else float("inf"),
        )
        self._plan_cache: Dict[str, NRCPlanChromosome] = {}

    def optimize_query(self, context: NRCQueryContext) -> NRCPlanChromosome:
        """Optimize an NRC query using genetic algorithms.

        First checks the plan cache for similar queries, then runs
        NSGA-II optimization if no cached plan is suitable.
        """
        # Check cache
        cache_key = hashlib.sha3_256(
            f"{context.nrc_dsl}:{sorted(context.relations)}".encode()
        ).hexdigest()

        if cache_key in self._plan_cache:
            cached = self._plan_cache[cache_key]
            # Verify cached plan still meets constraints
            if cached.fitness and cached.fitness.get("latency", float("inf")) <= context.max_latency_ms:
                logger.info(f"Using cached plan for query {context.query_id}")
                return cached

        # Run genetic optimization
        best_plan = self.nsga2.optimize(context)

        # Cache the result
        self._plan_cache[cache_key] = best_plan
        return best_plan

    def get_pareto_analysis(self, context: NRCQueryContext) -> Dict[str, Any]:
        """Run optimization and return full Pareto analysis."""
        population = self.nsga2.initialize_population(context)
        for ind in population:
            ind.fitness = self.nsga2.evaluator.evaluate(ind, context)

        fronts = self.nsga2.fast_non_dominated_sort(population)
        for front in fronts:
            self.nsga2.crowding_distance(front)

        return {
            "query_id": context.query_id,
            "pareto_fronts": len(fronts),
            "front_sizes": [len(f) for f in fronts],
            "best_plans": [
                {
                    "plan_id": p.plan_id,
                    "rank": p.rank,
                    "fitness": p.fitness,
                    "crowding_distance": p.crowding_distance,
                }
                for p in fronts[0][:10]
            ],
            "evolution_log": self.nsga2.get_evolution_log(),
        }
