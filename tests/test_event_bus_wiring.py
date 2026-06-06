"""
TR3-005: Event Bus Wiring — unit tests.

Verifies that:
- wire_platform_events() registers the expected callbacks
- Library article events reach the EventBus
- Observatory bridge maps AuditEvent categories to PlatformEventTypes
- Sentinel forward handler constructs correct channel mapping
- get_event_bus() returns a stable singleton
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.event_bus import EventBus, PlatformEventType, get_event_bus
from src.event_bus.types import EventEnvelope, EventMetadata
from src.event_bus.wiring import (
    _audit_category_to_event_type,
    _event_type_to_sentinel_channel,
    wire_platform_events,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _envelope(event_type: str, data: dict | None = None) -> EventEnvelope:
    import uuid

    return EventEnvelope(
        event_type=event_type,
        data=data or {},
        metadata=EventMetadata(event_id=str(uuid.uuid4()), source="test"),
    )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


def test_get_event_bus_singleton():
    b1 = get_event_bus()
    b2 = get_event_bus()
    assert b1 is b2
    assert isinstance(b1, EventBus)


# ---------------------------------------------------------------------------
# wire_platform_events registers callbacks
# ---------------------------------------------------------------------------


def test_wire_platform_events_registers_callbacks():
    bus = EventBus()
    # Patch attach_observatory_bridge so we don't spin up an async task
    with patch("src.event_bus.wiring.attach_observatory_bridge"):
        wire_platform_events(bus)

    # Verify patterns are registered (bus._callbacks is a dict keyed by pattern)
    registered_patterns = set(bus._callbacks.keys())
    assert "ai.*" in registered_patterns
    assert PlatformEventType.AI_INFERENCE_COMPLETE in registered_patterns
    assert "workflow.*" in registered_patterns
    assert "article.created" in registered_patterns
    assert "article.updated" in registered_patterns
    assert "article.deleted" in registered_patterns
    assert "**" in registered_patterns


# ---------------------------------------------------------------------------
# Sentinel channel mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "event_type,expected_channel",
    [
        ("ai.inference.complete", "ai"),
        ("ai.inference.failed", "ai"),
        ("auth.token.issued", "auth"),
        ("user.login", "users"),
        ("workflow.completed", "workflows"),
        ("service.health.changed", "platform"),
        ("secret.stored", "security"),
        ("order.created", "financial"),
        ("payment.received", "financial"),
        ("notification.sent", "platform"),
    ],
)
def test_sentinel_channel_mapping(event_type, expected_channel):
    assert _event_type_to_sentinel_channel(event_type) == expected_channel


# ---------------------------------------------------------------------------
# Observatory → EventBus mapping
# ---------------------------------------------------------------------------


def _make_audit_event(category_name: str, event_type: str):
    """
    Build a mock audit event using the same EventCategory enum that
    _audit_category_to_event_type imports.  We avoid src/observability/__init__
    (which drags in structlog) by patching the import path used inside wiring.py.
    """
    from src.event_bus.wiring import _audit_category_to_event_type  # noqa: F401 — ensure module loaded

    # Import observatory.py directly (avoids the __init__ structlog chain)
    import importlib.util
    import pathlib
    import sys

    mod_name = "_observatory_for_test"
    if mod_name not in sys.modules:
        # Stub out structlog before importing the metrics module
        sys.modules.setdefault("structlog", MagicMock())
        spec = importlib.util.spec_from_file_location(
            mod_name,
            pathlib.Path(__file__).parent.parent / "src/observability/observatory.py",
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    else:
        mod = sys.modules[mod_name]

    # Patch the wiring module to use *our* EventCategory so identity checks pass
    import src.event_bus.wiring as _wiring

    _wiring._observatory_module = mod  # store for reference (unused, just safety)

    # We need to patch the EventCategory imported inside _audit_category_to_event_type.
    # The function does:  from src.observability.observatory import EventCategory
    # We replace the cached module so the import resolves to our loaded copy.
    sys.modules.setdefault("src.observability.observatory", mod)

    return mod.AuditEvent(
        event_type=event_type,
        category=mod.EventCategory[category_name],
    )


@pytest.mark.parametrize(
    "cat,et,expected",
    [
        ("AI", "ai.inference.complete-done", PlatformEventType.AI_INFERENCE_COMPLETE),
        ("AI", "ai.inference.failed", PlatformEventType.AI_INFERENCE_FAILED),
        ("AI", "ai.inference.request", PlatformEventType.AI_INFERENCE_REQUEST),
        ("WORKFLOW", "workflow.completed", PlatformEventType.WORKFLOW_COMPLETED),
        ("WORKFLOW", "workflow.failed", PlatformEventType.WORKFLOW_FAILED),
        ("WORKFLOW", "workflow.started", PlatformEventType.WORKFLOW_STARTED),
        ("AUTH", "user.login", PlatformEventType.USER_LOGIN),
        ("AUTH", "user.logout", PlatformEventType.USER_LOGOUT),
        ("AUTH", "auth.token.issue", PlatformEventType.AUTH_TOKEN_ISSUED),
        ("AUTH", "auth.token.revoke", PlatformEventType.AUTH_TOKEN_REVOKED),
        ("SECRETS", "secret.stored", PlatformEventType.SECRET_STORED),
        ("SECRETS", "secret.retrieved", PlatformEventType.SECRET_RETRIEVED),
        ("SECRETS", "secret.rotated", PlatformEventType.SECRET_ROTATED),
        ("SECRETS", "secret.deleted", PlatformEventType.SECRET_DELETED),
        # Non-wired categories return None
        ("SYSTEM", "system.startup", None),
        ("DATA", "data.created", None),
    ],
)
def test_audit_category_to_event_type(cat, et, expected):
    audit_event = _make_audit_event(cat, et)
    result = _audit_category_to_event_type(audit_event)
    assert result == expected


# ---------------------------------------------------------------------------
# Library emits EventBus article events
# ---------------------------------------------------------------------------


def test_library_emits_article_created_event():
    """Library.create() should call bus.emit_async with 'article.created'."""
    from src.library.knowledge_base import Library

    emitted: list[dict] = []

    fake_bus = MagicMock()
    fake_bus.emit_async = lambda event_type, data, source: emitted.append(
        {"event_type": event_type, "data": data}
    )

    lib = Library()
    with patch("src.event_bus.get_event_bus", return_value=fake_bus):
        lib.create(title="Test", body="body", tags=["test"], author="tester")

    article_events = [e for e in emitted if "article" in str(e["event_type"])]
    assert len(article_events) >= 1
    assert article_events[0]["data"]["title"] == "Test"


def test_library_emits_article_deleted_event():
    from src.library.knowledge_base import Library

    emitted: list[dict] = []

    fake_bus = MagicMock()
    fake_bus.emit_async = lambda event_type, data, source: emitted.append(
        {"event_type": str(event_type)}
    )

    lib = Library()
    with patch("src.event_bus.get_event_bus", return_value=fake_bus):
        art = lib.create(title="Doomed", body="x")
        emitted.clear()
        lib.delete(art.id)

    assert any("deleted" in e["event_type"] for e in emitted)


# ---------------------------------------------------------------------------
# Library AI handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_library_on_ai_event_creates_article():
    from src.event_bus.wiring import _library_on_ai_event
    from src.library.knowledge_base import get_library

    lib = get_library()
    initial_count = len(lib._articles)

    env = _envelope(
        PlatformEventType.AI_INFERENCE_COMPLETE,
        {
            "prompt": "What is quantum?",
            "response": "A quantum is…",
            "model": "qnc",
            "provider": "think-tank",
        },
    )
    await _library_on_ai_event(env)

    assert len(lib._articles) > initial_count


@pytest.mark.asyncio
async def test_library_on_ai_event_skips_empty_response():
    from src.event_bus.wiring import _library_on_ai_event
    from src.library.knowledge_base import get_library

    lib = get_library()
    before = len(lib._articles)
    env = _envelope(PlatformEventType.AI_INFERENCE_COMPLETE, {"prompt": "hi", "response": ""})
    await _library_on_ai_event(env)
    # No new article created because response is empty
    assert len(lib._articles) == before


# ---------------------------------------------------------------------------
# Workflow handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_library_on_workflow_completed():
    from src.event_bus.wiring import _library_on_workflow_event
    from src.library.knowledge_base import get_library

    lib = get_library()
    before = len(lib._articles)

    env = _envelope(
        PlatformEventType.WORKFLOW_COMPLETED,
        {"workflow_id": "wf-123", "name": "Test Pipeline", "step_count": 5, "duration_ms": 300},
    )
    await _library_on_workflow_event(env)
    assert len(lib._articles) > before


@pytest.mark.asyncio
async def test_library_on_workflow_other_events_skipped():
    """Only WORKFLOW_COMPLETED creates an article; WORKFLOW_STARTED does not."""
    from src.event_bus.wiring import _library_on_workflow_event
    from src.library.knowledge_base import get_library

    lib = get_library()
    before = len(lib._articles)
    env = _envelope(PlatformEventType.WORKFLOW_STARTED, {"workflow_id": "wf-99"})
    await _library_on_workflow_event(env)
    assert len(lib._articles) == before


# ---------------------------------------------------------------------------
# Sentinel forward handler (mocked HTTP)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sentinel_forward_posts_to_correct_url():
    from src.event_bus.wiring import _sentinel_forward

    mock_response = MagicMock()
    mock_response.status_code = 200

    posted_payloads: list[dict] = []

    async def mock_post(url, json=None, **kwargs):
        posted_payloads.append({"url": url, "payload": json})
        return mock_response

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = mock_post

    env = _envelope("ai.inference.complete", {"prompt": "test", "response": "ok"})

    with patch.dict("os.environ", {"SENTINEL_URL": "http://sentinel:8041"}):
        # httpx may not be installed in all environments — mock at module level
        import sys

        fake_httpx = MagicMock()
        fake_httpx.AsyncClient = MagicMock(return_value=mock_client)
        with patch.dict(sys.modules, {"httpx": fake_httpx}):
            await _sentinel_forward(env)

    assert len(posted_payloads) == 1
    assert "sentinel:8041" in posted_payloads[0]["url"]
    assert posted_payloads[0]["payload"]["channel"] == "ai"
