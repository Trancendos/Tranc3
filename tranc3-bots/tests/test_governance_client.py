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
    # cubic P3: .response is shared class state too — without resetting it here, a
    # test that forgets to set its own response would silently reuse whatever the
    # previous test left behind instead of failing loudly.
    _FakeAsyncClient.response = None


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


@pytest.mark.parametrize("body", [["state", "approved"], "approved", 42, None])
async def test_non_dict_json_response_fails_closed_not_crash(monkeypatch, body):
    """cubic P2 (redesigned per a later P1 round): a reachable governance endpoint
    returning valid but non-object JSON (e.g. a list, a bare string) must not crash
    check_action with AttributeError on record.get() — but it also must not silently
    let dispatch through. A response WAS received; it's just unusable, which fails
    closed like every other 'backend is reachable but something's wrong' case."""
    monkeypatch.setattr(governance_client, "_GATE_ENABLED", True)
    monkeypatch.setattr(governance_client, "_BACKEND_URL", "http://backend:8000")
    _FakeAsyncClient.response = _FakeResponse(body)
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    with pytest.raises(governance_client.GovernanceBlockedError):
        await governance_client.check_action("generate", requestor="test")


@pytest.mark.parametrize("body", [{"state": "not-a-real-state"}, {"reason": "no state key"}])
async def test_unknown_or_missing_state_fails_closed_not_authorized(monkeypatch, body):
    """cubic P1: a reachable, 200, valid-JSON-object response with a missing or
    unrecognized 'state' previously fell through to `return record` (authorizing
    dispatch) because only _BLOCKED_STATES was checked, not the full state set —
    malformed-but-technically-valid responses must fail closed like every other
    'backend is reachable but something's wrong' case, not silently pass through."""
    monkeypatch.setattr(governance_client, "_GATE_ENABLED", True)
    monkeypatch.setattr(governance_client, "_BACKEND_URL", "http://backend:8000")
    _FakeAsyncClient.response = _FakeResponse(body)
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    with pytest.raises(governance_client.GovernanceBlockedError):
        await governance_client.check_action("generate", requestor="test")


async def test_non_200_status_fails_closed_not_open(monkeypatch):
    """cubic P1: a 5xx (or any other non-2xx) from a *reachable* backend previously
    fell into the same fail-open branch as a genuine network failure — a struggling
    or buggy governance service could silently disable enforcement entirely."""
    monkeypatch.setattr(governance_client, "_GATE_ENABLED", True)
    monkeypatch.setattr(governance_client, "_BACKEND_URL", "http://backend:8000")
    _FakeAsyncClient.response = _FakeResponse({"error": "internal"}, status_code=500)
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    with pytest.raises(governance_client.GovernanceBlockedError):
        await governance_client.check_action("generate", requestor="test")


def _assert_bad_timeout_env_falls_back_to_default(monkeypatch, bad_value: str) -> None:
    """Shared by the two tests below (cubic P3: was duplicated verbatim). Sets
    GOVERNANCE_GATE_TIMEOUT=bad_value, reloads governance_client against the real
    environment, and asserts _TIMEOUT falls back to 5.0 — then always restores the
    module's pre-reload state.

    importlib.reload() re-executes the module against the *real* environment,
    bypassing the autouse _reset_defaults fixture for the other three module-level
    settings — save and restore them explicitly so an ambient
    GOVERNANCE_GATE_ENABLED/TRANC3_ENGINE_URL/INTERNAL_SECRET in the real
    environment can't leak into tests that run after this one.
    """
    import importlib

    saved = {
        "_GATE_ENABLED": governance_client._GATE_ENABLED,
        "_BACKEND_URL": governance_client._BACKEND_URL,
        "_INTERNAL_SECRET": governance_client._INTERNAL_SECRET,
        "_TIMEOUT": governance_client._TIMEOUT,
    }
    monkeypatch.setenv("GOVERNANCE_GATE_TIMEOUT", bad_value)
    try:
        reloaded = importlib.reload(governance_client)
        assert reloaded._TIMEOUT == 5.0
    finally:
        monkeypatch.delenv("GOVERNANCE_GATE_TIMEOUT", raising=False)
        importlib.reload(governance_client)
        for name, value in saved.items():
            monkeypatch.setattr(governance_client, name, value)


async def test_invalid_governance_gate_timeout_env_falls_back_to_default(monkeypatch):
    """cubic P1: a typo'd or empty GOVERNANCE_GATE_TIMEOUT must not crash the whole
    package at import time, even when the gate is disabled."""
    _assert_bad_timeout_env_falls_back_to_default(monkeypatch, "not-a-number")


@pytest.mark.parametrize("bad_timeout", ["0", "-1", "-5.5", "inf", "nan"])
async def test_non_positive_or_non_finite_governance_gate_timeout_falls_back_to_default(
    monkeypatch, bad_timeout
):
    """cubic P1: httpx treats a timeout<=0 as 'time out immediately', which
    check_action()'s own network-error handler then reads as an unreachable backend
    and fails OPEN — so a non-positive GOVERNANCE_GATE_TIMEOUT override would turn
    every governed action into a silent bypass, not just a slow one. An infinite or
    NaN override is equally invalid (float('inf')/float('nan') both parse without
    raising ValueError). All must fall back to the 5.0s default, same as a typo."""
    _assert_bad_timeout_env_falls_back_to_default(monkeypatch, bad_timeout)
