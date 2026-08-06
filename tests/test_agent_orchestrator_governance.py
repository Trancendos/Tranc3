"""
Tests for AI Governance Constitution Phase 3 — AgentOrchestrator.submit_task()
gating Tier 4 dispatch through the escalation FSM (src/compliance/escalation_fsm.py).

Uses a small isolated fixture charter set and an isolated SQLite DB, mirroring
tests/test_escalation_fsm.py's pattern, rather than the real
docs/governance/charters/ seed set and shared data/ path.
"""

from __future__ import annotations

import json

import pytest

import src.agents.orchestrator as orchestrator_module
import src.compliance.ai_governance as ai_governance_module
import src.compliance.cab_gate as cab_gate_module
import src.compliance.escalation_fsm as fsm_module
from src.agents.orchestrator import AgentConfig, AgentOrchestrator, AgentTask
from src.compliance.escalation_fsm import CharterRegistry, EscalationFSM

ARCHPRIME_READONLY = {
    "charter_id": "test-archprime-readonly",
    "version": "1.0.0",
    "tier": 4,
    "domain": "ArchPrime",
    "mission": "Test charter with no approval required.",
    "allowed_actions": ["read_approved_documents"],
    "forbidden_actions": ["delete_thing"],
    "risk_tier": "minimal",
    "approval_required": False,
    "escalation_triggers": ["audit_gap"],
    "escalation_severity": "low",
    "audit_sink": "observatory",
    "fallback_behavior": "stop_and_escalate",
}

COMMPRIME_APPROVAL = {
    "charter_id": "test-commprime-approval",
    "version": "1.0.0",
    "tier": 4,
    "domain": "CommPrime",
    "mission": "Test charter requiring CAB approval.",
    "allowed_actions": ["read_ledger_summary"],
    "forbidden_actions": ["transfer_funds"],
    "risk_tier": "high",
    "approval_required": True,
    "escalation_triggers": ["irreversible_action_requested"],
    "escalation_severity": "high",
    "audit_sink": "observatory",
    "fallback_behavior": "stop_and_escalate",
}


@pytest.fixture
def charters_dir(tmp_path):
    d = tmp_path / "charters"
    d.mkdir()
    for charter in (ARCHPRIME_READONLY, COMMPRIME_APPROVAL):
        with open(d / f"{charter['charter_id']}.json", "w", encoding="utf-8") as f:
            json.dump(charter, f)
    return d


@pytest.fixture
def registry(charters_dir):
    return CharterRegistry(charters_dir)


@pytest.fixture
def fsm(registry, tmp_path, monkeypatch):
    monkeypatch.setattr(fsm_module, "_DB_PATH", tmp_path / "escalation_fsm.db")
    monkeypatch.setattr(cab_gate_module, "_DB_PATH", tmp_path / "cab_changes.db")
    monkeypatch.setattr(ai_governance_module, "_DB_PATH", tmp_path / "ai_governance.db")
    # cab_gate.cab_gate is a module-level singleton constructed at import time — see
    # tests/test_escalation_fsm.py's fsm fixture for why this explicit init is needed.
    with cab_gate_module._get_conn() as conn:
        cab_gate_module._init_db(conn)
    return EscalationFSM(registry)


@pytest.fixture
def orch(fsm, tmp_path, monkeypatch):
    monkeypatch.setattr(orchestrator_module, "get_escalation_fsm", lambda: fsm)
    return AgentOrchestrator(db_path=str(tmp_path / "agents.db"))


def test_approved_action_is_enqueued(orch):
    orch.register_agent(AgentConfig(id="agent-1", name="A1", role="reader", domain="ArchPrime"))
    task = AgentTask(agent_id="agent-1", action="read_approved_documents")
    task_id = orch.submit_task(task)

    stored = orch.get_task(task_id)
    assert stored.status == "pending"
    assert stored.escalation_record_id is not None
    assert any(t[2] == task_id for t in orch._queue)


def test_approval_required_action_is_not_enqueued(orch):
    orch.register_agent(AgentConfig(id="agent-2", name="A2", role="reader", domain="CommPrime"))
    task = AgentTask(agent_id="agent-2", action="read_ledger_summary")
    task_id = orch.submit_task(task)

    stored = orch.get_task(task_id)
    assert stored.status == "pending_governance"
    assert not any(t[2] == task_id for t in orch._queue)


def test_forbidden_action_is_blocked(orch):
    orch.register_agent(AgentConfig(id="agent-3", name="A3", role="reader", domain="CommPrime"))
    task = AgentTask(agent_id="agent-3", action="transfer_funds")
    task_id = orch.submit_task(task)

    stored = orch.get_task(task_id)
    assert stored.status == "blocked_governance"
    assert "rejected" in stored.error
    assert not any(t[2] == task_id for t in orch._queue)


def test_unmatched_action_escalates_rather_than_defaulting_permissive(orch):
    """Per §3.4: ambiguity (no charter covers the action) escalates, it is never
    treated as implicitly allowed."""
    orch.register_agent(AgentConfig(id="agent-4", name="A4", role="reader", domain="ArchPrime"))
    task = AgentTask(agent_id="agent-4", action="do_something_unlisted")
    task_id = orch.submit_task(task)

    stored = orch.get_task(task_id)
    assert stored.status == "pending_governance"
    assert not any(t[2] == task_id for t in orch._queue)


def test_unregistered_agent_resolves_to_unassigned_domain(orch):
    """An agent with no registered AgentConfig falls back to the 'unassigned' domain
    rather than raising — no charter covers (4, 'unassigned', ...) in this fixture set,
    so it escalates."""
    task = AgentTask(agent_id="ghost-agent", action="read_approved_documents")
    task_id = orch.submit_task(task)

    stored = orch.get_task(task_id)
    assert stored.status == "pending_governance"


def test_task_survives_reload_from_db(orch, fsm, tmp_path, monkeypatch):
    orch.register_agent(AgentConfig(id="agent-5", name="A5", role="reader", domain="ArchPrime"))
    task = AgentTask(agent_id="agent-5", action="read_approved_documents")
    task_id = orch.submit_task(task)

    monkeypatch.setattr(orchestrator_module, "get_escalation_fsm", lambda: fsm)
    reloaded = AgentOrchestrator(db_path=str(tmp_path / "agents.db"))
    stored = reloaded.get_task(task_id)
    assert stored is not None
    assert stored.action == "read_approved_documents"
    assert stored.escalation_record_id == orch.get_task(task_id).escalation_record_id
