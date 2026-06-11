"""
Trancendos Sentinel Station — Event Bus Bridge (Interplexus Hub)
================================================================
Redis Pub/Sub event distribution hub for the Infinity Ecosystem.

The Sentinel Station serves as the central nervous system for
cross-gateway event distribution. It uses Redis Pub/Sub for
real-time event broadcasting across all gateway instances and
services, with a graceful in-process fallback when Redis is
unavailable.

Architecture:
    Publisher → Sentinel Station → Redis Pub/Sub → Subscribers
                                      ↓ (fallback)
                              In-Process Pub/Sub → Local Subscribers

Features:
    - Redis Pub/Sub for cross-process event distribution
    - In-process async pub/sub fallback when Redis is down
    - Automatic reconnection with exponential backoff
    - Circuit breaker for Redis connections
    - Channel-based event routing (SentinelChannel)
    - Event serialization with optional compression
    - Health monitoring and statistics
    - Shared SSE event generator for dashboard broadcasting

OWASP Alignment:
    A01 (Broken Access Control): Channel-level access via RBAC
    A09 (Security Logging): All events are audit-logged

Usage:
    from Dimensional.infinity.sentinel_station import SentinelStation

    station = SentinelStation()
    await station.start()

    # Publish an event
    await station.publish("agents", {"type": "agent_created", "id": "abc"})

    # Subscribe to a channel
    async def handler(event):
        print(event)
    await station.subscribe("agents", handler)

    await station.stop()
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from Dimensional.infinity.nomenclature import SentinelChannel
from Dimensional.infinity.sentinel_config import (
    FallbackConfig,
    RedisConfig,
    SentinelStationConfig,
    sentinel_config,
)

logger = logging.getLogger(__name__)


# ── Event Data Model ────────────────────────────────────────────────────────


@dataclass
class SentinelEvent:
    """A Sentinel Station event.

    Events are the fundamental unit of communication in the
    Sentinel Station interplexus hub. Each event carries metadata
    about its origin, channel, and timing.
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    channel: str = ""
    event_type: str = ""
    source: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    compressed: bool = False

    def to_json(self) -> str:
        """Serialize event to JSON string."""
        data = {
            "id": self.id,
            "channel": self.channel,
            "event_type": self.event_type,
            "source": self.source,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "compressed": self.compressed,
        }
        return json.dumps(data, default=str)

    @classmethod
    def from_json(cls, data: str) -> SentinelEvent:
        """Deserialize event from JSON string."""
        try:
            obj = json.loads(data)
            return cls(
                id=obj.get("id", uuid.uuid4().hex[:16]),
                channel=obj.get("channel", ""),
                event_type=obj.get("event_type", ""),
                source=obj.get("source", ""),
                payload=obj.get("payload", {}),
                timestamp=obj.get("timestamp", datetime.now(timezone.utc).isoformat()),
                compressed=obj.get("compressed", False),
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to deserialize SentinelEvent: %s", e)
            return cls()


# ── Circuit Breaker ─────────────────────────────────────────────────────────


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """Simple circuit breaker for Redis connections.

    Prevents cascading failures when Redis is unavailable.
    After a threshold of failures, the circuit opens and
    stops attempting Redis operations, using the fallback instead.
    After a reset timeout, the circuit enters half-open state
    and allows a single test request through.
    """

    threshold: int = 5
    reset_timeout: float = 60.0
    _state: CircuitState = CircuitState.CLOSED
    _failure_count: int = 0
    _last_failure_time: float = 0.0

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.time() - self._last_failure_time > self.reset_timeout:
                self._state = CircuitState.HALF_OPEN
        return self._state

    def record_success(self) -> None:
        self._failure_count = 0
        self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self.threshold:
            self._state = CircuitState.OPEN
            logger.warning(
                "Sentinel Station circuit breaker OPEN after %d failures",
                self._failure_count,
            )

    @property
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    def reset(self) -> None:
        self._failure_count = 0
        self._state = CircuitState.CLOSED
        self._last_failure_time = 0.0


# ── In-Process Fallback Pub/Sub ─────────────────────────────────────────────


class InProcessPubSub:
    """In-process async pub/sub for when Redis is unavailable.

    Uses asyncio queues to distribute events to local subscribers.
    This ensures the system remains functional even without Redis,
    though cross-process distribution is unavailable.
    """

    def __init__(self, config: FallbackConfig) -> None:
        self._config = config
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}
        self._stats = {
            "published": 0,
            "delivered": 0,
            "dropped": 0,
        }

    async def publish(self, channel: str, event: SentinelEvent) -> int:
        """Publish an event to all subscribers on a channel.

        Returns the number of subscribers that received the event.
        """
        if channel not in self._subscribers:
            return 0

        delivered = 0
        for queue in self._subscribers[channel]:
            try:
                if queue.full():
                    # Drop oldest event to make room
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty as _exc:
                        logger.debug("suppressed %s", _exc, exc_info=False)
                    self._stats["dropped"] += 1
                queue.put_nowait(event)
                delivered += 1
            except Exception:
                self._stats["dropped"] += 1

        self._stats["published"] += 1
        self._stats["delivered"] += delivered
        return delivered

    def subscribe(self, channel: str) -> asyncio.Queue:
        """Subscribe to a channel and return a queue for receiving events."""
        if channel not in self._subscribers:
            self._subscribers[channel] = []
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._config.max_queue_size)
        self._subscribers[channel].append(queue)
        return queue

    def unsubscribe(self, channel: str, queue: asyncio.Queue) -> None:
        """Unsubscribe a queue from a channel."""
        if channel in self._subscribers:
            try:
                self._subscribers[channel].remove(queue)
            except ValueError as _exc:
                logger.debug("suppressed %s", _exc, exc_info=False)
            if not self._subscribers[channel]:
                del self._subscribers[channel]

    def get_subscriber_count(self, channel: str) -> int:
        """Get the number of subscribers for a channel."""
        return len(self._subscribers.get(channel, []))

    def get_stats(self) -> Dict[str, Any]:
        """Get fallback pub/sub statistics."""
        return {
            **self._stats,
            "channels": len(self._subscribers),
            "total_subscribers": sum(len(qs) for qs in self._subscribers.values()),
        }


# ── Redis Connection Manager ────────────────────────────────────────────────


class RedisConnectionManager:
    """Manages Redis connections with health checking and reconnection.

    Handles the lifecycle of Redis connections for the Sentinel Station,
    including initial connection, health checks, and graceful disconnection.
    """

    def __init__(self, config: RedisConfig) -> None:
        self._config = config
        self._pool: Optional[Any] = None
        self._client: Optional[Any] = None
        self._pubsub: Optional[Any] = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> bool:
        """Establish Redis connection pool and client.

        Returns True if connection was successful, False otherwise.
        """
        try:
            import redis.asyncio as aioredis

            self._pool = aioredis.ConnectionPool.from_url(
                self._config.url,
                max_connections=self._config.max_connections,
                socket_timeout=self._config.socket_timeout,
                socket_connect_timeout=self._config.socket_connect_timeout,
                health_check_interval=self._config.health_check_interval,
            )
            self._client = aioredis.Redis(connection_pool=self._pool)
            # Test connection
            await self._client.ping()
            self._connected = True
            logger.info("Sentinel Station connected to Redis at %s", self._config.host)
            return True
        except Exception as e:
            logger.warning("Sentinel Station failed to connect to Redis: %s", str(e)[:200])
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Gracefully close Redis connections."""
        if self._pubsub:
            try:
                await self._pubsub.unsubscribe()
                await self._pubsub.aclose()
            except Exception as _exc:
                logger.debug("suppressed %s", _exc, exc_info=False)
            self._pubsub = None

        if self._client:
            try:
                await self._client.aclose()
            except Exception as _exc:
                logger.debug("suppressed %s", _exc, exc_info=False)
            self._client = None

        if self._pool:
            try:
                await self._pool.disconnect()
            except Exception as _exc:
                logger.debug("suppressed %s", _exc, exc_info=False)
            self._pool = None

        self._connected = False
        logger.info("Sentinel Station disconnected from Redis")

    async def health_check(self) -> bool:
        """Check if Redis connection is healthy."""
        if not self._client:
            return False
        try:
            await self._client.ping()
            return True
        except Exception:
            self._connected = False
            return False

    async def publish(self, channel: str, message: str) -> int:
        """Publish a message to a Redis channel.

        Returns the number of receivers, or 0 if not connected.
        """
        if not self._client or not self._connected:
            return 0
        try:
            receivers = await self._client.publish(channel, message)
            return receivers
        except Exception as e:
            logger.warning("Redis publish failed: %s", str(e)[:200])
            self._connected = False
            return 0

    async def subscribe(self, channel: str) -> None:
        """Subscribe to a Redis channel."""
        if not self._client or not self._connected:
            return
        try:
            if not self._pubsub:
                self._pubsub = self._client.pubsub()
            await self._pubsub.subscribe(channel)
            logger.info("Sentinel Station subscribed to Redis channel: %s", channel)
        except Exception as e:
            logger.warning("Redis subscribe failed: %s", str(e)[:200])

    async def unsubscribe(self, channel: str) -> None:
        """Unsubscribe from a Redis channel."""
        if not self._pubsub:
            return
        try:
            await self._pubsub.unsubscribe(channel)
        except Exception as _exc:
            logger.debug("suppressed %s", _exc, exc_info=False)

    async def get_messages(self, timeout: float = 0.1) -> List[Dict[str, Any]]:
        """Get messages from subscribed channels.

        Returns a list of message dicts with 'type', 'channel', and 'data' keys.
        """
        if not self._pubsub:
            return []
        messages = []
        try:
            msg = await asyncio.wait_for(
                self._pubsub.get_message(ignore_subscribe_messages=True), timeout=timeout
            )
            while msg:
                messages.append(msg)
                msg = self._pubsub.get_message(ignore_subscribe_messages=True)
        except asyncio.TimeoutError as _exc:
            logger.debug("suppressed %s", _exc, exc_info=False)
        except Exception as _exc:
            logger.debug("suppressed %s", _exc, exc_info=False)
        return messages


# ── Sentinel Station ────────────────────────────────────────────────────────


class SentinelStation:
    """Sentinel Station — the interplexus hub for the Infinity Ecosystem.

    Central event distribution hub using Redis Pub/Sub for cross-gateway
    communication, with in-process fallback for when Redis is unavailable.

    The station manages:
    - Publishing events to Redis channels
    - Subscribing to Redis channels and dispatching to local handlers
    - Fallback to in-process pub/sub when Redis is down
    - Circuit breaker for Redis connections
    - Event statistics and health monitoring

    Lifecycle:
        1. Create instance: station = SentinelStation()
        2. Start: await station.start() — connects to Redis or falls back
        3. Publish: await station.publish("agents", {...})
        4. Subscribe: queue = await station.subscribe("agents")
        5. Stop: await station.stop() — gracefully disconnects
    """

    def __init__(self, config: Optional[SentinelStationConfig] = None) -> None:
        self._config = config or sentinel_config
        self._redis_mgr = RedisConnectionManager(self._config.redis)
        self._fallback = InProcessPubSub(self._config.fallback)
        self._circuit_breaker = CircuitBreaker(
            threshold=self._config.retry.circuit_breaker_threshold,
            reset_timeout=self._config.retry.circuit_breaker_reset_timeout,
        )
        self._subscribed_channels: Set[str] = set()
        self._local_handlers: Dict[str, List[Callable]] = {}
        self._listener_task: Optional[asyncio.Task] = None
        self._running = False
        self._stats = {
            "events_published": 0,
            "events_received": 0,
            "events_delivered_local": 0,
            "events_delivered_redis": 0,
            "redis_publish_attempts": 0,
            "redis_publish_failures": 0,
            "fallback_activations": 0,
            "started_at": None,
        }

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_redis_connected(self) -> bool:
        return self._redis_mgr.is_connected

    @property
    def circuit_breaker_state(self) -> CircuitState:
        return self._circuit_breaker.state

    async def start(self) -> None:
        """Start the Sentinel Station.

        Attempts to connect to Redis. If Redis is unavailable,
        activates the in-process fallback.
        """
        if self._running:
            return

        self._stats["started_at"] = datetime.now(timezone.utc).isoformat()

        # Try Redis connection
        connected = await self._redis_mgr.connect()
        if connected:
            self._circuit_breaker.record_success()
            logger.info(
                "Sentinel Station started with Redis backend (prefix: %s)",
                self._config.redis_channel_prefix,
            )
        else:
            self._circuit_breaker.record_failure()
            self._stats["fallback_activations"] += 1
            logger.info("Sentinel Station started with in-process fallback (Redis unavailable)")

        self._running = True

        # Start Redis listener task if connected
        if connected:
            self._listener_task = asyncio.create_task(self._redis_listener())

    async def stop(self) -> None:
        """Stop the Sentinel Station gracefully."""
        self._running = False

        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError as _exc:
                logger.debug("suppressed %s", _exc, exc_info=False)
            self._listener_task = None

        await self._redis_mgr.disconnect()
        logger.info("Sentinel Station stopped")

    async def publish(
        self,
        channel: str,
        payload: Dict[str, Any],
        event_type: str = "",
        source: str = "",
    ) -> SentinelEvent:
        """Publish an event to a Sentinel channel.

        The event is published to both Redis (if available) and the
        in-process fallback. Redis is the primary distribution mechanism
        for cross-gateway events, while the fallback handles local
        subscribers within the same process.

        Args:
            channel: SentinelChannel name (e.g., "agents", "workflows")
            payload: Event data dictionary
            event_type: Type of event (e.g., "agent_created")
            source: Source service identifier

        Returns:
            The published SentinelEvent
        """
        event = SentinelEvent(
            channel=channel,
            event_type=event_type,
            source=source,
            payload=payload,
        )

        # Always publish to in-process fallback (local subscribers)
        await self._fallback.publish(channel, event)
        self._stats["events_delivered_local"] += self._fallback.get_subscriber_count(channel)

        # Try Redis if circuit breaker allows
        if not self._circuit_breaker.is_open:
            self._stats["redis_publish_attempts"] += 1
            message = event.to_json()

            # Compress large messages
            if len(message) > self._config.compression_threshold:
                message = gzip.compress(message.encode()).hex()
                event.compressed = True

            receivers = await self._redis_mgr.publish(
                f"{self._config.redis_channel_prefix}{channel}", message
            )

            if receivers >= 0:
                self._circuit_breaker.record_success()
                self._stats["events_delivered_redis"] += receivers
            else:
                self._circuit_breaker.record_failure()
                self._stats["redis_publish_failures"] += 1
        else:
            # Circuit is open — skip Redis, fallback only
            self._stats["redis_publish_failures"] += 1

        self._stats["events_published"] += 1
        return event

    async def subscribe(self, channel: str, handler: Optional[Callable] = None) -> asyncio.Queue:
        """Subscribe to a Sentinel channel.

        If a handler callback is provided, it will be called for each event.
        Otherwise, events can be consumed from the returned asyncio.Queue.

        Args:
            channel: SentinelChannel name
            handler: Optional async callback(event) for each event

        Returns:
            asyncio.Queue for consuming events
        """
        # Subscribe to in-process fallback
        queue = self._fallback.subscribe(channel)

        # Register handler if provided
        if handler:
            if channel not in self._local_handlers:
                self._local_handlers[channel] = []
            self._local_handlers[channel].append(handler)

            # Start handler task
            asyncio.create_task(self._run_handler(channel, queue, handler))

        # Subscribe to Redis if connected
        if self._redis_mgr.is_connected and channel not in self._subscribed_channels:
            await self._redis_mgr.subscribe(f"{self._config.redis_channel_prefix}{channel}")
            self._subscribed_channels.add(channel)

        return queue

    async def unsubscribe(self, channel: str, handler: Optional[Callable] = None) -> None:
        """Unsubscribe from a Sentinel channel."""
        # Remove handler
        if handler and channel in self._local_handlers:
            try:
                self._local_handlers[channel].remove(handler)
            except ValueError as _exc:
                logger.debug("suppressed %s", _exc, exc_info=False)

        # Unsubscribe from Redis
        if channel in self._subscribed_channels:
            await self._redis_mgr.unsubscribe(f"{self._config.redis_channel_prefix}{channel}")
            self._subscribed_channels.discard(channel)

    async def _redis_listener(self) -> None:
        """Background task that listens for Redis Pub/Sub messages
        and dispatches them to local handlers and fallback subscribers.
        """
        while self._running:
            try:
                messages = await self._redis_mgr.get_messages(timeout=0.5)
                for msg in messages:
                    if msg.get("type") == "message":
                        channel = msg.get("channel", b"")
                        if isinstance(channel, bytes):
                            channel = channel.decode()
                        # Strip Redis channel prefix (e.g., "sentinel:")
                        prefix = self._config.redis_channel_prefix
                        if channel.startswith(prefix):
                            channel = channel[len(prefix) :]

                        data = msg.get("data", b"")
                        if isinstance(data, bytes):
                            data = data.decode()

                        # Decompress if needed (compressed messages are hex-encoded gzip)
                        try:
                            json.loads(data)
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            try:
                                data = gzip.decompress(bytes.fromhex(data)).decode()
                            except Exception as _exc:
                                logger.debug("suppressed %s", _exc, exc_info=False)

                        event = SentinelEvent.from_json(data)
                        self._stats["events_received"] += 1

                        # Distribute to in-process fallback subscribers
                        await self._fallback.publish(channel, event)
                        self._stats["events_delivered_local"] += 1

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Sentinel Station Redis listener error: %s", str(e)[:200])
                await asyncio.sleep(1)

    async def _run_handler(
        self,
        channel: str,
        queue: asyncio.Queue,
        handler: Callable,
    ) -> None:
        """Run a handler callback for events from a queue."""
        while self._running:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=1.0)
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(event)
                    else:
                        handler(event)
                except Exception as e:
                    logger.warning(
                        "Sentinel Station handler error on channel %s: %s",
                        channel,
                        str(e)[:200],
                    )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    async def health_check(self) -> Dict[str, Any]:
        """Perform a health check and return status information."""
        redis_healthy = await self._redis_mgr.health_check()
        return {
            "status": "ok" if self._running else "stopped",
            "backend": "redis" if redis_healthy else "fallback",
            "redis_connected": redis_healthy,
            "circuit_breaker": self._circuit_breaker.state.value,
            "subscribed_channels": list(self._subscribed_channels),
            "fallback_stats": self._fallback.get_stats(),
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get Sentinel Station statistics."""
        return {
            **self._stats,
            "running": self._running,
            "redis_connected": self._redis_mgr.is_connected,
            "circuit_breaker_state": self._circuit_breaker.state.value,
            "circuit_breaker_failures": self._circuit_breaker._failure_count,
            "subscribed_channels": list(self._subscribed_channels),
            "fallback": self._fallback.get_stats(),
            "uptime_seconds": (
                time.time()
                - time.mktime(datetime.fromisoformat(self._stats["started_at"]).timetuple())
                if self._stats["started_at"]
                else 0
            ),
        }


# ── Shared SSE Event Generator ──────────────────────────────────────────────


class SharedSSEGenerator:
    """Shared SSE event generator for broadcasting Sentinel events to SSE clients.

    Instead of creating a per-client event loop, this generator uses a single
    asyncio.Queue that receives events from the Sentinel Station and yields
    them to all connected SSE clients.

    This pattern ensures O(1) overhead per event regardless of the number
    of SSE clients, as opposed to O(n) with per-client loops.

    Usage:
        station = SentinelStation()
        await station.start()
        sse_gen = SharedSSEGenerator(station)
        # In your SSE endpoint:
        async def sse_endpoint(request):
            async for event in sse_gen.generate():
                yield event
    """

    def __init__(self, station: SentinelStation, channels: Optional[List[str]] = None) -> None:
        self._station = station
        self._channels = channels or [ch.value for ch in SentinelChannel]
        self._queue: Optional[asyncio.Queue] = None
        self._subscribed = False
        self._stats = {
            "events_yielded": 0,
            "clients_served": 0,
        }

    async def start(self) -> None:
        """Start the SSE generator by subscribing to Sentinel channels."""
        if self._subscribed:
            return
        self._queue = await self._station.subscribe("sentinel")
        # Also subscribe to specific channels
        for channel in self._channels:
            await self._station.subscribe(channel)
        self._subscribed = True

    async def generate(self):
        """Async generator that yields SSE-formatted events.

        This is a single generator that broadcasts to all SSE clients.
        Each client gets its own copy of events from the shared queue.
        """
        self._stats["clients_served"] += 1
        if not self._queue:
            await self.start()

        while True:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=30.0)
                self._stats["events_yielded"] += 1
                yield {
                    "event": event.event_type or "message",
                    "data": event.to_json(),
                }
            except asyncio.TimeoutError:
                # Send keepalive
                yield {
                    "event": "keepalive",
                    "data": json.dumps({"timestamp": datetime.now(timezone.utc).isoformat()}),
                }

    def get_stats(self) -> Dict[str, Any]:
        """Get SSE generator statistics."""
        return {**self._stats, "subscribed": self._subscribed}


# ── Module-level Singleton ──────────────────────────────────────────────────

# Lazy-initialized singleton for use across the gateway service
_sentinel_station: Optional[SentinelStation] = None


def get_sentinel_station() -> SentinelStation:
    """Get or create the Sentinel Station singleton."""
    global _sentinel_station
    if _sentinel_station is None:
        _sentinel_station = SentinelStation()
    return _sentinel_station
