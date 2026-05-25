# Dimensional/models.py
# Shared data models for Trancendos services

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class ServiceHealth(str, Enum):
    """Service health status"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ServiceCapability:
    """A capability offered by a service"""

    name: str
    version: str
    description: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ServiceInfo:
    """Service registration information"""

    name: str
    version: str
    endpoint: str
    health_url: str
    capabilities: List[ServiceCapability]
    health: ServiceHealth = ServiceHealth.UNKNOWN
    last_seen: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize service info to a JSON-friendly dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "endpoint": self.endpoint,
            "health_url": self.health_url,
            "capabilities": [c.__dict__ for c in self.capabilities],
            "health": self.health.value,
            "last_seen": self.last_seen.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class EventMessage:
    """Event bus message"""

    event_type: str
    source: str
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize event message to a JSON-friendly dictionary."""
        return {
            "event_type": self.event_type,
            "source": self.source,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
        }


@dataclass
class VectorClock:
    """Vector clock for causal ordering"""

    clock: Dict[str, int] = field(default_factory=dict)

    def increment(self, node_id: str) -> None:
        """Increment the counter for the given node."""
        self.clock[node_id] = self.clock.get(node_id, 0) + 1

    def merge(self, other: "VectorClock") -> None:
        """Merge another vector clock into this one, taking component-wise maximums."""
        for node, counter in other.clock.items():
            self.clock[node] = max(self.clock.get(node, 0), counter)

    def compare(self, other: "VectorClock") -> str:
        """Compare two vector clocks: 'before', 'after', 'concurrent', or 'equal'."""
        all_keys = set(self.clock.keys()) | set(other.clock.keys())

        self_before = any(self.clock.get(k, 0) < other.clock.get(k, 0) for k in all_keys)
        self_after = any(self.clock.get(k, 0) > other.clock.get(k, 0) for k in all_keys)

        if self_before and self_after:
            return "concurrent"
        elif self_before:
            return "before"
        elif self_after:
            return "after"
        else:
            return "equal"

    def to_dict(self) -> Dict[str, int]:
        """Return a shallow copy of the clock dictionary."""
        return self.clock.copy()
