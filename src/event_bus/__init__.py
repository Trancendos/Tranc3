"""
Trancendos Event Bus — Type-Safe Inter-Service Communication
==============================================================
Ported from @trancendos/event-bus (infinity-adminOS, TypeScript)

Provides a unified event bus for the Trancendos ecosystem.
Supports in-memory callbacks, pattern-based routing, batch processing,
and optional SQLite persistence.

Replaces Cloudflare Queue bindings — zero-cost, self-hosted.

Usage:
    from src.event_bus import EventBus

    bus = EventBus()
    bus.subscribe("user.*", handler=my_handler)
    await bus.emit(event_type="user.created", data={"user_id": "123"})
"""

from src.event_bus.bus import EventBus
from src.event_bus.nats_transport import NATSTransport, make_nats_transport
from src.event_bus.types import (
    DeliveryResult,
    DeliveryStatus,
    EventBusConfig,
    EventCallback,
    EventEnvelope,
    EventFilter,
    EventMetadata,
    EventSubscription,
    PlatformEventType,
)

__all__ = [
    "EventBus",
    "NATSTransport",
    "make_nats_transport",
    "DeliveryResult",
    "DeliveryStatus",
    "EventCallback",
    "EventBusConfig",
    "EventEnvelope",
    "EventFilter",
    "EventMetadata",
    "EventSubscription",
    "PlatformEventType",
]
