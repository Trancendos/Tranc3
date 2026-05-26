"""
AeonMind Core — Rust Crate Entry Point.

Modules:
    - adaptive: Adaptive meta-learning with L-BFGS
    - genetic:  Genetic/DNA evolution engine
    - liquid:   Liquid State Machine (reservoir computing)
    - quantum:  Smart Adaptive Quantum Circuit Variational Layers
    - wasm_bridge: Intelligent WebAssembly Systems Interface

Definition Hierarchy (Tranc3 Custom):
    - AI: The overarching ML/LLM complex (Tier 3)
    - Agent: Lower-level autonomous AI (Tier 4)
    - Bot: Stateless service worker/function (Tier 5)

Tier System:
    - 0: HUMAN (highest authority)
    - 1: ORCHESTRATOR
    - 2: PRIME
    - 3: AI
    - 4: AGENT
    - 5: BOT
*/

use thiserror::Error;

pub mod adaptive;
pub mod genetic;
pub mod liquid;
pub mod quantum;

#[cfg(feature = "wasm")]
pub mod wasm_bridge;

#[cfg(feature = "python")]
pub mod python_bindings;

// ─── Error Types ────────────────────────────────────────────

#[derive(Error, Debug)]
pub enum AeonMindError {
    #[error("Dimension mismatch: expected {expected}, got {actual}")]
    DimensionMismatch { expected: usize, actual: usize },

    #[error("Invalid parameter: {0}")]
    InvalidParameter(String),

    #[error("Convergence failure after {iterations} iterations")]
    ConvergenceFailure { iterations: usize },

    #[error("Quantum error: {0}")]
    QuantumError(String),

    #[error("Evolution error: {0}")]
    EvolutionError(String),

    #[error("Reservoir error: {0}")]
    ReservoirError(String),

    #[error("Serialization error: {0}")]
    SerializationError(String),
}

// ─── Tier System ────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum Tier {
    Human = 0,
    Orchestrator = 1,
    Prime = 2,
    Ai = 3,
    Agent = 4,
    Bot = 5,
}

impl Tier {
    pub fn has_authority_over(&self, other: &Tier) -> bool {
        self < other
    }

    pub fn name(&self) -> &'static str {
        match self {
            Tier::Human => "HUMAN",
            Tier::Orchestrator => "ORCHESTRATOR",
            Tier::Prime => "PRIME",
            Tier::Ai => "AI",
            Tier::Agent => "AGENT",
            Tier::Bot => "BOT",
        }
    }

    pub fn level(&self) -> u8 {
        *self as u8
    }
}

// ─── SentinelChannel ────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum SentinelChannel {
    Platform,
    Agents,
    Models,
    Workflows,
    Security,
    Hive,
    Nexus,
    Bridge,
    Pillars,
    Infrastructure,
    Events,
}

// ─── Entity Types ───────────────────────────────────────────

#[derive(Debug, Clone)]
pub struct AiComplex {
    pub cognitive_capacity: f64,
    pub agent_count: usize,
    pub bot_count: usize,
    pub models: Vec<String>,
    pub llm_endpoints: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct AgentEntity {
    pub autonomy_threshold: f64,
    pub dna: Vec<f64>,
    pub intelligence_score: f64,
    pub parent_ai_id: String,
}

#[derive(Debug, Clone)]
pub struct BotService {
    pub endpoint: String,
    pub stateless: bool,
    pub parent_agent_id: String,
}

impl BotService {
    pub fn new(endpoint: &str, parent_agent_id: &str) -> Self {
        Self {
            endpoint: endpoint.to_string(),
            stateless: true, // Bots are always stateless
            parent_agent_id: parent_agent_id.to_string(),
        }
    }
}

#[derive(Debug, Clone)]
pub enum EntityType {
    Ai(AiComplex),
    Agent(AgentEntity),
    Bot(BotService),
}

// ─── Tests ──────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_tier_ordering() {
        assert!(Tier::Human < Tier::Ai);
        assert!(Tier::Ai < Tier::Agent);
        assert!(Tier::Agent < Tier::Bot);
    }

    #[test]
    fn test_tier_levels() {
        assert_eq!(Tier::Human.level(), 0);
        assert_eq!(Tier::Orchestrator.level(), 1);
        assert_eq!(Tier::Prime.level(), 2);
        assert_eq!(Tier::Ai.level(), 3);
        assert_eq!(Tier::Agent.level(), 4);
        assert_eq!(Tier::Bot.level(), 5);
    }

    #[test]
    fn test_tier_names() {
        assert_eq!(Tier::Human.name(), "HUMAN");
        assert_eq!(Tier::Ai.name(), "AI");
        assert_eq!(Tier::Agent.name(), "AGENT");
        assert_eq!(Tier::Bot.name(), "BOT");
    }

    #[test]
    fn test_authority() {
        assert!(Tier::Human.has_authority_over(&Tier::Ai));
        assert!(Tier::Ai.has_authority_over(&Tier::Agent));
        assert!(!Tier::Bot.has_authority_over(&Tier::Ai));
    }

    #[test]
    fn test_bot_always_stateless() {
        let bot = BotService::new("http://localhost:8080", "agent-0");
        assert!(bot.stateless);
    }
}
