"""
AeonMind Core — Foundation modules for the Tranc3 Infinity Ecosystem.
"""

from .definitions import (
    Tier,
    SentinelChannel,
    BotService,
    AgentEntity,
    AiComplex,
    TIER_NAMES,
    TIER_DESCRIPTIONS,
    tier_hierarchy,
    sentinel_channels,
)
from .adaptive import AdaptiveMetaLearner, AdaptiveConfig, AdaptiveSummary
from .genetic_dna import DNAEvolutionEngine, GeneticConfig, Individual, GenerationStats
from .fluidic_liquidic import LiquidReservoir, ReservoirConfig, FluidicState
from .quantum import QuantumDecisionCircuit, QuantumCircuitConfig
from .frontier_agent import FrontierAgent, FrontierAgentConfig
from .rust_bridge import (
    has_rust_bindings,
    rust_version,
    tier_hierarchy as rust_tier_hierarchy,
    RustLiquidReservoir,
    RustEvolutionEngine,
    RustQuantumCircuit,
    RustAdaptiveLearner,
)

__all__ = [
    # Definitions
    "Tier",
    "SentinelChannel",
    "BotService",
    "AgentEntity",
    "AiComplex",
    "TIER_NAMES",
    "TIER_DESCRIPTIONS",
    "tier_hierarchy",
    "sentinel_channels",
    # Adaptive
    "AdaptiveMetaLearner",
    "AdaptiveConfig",
    "AdaptiveSummary",
    # Genetic
    "DNAEvolutionEngine",
    "GeneticConfig",
    "Individual",
    "GenerationStats",
    # Liquid
    "LiquidReservoir",
    "ReservoirConfig",
    "FluidicState",
    # Quantum
    "QuantumDecisionCircuit",
    "QuantumCircuitConfig",
    # Frontier
    "FrontierAgent",
    "FrontierAgentConfig",
    # Rust Bridge
    "has_rust_bindings",
    "rust_version",
    "rust_tier_hierarchy",
    "RustLiquidReservoir",
    "RustEvolutionEngine",
    "RustQuantumCircuit",
    "RustAdaptiveLearner",
]
