# src/evolution/self_improving_core.py
# TRANC3 Self-Evolution Engine

import logging
import numpy as np
import torch
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Individual:
    """A single individual in the evolutionary population."""

    genome: np.ndarray
    fitness: float = 0.0
    generation: int = 0
    mutations: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    metrics: Dict[str, float] = field(default_factory=dict)

    def copy(self) -> "Individual":
        return Individual(
            genome=self.genome.copy(),
            fitness=self.fitness,
            generation=self.generation,
            mutations=self.mutations,
            metrics=self.metrics.copy(),
        )


class GeneticOperators:
    """Crossover, mutation, and selection operators."""

    @staticmethod
    def crossover(parent_a: Individual, parent_b: Individual) -> Individual:
        point = np.random.randint(1, len(parent_a.genome))
        child_genome = np.concatenate(
            [parent_a.genome[:point], parent_b.genome[point:]]
        )
        return Individual(
            genome=child_genome,
            generation=max(parent_a.generation, parent_b.generation) + 1,
        )

    @staticmethod
    def mutate(individual: Individual, rate: float = 0.01) -> Individual:
        mutated = individual.copy()
        mask = np.random.random(len(mutated.genome)) < rate
        mutated.genome[mask] += np.random.randn(mask.sum()) * 0.1
        mutated.mutations += int(mask.sum())
        return mutated

    @staticmethod
    def tournament_select(population: List[Individual], k: int = 3) -> Individual:
        contestants = np.random.choice(
            population, size=min(k, len(population)), replace=False
        )
        return max(contestants, key=lambda ind: ind.fitness)


class FitnessEvaluator:
    """Evaluate fitness of individuals based on feedback signals."""

    def __init__(self):
        self._feedback_history: List[Dict] = []

    def record_feedback(self, feedback: Dict[str, float]):
        self._feedback_history.append(feedback)
        if len(self._feedback_history) > 1000:
            self._feedback_history.pop(0)

    def evaluate(
        self, individual: Individual, recent_feedback: Optional[List[Dict]] = None
    ) -> float:
        feedback = recent_feedback or self._feedback_history[-10:]
        if not feedback:
            return float(np.linalg.norm(individual.genome))

        quality = np.mean([f.get("quality_score", 0.5) for f in feedback])
        satisfaction = np.mean([f.get("user_satisfaction", 0.5) for f in feedback])
        diversity = float(np.std(individual.genome))

        fitness = quality * 0.4 + satisfaction * 0.4 + diversity * 0.2
        individual.fitness = fitness
        individual.metrics = {
            "quality": quality,
            "satisfaction": satisfaction,
            "diversity": diversity,
        }
        return fitness


class SelfEvolvingArchitecture:
    """
    Evolutionary self-improvement system.
    Maintains a population of genome vectors representing model parameter deltas.
    Evolves based on user feedback and quality signals.
    """

    def __init__(self, config: Dict):
        self.population_size = config.get("population_size", 10)
        self.mutation_rate = config.get("mutation_rate", 0.01)
        self.genome_dim = config.get("genome_dim", 768)
        self.elite_ratio = config.get("elite_ratio", 0.2)
        self.generation = 0

        self.operators = GeneticOperators()
        self.evaluator = FitnessEvaluator()

        # Initialise population
        self.population: List[Individual] = [
            Individual(genome=np.random.randn(self.genome_dim) * 0.01)
            for _ in range(self.population_size)
        ]
        logger.info(
            f"SelfEvolvingArchitecture initialised: pop={self.population_size}, dim={self.genome_dim}"
        )

    def evolve(
        self, num_generations: int = 1, feedback: Optional[List[Dict]] = None
    ) -> Individual:
        """Run evolutionary loop and return best individual."""
        for _ in range(num_generations):
            for ind in self.population:
                self.evaluator.evaluate(ind, feedback)

            self.population.sort(key=lambda x: x.fitness, reverse=True)

            n_elite = max(1, int(self.population_size * self.elite_ratio))
            new_population = self.population[:n_elite]

            while len(new_population) < self.population_size:
                parent_a = self.operators.tournament_select(self.population)
                parent_b = self.operators.tournament_select(self.population)
                child = self.operators.crossover(parent_a, parent_b)
                child = self.operators.mutate(child, self.mutation_rate)
                new_population.append(child)

            self.population = new_population
            self.generation += 1

        best = self.population[0]
        logger.info(
            f"Generation {self.generation}: best_fitness={best.fitness:.4f}, mutations={best.mutations}"
        )

        # Persist best genome to Redis — Gap G25 action
        self._persist_genome(best)

        return best

    def _persist_genome(self, individual: Individual):
        """Save best genome to Redis for cross-restart continuity."""
        try:
            import redis as _redis
            import json
            import os

            r = _redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
            r.set(
                "tranc3:evolution:best_genome",
                json.dumps(
                    {
                        "genome": individual.genome.tolist(),
                        "fitness": individual.fitness,
                        "generation": self.generation,
                        "mutations": individual.mutations,
                    }
                ),
                ex=86400 * 7,
            )  # 7-day TTL
        except Exception as e:
            logger.debug(f"Genome persist skipped: {e}")

    def load_genome_from_redis(self) -> bool:
        """Restore best genome from Redis on startup."""
        try:
            import redis as _redis
            import json
            import os

            r = _redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
            data = r.get("tranc3:evolution:best_genome")
            if data:
                saved = json.loads(data)
                self.population[0].genome = np.array(saved["genome"])
                self.population[0].fitness = saved["fitness"]
                self.generation = saved.get("generation", 0)
                logger.info(
                    f"Genome restored from Redis: gen={self.generation}, fitness={saved['fitness']:.4f}"
                )
                return True
        except Exception as e:
            logger.debug(f"Genome restore skipped: {e}")
        return False

    def get_best_genome(self) -> torch.Tensor:
        """Return best genome as a torch tensor for model injection."""
        best = max(self.population, key=lambda x: x.fitness)
        return torch.tensor(best.genome, dtype=torch.float32)

    def record_feedback(self, feedback: Dict[str, float]):
        self.evaluator.record_feedback(feedback)

    def get_stats(self) -> Dict:
        fitnesses = [ind.fitness for ind in self.population]
        return {
            "generation": self.generation,
            "population_size": len(self.population),
            "best_fitness": max(fitnesses) if fitnesses else 0.0,
            "avg_fitness": float(np.mean(fitnesses)) if fitnesses else 0.0,
            "mutation_rate": self.mutation_rate,
        }
