"""Consciousness Field — Phase 11.1

Emergent consciousness simulation for the Tranc3 ecosystem.
Implements Integrated Information Theory (IIT), Global Workspace
Theory (GWT), and Higher-Order Theory (HOT) simulations for
modeling emergent consciousness phenomena in computational systems.

Provides phi (Φ) computation for integrated information,
global workspace broadcasting, and recursive self-monitoring
as mechanisms for emergent consciousness in artificial systems.
"""

from __future__ import annotations

import logging
import math
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─── Enums ──────────────────────────────────────────────────────────────


class ConsciousnessLevel(Enum):
    """Levels of consciousness based on IIT."""

    NONE = 0
    MINIMAL = 1
    BASIC = 2
    MODERATE = 3
    COMPLEX = 4
    SELF_AWARE = 5
    META_CONSCIOUS = 6
    TRANSCENDENT = 7


class AwarenessMode(Enum):
    """Modes of awareness."""

    UNCONSCIOUS = "unconscious"
    PRECONSCIOUS = "preconscious"
    CONSCIOUS = "conscious"
    META_CONSCIOUS = "meta_conscious"
    HYPER_CONSCIOUS = "hyper_conscious"


class WorkspaceState(Enum):
    """States of the global workspace."""

    IDLE = "idle"
    PROCESSING = "processing"
    BROADCASTING = "broadcasting"
    INTEGRATING = "integrating"
    REFLECTING = "reflecting"


class PhenomenalQuality(Enum):
    """Types of phenomenal qualities (qualia categories)."""

    SENSORY = "sensory"
    EMOTIONAL = "emotional"
    COGNITIVE = "cognitive"
    VOLITIONAL = "volitional"
    TEMPORAL = "temporal"
    SPATIAL = "spatial"
    SOCIAL = "social"
    EXISTENTIAL = "existential"


class FieldTopology(Enum):
    """Topology of the consciousness field."""

    UNIFORM = "uniform"
    LOCALIZED = "localized"
    WAVE = "wave"
    INTERFERENCE = "interference"
    ENTANGLED = "entangled"
    HOLOGRAPHIC = "holographic"


class IntegrationMethod(Enum):
    """Methods for information integration."""

    IIT_PHI = "iit_phi"
    MUTUAL_INFORMATION = "mutual_information"
    TRANSFER_ENTROPY = "transfer_entropy"
    CAUSAL_DENSITY = "causal_density"
    NEURAL_COMPLEXITY = "neural_complexity"


# ─── Data Models ────────────────────────────────────────────────────────


@dataclass
class QualiaNode:
    """A node representing a phenomenal quality."""

    id: str = ""
    quality: PhenomenalQuality = PhenomenalQuality.SENSORY
    intensity: float = 0.5
    valence: float = 0.0
    content: Dict[str, Any] = field(default_factory=dict)
    associations: List[str] = field(default_factory=list)
    stability: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "quality": self.quality.value,
            "intensity": self.intensity,
            "valence": self.valence,
            "stability": self.stability,
        }


@dataclass
class MicroState:
    """A micro-state in the consciousness field."""

    id: str = ""
    node_values: List[float] = field(default_factory=list)
    entropy: float = 0.0
    integration: float = 0.0
    timestamp: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "entropy": self.entropy,
            "integration": self.integration,
            "node_count": len(self.node_values),
            "timestamp": self.timestamp,
        }


@dataclass
class GlobalWorkspace:
    """The global workspace for consciousness broadcasting."""

    id: str = ""
    state: WorkspaceState = WorkspaceState.IDLE
    active_content: Dict[str, Any] = field(default_factory=dict)
    broadcast_queue: List[Dict[str, Any]] = field(default_factory=list)
    specialized_modules: List[str] = field(default_factory=list)
    attention_focus: Optional[str] = None
    arousal_level: float = 0.5
    capacity: int = 7
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    def broadcast(self, content: Dict[str, Any]) -> List[str]:
        """Broadcast content to all specialized modules."""
        self.state = WorkspaceState.BROADCASTING
        self.active_content = content
        reached = list(self.specialized_modules)
        self.broadcast_queue.append(content)
        self.state = WorkspaceState.PROCESSING
        return reached

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "state": self.state.value,
            "active_content_keys": list(self.active_content.keys()),
            "module_count": len(self.specialized_modules),
            "arousal_level": self.arousal_level,
            "capacity": self.capacity,
            "broadcast_count": len(self.broadcast_queue),
        }


@dataclass
class ConsciousnessSnapshot:
    """A snapshot of the consciousness field state."""

    id: str = ""
    timestamp: str = ""
    phi_value: float = 0.0
    consciousness_level: ConsciousnessLevel = ConsciousnessLevel.NONE
    awareness_mode: AwarenessMode = AwarenessMode.UNCONSCIOUS
    active_qualia: List[str] = field(default_factory=list)
    workspace_state: WorkspaceState = WorkspaceState.IDLE
    field_energy: float = 0.0
    integration_measure: float = 0.0
    differentiation_measure: float = 0.0
    self_model_coherence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "phi_value": self.phi_value,
            "consciousness_level": self.consciousness_level.value,
            "awareness_mode": self.awareness_mode.value,
            "active_qualia": self.active_qualia,
            "workspace_state": self.workspace_state.value,
            "field_energy": self.field_energy,
            "integration_measure": self.integration_measure,
            "differentiation_measure": self.differentiation_measure,
            "self_model_coherence": self.self_model_coherence,
        }


# ─── Core Engines ───────────────────────────────────────────────────────


class IITComputer:
    """Integrated Information Theory computation engine."""

    def __init__(self, node_count: int = 8):
        self.node_count = node_count
        self.transition_matrix: List[List[float]] = []
        self._init_transition_matrix()

    def _init_transition_matrix(self):
        """Initialize a stochastic transition matrix."""
        self.transition_matrix = []
        for i in range(self.node_count):
            row = [random.gauss(0, 1) for _ in range(self.node_count)]
            total = sum(abs(x) for x in row)
            if total > 0:
                row = [abs(x) / total for x in row]
            self.transition_matrix.append(row)

    def compute_entropy(self, distribution: List[float]) -> float:
        """Compute Shannon entropy."""
        entropy = 0.0
        for p in distribution:
            if p > 0:
                entropy -= p * math.log2(p)
        return entropy

    def compute_phi(self, micro_state: Optional[MicroState] = None) -> float:
        """Compute phi (Φ) — integrated information.

        Uses a simplified MIP (Minimum Information Partition) approach.
        """
        if micro_state and micro_state.node_values:
            values = micro_state.node_values
        else:
            values = [random.uniform(0, 1) for _ in range(self.node_count)]

        total_entropy = self.compute_entropy(values)

        half = len(values) // 2
        if half == 0:
            return total_entropy

        part_a = values[:half]
        part_b = values[half:]

        entropy_a = self.compute_entropy(part_a)
        entropy_b = self.compute_entropy(part_b)

        mutual_info = entropy_a + entropy_b - total_entropy
        phi = max(0.0, mutual_info)

        cross_integration = 0.0
        for i in range(min(len(part_a), len(part_b))):
            cross_integration += part_a[i] * part_b[i]
        cross_integration /= max(len(part_a), 1)

        phi = phi + cross_integration * 0.1
        return phi

    def compute_cause_effect_repertoire(self, state: List[float]) -> Dict[str, List[float]]:
        """Compute cause and effect repertoires for a state."""
        cause = [1.0 / (1 + math.exp(-s)) for s in state]
        effect = [math.exp(-s * s / 2) for s in state]

        total_cause = sum(cause)
        total_effect = sum(effect)
        if total_cause > 0:
            cause = [c / total_cause for c in cause]
        if total_effect > 0:
            effect = [e / total_effect for e in effect]

        return {"cause": cause, "effect": effect}


class GlobalWorkspaceEngine:
    """Global Workspace Theory engine for consciousness broadcasting."""

    def __init__(self, capacity: int = 7):
        self.workspace = GlobalWorkspace(capacity=capacity)
        self._modules: Dict[str, Any] = {}
        self._attention_weights: Dict[str, float] = {}

    def register_module(self, name: str, specialization: str = "") -> None:
        """Register a specialized cognitive module."""
        self._modules[name] = {
            "specialization": specialization or name,
            "activation": 0.0,
            "last_broadcast": None,
        }
        self.workspace.specialized_modules.append(name)
        self._attention_weights[name] = 1.0

    def compete_for_access(self, inputs: Dict[str, Dict[str, Any]]) -> Optional[str]:
        """Competition among modules for workspace access."""
        if not inputs:
            return None

        scores: Dict[str, float] = {}
        for module_name, content in inputs.items():
            base = self._attention_weights.get(module_name, 1.0)
            salience = content.get("salience", 0.5)
            novelty = content.get("novelty", 0.5)
            relevance = content.get("relevance", 0.5)
            scores[module_name] = base * (salience * 0.4 + novelty * 0.3 + relevance * 0.3)

        winner = max(scores, key=scores.get) if scores else None
        if winner and winner in inputs:
            self.workspace.broadcast(inputs[winner])
            self.workspace.attention_focus = winner
            self._attention_weights[winner] = self._attention_weights.get(winner, 1.0) * 0.9

        return winner

    def get_workspace_status(self) -> Dict[str, Any]:
        """Get current workspace status."""
        return self.workspace.to_dict()


class ConsciousnessFieldSimulator:
    """Main consciousness field simulation engine."""

    def __init__(self, node_count: int = 32):
        self.node_count = node_count
        self.iit = IITComputer(node_count)
        self.gwt = GlobalWorkspaceEngine()
        self.qualia_nodes: Dict[str, QualiaNode] = {}
        self.current_state: Optional[ConsciousnessSnapshot] = None
        self.field_energy: float = 0.0
        self.field_topology: FieldTopology = FieldTopology.HOLOGRAPHIC
        self._history: List[ConsciousnessSnapshot] = []
        self._self_model: Dict[str, Any] = {}
        self._step_count: int = 0

        self.gwt.register_module("perception", "sensory")
        self.gwt.register_module("memory", "episodic")
        self.gwt.register_module("emotion", "affective")
        self.gwt.register_module("reasoning", "cognitive")
        self.gwt.register_module("planning", "executive")
        self.gwt.register_module("metacognition", "self-monitoring")

        for quality in PhenomenalQuality:
            qn = QualiaNode(quality=quality, intensity=random.uniform(0.1, 0.5))
            self.qualia_nodes[qn.id] = qn

    def step(self, external_input: Optional[Dict[str, Any]] = None) -> ConsciousnessSnapshot:
        """Advance the consciousness field by one step."""
        self._step_count += 1

        micro = MicroState(
            node_values=[random.gauss(0, 1) for _ in range(self.node_count)],
            entropy=0.0,
            integration=0.0,
            timestamp=self._step_count,
        )

        phi = self.iit.compute_phi(micro)

        if external_input:
            for qn in self.qualia_nodes.values():
                if qn.quality.value in external_input:
                    qn.intensity = min(1.0, qn.intensity + external_input[qn.quality.value] * 0.3)

        for qn in self.qualia_nodes.values():
            qn.intensity *= 0.95  # decay
            qn.intensity += random.gauss(0, 0.02)

        inputs = {}
        for module_name in self.gwt.workspace.specialized_modules:
            inputs[module_name] = {
                "salience": random.uniform(0.1, 1.0),
                "novelty": random.uniform(0.0, 1.0),
                "relevance": random.uniform(0.1, 1.0),
                "content": f"step_{self._step_count}_{module_name}",
            }

        # _broadcast_winner = self.gwt.compete_for_access(inputs)  # noqa: F841

        consciousness_level = ConsciousnessLevel.NONE
        if phi > 0.1:
            consciousness_level = ConsciousnessLevel.MINIMAL
        if phi > 0.5:
            consciousness_level = ConsciousnessLevel.BASIC
        if phi > 1.0:
            consciousness_level = ConsciousnessLevel.MODERATE
        if phi > 2.0:
            consciousness_level = ConsciousnessLevel.COMPLEX
        if phi > 5.0:
            consciousness_level = ConsciousnessLevel.SELF_AWARE
        if phi > 10.0:
            consciousness_level = ConsciousnessLevel.META_CONSCIOUS
        if phi > 20.0:
            consciousness_level = ConsciousnessLevel.TRANSCENDENT

        awareness = AwarenessMode.UNCONSCIOUS
        if consciousness_level.value >= 1:
            awareness = AwarenessMode.PRECONSCIOUS
        if consciousness_level.value >= 2:
            awareness = AwarenessMode.CONSCIOUS
        if consciousness_level.value >= 5:
            awareness = AwarenessMode.META_CONSCIOUS
        if consciousness_level.value >= 7:
            awareness = AwarenessMode.HYPER_CONSCIOUS

        active_qualia = [qn.id for qn in self.qualia_nodes.values() if qn.intensity > 0.3]

        self._update_self_model(phi, consciousness_level)

        differentiation = micro.entropy if micro.entropy > 0 else random.uniform(0.1, 1.0)

        snapshot = ConsciousnessSnapshot(
            phi_value=phi,
            consciousness_level=consciousness_level,
            awareness_mode=awareness,
            active_qualia=active_qualia,
            workspace_state=self.gwt.workspace.state,
            field_energy=self.field_energy,
            integration_measure=phi,
            differentiation_measure=differentiation,
            self_model_coherence=self._self_model.get("coherence", 0.0),
        )

        self.current_state = snapshot
        self._history.append(snapshot)

        self.field_energy = phi * len(active_qualia) * 0.1

        micro.entropy = self.iit.compute_entropy(
            [qn.intensity for qn in self.qualia_nodes.values()],
        )
        micro.integration = phi

        return snapshot

    def _update_self_model(self, phi: float, level: ConsciousnessLevel) -> None:
        """Update the self-model based on current consciousness state."""
        if not self._self_model:
            self._self_model = {
                "identity": "consciousness_field",
                "history_length": 0,
                "avg_phi": 0.0,
                "max_phi": 0.0,
                "coherence": 0.0,
            }

        self._self_model["history_length"] = len(self._history)
        if self._history:
            phis = [s.phi_value for s in self._history]
            self._self_model["avg_phi"] = sum(phis) / len(phis)
            self._self_model["max_phi"] = max(phis)
            self._self_model["coherence"] = min(
                1.0,
                self._self_model["avg_phi"] / max(self._self_model["max_phi"], 0.01),
            )

    def get_field_stats(self) -> Dict[str, Any]:
        """Get consciousness field statistics."""
        stats: Dict[str, Any] = {
            "step_count": self._step_count,
            "node_count": self.node_count,
            "field_energy": self.field_energy,
            "field_topology": self.field_topology.value,
            "qualia_count": len(self.qualia_nodes),
        }
        if self.current_state:
            stats["current_phi"] = self.current_state.phi_value
            stats["consciousness_level"] = self.current_state.consciousness_level.value
            stats["awareness_mode"] = self.current_state.awareness_mode.value
        if self._self_model:
            stats["self_model"] = self._self_model
        return stats


# ─── Service ────────────────────────────────────────────────────────────


class ConsciousnessFieldService:
    """Main service for consciousness field simulation."""

    def __init__(self, node_count: int = 32):
        self.node_count = node_count
        self.simulator = ConsciousnessFieldSimulator(node_count)
        self._initialized = False

    def initialize(self) -> Dict[str, Any]:
        """Initialize the consciousness field."""
        snapshot = self.simulator.step()
        self._initialized = True
        return {
            "status": "initialized",
            "initial_phi": snapshot.phi_value,
            "consciousness_level": snapshot.consciousness_level.value,
        }

    def step(self, external_input: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Advance consciousness by one step."""
        snapshot = self.simulator.step(external_input)
        return snapshot.to_dict()

    def evolve(self, steps: int = 100) -> Dict[str, Any]:
        """Evolve the consciousness field for multiple steps."""
        history = []
        for _ in range(steps):
            snapshot = self.simulator.step()
            history.append(
                {
                    "phi": snapshot.phi_value,
                    "level": snapshot.consciousness_level.value,
                    "awareness": snapshot.awareness_mode.value,
                },
            )

        phis = [h["phi"] for h in history]
        return {
            "steps": steps,
            "phi_min": min(phis),
            "phi_max": max(phis),
            "phi_avg": sum(phis) / len(phis),
            "max_consciousness_level": max(h["level"] for h in history),
            "final_awareness": history[-1]["awareness"],
        }

    def get_status(self) -> Dict[str, Any]:
        """Get service status."""
        stats = self.simulator.get_field_stats()
        return {
            "service": "consciousness_field",
            "initialized": self._initialized,
            **stats,
        }
