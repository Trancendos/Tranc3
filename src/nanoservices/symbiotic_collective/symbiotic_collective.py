"""Symbiotic Collective — Phase 11.1

Collective intelligence framework for the Tranc3 ecosystem.
Implements symbiotic agent coordination, emergent collective
behaviors, stigmergic communication, quorum sensing, and
self-organizing collective decision-making.

Provides a framework for multiple agents to form symbiotic
relationships, share capabilities, and exhibit emergent
collective intelligence that surpasses individual agent
capabilities through synergy, specialization, and co-evolution.
"""

from __future__ import annotations

import logging
import random  # nosec B311 -- non-cryptographic simulation use
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


# ─── Enums ──────────────────────────────────────────────────────────────


class SymbiosisType(Enum):
    """Types of symbiotic relationships."""

    MUTUALISM = "mutualism"  # Both benefit
    COMMENSALISM = "commensalism"  # One benefits, other neutral
    PARASITISM = "parasitism"  # One benefits, other harmed
    AMENSALISM = "amensalism"  # One harmed, other neutral
    SYNERGISM = "synergism"  # Combined effect > sum
    SYNCHRONY = "synchrony"  # Temporal coordination
    ENDOSYMBIOSIS = "endosymbiosis"  # One inside another
    COEVOLUTION = "coevolution"  # Reciprocal adaptation


class CollectiveRole(Enum):
    """Roles agents can play in the collective."""

    LEADER = "leader"
    FOLLOWER = "follower"
    SPECIALIST = "specialist"
    GENERALIST = "generalist"
    MEDIATOR = "mediator"
    SCOUT = "scout"
    ARCHITECT = "architect"
    CUSTODIAN = "custodian"
    CATALYST = "catalyst"
    BRIDGE = "bridge"


class CommunicationMode(Enum):
    """Modes of inter-agent communication."""

    DIRECT = "direct"
    STIGMERGIC = "stigmergic"  # Environment-mediated
    BROADCAST = "broadcast"
    QUORUM = "quorum"  # Threshold-based
    PHEROMONE = "pheromone"  # Chemical-like signaling
    RESONANCE = "resonance"  # Frequency-based
    TELEMETRIC = "telemetric"  # Remote sensing


class CollectiveDecision(Enum):
    """Types of collective decisions."""

    CONSENSUS = "consensus"
    MAJORITY = "majority"
    WEIGHTED = "weighted"
    DELEGATED = "delegated"
    EMERGENT = "emergent"
    AUCTION = "auction"
    VETO = "veto"


class EmergenceLevel(Enum):
    """Levels of emergent collective behavior."""

    NONE = 0
    COORDINATION = 1  # Simple coordination
    COOPERATION = 2  # Active cooperation
    COLLABORATION = 3  # Deep collaboration
    INTEGRATION = 4  # Full integration
    SUPERORGANISM = 5  # Unified collective entity
    TRANSCENDENCE = 6  # Beyond individual comprehension


class CollectiveState(Enum):
    """States of the collective."""

    FORMING = "forming"
    STORMING = "storming"
    NORMING = "norming"
    PERFORMING = "performing"
    ADJOURNING = "adjourning"
    EVOLVING = "evolving"
    TRANSCENDENT = "transcendent"


# ─── Data Models ────────────────────────────────────────────────────────


@dataclass
class SymbioticAgent:
    """An agent in the symbiotic collective."""

    id: str = ""
    name: str = ""
    capabilities: List[str] = field(default_factory=list)
    role: CollectiveRole = CollectiveRole.GENERALIST
    fitness: float = 1.0
    energy: float = 1.0
    trust_scores: Dict[str, float] = field(default_factory=dict)
    symbiosis_partners: List[str] = field(default_factory=list)
    communication_preferences: List[CommunicationMode] = field(default_factory=list)
    knowledge: Dict[str, float] = field(default_factory=dict)
    specializations: List[str] = field(default_factory=list)
    reputation: float = 0.5
    generation: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.capabilities:
            self.capabilities = random.sample(
                [
                    "reasoning",
                    "perception",
                    "memory",
                    "planning",
                    "learning",
                    "communication",
                    "creativity",
                    "analysis",
                    "synthesis",
                    "evaluation",
                ],
                k=random.randint(2, 5),
            )
        if not self.communication_preferences:
            self.communication_preferences = [random.choice(list(CommunicationMode))]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role.value,
            "fitness": self.fitness,
            "energy": self.energy,
            "capability_count": len(self.capabilities),
            "partner_count": len(self.symbiosis_partners),
            "reputation": self.reputation,
            "generation": self.generation,
        }


@dataclass
class SymbioticRelation:
    """A symbiotic relationship between agents."""

    id: str = ""
    agent_a_id: str = ""
    agent_b_id: str = ""
    symbiosis_type: SymbiosisType = SymbiosisType.MUTUALISM
    strength: float = 0.5
    benefit_a: float = 0.0
    benefit_b: float = 0.0
    duration: int = 0
    stability: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "agent_a": self.agent_a_id[:8],
            "agent_b": self.agent_b_id[:8],
            "symbiosis_type": self.symbiosis_type.value,
            "strength": self.strength,
            "benefit_a": self.benefit_a,
            "benefit_b": self.benefit_b,
            "stability": self.stability,
        }


@dataclass
class StigmergicSignal:
    """A stigmergic (environment-mediated) signal."""

    id: str = ""
    agent_id: str = ""
    signal_type: str = ""
    content: Dict[str, Any] = field(default_factory=dict)
    intensity: float = 1.0
    decay_rate: float = 0.1
    location: str = ""
    timestamp: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def decay(self) -> float:
        """Apply decay and return new intensity."""
        self.intensity *= 1.0 - self.decay_rate
        return self.intensity

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "agent_id": self.agent_id[:8],
            "signal_type": self.signal_type,
            "intensity": self.intensity,
            "location": self.location,
        }


@dataclass
class CollectiveDecisionRecord:
    """Record of a collective decision."""

    id: str = ""
    decision_type: CollectiveDecision = CollectiveDecision.CONSENSUS
    proposal: str = ""
    proposer_id: str = ""
    votes: Dict[str, float] = field(default_factory=dict)
    outcome: str = ""
    participation_rate: float = 0.0
    consensus_level: float = 0.0
    timestamp: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "decision_type": self.decision_type.value,
            "proposal": self.proposal[:100],
            "outcome": self.outcome,
            "participation_rate": self.participation_rate,
            "consensus_level": self.consensus_level,
            "vote_count": len(self.votes),
        }


# ─── Core Engine ────────────────────────────────────────────────────────


class SymbiosisEngine:
    """Engine for managing symbiotic relationships."""

    def __init__(self):
        self.relations: Dict[str, SymbioticRelation] = {}

    def form_symbiosis(
        self,
        a: SymbioticAgent,
        b: SymbioticAgent,
        symbiosis_type: SymbiosisType = SymbiosisType.MUTUALISM,
    ) -> SymbioticRelation:
        """Form a symbiotic relationship between two agents."""
        compatibility = self._compute_compatibility(a, b)

        relation = SymbioticRelation(
            agent_a_id=a.id,
            agent_b_id=b.id,
            symbiosis_type=symbiosis_type,
            strength=compatibility,
        )

        if symbiosis_type == SymbiosisType.MUTUALISM:
            relation.benefit_a = compatibility * 0.3
            relation.benefit_b = compatibility * 0.3
        elif symbiosis_type == SymbiosisType.COMMENSALISM:
            relation.benefit_a = compatibility * 0.3
            relation.benefit_b = 0.0
        elif symbiosis_type == SymbiosisType.SYNERGISM:
            synergy = compatibility * 0.5
            relation.benefit_a = synergy
            relation.benefit_b = synergy

        self.relations[relation.id] = relation
        a.symbiosis_partners.append(b.id)
        b.symbiosis_partners.append(a.id)

        return relation

    def evaluate_symbiosis(
        self, relation: SymbioticRelation, a: SymbioticAgent, b: SymbioticAgent
    ) -> Dict[str, float]:
        """Evaluate the health of a symbiotic relationship."""
        a.fitness += relation.benefit_a
        b.fitness += relation.benefit_b

        relation.duration += 1
        if relation.benefit_a > 0 and relation.benefit_b > 0:
            relation.stability = min(1.0, relation.stability + 0.05)
        elif relation.benefit_a < 0 or relation.benefit_b < 0:
            relation.stability = max(0.0, relation.stability - 0.1)

        return {
            "strength": relation.strength,
            "stability": relation.stability,
            "benefit_a": relation.benefit_a,
            "benefit_b": relation.benefit_b,
        }

    def _compute_compatibility(self, a: SymbioticAgent, b: SymbioticAgent) -> float:
        """Compute compatibility between two agents."""
        cap_overlap = len(set(a.capabilities) & set(b.capabilities))
        cap_complement = len(set(a.capabilities) ^ set(b.capabilities))

        overlap_score = cap_overlap / max(len(a.capabilities) + len(b.capabilities), 1)
        complement_score = cap_complement / max(len(a.capabilities) + len(b.capabilities), 1)

        return 0.3 * overlap_score + 0.7 * complement_score


class StigmergicChannel:
    """Stigmergic communication channel."""

    def __init__(self, decay_rate: float = 0.1):
        self.decay_rate = decay_rate
        self.signals: Dict[str, StigmergicSignal] = {}

    def deposit(
        self, agent_id: str, signal_type: str, content: Dict[str, Any], location: str = ""
    ) -> StigmergicSignal:
        """Deposit a stigmergic signal."""
        signal = StigmergicSignal(
            agent_id=agent_id,
            signal_type=signal_type,
            content=content,
            decay_rate=self.decay_rate,
            location=location,
        )
        self.signals[signal.id] = signal
        return signal

    def sense(
        self, location: str = "", signal_type: str = "", min_intensity: float = 0.1
    ) -> List[StigmergicSignal]:
        """Sense stigmergic signals at a location."""
        results = []
        for signal in list(self.signals.values()):
            signal.decay()
            if signal.intensity < min_intensity:
                del self.signals[signal.id]
                continue
            if location and signal.location != location:
                continue
            if signal_type and signal.signal_type != signal_type:
                continue
            results.append(signal)
        return results


class QuorumSensor:
    """Quorum sensing for collective decision-making."""

    def __init__(self, quorum_threshold: float = 0.6):
        self.quorum_threshold = quorum_threshold
        self._signals: Dict[str, int] = {}

    def signal(self, agent_id: str, signal_type: str) -> bool:
        """An agent signals. Returns True if quorum reached."""
        key = signal_type
        self._signals[key] = self._signals.get(key, 0) + 1
        return self._signals[key] >= self.quorum_threshold * 100  # Simplified

    def reset(self, signal_type: str = "") -> None:
        """Reset quorum sensing."""
        if signal_type:
            self._signals.pop(signal_type, None)
        else:
            self._signals.clear()


class CollectiveIntelligenceEngine:
    """Main engine for collective intelligence."""

    def __init__(self, agent_count: int = 10):
        self.agents: Dict[str, SymbioticAgent] = {}
        self.symbiosis_engine = SymbiosisEngine()
        self.stigmergic_channel = StigmergicChannel()
        self.quorum_sensor = QuorumSensor()
        self.decisions: Dict[str, CollectiveDecisionRecord] = {}
        self.emergence_level = EmergenceLevel.NONE
        self.collective_state = CollectiveState.FORMING
        self._step_count = 0

        for i in range(agent_count):
            agent = SymbioticAgent(
                name=f"agent_{i}",
                role=random.choice(list(CollectiveRole)),
            )
            self.agents[agent.id] = agent

    def step(self) -> Dict[str, Any]:
        """Advance the collective by one step."""
        self._step_count += 1

        # Form symbiotic relationships
        agent_list = list(self.agents.values())
        if len(agent_list) >= 2 and random.random() < 0.3:
            a, b = random.sample(agent_list, 2)
            if b.id not in a.symbiosis_partners:
                stype = random.choice(list(SymbiosisType))
                self.symbiosis_engine.form_symbiosis(a, b, stype)

        # Evaluate existing relationships
        for rel in list(self.symbiosis_engine.relations.values()):
            a = self.agents.get(rel.agent_a_id)
            b = self.agents.get(rel.agent_b_id)
            if a and b:
                self.symbiosis_engine.evaluate_symbiosis(rel, a, b)
                if rel.stability < 0.1:
                    # Relationship dissolved
                    if b.id in a.symbiosis_partners:
                        a.symbiosis_partners.remove(b.id)
                    if a.id in b.symbiosis_partners:
                        b.symbiosis_partners.remove(a.id)

        # Stigmergic communication
        for agent in agent_list:
            if random.random() < 0.2:
                self.stigmergic_channel.deposit(
                    agent.id,
                    random.choice(["task", "resource", "threat", "opportunity"]),
                    {"step": self._step_count},
                )

        # Update emergence level
        self._update_emergence()

        # Update collective state
        self._update_state()

        return self.get_collective_stats()

    def decide(
        self,
        proposal: str,
        proposer_id: str,
        decision_type: CollectiveDecision = CollectiveDecision.CONSENSUS,
    ) -> CollectiveDecisionRecord:
        """Make a collective decision."""
        votes: Dict[str, float] = {}
        for agent in self.agents.values():
            vote = random.uniform(0, 1)
            if agent.id in proposer_id:
                vote = min(1.0, vote + 0.3)
            votes[agent.id] = vote

        if decision_type == CollectiveDecision.CONSENSUS:
            avg = sum(votes.values()) / len(votes) if votes else 0
            consensus_level = (
                1.0 - (sum(abs(v - avg) for v in votes.values()) / len(votes)) if votes else 0
            )
            outcome = "approved" if consensus_level > 0.5 and avg > 0.5 else "rejected"
        elif decision_type == CollectiveDecision.MAJORITY:
            yes = sum(1 for v in votes.values() if v > 0.5)
            outcome = "approved" if yes > len(votes) / 2 else "rejected"
            consensus_level = max(yes, len(votes) - yes) / len(votes) if votes else 0
        elif decision_type == CollectiveDecision.WEIGHTED:
            total_weight = sum(agent.reputation for agent in self.agents.values())
            weighted_sum = sum(
                self.agents[aid].reputation * v for aid, v in votes.items() if aid in self.agents
            )
            outcome = "approved" if weighted_sum / total_weight > 0.5 else "rejected"
            consensus_level = abs(weighted_sum / total_weight - 0.5) * 2
        else:
            outcome = "approved" if random.random() > 0.3 else "rejected"
            consensus_level = random.uniform(0.3, 0.9)

        record = CollectiveDecisionRecord(
            decision_type=decision_type,
            proposal=proposal,
            proposer_id=proposer_id,
            votes=votes,
            outcome=outcome,
            participation_rate=len(votes) / max(len(self.agents), 1),
            consensus_level=consensus_level,
        )
        self.decisions[record.id] = record
        return record

    def _update_emergence(self) -> None:
        """Update the emergence level based on collective metrics."""
        agent_list = list(self.agents.values())
        if not agent_list:
            self.emergence_level = EmergenceLevel.NONE
            return

        avg_partners = sum(len(a.symbiosis_partners) for a in agent_list) / len(agent_list)
        avg_fitness = sum(a.fitness for a in agent_list) / len(agent_list)
        relation_count = len(self.symbiosis_engine.relations)
        signal_count = len(self.stigmergic_channel.signals)

        score = 0.0
        score += min(avg_partners / 5.0, 1.0) * 0.3
        score += min(avg_fitness / 5.0, 1.0) * 0.3
        score += min(relation_count / 20.0, 1.0) * 0.2
        score += min(signal_count / 50.0, 1.0) * 0.2

        if score < 0.15:
            self.emergence_level = EmergenceLevel.NONE
        elif score < 0.3:
            self.emergence_level = EmergenceLevel.COORDINATION
        elif score < 0.5:
            self.emergence_level = EmergenceLevel.COOPERATION
        elif score < 0.7:
            self.emergence_level = EmergenceLevel.COLLABORATION
        elif score < 0.85:
            self.emergence_level = EmergenceLevel.INTEGRATION
        elif score < 0.95:
            self.emergence_level = EmergenceLevel.SUPERORGANISM
        else:
            self.emergence_level = EmergenceLevel.TRANSCENDENCE

    def _update_state(self) -> None:
        """Update the collective state based on dynamics."""
        if self._step_count < 10:
            self.collective_state = CollectiveState.FORMING
        elif self._step_count < 25:
            self.collective_state = CollectiveState.STORMING
        elif self._step_count < 50:
            self.collective_state = CollectiveState.NORMING
        elif self._step_count < 100:
            self.collective_state = CollectiveState.PERFORMING
        else:
            self.collective_state = CollectiveState.EVOLVING

        if self.emergence_level == EmergenceLevel.TRANSCENDENCE:
            self.collective_state = CollectiveState.TRANSCENDENT

    def get_collective_stats(self) -> Dict[str, Any]:
        """Get collective intelligence statistics."""
        agent_list = list(self.agents.values())
        return {
            "step_count": self._step_count,
            "agent_count": len(agent_list),
            "relation_count": len(self.symbiosis_engine.relations),
            "emergence_level": self.emergence_level.value,
            "collective_state": self.collective_state.value,
            "avg_fitness": sum(a.fitness for a in agent_list) / len(agent_list)
            if agent_list
            else 0,
            "avg_partners": sum(len(a.symbiosis_partners) for a in agent_list) / len(agent_list)
            if agent_list
            else 0,
            "active_signals": len(self.stigmergic_channel.signals),
            "decision_count": len(self.decisions),
        }


# ─── Service ────────────────────────────────────────────────────────────


class SymbioticCollectiveService:
    """Main service for symbiotic collective intelligence."""

    def __init__(self, agent_count: int = 10):
        self.engine = CollectiveIntelligenceEngine(agent_count)
        self._initialized = False

    def initialize(self) -> Dict[str, Any]:
        """Initialize the collective."""
        for _ in range(20):
            self.engine.step()

        self._initialized = True
        return {
            "status": "initialized",
            **self.engine.get_collective_stats(),
        }

    def step(self) -> Dict[str, Any]:
        """Advance the collective by one step."""
        return self.engine.step()

    def decide(self, proposal: str, decision_type: str = "consensus") -> Dict[str, Any]:
        """Make a collective decision."""
        dt = CollectiveDecision(decision_type)
        proposer = random.choice(list(self.engine.agents.keys())) if self.engine.agents else ""
        record = self.engine.decide(proposal, proposer, dt)
        return record.to_dict()

    def get_status(self) -> Dict[str, Any]:
        """Get service status."""
        stats = self.engine.get_collective_stats()
        return {
            "service": "symbiotic_collective",
            "initialized": self._initialized,
            **stats,
        }
