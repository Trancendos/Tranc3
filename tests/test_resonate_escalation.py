"""Tests for Resonate's human-escalation honesty (src/resonate/empathy.py).

Guards against regressing to the previous behaviour where escalate_to_human()
unconditionally claimed "A support team member has been notified" even though
no real delivery was ever attempted.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.resonate import empathy as empathy_module
from src.resonate.empathy import Resonate, get_resonate
from src.resonate.routes import router as resonate_router

_test_app = FastAPI()
_test_app.include_router(resonate_router)
client = TestClient(_test_app)


@pytest.mark.asyncio
async def test_escalate_without_webhook_configured_does_not_claim_notified(monkeypatch):
    monkeypatch.setattr(empathy_module, "_ESCALATION_WEBHOOK_URL", "")
    result = await Resonate().escalate_to_human(user_id="u1", context="I need help")
    assert result["escalated"] is True
    assert "notified" not in result["message"].lower()
    assert result["notification_dispatched"] is False


@pytest.mark.asyncio
async def test_escalate_reports_dispatch_failure_honestly(monkeypatch):
    monkeypatch.setattr(
        empathy_module, "_ESCALATION_WEBHOOK_URL", "https://example.com/hooks/support"
    )

    async def _fail(self, user_id, context):
        return False

    monkeypatch.setattr(Resonate, "_dispatch_notification", _fail)
    result = await Resonate().escalate_to_human(user_id="u1", context="I need help")
    assert result["escalated"] is True
    assert "could not confirm" in result["message"].lower()
    assert result["notification_dispatched"] is False


@pytest.mark.asyncio
async def test_escalate_reports_success_only_on_confirmed_dispatch(monkeypatch):
    monkeypatch.setattr(
        empathy_module, "_ESCALATION_WEBHOOK_URL", "https://example.com/hooks/support"
    )

    async def _succeed(self, user_id, context):
        return True

    monkeypatch.setattr(Resonate, "_dispatch_notification", _succeed)
    result = await Resonate().escalate_to_human(user_id="u1", context="I need help")
    assert result["escalated"] is True
    assert "flagged for urgent review" in result["message"].lower()


@pytest.mark.asyncio
async def test_dispatch_notification_false_when_no_webhook_configured(monkeypatch):
    monkeypatch.setattr(empathy_module, "_ESCALATION_WEBHOOK_URL", "")
    dispatched = await Resonate()._dispatch_notification("u1", "context")
    assert dispatched is False


@pytest.mark.asyncio
async def test_dispatch_notification_trusts_response_body_not_status_code(monkeypatch):
    """The notifications worker always returns HTTP 200, even on failure —
    delivery must be judged from the `ok` field in the response body."""
    monkeypatch.setattr(
        empathy_module, "_ESCALATION_WEBHOOK_URL", "https://example.com/hooks/support"
    )

    class _FakeResponse:
        status_code = 200

        def json(self):
            return {"ok": False, "reason": "Rate limit exceeded"}

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            return _FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    dispatched = await Resonate()._dispatch_notification("u1", "context")
    assert dispatched is False


@pytest.mark.asyncio
async def test_dispatch_notification_network_error_returns_false(monkeypatch):
    """A connection failure to the notifications worker must not raise —
    escalate_to_human() has no other fallback and must always return a
    response to the user."""
    monkeypatch.setattr(
        empathy_module, "_ESCALATION_WEBHOOK_URL", "https://example.com/hooks/support"
    )

    class _RaisingAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            raise ConnectionError("notifications worker unreachable")

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _RaisingAsyncClient)
    dispatched = await Resonate()._dispatch_notification("u1", "context")
    assert dispatched is False


@pytest.mark.asyncio
async def test_escalate_survives_observatory_failure(monkeypatch):
    """observe() failing must not block the escalation response itself."""
    monkeypatch.setattr(empathy_module, "_ESCALATION_WEBHOOK_URL", "")

    def _boom(*args, **kwargs):
        raise RuntimeError("observatory unreachable")

    import src.observability.observatory as observatory_module

    monkeypatch.setattr(observatory_module, "observe", _boom)
    result = await Resonate().escalate_to_human(user_id="u1", context="I need help")
    assert result["escalated"] is True


def test_wrap_response_passthrough_when_no_sensitivity():
    result = Resonate().wrap_response("plain response")
    assert result == "plain response"


def test_wrap_response_passthrough_when_mood_high():
    result = Resonate().wrap_response("plain response", sensitivity_level="none", user_mood=4)
    assert result == "plain response"


def test_wrap_response_adds_empathy_prefix_for_high_sensitivity():
    result = Resonate().wrap_response("you'll be okay", sensitivity_level="high")
    assert "you'll be okay" in result
    assert len(result) > len("you'll be okay")


def test_wrap_response_adds_prefix_for_low_mood():
    result = Resonate().wrap_response("response", sensitivity_level="none", user_mood=1)
    assert "response" in result


def test_wrap_response_includes_crisis_resources():
    result = Resonate().wrap_response(
        "response", sensitivity_level="critical", crisis_resources=True
    )
    assert "Samaritans" in result
    assert "988" in result


def test_wrap_response_medium_sensitivity_adds_validation_phrase():
    result = Resonate().wrap_response("response", sensitivity_level="medium")
    assert "response" in result
    assert len(result) > len("response")


def test_stats_reports_active():
    assert Resonate().stats() == {"service": "resonate", "status": "active"}


def test_get_resonate_returns_singleton():
    a = get_resonate()
    b = get_resonate()
    assert a is b
    assert isinstance(a, Resonate)


def test_status_route():
    resp = client.get("/resonate/status")
    assert resp.status_code == 200
    assert resp.json() == {"service": "resonate", "status": "active"}


def test_wrap_route_requires_response_text():
    resp = client.post("/resonate/wrap", json={})
    assert resp.status_code == 400


def test_wrap_route_returns_wrapped_response():
    resp = client.post("/resonate/wrap", json={"response": "hello"})
    assert resp.status_code == 200
    assert resp.json() == {"wrapped_response": "hello"}


def test_escalate_route_does_not_claim_notified_without_webhook(monkeypatch):
    monkeypatch.setattr(empathy_module, "_ESCALATION_WEBHOOK_URL", "")
    resp = client.post("/resonate/escalate/u1", json={"context": "help"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["escalated"] is True
    assert "notified" not in body["message"].lower()
