"""Event Sourcing & CQRS — Phase 12

Immutable event log with projections for auditability and
event-driven architecture. Zero-cost in-memory implementation.
"""

from __future__ import annotations  # noqa: I001

import hashlib
import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class EventType(Enum):
    SERVICE_CREATED = "service_created"
    SERVICE_UPDATED = "service_updated"
    SERVICE_DELETED = "service_deleted"
    CONFIG_CHANGED = "config_changed"
    SCALING_EVENT = "scaling_event"
    FAULT_INJECTED = "fault_injected"
    REPAIR_EXECUTED = "repair_executed"
    CIRCUIT_STATE_CHANGED = "circuit_state_changed"
    USER_ACTION = "user_action"
    SYSTEM_EVENT = "system_event"


@dataclass
class Event:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    event_type: EventType = EventType.SYSTEM_EVENT
    aggregate_id: str = ""
    aggregate_type: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    version: int = 1
    causation_id: Optional[str] = None
    correlation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def get_hash(self) -> str:
        content = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()


@dataclass
class Snapshot:
    aggregate_id: str
    aggregate_type: str
    state: Dict[str, Any]
    version: int
    timestamp: float = field(default_factory=time.time)


@dataclass
class Projection:
    name: str
    state: Dict[str, Any] = field(default_factory=dict)
    last_event_id: str = ""
    last_event_version: int = 0
    updated_at: float = field(default_factory=time.time)


class EventStore:
    """Immutable append-only event log."""

    def __init__(self, max_events: int = 100000):
        self._events: List[Event] = []
        self._snapshots: Dict[str, Snapshot] = {}
        self._max_events = max_events
        self._event_index: Dict[str, int] = {}  # event_id -> index

    def append(self, event: Event) -> bool:
        # Validate version
        if event.aggregate_id:
            last_version = self._get_version(event.aggregate_id)
            if event.version != last_version + 1:
                logger.warning(
                    "Version conflict for %s: expected %d, got %d",
                    event.aggregate_id,
                    last_version + 1,
                    event.version,
                )
                return False

        event.id = event.id or uuid.uuid4().hex[:12]
        self._events.append(event)
        self._event_index[event.id] = len(self._events) - 1

        # Trim if needed
        if len(self._events) > self._max_events:
            self._events = self._events[len(self._events) - self._max_events :]
            self._events = self._events[-self._max_events :]
            # Rebuild index
            self._event_index = {e.id: i for i, e in enumerate(self._events)}

        return True

    def get_events(self, aggregate_id: str = "", from_version: int = 0) -> List[Event]:
        if not aggregate_id:
            return list(self._events)
        return [
            e for e in self._events if e.aggregate_id == aggregate_id and e.version >= from_version
        ]

    def get_event(self, event_id: str) -> Optional[Event]:
        idx = self._event_index.get(event_id)
        if idx is not None and idx < len(self._events):
            return self._events[idx]
        return None

    def _get_version(self, aggregate_id: str) -> int:
        events = [e for e in self._events if e.aggregate_id == aggregate_id]
        return max((e.version for e in events), default=0)

    def save_snapshot(self, snapshot: Snapshot) -> None:
        self._snapshots[snapshot.aggregate_id] = snapshot

    def get_snapshot(self, aggregate_id: str) -> Optional[Snapshot]:
        return self._snapshots.get(aggregate_id)

    def get_all_snapshots(self) -> List[Snapshot]:
        return list(self._snapshots.values())


class ProjectionEngine:
    """Builds and maintains read-side projections from events."""

    def __init__(self, event_store: EventStore):
        self._store = event_store
        self._projections: Dict[str, Projection] = {}
        self._handlers: Dict[EventType, List[Callable[[Event], None]]] = {}

    def register_projection(self, name: str) -> Projection:
        if name not in self._projections:
            self._projections[name] = Projection(name=name)
        return self._projections[name]

    def register_handler(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def rebuild(self, projection_name: str) -> Projection:
        projection = self._projections.get(projection_name)
        if not projection:
            projection = self.register_projection(projection_name)

        projection.state = {}
        projection.last_event_id = ""
        projection.last_event_version = 0

        for event in self._store.get_events():
            self._apply_event(event, projection)

        projection.updated_at = time.time()
        logger.info(
            "Rebuilt projection %s with %d events", projection_name, len(self._store.get_events())
        )
        return projection

    def update(self, event: Event) -> None:
        for projection in self._projections.values():
            self._apply_event(event, projection)

    def _apply_event(self, event: Event, projection: Projection) -> None:
        handlers = self._handlers.get(event.event_type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error("Projection handler error: %s", e)

        projection.last_event_id = event.id
        projection.last_event_version = event.version
        projection.updated_at = time.time()

    def get_projection(self, name: str) -> Optional[Projection]:
        return self._projections.get(name)

    def get_all_projections(self) -> Dict[str, Projection]:
        return dict(self._projections)


class AggregateRoot:
    """Base class for event-sourced aggregates."""

    def __init__(self, aggregate_id: str, aggregate_type: str):
        self._aggregate_id = aggregate_id
        self._aggregate_type = aggregate_type
        self._version = 0
        self._uncommitted_events: List[Event] = []

    @property
    def aggregate_id(self) -> str:
        return self._aggregate_id

    @property
    def aggregate_type(self) -> str:
        return self._aggregate_type

    @property
    def version(self) -> int:
        return self._version

    def _apply_event(self, event: Event) -> None:
        self._version = event.version
        # Subclasses override to apply event to state

    def _raise_event(
        self, event_type: EventType, data: Dict[str, Any], metadata: Dict[str, Any] = None
    ) -> None:
        self._version += 1
        event = Event(
            event_type=event_type,
            aggregate_id=self._aggregate_id,
            aggregate_type=self._aggregate_type,
            data=data,
            metadata=metadata or {},
            version=self._version,
        )
        self._uncommitted_events.append(event)
        self._apply_event(event)

    def mark_events_committed(self) -> List[Event]:
        events = list(self._uncommitted_events)
        self._uncommitted_events.clear()
        return events

    def load_from_history(self, events: List[Event]) -> None:
        for event in events:
            self._apply_event(event)


class EventSourcingCQRSService:
    """Main service: event sourcing with CQRS projections."""

    def __init__(self, max_events: int = 100000):
        self._store = EventStore(max_events=max_events)
        self._projections = ProjectionEngine(self._store)
        self._aggregates: Dict[str, AggregateRoot] = {}

    def initialize(self) -> None:
        # Register default projections
        self._projections.register_projection("service_lifecycle")
        self._projections.register_projection("fault_timeline")
        self._projections.register_projection("scaling_history")

        # Register handlers
        self._projections.register_handler(EventType.SERVICE_CREATED, self._on_service_created)
        self._projections.register_handler(EventType.FAULT_INJECTED, self._on_fault_injected)
        self._projections.register_handler(EventType.SCALING_EVENT, self._on_scaling_event)

        logger.info("EventSourcingCQRSService initialized")

    def append_event(self, event: Event) -> bool:
        success = self._store.append(event)
        if success:
            self._projections.update(event)
        return success

    def get_events(self, aggregate_id: str = "", from_version: int = 0) -> List[Event]:
        return self._store.get_events(aggregate_id, from_version)

    def get_projection(self, name: str) -> Optional[Projection]:
        return self._projections.get_projection(name)

    def rebuild_projection(self, name: str) -> Projection:
        return self._projections.rebuild(name)

    def save_aggregate(self, aggregate: AggregateRoot) -> bool:
        events = aggregate.mark_events_committed()
        for event in events:
            if not self.append_event(event):
                return False
        self._aggregates[aggregate.aggregate_id] = aggregate
        return True

    def get_aggregate(self, aggregate_id: str) -> Optional[AggregateRoot]:
        return self._aggregates.get(aggregate_id)

    def _on_service_created(self, event: Event) -> None:
        proj = self._projections.get_projection("service_lifecycle")
        if proj:
            proj.state[event.aggregate_id] = {"created_at": event.timestamp, "status": "active"}

    def _on_fault_injected(self, event: Event) -> None:
        proj = self._projections.get_projection("fault_timeline")
        if proj:
            if "faults" not in proj.state:
                proj.state["faults"] = []
            proj.state["faults"].append(
                {
                    "service": event.aggregate_id,
                    "fault_type": event.data.get("fault_type"),
                    "timestamp": event.timestamp,
                }
            )

    def _on_scaling_event(self, event: Event) -> None:
        proj = self._projections.get_projection("scaling_history")
        if proj:
            if "events" not in proj.state:
                proj.state["events"] = []
            proj.state["events"].append(
                {
                    "service": event.aggregate_id,
                    "direction": event.data.get("direction"),
                    "timestamp": event.timestamp,
                }
            )
