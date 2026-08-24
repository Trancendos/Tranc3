"""
Tests for BotRegistry._dispatch()'s governance gate wiring (AI Governance
Constitution Phase 3) — see bots/governance_client.py for the HTTP client itself.
"""

from __future__ import annotations

import pytest
from bots import governance_client
from bots.registry import BotRegistry
from bots.types import JobSpec


async def test_dispatch_calls_governance_gate_before_handler(monkeypatch):
    calls = []

    async def fake_check_action(bot_type, requestor):
        calls.append((bot_type, requestor))
        return {"state": "approved"}

    async def fake_handler(payload):
        return {"ok": True}

    monkeypatch.setattr(governance_client, "check_action", fake_check_action)
    monkeypatch.setattr("bots.registry.HANDLERS", {"generate": fake_handler})

    registry = BotRegistry()
    job = JobSpec(bot_type="generate", payload={})
    result = await registry._dispatch(job)

    assert result == {"ok": True}
    assert calls == [("generate", f"bot-registry:{job.job_id}")]


async def test_dispatch_propagates_governance_block(monkeypatch):
    async def blocking_check_action(bot_type, requestor):
        raise governance_client.GovernanceBlockedError("blocked by governance (rejected)")

    async def fake_handler(payload):
        raise AssertionError("handler must not run when governance blocks the dispatch")

    monkeypatch.setattr(governance_client, "check_action", blocking_check_action)
    monkeypatch.setattr("bots.registry.HANDLERS", {"generate": fake_handler})

    registry = BotRegistry()
    job = JobSpec(bot_type="generate", payload={})

    with pytest.raises(governance_client.GovernanceBlockedError):
        await registry._dispatch(job)


async def test_dispatch_gate_disabled_by_default_does_not_block(monkeypatch):
    """With GOVERNANCE_GATE_ENABLED unset (the default), check_action is a real
    no-op — dispatch must behave exactly as it did before Phase 3."""
    monkeypatch.setattr(governance_client, "_GATE_ENABLED", False)

    async def fake_handler(payload):
        return {"ok": True}

    monkeypatch.setattr("bots.registry.HANDLERS", {"generate": fake_handler})

    registry = BotRegistry()
    job = JobSpec(bot_type="generate", payload={})
    result = await registry._dispatch(job)
    assert result == {"ok": True}


async def test_dispatch_unknown_bot_type_raises_before_governance_check(monkeypatch):
    calls = []

    async def fake_check_action(bot_type, requestor):
        calls.append(bot_type)
        return {"state": "approved"}

    monkeypatch.setattr(governance_client, "check_action", fake_check_action)
    monkeypatch.setattr("bots.registry.HANDLERS", {})

    registry = BotRegistry()
    job = JobSpec(bot_type="nonexistent", payload={})

    with pytest.raises(ValueError):
        await registry._dispatch(job)
    assert calls == []
