/*
AeonMind Smart Adaptive Quantum Circuit Variational Layers.

Implements parameterized quantum circuits with:
    - Multi-layer Rot gates (Rx, Ry, Rz) with parameterized rotations
    - CNOT/CZ entangling gates with configurable strategy
    - Parameter shift rule for gradient computation
    - Adaptive layer depth control
    - Gradient descent optimization with adaptive learning rate

Gate matrices are 2×2 Complex64 for all gate types.

Part of the Tranc3 Infinity Ecosystem.
*/

use num_complex::Complex64;
use rand::Rng;
use serde::{Deserialize, Serialize};
use std::f64::consts::PI;

// ─── Gate Types ─────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub enum GateType {
    X,
    Y,
    Z,
    H,
    Rx,
    Ry,
    Rz,
    CNOT,
    CZ,
    SWAP,
    Identity,
    Phase,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Gate {
    pub gate_type: GateType,
    pub target: usize,
    pub control: Option<usize>,
    pub parameter: Option<f64>,
    pub layer: usize,
}

impl Gate {
    pub fn single(
        gate_type: GateType,
        target: usize,
        parameter: Option<f64>,
        layer: usize,
    ) -> Self {
        Self {
            gate_type,
            target,
            control: None,
            parameter,
            layer,
        }
    }

    pub fn two_qubit(gate_type: GateType, target: usize, control: usize, layer: usize) -> Self {
        Self {
            gate_type,
            target,
            control: Some(control),
            parameter: None,
            layer,
        }
    }

    /// Get the 2×2 matrix for single-qubit gates.
    pub fn matrix(&self) -> [[Complex64; 2]; 2] {
        let zero = Complex64::new(0.0, 0.0);
        let one = Complex64::new(1.0, 0.0);
        let im = Complex64::new(0.0, 1.0);
        let sqrt2_inv = Complex64::new(1.0 / 2.0_f64.sqrt(), 0.0);

        match self.gate_type {
            GateType::X => [[zero, one], [one, zero]],
            GateType::Y => [[zero, -im], [im, zero]],
            GateType::Z => [[one, zero], [zero, -one]],
            GateType::H => [[sqrt2_inv, sqrt2_inv], [sqrt2_inv, -sqrt2_inv]],
            GateType::Rx => {
                let theta = self.parameter.unwrap_or(0.0);
                let c = Complex64::new((theta / 2.0).cos(), 0.0);
                let s = Complex64::new(0.0, -(theta / 2.0).sin());
                [[c, s], [s, c]]
            }
            GateType::Ry => {
                let theta = self.parameter.unwrap_or(0.0);
                let c = Complex64::new((theta / 2.0).cos(), 0.0);
                let s = Complex64::new(-(theta / 2.0).sin(), 0.0);
                [[c, s], [-s, c]]
            }
            GateType::Rz => {
                let theta = self.parameter.unwrap_or(0.0);
                let exp_pos = Complex64::new((-theta / 2.0).cos(), (-theta / 2.0).sin());
                let exp_neg = Complex64::new((theta / 2.0).cos(), (theta / 2.0).sin());
                [[exp_pos, zero], [zero, exp_neg]]
            }
            GateType::Identity => [[one, zero], [zero, one]],
            GateType::Phase => {
                let theta = self.parameter.unwrap_or(0.0);
                let phase = Complex64::new(theta.cos(), theta.sin());
                [[one, zero], [zero, phase]]
            }
            _ => [[one, zero], [zero, one]], // Two-qubit gates handled separately
        }
    }
}

// ─── Configuration ──────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QuantumCircuitConfig {
    pub n_qubits: usize,
    pub n_layers: usize,
    pub rotations_per_layer: usize,
    pub adaptive_depth: bool,
    pub max_depth: usize,
    pub entangling_gate: GateType,
    pub entangling_strategy: String,
    pub parameter_range: (f64, f64),
}

impl Default for QuantumCircuitConfig {
    fn default() -> Self {
        Self {
            n_qubits: 4,
            n_layers: 3,
            rotations_per_layer: 3,
            adaptive_depth: true,
            max_depth: 10,
            entangling_gate: GateType::CNOT,
            entangling_strategy: "linear".to_string(),
            parameter_range: (-PI, PI),
        }
    }
}

// ─── Variational Layer ──────────────────────────────────────

#[derive(Debug, Clone)]
pub struct VariationalLayer {
    pub gates: Vec<Gate>,
    pub n_parameters: usize,
    pub active: bool,
}

// ─── Quantum State ──────────────────────────────────────────

#[derive(Debug, Clone)]
pub struct QuantumState {
    pub amplitudes: Vec<Complex64>,
    pub n_qubits: usize,
}

impl QuantumState {
    pub fn zeros(n_qubits: usize) -> Self {
        let dim = 1 << n_qubits;
        let mut amplitudes = vec![Complex64::new(0.0, 0.0); dim];
        amplitudes[0] = Complex64::new(1.0, 0.0);
        Self {
            amplitudes,
            n_qubits,
        }
    }

    pub fn superposition(n_qubits: usize) -> Self {
        let dim = 1 << n_qubits;
        let norm = Complex64::new(1.0 / (dim as f64).sqrt(), 0.0);
        Self {
            amplitudes: vec![norm; dim],
            n_qubits,
        }
    }

    pub fn probabilities(&self) -> Vec<f64> {
        let norm: f64 = self.amplitudes.iter().map(|a| a.norm_sqr()).sum();
        self.amplitudes
            .iter()
            .map(|a| a.norm_sqr() / norm)
            .collect()
    }

    pub fn normalize(&mut self) {
        let norm: f64 = self
            .amplitudes
            .iter()
            .map(|a| a.norm_sqr())
            .sum::<f64>()
            .sqrt();
        if norm > 0.0 {
            for a in &mut self.amplitudes {
                *a /= norm;
            }
        }
    }

    pub fn entropy(&self) -> f64 {
        let probs = self.probabilities();
        probs
            .iter()
            .filter(|&&p| p > 0.0)
            .map(|&p| -p * p.log2())
            .sum()
    }
}

// ─── Optimization Step ──────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OptimizationStep {
    pub iteration: usize,
    pub cost: f64,
    pub gradient_norm: f64,
    pub parameters: Vec<f64>,
    pub active_layers: usize,
}

// ─── Circuit Summary ────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CircuitSummary {
    pub n_qubits: usize,
    pub n_layers: usize,
    pub total_parameters: usize,
    pub entangling_strategy: String,
    pub adaptive_depth: bool,
    pub active_layers: usize,
    pub current_cost: Option<f64>,
}

// ─── Quantum Decision Circuit ───────────────────────────────

pub struct QuantumDecisionCircuit {
    config: QuantumCircuitConfig,
    n_qubits: usize,
    n_layers: usize,
    parameters: Vec<f64>,
    layer_active: Vec<bool>,
    params_per_layer: usize,
    optimization_history: Vec<OptimizationStep>,
    current_cost: Option<f64>,
}

impl QuantumDecisionCircuit {
    pub fn new(config: QuantumCircuitConfig) -> Self {
        let n_qubits = config.n_qubits;
        let n_layers = config.n_layers;
        let params_per_layer = config.rotations_per_layer * n_qubits;
        let total_params = params_per_layer * n_layers;

        let mut rng = rand::thread_rng();
        let (low, high) = config.parameter_range;
        let parameters: Vec<f64> = (0..total_params)
            .map(|_| rng.gen_range(low..high))
            .collect();

        Self {
            n_qubits,
            n_layers,
            parameters,
            layer_active: vec![true; n_layers],
            params_per_layer,
            optimization_history: Vec::new(),
            current_cost: None,
            config,
        }
    }

    /// Execute the circuit and return probabilities.
    pub fn execute(&self, input_data: Option<&[f64]>) -> Vec<f64> {
        let _dim = 1 << self.n_qubits;
        let mut state = QuantumState::zeros(self.n_qubits);

        let mut params = self.parameters.clone();
        if let Some(input) = input_data {
            for (i, &val) in input.iter().enumerate() {
                if i * self.config.rotations_per_layer < params.len() {
                    params[i * self.config.rotations_per_layer] += val;
                }
            }
        }

        for layer_idx in 0..self.n_layers {
            if !self.layer_active[layer_idx] {
                continue;
            }
            let offset = layer_idx * self.params_per_layer;

            // Rotation block
            for q in 0..self.n_qubits {
                let p = offset + q * self.config.rotations_per_layer;
                if self.config.rotations_per_layer >= 1 {
                    apply_single_qubit_gate(
                        &mut state,
                        q,
                        &Gate::single(GateType::Rz, q, Some(params[p]), layer_idx),
                    );
                }
                if self.config.rotations_per_layer >= 2 && p + 1 < params.len() {
                    apply_single_qubit_gate(
                        &mut state,
                        q,
                        &Gate::single(GateType::Ry, q, Some(params[p + 1]), layer_idx),
                    );
                }
                if self.config.rotations_per_layer >= 3 && p + 2 < params.len() {
                    apply_single_qubit_gate(
                        &mut state,
                        q,
                        &Gate::single(GateType::Rz, q, Some(params[p + 2]), layer_idx),
                    );
                }
            }

            // Entangling block
            self.apply_entangling(&mut state);
        }

        state.probabilities()
    }

    fn apply_entangling(&self, state: &mut QuantumState) {
        match self.config.entangling_strategy.as_str() {
            "linear" => {
                for i in 0..self.n_qubits.saturating_sub(1) {
                    apply_cnot(state, i, i + 1);
                }
            }
            "circular" => {
                for i in 0..self.n_qubits {
                    apply_cnot(state, i, (i + 1) % self.n_qubits);
                }
            }
            "full" => {
                for i in 0..self.n_qubits {
                    for j in (i + 1)..self.n_qubits {
                        apply_cnot(state, i, j);
                    }
                }
            }
            _ => {}
        }
    }

    /// Make a decision (argmax of probabilities).
    pub fn decide(&self, input_data: Option<&[f64]>) -> usize {
        let probs = self.execute(input_data);
        probs
            .iter()
            .enumerate()
            .max_by(|(_, a), (_, b)| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal))
            .map(|(i, _)| i)
            .unwrap_or(0)
    }

    /// Compute cost (entropy-based or cross-entropy).
    pub fn compute_cost(&self, target_probs: Option<&[f64]>, input_data: Option<&[f64]>) -> f64 {
        let probs = self.execute(input_data);
        let eps = 1e-10;

        if let Some(target) = target_probs {
            let target: Vec<f64> = target.iter().map(|&p| p.max(eps)).collect();
            let sum: f64 = target.iter().sum();
            let target: Vec<f64> = target.iter().map(|&p| p / sum).collect();
            probs
                .iter()
                .zip(target.iter())
                .map(|(&p, &t)| if p > eps { -t * p.ln() } else { 0.0 })
                .sum()
        } else {
            probs
                .iter()
                .filter(|&&p| p > eps)
                .map(|&p| p * p.ln())
                .sum()
        }
    }

    /// Compute gradients using the parameter shift rule.
    pub fn compute_gradients(
        &self,
        target_probs: Option<&[f64]>,
        input_data: Option<&[f64]>,
        shift: f64,
    ) -> Vec<f64> {
        let mut gradients = vec![0.0; self.parameters.len()];
        let sin_shift = shift.sin();

        for i in 0..self.parameters.len() {
            let mut params_plus = self.parameters.clone();
            params_plus[i] += shift;
            let circuit_plus = self.clone_with_params(params_plus);
            let cost_plus = circuit_plus.compute_cost(target_probs, input_data);

            let mut params_minus = self.parameters.clone();
            params_minus[i] -= shift;
            let circuit_minus = self.clone_with_params(params_minus);
            let cost_minus = circuit_minus.compute_cost(target_probs, input_data);

            if sin_shift.abs() > 1e-10 {
                gradients[i] = (cost_plus - cost_minus) / (2.0 * sin_shift);
            }
        }

        gradients
    }

    fn clone_with_params(&self, params: Vec<f64>) -> Self {
        Self {
            config: self.config.clone(),
            n_qubits: self.n_qubits,
            n_layers: self.n_layers,
            parameters: params,
            layer_active: self.layer_active.clone(),
            params_per_layer: self.params_per_layer,
            optimization_history: Vec::new(),
            current_cost: None,
        }
    }

    /// Optimize circuit parameters using gradient descent.
    pub fn optimize(
        &mut self,
        target_probs: Option<&[f64]>,
        input_data: Option<&[f64]>,
        n_iterations: usize,
        learning_rate: f64,
        adaptive_lr: bool,
    ) -> Vec<OptimizationStep> {
        let mut lr = learning_rate;
        let mut best_cost = f64::INFINITY;
        let mut best_params = self.parameters.clone();

        for iteration in 0..n_iterations {
            let cost = self.compute_cost(target_probs, input_data);
            let gradients = self.compute_gradients(target_probs, input_data, PI / 2.0);
            let grad_norm: f64 = gradients.iter().map(|g| g * g).sum::<f64>().sqrt();

            if cost < best_cost {
                best_cost = cost;
                best_params = self.parameters.clone();
            }

            // Gradient clipping
            let clipped_gradients: Vec<f64> = if grad_norm > 5.0 {
                gradients.iter().map(|g| g * 5.0 / grad_norm).collect()
            } else {
                gradients
            };

            // Update parameters
            for (i, g) in clipped_gradients.iter().enumerate() {
                if i < self.parameters.len() {
                    self.parameters[i] -= lr * g;
                }
            }

            // Adaptive learning rate
            if adaptive_lr && iteration > 0 && !self.optimization_history.is_empty() {
                let prev_cost = self.optimization_history.last().unwrap().cost;
                if cost > prev_cost {
                    lr *= 0.8;
                } else if cost < prev_cost {
                    lr = (lr * 1.05).min(learning_rate * 2.0);
                }
                lr = lr.max(1e-6);
            }

            let active_layers = self.layer_active.iter().filter(|&&a| a).count();
            self.current_cost = Some(cost);

            self.optimization_history.push(OptimizationStep {
                iteration,
                cost,
                gradient_norm: grad_norm,
                parameters: self.parameters.clone(),
                active_layers,
            });

            // Adaptive layer depth
            if self.config.adaptive_depth && iteration > 0 && iteration % 20 == 0 {
                self.adapt_layer_depth(cost);
            }
        }

        if best_cost < self.current_cost.unwrap_or(f64::INFINITY) {
            self.parameters = best_params;
            self.current_cost = Some(best_cost);
        }

        self.optimization_history.clone()
    }

    /// Adaptively enable/disable layers based on recent cost variance and magnitude.
    pub fn adapt_layer_depth(&mut self, current_cost: f64) {
        if self.optimization_history.len() < 5 {
            return;
        }

        let recent: Vec<f64> = self
            .optimization_history
            .iter()
            .rev()
            .take(5)
            .map(|s| s.cost)
            .collect();
        let mean = recent.iter().sum::<f64>() / recent.len() as f64;
        let variance = recent.iter().map(|c| (c - mean).powi(2)).sum::<f64>() / recent.len() as f64;

        // Scale instability threshold by cost magnitude so high-cost problems
        // tolerate proportionally larger variance before pruning layers.
        let instability_threshold = 0.01 * (1.0 + current_cost.abs());
        if variance > instability_threshold && self.layer_active.iter().filter(|&&a| a).count() > 1 {
            // Unstable — deactivate last active layer
            for i in (0..self.n_layers).rev() {
                if self.layer_active[i] {
                    self.layer_active[i] = false;
                    break;
                }
            }
        } else if variance < 1e-6 {
            let active = self.layer_active.iter().filter(|&&a| a).count();
            if active < self.config.max_depth {
                for i in 0..self.n_layers {
                    if !self.layer_active[i] {
                        self.layer_active[i] = true;
                        break;
                    }
                }
            }
        }
    }

    /// Get the number of active layers.
    pub fn depth(&self) -> usize {
        self.layer_active.iter().filter(|&&a| a).count()
    }

    /// Get circuit summary.
    pub fn circuit_summary(&self) -> CircuitSummary {
        CircuitSummary {
            n_qubits: self.n_qubits,
            n_layers: self.n_layers,
            total_parameters: self.parameters.len(),
            entangling_strategy: self.config.entangling_strategy.clone(),
            adaptive_depth: self.config.adaptive_depth,
            active_layers: self.depth(),
            current_cost: self.current_cost,
        }
    }

    pub fn n_qubits(&self) -> usize {
        self.n_qubits
    }

    pub fn n_layers(&self) -> usize {
        self.n_layers
    }
}

// ─── Gate Application Helpers ───────────────────────────────

#[allow(clippy::needless_range_loop)]
fn apply_single_qubit_gate(state: &mut QuantumState, qubit: usize, gate: &Gate) {
    let matrix = gate.matrix();
    let dim = state.amplitudes.len();
    let n = state.n_qubits;

    let mut new_amps = state.amplitudes.clone();

    for i in 0..dim {
        let bit = (i >> (n - 1 - qubit)) & 1;
        let j = i ^ (1 << (n - 1 - qubit));

        if bit == 0 {
            new_amps[i] = matrix[0][0] * state.amplitudes[i] + matrix[0][1] * state.amplitudes[j];
        } else {
            new_amps[i] = matrix[1][0] * state.amplitudes[j] + matrix[1][1] * state.amplitudes[i];
        }
    }

    state.amplitudes = new_amps;
    state.normalize();
}

fn apply_cnot(state: &mut QuantumState, control: usize, target: usize) {
    let dim = state.amplitudes.len();
    let n = state.n_qubits;
    let mut new_amps = state.amplitudes.clone();

    for i in 0..dim {
        let control_bit = (i >> (n - 1 - control)) & 1;
        if control_bit == 1 {
            let j = i ^ (1 << (n - 1 - target));
            new_amps[i] = state.amplitudes[j];
            new_amps[j] = state.amplitudes[i];
        }
    }

    state.amplitudes = new_amps;
}

#[allow(dead_code)]
fn apply_cz(state: &mut QuantumState, control: usize, target: usize) {
    let dim = state.amplitudes.len();
    let n = state.n_qubits;

    for i in 0..dim {
        let control_bit = (i >> (n - 1 - control)) & 1;
        let target_bit = (i >> (n - 1 - target)) & 1;
        if control_bit == 1 && target_bit == 1 {
            state.amplitudes[i] = -state.amplitudes[i];
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_circuit_creation() {
        let config = QuantumCircuitConfig::default();
        let circuit = QuantumDecisionCircuit::new(config);
        assert_eq!(circuit.n_qubits, 4);
        assert_eq!(circuit.n_layers, 3);
    }

    #[test]
    fn test_execute_returns_probabilities() {
        let config = QuantumCircuitConfig {
            n_qubits: 2,
            n_layers: 1,
            ..Default::default()
        };
        let circuit = QuantumDecisionCircuit::new(config);
        let probs = circuit.execute(None);
        assert_eq!(probs.len(), 4);
        let sum: f64 = probs.iter().sum();
        assert!((sum - 1.0).abs() < 1e-6);
    }

    #[test]
    fn test_decide() {
        let config = QuantumCircuitConfig {
            n_qubits: 2,
            n_layers: 1,
            ..Default::default()
        };
        let circuit = QuantumDecisionCircuit::new(config);
        let decision = circuit.decide(None);
        assert!(decision < 4);
    }

    #[test]
    fn test_compute_cost() {
        let config = QuantumCircuitConfig {
            n_qubits: 2,
            n_layers: 1,
            ..Default::default()
        };
        let circuit = QuantumDecisionCircuit::new(config);
        let cost = circuit.compute_cost(None, None);
        assert!(cost.is_finite());
    }

    #[test]
    fn test_compute_gradients() {
        let config = QuantumCircuitConfig {
            n_qubits: 2,
            n_layers: 1,
            ..Default::default()
        };
        let circuit = QuantumDecisionCircuit::new(config);
        let gradients = circuit.compute_gradients(None, None, PI / 2.0);
        assert_eq!(gradients.len(), circuit.parameters.len());
    }

    #[test]
    fn test_optimize() {
        let config = QuantumCircuitConfig {
            n_qubits: 2,
            n_layers: 1,
            adaptive_depth: false,
            ..Default::default()
        };
        let mut circuit = QuantumDecisionCircuit::new(config);
        let history = circuit.optimize(None, None, 10, 0.01, false);
        assert_eq!(history.len(), 10);
    }

    #[test]
    fn test_gate_matrix_x() {
        let gate = Gate::single(GateType::X, 0, None, 0);
        let matrix = gate.matrix();
        assert!((matrix[0][1].re - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_gate_matrix_h() {
        let gate = Gate::single(GateType::H, 0, None, 0);
        let matrix = gate.matrix();
        assert!((matrix[0][0].re - 1.0 / 2.0_f64.sqrt()).abs() < 1e-10);
    }

    #[test]
    fn test_entangling_strategies() {
        for strategy in &["linear", "circular", "full"] {
            let config = QuantumCircuitConfig {
                n_qubits: 3,
                n_layers: 1,
                entangling_strategy: strategy.to_string(),
                ..Default::default()
            };
            let circuit = QuantumDecisionCircuit::new(config);
            let probs = circuit.execute(None);
            let sum: f64 = probs.iter().sum();
            assert!((sum - 1.0).abs() < 1e-6);
        }
    }

    #[test]
    fn test_quantum_state_zeros() {
        let state = QuantumState::zeros(3);
        assert_eq!(state.amplitudes.len(), 8);
        assert!((state.amplitudes[0].re - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_quantum_state_superposition() {
        let state = QuantumState::superposition(3);
        let probs = state.probabilities();
        let sum: f64 = probs.iter().sum();
        assert!((sum - 1.0).abs() < 1e-6);
    }

    #[test]
    fn test_circuit_summary() {
        let config = QuantumCircuitConfig::default();
        let circuit = QuantumDecisionCircuit::new(config);
        let summary = circuit.circuit_summary();
        assert_eq!(summary.n_qubits, 4);
    }

    #[test]
    fn test_adapt_layer_depth() {
        let config = QuantumCircuitConfig {
            n_qubits: 2,
            n_layers: 3,
            adaptive_depth: true,
            max_depth: 6,
            ..Default::default()
        };
        let mut circuit = QuantumDecisionCircuit::new(config);
        circuit.adapt_layer_depth(1.0);
        assert!(circuit.depth() >= 1);
    }
}
