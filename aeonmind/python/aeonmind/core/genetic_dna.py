"""
AeonMind Genetic DNA Evolution Engine — Python Implementation.

Implements evolutionary algorithms for agent policy optimization.
DNA is represented as a real-valued vector. Uses DEAP-style
tournament selection, crossover, and mutation operators.
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np


@dataclass
class GeneticConfig:
    """Configuration for the DNA Evolution Engine."""

    population_size: int = 50
    dna_length: int = 32
    mutation_rate: float = 0.1
    mutation_strength: float = 0.5
    crossover_rate: float = 0.7
    tournament_size: int = 3
    elitism_count: int = 2
    max_generations: int = 100
    diversity_threshold: float = 0.1
    adaptive_mutation: bool = True
    dna_range: Tuple[float, float] = (-1.0, 1.0)


@dataclass
class Individual:
    """An individual in the evolutionary population."""

    dna: np.ndarray
    fitness: float = float("-inf")
    age: int = 0
    metadata: Dict = field(default_factory=dict)

    @property
    def dna_list(self) -> List[float]:
        return self.dna.tolist()


@dataclass
class GenerationStats:
    """Statistics for a single generation."""

    generation: int
    best_fitness: float
    worst_fitness: float
    avg_fitness: float
    std_fitness: float
    diversity: float


class DNAEvolutionEngine:
    """DNA Evolution Engine for agent policy optimization.

    Uses tournament selection, uniform/blended crossover, and
    Gaussian mutation with adaptive mutation rates. Maintains
    population diversity through injection and elitism.
    """

    def __init__(self, config: Optional[GeneticConfig] = None):
        self.config = config or GeneticConfig()
        self.population: List[Individual] = []
        self.generation = 0
        self._best_ever: Optional[Individual] = None
        self._stats_history: List[GenerationStats] = []
        self._initialize_population()

    def _initialize_population(self) -> None:
        """Create the initial random population."""
        self.population = []
        low, high = self.config.dna_range
        for _ in range(self.config.population_size):
            dna = np.random.uniform(low, high, self.config.dna_length)
            self.population.append(Individual(dna=dna))

    def evaluate(self, fitness_fn: Callable[[np.ndarray], float]) -> None:
        """Evaluate all individuals in the population."""
        for ind in self.population:
            ind.fitness = fitness_fn(ind.dna)
            if self._best_ever is None or ind.fitness > self._best_ever.fitness:
                self._best_ever = copy.deepcopy(ind)

    def tournament_select(self) -> Individual:
        """Select an individual using tournament selection."""
        candidates = random.sample(
            self.population, min(self.config.tournament_size, len(self.population))
        )
        return max(candidates, key=lambda ind: ind.fitness)

    def crossover(self, parent1: Individual, parent2: Individual) -> Tuple[Individual, Individual]:
        """Perform blended crossover between two parents."""
        if random.random() > self.config.crossover_rate:
            return copy.deepcopy(parent1), copy.deepcopy(parent2)

        # Blended crossover
        alpha = random.random()
        dna1 = alpha * parent1.dna + (1 - alpha) * parent2.dna
        dna2 = (1 - alpha) * parent1.dna + alpha * parent2.dna

        child1 = Individual(dna=dna1)
        child2 = Individual(dna=dna2)
        return child1, child2

    def mutate(self, individual: Individual) -> Individual:
        """Apply Gaussian mutation to an individual's DNA."""
        dna = individual.dna.copy()
        for i in range(len(dna)):
            if random.random() < self.config.mutation_rate:
                dna[i] += np.random.normal(0, self.config.mutation_strength)
                # Clip to range
                low, high = self.config.dna_range
                dna[i] = np.clip(dna[i], low, high)
        individual.dna = dna
        return individual

    def adapt_mutation(self) -> None:
        """Adapt mutation rate based on population diversity."""
        if not self.config.adaptive_mutation:
            return
        diversity = self.population_diversity()
        if diversity < self.config.diversity_threshold:
            self.config.mutation_rate = min(0.5, self.config.mutation_rate * 1.2)
            self.config.mutation_strength = min(2.0, self.config.mutation_strength * 1.1)
        else:
            self.config.mutation_rate = max(0.01, self.config.mutation_rate * 0.95)
            self.config.mutation_strength = max(0.1, self.config.mutation_strength * 0.95)

    def evolve_generation(self) -> GenerationStats:
        """Evolve a single generation."""
        # Sort by fitness (descending)
        self.population.sort(key=lambda ind: ind.fitness, reverse=True)

        # Elitism: keep top individuals
        new_population = copy.deepcopy(self.population[: self.config.elitism_count])

        # Generate offspring
        while len(new_population) < self.config.population_size:
            parent1 = self.tournament_select()
            parent2 = self.tournament_select()
            child1, child2 = self.crossover(parent1, parent2)
            child1 = self.mutate(child1)
            child2 = self.mutate(child2)
            new_population.append(child1)
            if len(new_population) < self.config.population_size:
                new_population.append(child2)

        self.population = new_population
        self.generation += 1

        # Age all individuals
        for ind in self.population:
            ind.age += 1

        # Adapt mutation rate
        self.adapt_mutation()

        stats = self.compute_stats()
        self._stats_history.append(stats)
        return stats

    def evolve(
        self,
        fitness_fn: Callable[[np.ndarray], float],
        generations: Optional[int] = None,
        callback: Optional[Callable[[int, GenerationStats], None]] = None,
    ) -> GenerationStats:
        """Run evolution for multiple generations."""
        n_gens = generations or self.config.max_generations
        last_stats = None

        for _i in range(n_gens):
            self.evaluate(fitness_fn)
            last_stats = self.evolve_generation()
            if callback:
                callback(self.generation, last_stats)

        return last_stats

    def compute_stats(self) -> GenerationStats:
        """Compute population statistics."""
        fitnesses = [ind.fitness for ind in self.population if ind.fitness > float("-inf")]
        if not fitnesses:
            return GenerationStats(
                generation=self.generation,
                best_fitness=float("-inf"),
                worst_fitness=float("-inf"),
                avg_fitness=float("-inf"),
                std_fitness=0.0,
                diversity=0.0,
            )

        return GenerationStats(
            generation=self.generation,
            best_fitness=max(fitnesses),
            worst_fitness=min(fitnesses),
            avg_fitness=float(np.mean(fitnesses)),
            std_fitness=float(np.std(fitnesses)),
            diversity=self.population_diversity(),
        )

    def population_diversity(self) -> float:
        """Compute population diversity as average pairwise distance."""
        if len(self.population) < 2:
            return 0.0
        sample_size = min(20, len(self.population))
        sample = random.sample(self.population, sample_size)
        distances = []
        for i in range(len(sample)):
            for j in range(i + 1, len(sample)):
                dist = np.linalg.norm(sample[i].dna - sample[j].dna)
                distances.append(dist)
        return float(np.mean(distances)) if distances else 0.0

    def best_individual(self) -> Optional[Individual]:
        """Get the best individual in the current population."""
        if not self.population:
            return None
        return max(self.population, key=lambda ind: ind.fitness)

    def best_ever(self) -> Optional[Individual]:
        """Get the best individual ever seen."""
        return self._best_ever

    def inject_random(self, count: int = 5) -> None:
        """Inject random individuals to maintain diversity."""
        low, high = self.config.dna_range
        for _ in range(count):
            dna = np.random.uniform(low, high, self.config.dna_length)
            self.population.append(Individual(dna=dna))
        # Trim to population size by removing worst
        self.population.sort(key=lambda ind: ind.fitness, reverse=True)
        self.population = self.population[: self.config.population_size]

    def reset(self) -> None:
        """Reset the evolution engine."""
        self.population = []
        self.generation = 0
        self._best_ever = None
        self._stats_history = []
        self._initialize_population()
