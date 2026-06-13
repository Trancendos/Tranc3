/*
AeonMind Genetic/DNA Evolution Engine — DEAP-style Evolutionary Algorithms.

Implements:
    - Population-based DNA evolution
    - Tournament selection
    - Multi-point crossover
    - Gaussian mutation with adaptive rates
    - Elite preservation
    - Generation statistics tracking

DNA is represented as a real-valued vector (Vec<f64>).

Part of the Tranc3 Infinity Ecosystem.
*/

use rand::Rng;
use serde::{Deserialize, Serialize};

// ─── Configuration ──────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GeneticConfig {
    pub population_size: usize,
    pub dna_length: usize,
    pub elite_count: usize,
    pub crossover_rate: f64,
    pub mutation_rate: f64,
    pub mutation_strength: f64,
    pub adaptive_mutation: bool,
    pub min_mutation_strength: f64,
    pub max_mutation_strength: f64,
    pub tournament_size: usize,
}

impl Default for GeneticConfig {
    fn default() -> Self {
        Self {
            population_size: 50,
            dna_length: 64,
            elite_count: 2,
            crossover_rate: 0.7,
            mutation_rate: 0.1,
            mutation_strength: 0.5,
            adaptive_mutation: true,
            min_mutation_strength: 0.01,
            max_mutation_strength: 2.0,
            tournament_size: 3,
        }
    }
}

// ─── Individual ─────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Individual {
    pub id: usize,
    pub dna: Vec<f64>,
    pub fitness: f64,
    pub generation: usize,
    pub age: usize,
    pub is_elite: bool,
    pub parent_ids: Vec<usize>,
    pub mutation_count: usize,
}

impl Individual {
    pub fn random(id: usize, dna_length: usize) -> Self {
        let mut rng = rand::thread_rng();
        Self {
            id,
            dna: (0..dna_length).map(|_| rng.gen_range(-1.0..1.0)).collect(),
            fitness: f64::NEG_INFINITY,
            generation: 0,
            age: 0,
            is_elite: false,
            parent_ids: Vec::new(),
            mutation_count: 0,
        }
    }

    pub fn zero(id: usize, dna_length: usize) -> Self {
        Self {
            id,
            dna: vec![0.0; dna_length],
            fitness: f64::NEG_INFINITY,
            generation: 0,
            age: 0,
            is_elite: false,
            parent_ids: Vec::new(),
            mutation_count: 0,
        }
    }

    pub fn dna_distance(&self, other: &Individual) -> f64 {
        self.dna
            .iter()
            .zip(other.dna.iter())
            .map(|(a, b)| (a - b).powi(2))
            .sum::<f64>()
            .sqrt()
    }

    pub fn diversity_contribution(&self, population: &[Individual]) -> f64 {
        if population.is_empty() {
            return 0.0;
        }
        let distances: Vec<f64> = population
            .iter()
            .filter(|ind| ind.id != self.id)
            .map(|ind| self.dna_distance(ind))
            .collect();
        if distances.is_empty() {
            0.0
        } else {
            distances.iter().sum::<f64>() / distances.len() as f64
        }
    }

    pub fn dna(&self) -> &[f64] {
        &self.dna
    }
}

// ─── Generation Statistics ──────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GenerationStats {
    pub generation: usize,
    pub best_fitness: f64,
    pub worst_fitness: f64,
    pub mean_fitness: f64,
    pub diversity: f64,
    pub mutation_strength: f64,
}

// ─── Evolution Engine ───────────────────────────────────────

pub struct EvolutionEngine {
    config: GeneticConfig,
    population: Vec<Individual>,
    generation: usize,
    next_id: usize,
    best_ever: Option<Individual>,
    mutation_strength: f64,
}

impl EvolutionEngine {
    pub fn new(config: GeneticConfig) -> Self {
        let _next_id = 0;
        let population: Vec<Individual> = (0..config.population_size)
            .map(|i| Individual::random(i, config.dna_length))
            .collect();

        Self {
            mutation_strength: config.mutation_strength,
            next_id: population.len(),
            population,
            generation: 0,
            best_ever: None,
            config,
        }
    }

    /// Evaluate the population using a fitness function.
    pub fn evaluate<F>(&mut self, fitness_fn: F) -> Vec<f64>
    where
        F: Fn(&[f64]) -> f64,
    {
        let mut fitnesses = Vec::with_capacity(self.population.len());
        for ind in &mut self.population {
            let fitness = fitness_fn(&ind.dna);
            ind.fitness = fitness;
            fitnesses.push(fitness);

            if self.best_ever.is_none() || fitness > self.best_ever.as_ref().unwrap().fitness {
                self.best_ever = Some(ind.clone());
            }
        }
        fitnesses
    }

    /// Evolve one generation.
    pub fn evolve_generation<F>(&mut self, fitness_fn: F)
    where
        F: Fn(&[f64]) -> f64,
    {
        // Sort by fitness (descending)
        self.population.sort_by(|a, b| {
            b.fitness
                .partial_cmp(&a.fitness)
                .unwrap_or(std::cmp::Ordering::Equal)
        });

        let mut new_population = Vec::new();

        // Elitism
        for i in 0..self.config.elite_count.min(self.population.len()) {
            let mut elite = self.population[i].clone();
            elite.is_elite = true;
            elite.age += 1;
            new_population.push(elite);
        }

        // Fill remaining population
        while new_population.len() < self.config.population_size {
            let parent1 = self.tournament_select();
            let parent2 = self.tournament_select();

            let p1_id = parent1.id;
            let p2_id = parent2.id;
            let (child1_dna, child2_dna) = self.crossover(&parent1.dna, &parent2.dna);

            for dna in [child1_dna, child2_dna] {
                if new_population.len() < self.config.population_size {
                    let mutated_dna = self.mutate(&dna);
                    let mut child = Individual {
                        id: self.next_id,
                        dna: mutated_dna,
                        fitness: f64::NEG_INFINITY,
                        generation: self.generation + 1,
                        age: 0,
                        is_elite: false,
                        parent_ids: vec![p1_id, p2_id],
                        mutation_count: 0,
                    };
                    child.fitness = fitness_fn(&child.dna);
                    new_population.push(child);
                    self.next_id += 1;
                }
            }
        }

        self.population = new_population;
        self.generation += 1;

        // Adapt mutation
        if self.config.adaptive_mutation {
            self.adapt_mutation();
        }
    }

    /// Run evolution for n generations.
    pub fn evolve<F>(&mut self, fitness_fn: F, n_generations: usize) -> Vec<GenerationStats>
    where
        F: Fn(&[f64]) -> f64 + Copy,
    {
        let mut stats = Vec::new();
        for _ in 0..n_generations {
            self.evaluate(fitness_fn);
            self.evolve_generation(fitness_fn);
            stats.push(self.compute_stats());
        }
        stats
    }

    /// Tournament selection.
    pub fn tournament_select(&self) -> &Individual {
        let mut rng = rand::thread_rng();
        let mut best: Option<&Individual> = None;
        for _ in 0..self.config.tournament_size {
            let idx = rng.gen_range(0..self.population.len());
            let candidate = &self.population[idx];
            if best.is_none() || candidate.fitness > best.unwrap().fitness {
                best = Some(candidate);
            }
        }
        best.unwrap()
    }

    /// Multi-point crossover.
    pub fn crossover(&self, dna1: &[f64], dna2: &[f64]) -> (Vec<f64>, Vec<f64>) {
        let mut rng = rand::thread_rng();
        if rng.gen::<f64>() > self.config.crossover_rate {
            return (dna1.to_vec(), dna2.to_vec());
        }

        let n = dna1.len().min(dna2.len());
        if n <= 1 {
            return (dna1.to_vec(), dna2.to_vec());
        }
        let crossover_point = rng.gen_range(1..n);

        let mut child1 = Vec::with_capacity(n);
        let mut child2 = Vec::with_capacity(n);

        for i in 0..n {
            if i < crossover_point {
                child1.push(dna1[i]);
                child2.push(dna2[i]);
            } else {
                child1.push(dna2[i]);
                child2.push(dna1[i]);
            }
        }

        (child1, child2)
    }

    /// Gaussian mutation.
    pub fn mutate(&self, dna: &[f64]) -> Vec<f64> {
        let mut rng = rand::thread_rng();
        dna.iter()
            .map(|&gene| {
                if rng.gen::<f64>() < self.config.mutation_rate {
                    let mutation: f64 = rng.gen_range(-1.0..1.0) * self.mutation_strength;
                    gene + mutation
                } else {
                    gene
                }
            })
            .collect()
    }

    /// Adapt mutation strength.
    pub fn adapt_mutation(&mut self) {
        let stats = self.compute_stats();
        if stats.diversity < 0.1 {
            self.mutation_strength =
                (self.mutation_strength * 1.1).min(self.config.max_mutation_strength);
        } else if stats.diversity > 0.5 {
            self.mutation_strength =
                (self.mutation_strength * 0.9).max(self.config.min_mutation_strength);
        }
    }

    /// Compute generation statistics.
    pub fn compute_stats(&self) -> GenerationStats {
        let fitnesses: Vec<f64> = self.population.iter().map(|i| i.fitness).collect();
        let best = fitnesses.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
        let worst = fitnesses.iter().cloned().fold(f64::INFINITY, f64::min);
        let mean = if fitnesses.is_empty() {
            0.0
        } else {
            fitnesses.iter().sum::<f64>() / fitnesses.len() as f64
        };
        let diversity = self.population_diversity();

        GenerationStats {
            generation: self.generation,
            best_fitness: best,
            worst_fitness: worst,
            mean_fitness: mean,
            diversity,
            mutation_strength: self.mutation_strength,
        }
    }

    /// Compute population diversity (mean pairwise distance).
    pub fn population_diversity(&self) -> f64 {
        if self.population.len() < 2 {
            return 0.0;
        }
        let n = self.population.len();
        let mut total_dist = 0.0;
        let mut count = 0;
        for i in 0..n {
            for j in (i + 1)..n {
                total_dist += self.population[i].dna_distance(&self.population[j]);
                count += 1;
            }
        }
        if count == 0 {
            0.0
        } else {
            total_dist / count as f64
        }
    }

    /// Get the best individual in the current population.
    pub fn best_individual(&self) -> Option<&Individual> {
        self.population.iter().max_by(|a, b| {
            a.fitness
                .partial_cmp(&b.fitness)
                .unwrap_or(std::cmp::Ordering::Equal)
        })
    }

    /// Get the best individual ever seen.
    pub fn best_ever(&self) -> Option<&Individual> {
        self.best_ever.as_ref()
    }

    /// Inject a random individual to increase diversity.
    pub fn inject_random(&mut self) {
        if !self.population.is_empty() {
            let worst_idx = self
                .population
                .iter()
                .enumerate()
                .min_by(|(_, a), (_, b)| {
                    a.fitness
                        .partial_cmp(&b.fitness)
                        .unwrap_or(std::cmp::Ordering::Equal)
                })
                .map(|(i, _)| i);
            if let Some(idx) = worst_idx {
                self.population[idx] = Individual::random(self.next_id, self.config.dna_length);
                self.next_id += 1;
            }
        }
    }

    pub fn population(&self) -> &[Individual] {
        &self.population
    }

    pub fn set_fitness(&mut self, idx: usize, fitness: f64) {
        if let Some(ind) = self.population.get_mut(idx) {
            ind.fitness = fitness;
            if self.best_ever.as_ref().is_none_or(|b| fitness > b.fitness) {
                self.best_ever = Some(ind.clone());
            }
        }
    }

    pub fn generation(&self) -> usize {
        self.generation
    }

    pub fn best_dna(&self) -> &[f64] {
        self.best_individual()
            .map(|ind| ind.dna.as_slice())
            .unwrap_or(&[])
    }

    /// Advance one generation using current fitness values. New children receive NEG_INFINITY
    /// fitness and should be evaluated externally before the next advance.
    pub fn advance_generation(&mut self) {
        self.evolve_generation(|_| f64::NEG_INFINITY);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_individual_random() {
        let ind = Individual::random(0, 64);
        assert_eq!(ind.dna.len(), 64);
        assert_eq!(ind.id, 0);
    }

    #[test]
    fn test_individual_zero() {
        let ind = Individual::zero(1, 32);
        assert_eq!(ind.dna.len(), 32);
        assert!(ind.dna.iter().all(|&v| v == 0.0));
    }

    #[test]
    fn test_dna_distance() {
        let a = Individual {
            id: 0,
            dna: vec![0.0, 0.0],
            fitness: 0.0,
            generation: 0,
            age: 0,
            is_elite: false,
            parent_ids: vec![],
            mutation_count: 0,
        };
        let b = Individual {
            id: 1,
            dna: vec![3.0, 4.0],
            fitness: 0.0,
            generation: 0,
            age: 0,
            is_elite: false,
            parent_ids: vec![],
            mutation_count: 0,
        };
        let dist = a.dna_distance(&b);
        assert!((dist - 5.0).abs() < 1e-6);
    }

    #[test]
    fn test_evolution_engine_creation() {
        let config = GeneticConfig::default();
        let engine = EvolutionEngine::new(config);
        assert_eq!(engine.population.len(), 50);
    }

    #[test]
    fn test_evaluate() {
        let config = GeneticConfig {
            population_size: 10,
            dna_length: 10,
            ..Default::default()
        };
        let mut engine = EvolutionEngine::new(config);
        let fitnesses = engine.evaluate(|dna| -dna.iter().map(|x| x * x).sum::<f64>());
        assert_eq!(fitnesses.len(), 10);
    }

    #[test]
    fn test_tournament_select() {
        let config = GeneticConfig {
            population_size: 10,
            dna_length: 5,
            ..Default::default()
        };
        let mut engine = EvolutionEngine::new(config);
        engine.evaluate(|dna| dna.iter().sum());
        let selected = engine.tournament_select();
        assert!(!selected.dna.is_empty());
    }

    #[test]
    fn test_crossover() {
        let config = GeneticConfig::default();
        let engine = EvolutionEngine::new(config);
        let p1 = vec![1.0; 64];
        let p2 = vec![2.0; 64];
        let (c1, c2) = engine.crossover(&p1, &p2);
        assert_eq!(c1.len(), 64);
        assert_eq!(c2.len(), 64);
    }

    #[test]
    fn test_mutate() {
        let config = GeneticConfig {
            mutation_rate: 1.0,
            ..Default::default()
        };
        let engine = EvolutionEngine::new(config);
        let dna = vec![0.0; 64];
        let mutated = engine.mutate(&dna);
        assert!(mutated.iter().any(|&v| v != 0.0));
    }

    #[test]
    fn test_sphere_optimization() {
        let config = GeneticConfig {
            population_size: 30,
            dna_length: 5,
            ..Default::default()
        };
        let mut engine = EvolutionEngine::new(config);
        let stats = engine.evolve(|dna| -dna.iter().map(|x| x * x).sum::<f64>(), 50);
        assert!(!stats.is_empty());
        assert!(stats.last().unwrap().best_fitness > -25.0); // Should improve from initial
    }

    #[test]
    fn test_population_diversity() {
        let config = GeneticConfig {
            population_size: 10,
            dna_length: 10,
            ..Default::default()
        };
        let engine = EvolutionEngine::new(config);
        let diversity = engine.population_diversity();
        assert!(diversity >= 0.0);
    }
}
