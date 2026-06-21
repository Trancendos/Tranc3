"""
test_service.py — Unit tests for gateway-service business logic.
Tests circuit breaker, cache, RBAC/ABAC helpers, and upstream fetch.
These tests import directly from service.py and do not require a
running FastAPI app or real Dimensional runtime.
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------


def test_circuit_breaker_starts_closed():
    from service import _circuit_breaker, init_circuit_breakers

    init_circuit_breakers()
    for state in _circuit_breaker.values():
        assert state["state"] == "closed"
        assert state["failures"] == 0


def test_record_failure_opens_circuit():
    from service import _circuit_breaker, _record_failure, init_circuit_breakers

    init_circuit_breakers()
    name = "vault"
    _record_failure(name)
    _record_failure(name)
    assert _circuit_breaker[name]["state"] == "closed"
    _record_failure(name)  # 3rd failure → open
    assert _circuit_breaker[name]["state"] == "open"


def test_record_success_resets_circuit():
    from service import _circuit_breaker, _record_failure, _record_success, init_circuit_breakers

    init_circuit_breakers()
    for _ in range(3):
        _record_failure("topology")
    assert _circuit_breaker["topology"]["state"] == "open"

    _record_success("topology")
    assert _circuit_breaker["topology"]["state"] == "closed"
    assert _circuit_breaker["topology"]["failures"] == 0


def test_is_circuit_open_half_opens_after_timeout():
    from service import _circuit_breaker, _is_circuit_open, init_circuit_breakers

    init_circuit_breakers()
    name = "ledger"
    _circuit_breaker[name]["state"] = "open"
    _circuit_breaker[name]["last_failure"] = time.time() - 31  # > 30 s ago

    result = _is_circuit_open(name)
    assert result is False
    assert _circuit_breaker[name]["state"] == "half_open"


def test_is_circuit_open_true_when_recent_failure():
    from service import _circuit_breaker, _is_circuit_open, init_circuit_breakers

    init_circuit_breakers()
    name = "model_router"
    _circuit_breaker[name]["state"] = "open"
    _circuit_breaker[name]["last_failure"] = time.time()

    assert _is_circuit_open(name) is True


# ---------------------------------------------------------------------------
# Cache Layer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_stores_result():
    from service import _cache, get_cached_or_fetch

    _cache.clear()
    fetcher = AsyncMock(return_value={"data": "fresh"})
    result = await get_cached_or_fetch("test_key", fetcher, ttl=60)
    assert result == {"data": "fresh"}
    assert fetcher.call_count == 1

    # Second call must use cache, not call fetcher again
    result2 = await get_cached_or_fetch("test_key", fetcher, ttl=60)
    assert result2 == {"data": "fresh"}
    assert fetcher.call_count == 1


@pytest.mark.asyncio
async def test_cache_expires():
    from service import _cache, get_cached_or_fetch

    _cache.clear()
    fetcher = AsyncMock(side_effect=[{"v": 1}, {"v": 2}])
    await get_cached_or_fetch("exp_key", fetcher, ttl=0.001)
    await asyncio.sleep(0.02)
    result = await get_cached_or_fetch("exp_key", fetcher, ttl=0.001)
    assert result == {"v": 2}
    assert fetcher.call_count == 2


def test_evict_expired_cache():
    from service import _cache, evict_expired_cache

    _cache.clear()
    _cache["old"] = (time.time() - 100, "stale")
    _cache["new"] = (time.time(), "fresh")
    removed = evict_expired_cache()
    assert removed == 1
    assert "old" not in _cache
    assert "new" in _cache


# ---------------------------------------------------------------------------
# fetch_worker — circuit breaker short-circuit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_worker_returns_none_when_open():
    from service import _circuit_breaker, fetch_worker, init_circuit_breakers

    init_circuit_breakers()
    name = "workflow"
    _circuit_breaker[name]["state"] = "open"
    _circuit_breaker[name]["last_failure"] = time.time()

    result = await fetch_worker(name, "/stats")
    assert result is None


@pytest.mark.asyncio
async def test_fetch_worker_success():
    from service import fetch_worker, init_circuit_breakers

    init_circuit_breakers()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"ok": True}

    with patch("service.httpx.AsyncClient") as mock_cls:
        instance = mock_cls.return_value.__aenter__.return_value
        instance.get = AsyncMock(return_value=mock_response)
        result = await fetch_worker("vault", "/stats")

    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_fetch_worker_records_failure_on_error():
    import httpx
    from service import _circuit_breaker, fetch_worker, init_circuit_breakers

    init_circuit_breakers()

    with patch("service.httpx.AsyncClient") as mock_cls:
        instance = mock_cls.return_value.__aenter__.return_value
        instance.get = AsyncMock(side_effect=httpx.ConnectError("down"))
        result = await fetch_worker("benchmark", "/stats")

    assert result is None
    assert _circuit_breaker["benchmark"]["failures"] >= 1


# ---------------------------------------------------------------------------
# fetch_worker_list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_worker_list_from_list():
    from service import fetch_worker_list

    with patch("service.fetch_worker", new_callable=AsyncMock, return_value=[1, 2, 3]):
        result = await fetch_worker_list("deepagents", "/agents")
    assert result == [1, 2, 3]


@pytest.mark.asyncio
async def test_fetch_worker_list_from_items_key():
    from service import fetch_worker_list

    with patch("service.fetch_worker", new_callable=AsyncMock, return_value={"items": ["x"]}):
        result = await fetch_worker_list("deepagents", "/agents")
    assert result == ["x"]


@pytest.mark.asyncio
async def test_fetch_worker_list_from_nested_list():
    from service import fetch_worker_list

    with patch(
        "service.fetch_worker",
        new_callable=AsyncMock,
        return_value={"agents": [{"id": "a1"}], "total": 1},
    ):
        result = await fetch_worker_list("deepagents", "/agents")
    assert result == [{"id": "a1"}]


@pytest.mark.asyncio
async def test_fetch_worker_list_returns_empty_on_none():
    from service import fetch_worker_list

    with patch("service.fetch_worker", new_callable=AsyncMock, return_value=None):
        result = await fetch_worker_list("deepagents", "/agents")
    assert result == []


# ---------------------------------------------------------------------------
# get_user
# ---------------------------------------------------------------------------


def test_get_user_returns_anonymous_when_no_attribute():
    from service import get_user

    request = MagicMock(spec=[])  # no .state
    user = get_user(request)
    assert user["sub"] == "anonymous"


def test_get_user_returns_state_user():
    from service import get_user

    request = MagicMock()
    request.state.user = {"sub": "alice", "role": "admin", "tier": "divine"}
    user = get_user(request)
    assert user["sub"] == "alice"


# ---------------------------------------------------------------------------
# tier_name_to_value
# ---------------------------------------------------------------------------


def test_tier_name_to_value_fallback():
    from service import tier_name_to_value

    assert tier_name_to_value("NONEXISTENT_TIER") == 0


# ---------------------------------------------------------------------------
# get_circuit_breaker_states
# ---------------------------------------------------------------------------


def test_get_circuit_breaker_states():
    from service import get_circuit_breaker_states, init_circuit_breakers

    init_circuit_breakers()
    states = get_circuit_breaker_states()
    assert isinstance(states, dict)
    for v in states.values():
        assert isinstance(v, str)
