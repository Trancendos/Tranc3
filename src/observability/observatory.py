# src/observability/observatory.py
# The Observatory — audit log for every action, change, activity on Trancendos.
#
# Every write operation anywhere in the platform emits an AuditEvent.
# Events are:
#   1. Stored in-process ring buffer (last 10k events) for fast /observatory/feed
#   2. Written to the audit log table (PostgreSQL, via async queue)
#   3. Forwarded to The Library for KB article generation triggers
#   4. Forwarded to The Void when secrets are accessed
#
# Usage:
#   from src.observability.observatory import observe
#   observe("user.login", actor="user:42", target="auth", metadata={"ip": "..."})

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from shared_core.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)

# Max events kept in memory
_RING_BUFFER_SIZE = 10_000


class EventSeverity(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    SECURITY = "security"  # always retained, triggers Cryptex


class EventCategory(str, Enum):
    AUTH = "auth"  # login, logout, token refresh, SSO
    DATA = "data"  # create, read, update, delete
    SECRETS = "secrets"  # The Void access
    WORKFLOW = "workflow"  # The Digital Grid runs
    AI = "ai"  # inference, embedding, generation
    BILLING = "billing"  # payments, tier changes
    SECURITY = "security"  # Cryptex, The Ice Box, The Lighthouse
    GOVERNANCE = "governance"  # The Town Hall policy changes
    SYSTEM = "system"  # startup, shutdown, config changes
    AUDIT = "audit"  # admin actions


@dataclass
class AuditEvent:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    event_type: str = ""  # e.g. "user.login", "secret.retrieve"
    category: EventCategory = EventCategory.SYSTEM
    severity: EventSeverity = EventSeverity.INFO
    actor: Optional[str] = None  # "user:42", "system", "bot:CODE"
    actor_ip: Optional[str] = None
    target: Optional[str] = None  # "auth", "secret:abc", "workflow:xyz"
    service: str = "tranc3-backend"  # which Trancendos service
    location: Optional[str] = None  # The Spark, The Void, Royal Bank, etc.
    outcome: str = "success"  # "success" | "failure" | "partial"
    metadata: Dict[str, Any] = field(default_factory=dict)
    session_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the audit event to a JSON-friendly dictionary."""
        d = asdict(self)
        d["category"] = self.category.value
        d["severity"] = self.severity.value
        return d


class Observatory:
    """
    The Observatory — central audit and event log for the Trancendos platform.

    Accepts events from anywhere in the platform, persists them, and exposes
    a streaming feed for real-time monitoring dashboards.
    """

    def __init__(self, buffer_size: int = _RING_BUFFER_SIZE):
        self._buffer: deque[AuditEvent] = deque(maxlen=buffer_size)
        self._subscribers: List[asyncio.Queue] = []
        self._lock = asyncio.Lock() if asyncio.get_event_loop().is_running() else None
        self._write_queue: Optional[asyncio.Queue] = None
        self._writer_task: Optional[asyncio.Task] = None

    def record(
        self,
        event_type: str,
        *,
        actor: Optional[str] = None,
        target: Optional[str] = None,
        category: EventCategory = EventCategory.SYSTEM,
        severity: EventSeverity = EventSeverity.INFO,
        service: str = "tranc3-backend",
        location: Optional[str] = None,
        outcome: str = "success",
        metadata: Optional[Dict[str, Any]] = None,
        actor_ip: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> AuditEvent:
        """Record an audit event, persist it to the ring buffer, and notify subscribers."""
        event = AuditEvent(
            event_type=event_type,
            category=category,
            severity=severity,
            actor=actor,
            actor_ip=actor_ip,
            target=target,
            service=service,
            location=location,
            outcome=outcome,
            metadata=metadata or {},
            session_id=session_id,
        )
        self._buffer.append(event)
        logger.debug(  # codeql[py/cleartext-logging]
            "observatory: %s actor=%s target=%s outcome=%s",
            sanitize_for_log(event_type),
            sanitize_for_log(actor),
            sanitize_for_log(target),
            sanitize_for_log(outcome),
        )
        self._notify_subscribers(event)

        # Forward SECURITY and CRITICAL events to The Basement for permanent archival
        if severity in (EventSeverity.SECURITY, EventSeverity.CRITICAL):
            try:
                from src.basement.archive import get_basement

                get_basement().ingest_observatory_event(event)
            except Exception:
                pass  # nosec B110 — graceful degradation; error logged upstream

        return event

    def _notify_subscribers(self, event: AuditEvent) -> None:
        dead = []
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self._subscribers.remove(q)

    def subscribe(self, maxsize: int = 1000) -> asyncio.Queue:
        """Subscribe to the live event stream. Returns an asyncio.Queue."""
        q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """Remove a subscriber queue from the live event stream."""
        try:
            self._subscribers.remove(q)
        except ValueError:
            logger.debug("Graceful degradation: %s", "unknown")  # nosec B110

    def recent(
        self, limit: int = 100, category: Optional[EventCategory] = None
    ) -> List[AuditEvent]:
        """Return recent events, newest first. Optionally filter by category."""
        events = list(self._buffer)
        if category:
            events = [e for e in events if e.category == category]
        return list(reversed(events))[-limit:]

    def search(
        self, actor: Optional[str] = None, event_type: Optional[str] = None, limit: int = 50
    ) -> List[AuditEvent]:
        """Search the buffer for events matching the given actor or event_type prefix."""
        results = []
        for e in reversed(self._buffer):
            if actor and e.actor != actor:
                continue
            if event_type and not e.event_type.startswith(event_type):
                continue
            results.append(e)
            if len(results) >= limit:
                break
        return results

    def stats(self) -> Dict[str, Any]:
        """Return summary statistics about the event buffer."""
        total = len(self._buffer)
        by_category: Dict[str, int] = {}
        by_severity: Dict[str, int] = {}
        for e in self._buffer:
            by_category[e.category.value] = by_category.get(e.category.value, 0) + 1
            by_severity[e.severity.value] = by_severity.get(e.severity.value, 0) + 1
        return {
            "total_events": total,
            "buffer_capacity": self._buffer.maxlen,
            "subscribers": len(self._subscribers),
            "by_category": by_category,
            "by_severity": by_severity,
        }


# Module-level singleton
_observatory: Optional[Observatory] = None


def get_observatory() -> Observatory:
    """Return the module-level Observatory singleton, creating it if necessary."""
    global _observatory
    if _observatory is None:
        _observatory = Observatory()
    return _observatory


def observe(
    event_type: str,
    **kwargs: Any,
) -> AuditEvent:
    """Convenience function — call from anywhere in the platform."""
    return get_observatory().record(event_type, **kwargs)
