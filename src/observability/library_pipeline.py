"""Observatory → Library pipeline — wires audit events to KB article triggers."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, asdict
from typing import Any, Optional

logger = logging.getLogger("tranc3.observability.library_pipeline")

LIBRARY_URL = os.getenv("LIBRARY_URL", "http://localhost:8024")  # search-service / wiki
PIPELINE_ENABLED = os.getenv("LIBRARY_PIPELINE_ENABLED", "true").lower() == "true"
BATCH_SIZE = int(os.getenv("LIBRARY_PIPELINE_BATCH_SIZE", "20"))
FLUSH_INTERVAL_SEC = float(os.getenv("LIBRARY_PIPELINE_FLUSH_INTERVAL", "30"))


@dataclass
class KBTrigger:
    """Payload sent to The Library when an audit event warrants KB article creation."""
    event_type: str
    actor: str
    resource: str
    summary: str
    severity: str  # info|warning|error|critical
    timestamp: float
    tags: list[str]
    source_service: str = "observatory"


_queue: list[KBTrigger] = []
_lock = asyncio.Lock()


def _should_trigger(event: dict[str, Any]) -> bool:
    """Only forward events that are Library-worthy (errors, security, significant changes)."""
    severity = event.get("severity", "info")
    action = event.get("action", "")
    return severity in ("error", "critical") or action.startswith(
        ("secret.", "auth.", "vault.", "security.", "cve.")
    )


async def ingest(event: dict[str, Any]) -> None:
    """Receive an Observatory audit event and queue it for Library if eligible."""
    if not PIPELINE_ENABLED or not _should_trigger(event):
        return

    trigger = KBTrigger(
        event_type=event.get("action", "unknown"),
        actor=str(event.get("actor", "system")),
        resource=str(event.get("resource", "")),
        summary=str(event.get("message", event.get("action", ""))),
        severity=event.get("severity", "info"),
        timestamp=event.get("timestamp", time.time()),
        tags=event.get("tags", []),
    )

    async with _lock:
        _queue.append(trigger)
        if len(_queue) >= BATCH_SIZE:
            await _flush()


async def _flush() -> None:
    """Send queued triggers to The Library (Outline). Must hold _lock."""
    if not _queue:
        return

    batch = _queue.copy()
    _queue.clear()

    try:
        import httpx  # type: ignore[import-not-found]

        payload = {"triggers": [asdict(t) for t in batch]}
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{LIBRARY_URL}/kb/ingest", json=payload)
            if resp.status_code >= 400:
                logger.warning("Library pipeline HTTP %s — %s", resp.status_code, resp.text[:200])
            else:
                logger.debug("Library pipeline flushed %d triggers", len(batch))
    except Exception as exc:  # noqa: BLE001
        # Library unavailable — silently drop (observability must not cascade-fail)
        logger.debug("Library pipeline unavailable: %s", exc)


async def flush_loop() -> None:
    """Background coroutine: flush the queue every FLUSH_INTERVAL_SEC seconds."""
    while True:
        await asyncio.sleep(FLUSH_INTERVAL_SEC)
        async with _lock:
            await _flush()


def start_pipeline(app: Any = None) -> None:
    """
    Register the flush loop on app startup (FastAPI lifespan compatible).
    Call this from api.py / api/core.py startup.
    """
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(flush_loop())
        logger.info("Observatory→Library pipeline started (batch=%d, interval=%ss)",
                    BATCH_SIZE, FLUSH_INTERVAL_SEC)
    except RuntimeError:
        logger.warning("No running event loop — Library pipeline deferred")
