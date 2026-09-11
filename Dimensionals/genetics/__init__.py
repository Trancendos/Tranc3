"""
shared_core.genetics — DNA/Genetic algorithm optimisation layer.

Provides adaptive parameter evolution for workers and routing configs.
Uses DEAP when available, falls back to pure-Python NSGA-II otherwise.
"""

from .fitness import FitnessEvaluator, LatencyThroughputFitness
from .genome import (
    GenomeConfig,
    config_to_genome,
    crossover_genomes,
    genome_to_config,
    mutate_genome,
)
from .optimizer import GeneticOptimizer, Individual, Population

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
