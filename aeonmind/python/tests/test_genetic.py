"""
Tests for AeonMind DNA Evolution Engine.
"""

import pytest  # noqa: I001
import numpy as np

from aeonmind.core.genetic_dna import DNAEvolutionEngine, GeneticConfig, Individual


class TestDNAEvolutionEngine:
    """Tests for the DNAEvolutionEngine."""

    def test_engine_creation(self):
        engine = DNAEvolutionEngine()
        assert len(engine.population) == engine.config.population_size

    def test_custom_config(self):
        config = GeneticConfig(population_size=20, dna_length=16)
        engine = DNAEvolutionEngine(config)
        assert len(engine.population) == 20
        assert len(engine.population[0].dna) == 16

    def test_evaluate(self):
        engine = DNAEvolutionEngine(GeneticConfig(population_size=10, dna_length=8))

        def sphere_fitness(dna):
            return -float(np.sum(dna ** 2))  # negative because we maximize

        engine.evaluate(sphere_fitness)
        best = engine.best_individual()
        assert best is not None
        assert best.fitness > float("-inf")

    def test_tournament_select(self):
        engine = DNAEvolutionEngine(GeneticConfig(population_size=20, dna_length=8))

        def sphere_fitness(dna):
            return -float(np.sum(dna ** 2))

        engine.evaluate(sphere_fitness)
        selected = engine.tournament_select()
        assert selected is not None
        assert len(selected.dna) == 8

    def test_crossover(self):
        config = GeneticConfig(population_size=10, dna_length=8)
        engine = DNAEvolutionEngine(config)
        parent1 = Individual(dna=np.ones(8))
        parent2 = Individual(dna=np.zeros(8))
        child1, child2 = engine.crossover(parent1, parent2)
        assert len(child1.dna) == 8
        assert len(child2.dna) == 8

    def test_mutate(self):
        config = GeneticConfig(mutation_rate=1.0, mutation_strength=0.5)
        engine = DNAEvolutionEngine(config)
        individual = Individual(dna=np.zeros(8))
        mutated = engine.mutate(individual)
        # With mutation_rate=1.0, all genes should be mutated
        assert not np.allclose(mutated.dna, np.zeros(8))

    def test_evolve_generation(self):
        config = GeneticConfig(population_size=20, dna_length=8)
        engine = DNAEvolutionEngine(config)

        def sphere_fitness(dna):
            return -float(np.sum(dna ** 2))

        engine.evaluate(sphere_fitness)
        stats = engine.evolve_generation()
        assert stats.generation == 1
        assert isinstance(stats.best_fitness, float)

    def test_evolve_multiple_generations(self):
        config = GeneticConfig(
            population_size=20,
            dna_length=8,
            max_generations=5,
        )
        engine = DNAEvolutionEngine(config)

        def sphere_fitness(dna):
            return -float(np.sum(dna ** 2))

        final_stats = engine.evolve(sphere_fitness, generations=5)  # noqa: F841
        assert engine.generation == 5

    def test_population_diversity(self):
        engine = DNAEvolutionEngine(GeneticConfig(population_size=20, dna_length=8))
        diversity = engine.population_diversity()
        assert diversity >= 0.0

    def test_best_ever(self):
        engine = DNAEvolutionEngine(GeneticConfig(population_size=10, dna_length=8))

        def sphere_fitness(dna):
            return -float(np.sum(dna ** 2))

        engine.evaluate(sphere_fitness)
        best = engine.best_ever()
        assert best is not None
        assert best.fitness > float("-inf")

    def test_inject_random(self):
        engine = DNAEvolutionEngine(GeneticConfig(population_size=20, dna_length=8))
        initial_size = len(engine.population)  # noqa: F841
        engine.inject_random(5)
        # Should not exceed population_size
        assert len(engine.population) <= engine.config.population_size

    def test_reset(self):
        engine = DNAEvolutionEngine()
        def fitness(dna):
            return -float(np.sum(dna ** 2))
        engine.evaluate(fitness)
        engine.evolve_generation()
        engine.reset()
        assert engine.generation == 0
