//! AeonMind WebAssembly Edge Agent
//!
//! Lightweight agent for edge/browser deployment using wasm-bindgen.
//! Implements intelligent fluidic state tracking and adaptive
//! decision-making for the Tranc3 Infinity Ecosystem.
//!
//! Custom Hierarchy:
//!   AI    = The overarching ML/LLM Complex (Tier 3)
//!   Agent = Lower-level autonomous AI (Tier 4)
//!   Bot   = Stateless service worker/function (Tier 5)

use rand::Rng;
use wasm_bindgen::prelude::*;

// ── Scoring Weights ─────────────────────────────────────────────────────────

/// Configurable weights for intelligence scoring components.
#[wasm_bindgen]
#[derive(Clone)]
pub struct ScoringWeights {
    decision_quality: f64,
    adaptation_speed: f64,
    state_coherence: f64,
    resource_efficiency: f64,
    communication: f64,
}

#[wasm_bindgen]
impl ScoringWeights {
    #[wasm_bindgen(constructor)]
    pub fn new() -> Self {
        Self {
            decision_quality: 0.30,
            adaptation_speed: 0.25,
            state_coherence: 0.20,
            resource_efficiency: 0.15,
            communication: 0.10,
        }
    }

    pub fn with_weights(
        decision_quality: f64,
        adaptation_speed: f64,
        state_coherence: f64,
        resource_efficiency: f64,
        communication: f64,
    ) -> Self {
        let mut w = Self {
            decision_quality,
            adaptation_speed,
            state_coherence,
            resource_efficiency,
            communication,
        };
        w.normalize();
        w
    }

    fn normalize(&mut self) {
        let total = self.decision_quality
            + self.adaptation_speed
            + self.state_coherence
            + self.resource_efficiency
            + self.communication;
        if total > 0.0 {
            self.decision_quality /= total;
            self.adaptation_speed /= total;
            self.state_coherence /= total;
            self.resource_efficiency /= total;
            self.communication /= total;
        }
    }

    pub fn validate(&self) -> bool {
        self.decision_quality >= 0.0
            && self.adaptation_speed >= 0.0
            && self.state_coherence >= 0.0
            && self.resource_efficiency >= 0.0
            && self.communication >= 0.0
    }
}

// ── Fluidic Agent State ─────────────────────────────────────────────────────

/// Adaptive fluidic state with velocity, acceleration, energy,
/// coherence, entropy, and compression tracking.
#[wasm_bindgen]
#[derive(Clone)]
pub struct FluidicAgentState {
    velocity: Vec<f64>,
    acceleration: Vec<f64>,
    energy: f64,
    coherence: f64,
    entropy: f64,
    compression: f64,
    timestamp: f64,
}

#[wasm_bindgen]
impl FluidicAgentState {
    #[wasm_bindgen(constructor)]
    pub fn new(dim: usize) -> Self {
        Self {
            velocity: vec![0.0; dim],
            acceleration: vec![0.0; dim],
            energy: 1.0,
            coherence: 1.0,
            entropy: 0.0,
            compression: 1.0,
            timestamp: 0.0,
        }
    }

    pub fn zeros(dim: usize) -> Self {
        Self::new(dim)
    }

    pub fn update(&mut self, new_state: &[f64], dt: f64) {
        let dim = self.velocity.len().min(new_state.len());
        for i in 0..dim {
            let new_accel = (new_state[i] - self.velocity[i]) / dt.max(1e-6);
            self.acceleration[i] = 0.9 * self.acceleration[i] + 0.1 * new_accel;
            self.velocity[i] = new_state[i];
        }

        // Energy = L2 norm of velocity
        self.energy = self.velocity.iter().map(|v| v * v).sum::<f64>().sqrt();

        // Coherence = inverse of velocity standard deviation
        let mean: f64 = self.velocity.iter().sum::<f64>() / self.velocity.len() as f64;
        let variance: f64 =
            self.velocity.iter().map(|v| (v - mean).powi(2)).sum::<f64>() / self.velocity.len() as f64;
        self.coherence = 1.0 / (1.0 + variance.sqrt());

        // Approximate entropy
        let total: f64 = self.velocity.iter().map(|v| v.abs()).sum::<f64>() + 1e-10;
        let mut entropy = 0.0;
        for v in &self.velocity {
            let p = (v.abs() + 1e-10) / total;
            if p > 0.0 {
                entropy -= p * p.ln();
            }
        }
        self.entropy = entropy;

        // Compression
        let max_val = self.velocity.iter().map(|v| v.abs()).fold(0.0_f64, f64::max) + 1e-10;
        self.compression = max_val / total;

        self.timestamp += dt;
    }

    pub fn compress(&self) -> Vec<f64> {
        let mean_vel = self.velocity.iter().sum::<f64>() / self.velocity.len() as f64;
        let vel_var: f64 =
            self.velocity.iter().map(|v| (v - mean_vel).powi(2)).sum::<f64>() / self.velocity.len() as f64;
        let mean_accel = self.acceleration.iter().sum::<f64>() / self.acceleration.len() as f64;

        vec![
            self.energy,
            self.coherence,
            self.entropy,
            self.compression,
            mean_vel,
            vel_var.sqrt(),
            mean_accel,
            self.timestamp,
        ]
    }

    pub fn decay(&mut self, rate: f64) {
        for v in &mut self.velocity {
            *v *= rate;
        }
        for a in &mut self.acceleration {
            *a *= rate;
        }
        self.energy *= rate;
    }

    // Getters
    pub fn energy(&self) -> f64 { self.energy }
    pub fn coherence(&self) -> f64 { self.coherence }
    pub fn entropy(&self) -> f64 { self.entropy }
    pub fn compression(&self) -> f64 { self.compression }
    pub fn timestamp(&self) -> f64 { self.timestamp }
}

// ── Intelligence Score ──────────────────────────────────────────────────────

/// Multi-factor intelligence scoring for agent evaluation.
#[wasm_bindgen]
#[derive(Clone)]
pub struct IntelligenceScore {
    decision_quality: f64,
    adaptation_speed: f64,
    state_coherence: f64,
    resource_efficiency: f64,
    communication: f64,
    overall: f64,
}

#[wasm_bindgen]
impl IntelligenceScore {
    #[wasm_bindgen(constructor)]
    pub fn new() -> Self {
        Self {
            decision_quality: 0.5,
            adaptation_speed: 0.5,
            state_coherence: 0.5,
            resource_efficiency: 0.5,
            communication: 0.5,
            overall: 0.5,
        }
    }

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
            decision_quality,
            adaptation_speed,
            state_coherence,
            resource_efficiency,
            communication,
            overall,
        }
    }

    // Getters
    pub fn decision_quality(&self) -> f64 { self.decision_quality }
    pub fn adaptation_speed(&self) -> f64 { self.adaptation_speed }
    pub fn state_coherence(&self) -> f64 { self.state_coherence }
    pub fn resource_efficiency(&self) -> f64 { self.resource_efficiency }
    pub fn communication(&self) -> f64 { self.communication }
    pub fn overall(&self) -> f64 { self.overall }
}

// ── WASM Agent ──────────────────────────────────────────────────────────────

/// AeonMind WebAssembly Edge Agent for browser/edge deployment.
#[wasm_bindgen]
pub struct WasmAgent {
    id: String,
    name: String,
    fluidic_state: FluidicAgentState,
    intelligence: IntelligenceScore,
    weights: ScoringWeights,
    state_dim: usize,
    action_dim: usize,
    total_decisions: u32,
    successful_decisions: u32,
}

#[wasm_bindgen]
impl WasmAgent {
    #[wasm_bindgen(constructor)]
    pub fn new(name: String, state_dim: usize, action_dim: usize) -> Self {
        Self {
            id: format!("wasm-agent-{}", js_sys::Date::now() as u64),
            name,
            fluidic_state: FluidicAgentState::new(state_dim),
            intelligence: IntelligenceScore::new(),
            weights: ScoringWeights::new(),
            state_dim,
            action_dim,
            total_decisions: 0,
            successful_decisions: 0,
        }
    }

    /// Process an input state and return an action index.
    pub fn process(&mut self, input_state: &[f64]) -> usize {
        self.fluidic_state.update(input_state, 0.1);
        let compressed = self.fluidic_state.compress();

        // Simple decision: weighted sum of compressed state mod action_dim
        let score: f64 = compressed.iter().enumerate().map(|(i, v)| v * (i as f64 + 1.0)).sum();
        let action = (score.abs() as usize) % self.action_dim.max(1);

        self.total_decisions += 1;
        action
    }

    /// Make a decision based on current fluidic state.
    pub fn decide(&mut self) -> usize {
        let compressed = self.fluidic_state.compress();
        let score: f64 = compressed.iter().sum();
        let action = (score.abs() as usize) % self.action_dim.max(1);
        self.total_decisions += 1;
        action
    }

    /// Report the outcome of a previous decision.
    pub fn report_decision_outcome(&mut self, success: bool) {
        if success {
            self.successful_decisions += 1;
        }

        let success_rate = if self.total_decisions > 0 {
            self.successful_decisions as f64 / self.total_decisions as f64
        } else {
            0.5
        };

        self.intelligence = IntelligenceScore::compute(
            success_rate,
            self.fluidic_state.coherence(),
            self.fluidic_state.energy().min(1.0),
            1.0 / (1.0 + self.fluidic_state.entropy()),
            self.fluidic_state.compression(),
            &self.weights,
        );
    }

    /// Reset the agent to initial state.
    pub fn reset(&mut self) {
        self.fluidic_state = FluidicAgentState::new(self.state_dim);
        self.intelligence = IntelligenceScore::new();
        self.total_decisions = 0;
        self.successful_decisions = 0;
    }

    /// Get agent ID.
    pub fn id(&self) -> String { self.id.clone() }

    /// Get agent name.
    pub fn name(&self) -> String { self.name.clone() }

    /// Get total decisions made.
    pub fn total_decisions(&self) -> u32 { self.total_decisions }

    /// Get successful decisions count.
    pub fn successful_decisions(&self) -> u32 { self.successful_decisions }

    /// Get overall intelligence score.
    pub fn intelligence_score(&self) -> f64 { self.intelligence.overall() }

    /// Get agent state as JSON-like string.
    pub fn summary(&self) -> String {
        format!(
            "{{\"id\":\"{}\",\"name\":\"{}\",\"total_decisions\":{},\"successful_decisions\":{},\"intelligence\":{:.4},\"energy\":{:.4},\"coherence\":{:.4}}}",
            self.id,
            self.name,
            self.total_decisions,
            self.successful_decisions,
            self.intelligence.overall(),
            self.fluidic_state.energy(),
            self.fluidic_state.coherence(),
        )
    }
}

// ── Free Functions (JS-accessible) ─────────────────────────────────────────

/// Create a new WasmAgent (convenience function).
#[wasm_bindgen]
pub fn create_wasm_agent(name: String, state_dim: usize, action_dim: usize) -> WasmAgent {
    WasmAgent::new(name, state_dim, action_dim)
}

/// Process input with an agent (convenience function).
#[wasm_bindgen]
pub fn process_input(agent: &mut WasmAgent, input_state: &[f64]) -> usize {
    agent.process(input_state)
}

/// Get agent summary string.
#[wasm_bindgen]
pub fn get_agent_summary(agent: &WasmAgent) -> String {
    agent.summary()
}

// ── Panic Hook ──────────────────────────────────────────────────────────────

/// Set up panic hook for better error messages in WASM.
#[wasm_bindgen(start)]
pub fn init() {
    console_error_panic_hook::set_once();
}

mod console_error_panic_hook {
    use wasm_bindgen::prelude::*;

    pub fn set_once() {
        // In production, use the console_error_panic_hook crate
        // For now, we use a minimal implementation
        #[wasm_bindgen(inline_js = "export function set_once() { console.log('AeonMind WASM initialized'); }")]
        extern "C" {
            fn set_once();
        }
        unsafe { set_once(); }
    }
}
