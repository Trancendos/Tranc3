# src/fluidic/causal_bus.py
# Causal event bus — event ordering with vector clocks for distributed consistency

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Dict, List, Set

from shared_core.models import EventMessage, VectorClock
from shared_core.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


class CausalEventBus:
    """
    Event bus with causal ordering using vector clocks.
    Guarantees that events are delivered in causal order,
    even across distributed services.
    """

    def __init__(self, node_id: str = "tranc3-causal", replay_limit: int = 200):
        self.node_id = node_id
        self._vector_clock = VectorClock()
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._event_log: List[EventMessage] = []
        self._replay_limit = replay_limit
        self._pending: List[EventMessage] = []
        self._delivered: Set[str] = set()
        self._running = False

    async def start(self) -> None:
        self._running = True
        logger.info("CausalEventBus started (node=%s)", sanitize_for_log(self.node_id))

    async def stop(self) -> None:
        self._running = False
        logger.info("CausalEventBus stopped (node=%s)", sanitize_for_log(self.node_id))

    def subscribe(self, event_type: str, handler: Callable) -> None:
        self._subscribers[event_type].append(handler)

    def subscribe_all(self, handler: Callable) -> None:
        self._subscribers["*"].append(handler)

    async def publish(self, event: EventMessage) -> None:
        self._vector_clock.increment(self.node_id)
        event.metadata["vector_clock"] = self._vector_clock.to_dict()
        event.metadata["source_node"] = self.node_id

        self._event_log.append(event)
        if len(self._event_log) > self._replay_limit:
            self._event_log = self._event_log[-self._replay_limit :]

        await self._deliver(event)

    async def publish_remote(self, event: EventMessage, remote_clock: Dict[str, int]) -> None:
        remote_vc = VectorClock(clock=remote_clock)
        source_node = event.metadata.get("source_node", "unknown")

        if self._can_deliver(remote_vc, source_node):
            self._vector_clock.merge(remote_vc)
            self._vector_clock.increment(self.node_id)
            await self._deliver(event)
        else:
            self._pending.append(event)
            logger.debug(
                "Buffered remote event: %s (pending=%s)",
                sanitize_for_log(event.event_type),
                sanitize_for_log(len(self._pending)),
            )

        await self._try_deliver_pending()

    def _can_deliver(self, remote_vc: VectorClock, source_node: str) -> bool:
        for node, counter in remote_vc.clock.items():
            if node == source_node:
                if counter > self._vector_clock.clock.get(node, 0) + 1:
                    return False
            else:
                if counter > self._vector_clock.clock.get(node, 0):
                    return False
        return True

    async def _try_deliver_pending(self) -> None:
        still_pending = []
        for event in self._pending:
            remote_vc_data = event.metadata.get("vector_clock", {})
            source_node = event.metadata.get("source_node", "unknown")
            remote_vc = VectorClock(clock=remote_vc_data)

            if self._can_deliver(remote_vc, source_node):
                self._vector_clock.merge(remote_vc)
                self._vector_clock.increment(self.node_id)
                await self._deliver(event)
            else:
                still_pending.append(event)
        self._pending = still_pending

    async def _deliver(self, event: EventMessage) -> None:
        handlers = self._subscribers.get(event.event_type, []) + self._subscribers.get("*", [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(
                    "Causal delivery error for %s: %s",
                    sanitize_for_log(event.event_type),
                    sanitize_for_log(e),
                )

    @property
    def clock_state(self) -> Dict[str, int]:
        return self._vector_clock.to_dict()

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def stats(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "vector_clock": self.clock_state,
            "subscribers": {k: len(v) for k, v in self._subscribers.items()},
            "pending_events": self.pending_count,
            "logged_events": len(self._event_log),
        }


causal_bus = CausalEventBus()
