"""
Event Bus Wiring — TR3-005
==========================
Connects Observatory telemetry → EventBus → Library/Think Tank/Search indexing.
Provides the Sentinel Station ↔ EventBus bridge.

Call `wire_platform_events(bus)` once at application startup (after the EventBus
is constructed) to activate all subscriptions.

Architecture:
    Observatory.record()
        ↓ (via _notify_subscribers / async listener task)
    EventBus.emit(event_type, data)
        ↓ subscriptions:
        ├── "ai.*"        → Library: auto-create Knowledge-Base article
        ├── "ai.*"        → Think Tank indexer: store inference result
        ├── "article.*"   → Search Service: index / deindex document
        ├── "workflow.*"  → Library: record workflow KB entry
        └── "**"          → Sentinel Station: cross-gateway broadcast

All handlers are fire-and-forget (errors are logged, never raised).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from src.event_bus.types import EventEnvelope, PlatformEventType

if TYPE_CHECKING:
    from src.event_bus.bus import EventBus

logger = logging.getLogger("tranc3.event_bus.wiring")

# ---------------------------------------------------------------------------
# Handler: Library — AI inference → Knowledge Base article
# ---------------------------------------------------------------------------

async def _library_on_ai_event(envelope: EventEnvelope) -> None:
    """On AI_INFERENCE_COMPLETE, auto-create a Library article summarising the result."""
    try:
        from src.library.knowledge_base import get_library  # noqa: PLC0415

        lib = get_library()
        data: dict[str, Any] = envelope.data or {}
        prompt = data.get("prompt", "")[:120]
        response_text = data.get("response", "")[:500]
        model = data.get("model", "unknown")
        provider = data.get("provider", "unknown")

        if not response_text:
            return

        title = f"AI Inference: {prompt[:60]}" if prompt else f"AI inference via {model}"
        body = (
            f"**Model**: {model}  |  **Provider**: {provider}\n\n"
            f"**Prompt**\n{prompt}\n\n"
            f"**Response**\n{response_text}"
        )
        lib.create(
            title=title,
            body=body,
            tags=["ai", "inference", model, provider],
            author="system:luminous",
            source="observatory",
        )
    except Exception as exc:  # nosec B110
        logger.debug("library_on_ai_event: %s", exc)


# ---------------------------------------------------------------------------
# Handler: Library — Workflow completed → KB entry
# ---------------------------------------------------------------------------

async def _library_on_workflow_event(envelope: EventEnvelope) -> None:
    """On WORKFLOW_COMPLETED, auto-create a Library article documenting the run."""
    try:
        from src.library.knowledge_base import get_library  # noqa: PLC0415

        if envelope.event_type != PlatformEventType.WORKFLOW_COMPLETED:
            return

        lib = get_library()
        data: dict[str, Any] = envelope.data or {}
        wf_id = data.get("workflow_id", "unknown")
        wf_name = data.get("name", wf_id)
        duration_ms = data.get("duration_ms", 0)
        step_count = data.get("step_count", 0)

        lib.create(
            title=f"Workflow run: {wf_name}",
            body=(
                f"**Workflow ID**: {wf_id}\n"
                f"**Steps**: {step_count}\n"
                f"**Duration**: {duration_ms} ms\n\n"
                f"Data: {str(data)[:400]}"
            ),
            tags=["workflow", "digital-grid", wf_id],
            author="system:digital-grid",
            source="observatory",
        )
    except Exception as exc:  # nosec B110
        logger.debug("library_on_workflow_event: %s", exc)


# ---------------------------------------------------------------------------
# Handler: Think Tank — AI inference → index result
# ---------------------------------------------------------------------------

async def _thinktank_on_ai_event(envelope: EventEnvelope) -> None:
    """
    Store AI inference results in the Think Tank research index (search-service).

    The search-service exposes PUT /indices/{index}/documents/{id}.
    We talk to it over HTTP if SEARCH_SERVICE_URL is set; otherwise skip silently.
    """
    try:
        import os  # noqa: PLC0415

        import httpx  # noqa: PLC0415

        base_url = os.environ.get("SEARCH_SERVICE_URL", "http://localhost:8017")
        data: dict[str, Any] = envelope.data or {}
        doc_id = envelope.metadata.event_id
        prompt = data.get("prompt", "")
        response_text = data.get("response", "")
        if not response_text:
            return

        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.put(
                f"{base_url}/indices/think-tank/documents/{doc_id}",
                json={
                    "title": prompt[:120] or "AI inference result",
                    "body": response_text[:2000],
                    "metadata": {
                        "model": data.get("model"),
                        "provider": data.get("provider"),
                        "event_id": doc_id,
                    },
                },
            )
    except Exception as exc:  # nosec B110
        logger.debug("thinktank_on_ai_event: %s", exc)


# ---------------------------------------------------------------------------
# Handler: Search Service — article created/updated → index document
# ---------------------------------------------------------------------------

async def _search_on_article_created(envelope: EventEnvelope) -> None:
    """Forward Library article.created / article.updated to search-service for FTS indexing."""
    try:
        import os  # noqa: PLC0415

        import httpx  # noqa: PLC0415

        base_url = os.environ.get("SEARCH_SERVICE_URL", "http://localhost:8017")
        data: dict[str, Any] = envelope.data or {}
        article_id = data.get("id")
        title = data.get("title", "")
        body = data.get("body", "")
        if not article_id:
            return

        async with httpx.AsyncClient(timeout=5.0) as client:
            # Ensure index exists first (idempotent)
            await client.post(
                f"{base_url}/indices",
                json={"name": "library", "description": "The Library knowledge base articles"},
            )
            await client.put(
                f"{base_url}/indices/library/documents/{article_id}",
                json={
                    "title": title,
                    "body": body[:4000],
                    "metadata": {
                        "source": data.get("source"),
                        "tags": data.get("tags", []),
                        "author": data.get("author"),
                    },
                },
            )
    except Exception as exc:  # nosec B110
        logger.debug("search_on_article_created: %s", exc)


async def _search_on_article_deleted(envelope: EventEnvelope) -> None:
    """Remove deleted Library articles from search-service index."""
    try:
        import os  # noqa: PLC0415

        import httpx  # noqa: PLC0415

        base_url = os.environ.get("SEARCH_SERVICE_URL", "http://localhost:8017")
        data: dict[str, Any] = envelope.data or {}
        article_id = data.get("id")
        if not article_id:
            return

        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.delete(f"{base_url}/indices/library/documents/{article_id}")
    except Exception as exc:  # nosec B110
        logger.debug("search_on_article_deleted: %s", exc)


# ---------------------------------------------------------------------------
# Handler: Sentinel Station — forward every event via REST
# ---------------------------------------------------------------------------

async def _sentinel_forward(envelope: EventEnvelope) -> None:
    """
    Broadcast every platform event to Sentinel Station for cross-gateway distribution.

    Sentinel exposes POST /api/events/publish (port 8041).
    If SENTINEL_URL is unset or Sentinel is unreachable the broadcast is skipped.
    """
    try:
        import os  # noqa: PLC0415

        import httpx  # noqa: PLC0415

        base_url = os.environ.get("SENTINEL_URL", "http://localhost:8041")
        payload = {
            "channel": _event_type_to_sentinel_channel(str(envelope.event_type)),
            "event_type": str(envelope.event_type),
            "source": envelope.metadata.source or "tranc3-backend",
            "payload": envelope.data or {},
            "correlation_id": envelope.metadata.correlation_id,
        }
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.post(f"{base_url}/api/events/publish", json=payload)
    except Exception as exc:  # nosec B110
        logger.debug("sentinel_forward: %s", exc)


def _event_type_to_sentinel_channel(event_type: str) -> str:
    """Map an EventBus event type string to the closest Sentinel channel name."""
    if event_type.startswith("ai."):
        return "ai"
    if event_type.startswith("auth."):
        return "auth"
    if event_type.startswith("user."):
        return "users"
    if event_type.startswith("workflow."):
        return "workflows"
    if event_type.startswith("service."):
        return "platform"
    if event_type.startswith("secret."):
        return "security"
    if event_type.startswith("order.") or event_type.startswith("payment."):
        return "financial"
    return "platform"


# ---------------------------------------------------------------------------
# Observatory → EventBus bridge
# ---------------------------------------------------------------------------

def attach_observatory_bridge(bus: "EventBus") -> None:
    """
    Subscribe an asyncio.Queue to Observatory and forward each AuditEvent
    to the EventBus as a typed platform event.

    This is started as a background asyncio task at application startup.
    """
    from src.observability.observatory import get_observatory  # noqa: PLC0415

    obs = get_observatory()
    queue = obs.subscribe(maxsize=2000)

    async def _forward_loop() -> None:
        while True:
            try:
                audit_event = await queue.get()
                # Map Observatory category → EventBus event type
                event_type = _audit_category_to_event_type(audit_event)
                if event_type is None:
                    continue
                await bus.emit(
                    event_type=event_type,
                    data={
                        "observatory_id": audit_event.id,
                        "audit_event_type": audit_event.event_type,
                        "actor": audit_event.actor,
                        "target": audit_event.target,
                        "service": audit_event.service,
                        "outcome": audit_event.outcome,
                        "severity": audit_event.severity.value,
                        "metadata": audit_event.metadata,
                        # Carry AI fields if present in metadata
                        "prompt": audit_event.metadata.get("prompt", ""),
                        "response": audit_event.metadata.get("response", ""),
                        "model": audit_event.metadata.get("model", ""),
                        "provider": audit_event.metadata.get("provider", ""),
                    },
                    source="observatory",
                    tenant_id=audit_event.metadata.get("tenant_id"),
                )
            except asyncio.CancelledError:
                obs.unsubscribe(queue)
                return
            except Exception as exc:  # nosec B110
                logger.debug("observatory_bridge: %s", exc)

    asyncio.ensure_future(_forward_loop())
    logger.info("event_bus.wiring: Observatory → EventBus bridge active")


def _audit_category_to_event_type(audit_event: Any) -> "str | None":
    """Map an AuditEvent to the closest PlatformEventType string, or None to skip."""
    from src.observability.observatory import EventCategory  # noqa: PLC0415

    cat = audit_event.category
    et = audit_event.event_type  # e.g. "user.login", "secret.retrieve"

    if cat == EventCategory.AI:
        if "complete" in et or "done" in et or "response" in et:
            return PlatformEventType.AI_INFERENCE_COMPLETE
        if "fail" in et or "error" in et:
            return PlatformEventType.AI_INFERENCE_FAILED
        return PlatformEventType.AI_INFERENCE_REQUEST

    if cat == EventCategory.WORKFLOW:
        if "complete" in et or "done" in et or "finish" in et:
            return PlatformEventType.WORKFLOW_COMPLETED
        if "fail" in et or "error" in et:
            return PlatformEventType.WORKFLOW_FAILED
        if "start" in et or "begin" in et:
            return PlatformEventType.WORKFLOW_STARTED
        return PlatformEventType.WORKFLOW_STEP_COMPLETE

    if cat == EventCategory.AUTH:
        if "login" in et or "sign_in" in et:
            return PlatformEventType.USER_LOGIN
        if "logout" in et or "sign_out" in et:
            return PlatformEventType.USER_LOGOUT
        if "token" in et and "issue" in et:
            return PlatformEventType.AUTH_TOKEN_ISSUED
        if "token" in et and "revok" in et:
            return PlatformEventType.AUTH_TOKEN_REVOKED
        return None

    if cat == EventCategory.SECRETS:
        if "store" in et or "creat" in et:
            return PlatformEventType.SECRET_STORED
        if "retriev" in et or "get" in et:
            return PlatformEventType.SECRET_RETRIEVED
        if "rotat" in et:
            return PlatformEventType.SECRET_ROTATED
        if "delet" in et:
            return PlatformEventType.SECRET_DELETED
        return None

    # Skip DEBUG/INFO system and data events to avoid noise
    return None


# ---------------------------------------------------------------------------
# Public wiring entry point
# ---------------------------------------------------------------------------

def wire_platform_events(bus: "EventBus") -> None:
    """
    Register all intra-platform EventBus subscriptions and start the
    Observatory → EventBus bridge task.

    Call once at application startup, e.g. inside the FastAPI lifespan.
    """
    # AI inference → Library KB article
    bus.on("ai.*", _library_on_ai_event)

    # AI inference → Think Tank (search-service index)
    bus.on(PlatformEventType.AI_INFERENCE_COMPLETE, _thinktank_on_ai_event)

    # Workflow completed → Library KB entry
    bus.on("workflow.*", _library_on_workflow_event)

    # Article created/updated → Search Service
    bus.on("article.created", _search_on_article_created)
    bus.on("article.updated", _search_on_article_created)
    bus.on("article.deleted", _search_on_article_deleted)

    # All events → Sentinel Station cross-gateway broadcast
    bus.on("**", _sentinel_forward)

    # Observatory audit events → EventBus bridge (async background task)
    try:
        attach_observatory_bridge(bus)
    except Exception as exc:
        logger.warning("event_bus.wiring: observatory bridge skipped: %s", exc)

    logger.info(
        "event_bus.wiring: platform event subscriptions active "
        "(library-ai, library-workflow, thinktank-ai, search-articles, sentinel-broadcast)"
    )
