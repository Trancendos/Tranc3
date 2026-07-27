"""Observatory → Library pipeline — wires audit events to KB article triggers.

Runs in-process alongside The Library (both live inside the tranc3-backend
app), so triggers are handed straight to ``Library.create()`` rather than
round-tripped over HTTP to a ``/kb/ingest`` endpoint that has never existed.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("tranc3.observability.library_pipeline")

PIPELINE_ENABLED = os.getenv("LIBRARY_PIPELINE_ENABLED", "true").lower() == "true"
BATCH_SIZE = int(os.getenv("LIBRARY_PIPELINE_BATCH_SIZE", "20"))
FLUSH_INTERVAL_SEC = float(os.getenv("LIBRARY_PIPELINE_FLUSH_INTERVAL", "30"))

# Severities that warrant a KB article regardless of event_type.
_TRIGGER_SEVERITIES = ("critical", "security")
# event_type prefixes that warrant a KB article regardless of severity.
_TRIGGER_EVENT_PREFIXES = ("secret.", "auth.", "vault.", "security.", "cve.")


@dataclass
class KBTrigger:
    """A single Observatory audit event queued for Library ingestion."""

    event_type: str
    actor: str
    resource: str
    summary: str
    severity: str  # matches src.observability.observatory.EventSeverity values
    timestamp: float
    tags: list[str]
    source_service: str = "observatory"


_queue: list[KBTrigger] = []
_lock = asyncio.Lock()


def _should_trigger(event: dict[str, Any]) -> bool:
    """Only forward events that are Library-worthy (errors, security, significant changes).

    ``event`` is expected to be an ``AuditEvent.to_dict()`` — keyed by
    ``event_type``/``severity``/``target``/``metadata``, not the
    ``action``/``resource`` names this once (incorrectly) checked for.
    """
    severity = str(event.get("severity", "info"))
    event_type = str(event.get("event_type", ""))
    return severity in _TRIGGER_SEVERITIES or event_type.startswith(_TRIGGER_EVENT_PREFIXES)


async def ingest(event: dict[str, Any]) -> None:
    """Receive an Observatory audit event and queue it for Library if eligible."""
    if not PIPELINE_ENABLED or not _should_trigger(event):
        return

    metadata = event.get("metadata") or {}
    trigger = KBTrigger(
        event_type=str(event.get("event_type", "unknown")),
        actor=str(event.get("actor") or "system"),
        resource=str(event.get("target") or ""),
        summary=str(metadata.get("message", event.get("event_type", ""))),
        severity=str(event.get("severity", "info")),
        timestamp=event.get("timestamp", time.time()),
        tags=list(metadata.get("tags", [])),
    )

    batch: list[KBTrigger] = []
    async with _lock:
        _queue.append(trigger)
        if len(_queue) >= BATCH_SIZE:
            batch = _queue.copy()
            _queue.clear()
    # Flush outside the lock so I/O doesn't block concurrent ingest() calls
    if batch:
        await _send_batch(batch)


def _format_article_body(batch: list[KBTrigger]) -> str:
    lines = [f"Auto-generated from {len(batch)} Observatory audit event(s).", ""]
    for t in batch:
        lines.append(f"- [{t.severity}] {t.event_type} — actor={t.actor} resource={t.resource}")
        if t.summary and t.summary != t.event_type:
            lines.append(f"  {t.summary}")
    return "\n".join(lines)


async def _send_batch(batch: list[KBTrigger]) -> None:
    """Create a Library article from a pre-collected batch; called outside the lock."""
    try:
        from src.library.knowledge_base import get_library

        worst_severity = "critical" if any(t.severity == "critical" for t in batch) else "security"
        tags = {"observatory", "auto-generated", worst_severity}
        for t in batch:
            tags.update(t.tags)

        get_library().create(
            title=f"Observatory alert batch — {len(batch)} {worst_severity} event(s)",
            body=_format_article_body(batch),
            tags=sorted(tags),
            author="observatory",
            source="observatory",
        )
        logger.debug("Library pipeline created article from %d triggers", len(batch))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Library pipeline failed to ingest batch: %s", exc)


async def _flush() -> None:
    """Drain the queue under lock, then send outside it."""
    batch: list[KBTrigger] = []
    async with _lock:
        if _queue:
            batch = _queue.copy()
            _queue.clear()
    if batch:
        await _send_batch(batch)


async def flush_loop() -> None:
    """Background coroutine: flush the queue every FLUSH_INTERVAL_SEC seconds."""
    while True:
        await asyncio.sleep(FLUSH_INTERVAL_SEC)
        await _flush()


def start_pipeline(app: Any = None) -> None:
    """
    Register the flush loop on app startup (FastAPI lifespan compatible).
    Call this from api.py / api/core.py startup.
    """
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(flush_loop())
        logger.info(
            "Observatory→Library pipeline started (batch=%d, interval=%ss)",
            BATCH_SIZE,
            FLUSH_INTERVAL_SEC,
        )
    except RuntimeError:
        logger.warning("No running event loop — Library pipeline deferred")
