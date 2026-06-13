# src/nexus/hub.py
# The Nexus — AI communications and transfer hub.
#
# The Nexus is the central message broker between all Trancendos services.
# It handles:
#   - Inter-service messages (publish/subscribe)
#   - AI task routing (dispatches to Luminous / Tranc3Engine)
#   - WebSocket connection management (bridges to infinity-ws-api CF Worker)
#   - Event fan-out to The Observatory, The Digital Grid, The Spark SSE
#
# The Nexus exposes both a Python API (for in-process use) and an HTTP API
# at /nexus/send, /nexus/subscribe (WebSocket), /nexus/status.

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from Dimensional.error_handlers import safe_error_detail
from Dimensional.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


class MessagePriority(int, Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class MessageType(str, Enum):
    # AI pipeline
    INFERENCE_REQUEST = "inference.request"
    INFERENCE_RESPONSE = "inference.response"
    EMBED_REQUEST = "embed.request"
    EMBED_RESPONSE = "embed.response"

    # Inter-service
    SERVICE_EVENT = "service.event"
    HEALTH_PING = "health.ping"
    HEALTH_PONG = "health.pong"

    # Grid / workflow
    WORKFLOW_TRIGGER = "workflow.trigger"
    WORKFLOW_STATUS = "workflow.status"

    # Observatory
    AUDIT_EVENT = "audit.event"

    # User
    USER_MESSAGE = "user.message"
    BROADCAST = "broadcast"


@dataclass
class NexusMessage:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    type: MessageType = MessageType.SERVICE_EVENT
    priority: MessagePriority = MessagePriority.NORMAL
    sender: str = "system"
    recipient: Optional[str] = None  # None = broadcast
    topic: Optional[str] = None  # pub/sub topic
    payload: Dict[str, Any] = field(default_factory=dict)
    reply_to: Optional[str] = None  # message ID to reply to
    ttl_seconds: float = 30.0  # discard if not consumed within TTL

    def is_expired(self) -> bool:
        return time.time() > self.timestamp + self.ttl_seconds


_Handler = Callable[[NexusMessage], Any]


class NexusHub:
    """
    The Nexus — central communications hub for Trancendos.

    Supports both direct send (point-to-point) and pub/sub (topic-based).
    All messages are observable via The Observatory.
    """

    def __init__(self):
        self._topics: Dict[str, List[asyncio.Queue]] = {}
        self._direct: Dict[str, asyncio.Queue] = {}
        self._handlers: Dict[str, List[_Handler]] = {}
        self._stats = {
            "sent": 0,
            "delivered": 0,
            "dropped": 0,
            "subscribers": 0,
        }

    # ── Pub/sub ──────────────────────────────────────────────────────────────

    def subscribe_topic(self, topic: str, maxsize: int = 500) -> asyncio.Queue:
        """Subscribe to a named topic. Returns a queue that receives messages."""
        q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._topics.setdefault(topic, []).append(q)
        self._stats["subscribers"] += 1
        logger.debug(
            "nexus: +subscriber topic=%s total=%d",
            sanitize_for_log(topic),
            len(self._topics[topic]),
        )  # codeql[py/cleartext-logging]
        return q

    def unsubscribe_topic(self, topic: str, q: asyncio.Queue) -> None:
        subscribers = self._topics.get(topic, [])
        try:
            subscribers.remove(q)
            self._stats["subscribers"] -= 1
        except ValueError:
            logger.debug("Graceful degradation: %s", "unknown")  # nosec B110

    def publish(
        self,
        topic: str,
        payload: Dict[str, Any],
        sender: str = "system",
        priority: MessagePriority = MessagePriority.NORMAL,
        ttl_seconds: float = 30.0,
    ) -> NexusMessage:
        """Publish a message to all subscribers on a topic."""
        msg = NexusMessage(
            type=MessageType.SERVICE_EVENT,
            priority=priority,
            sender=sender,
            topic=topic,
            payload=payload,
            ttl_seconds=ttl_seconds,
        )
        self._fan_out(topic, msg)
        return msg

    def _fan_out(self, topic: str, msg: NexusMessage) -> None:
        self._stats["sent"] += 1
        subscribers = self._topics.get(topic, [])
        dead = []
        for q in subscribers:
            try:
                q.put_nowait(msg)
                self._stats["delivered"] += 1
            except asyncio.QueueFull:
                self._stats["dropped"] += 1
                dead.append(q)
        for q in dead:
            try:
                subscribers.remove(q)
                self._stats["subscribers"] -= 1
            except ValueError:
                logger.debug("Graceful degradation: %s", "unknown")  # nosec B110

    # ── Direct send ──────────────────────────────────────────────────────────

    def register_service(self, service_id: str, maxsize: int = 200) -> asyncio.Queue:
        """Register a service to receive direct messages. Returns its inbox queue."""
        q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._direct[service_id] = q
        return q

    async def send(
        self,
        recipient: str,
        payload: Dict[str, Any],
        sender: str = "system",
        msg_type: MessageType = MessageType.SERVICE_EVENT,
        priority: MessagePriority = MessagePriority.NORMAL,
    ) -> Optional[NexusMessage]:
        """Send a direct message to a registered service. Returns None if no inbox."""
        q = self._direct.get(recipient)
        if q is None:
            logger.debug(
                "nexus: no inbox for recipient=%s", sanitize_for_log(recipient)
            )  # codeql[py/cleartext-logging]
            self._stats["dropped"] += 1
            return None
        msg = NexusMessage(
            type=msg_type,
            priority=priority,
            sender=sender,
            recipient=recipient,
            payload=payload,
        )
        self._stats["sent"] += 1
        try:
            await q.put(msg)
            self._stats["delivered"] += 1
        except asyncio.QueueFull:
            self._stats["dropped"] += 1
        return msg

    # ── AI routing ───────────────────────────────────────────────────────────

    async def route_inference(
        self, prompt: str, personality: str = "tranc3-base", sender: str = "system"
    ) -> Dict[str, Any]:
        """Route an inference request through Luminous (Tranc3Engine)."""
        try:
            from src.core.tranc3_inference import get_engine

            engine = get_engine()
            result = await engine.generate(prompt, personality=personality)
            self.publish(
                "ai.inference.complete", {"prompt_len": len(prompt), **result}, sender=sender
            )
            return result
        except Exception as exc:
            logger.error(
                "nexus.route_inference error: %s", sanitize_for_log(exc)
            )  # codeql[py/cleartext-logging]
            return {"response": "", "error": safe_error_detail(exc, 500)}

    # ── Status ───────────────────────────────────────────────────────────────

    def status(self) -> Dict[str, Any]:
        return {
            "topics": {t: len(qs) for t, qs in self._topics.items()},
            "registered_services": list(self._direct.keys()),
            "stats": self._stats,
        }


# Module-level singleton
_hub: Optional[NexusHub] = None


def get_nexus() -> NexusHub:
    global _hub
    if _hub is None:
        _hub = NexusHub()
    return _hub
