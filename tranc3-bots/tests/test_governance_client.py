"""
Tests for bots/governance_client.py — AI Governance Constitution Phase 3.

tranc3-bots is a separately deployed package with no dependency on the main
repo's src.compliance.escalation_fsm, so this client talks to the main
backend's POST /governance/actions route over HTTP instead of importing the
FSM directly. These tests fake httpx.AsyncClient rather than making real
network calls or adding a new test dependency (no respx in requirements.txt).
"""

from __future__ import annotations

import httpx
import pytest
from bots import governance_client


class _FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error", request=httpx.Request("POST", "http://x"), response=None
            )

    def json(self):
        return self._json_data


class _FakeAsyncClient:
    last_call = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None, headers=None):
        _FakeAsyncClient.last_call = {"url": url, "json": json, "headers": headers}
        return _FakeAsyncClient.response


class _RaisingAsyncClient(_FakeAsyncClient):
    async def post(self, url, json=None, headers=None):
        raise httpx.ConnectTimeout("boom")


@pytest.fixture(autouse=True)
def _reset_defaults(monkeypatch):
    monkeypatch.setattr(governance_client, "_GATE_ENABLED", False)
    monkeypatch.setattr(governance_client, "_BACKEND_URL", "")
    monkeypatch.setattr(governance_client, "_INTERNAL_SECRET", "")
    _FakeAsyncClient.last_call = None


async def test_gate_disabled_by_default_is_a_noop(monkeypatch):
    # governance_client._GATE_ENABLED already False via fixture; no httpx patch needed —
    # a real network call here would fail the test if one were attempted.
    result = await governance_client.check_action("generate", requestor="test")
    assert result is None


async def test_gate_enabled_but_no_backend_url_skips(monkeypatch):
    monkeypatch.setattr(governance_client, "_GATE_ENABLED", True)
    monkeypatch.setattr(governance_client, "_BACKEND_URL", "")
    result = await governance_client.check_action("generate", requestor="test")
    assert result is None


async def test_approved_action_returns_record(monkeypatch):
    monkeypatch.setattr(governance_client, "_GATE_ENABLED", True)
    monkeypatch.setattr(governance_client, "_BACKEND_URL", "http://backend:8000")
    _FakeAsyncClient.response = _FakeResponse({"state": "approved", "record_id": "ESC-1"})
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    record = await governance_client.check_action("generate", requestor="bot-registry:job-1")
    assert record["state"] == "approved"
    assert _FakeAsyncClient.last_call["json"] == {
        "tier": 5,
        "domain": "unassigned",
        "action": "generate",
        "requestor": "bot-registry:job-1",
    }


async def test_rejected_action_raises_governance_blocked(monkeypatch):
    monkeypatch.setattr(governance_client, "_GATE_ENABLED", True)
    monkeypatch.setattr(governance_client, "_BACKEND_URL", "http://backend:8000")
    _FakeAsyncClient.response = _FakeResponse({"state": "rejected", "reason": "forbidden action"})
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    with pytest.raises(governance_client.GovernanceBlockedError):
        await governance_client.check_action("generate", requestor="test")


async def test_halted_action_raises_governance_blocked(monkeypatch):
    monkeypatch.setattr(governance_client, "_GATE_ENABLED", True)
    monkeypatch.setattr(governance_client, "_BACKEND_URL", "http://backend:8000")
    _FakeAsyncClient.response = _FakeResponse({"state": "halted", "reason": "hard stop"})
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    with pytest.raises(governance_client.GovernanceBlockedError):
        await governance_client.check_action("generate", requestor="test")


async def test_escalated_action_does_not_raise(monkeypatch):
    """escalated/pending_cab are not blocking states for a stateless bot dispatch —
    only rejected/halted stop the call."""
    monkeypatch.setattr(governance_client, "_GATE_ENABLED", True)
    monkeypatch.setattr(governance_client, "_BACKEND_URL", "http://backend:8000")
    _FakeAsyncClient.response = _FakeResponse({"state": "escalated"})
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    record = await governance_client.check_action("generate", requestor="test")
    assert record["state"] == "escalated"


async def test_network_error_fails_open(monkeypatch):
    monkeypatch.setattr(governance_client, "_GATE_ENABLED", True)
    monkeypatch.setattr(governance_client, "_BACKEND_URL", "http://backend:8000")
    monkeypatch.setattr(httpx, "AsyncClient", _RaisingAsyncClient)

    result = await governance_client.check_action("generate", requestor="test")
    assert result is None


async def test_internal_secret_forwarded_when_set(monkeypatch):
    monkeypatch.setattr(governance_client, "_GATE_ENABLED", True)
    monkeypatch.setattr(governance_client, "_BACKEND_URL", "http://backend:8000")
    monkeypatch.setattr(governance_client, "_INTERNAL_SECRET", "shh")
    _FakeAsyncClient.response = _FakeResponse({"state": "approved"})
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    await governance_client.check_action("generate", requestor="test")
    assert _FakeAsyncClient.last_call["headers"] == {"X-Internal-Secret": "shh"}


@pytest.mark.parametrize("status_code", [401, 403])
async def test_auth_failure_fails_closed_not_open(monkeypatch, status_code):
    """cubic P1: a missing/mismatched INTERNAL_SECRET is a configuration error, not an
    infra outage — treating the backend's 401/403 the same as a network failure would
    mean governance was silently never actually being enforced once the gate was
    turned on."""
    monkeypatch.setattr(governance_client, "_GATE_ENABLED", True)
    monkeypatch.setattr(governance_client, "_BACKEND_URL", "http://backend:8000")
    _FakeAsyncClient.response = _FakeResponse({"error": "forbidden"}, status_code=status_code)
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    with pytest.raises(governance_client.GovernanceBlockedError):
        await governance_client.check_action("generate", requestor="test")


async def test_invalid_governance_gate_timeout_env_falls_back_to_default(monkeypatch):
    """cubic P1: a typo'd or empty GOVERNANCE_GATE_TIMEOUT must not crash the whole
    package at import time, even when the gate is disabled."""
    import importlib

    monkeypatch.setenv("GOVERNANCE_GATE_TIMEOUT", "not-a-number")
    try:
        reloaded = importlib.reload(governance_client)
        assert reloaded._TIMEOUT == 5.0
    finally:
        monkeypatch.delenv("GOVERNANCE_GATE_TIMEOUT", raising=False)
        importlib.reload(governance_client)
