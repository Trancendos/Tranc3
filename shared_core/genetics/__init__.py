"""
shared_core.genetics — DNA/Genetic algorithm optimisation layer.

Provides adaptive parameter evolution for workers and routing configs.
Uses DEAP when available, falls back to pure-Python NSGA-II otherwise.
"""

from .genome import GenomeConfig, mutate_genome, crossover_genomes, config_to_genome, genome_to_config
from .optimizer import GeneticOptimizer, Individual, Population
from .fitness import FitnessEvaluator, LatencyThroughputFitness

__all__ = [
    "GenomeConfig",
    "mutate_genome",
    "crossover_genomes",
    "config_to_genome",
    "genome_to_config",
    "GeneticOptimizer",
    "Individual",
    "Population",
    "FitnessEvaluator",
    "LatencyThroughputFitness",
]
