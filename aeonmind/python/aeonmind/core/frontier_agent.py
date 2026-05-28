"""
AeonMind Frontier Agent — Unified Agent Combining All Subsystems.

The FrontierAgent integrates:
  - LiquidReservoir (fluidic temporal processing)
  - QuantumDecisionCircuit (variational decision-making)
  - AdaptiveMetaLearner (meta-learning optimization)
  - DNAEvolutionEngine (evolutionary policy optimization)

Together they form a Tier 4 autonomous agent capable of
perception, decision-making, learning, and evolution.
"""

from __future__ import annotations  # noqa: I001

import json
import time
from dataclasses import dataclass, field  # noqa: F401
from typing import Any, Dict, List, Optional  # noqa: UP035

import numpy as np

from .definitions import Tier, AgentEntity, SentinelChannel
from .adaptive import AdaptiveMetaLearner, AdaptiveConfig
from .genetic_dna import DNAEvolutionEngine, GeneticConfig
from .fluidic_liquidic import LiquidReservoir, ReservoirConfig, FluidicState  # noqa: F401
from .quantum import QuantumDecisionCircuit, QuantumCircuitConfig


@dataclass
class FrontierAgentConfig:
    """Configuration for the Frontier Agent."""
    name: str = "frontier-agent"
    state_dim: int = 10
    action_dim: int = 4
    # Subsystem configs
    reservoir_config: Optional[ReservoirConfig] = None  # noqa: UP045
    quantum_config: Optional[QuantumCircuitConfig] = None  # noqa: UP045
    adaptive_config: Optional[AdaptiveConfig] = None  # noqa: UP045
    genetic_config: Optional[GeneticConfig] = None  # noqa: UP045


@dataclass
class DecisionRecord:
    """Record of a decision made by the agent."""
    timestamp: float
    action: int
    confidence: float
    state_features: List[float]  # noqa: UP006
    outcome: Optional[bool] = None  # noqa: UP045


class FrontierAgent:
    """Frontier Agent — Tier 4 Autonomous AI.

    Combines liquid reservoir computing, quantum decision circuits,
    adaptive meta-learning, and DNA evolution into a unified agent
    capable of perception, decision-making, and self-improvement.
    """

    def __init__(self, config: Optional[FrontierAgentConfig] = None):  # noqa: UP045
        self.config = config or FrontierAgentConfig()
        self.id = f"agent-{int(time.time() * 1000) % 1000000:06d}"

        # Initialize subsystems
        reservoir_config = self.config.reservoir_config or ReservoirConfig(
            input_size=self.config.state_dim,
            reservoir_size=100,
        )
        self.reservoir = LiquidReservoir(reservoir_config)

        quantum_config = self.config.quantum_config or QuantumCircuitConfig(
            n_qubits=max(2, int(np.log2(max(self.config.action_dim, 2)) + 1)),
            n_layers=2,
        )
        self.quantum = QuantumDecisionCircuit(quantum_config)

        adaptive_config = self.config.adaptive_config or AdaptiveConfig()
        self.learner = AdaptiveMetaLearner(
            n_params=reservoir_config.reservoir_size,
            config=adaptive_config,
        )

        genetic_config = self.config.genetic_config or GeneticConfig(
            dna_length=self.config.state_dim,
        )
        self.evolution = DNAEvolutionEngine(genetic_config)

        # State tracking
        self._decision_history: List[DecisionRecord] = []  # noqa: UP006
        self._total_decisions = 0
        self._successful_decisions = 0
        self._intelligence_score = 0.5
        self._last_action: Optional[int] = None  # noqa: UP045

    def process(self, input_data: np.ndarray) -> Dict[str, Any]:  # noqa: UP006
        """Process input through the full agent pipeline.

        Pipeline: Reservoir → Quantum → Fluidic State → Evolution/Optimization
        """
        # Step 1: Reservoir computing for temporal processing
        reservoir_state = self.reservoir.step(input_data)

        # Step 2: Quantum decision
        self.quantum._parameters = reservoir_state[:len(self.quantum._parameters)] \
            if len(reservoir_state) >= len(self.quantum._parameters) \
            else np.pad(reservoir_state, (0, len(self.quantum._parameters) - len(reservoir_state)))
        probabilities = self.quantum.execute(use_pennylane=False)
        action = int(np.argmax(probabilities[:self.config.action_dim]))

        # Step 3: Fluidic state update
        fluidic = self.reservoir.fluidic_state()
        confidence = float(np.max(probabilities[:self.config.action_dim]))

        # Step 4: Adaptive learning step (use reservoir output as gradient signal)
        gradient = -reservoir_state[:self.learner.n_params] \
            if len(reservoir_state) >= self.learner.n_params \
            else np.pad(-reservoir_state, (0, self.learner.n_params - len(reservoir_state)))
        self.learner.step(gradient)

        # Record decision
        decision = DecisionRecord(
            timestamp=time.time(),
            action=action,
            confidence=confidence,
            state_features=reservoir_state[:8].tolist(),
        )
        self._decision_history.append(decision)
        self._total_decisions += 1
        self._last_action = action

        return {
            "action": action,
            "confidence": confidence,
            "probabilities": probabilities[:self.config.action_dim].tolist(),
            "fluidic_energy": fluidic.energy,
            "fluidic_coherence": fluidic.coherence,
            "intelligence": self._intelligence_score,
        }

    def report_outcome(self, success: bool) -> None:
        """Report the outcome of the last decision."""
        if self._decision_history:
            self._decision_history[-1].outcome = success

        if success:
            self._successful_decisions += 1

        # Update intelligence score
        if self._total_decisions > 0:
            success_rate = self._successful_decisions / self._total_decisions
            fluidic = self.reservoir.fluidic_state()
            self._intelligence_score = (
                0.4 * success_rate
                + 0.2 * fluidic.coherence
                + 0.2 * min(fluidic.energy, 1.0)
                + 0.1 * fluidic.compression
                + 0.1 * (1.0 / (1.0 + fluidic.entropy))
            )

    def to_entity(self) -> AgentEntity:
        """Convert to an AgentEntity for tier system integration."""
        entity = AgentEntity(
            id=self.id,
            name=self.config.name,
            tier=Tier.AGENT,
            capabilities=["quantum_decision", "reservoir_computing", "evolution", "adaptive_learning"],  # noqa: E501
            confidence=self._intelligence_score,
            status="active" if self._total_decisions > 0 else "idle",
        )
        entity.subscribe(SentinelChannel.AGENTS)
        return entity

    @classmethod
    def from_entity(cls, entity: AgentEntity, config: Optional[FrontierAgentConfig] = None) -> FrontierAgent:  # noqa: UP045, E501
        """Create a FrontierAgent from an AgentEntity."""
        agent = cls(config or FrontierAgentConfig(name=entity.name))
        agent.id = entity.id
        return agent

    def summary(self) -> Dict[str, Any]:  # noqa: UP006
        """Get a summary of the agent's current state."""
        fluidic = self.reservoir.fluidic_state()
        return {
            "name": self.config.name,
            "id": self.id,
            "tier": "AGENT (Tier 4)",
            "total_decisions": self._total_decisions,
            "successful_decisions": self._successful_decisions,
            "intelligence": round(self._intelligence_score, 4),
            "fluidic_energy": round(fluidic.energy, 4),
            "fluidic_coherence": round(fluidic.coherence, 4),
            "fluidic_entropy": round(fluidic.entropy, 4),
            "reservoir_size": self.reservoir.config.reservoir_size,
            "quantum_n_qubits": self.quantum.config.n_qubits,
            "quantum_n_layers": self.quantum.config.n_layers,
        }

    def summary_json(self) -> str:
        """Get summary as JSON string."""
        return json.dumps(self.summary(), indent=2)

    def reset(self) -> None:
        """Reset the agent to initial state."""
        self.reservoir.reset()
        self.quantum.reset()
        self.learner.reset()
        self.evolution.reset()
        self._decision_history = []
        self._total_decisions = 0
        self._successful_decisions = 0
        self._intelligence_score = 0.5
        self._last_action = None
