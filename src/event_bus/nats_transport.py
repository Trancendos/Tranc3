"""
NATS JetStream Transport Adapter for the Trancendos Event Bus
==============================================================
Optional transport layer that publishes events through NATS JetStream
alongside the existing SQLite + in-memory callback delivery.

Fully optional:
  - If ``nats-py`` is not installed, the module defines a no-op stub.
  - If ``NATS_URL`` environment variable is not set, ``connect()`` is a no-op.

Usage:
    import asyncio
    from src.event_bus.nats_transport import NATSTransport

    transport = NATSTransport()
    await transport.connect()  # no-op if NATS_URL unset or nats-py missing

    await transport.publish("user.created", {"user_id": "123"})
    await transport.subscribe("user.*", my_async_callback)

    await transport.disconnect()

Subject mapping:
    Trancendos event type  →  NATS subject
    "user.created"         →  "tranc3.user.created"
    "user.*"               →  "tranc3.user.*"   (wildcard preserved)
    "**"                   →  "tranc3.>"         (multi-level wildcard)

Stream:
    Name: TRANC3
    Subjects: tranc3.>
    Durable consumer: tranc3-event-bus
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Callable, Coroutine

logger = logging.getLogger("tranc3.event_bus.nats")

# ---------------------------------------------------------------------------
# Optional import guard — nats-py may not be installed
# ---------------------------------------------------------------------------

try:
    import nats
    import nats.js  # noqa: F401  — confirms JetStream is available
    from nats.aio.client import Client as NATSClient
    from nats.js.api import ConsumerConfig, StreamConfig
    from nats.js.errors import NotFoundError

    _NATS_AVAILABLE = True
except ImportError:
    _NATS_AVAILABLE = False
    NATSClient = None  # type: ignore[assignment,misc]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STREAM_NAME = "TRANC3"
STREAM_SUBJECT_PREFIX = "tranc3"
STREAM_SUBJECTS = [f"{STREAM_SUBJECT_PREFIX}.>"]
DURABLE_CONSUMER_NAME = "tranc3-event-bus"


# ---------------------------------------------------------------------------
# Subject helpers
# ---------------------------------------------------------------------------


def _event_type_to_subject(event_type: str) -> str:
    """
    Map a Trancendos event type to a NATS subject.

    Examples:
        "user.created"  →  "tranc3.user.created"
        "user.*"        →  "tranc3.user.*"
        "**"            →  "tranc3.>"
    """
    if event_type == "**":
        return f"{STREAM_SUBJECT_PREFIX}.>"
    return f"{STREAM_SUBJECT_PREFIX}.{event_type}"


def _pattern_to_nats_subject(pattern: str) -> str:
    """
    Convert a Trancendos subscription pattern to a NATS subject filter.

    "user.*"  →  "tranc3.user.*"   (single-level wildcard, NATS '*')
    "**"      →  "tranc3.>"        (multi-level wildcard, NATS '>')
    """
    if pattern == "**":
        return f"{STREAM_SUBJECT_PREFIX}.>"
    return f"{STREAM_SUBJECT_PREFIX}.{pattern}"


# ---------------------------------------------------------------------------
# No-op stub — used when nats-py is unavailable
# ---------------------------------------------------------------------------


class _NoOpTransport:
    """Silent no-op transport used when nats-py is not installed."""

    async def connect(self) -> None:  # noqa: D401
        pass

    async def disconnect(self) -> None:
        pass

    async def publish(self, subject: str, data: dict[str, Any]) -> None:
        pass

    async def subscribe(
        self,
        subject_pattern: str,
        callback: Callable[..., Coroutine[Any, Any, None]],
    ) -> None:
        pass

    async def create_stream(self, name: str, subjects: list[str]) -> None:
        pass

    @property
    def is_connected(self) -> bool:
        return False


# ---------------------------------------------------------------------------
# NATSTransport — full implementation
# ---------------------------------------------------------------------------


class NATSTransport:
    """
    Optional NATS JetStream transport adapter for the Trancendos Event Bus.

    Thread-safe, asyncio-compatible. Gracefully degrades to a no-op when:
    - ``nats-py`` is not installed, or
    - The ``NATS_URL`` environment variable is not set.

    Public API:
        connect()             — connect to NATS and ensure TRANC3 stream exists
        disconnect()          — flush, drain, and close the connection
        publish(subject, data) — publish a dict payload to a NATS subject
        subscribe(pattern, cb) — subscribe to a NATS subject pattern (push)
        create_stream(...)    — create/update a JetStream stream
        is_connected          — bool property
    """

    def __init__(
        self,
        nats_url: str | None = None,
        *,
        stream_name: str = STREAM_NAME,
        durable_name: str = DURABLE_CONSUMER_NAME,
    ) -> None:
        self._url: str | None = nats_url or os.getenv("NATS_URL")
        self._stream_name = stream_name
        self._durable_name = durable_name
        self._client: NATSClient | None = None
        self._js: Any = None  # JetStreamContext
        self._lock = asyncio.Lock()
        self._subscriptions: list[Any] = []  # nats.aio.subscription.Subscription

        if not _NATS_AVAILABLE:
            logger.debug(
                "nats-py not installed — NATSTransport operating as no-op. "
                "Install nats-py>=2.6.0 to enable NATS JetStream transport."
            )
        elif not self._url:
            logger.debug(
                "NATS_URL not set — NATSTransport operating as no-op. "
                "Set NATS_URL to enable NATS JetStream transport."
            )

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        """Return True if the NATS client is connected."""
        if not _NATS_AVAILABLE or self._client is None:
            return False
        return not self._client.is_closed  # type: ignore[union-attr]

    @property
    def _nats_enabled(self) -> bool:
        """Return True if NATS is both available and configured."""
        return _NATS_AVAILABLE and bool(self._url)

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def connect(self) -> None:
        """
        Connect to NATS and initialise the TRANC3 JetStream stream.

        No-op if nats-py is not installed or NATS_URL is not set.
        """
        if not self._nats_enabled:
            return

        async with self._lock:
            if self.is_connected:
                return

            try:
                self._client = await nats.connect(  # type: ignore[union-attr]
                    self._url,
                    name="tranc3-event-bus",
                    reconnect_time_wait=2,
                    max_reconnect_attempts=5,
                )
                self._js = self._client.jetstream()
                await self._ensure_stream()
                logger.info(
                    "nats_transport_connected",
                    extra={"url": self._url, "stream": self._stream_name},
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "nats_transport_connect_failed — operating as no-op: %s",
                    exc,
                )
                self._client = None
                self._js = None

    async def disconnect(self) -> None:
        """Flush, drain, and close the NATS connection."""
        if not self.is_connected or self._client is None:
            return

        async with self._lock:
            try:
                await self._client.flush(timeout=5)
                await self._client.drain()
            except Exception as exc:  # noqa: BLE001
                logger.debug("nats_transport_drain_error: %s", exc)
            finally:
                self._subscriptions.clear()
                self._client = None
                self._js = None
                logger.info("nats_transport_disconnected")

    # ── Publish ──────────────────────────────────────────────────────────

    async def publish(self, subject: str, data: dict[str, Any]) -> None:
        """
        Publish a dict payload to a NATS subject via JetStream.

        ``subject`` should be the NATS subject (e.g. ``tranc3.user.created``),
        not the raw event type.  The EventBus integration calls
        ``_event_type_to_subject`` before invoking this method.

        No-op if transport is not connected.
        """
        if not self.is_connected or self._js is None:
            return

        try:
            payload = json.dumps(data, default=str).encode("utf-8")
            await self._js.publish(subject, payload)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "nats_publish_error",
                extra={"subject": subject, "error": str(exc)},
            )

    # ── Subscribe ────────────────────────────────────────────────────────

    async def subscribe(
        self,
        subject_pattern: str,
        callback: Callable[..., Coroutine[Any, Any, None]],
    ) -> None:
        """
        Subscribe to a NATS subject pattern with a durable push consumer.

        ``subject_pattern`` should be the raw Trancendos pattern (e.g. ``user.*``);
        it will be converted to a NATS subject filter automatically.

        No-op if transport is not connected.
        """
        if not self.is_connected or self._js is None:
            return

        nats_subject = _pattern_to_nats_subject(subject_pattern)
        durable = f"{self._durable_name}-{subject_pattern.replace('*', 'star').replace('.', '-')}"

        async def _message_handler(msg: Any) -> None:
            try:
                raw = json.loads(msg.data.decode("utf-8"))
                await callback(raw)
                await msg.ack()
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "nats_subscriber_callback_error",
                    extra={"subject": nats_subject, "error": str(exc)},
                )
                try:
                    await msg.nak()
                except Exception:  # noqa: BLE001
                    pass

        try:
            sub = await self._js.subscribe(
                nats_subject,
                durable=durable,
                cb=_message_handler,
                config=ConsumerConfig(
                    durable_name=durable,
                    ack_wait=30,
                    max_deliver=3,
                ),
            )
            self._subscriptions.append(sub)
            logger.info(
                "nats_subscribed",
                extra={"nats_subject": nats_subject, "durable": durable},
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "nats_subscribe_error",
                extra={"subject": nats_subject, "error": str(exc)},
            )

    # ── Stream management ────────────────────────────────────────────────

    async def create_stream(
        self,
        name: str,
        subjects: list[str],
    ) -> None:
        """
        Create or update a JetStream stream.

        No-op if transport is not connected.
        """
        if not self.is_connected or self._js is None:
            return

        try:
            await self._js.add_stream(
                StreamConfig(
                    name=name,
                    subjects=subjects,
                    retention="limits",
                    max_msgs=1_000_000,
                    max_bytes=512 * 1024 * 1024,  # 512 MB
                    max_age=7 * 24 * 3600,  # 7 days in seconds
                    storage="file",
                    num_replicas=1,
                )
            )
            logger.info(
                "nats_stream_created",
                extra={"name": name, "subjects": subjects},
            )
        except Exception as exc:  # noqa: BLE001
            # Stream may already exist — attempt update
            try:
                await self._js.update_stream(
                    StreamConfig(
                        name=name,
                        subjects=subjects,
                    )
                )
                logger.debug("nats_stream_updated: %s", name)
            except Exception as update_exc:  # noqa: BLE001
                logger.warning(
                    "nats_stream_create_error",
                    extra={"name": name, "error": str(exc), "update_error": str(update_exc)},
                )

    # ── Private helpers ──────────────────────────────────────────────────

    async def _ensure_stream(self) -> None:
        """Ensure the TRANC3 stream exists, creating it if necessary."""
        if self._js is None:
            return

        try:
            # Check if stream already exists
            await self._js.find_stream(STREAM_SUBJECTS[0])
            logger.debug("nats_stream_exists: %s", self._stream_name)
        except NotFoundError:
            # Stream does not exist — create it
            await self.create_stream(self._stream_name, STREAM_SUBJECTS)
        except Exception as exc:  # noqa: BLE001
            # Older nats-py versions may not have find_stream — fall back to create
            logger.debug("nats_stream_check_fallback: %s", exc)
            await self.create_stream(self._stream_name, STREAM_SUBJECTS)


# ---------------------------------------------------------------------------
# Convenience factory — returns NATSTransport or no-op stub
# ---------------------------------------------------------------------------


def make_nats_transport(nats_url: str | None = None) -> NATSTransport:
    """
    Factory that always returns a ``NATSTransport`` instance.

    The instance silently no-ops if nats-py is missing or NATS_URL is not set,
    so callers do not need to guard against availability themselves.
    """
    return NATSTransport(nats_url=nats_url)


__all__ = [
    "NATSTransport",
    "make_nats_transport",
    "STREAM_NAME",
    "STREAM_SUBJECT_PREFIX",
    "STREAM_SUBJECTS",
    "DURABLE_CONSUMER_NAME",
    "_event_type_to_subject",
    "_pattern_to_nats_subject",
]
