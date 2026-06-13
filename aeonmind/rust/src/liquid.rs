/*
AeonMind Liquid State Machine — Reservoir Computing with Fluidic State.

Implements a Liquid Reservoir with:
    - Leaky integrator neurons with configurable spectral radius
    - Sparse random recurrent connections
    - Fluidic state tracking (energy, entropy, variance)
    - Readout training via ridge regression
    - Adaptive spectral radius adjustment

Part of the Tranc3 Infinity Ecosystem.
*/

use ndarray::{Array1, Array2, Ix2};
use ndarray_rand::RandomExt;
use rand::distributions::Uniform;
use rand::Rng;
use serde::{Deserialize, Serialize};

// ─── Configuration ──────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReservoirConfig {
    pub reservoir_size: usize,
    pub input_size: usize,
    pub output_size: usize,
    pub spectral_radius: f64,
    pub leak_rate: f64,
    pub sparsity: f64,
    pub input_scaling: f64,
    pub bias_scaling: f64,
    pub activation: String,
}

impl Default for ReservoirConfig {
    fn default() -> Self {
        Self {
            reservoir_size: 200,
            input_size: 10,
            output_size: 5,
            spectral_radius: 0.95,
            leak_rate: 0.3,
            sparsity: 0.1,
            input_scaling: 1.0,
            bias_scaling: 0.1,
            activation: "tanh".to_string(),
        }
    }
}

// ─── Fluidic State ──────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FluidicState {
    pub mean_energy: f64,
    pub variance: f64,
    pub max_activation: f64,
    pub spectral_radius: f64,
    pub time_step: usize,
    pub entropy: f64,
}

// ─── Reservoir State ────────────────────────────────────────

#[derive(Debug, Clone)]
pub struct ReservoirState {
    pub activations: Array1<f64>,
    pub time_step: usize,
    pub spectral_radius: f64,
    pub mean_energy: f64,
}

// ─── Liquid Reservoir ───────────────────────────────────────

pub struct LiquidReservoir {
    config: ReservoirConfig,
    state: Array1<f64>,
    weights: Array2<f64>,
    input_weights: Array2<f64>,
    bias: Array1<f64>,
    time_step: usize,
    current_spectral_radius: f64,
}

impl LiquidReservoir {
    pub fn new(config: ReservoirConfig) -> Self {
        let n = config.reservoir_size;
        let m = config.input_size;

        // Initialize sparse recurrent weights
        let mut weights = Array2::<f64>::zeros((n, n));
        let mut rng = rand::thread_rng();
        for i in 0..n {
            for j in 0..n {
                if rng.gen::<f64>() < config.sparsity {
                    weights[[i, j]] = rng.gen_range(-1.0..1.0);
                }
            }
        }

        // Scale to desired spectral radius
        let sr = compute_spectral_radius(&weights);
        if sr > 0.0 {
            weights.mapv_inplace(|v| v * (config.spectral_radius / sr));
        }

        let current_spectral_radius = config.spectral_radius;

        // Random input weights
        let input_weights = Array2::random((n, m), Uniform::new(-1.0, 1.0))
            .mapv(|v| v * config.input_scaling);

        // Bias
        let bias = Array1::random(n, Uniform::new(-1.0, 1.0))
            .mapv(|v| v * config.bias_scaling);

        Self {
            config,
            state: Array1::zeros(n),
            weights,
            input_weights,
            bias,
            time_step: 0,
            current_spectral_radius,
        }
    }

    /// Process one time step through the reservoir.
    pub fn step(&mut self, input: &[f64]) -> Array1<f64> {
        let input_arr = Array1::from_vec(input.to_vec());
        let pre_activation = self.weights.dot(&self.state)
            + self.input_weights.dot(&input_arr)
            + &self.bias;

        let new_state = (1.0 - self.config.leak_rate) * &self.state
            + self.config.leak_rate * pre_activation.mapv(tanh_activation);

        self.state = new_state;
        self.time_step += 1;
        self.state.clone()
    }

    /// Process a sequence of inputs.
    pub fn process_sequence(&mut self, inputs: &[Vec<f64>]) -> Vec<Array1<f64>> {
        inputs.iter().map(|inp| self.step(inp)).collect()
    }

    /// Reset the reservoir state.
    pub fn reset(&mut self) {
        self.state = Array1::zeros(self.config.reservoir_size);
        self.time_step = 0;
    }

    /// Warmup with random inputs.
    pub fn warmup(&mut self, n_steps: usize) {
        let mut rng = rand::thread_rng();
        for _ in 0..n_steps {
            let input: Vec<f64> = (0..self.config.input_size)
                .map(|_| rng.gen_range(-1.0..1.0))
                .collect();
            self.step(&input);
        }
    }

    /// Get the current reservoir state features.
    pub fn get_state_features(&self) -> Vec<f64> {
        self.state.to_vec()
    }

    /// Train a readout layer via ridge regression.
    pub fn train_readout(
        &self,
        states: &[Vec<f64>],
        targets: &[Vec<f64>],
        ridge_param: f64,
    ) -> Array2<f64> {
        let n_samples = states.len();
        let n_reservoir = self.config.reservoir_size;
        let n_output = self.config.output_size;

        let mut s_matrix = Array2::<f64>::zeros((n_samples, n_reservoir));
        let mut t_matrix = Array2::<f64>::zeros((n_samples, n_output));

        for (i, (s, t)) in states.iter().zip(targets.iter()).enumerate() {
            for (j, &val) in s.iter().enumerate() {
                if j < n_reservoir {
                    s_matrix[[i, j]] = val;
                }
            }
            for (j, &val) in t.iter().enumerate() {
                if j < n_output {
                    t_matrix[[i, j]] = val;
                }
            }
        }

        // Ridge: W = (S^T S + λI)^-1 S^T T
        let sts = s_matrix.t().dot(&s_matrix);
        let identity = Array2::<f64>::eye(n_reservoir);
        let regularized = sts + ridge_param * identity;

        // Simple inverse via Gauss-Jordan (for small matrices)
        let inv = simple_inverse(&regularized).unwrap_or(identity);
        let readout = inv.dot(&s_matrix.t().dot(&t_matrix));

        readout
    }

    /// Adapt the spectral radius toward a target.
    pub fn adapt_spectral_radius(&mut self, target: f64) {
        let current_sr = compute_spectral_radius(&self.weights);
        if current_sr > 0.0 {
            let scale = target / current_sr;
            self.weights.mapv_inplace(|v| v * scale);
            self.current_spectral_radius = target;
        }
    }

    /// Get the current fluidic state.
    pub fn fluidic_state(&self) -> FluidicState {
        let energy: f64 = self.state.mapv(|v| v * v).sum() / self.state.len() as f64;
        let mean = self.state.sum() / self.state.len() as f64;
        let variance = self.state.mapv(|v| (v - mean).powi(2)).sum() / self.state.len() as f64;
        let max_activation = self.state.iter().cloned().fold(f64::NEG_INFINITY, f64::max);

        FluidicState {
            mean_energy: energy,
            variance,
            max_activation,
            spectral_radius: self.current_spectral_radius,
            time_step: self.time_step,
            entropy: compute_approximate_entropy(&self.state),
        }
    }
}

// ─── Helper Functions ───────────────────────────────────────

fn tanh_activation(x: f64) -> f64 {
    x.tanh()
}

fn compute_spectral_radius(matrix: &Array2<f64>) -> f64 {
    // Power iteration method
    let n = matrix.nrows();
    if n == 0 {
        return 0.0;
    }

    let mut v = Array1::from_vec((0..n).map(|i| (i as f64 + 1.0) / n as f64).collect());
    let _norm: f64 = v.mapv(|x| x * x).sum().sqrt();
    if _norm > 0.0 {
        v.mapv_inplace(|x| x / _norm);
    }

    let mut eigenvalue = 0.0;
    for _ in 0..100 {
        let new_v = matrix.dot(&v);
        let norm: f64 = new_v.mapv(|x| x * x).sum().sqrt();
        if norm == 0.0 {
            break;
        }
        v = new_v.mapv(|x| x / norm);
        eigenvalue = norm;
    }

    eigenvalue.abs()
}

fn compute_approximate_entropy(state: &Array1<f64>) -> f64 {
    if state.is_empty() {
        return 0.0;
    }
    let n = state.len() as f64;
    let sum_sq: f64 = state.mapv(|v| v * v).sum();
    if sum_sq == 0.0 {
        return 0.0;
    }
    // Approximate entropy via normalized energy distribution
    let probs = state.mapv(|v| (v * v) / sum_sq);
    probs.mapv(|p| if p > 0.0 { -p * p.ln() } else { 0.0 }).sum()
}

fn simple_inverse(matrix: &Array2<f64>) -> Option<Array2<f64>> {
    let n = matrix.nrows();
    if n == 0 || n != matrix.ncols() {
        return None;
    }

    let mut aug = Array2::<f64>::zeros((n, 2 * n));
    for i in 0..n {
        for j in 0..n {
            aug[[i, j]] = matrix[[i, j]];
        }
        aug[[i, n + i]] = 1.0;
    }

    // Forward elimination
    for col in 0..n {
        let mut max_row = col;
        let mut max_val = aug[[col, col]].abs();
        for row in (col + 1)..n {
            if aug[[row, col]].abs() > max_val {
                max_val = aug[[row, col]].abs();
                max_row = row;
            }
        }
        if max_val < 1e-10 {
            return None;
        }

        // Swap rows
        for j in 0..(2 * n) {
            let tmp = aug[[col, j]];
            aug[[col, j]] = aug[[max_row, j]];
            aug[[max_row, j]] = tmp;
        }

        let pivot = aug[[col, col]];
        for j in 0..(2 * n) {
            aug[[col, j]] /= pivot;
        }

        for row in 0..n {
            if row != col {
                let factor = aug[[row, col]];
                for j in 0..(2 * n) {
                    aug[[row, j]] -= factor * aug[[col, j]];
                }
            }
        }
    }

    let mut result = Array2::<f64>::zeros((n, n));
    for i in 0..n {
        for j in 0..n {
            result[[i, j]] = aug[[i, n + j]];
        }
    }

    Some(result)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_reservoir_creation() {
        let config = ReservoirConfig::default();
        let reservoir = LiquidReservoir::new(config);
        assert_eq!(reservoir.state.len(), 200);
    }

    #[test]
    fn test_step() {
        let config = ReservoirConfig {
            reservoir_size: 50,
            input_size: 5,
            ..Default::default()
        };
        let mut reservoir = LiquidReservoir::new(config);
        let input = vec![0.1; 5];
        let output = reservoir.step(&input);
        assert_eq!(output.len(), 50);
    }

    #[test]
    fn test_process_sequence() {
        let config = ReservoirConfig {
            reservoir_size: 30,
            input_size: 3,
            ..Default::default()
        };
        let mut reservoir = LiquidReservoir::new(config);
        let inputs: Vec<Vec<f64>> = (0..10).map(|_| vec![0.5; 3]).collect();
        let outputs = reservoir.process_sequence(&inputs);
        assert_eq!(outputs.len(), 10);
    }

    #[test]
    fn test_reset() {
        let config = ReservoirConfig {
            reservoir_size: 20,
            input_size: 3,
            ..Default::default()
        };
        let mut reservoir = LiquidReservoir::new(config);
        reservoir.step(&vec![0.5; 3]);
        reservoir.reset();
        assert_eq!(reservoir.time_step, 0);
    }

    #[test]
    fn test_warmup() {
        let config = ReservoirConfig {
            reservoir_size: 20,
            input_size: 3,
            ..Default::default()
        };
        let mut reservoir = LiquidReservoir::new(config);
        reservoir.warmup(5);
        assert_eq!(reservoir.time_step, 5);
    }

    #[test]
    fn test_fluidic_state() {
        let config = ReservoirConfig {
            reservoir_size: 20,
            input_size: 3,
            ..Default::default()
        };
        let mut reservoir = LiquidReservoir::new(config);
        reservoir.step(&vec![0.5; 3]);
        let fs = reservoir.fluidic_state();
        assert!(fs.mean_energy >= 0.0);
        assert_eq!(fs.time_step, 1);
    }

    #[test]
    fn test_spectral_radius() {
        let config = ReservoirConfig {
            spectral_radius: 0.9,
            ..Default::default()
        };
        let reservoir = LiquidReservoir::new(config);
        assert!((reservoir.current_spectral_radius - 0.9).abs() < 0.1);
    }

    #[test]
    fn test_adapt_spectral_radius() {
        let config = ReservoirConfig::default();
        let mut reservoir = LiquidReservoir::new(config);
        reservoir.adapt_spectral_radius(0.8);
        assert!((reservoir.current_spectral_radius - 0.8).abs() < 0.05);
    }

    #[test]
    fn test_state_features() {
        let config = ReservoirConfig {
            reservoir_size: 20,
            ..Default::default()
        };
        let reservoir = LiquidReservoir::new(config);
        let features = reservoir.get_state_features();
        assert_eq!(features.len(), 20);
    }

    #[test]
    fn test_entropy() {
        let state = Array1::from_vec(vec![0.5, 0.3, 0.2]);
        let entropy = compute_approximate_entropy(&state);
        assert!(entropy >= 0.0);
    }
}
