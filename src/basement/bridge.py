# src/basement/bridge.py
# Best-effort fire-and-forget bridge from Observatory's audit writes to
# workers/basement/'s durable SQLite+FTS5 archive.
#
# Fail-open by design (explicit product decision, 2026-08-08): the in-process
# Basement singleton (src/basement/archive.py) is in-memory and lost on
# restart, but it remains the source of truth for anything read back within
# this process's lifetime (routes.py's /basement/* endpoints, RAG search).
# This bridge additionally persists SECURITY/CRITICAL/retention-tagged/
# legal-hold events to the worker's durable store so they survive a restart
# — but if the worker is unreachable, the event is only missing from durable
# archival this one time, never dropped from the in-process archive, and the
# action that triggered the audit write is never blocked or delayed because
# of it. Mirrors src/nexus/hub.py's _forward_to_ws_hub() pattern: capped
# in-flight concurrency reserved before scheduling (not inside the task body,
# so a burst can't accumulate unbounded tasks/sockets), fire-and-forget
# asyncio.create_task(), never raises, never blocks the caller.

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from Dimensional.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)

_BASEMENT_URL = os.environ.get("BASEMENT_URL", "http://basement:8068")
_BASEMENT_INTERNAL_SECRET = os.environ.get("BASEMENT_INTERNAL_SECRET", "")

_FORWARD_CONCURRENCY = int(os.environ.get("BASEMENT_FORWARD_CONCURRENCY", "10"))
_forward_inflight = 0


def forward_event(event: Any) -> None:
    """Schedule a fire-and-forget durable-archive write for an AuditEvent.

    No-op if there's no running event loop (e.g. a sync test context) or if
    the in-flight cap is already reached — matches the fail-open contract:
    a skipped forward is silent, not an error.
    """
    global _forward_inflight
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    if _forward_inflight >= _FORWARD_CONCURRENCY:
        return
    _forward_inflight += 1
    loop.create_task(_post_archive(event))


async def _post_archive(event: Any) -> None:
    global _forward_inflight
    try:
        import httpx

        headers = (
            {"X-Internal-Secret": _BASEMENT_INTERNAL_SECRET} if _BASEMENT_INTERNAL_SECRET else {}
        )
        category = getattr(event, "category", None)
        severity = getattr(event, "severity", None)
        payload = {
            "source": "observatory",
            "ref_id": event.id,
            "actor": event.actor or "unknown",
            "action": event.event_type,
            "resource": event.target,
            "details": {
                "service": event.service,
                "category": getattr(category, "value", str(category)),
                "severity": getattr(severity, "value", str(severity)),
                "retention_class": event.retention_class,
                "legal_hold": event.legal_hold,
                **(event.metadata or {}),
            },
            "outcome": event.outcome,
            "original_ts": event.timestamp,
        }
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.post(
                f"{_BASEMENT_URL}/archive",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
    except Exception as exc:
        # sanitize_for_log() strips CR/LF, but CodeQL's py/log-injection
        # query doesn't trace that across the module boundary — inline
        # .replace() too so the barrier is visible to it directly (same
        # pattern as src/nexus/hub.py._post_broadcast).
        safe_type = str(getattr(event, "event_type", "")).replace("\r", "").replace("\n", "")
        logger.debug(
            "basement: durable archive forward skipped (event_type=%s): %s",
            safe_type,
            sanitize_for_log(exc),
        )  # codeql[py/cleartext-logging]
    finally:
        _forward_inflight -= 1
