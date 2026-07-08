"""Tests for Resonate's human-escalation honesty (src/resonate/empathy.py).

Guards against regressing to the previous behaviour where escalate_to_human()
unconditionally claimed "A support team member has been notified" even though
no real delivery was ever attempted.
"""

import pytest

from src.resonate import empathy as empathy_module
from src.resonate.empathy import Resonate


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
