"""
AeonMind Rust Python Bindings — PyO3 Module Definitions.

Exposes the Rust core functionality to Python via PyO3/maturin.
All structs and enums are annotated with #[pyclass] and methods
with #[pymethods] for seamless Python interop.
"""

use pyo3::prelude::*;
use pyo3::types::PyDict;

use crate::{Tier, SentinelChannel, AeonMindError, EntityType, AiComplex, AgentEntity, BotService};
use crate::liquid::{LiquidReservoir, ReservoirConfig as RustReservoirConfig};
use crate::genetic::{EvolutionEngine, GeneticConfig as RustGeneticConfig};
use crate::quantum::{QuantumDecisionCircuit, QuantumCircuitConfig as RustQuantumConfig};
use crate::adaptive::{AdaptiveMetaLearner, AdaptiveConfig as RustAdaptiveConfig};
use crate::wasm_bridge::{WasmAgent, WasmAgentConfig as RustWasmConfig, FluidicAgentState, IntelligenceScore, ScoringWeights};

// ── Tier & SentinelChannel PyO3 ─────────────────────────────────────────────

#[pymethods]
impl Tier {
    #[getter]
    fn value(&self) -> u8 {
        *self as u8
    }

    fn __repr__(&self) -> String {
        format!("Tier::{:?}({})", self, *self as u8)
    }
}

#[pymethods]
impl SentinelChannel {
    #[getter]
    fn value(&self) -> &str {
        self.as_str()
    }

    fn __repr__(&self) -> String {
        format!("SentinelChannel::{}", self.as_str())
    }
}

// ── Liquid Reservoir PyO3 ───────────────────────────────────────────────────

#[pyclass(name = "RustLiquidReservoir")]
pub struct PyLiquidReservoir {
    inner: LiquidReservoir,
}

#[pymethods]
impl PyLiquidReservoir {
    #[new]
    #[pyo3(signature = (input_size=10, reservoir_size=200, spectral_radius=0.95, leaking_rate=0.3, seed=None))]
    fn new(
        input_size: usize,
        reservoir_size: usize,
        spectral_radius: f64,
        leaking_rate: f64,
        seed: Option<u64>,
    ) -> PyResult<Self> {
        let config = RustReservoirConfig {
            input_size,
            reservoir_size,
            spectral_radius,
            leaking_rate,
            input_scaling: 1.0,
            connectivity: 0.1,
            washout: 50,
            seed,
        };
        Ok(Self {
            inner: LiquidReservoir::new(config),
        })
    }

    fn step(&mut self, input_data: Vec<f64>) -> Vec<f64> {
        self.inner.step(&input_data)
    }

    fn reset(&mut self) {
        self.inner.reset();
    }

    fn warmup(&mut self, n_steps: usize) {
        self.inner.warmup(n_steps);
    }

    fn get_spectral_radius(&self) -> f64 {
        self.inner.spectral_radius()
    }
}

// ── Evolution Engine PyO3 ───────────────────────────────────────────────────

#[pyclass(name = "RustEvolutionEngine")]
pub struct PyEvolutionEngine {
    inner: EvolutionEngine,
}

#[pymethods]
impl PyEvolutionEngine {
    #[new]
    #[pyo3(signature = (population_size=50, dna_length=32, mutation_rate=0.1, crossover_rate=0.7))]
    fn new(
        population_size: usize,
        dna_length: usize,
        mutation_rate: f64,
        crossover_rate: f64,
    ) -> Self {
        let config = RustGeneticConfig {
            population_size,
            dna_length,
            mutation_rate,
            crossover_rate,
            ..Default::default()
        };
        Self {
            inner: EvolutionEngine::new(config),
        }
    }

    fn evolve(&mut self, fitness_fn: &PyAny) -> PyResult<f64> {
        let population = self.inner.population();
        let mut best_fitness = f64::NEG_INFINITY;

        for i in 0..population.len() {
            let dna = population[i].dna().to_vec();
            let args = (dna,);
            let result = fitness_fn.call1(args)?;
            let fitness: f64 = result.extract()?;
            if fitness > best_fitness {
                best_fitness = fitness;
            }
            self.inner.set_fitness(i, fitness);
        }

        self.inner.evolve_generation();
        Ok(best_fitness)
    }

    fn best_dna(&self) -> Vec<f64> {
        self.inner.best_dna().to_vec()
    }

    fn generation(&self) -> usize {
        self.inner.generation()
    }
}

// ── Quantum Circuit PyO3 ────────────────────────────────────────────────────

#[pyclass(name = "RustQuantumCircuit")]
pub struct PyQuantumCircuit {
    inner: QuantumDecisionCircuit,
}

#[pymethods]
impl PyQuantumCircuit {
    #[new]
    #[pyo3(signature = (n_qubits=4, n_layers=2, rotations_per_layer=3))]
    fn new(n_qubits: usize, n_layers: usize, rotations_per_layer: usize) -> Self {
        let config = RustQuantumConfig {
            n_qubits,
            n_layers,
            rotations_per_layer,
            ..Default::default()
        };
        Self {
            inner: QuantumDecisionCircuit::new(config),
        }
    }

    fn execute(&mut self) -> Vec<f64> {
        self.inner.execute()
    }

    fn decide(&mut self) -> usize {
        self.inner.decide()
    }

    fn n_qubits(&self) -> usize {
        self.inner.n_qubits()
    }

    fn n_layers(&self) -> usize {
        self.inner.n_layers()
    }
}

// ── Adaptive Meta-Learner PyO3 ──────────────────────────────────────────────

#[pyclass(name = "RustAdaptiveLearner")]
pub struct PyAdaptiveLearner {
    inner: AdaptiveMetaLearner,
}

#[pymethods]
impl PyAdaptiveLearner {
    #[new]
    #[pyo3(signature = (n_params=32, learning_rate=0.01, memory_size=10))]
    fn new(n_params: usize, learning_rate: f64, memory_size: usize) -> Self {
        let config = RustAdaptiveConfig {
            learning_rate,
            memory_size,
            ..Default::default()
        };
        Self {
            inner: AdaptiveMetaLearner::new(n_params, config),
        }
    }

    fn step(&mut self, gradient: Vec<f64>) -> Vec<f64> {
        self.inner.step(&gradient)
    }

    fn parameters(&self) -> Vec<f64> {
        self.inner.parameters().to_vec()
    }
}

// ── Module Registration ─────────────────────────────────────────────────────

#[pymodule]
fn _aeonmind_rust(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyLiquidReservoir>()?;
    m.add_class::<PyEvolutionEngine>()?;
    m.add_class::<PyQuantumCircuit>()?;
    m.add_class::<PyAdaptiveLearner>()?;
    m.add("__version__", "0.9.0")?;
    Ok(())
}
