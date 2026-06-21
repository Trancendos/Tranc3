"""
Tests for infinity-ai FastAPI routes (router.py).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


def test_health_healthy(test_app, gateway):
    gateway.ollama.health_check = AsyncMock(return_value=True)
    resp = test_app.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["service"] == "infinity-ai"
    assert "ollama" in body["providers"]


def test_health_degraded(test_app, gateway):
    gateway.ollama.health_check = AsyncMock(return_value=False)
    resp = test_app.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "degraded"


# ---------------------------------------------------------------------------
# /v1/models
# ---------------------------------------------------------------------------


def test_list_models(test_app):
    resp = test_app.get("/v1/models")
    assert resp.status_code == 200
    body = resp.json()
    assert body["object"] == "list"
    ids = [m["id"] for m in body["data"]]
    assert "llama3.2" in ids
    assert "offline-fallback" in ids


# ---------------------------------------------------------------------------
# /v1/chat/completions
# ---------------------------------------------------------------------------


def _mock_offline_response():
    """Return a ChatCompletionResponse-shaped dict for mocking."""
    from models import ChatCompletionChoice, ChatCompletionResponse, ChatMessage

    return ChatCompletionResponse(
        model="llama3.2",
        choices=[
            ChatCompletionChoice(
                message=ChatMessage(role="assistant", content="Offline response"),
                finish_reason="stop",
            )
        ],
        provider="offline",
    )


def test_chat_completions_v1(test_app, gateway):
    gateway.route = AsyncMock(return_value=_mock_offline_response())
    resp = test_app.post(
        "/v1/chat/completions",
        json={
            "model": "llama3.2",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["choices"][0]["message"]["role"] == "assistant"


def test_chat_completions_no_v1(test_app, gateway):
    gateway.route = AsyncMock(return_value=_mock_offline_response())
    resp = test_app.post(
        "/chat/completions",
        json={
            "model": "llama3.2",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /usage/{tenant_id}
# ---------------------------------------------------------------------------


def test_get_usage(test_app, tmp_db):
    resp = test_app.get("/usage/test-tenant")
    assert resp.status_code == 200
    body = resp.json()
    assert body["tenant_id"] == "test-tenant"
    assert "daily_limit" in body
    assert "remaining" in body


def test_get_usage_stats(test_app):
    resp = test_app.get("/usage/test-tenant/stats?hours=24")
    assert resp.status_code == 200
    assert "stats" in resp.json()


# ---------------------------------------------------------------------------
# /admin/budget
# ---------------------------------------------------------------------------


def test_set_budget(test_app):
    resp = test_app.post("/admin/budget?tenant_id=mytenant&daily_limit=50000")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["daily_limit"] == 50000


# ---------------------------------------------------------------------------
# /admin/cache/clear
# ---------------------------------------------------------------------------


def test_clear_cache(test_app):
    resp = test_app.post("/admin/cache/clear")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


# ---------------------------------------------------------------------------
# /providers
# ---------------------------------------------------------------------------


def test_providers_dashboard(test_app, gateway):
    gateway.ollama.health_check = AsyncMock(return_value=False)
    resp = test_app.get("/providers")
    assert resp.status_code == 200
    body = resp.json()
    assert "providers" in body
    assert "active_provider" in body
