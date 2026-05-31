"""
AeonMind Core — Foundation modules for the Tranc3 Infinity Ecosystem.
"""

from .adaptive import AdaptiveConfig, AdaptiveMetaLearner, AdaptiveSummary
from .definitions import (
    TIER_DESCRIPTIONS,
    TIER_NAMES,
    AgentEntity,
    AiComplex,
    BotService,
    SentinelChannel,
    Tier,
    sentinel_channels,
    tier_hierarchy,
)
from .fluidic_liquidic import FluidicState, LiquidReservoir, ReservoirConfig
from .frontier_agent import FrontierAgent, FrontierAgentConfig
from .genetic_dna import DNAEvolutionEngine, GenerationStats, GeneticConfig, Individual
from .quantum import QuantumCircuitConfig, QuantumDecisionCircuit
from .rust_bridge import (
    RustAdaptiveLearner,
    RustEvolutionEngine,
    RustLiquidReservoir,
    RustQuantumCircuit,
    has_rust_bindings,
    rust_version,
)
from .rust_bridge import (
    tier_hierarchy as rust_tier_hierarchy,
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
