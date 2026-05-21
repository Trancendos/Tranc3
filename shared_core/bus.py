# shared_core/bus.py
# Event bus for nanoservice communication — the nervous system of Trancendos

import asyncio
import logging
from collections import defaultdict
from typing import Callable, Dict, List, Optional

from .models import EventMessage, VectorClock

logger = logging.getLogger(__name__)


class EventBus:
    """
    Lightweight async event bus for inter-service communication.
    Supports topic-based pub/sub, causal ordering via vector clocks,
    and replay for late subscribers.
    """

    def __init__(self, node_id: str = "tranc3-bus", replay_limit: int = 100):
        self.node_id = node_id
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._vector_clock = VectorClock()
        self._event_log: List[EventMessage] = []
        self._replay_limit = replay_limit
        self._running = False

    async def start(self) -> None:
        """Start the event bus"""
        self._running = True
        logger.info(f"EventBus started (node={self.node_id})")

    async def stop(self) -> None:
        """Stop the event bus"""
        self._running = False
        logger.info(f"EventBus stopped (node={self.node_id})")

    def subscribe(self, event_type: str, handler: Callable) -> None:
        """Subscribe to events of a specific type"""
        self._subscribers[event_type].append(handler)
        logger.debug(f"Subscribed to {event_type}: {handler.__name__}")

    def subscribe_all(self, handler: Callable) -> None:
        """Subscribe to all events (wildcard)"""
        self._subscribers["*"].append(handler)

    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        """Unsubscribe from events"""
        if event_type in self._subscribers:
            self._subscribers[event_type] = [
                h for h in self._subscribers[event_type] if h != handler
            ]

    async def publish(self, event: EventMessage) -> None:
        """Publish an event to all subscribers"""
        # Update vector clock
        self._vector_clock.increment(self.node_id)

        # Store for replay
        self._event_log.append(event)
        if len(self._event_log) > self._replay_limit:
            self._event_log = self._event_log[-self._replay_limit:]

        # Notify specific subscribers
        handlers = self._subscribers.get(event.event_type, []) + self._subscribers.get("*", [])

        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(
                    f"Event handler error for {event.event_type}: {e}",
                    extra={"handler": handler.__name__, "event": event.to_dict()},
                )

    async def replay(self, event_type: Optional[str] = None, handler: Optional[Callable] = None) -> List[EventMessage]:
        """Replay events for late subscribers. Optionally filter by type."""
        events = self._event_log
        if event_type:
            events = [e for e in events if e.event_type == event_type]

        if handler:
            for event in events:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(event)
                    else:
                        handler(event)
                except Exception as e:
                    logger.error(f"Replay handler error: {e}")

        return events

    def get_log(self, event_type: Optional[str] = None, limit: int = 50) -> List[Dict]:
        """Get recent events from the log"""
        events = self._event_log
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return [e.to_dict() for e in events[-limit:]]

    @property
    def vector_clock_state(self) -> Dict[str, int]:
        """Current vector clock state for debugging"""
        return self._vector_clock.to_dict()


# Singleton
bus = EventBus()
