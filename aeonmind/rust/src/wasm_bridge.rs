/*
AeonMind Intelligent WebAssembly Systems Interface.

Implements adaptive fluidic state and intelligence scoring for
WASM-deployed agents:
    - FluidicAgentState with velocity, acceleration, energy, coherence, entropy
    - IntelligenceScore with multi-factor scoring
    - ScoringWeights for configurable component weights
    - WasmAgent for edge/browser agent deployment
    - Compression and decay of agent state

Part of the Tranc3 Infinity Ecosystem.
*/

use crate::{SentinelChannel, Tier};
use serde::{Deserialize, Serialize};

// ─── Scoring Weights ────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScoringWeights {
    pub decision_quality: f64,
    pub adaptation_speed: f64,
    pub state_coherence: f64,
    pub resource_efficiency: f64,
    pub communication: f64,
}

impl Default for ScoringWeights {
    fn default() -> Self {
        Self {
            decision_quality: 0.30,
            adaptation_speed: 0.20,
            state_coherence: 0.20,
            resource_efficiency: 0.15,
            communication: 0.15,
        }
    }
}

impl ScoringWeights {
    pub fn validate(&self) -> bool {
        let sum = self.decision_quality
            + self.adaptation_speed
            + self.state_coherence
            + self.resource_efficiency
            + self.communication;
        (sum - 1.0).abs() < 1e-6
    }

    pub fn normalize(&mut self) {
        let sum = self.decision_quality
            + self.adaptation_speed
            + self.state_coherence
            + self.resource_efficiency
            + self.communication;
        if sum > 0.0 {
            self.decision_quality /= sum;
            self.adaptation_speed /= sum;
            self.state_coherence /= sum;
            self.resource_efficiency /= sum;
            self.communication /= sum;
        }
    }
}

// ─── Fluidic Agent State ────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FluidicAgentState {
    pub state: Vec<f64>,
    pub velocity: Vec<f64>,
    pub acceleration: Vec<f64>,
    pub energy: f64,
    pub entropy: f64,
    pub coherence: f64,
    pub time_step: usize,
    pub memory_usage: usize,
    pub compression_ratio: f64,
}

impl FluidicAgentState {
    pub fn zeros(dimensions: usize) -> Self {
        Self {
            state: vec![0.0; dimensions],
            velocity: vec![0.0; dimensions],
            acceleration: vec![0.0; dimensions],
            energy: 0.0,
            entropy: 0.0,
            coherence: 1.0,
            time_step: 0,
            memory_usage: 0,
            compression_ratio: 1.0,
        }
    }

    /// Update the fluidic state with new input.
    #[allow(clippy::needless_range_loop)]
    pub fn update(&mut self, input: &[f64], leak_rate: f64) {
        let n = self.state.len().min(input.len());
        let mut new_acceleration = Vec::with_capacity(n);

        for i in 0..n {
            let new_velocity = (1.0 - leak_rate) * self.velocity[i] + leak_rate * input[i];
            let accel = new_velocity - self.velocity[i];
            new_acceleration.push(accel);
            self.velocity[i] = new_velocity;
            self.state[i] += self.velocity[i];
        }

        self.acceleration = new_acceleration;
        self.time_step += 1;

        // Update energy
        self.energy = self.state.iter().map(|v| v * v).sum::<f64>() / self.state.len() as f64;

        // Update entropy
        let sum_sq: f64 = self.state.iter().map(|v| v * v).sum();
        if sum_sq > 0.0 {
            let probs: Vec<f64> = self.state.iter().map(|v| (v * v) / sum_sq).collect();
            self.entropy = probs
                .iter()
                .filter(|&&p| p > 1e-10)
                .map(|&p| -p * p.ln())
                .sum();
        }

        // Update coherence (1 - normalized entropy)
        let max_entropy = (self.state.len() as f64).ln();
        self.coherence = if max_entropy > 0.0 {
            1.0 - self.entropy / max_entropy
        } else {
            1.0
        };
    }

    /// Compress the state by removing near-zero entries.
    pub fn compress(&mut self, threshold: f64) {
        let mut compressed = Vec::new();
        let mut compressed_vel = Vec::new();
        let mut compressed_acc = Vec::new();

        for i in 0..self.state.len() {
            if self.state[i].abs() > threshold || self.velocity[i].abs() > threshold {
                compressed.push(self.state[i]);
                compressed_vel.push(self.velocity[i]);
                compressed_acc.push(self.acceleration.get(i).copied().unwrap_or(0.0));
            }
        }

        if !compressed.is_empty() {
            let original_size = self.state.len();
            self.state = compressed;
            self.velocity = compressed_vel;
            self.acceleration = compressed_acc;
            self.compression_ratio = original_size as f64 / self.state.len() as f64;
            self.memory_usage = self.state.len() * 8; // 8 bytes per f64
        }
    }

    /// Apply exponential decay to the state.
    pub fn decay(&mut self, decay_rate: f64) {
        for v in &mut self.state {
            *v *= decay_rate;
        }
        for v in &mut self.velocity {
            *v *= decay_rate;
        }
        self.energy *= decay_rate;
    }
}

// ─── Intelligence Score ─────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IntelligenceScore {
    pub overall: f64,
    pub decision_quality: f64,
    pub adaptation_speed: f64,
    pub state_coherence: f64,
    pub resource_efficiency: f64,
    pub communication: f64,
}

impl IntelligenceScore {
    pub fn compute(
        decision_quality: f64,
        adaptation_speed: f64,
        state_coherence: f64,
        resource_efficiency: f64,
        communication: f64,
        weights: &ScoringWeights,
    ) -> Self {
        let overall = weights.decision_quality * decision_quality
            + weights.adaptation_speed * adaptation_speed
            + weights.state_coherence * state_coherence
            + weights.resource_efficiency * resource_efficiency
            + weights.communication * communication;

        Self {
            overall: overall.clamp(0.0, 1.0),
            decision_quality: decision_quality.clamp(0.0, 1.0),
            adaptation_speed: adaptation_speed.clamp(0.0, 1.0),
            state_coherence: state_coherence.clamp(0.0, 1.0),
            resource_efficiency: resource_efficiency.clamp(0.0, 1.0),
            communication: communication.clamp(0.0, 1.0),
        }
    }
}

// ─── WASM Agent Config ──────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WasmAgentConfig {
    pub agent_id: String,
    pub max_memory_bytes: usize,
    pub max_compute_budget: usize,
    pub state_dimensions: usize,
    pub scoring_weights: ScoringWeights,
    pub enable_compression: bool,
    pub compression_threshold: f64,
    pub tier: Tier,
    pub channels: Vec<SentinelChannel>,
}

impl Default for WasmAgentConfig {
    fn default() -> Self {
        Self {
            agent_id: "wasm-agent-0".to_string(),
            max_memory_bytes: 1024 * 1024, // 1MB
            max_compute_budget: 1000,
            state_dimensions: 64,
            scoring_weights: ScoringWeights::default(),
            enable_compression: true,
            compression_threshold: 0.01,
            tier: Tier::Agent,
            channels: vec![SentinelChannel::Agents, SentinelChannel::Workflows],
        }
    }
}

// ─── WASM Agent Summary ─────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WasmAgentSummary {
    pub agent_id: String,
    pub tier: String,
    pub time_step: usize,
    pub energy: f64,
    pub coherence: f64,
    pub intelligence_score: f64,
    pub decisions_made: usize,
    pub decision_accuracy: f64,
    pub compression_ratio: f64,
}

// ─── WASM Agent ─────────────────────────────────────────────

pub struct WasmAgent {
    config: WasmAgentConfig,
    fluidic_state: FluidicAgentState,
    intelligence_score: IntelligenceScore,
    decisions_made: usize,
    correct_decisions: usize,
    compute_used: usize,
}

impl WasmAgent {
    pub fn new(config: WasmAgentConfig) -> Self {
        let fluidic_state = FluidicAgentState::zeros(config.state_dimensions);
        let intelligence_score = IntelligenceScore {
            overall: 0.5,
            decision_quality: 0.5,
            adaptation_speed: 0.5,
            state_coherence: 1.0,
            resource_efficiency: 1.0,
            communication: 0.5,
        };

        Self {
            fluidic_state,
            intelligence_score,
            decisions_made: 0,
            correct_decisions: 0,
            compute_used: 0,
            config,
        }
    }

    /// Process input through the WASM agent.
    pub fn process(&mut self, input: &[f64]) -> Vec<f64> {
        if self.compute_used >= self.config.max_compute_budget {
            return self.fluidic_state.state.clone();
        }

        self.fluidic_state.update(input, 0.3);
        self.compute_used += 1;

        if self.config.enable_compression {
            self.fluidic_state
                .compress(self.config.compression_threshold);
        }

        self.fluidic_state.state.clone()
    }

    /// Make a decision based on the current state.
    pub fn decide(&mut self) -> usize {
        if self.fluidic_state.state.is_empty() {
            return 0;
        }
        self.decisions_made += 1;
        self.compute_used += 1;

        // Decision based on state energy distribution
        let max_idx = self
            .fluidic_state
            .state
            .iter()
            .enumerate()
            .max_by(|(_, a), (_, b)| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal))
            .map(|(i, _)| i);

        max_idx.unwrap_or(0)
    }

    /// Report the outcome of a decision.
    pub fn report_decision_outcome(&mut self, correct: bool) {
        if correct {
            self.correct_decisions += 1;
        }
        self.update_intelligence_score();
    }

    /// Update the intelligence score.
    pub fn update_intelligence_score(&mut self) {
        let decision_quality = if self.decisions_made > 0 {
            self.correct_decisions as f64 / self.decisions_made as f64
        } else {
            0.5
        };

        let resource_efficiency = if self.config.max_compute_budget > 0 {
            1.0 - (self.compute_used as f64 / self.config.max_compute_budget as f64).min(1.0)
        } else {
            1.0
        };

        self.intelligence_score = IntelligenceScore::compute(
            decision_quality,
            self.fluidic_state.coherence,
            self.fluidic_state.coherence,
            resource_efficiency,
            0.5, // Placeholder for communication score
            &self.config.scoring_weights,
        );
    }

    /// Reset the agent.
    pub fn reset(&mut self) {
        self.fluidic_state = FluidicAgentState::zeros(self.config.state_dimensions);
        self.decisions_made = 0;
        self.correct_decisions = 0;
        self.compute_used = 0;
    }

    /// Get agent summary.
    pub fn summary(&self) -> WasmAgentSummary {
        WasmAgentSummary {
            agent_id: self.config.agent_id.clone(),
            tier: self.config.tier.name().to_string(),
            time_step: self.fluidic_state.time_step,
            energy: self.fluidic_state.energy,
            coherence: self.fluidic_state.coherence,
            intelligence_score: self.intelligence_score.overall,
            decisions_made: self.decisions_made,
            decision_accuracy: if self.decisions_made > 0 {
                self.correct_decisions as f64 / self.decisions_made as f64
            } else {
                0.0
            },
            compression_ratio: self.fluidic_state.compression_ratio,
        }
    }
}

// ─── WASM Exports (conditional) ─────────────────────────────

#[cfg(all(feature = "wasm", target_arch = "wasm32"))]
mod wasm_exports {
    use super::*;
    use wasm_bindgen::prelude::*;

    #[wasm_bindgen]
    pub fn create_wasm_agent(dimensions: usize) -> *mut WasmAgent {
        let config = WasmAgentConfig {
            state_dimensions: dimensions,
            ..Default::default()
        };
        Box::into_raw(Box::new(WasmAgent::new(config)))
    }

    #[wasm_bindgen]
    pub fn process_input(agent_ptr: *mut WasmAgent, input: &[f64]) -> Vec<f64> {
        let agent = unsafe { &mut *agent_ptr };
        agent.process(input)
    }

    #[wasm_bindgen]
    pub fn get_agent_summary(agent_ptr: *const WasmAgent) -> JsValue {
        let agent = unsafe { &*agent_ptr };
        serde_wasm_bindgen::to_value(&agent.summary()).unwrap_or(JsValue::NULL)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_scoring_weights_default() {
        let weights = ScoringWeights::default();
        assert!(weights.validate());
    }

    #[test]
    fn test_scoring_weights_normalize() {
        let mut weights = ScoringWeights {
            decision_quality: 2.0,
            adaptation_speed: 2.0,
            state_coherence: 2.0,
            resource_efficiency: 2.0,
            communication: 2.0,
        };
        weights.normalize();
        assert!(weights.validate());
    }

    #[test]
    fn test_fluidic_state_zeros() {
        let state = FluidicAgentState::zeros(10);
        assert_eq!(state.state.len(), 10);
        assert_eq!(state.energy, 0.0);
    }

    #[test]
    fn test_fluidic_state_update() {
        let mut state = FluidicAgentState::zeros(5);
        state.update(&[1.0, 0.5, 0.0, -0.5, -1.0], 0.3);
        assert!(state.energy > 0.0);
        assert_eq!(state.time_step, 1);
    }

    #[test]
    fn test_fluidic_state_compress() {
        let mut state = FluidicAgentState::zeros(10);
        state.state[0] = 1.0;
        state.state[5] = 0.5;
        state.compress(0.1);
        assert!(state.compression_ratio > 1.0);
    }

    #[test]
    fn test_fluidic_state_decay() {
        let mut state = FluidicAgentState::zeros(3);
        state.state = vec![1.0, 1.0, 1.0];
        state.decay(0.5);
        assert!((state.state[0] - 0.5).abs() < 1e-10);
    }

    #[test]
    fn test_intelligence_score_compute() {
        let weights = ScoringWeights::default();
        let score = IntelligenceScore::compute(0.8, 0.7, 0.9, 0.6, 0.5, &weights);
        assert!((0.0..=1.0).contains(&score.overall));
    }

    #[test]
    fn test_wasm_agent_creation() {
        let config = WasmAgentConfig::default();
        let agent = WasmAgent::new(config);
        assert_eq!(agent.decisions_made, 0);
    }

    #[test]
    fn test_wasm_agent_process() {
        let config = WasmAgentConfig {
            state_dimensions: 5,
            ..Default::default()
        };
        let mut agent = WasmAgent::new(config);
        let output = agent.process(&[1.0, 0.5, 0.0, -0.5, -1.0]);
        assert!(!output.is_empty());
    }

    #[test]
    fn test_wasm_agent_decide() {
        let config = WasmAgentConfig {
            state_dimensions: 5,
            ..Default::default()
        };
        let mut agent = WasmAgent::new(config);
        agent.process(&[1.0, 0.5, 0.0, -0.5, -1.0]);
        let decision = agent.decide();
        assert!(decision < 5);
    }

    #[test]
    fn test_wasm_agent_report_outcome() {
        let config = WasmAgentConfig::default();
        let mut agent = WasmAgent::new(config);
        agent.process(&[1.0; 64]);
        agent.decide();
        agent.report_decision_outcome(true);
        assert_eq!(agent.correct_decisions, 1);
        assert!(agent.intelligence_score.overall > 0.0);
    }

    #[test]
    fn test_wasm_agent_summary() {
        let config = WasmAgentConfig::default();
        let agent = WasmAgent::new(config);
        let summary = agent.summary();
        assert_eq!(summary.agent_id, "wasm-agent-0");
    }
}
