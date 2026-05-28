"""
AeonMind — Polyglot AI Framework for the Tranc3 Infinity Ecosystem.

AeonMind provides a multi-language framework combining:
  - Rust (PyO3) for performance-critical cores
  - Go (gRPC) for orchestration
  - Python for high-level orchestration and ML
  - WebAssembly for edge deployment

Custom Hierarchy:
  AI    = The overarching ML/LLM Complex (Tier 3)
  Agent = Lower-level autonomous AI (Tier 4)
  Bot   = Stateless service worker/function (Tier 5)
"""

__version__ = "0.9.0"
__author__ = "Trancendos"

# Core modules — always available
from .core.definitions import Tier, SentinelChannel, BotService, AgentEntity, AiComplex  # noqa: I001
from .core.adaptive import AdaptiveMetaLearner, AdaptiveConfig
from .core.genetic_dna import DNAEvolutionEngine, GeneticConfig
from .core.fluidic_liquidic import LiquidReservoir, ReservoirConfig
from .core.quantum import QuantumDecisionCircuit, QuantumCircuitConfig
from .core.frontier_agent import FrontierAgent, FrontierAgentConfig

# Systems — orchestrator
from .systems.orchestrator import LogicalOrchestrator

# Services — bot services
from .services.bot_services import BotServiceWorker, BotServiceRegistry

# Conditional Rust bindings
from .core.rust_bridge import has_rust_bindings, rust_version

__all__ = [
    # Version
    "__version__",
    # Definitions
    "Tier",
    "SentinelChannel",
    "BotService",
    "AgentEntity",
    "AiComplex",
    # Core
    "AdaptiveMetaLearner",
    "AdaptiveConfig",
    "DNAEvolutionEngine",
    "GeneticConfig",
    "LiquidReservoir",
    "ReservoirConfig",
    "QuantumDecisionCircuit",
    "QuantumCircuitConfig",
    "FrontierAgent",
    "FrontierAgentConfig",
    # Systems
    "LogicalOrchestrator",
    # Services
    "BotServiceWorker",
    "BotServiceRegistry",
    # Rust Bridge
    "has_rust_bindings",
    "rust_version",
]
