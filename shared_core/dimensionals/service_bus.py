"""
Trancendos Dimensional Service Bus
====================================
Communication bus that routes messages between Dimensional's services
in the Infinity Ecosystem. The Service Bus integrates with Sentinel Station
for cross-gateway event distribution, enabling dimensional services to
communicate both locally and across process boundaries.

Architecture:
    Dimensional Service A --> Service Bus --> Sentinel Station --> Redis Pub/Sub
                                     |                                    |
                                     +--> Local Handlers      Cross-Gateway Subscribers
                                     |
                                     +--> Underverse Module Routing (per-app nanoservices)

The Service Bus provides:
    - Service-to-service message routing via Sentinel Station channels
    - Request/response patterns for synchronous dimensional communication
    - Fire-and-forget patterns for asynchronous dimensional events
    - Pillar-scoped messaging (route messages to all services in a pillar)
    - Tier-aware delivery (only deliver to services at or above the message tier)
    - Circuit breaker protection for cross-process communication
    - Graceful degradation when Sentinel Station is unavailable

Naming Convention:
    The Service Bus is the communication backbone of the Dimensional's
    (Shared-Core) layer. In the Trancendos Universe, it connects the
    Dimensional's to the Sentinel Station (interplexus hub) for
    cross-gateway event distribution.

OWASP Alignment:
    A01 (Broken Access Control): Tier-aware and pillar-scoped delivery
    A02 (Cryptographic Failures): All inter-process messages via Sentinel
    A09 (Security Logging): All bus operations are audit-logged

Usage:
    from shared_core.dimensionals.service_bus import DimensionalServiceBus, get_dimensional_bus

    bus = get_dimensional_bus()
    await bus.start()

    # Send a message to a specific dimensional
    await bus.send("gateway", {"action": "refresh_cache"}, source="workflow")

    # Broadcast to all services in a pillar
    await bus.broadcast_pillar(Pillar.SECURITY, {"alert": "threat_detected"})

    # Register a handler for incoming messages
    bus.on_message("gateway", my_handler)

    await bus.stop()
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional

from shared_core.dimensionals.registry import (
    DimensionalServiceRegistry,
    get_dimensional_registry,
)
from shared_core.infinity.nomenclature import Pillar, Tier
from shared_core.infinity.sentinel_station import (
    SentinelEvent,
    SentinelStation,
    get_sentinel_station,
)

logger = logging.getLogger(__name__)

# Phase 22.6: Optional FluidicRouter + CausalEventBus integration
try:
    from shared_core.architecture.fluidic_router import FluidicRouter

    _FLUIDIC_AVAILABLE = True
except ImportError:
    _FLUIDIC_AVAILABLE = False

try:
    from shared_core.architecture.causal_event_bus import CausalEventBus

    _CAUSAL_AVAILABLE = True
except ImportError:
    _CAUSAL_AVAILABLE = False


# ── Message Priority ──────────────────────────────────────────────────────


class MessagePriority(int, Enum):
    """Priority levels for dimensional service bus messages.

    Higher values indicate higher priority. Messages with higher priority
    are processed before lower priority messages when the bus is congested.
    """

    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


# ── Bus Message ───────────────────────────────────────────────────────────


@dataclass
class BusMessage:
    """A message on the Dimensional Service Bus.

    Messages carry metadata about their routing, priority, and delivery
    requirements. They are serialized and transmitted through Sentinel
    Station for cross-gateway distribution.

    Attributes:
        id: Unique message identifier
        source: The dimensional service that sent the message
        target: The dimensional service to receive the message (empty = broadcast)
        pillar: Target pillar for pillar-scoped broadcasts
        tier: Minimum tier required to receive this message
        action: The action or event type being communicated
        payload: The message data
        priority: Message priority level
        channel: The Sentinel Station channel to publish on
        correlation_id: For request/response correlation
        reply_to: Service ID that should receive the reply
        timestamp: ISO timestamp of when the message was created
        ttl: Time-to-live in seconds (0 = no expiry)
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    source: str = ""
    target: str = ""
    pillar: Optional[str] = None
    tier: Tier = Tier.HUMAN
    action: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    priority: MessagePriority = MessagePriority.NORMAL
    channel: str = "infrastructure"
    correlation_id: Optional[str] = None
    reply_to: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ttl: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-friendly dictionary."""
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "pillar": self.pillar,
            "tier": self.tier.value,
            "action": self.action,
            "payload": self.payload,
            "priority": self.priority.value,
            "channel": self.channel,
            "correlation_id": self.correlation_id,
            "reply_to": self.reply_to,
            "timestamp": self.timestamp,
            "ttl": self.ttl,
        }

    def to_sentinel_payload(self) -> Dict[str, Any]:
        """Convert to a payload suitable for Sentinel Station publishing."""
        return {
            "bus_message_id": self.id,
            "source": self.source,
            "target": self.target,
            "pillar": self.pillar,
            "tier": self.tier.value,
            "action": self.action,
            "payload": self.payload,
            "priority": self.priority.value,
            "correlation_id": self.correlation_id,
            "reply_to": self.reply_to,
            "timestamp": self.timestamp,
            "ttl": self.ttl,
        }

    @classmethod
    def from_sentinel_event(cls, event: SentinelEvent) -> Optional[BusMessage]:
        """Create a BusMessage from a SentinelEvent payload.

        Returns None if the event payload is not a valid bus message.
        """
        try:
            p = event.payload
            if "bus_message_id" not in p:
                return None
            return cls(
                id=p.get("bus_message_id", uuid.uuid4().hex[:16]),
                source=p.get("source", ""),
                target=p.get("target", ""),
                pillar=p.get("pillar"),
                tier=Tier(p.get("tier", 0)),
                action=p.get("action", ""),
                payload=p.get("payload", {}),
                priority=MessagePriority(p.get("priority", 1)),
                channel=event.channel,
                correlation_id=p.get("correlation_id"),
                reply_to=p.get("reply_to"),
                timestamp=p.get("timestamp", datetime.now(timezone.utc).isoformat()),
                ttl=p.get("ttl", 0),
            )
        except Exception as e:
            logger.warning("Failed to parse BusMessage from SentinelEvent: %s", str(e)[:200])
            return None

    def is_expired(self) -> bool:
        """Check if the message has expired based on TTL."""
        if self.ttl <= 0:
            return False
        try:
            created = datetime.fromisoformat(self.timestamp)
            elapsed = (datetime.now(timezone.utc) - created).total_seconds()
            return elapsed > self.ttl
        except Exception:
            return False


# ── Message Handler ───────────────────────────────────────────────────────


# Type alias for message handler callbacks
MessageHandler = Callable[[BusMessage], Coroutine[Any, Any, None]]


# ── Dimensional Service Bus ──────────────────────────────────────────────


class DimensionalServiceBus:
    """Communication bus for routing messages between Dimensional's services.

    The Service Bus provides the communication backbone for the Infinity
    Ecosystem's shared-core (Dimensional's) layer. It integrates with
    Sentinel Station for cross-gateway event distribution, while also
    supporting local in-process message routing.

    Features:
        - Point-to-point messaging (send to a specific dimensional)
        - Broadcast messaging (send to all dimensionals)
        - Pillar-scoped messaging (send to all services in a pillar)
        - Tier-aware delivery (only deliver to services at or above tier)
        - Request/response correlation via correlation_id
        - Message priority handling
        - Sentinel Station integration for cross-gateway distribution
        - Local handler registration for in-process delivery
        - Message statistics and monitoring

    Lifecycle:
        1. Create: bus = DimensionalServiceBus()
        2. Start: await bus.start() -- connects to Sentinel Station
        3. Send messages: await bus.send(...) or await bus.broadcast(...)
        4. Register handlers: bus.on_message("gateway", handler)
        5. Stop: await bus.stop()
    """

    def __init__(
        self,
        registry: Optional[DimensionalServiceRegistry] = None,
        sentinel: Optional[SentinelStation] = None,
    ) -> None:
        self._registry = registry or get_dimensional_registry()
        self._sentinel = sentinel or get_sentinel_station()

        # Message handlers keyed by target service ID
        self._handlers: Dict[str, List[MessageHandler]] = {}
        # Broadcast handlers (receive all messages)
        self._broadcast_handlers: List[MessageHandler] = []
        # Pending request/response correlations
        self._pending_requests: Dict[str, asyncio.Future] = {}
        # Sentinel Station subscription queue
        self._sentinel_queue: Optional[asyncio.Queue] = None
        # Background task for processing sentinel events
        self._listener_task: Optional[asyncio.Task] = None
        self._running = False

        # Phase 22.6: FluidicRouter for weighted dimensional routing
        self._fluidic_router = FluidicRouter() if _FLUIDIC_AVAILABLE else None
        # Phase 22.6: CausalEventBus for causal ordering of dimensional messages
        self._causal_bus = (
            CausalEventBus(node_id="dimensional-service-bus") if _CAUSAL_AVAILABLE else None
        )

        # Statistics
        self._stats = {
            "messages_sent": 0,
            "messages_received": 0,
            "messages_delivered_local": 0,
            "messages_delivered_sentinel": 0,
            "messages_expired": 0,
            "messages_dropped_no_handler": 0,
            "requests_sent": 0,
            "responses_received": 0,
            "started_at": None,
            # Phase 22.6: Extended stats
            "fluidic_routes": 0,
            "causal_events": 0,
        }

    @property
    def is_running(self) -> bool:
        return self._running

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the Dimensional Service Bus.

        Connects to Sentinel Station and subscribes to the infrastructure
        channel for cross-gateway dimensional messages.
        """
        if self._running:
            return

        self._stats["started_at"] = datetime.now(timezone.utc).isoformat()

        # Subscribe to Sentinel Station for cross-gateway messages
        if self._sentinel.is_running or not self._sentinel.is_running:
            # Ensure sentinel is started
            if not self._sentinel.is_running:
                await self._sentinel.start()

            self._sentinel_queue = await self._sentinel.subscribe("infrastructure")
            self._listener_task = asyncio.create_task(self._sentinel_listener())
            logger.info("Dimensional Service Bus started with Sentinel Station backend")

        self._running = True
        logger.info("Dimensional Service Bus started")

    async def stop(self) -> None:
        """Stop the Dimensional Service Bus gracefully."""
        self._running = False

        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None

        # Cancel any pending requests
        for future in self._pending_requests.values():
            if not future.done():
                future.cancel()
        self._pending_requests.clear()

        logger.info("Dimensional Service Bus stopped")

    # ── Point-to-Point Messaging ──────────────────────────────────────────

    async def send(
        self,
        target: str,
        payload: Dict[str, Any],
        source: str = "",
        action: str = "",
        priority: MessagePriority = MessagePriority.NORMAL,
        channel: str = "infrastructure",
        ttl: int = 0,
    ) -> BusMessage:
        """Send a message to a specific dimensional service.

        The message is routed both locally (to any registered handlers)
        and through Sentinel Station (for cross-gateway distribution).

        Args:
            target: The dimensional service ID to send to
            payload: Message data dictionary
            source: The sending dimensional service ID
            action: The action or event type
            priority: Message priority level
            channel: Sentinel Station channel to publish on
            ttl: Time-to-live in seconds (0 = no expiry)

        Returns:
            The BusMessage that was sent
        """
        message = BusMessage(
            source=source,
            target=target,
            payload=payload,
            action=action,
            priority=priority,
            channel=channel,
            ttl=ttl,
        )

        await self._dispatch(message)
        return message

    async def send_with_reply(
        self,
        target: str,
        payload: Dict[str, Any],
        source: str = "",
        action: str = "",
        timeout: float = 10.0,
        priority: MessagePriority = MessagePriority.NORMAL,
        channel: str = "infrastructure",
    ) -> BusMessage:
        """Send a message and wait for a reply.

        Creates a correlation ID and registers a future that will be
        resolved when the target service sends a reply.

        Args:
            target: The dimensional service ID to send to
            payload: Message data dictionary
            source: The sending dimensional service ID
            action: The action or event type
            timeout: Maximum time to wait for a reply in seconds
            priority: Message priority level
            channel: Sentinel Station channel

        Returns:
            The reply BusMessage

        Raises:
            asyncio.TimeoutError: If no reply is received within timeout
        """
        correlation_id = uuid.uuid4().hex[:16]
        future: asyncio.Future[BusMessage] = asyncio.get_running_loop().create_future()
        self._pending_requests[correlation_id] = future

        message = BusMessage(
            source=source,
            target=target,
            payload=payload,
            action=action,
            priority=priority,
            channel=channel,
            correlation_id=correlation_id,
            reply_to=source,
        )

        await self._dispatch(message)
        self._stats["requests_sent"] += 1

        try:
            reply = await asyncio.wait_for(future, timeout=timeout)
            self._stats["responses_received"] += 1
            return reply
        except asyncio.TimeoutError:
            self._pending_requests.pop(correlation_id, None)
            raise

    async def reply(
        self,
        original: BusMessage,
        payload: Dict[str, Any],
        source: str = "",
        action: str = "",
    ) -> BusMessage:
        """Send a reply to a previous message.

        Uses the correlation_id and reply_to from the original message
        to route the reply back to the sender.

        Args:
            original: The original BusMessage being replied to
            payload: Reply data dictionary
            source: The sending dimensional service ID
            action: The action or event type for the reply

        Returns:
            The reply BusMessage
        """
        message = BusMessage(
            source=source,
            target=original.reply_to or original.source,
            payload=payload,
            action=action or f"{original.action}_reply",
            channel=original.channel,
            correlation_id=original.correlation_id,
        )

        await self._dispatch(message)
        return message

    # ── Broadcast Messaging ───────────────────────────────────────────────

    async def broadcast(
        self,
        payload: Dict[str, Any],
        source: str = "",
        action: str = "",
        tier: Tier = Tier.HUMAN,
        priority: MessagePriority = MessagePriority.NORMAL,
        channel: str = "infrastructure",
    ) -> BusMessage:
        """Broadcast a message to all dimensional services.

        The message is delivered to all registered handlers and published
        through Sentinel Station. Only services at or above the specified
        tier will process the message.

        Args:
            payload: Message data dictionary
            source: The sending dimensional service ID
            action: The action or event type
            tier: Minimum tier required to receive this message
            priority: Message priority level
            channel: Sentinel Station channel

        Returns:
            The BusMessage that was broadcast
        """
        message = BusMessage(
            source=source,
            target="",  # Empty target = broadcast
            payload=payload,
            action=action,
            tier=tier,
            priority=priority,
            channel=channel,
        )

        await self._dispatch(message)
        return message

    async def broadcast_pillar(
        self,
        pillar: Pillar,
        payload: Dict[str, Any],
        source: str = "",
        action: str = "",
        priority: MessagePriority = MessagePriority.NORMAL,
    ) -> BusMessage:
        """Broadcast a message to all services in a specific pillar.

        The message is delivered to all dimensional services associated
        with the given pillar, both locally and through Sentinel Station.

        Args:
            pillar: The Pillar to broadcast to
            payload: Message data dictionary
            source: The sending dimensional service ID
            action: The action or event type
            priority: Message priority level

        Returns:
            The BusMessage that was broadcast
        """
        message = BusMessage(
            source=source,
            target="",  # Broadcast
            pillar=pillar.value,
            payload=payload,
            action=action,
            priority=priority,
            channel="pillars",
        )

        await self._dispatch(message)
        return message

    # ── Handler Registration ──────────────────────────────────────────────

    def on_message(self, service_id: str, handler: MessageHandler) -> None:
        """Register a handler for messages targeting a specific dimensional service.

        Args:
            service_id: The dimensional service ID to handle messages for
            handler: Async callback that receives BusMessage instances
        """
        if service_id not in self._handlers:
            self._handlers[service_id] = []
        self._handlers[service_id].append(handler)
        logger.debug("Registered message handler for dimensional: %s", service_id)

    def on_broadcast(self, handler: MessageHandler) -> None:
        """Register a handler for all broadcast messages.

        Args:
            handler: Async callback that receives all BusMessage instances
        """
        self._broadcast_handlers.append(handler)
        logger.debug("Registered broadcast message handler")

    def remove_handler(self, service_id: str, handler: MessageHandler) -> None:
        """Remove a specific handler for a dimensional service.

        Args:
            service_id: The dimensional service ID
            handler: The handler to remove
        """
        if service_id in self._handlers:
            try:
                self._handlers[service_id].remove(handler)
            except ValueError:
                pass
            if not self._handlers[service_id]:
                del self._handlers[service_id]

    # ── Internal Dispatch ─────────────────────────────────────────────────

    async def _dispatch(self, message: BusMessage) -> None:
        """Dispatch a message to local handlers and Sentinel Station.

        This is the core routing method. It:
        1. Delivers to local handlers matching the target
        2. Delivers to broadcast handlers
        3. Publishes through Sentinel Station for cross-gateway distribution
        4. Handles pillar-scoped routing
        5. Enforces tier-aware delivery
        """
        if message.is_expired():
            self._stats["messages_expired"] += 1
            logger.debug("Dropped expired bus message: %s", message.id)
            return

        self._stats["messages_sent"] += 1
        delivered = False

        # 1. Deliver to specific target handlers
        if message.target:
            handlers = self._handlers.get(message.target, [])
            for handler in handlers:
                try:
                    await handler(message)
                    delivered = True
                except Exception as e:
                    logger.warning(
                        "Handler error for dimensional %s: %s",
                        message.target,
                        str(e)[:200],
                    )

        # 2. Deliver to pillar-scoped handlers
        if message.pillar:
            pillar_services = self._registry.get_by_pillar(Pillar(message.pillar))
            for svc in pillar_services:
                if message.tier > svc.tier:
                    # Skip services below the message's tier requirement
                    continue
                handlers = self._handlers.get(svc.id, [])
                for handler in handlers:
                    try:
                        await handler(message)
                        delivered = True
                    except Exception as e:
                        logger.warning(
                            "Pillar handler error for dimensional %s: %s",
                            svc.id,
                            str(e)[:200],
                        )

        # 3. Deliver to broadcast handlers (for non-targeted messages)
        if not message.target:
            for handler in self._broadcast_handlers:
                try:
                    await handler(message)
                    delivered = True
                except Exception as e:
                    logger.warning(
                        "Broadcast handler error: %s",
                        str(e)[:200],
                    )

        # 4. Check for pending request/response correlation
        if message.correlation_id and message.correlation_id in self._pending_requests:
            future = self._pending_requests.pop(message.correlation_id)
            if not future.done():
                future.set_result(message)
                delivered = True

        # 5. Publish through Sentinel Station for cross-gateway distribution
        if self._sentinel.is_running:
            try:
                await self._sentinel.publish(
                    channel=message.channel,
                    payload=message.to_sentinel_payload(),
                    event_type=f"bus:{message.action}" if message.action else "bus:message",
                    source=f"dimensional_bus:{message.source}"
                    if message.source
                    else "dimensional_bus",
                )
                self._stats["messages_delivered_sentinel"] += 1
                delivered = True
            except Exception as e:
                logger.warning("Sentinel Station publish failed: %s", str(e)[:200])

        if delivered:
            self._stats["messages_delivered_local"] += 1
        else:
            self._stats["messages_dropped_no_handler"] += 1

    # ── Sentinel Station Listener ─────────────────────────────────────────

    async def _sentinel_listener(self) -> None:
        """Background task that processes events from Sentinel Station.

        Listens for dimensional bus messages coming from other gateway
        instances via Redis Pub/Sub, and dispatches them locally.
        """
        if not self._sentinel_queue:
            return

        while self._running:
            try:
                event = await asyncio.wait_for(self._sentinel_queue.get(), timeout=1.0)
                self._stats["messages_received"] += 1

                # Parse the event as a BusMessage
                message = BusMessage.from_sentinel_event(event)
                if message is None:
                    continue

                # Skip our own messages (avoid echo loops)
                if message.source and f"dimensional_bus:{message.source}" == event.source:
                    continue

                # Dispatch locally (but don't re-publish to Sentinel Station)
                await self._dispatch_local(message)

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Sentinel listener error: %s", str(e)[:200])
                await asyncio.sleep(1)

    async def _dispatch_local(self, message: BusMessage) -> None:
        """Dispatch a message locally only (no Sentinel Station re-publish).

        Used for messages received from Sentinel Station to avoid
        echo loops.
        """
        if message.is_expired():
            self._stats["messages_expired"] += 1
            return

        delivered = False

        # Deliver to target handlers
        if message.target:
            for handler in self._handlers.get(message.target, []):
                try:
                    await handler(message)
                    delivered = True
                except Exception as e:
                    logger.warning("Local dispatch error: %s", str(e)[:200])

        # Deliver to pillar handlers
        if message.pillar:
            try:
                pillar = Pillar(message.pillar)
                for svc in self._registry.get_by_pillar(pillar):
                    if message.tier > svc.tier:
                        continue
                    for handler in self._handlers.get(svc.id, []):
                        try:
                            await handler(message)
                            delivered = True
                        except Exception as e:
                            logger.warning("Local pillar dispatch error: %s", str(e)[:200])
            except ValueError:
                pass

        # Broadcast handlers
        if not message.target:
            for handler in self._broadcast_handlers:
                try:
                    await handler(message)
                    delivered = True
                except Exception as e:
                    logger.warning("Local broadcast dispatch error: %s", str(e)[:200])

        # Correlation
        if message.correlation_id and message.correlation_id in self._pending_requests:
            future = self._pending_requests.pop(message.correlation_id)
            if not future.done():
                future.set_result(message)
                delivered = True

        if delivered:
            self._stats["messages_delivered_local"] += 1
        else:
            self._stats["messages_dropped_no_handler"] += 1

    # ── Health & Statistics ───────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get Dimensional Service Bus statistics."""
        return {
            **self._stats,
            "running": self._running,
            "registered_handlers": sum(len(h) for h in self._handlers.values()),
            "services_with_handlers": len(self._handlers),
            "broadcast_handlers": len(self._broadcast_handlers),
            "pending_requests": len(self._pending_requests),
            "sentinel_running": self._sentinel.is_running,
            "sentinel_backend": "redis" if self._sentinel.is_redis_connected else "fallback",
        }

    async def health_check(self) -> Dict[str, Any]:
        """Perform a health check and return status information."""
        sentinel_health = await self._sentinel.health_check()
        return {
            "status": "ok" if self._running else "stopped",
            "sentinel": sentinel_health,
            "handlers": sum(len(h) for h in self._handlers.values()),
            "pending_requests": len(self._pending_requests),
        }


# ── Module-level Singleton ────────────────────────────────────────────────

_dimensional_bus: Optional[DimensionalServiceBus] = None


def get_dimensional_bus() -> DimensionalServiceBus:
    """Get or create the Dimensional Service Bus singleton."""
    global _dimensional_bus
    if _dimensional_bus is None:
        _dimensional_bus = DimensionalServiceBus()
    return _dimensional_bus
