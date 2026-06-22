"""
Tests for infinity-ai service layer (service.py).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

# ---------------------------------------------------------------------------
# LRU Cache
# ---------------------------------------------------------------------------


def test_lru_cache_basic():
    from service import LRUCache

    cache = LRUCache(max_size=3)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)
    assert cache.get("a") == 1
    assert cache.get("b") == 2
    assert cache.get("missing") is None


def test_lru_cache_evicts_oldest():
    from service import LRUCache

    cache = LRUCache(max_size=2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)  # should evict "a"
    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.get("c") == 3


def test_lru_cache_clear():
    from service import LRUCache

    cache = LRUCache(max_size=10)
    cache.put("x", 99)
    cache.clear()
    assert cache.get("x") is None


# ---------------------------------------------------------------------------
# OfflineClient
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_offline_client_default():
    from models import ChatMessage
    from service import OfflineClient

    client = OfflineClient()
    result = await client.complete(
        "model", [ChatMessage(role="user", content="what is this")], 100, 0.7
    )
    assert "offline" in result.get("content", "").lower() or result.get("content")


@pytest.mark.asyncio
async def test_offline_client_greeting():
    from models import ChatMessage
    from service import OfflineClient

    client = OfflineClient()
    result = await client.complete(
        "model", [ChatMessage(role="user", content="hello there")], 100, 0.7
    )
    assert "offline" in result["content"].lower()


# ---------------------------------------------------------------------------
# AIGatewayRouter — caching
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_router_uses_lru_cache(tmp_db):
    from models import ChatCompletionChoice, ChatCompletionResponse, ChatMessage
    from service import AIGatewayRouter

    router = AIGatewayRouter(tmp_db)

    # Pre-populate the LRU cache with a fake response
    fake = ChatCompletionResponse(
        model="llama3.2",
        choices=[
            ChatCompletionChoice(
                message=ChatMessage(role="assistant", content="cached"),
                finish_reason="stop",
            )
        ],
        provider="ollama",
    )
    import hashlib

    # msgs unused — hash key is built from raw string below
    raw = "default:llama3.2:user:test prompt:512:0.7"
    key = hashlib.sha256(raw.encode()).hexdigest()[:32]
    router.cache.put(key, fake)

    from models import ChatCompletionRequest

    req = ChatCompletionRequest(
        model="llama3.2",
        messages=[ChatMessage(role="user", content="test prompt")],
        max_tokens=512,
        temperature=0.7,
    )
    resp = await router.route(req)
    assert resp.provider == "cache"


# ---------------------------------------------------------------------------
# AIGatewayRouter — budget enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_router_rejects_over_budget(tmp_db):
    from fastapi import HTTPException
    from service import AIGatewayRouter

    router = AIGatewayRouter(tmp_db)

    # Set budget to 0
    from datetime import datetime, timezone

    from models import TokenBudget

    budget = TokenBudget(
        tenant_id="broke", daily_limit=0, used_today=0, last_reset=datetime.now(timezone.utc)
    )
    tmp_db._save_budget(budget)

    from models import ChatCompletionRequest, ChatMessage

    req = ChatCompletionRequest(
        model="llama3.2",
        messages=[ChatMessage(role="user", content="hi")],
        max_tokens=1024,
        tenant_id="broke",
    )
    with pytest.raises(HTTPException) as exc_info:
        await router.route(req)
    assert exc_info.value.status_code == 429


# ---------------------------------------------------------------------------
# AIGatewayRouter — offline fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_router_falls_back_to_offline(tmp_db):
    from service import AIGatewayRouter

    router = AIGatewayRouter(tmp_db)

    # Make all real providers return None
    for _, client in router.providers:
        if hasattr(client, "complete") and not isinstance(
            client.__class__.__name__ == "OfflineClient", bool
        ):
            client.complete = AsyncMock(return_value=None)

    # Patch all except offline to return None, offline to return its normal response
    for name, client in router.providers:
        if name.value != "offline":
            client.complete = AsyncMock(return_value=None)

    from models import ChatCompletionRequest, ChatMessage

    req = ChatCompletionRequest(
        model="llama3.2",
        messages=[ChatMessage(role="user", content="hello")],
        max_tokens=64,
    )
    resp = await router.route(req)
    assert resp.provider == "offline"
    assert resp.choices[0].message.content != ""
