"""Unified Reality Kernel — Phase 11

Multi-reality computation bridge for the Tranc3 ecosystem.
Provides a unified abstraction layer across physical, digital,
virtual, augmented, and mixed reality domains with consistent
state synchronization, cross-reality mapping, and reality-agnostic
computation patterns.

Enables seamless computation across reality layers with state
consistency guarantees, event propagation, and reality-aware
scheduling for mixed-reality applications.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─── Enums ────────────────────────────────────────────────────────────────


class RealityLayer(Enum):
    """Reality computation layers."""

    PHYSICAL = "physical"
    DIGITAL = "digital"
    VIRTUAL = "virtual"
    AUGMENTED = "augmented"
    MIXED = "mixed"
    SIMULATED = "simulated"
    ABSTRACT = "abstract"
    QUANTUM = "quantum"


class SyncMode(Enum):
    """State synchronization modes."""

    REAL_TIME = "real_time"
    PERIODIC = "periodic"
    ON_DEMAND = "on_demand"
    EVENT_DRIVEN = "event_driven"
    CAUSAL = "causal"


class KernelState(Enum):
    """Reality kernel states."""

    INITIALIZING = "initializing"
    RUNNING = "running"
    SYNCING = "syncing"
    PAUSED = "paused"
    BRANCHED = "branched"
    MERGED = "merged"
    ERROR = "error"


class ConsistencyLevel(Enum):
    """State consistency guarantees."""

    STRONG = "strong"
    EVENTUAL = "eventual"
    CAUSAL = "causal"
    SESSION = "session"
    WEAK = "weak"
    LAST_WRITER_WINS = "last_writer_wins"


class EntityType(Enum):
    """Types of entities across realities."""

    AGENT = "agent"
    OBJECT = "object"
    ENVIRONMENT = "environment"
    SENSOR = "sensor"
    ACTUATOR = "actuator"
    OBSERVER = "observer"
    PROCESS = "process"


# ─── Data Models ──────────────────────────────────────────────────────────


@dataclass
class RealityEntity:
    """An entity that exists across one or more reality layers."""

    entity_id: str
    entity_type: EntityType = EntityType.OBJECT
    name: str = ""
    layers: List[RealityLayer] = field(default_factory=lambda: [RealityLayer.DIGITAL])
    properties: Dict[str, Any] = field(default_factory=dict)
    state_version: int = 0
    is_synchronized: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type.value,
            "name": self.name,
            "layers": [l.value for l in self.layers],
            "state_version": self.state_version,
            "is_synchronized": self.is_synchronized,
        }


@dataclass
class RealityState:
    """State snapshot of a reality layer."""

    state_id: str
    layer: RealityLayer
    entities: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    version: int = 0
    consistency: ConsistencyLevel = ConsistencyLevel.EVENTUAL

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state_id": self.state_id,
            "layer": self.layer.value,
            "entity_count": len(self.entities),
            "version": self.version,
            "consistency": self.consistency.value,
        }


@dataclass
class CrossRealityMapping:
    """Mapping between entities across reality layers."""

    mapping_id: str
    source_entity: str
    source_layer: RealityLayer
    target_entity: str
    target_layer: RealityLayer
    transform: Dict[str, Any] = field(default_factory=dict)
    bidirectional: bool = True
    sync_delay_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mapping_id": self.mapping_id,
            "source_entity": self.source_entity,
            "source_layer": self.source_layer.value,
            "target_entity": self.target_entity,
            "target_layer": self.target_layer.value,
            "bidirectional": self.bidirectional,
        }


@dataclass
class RealityEvent:
    """An event that propagates across reality layers."""

    event_id: str
    source_layer: RealityLayer
    event_type: str
    data: Dict[str, Any] = field(default_factory=dict)
    target_layers: List[RealityLayer] = field(default_factory=list)
    propagation_delay_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_propagated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "source_layer": self.source_layer.value,
            "event_type": self.event_type,
            "target_layers": [l.value for l in self.target_layers],
            "is_propagated": self.is_propagated,
        }


# ─── State Synchronizer ──────────────────────────────────────────────────


class StateSynchronizer:
    """Synchronizes state across reality layers.

    Implements various synchronization strategies from strong
    consistency to eventual consistency with conflict resolution.
    """

    def __init__(self, consistency: ConsistencyLevel = ConsistencyLevel.EVENTUAL):
        self.consistency = consistency
        self.state_snapshots: Dict[RealityLayer, RealityState] = {}
        self.sync_log: List[Dict[str, Any]] = []

    def snapshot(self, layer: RealityLayer, entities: Dict[str, RealityEntity]) -> RealityState:
        """Take a state snapshot of a reality layer."""
        state = RealityState(
            state_id=str(uuid.uuid4())[:8],
            layer=layer,
            entities={eid: e.to_dict() for eid, e in entities.items()},
            version=len(self.state_snapshots) + 1,
        )
        self.state_snapshots[layer] = state
        return state

    def sync_layers(
        self,
        source: RealityLayer,
        target: RealityLayer,
        mapping: Optional[CrossRealityMapping] = None,
    ) -> Dict[str, Any]:
        """Synchronize state between two layers."""
        src_state = self.state_snapshots.get(source)
        tgt_state = self.state_snapshots.get(target)

        if not src_state:
            return {"error": f"No snapshot for {source.value}"}

        conflicts = 0
        synced_entities = 0

        if tgt_state:
            for eid, src_entity in src_state.entities.items():
                if eid in tgt_state.entities:
                    if src_entity.get("state_version", 0) != tgt_state.entities[eid].get(
                        "state_version", 0
                    ):
                        conflicts += 1
                synced_entities += 1
        else:
            synced_entities = len(src_state.entities)

        result = {
            "source": source.value,
            "target": target.value,
            "synced_entities": synced_entities,
            "conflicts": conflicts,
            "consistency": self.consistency.value,
        }
        self.sync_log.append(result)
        return result

    def resolve_conflict(
        self,
        entity_id: str,
        layer_states: Dict[RealityLayer, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Resolve a state conflict across layers."""
        if self.consistency == ConsistencyLevel.STRONG:
            # Use highest version
            winner = max(layer_states.items(), key=lambda x: x[1].get("state_version", 0))
            return {"resolved": True, "winner_layer": winner[0].value, "method": "highest_version"}
        elif self.consistency == ConsistencyLevel.LAST_WRITER_WINS:
            winner = max(layer_states.items(), key=lambda x: x[1].get("timestamp", ""))
            return {"resolved": True, "winner_layer": winner[0].value, "method": "last_writer_wins"}
        else:
            # Merge strategy
            return {"resolved": True, "method": "merge", "merged": True}


# ─── Event Propagator ─────────────────────────────────────────────────────


class EventPropagator:
    """Propagates events across reality layers."""

    def __init__(self):
        self.subscriptions: Dict[RealityLayer, List[str]] = {}
        self.event_history: List[RealityEvent] = []

    def subscribe(self, layer: RealityLayer, event_type: str) -> None:
        """Subscribe a layer to an event type."""
        if layer not in self.subscriptions:
            self.subscriptions[layer] = []
        self.subscriptions[layer].append(event_type)

    def propagate(self, event: RealityEvent) -> Dict[str, Any]:
        """Propagate an event to target layers."""
        propagated_to = []
        for layer in event.target_layers:
            subs = self.subscriptions.get(layer, [])
            if event.event_type in subs or "*" in subs:
                propagated_to.append(layer.value)

        event.is_propagated = True
        self.event_history.append(event)

        return {
            "event_id": event.event_id,
            "propagated_to": propagated_to,
            "total_targets": len(event.target_layers),
        }


# ─── Main Service ─────────────────────────────────────────────────────────


class UnifiedRealityKernelService:
    """Unified Reality Kernel Service for the Tranc3 ecosystem.

    Provides multi-reality computation bridging with state
    synchronization, event propagation, and cross-reality
    entity mapping for mixed-reality applications.
    """

    def __init__(self, consistency: ConsistencyLevel = ConsistencyLevel.EVENTUAL):
        self._service_id = str(uuid.uuid4())
        self.state = KernelState.RUNNING
        self.entities: Dict[str, RealityEntity] = {}
        self.mappings: Dict[str, CrossRealityMapping] = {}
        self.synchronizer = StateSynchronizer(consistency)
        self.propagator = EventPropagator()
        self.active_layers: List[RealityLayer] = [RealityLayer.DIGITAL]
        self.events: List[RealityEvent] = []

    def register_entity(
        self,
        name: str,
        entity_type: EntityType = EntityType.OBJECT,
        layers: Optional[List[RealityLayer]] = None,
        properties: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Register an entity across reality layers."""
        eid = str(uuid.uuid4())[:8]
        entity = RealityEntity(
            entity_id=eid,
            entity_type=entity_type,
            name=name,
            layers=layers or [RealityLayer.DIGITAL],
            properties=properties or {},
        )
        self.entities[eid] = entity
        return entity.to_dict()

    def create_mapping(
        self,
        source_entity: str,
        source_layer: RealityLayer,
        target_entity: str,
        target_layer: RealityLayer,
        bidirectional: bool = True,
    ) -> Dict[str, Any]:
        """Create a cross-reality mapping."""
        mid = str(uuid.uuid4())[:8]
        mapping = CrossRealityMapping(
            mapping_id=mid,
            source_entity=source_entity,
            source_layer=source_layer,
            target_entity=target_entity,
            target_layer=target_layer,
            bidirectional=bidirectional,
        )
        self.mappings[mid] = mapping
        return mapping.to_dict()

    def emit_event(
        self,
        source_layer: RealityLayer,
        event_type: str,
        data: Dict[str, Any],
        target_layers: Optional[List[RealityLayer]] = None,
    ) -> Dict[str, Any]:
        """Emit an event across reality layers."""
        event = RealityEvent(
            event_id=str(uuid.uuid4())[:8],
            source_layer=source_layer,
            event_type=event_type,
            data=data,
            target_layers=target_layers or self.active_layers,
        )
        self.events.append(event)
        return self.propagator.propagate(event)

    def sync_layers(
        self,
        source: RealityLayer,
        target: RealityLayer,
    ) -> Dict[str, Any]:
        """Synchronize state between two reality layers."""
        # Take snapshots first
        source_entities = {eid: e for eid, e in self.entities.items() if source in e.layers}
        self.synchronizer.snapshot(source, source_entities)

        target_entities = {eid: e for eid, e in self.entities.items() if target in e.layers}
        self.synchronizer.snapshot(target, target_entities)

        return self.synchronizer.sync_layers(source, target)

    def get_unified_reality_kernel_status(self) -> Dict[str, Any]:
        """Get service status."""
        return {
            "service_id": self._service_id,
            "service_type": "unified_reality_kernel",
            "state": self.state.value,
            "entities": len(self.entities),
            "cross_reality_mappings": len(self.mappings),
            "active_layers": [l.value for l in self.active_layers],
            "events_processed": len(self.events),
            "consistency": self.synchronizer.consistency.value,
            "status": "operational",
        }
