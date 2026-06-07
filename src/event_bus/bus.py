"""
Event Bus — Core Implementation
==================================
Ported from @trancendos/event-bus EventBus class.

Provides pattern-based event routing, in-memory callbacks,
batch processing, and optional SQLite persistence.

Replaces Cloudflare Queue bindings — zero-cost, self-hosted.
"""

from __future__ import annotations

import asyncio
import fnmatch
import json
import logging
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from Dimensional.sanitize import sanitize_for_log
from src.database.encrypted_sqlite import connect as sqlite3_connect
from src.event_bus.types import (
    DEFAULT_EVENT_BUS_CONFIG,
    DeliveryResult,
    DeliveryStatus,
    EventBusConfig,
    EventCallback,
    EventEnvelope,
    EventMetadata,
    EventSubscription,
)

# Optional NATS transport — imported lazily to avoid hard dependency
try:
    from src.event_bus.nats_transport import NATSTransport, _event_type_to_subject

    _NATS_TRANSPORT_AVAILABLE = True
except ImportError:
    _NATS_TRANSPORT_AVAILABLE = False
    NATSTransport = None  # type: ignore[assignment,misc]
    _event_type_to_subject = None  # type: ignore[assignment]

logger = logging.getLogger("tranc3.event_bus")


class EventBusError(Exception):
    """Event bus specific errors."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


class EventBus:
    """
    Platform Event Bus for type-safe inter-service communication.

    Features:
    - Pattern-based routing (e.g., 'user.*', 'order.created')
    - In-memory callbacks with subscribe/unsubscribe
    - Fire-and-forget emission
    - Batch processing with configurable flush
    - Optional SQLite persistence for event log
    - Payload size validation

    Usage:
        bus = EventBus()
        bus.subscribe(EventSubscription(id="sub1", subscriber="my-worker", event_pattern="user.*"))
        await bus.emit(event_type="user.created", data={"user_id": "123"})
    """

    def __init__(self, config: EventBusConfig | None = None) -> None:
        self.config = config or DEFAULT_EVENT_BUS_CONFIG
        self._subscriptions: dict[str, EventSubscription] = {}
        self._callbacks: dict[str, list[EventCallback]] = {}
        self._buffer: list[EventEnvelope] = []
        self._event_log: list[EventEnvelope] = []
        self._db: sqlite3.Connection | None = None

        # Optional NATS JetStream transport (set via set_nats_transport())
        self._nats_transport: Any | None = None  # NATSTransport instance

        # Initialise SQLite if configured
        if self.config.sqlite_path:
            self._init_sqlite(self.config.sqlite_path)

    def _init_sqlite(self, path: str) -> None:
        """Initialise SQLite persistence."""
        db_path = Path(path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3_connect(str(db_path))
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                data TEXT NOT NULL,
                source TEXT,
                tenant_id TEXT,
                timestamp TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)
        """)
        self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_tenant ON events(tenant_id)
        """)
        self._db.commit()

    async def close(self) -> None:
        """Clean up resources."""
        if self._buffer:
            await self.flush()
        if self._db:
            self._db.close()
        if self._nats_transport is not None:
            await self._nats_transport.disconnect()

    # ── NATS transport ───────────────────────────────────────

    def set_nats_transport(self, transport: Any) -> None:
        """
        Attach an optional NATS JetStream transport adapter.

        Once set, every call to ``emit()`` will publish the event through
        NATS JetStream *in addition* to the local SQLite + callback delivery.

        Pass a ``NATSTransport`` instance (from ``src.event_bus.nats_transport``).
        The transport must already be connected (``await transport.connect()``).

        Example::

            from src.event_bus.nats_transport import make_nats_transport
            transport = make_nats_transport()
            await transport.connect()
            bus.set_nats_transport(transport)
        """
        self._nats_transport = transport
        logger.info("event_bus_nats_transport_attached")

    # ── Emit ─────────────────────────────────────────────────

    async def emit(
        self,
        event_type: str,
        data: dict[str, Any] | None = None,
        source: str = "",
        tenant_id: str | None = None,
        correlation_id: str | None = None,
    ) -> list[DeliveryResult]:
        """
        Emit an event to all matching subscribers.

        Returns delivery results for each matched subscription.
        """
        event = self._build_envelope(
            event_type=event_type,
            data=data or {},
            source=source,
            tenant_id=tenant_id,
            correlation_id=correlation_id,
        )

        # Validate payload size
        payload_size = len(json.dumps(event.data).encode("utf-8"))
        if payload_size > self.config.max_payload_size:
            raise EventBusError(
                "PAYLOAD_TOO_LARGE",
                f"Event payload size {payload_size} exceeds max {self.config.max_payload_size}",
            )

        # Persist to log
        if self.config.persist_events:
            self._event_log.append(event)
            self._persist_to_sqlite(event)

        # Buffer for batch processing
        self._buffer.append(event)

        # Publish through NATS JetStream if transport is attached
        if self._nats_transport is not None and _event_type_to_subject is not None:
            try:
                nats_subject = _event_type_to_subject(event_type)
                await self._nats_transport.publish(
                    nats_subject,
                    event.model_dump(mode="json"),
                )
            except Exception as _nats_exc:  # noqa: BLE001
                logger.error(
                    "nats_publish_error",
                    extra={"event_type": event_type, "error": str(_nats_exc)},
                )

        # Find matching subscriptions
        results: list[DeliveryResult] = []
        matching_subs = self._find_matching_subscriptions(event)

        for sub in matching_subs:
            result = await self._deliver(event, sub)
            results.append(result)

        # Deliver to in-memory callbacks
        await self._deliver_to_callbacks(event)

        # Flush buffer if needed
        if len(self._buffer) >= self.config.batch_size:
            await self.flush()

        return results

    def emit_async(
        self,
        event_type: str,
        data: dict[str, Any] | None = None,
        source: str = "",
        tenant_id: str | None = None,
    ) -> None:
        """Emit without awaiting delivery. Fire-and-forget pattern."""
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(
                self.emit(
                    event_type=event_type,
                    data=data,
                    source=source,
                    tenant_id=tenant_id,
                ),
            )
        except RuntimeError:
            logger.warning("emit_async_no_loop", extra={"event_type": event_type})

    # ── Subscribe ────────────────────────────────────────────

    def subscribe(self, subscription: EventSubscription) -> None:
        """Register a subscription for event delivery."""
        self._subscriptions[subscription.id] = subscription
        logger.info(
            "event_subscribed",
            extra={"subscriber": subscription.subscriber, "pattern": subscription.event_pattern},
        )

    def unsubscribe(self, subscription_id: str) -> bool:
        """Remove a subscription by ID."""
        return self._subscriptions.pop(subscription_id, None) is not None

    def on(self, event_pattern: str, callback: EventCallback) -> Callable[[], None]:
        """
        Register an in-memory callback for an event pattern.
        Returns an unsubscribe function.
        """
        callbacks = self._callbacks.get(event_pattern, [])
        callbacks.append(callback)
        self._callbacks[event_pattern] = callbacks

        def unsubscribe() -> None:
            cbs = self._callbacks.get(event_pattern, [])
            if callback in cbs:
                cbs.remove(callback)
            if not cbs:
                self._callbacks.pop(event_pattern, None)

        return unsubscribe

    def once(self, event_pattern: str, callback: EventCallback) -> Callable[[], None]:
        """Register a one-time callback for an event pattern."""
        unsubscribe_fn: Callable[[], None] | None = None

        async def one_shot(event: EventEnvelope) -> None:
            if unsubscribe_fn:
                unsubscribe_fn()
            await callback(event)

        unsubscribe_fn = self.on(event_pattern, one_shot)
        return unsubscribe_fn

    # ── Query ────────────────────────────────────────────────

    def get_subscriptions(self) -> list[EventSubscription]:
        """Get all registered subscriptions."""
        return list(self._subscriptions.values())

    def get_matching_subscriptions(self, event_type: str) -> list[EventSubscription]:
        """Get subscriptions matching an event type."""
        return [
            sub
            for sub in self._subscriptions.values()
            if sub.enabled and self._matches_pattern(sub.event_pattern, event_type)
        ]

    def get_event_log(self) -> list[EventEnvelope]:
        """Get the event log (when persistEvents is true)."""
        return list(self._event_log)

    # ── Batch Processing ─────────────────────────────────────

    async def flush(self) -> int:
        """Flush the event buffer. Returns number of events flushed."""
        events = self._buffer.copy()
        self._buffer.clear()
        logger.info("event_buffer_flushed: %s events", sanitize_for_log(len(events)))
        return len(events)

    # ── Private ──────────────────────────────────────────────

    def _build_envelope(
        self,
        event_type: str,
        data: dict[str, Any],
        source: str = "",
        tenant_id: str | None = None,
        correlation_id: str | None = None,
    ) -> EventEnvelope:
        """Build a complete event envelope."""
        return EventEnvelope(
            event_type=event_type,
            data=data,
            metadata=EventMetadata(
                event_id=str(uuid.uuid4()),
                correlation_id=correlation_id,
                source=source,
                tenant_id=tenant_id,
                timestamp=datetime.now(timezone.utc),
            ),
        )

    def _find_matching_subscriptions(self, event: EventEnvelope) -> list[EventSubscription]:
        """Find all subscriptions matching an event."""
        matching = []
        for sub in self._subscriptions.values():
            if not sub.enabled:
                continue
            if not self._matches_pattern(sub.event_pattern, event.event_type):
                continue
            # Apply filters
            if sub.filter:
                if sub.filter.tenant_id and sub.filter.tenant_id != event.metadata.tenant_id:
                    continue
                if sub.filter.source and sub.filter.source != event.metadata.source:
                    continue
            matching.append(sub)
        return matching

    def _matches_pattern(self, pattern: str, event_type: str) -> bool:
        """
        Match an event type against a pattern.

        Supports:
        - Exact match: "user.created"
        - Wildcard: "user.*"
        - Multi-level wildcard: "user.**"
        - Glob patterns: "order.*.completed"
        """
        if pattern == event_type:
            return True
        if pattern == "**":
            return True
        if "*" in pattern:
            return fnmatch.fnmatch(event_type, pattern)
        return False

    async def _deliver(self, event: EventEnvelope, sub: EventSubscription) -> DeliveryResult:
        """Deliver an event to a subscriber."""
        start = time.monotonic()
        attempts = 0

        for attempt in range(sub.max_retries + 1):
            attempts += 1
            try:
                if sub.delivery_type == "callback":
                    # Look up in-memory callback
                    callbacks = self._callbacks.get(sub.event_pattern, [])
                    for cb in callbacks:
                        await cb(event)

                elif sub.delivery_type == "webhook" and sub.endpoint:
                    # Webhook delivery — would use httpx here
                    import httpx

                    async with httpx.AsyncClient() as client:
                        resp = await client.post(
                            sub.endpoint,
                            json=event.model_dump(mode="json"),
                            timeout=10.0,
                        )
                        if resp.status_code >= 400:
                            raise Exception(f"Webhook returned {resp.status_code}")

                latency_ms = (time.monotonic() - start) * 1000
                return DeliveryResult(
                    subscription_id=sub.id,
                    status=DeliveryStatus.DELIVERED,
                    attempts=attempts,
                    latency_ms=latency_ms,
                )

            except Exception as e:
                if attempt < sub.max_retries:
                    await asyncio.sleep(sub.retry_delay_ms / 1000.0)
                    continue

                latency_ms = (time.monotonic() - start) * 1000
                return DeliveryResult(
                    subscription_id=sub.id,
                    status=DeliveryStatus.FAILED,
                    error=str(e),
                    attempts=attempts,
                    latency_ms=latency_ms,
                )

        return DeliveryResult(
            subscription_id=sub.id,
            status=DeliveryStatus.FAILED,
            error="Max retries exceeded",
            attempts=attempts,
        )

    async def _deliver_to_callbacks(self, event: EventEnvelope) -> None:
        """Deliver an event to all matching in-memory callbacks."""
        # Snapshot the callback map to avoid RuntimeError from dict mutation
        # during iteration (e.g., `once` callbacks unsubscribe themselves)
        snapshot = {pattern: list(cbs) for pattern, cbs in self._callbacks.items()}
        for pattern, callbacks in snapshot.items():
            if self._matches_pattern(pattern, event.event_type):
                for cb in callbacks:
                    try:
                        await cb(event)
                    except Exception as e:
                        logger.error(
                            "callback_delivery_error",
                            extra={"pattern": pattern, "error": str(e)},
                        )

    def _persist_to_sqlite(self, event: EventEnvelope) -> None:
        """Persist an event to SQLite."""
        if not self._db:
            return
        try:
            self._db.execute(
                "INSERT INTO events (event_id, event_type, data, source, tenant_id, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    event.metadata.event_id,
                    event.event_type,
                    json.dumps(event.data),
                    event.metadata.source,
                    event.metadata.tenant_id,
                    event.metadata.timestamp.isoformat(),
                ),
            )
            self._db.commit()
        except sqlite3.Error as e:
            logger.error("sqlite_persist_error: %s", sanitize_for_log(e))
