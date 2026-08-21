"""
Tests for the AI Governance Constitution's escalation FSM
(src/compliance/escalation_fsm.py) and its FastAPI routes
(src/compliance/governance_routes.py) — Phase 2 of
docs/governance/AI-GOVERNANCE-CONSTITUTION.md.

Uses a small fixture charter set and an isolated SQLite DB per test rather than the
real docs/governance/charters/ seed set and shared data/ path, so tests are
deterministic and don't collide with each other or with a running process.
"""

from __future__ import annotations

import json
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.compliance.ai_governance as ai_governance_module
import src.compliance.cab_gate as cab_gate_module
import src.compliance.escalation_fsm as fsm_module
from src.compliance.escalation_fsm import (
    ActionForbiddenError,
    ActionRequest,
    CharterNotFoundError,
    CharterRegistry,
    CharterValidationError,
    EscalationError,
    EscalationFSM,
    RecordNotFoundError,
)
from src.observability.observatory import EventSeverity, Observatory

ALLOWED_ONLY = {
    "charter_id": "test-allowed-only",
    "version": "1.0.0",
    "tier": 4,
    "domain": "ArchPrime",
    "mission": "Test charter with no approval required.",
    "allowed_actions": ["read_thing"],
    "forbidden_actions": ["delete_thing"],
    "risk_tier": "minimal",
    "approval_required": False,
    "escalation_triggers": ["audit_gap"],
    "escalation_severity": "low",
    "audit_sink": "observatory",
    "fallback_behavior": "stop_and_escalate",
}

APPROVAL_REQUIRED = {
    "charter_id": "test-approval-required",
    "version": "1.0.0",
    "tier": 3,
    "domain": "CommPrime",
    "mission": "Test charter requiring CAB approval.",
    "allowed_actions": ["transfer_funds"],
    "forbidden_actions": ["bypass_ledger"],
    "risk_tier": "high",
    "approval_required": True,
    "escalation_triggers": ["irreversible_action_requested"],
    "escalation_severity": "high",
    "audit_sink": "observatory",
    "fallback_behavior": "stop_and_escalate",
}

CONFIDENCE_GATED = {
    "charter_id": "test-confidence-gated",
    "version": "1.0.0",
    "tier": 4,
    "domain": "KnowPrime",
    "mission": "Test charter with a confidence threshold.",
    "allowed_actions": ["summarize_thing"],
    "forbidden_actions": ["publish_thing"],
    "risk_tier": "limited",
    "approval_required": False,
    "escalation_triggers": ["confidence_below_threshold"],
    "escalation_severity": "medium",
    "audit_sink": "observatory",
    "fallback_behavior": "stop_and_escalate",
    "confidence_model": {
        "threshold": 0.6,
        "weights": {
            "decision_quality": 0.30,
            "adaptation_speed": 0.25,
            "state_coherence": 0.20,
            "resource_efficiency": 0.15,
            "communication": 0.10,
        },
    },
}


SAFETY_GATED = {
    "charter_id": "test-safety-gated",
    "version": "1.0.0",
    "tier": 4,
    "domain": "SecPrime",
    "mission": "Test charter with critical severity and non-confidence escalation triggers.",
    "allowed_actions": ["read_threat_intel"],
    "forbidden_actions": ["quarantine_service"],
    "risk_tier": "high",
    "approval_required": False,
    "escalation_triggers": ["sensitive_data_detected", "prompt_injection_suspected"],
    "escalation_severity": "critical",
    "audit_sink": "observatory",
    "fallback_behavior": "stop_and_escalate",
}


@pytest.fixture
def charters_dir(tmp_path):
    d = tmp_path / "charters"
    d.mkdir()
    for charter in (ALLOWED_ONLY, APPROVAL_REQUIRED, CONFIDENCE_GATED, SAFETY_GATED):
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
    # cab_gate.cab_gate is a module-level singleton constructed at import time — its
    # __init__ already ran _init_db() against whatever _DB_PATH was active then, so the
    # freshly-monkeypatched tmp_path DB needs the cab_changes table created explicitly.
    with cab_gate_module._get_conn() as conn:
        cab_gate_module._init_db(conn)
    return EscalationFSM(registry)


# tests/conftest.py always sets INTERNAL_SECRET (falling back to a fixed test
# value if the environment didn't provide one — see tests/conftest.py), so
# _INTERNAL_SECRET is never "" in this suite — every POST call below needs the
# matching X-Internal-Secret header, same pattern as tests/test_matrix_suites.py
# uses for matrix_suites_routes.
_TEST_INTERNAL_SECRET = os.environ["INTERNAL_SECRET"]


@pytest.fixture
def client(registry, fsm, monkeypatch):
    import src.compliance.governance_routes as routes_module

    monkeypatch.setattr(routes_module, "_fsm", fsm)
    monkeypatch.setattr(routes_module, "_INTERNAL_SECRET", _TEST_INTERNAL_SECRET)
    monkeypatch.setattr(fsm_module, "_registry", registry)
    app = FastAPI()
    app.include_router(routes_module.router)
    return TestClient(app, headers={"X-Internal-Secret": _TEST_INTERNAL_SECRET})


@pytest.fixture
def unauthenticated_client(registry, fsm, monkeypatch):
    import src.compliance.governance_routes as routes_module

    monkeypatch.setattr(routes_module, "_fsm", fsm)
    monkeypatch.setattr(routes_module, "_INTERNAL_SECRET", _TEST_INTERNAL_SECRET)
    monkeypatch.setattr(fsm_module, "_registry", registry)
    app = FastAPI()
    app.include_router(routes_module.router)
    return TestClient(app)


# ---------------------------------------------------------------------------
# CharterRegistry
# ---------------------------------------------------------------------------


def test_registry_loads_all_fixture_charters(registry):
    assert len(registry.list_all()) == 4


def test_registry_get_unknown_charter_raises(registry):
    with pytest.raises(CharterNotFoundError):
        registry.get("does-not-exist")


def test_registry_find_for_allowed_action(registry):
    charter = registry.find_for(4, "ArchPrime", "read_thing")
    assert charter.charter_id == "test-allowed-only"


def test_registry_find_for_forbidden_action_raises(registry):
    with pytest.raises(ActionForbiddenError):
        registry.find_for(4, "ArchPrime", "delete_thing")


def test_registry_find_for_unmatched_action_raises_not_found(registry):
    with pytest.raises(CharterNotFoundError):
        registry.find_for(4, "ArchPrime", "launch_nuclear_codes")


def test_registry_duplicate_charter_id_raises(tmp_path):
    d = tmp_path / "dup"
    d.mkdir()
    for i in range(2):
        with open(d / f"c{i}.json", "w", encoding="utf-8") as f:
            json.dump(ALLOWED_ONLY, f)
    with pytest.raises(CharterValidationError, match="Duplicate charter_id"):
        CharterRegistry(d)


def test_registry_schema_invalid_charter_raises(tmp_path):
    d = tmp_path / "bad"
    d.mkdir()
    bad = dict(ALLOWED_ONLY)
    del bad["mission"]
    with open(d / "bad.json", "w", encoding="utf-8") as f:
        json.dump(bad, f)
    with pytest.raises(CharterValidationError):
        CharterRegistry(d)


def test_registry_missing_directory_loads_empty(tmp_path):
    registry = CharterRegistry(tmp_path / "does-not-exist")
    assert registry.list_all() == []


def test_real_seed_charters_load_and_validate():
    """The 11 real charters shipped in docs/governance/charters/ must themselves
    pass schema validation — this is the regression test that would catch the
    same $defs.example / confidence_model bugs CodeRabbit found in the schema."""
    registry = CharterRegistry()
    assert len(registry.list_all()) >= 10


# ---------------------------------------------------------------------------
# EscalationFSM.submit()
# ---------------------------------------------------------------------------


def test_submit_allowed_action_approves_immediately(fsm):
    record = fsm.submit(
        ActionRequest(tier=4, domain="ArchPrime", action="read_thing", requestor="agent-1")
    )
    assert record.state == "approved"
    assert record.charter_id == "test-allowed-only"


def test_submit_forbidden_action_rejects(fsm):
    record = fsm.submit(
        ActionRequest(tier=4, domain="ArchPrime", action="delete_thing", requestor="agent-1")
    )
    assert record.state == "rejected"
    assert "forbidden" in record.reason


def test_submit_unmatched_action_escalates_not_permissive(fsm):
    """Per AI-GOVERNANCE-CONSTITUTION.md §3.4: ambiguity escalates, never defaults
    permissive — an action no charter covers must not silently succeed."""
    record = fsm.submit(
        ActionRequest(
            tier=4, domain="ArchPrime", action="do_something_unspecified", requestor="agent-1"
        )
    )
    assert record.state == "escalated"


def test_submit_approval_required_routes_to_pending_cab(fsm):
    record = fsm.submit(
        ActionRequest(tier=3, domain="CommPrime", action="transfer_funds", requestor="agent-2")
    )
    assert record.state == "pending_cab"
    assert record.cab_change_id is not None
    assert record.cab_change_id.startswith("CAB-")


def test_submit_low_confidence_escalates(fsm):
    record = fsm.submit(
        ActionRequest(
            tier=4,
            domain="KnowPrime",
            action="summarize_thing",
            requestor="agent-3",
            confidence=0.1,
        )
    )
    assert record.state == "escalated"
    assert "confidence" in record.reason


def test_submit_sufficient_confidence_does_not_escalate(fsm):
    record = fsm.submit(
        ActionRequest(
            tier=4,
            domain="KnowPrime",
            action="summarize_thing",
            requestor="agent-3",
            confidence=0.9,
        )
    )
    assert record.state == "approved"


def test_submit_no_confidence_provided_does_not_escalate(fsm):
    """A charter can require confidence_model without every caller supplying a
    confidence score — absence of a score is not the same as a low score."""
    record = fsm.submit(
        ActionRequest(tier=4, domain="KnowPrime", action="summarize_thing", requestor="agent-3")
    )
    assert record.state == "approved"


# ---------------------------------------------------------------------------
# CAB resolution, freeze, halt, complete
# ---------------------------------------------------------------------------


def test_resolve_cab_approve(fsm):
    record = fsm.submit(
        ActionRequest(tier=3, domain="CommPrime", action="transfer_funds", requestor="agent-2")
    )
    resolved = fsm.resolve_cab(record.record_id, approver="human-1", approved=True)
    assert resolved.state == "approved"


def test_resolve_cab_reject(fsm):
    record = fsm.submit(
        ActionRequest(tier=3, domain="CommPrime", action="transfer_funds", requestor="agent-2")
    )
    resolved = fsm.resolve_cab(record.record_id, approver="human-1", approved=False)
    assert resolved.state == "rejected"


def test_resolve_cab_on_non_pending_record_raises(fsm):
    record = fsm.submit(
        ActionRequest(tier=4, domain="ArchPrime", action="read_thing", requestor="agent-1")
    )
    assert record.state == "approved"
    with pytest.raises(EscalationError, match="not pending_cab"):
        fsm.resolve_cab(record.record_id, approver="human-1", approved=True)


def test_freeze_and_halt(fsm):
    record = fsm.submit(
        ActionRequest(tier=4, domain="ArchPrime", action="read_thing", requestor="agent-1")
    )
    frozen = fsm.freeze(record.record_id, reason="suspicious pattern")
    assert frozen.state == "frozen"
    halted = fsm.halt(record.record_id, reason="confirmed violation")
    assert halted.state == "halted"


def test_list_halted_is_the_hard_stop_matrix_aggregation_point(fsm):
    """docs/governance/HARD-STOP-MATRIX.md: 'no single place that answers is
    anything hard-stopped right now' — list_halted() is that place."""
    r1 = fsm.submit(ActionRequest(tier=4, domain="ArchPrime", action="read_thing", requestor="a"))
    r2 = fsm.submit(ActionRequest(tier=4, domain="ArchPrime", action="read_thing", requestor="b"))
    assert fsm.list_halted() == []
    fsm.halt(r1.record_id, reason="test")
    halted = fsm.list_halted()
    assert len(halted) == 1
    assert halted[0].record_id == r1.record_id
    assert r2.record_id not in [h.record_id for h in halted]


def test_complete_requires_approved_state(fsm):
    record = fsm.submit(
        ActionRequest(tier=4, domain="ArchPrime", action="read_thing", requestor="agent-1")
    )
    assert record.state == "approved"
    completed = fsm.complete(record.record_id)
    assert completed.state == "completed"


def test_complete_on_pending_cab_raises(fsm):
    record = fsm.submit(
        ActionRequest(tier=3, domain="CommPrime", action="transfer_funds", requestor="agent-2")
    )
    assert record.state == "pending_cab"
    with pytest.raises(EscalationError, match="must be 'approved'"):
        fsm.complete(record.record_id)


def test_get_unknown_record_raises(fsm):
    with pytest.raises(RecordNotFoundError):
        fsm.get("ESC-DOESNOTEXIST")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def test_route_list_charters(client):
    resp = client.get("/governance/charters")
    assert resp.status_code == 200
    ids = {c["charter_id"] for c in resp.json()}
    assert "test-allowed-only" in ids


def test_route_get_charter(client):
    resp = client.get("/governance/charters/test-allowed-only")
    assert resp.status_code == 200
    assert resp.json()["mission"] == ALLOWED_ONLY["mission"]


def test_route_get_charter_not_found(client):
    resp = client.get("/governance/charters/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["error"] == "unknown_charter"


def test_route_submit_action_allowed(client):
    resp = client.post(
        "/governance/actions",
        json={"tier": 4, "domain": "ArchPrime", "action": "read_thing", "requestor": "agent-1"},
    )
    assert resp.status_code == 200
    assert resp.json()["state"] == "approved"


def test_route_get_action(client):
    submit_resp = client.post(
        "/governance/actions",
        json={"tier": 4, "domain": "ArchPrime", "action": "read_thing", "requestor": "agent-1"},
    )
    record_id = submit_resp.json()["record_id"]
    get_resp = client.get(f"/governance/actions/{record_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["record_id"] == record_id


def test_route_get_action_not_found(client):
    resp = client.get("/governance/actions/ESC-DOESNOTEXIST")
    assert resp.status_code == 404
    assert resp.json()["error"] == "unknown_record"


def test_route_get_action_transitions(client):
    submit_resp = client.post(
        "/governance/actions",
        json={"tier": 4, "domain": "ArchPrime", "action": "read_thing", "requestor": "agent-1"},
    )
    record_id = submit_resp.json()["record_id"]

    resp = client.get(f"/governance/actions/{record_id}/transitions")
    assert resp.status_code == 200
    body = resp.json()
    assert [t["state"] for t in body] == ["validated", "policy_checked", "approved"]
    for transition in body:
        assert set(transition.keys()) == {"state", "reason", "ts"}


def test_route_get_action_transitions_not_found(client):
    resp = client.get("/governance/actions/ESC-DOESNOTEXIST/transitions")
    assert resp.status_code == 404
    assert resp.json()["error"] == "unknown_record"


def test_route_list_halted_empty_by_default(client):
    resp = client.get("/governance/halted")
    assert resp.status_code == 200
    assert resp.json() == []


def test_route_halt_action_and_list_halted(client):
    submit_resp = client.post(
        "/governance/actions",
        json={"tier": 4, "domain": "ArchPrime", "action": "read_thing", "requestor": "agent-1"},
    )
    record_id = submit_resp.json()["record_id"]
    halt_resp = client.post(f"/governance/actions/{record_id}/halt", json={"reason": "test halt"})
    assert halt_resp.status_code == 200
    assert halt_resp.json()["state"] == "halted"

    halted_resp = client.get("/governance/halted")
    assert len(halted_resp.json()) == 1
    assert halted_resp.json()[0]["record_id"] == record_id


def test_route_cab_decision(client):
    submit_resp = client.post(
        "/governance/actions",
        json={"tier": 3, "domain": "CommPrime", "action": "transfer_funds", "requestor": "agent-2"},
    )
    record_id = submit_resp.json()["record_id"]
    assert submit_resp.json()["state"] == "pending_cab"

    decision_resp = client.post(
        f"/governance/actions/{record_id}/cab-decision",
        json={"approver": "human-1", "approved": True},
    )
    assert decision_resp.status_code == 200
    assert decision_resp.json()["state"] == "approved"


def test_route_cab_decision_invalid_state(client):
    submit_resp = client.post(
        "/governance/actions",
        json={"tier": 4, "domain": "ArchPrime", "action": "read_thing", "requestor": "agent-1"},
    )
    record_id = submit_resp.json()["record_id"]
    assert submit_resp.json()["state"] == "approved"

    decision_resp = client.post(
        f"/governance/actions/{record_id}/cab-decision",
        json={"approver": "human-1", "approved": True},
    )
    assert decision_resp.status_code == 409
    assert decision_resp.json()["error"] == "invalid_state"


def test_route_post_rejects_missing_internal_secret(unauthenticated_client):
    resp = unauthenticated_client.post(
        "/governance/actions",
        json={"tier": 4, "domain": "ArchPrime", "action": "read_thing", "requestor": "agent-1"},
    )
    assert resp.status_code == 403


def test_route_post_rejects_wrong_internal_secret(unauthenticated_client):
    resp = unauthenticated_client.post(
        "/governance/actions",
        json={"tier": 4, "domain": "ArchPrime", "action": "read_thing", "requestor": "agent-1"},
        headers={"X-Internal-Secret": "wrong-secret"},
    )
    assert resp.status_code == 403


def test_route_post_accepts_correct_internal_secret(unauthenticated_client):
    resp = unauthenticated_client.post(
        "/governance/actions",
        json={"tier": 4, "domain": "ArchPrime", "action": "read_thing", "requestor": "agent-1"},
        headers={"X-Internal-Secret": _TEST_INTERNAL_SECRET},
    )
    assert resp.status_code == 200


def test_route_get_does_not_require_internal_secret(unauthenticated_client):
    """GET routes are read-only and unauthenticated, same as matrix_suites_routes."""
    resp = unauthenticated_client.get("/governance/charters")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Regression tests for cubic's findings on commit a757f1dd
# ---------------------------------------------------------------------------


def test_context_safety_trigger_escalates(fsm):
    """cubic P1: sensitive_data_detected/prompt_injection_suspected previously had no
    effect on FSM state even when the charter declared them as escalation_triggers."""
    record = fsm.submit(
        ActionRequest(
            tier=4,
            domain="SecPrime",
            action="read_threat_intel",
            requestor="agent-sec",
            context={"sensitive_data_detected": True},
        )
    )
    assert record.state == "escalated"
    assert "sensitive_data_detected" in record.reason


def test_context_safety_trigger_absent_does_not_escalate(fsm):
    record = fsm.submit(
        ActionRequest(
            tier=4,
            domain="SecPrime",
            action="read_threat_intel",
            requestor="agent-sec",
            context={},
        )
    )
    assert record.state == "approved"


def test_context_trigger_not_declared_by_charter_is_ignored(fsm):
    """Only triggers the charter actually declares in escalation_triggers should fire —
    a context flag for an undeclared trigger must not affect the outcome."""
    record = fsm.submit(
        ActionRequest(
            tier=4,
            domain="ArchPrime",
            action="read_thing",
            requestor="agent-1",
            context={"production_change": True},  # ALLOWED_ONLY doesn't declare this trigger
        )
    )
    assert record.state == "approved"


def test_escalation_severity_maps_to_observatory_critical(fsm, monkeypatch):
    """cubic P2: a critical-severity charter's escalation was previously always emitted
    as EventSeverity.WARNING, missing Observatory's CRITICAL archival path."""
    captured = []
    original_record = Observatory.record

    def spy_record(self, event_type, *, severity=None, **kwargs):
        captured.append((event_type, severity))
        return original_record(self, event_type, severity=severity, **kwargs)

    monkeypatch.setattr(Observatory, "record", spy_record)

    record = fsm.submit(
        ActionRequest(
            tier=4,
            domain="SecPrime",
            action="read_threat_intel",
            requestor="agent-sec",
            context={"sensitive_data_detected": True},
        )
    )
    assert record.state == "escalated"
    escalated_events = [c for c in captured if c[0] == "governance.action.escalated"]
    assert escalated_events
    assert escalated_events[-1][1] == EventSeverity.CRITICAL


def test_unassigned_escalation_logs_incident(fsm, monkeypatch):
    """cubic P2: unknown-action escalations previously never logged an AIIncident,
    making them invisible to governance incident views."""
    logged = []
    monkeypatch.setattr(
        fsm_module,
        "log_ai_incident",
        lambda **kw: logged.append(kw) or ai_governance_module.AIIncident(**kw),
    )
    record = fsm.submit(
        ActionRequest(tier=4, domain="ArchPrime", action="totally_unknown_action", requestor="a")
    )
    assert record.state == "escalated"
    assert len(logged) == 1
    assert logged[0]["model_id"] == "unassigned"


def test_freeze_logs_incident(fsm, monkeypatch):
    """cubic P2: freeze() previously never logged an AIIncident."""
    logged = []
    monkeypatch.setattr(
        fsm_module,
        "log_ai_incident",
        lambda **kw: logged.append(kw) or ai_governance_module.AIIncident(**kw),
    )
    record = fsm.submit(
        ActionRequest(tier=4, domain="ArchPrime", action="read_thing", requestor="agent-1")
    )
    fsm.freeze(record.record_id, reason="suspicious pattern")
    assert len(logged) == 1
    assert logged[0]["model_id"] == "test-allowed-only"


def test_transition_history_records_every_state(fsm):
    """cubic P2: escalation_records only stores current state (UPDATE overwrites it) —
    escalation_transitions must retain the full path."""
    record = fsm.submit(
        ActionRequest(tier=3, domain="CommPrime", action="transfer_funds", requestor="agent-2")
    )
    fsm.resolve_cab(record.record_id, approver="human-1", approved=True)
    fsm.complete(record.record_id)

    transitions = fsm.list_transitions(record.record_id)
    states = [t["state"] for t in transitions]
    assert states == [
        "validated",
        "policy_checked",
        "pending_cab",
        "approved",
        "executing",
        "completed",
    ]


def test_transition_history_survives_new_fsm_instance(registry, tmp_path, monkeypatch):
    """The whole point of a durable table: a fresh EscalationFSM (simulating a process
    restart) reading the same DB file must still see the full history."""
    monkeypatch.setattr(fsm_module, "_DB_PATH", tmp_path / "escalation_fsm.db")
    monkeypatch.setattr(cab_gate_module, "_DB_PATH", tmp_path / "cab_changes.db")
    monkeypatch.setattr(ai_governance_module, "_DB_PATH", tmp_path / "ai_governance.db")

    fsm1 = EscalationFSM(registry)
    record = fsm1.submit(
        ActionRequest(tier=4, domain="ArchPrime", action="read_thing", requestor="agent-1")
    )

    fsm2 = EscalationFSM(registry)
    transitions = fsm2.list_transitions(record.record_id)
    assert [t["state"] for t in transitions] == ["validated", "policy_checked", "approved"]


def test_resolve_cab_approve_actually_persists_in_cab_gate(fsm):
    """cubic P1: resolve_cab previously flipped FSM state to 'approved' without ever
    calling cab_gate.approve_change() — the underlying cab_changes row stayed 'pending'
    forever, letting a caller bypass MC-RULE-007 and leaving the two stores diverged."""
    record = fsm.submit(
        ActionRequest(tier=3, domain="CommPrime", action="transfer_funds", requestor="agent-2")
    )
    change_id = record.cab_change_id
    assert change_id is not None

    check_before = cab_gate_module.cab_gate.check_change(
        "governance.CommPrime.transfer_funds", change_id, "agent-2"
    )
    assert check_before["approved"] is False

    fsm.resolve_cab(record.record_id, approver="human-1", approved=True)

    check_after = cab_gate_module.cab_gate.check_change(
        "governance.CommPrime.transfer_funds", change_id, "agent-2"
    )
    assert check_after["approved"] is True


def test_cab_gate_get_approver_returns_persisted_approver(fsm):
    change_id = cab_gate_module.cab_gate.register_change(
        change_type="test", description="test", requestor="agent-1", risk="low"
    )
    assert cab_gate_module.cab_gate.get_approver(change_id) is None

    cab_gate_module.cab_gate.approve_change(change_id, approver="human-1")
    assert cab_gate_module.cab_gate.get_approver(change_id) == "human-1"


def test_cab_gate_get_approver_unknown_change_returns_none(fsm):
    assert cab_gate_module.cab_gate.get_approver("CAB-DOESNOTEXIST") is None


def test_resolve_cab_reject_actually_persists_in_cab_gate(fsm):
    """cubic P1, reject path: rejecting via the FSM must persist in cab_changes too,
    not just flip the FSM record to 'rejected' with nothing backing it."""
    record = fsm.submit(
        ActionRequest(tier=3, domain="CommPrime", action="transfer_funds", requestor="agent-2")
    )
    change_id = record.cab_change_id

    resolved = fsm.resolve_cab(record.record_id, approver="human-1", approved=False)
    assert resolved.state == "rejected"

    with cab_gate_module._get_conn() as conn:
        row = conn.execute(
            "SELECT status, approver FROM cab_changes WHERE change_id = ?", (change_id,)
        ).fetchone()
    assert row["status"] == "rejected"
    assert row["approver"] == "human-1"


def test_check_change_rejected_but_not_cab_required_is_not_reported_approved(fsm):
    """cubic P2: check_change()'s `approved if cab_required else True` shortcut
    previously ran even for a rejected change, so a rejected-but-not-cab-required
    change (e.g. later reclassified to low risk) could be reported as approved:true."""
    change_id = cab_gate_module.cab_gate.register_change(
        change_type="not-in-any-required-list",
        description="test",
        requestor="agent-1",
        risk="low",
    )
    cab_gate_module.cab_gate.reject_change(change_id, approver="human-1")

    result = cab_gate_module.cab_gate.check_change("not-in-any-required-list", change_id, "agent-1")
    assert result["approved"] is False
    assert "rejected" in result["reason"]


def test_reject_change_does_not_set_approved_at(fsm):
    """cubic P2: a rejected row previously carried a non-null approved_at, making the
    audit row read as an approval for a decision that was actually a rejection."""
    change_id = cab_gate_module.cab_gate.register_change(
        change_type="test", description="test", requestor="agent-1", risk="low"
    )
    cab_gate_module.cab_gate.reject_change(change_id, approver="human-1")

    with cab_gate_module._get_conn() as conn:
        row = conn.execute(
            "SELECT status, approved_at, decided_at FROM cab_changes WHERE change_id = ?",
            (change_id,),
        ).fetchone()
    assert row["status"] == "rejected"
    assert row["approved_at"] is None
    assert row["decided_at"] is not None


def test_approve_change_sets_both_approved_at_and_decided_at(fsm):
    change_id = cab_gate_module.cab_gate.register_change(
        change_type="test", description="test", requestor="agent-1", risk="low"
    )
    cab_gate_module.cab_gate.approve_change(change_id, approver="human-1")

    with cab_gate_module._get_conn() as conn:
        row = conn.execute(
            "SELECT status, approved_at, decided_at FROM cab_changes WHERE change_id = ?",
            (change_id,),
        ).fetchone()
    assert row["status"] == "approved"
    assert row["approved_at"] is not None
    assert row["decided_at"] is not None


def test_init_db_backfills_decided_at_for_legacy_rejected_rows_too(fsm):
    """cubic P2: an earlier revision of reject_change() (before decided_at existed)
    stored the rejection timestamp in approved_at despite the misleading name — see
    git history of reject_change(). The decided_at backfill in _init_db() originally
    only covered status='approved' rows, so upgrading a DB containing legacy rejected
    changes left them with decided_at=NULL, making decision-time reports misclassify
    already-resolved rejections as unresolved.

    Reproduces the actual legacy precondition (a table that predates the decided_at
    column at all — the backfill only ever runs the one time _init_db() adds that
    column, so re-running it against an already-migrated DB is a no-op and would
    prove nothing) with a hand-built rejected row whose rejection timestamp sits in
    approved_at, then runs _init_db() to confirm the backfill now recovers it.
    """
    with cab_gate_module._get_conn() as conn:
        conn.execute("DROP TABLE IF EXISTS cab_changes")
        conn.execute(
            """
            CREATE TABLE cab_changes (
                change_id    TEXT PRIMARY KEY,
                change_type  TEXT NOT NULL,
                description  TEXT NOT NULL,
                requestor    TEXT NOT NULL,
                risk         TEXT NOT NULL DEFAULT 'low',
                status       TEXT NOT NULL DEFAULT 'pending',
                approver     TEXT,
                created_at   REAL NOT NULL,
                approved_at  REAL
            )
            """
        )
        conn.execute(
            "INSERT INTO cab_changes "
            "(change_id, change_type, description, requestor, status, approver, "
            "created_at, approved_at) VALUES (?, 'test', 'test', 'agent-1', "
            "'rejected', 'human-1', ?, ?)",
            ("legacy-rejected-1", 1700000000.0, 1700000000.0),
        )
        conn.commit()

        cab_gate_module._init_db(conn)  # adds decided_at + runs the backfill

        row = conn.execute(
            "SELECT status, approved_at, decided_at FROM cab_changes WHERE change_id = ?",
            ("legacy-rejected-1",),
        ).fetchone()
    assert row["status"] == "rejected"
    assert row["decided_at"] == row["approved_at"] == 1700000000.0


def test_cab_gate_init_db_tolerates_concurrent_duplicate_column_race(fsm):
    """cubic P1: multiple Uvicorn workers can each observe 'decided_at' missing on a
    pre-migration DB and race through the ALTER TABLE — the loser must not crash API
    startup with 'duplicate column name: decided_at', it just lost the race.

    cubic P3 follow-up: the original version of this test called _init_db() twice on
    a connection whose very first CREATE TABLE IF NOT EXISTS already declares
    decided_at, so neither call ever reached the ALTER branch at all — it only proved
    _init_db() is safely re-runnable, not that a genuine PRAGMA-read-then-ALTER race
    is swallowed. This version starts from a table that's missing the column, then
    makes a *second* connection win the ALTER in the narrow window between _init_db()'s
    own PRAGMA read and its ALTER call — reproducing exactly what two racing workers
    would do to the same on-disk DB file — so _init_db() must hit and swallow the
    real 'duplicate column name' error, not just skip an ALTER it never attempted.
    """
    with cab_gate_module._get_conn() as conn:
        conn.execute("DROP TABLE IF EXISTS cab_changes")
        conn.execute(
            """
            CREATE TABLE cab_changes (
                change_id    TEXT PRIMARY KEY,
                change_type  TEXT NOT NULL,
                description  TEXT NOT NULL,
                requestor    TEXT NOT NULL,
                risk         TEXT NOT NULL DEFAULT 'low',
                status       TEXT NOT NULL DEFAULT 'pending',
                approver     TEXT,
                created_at   REAL NOT NULL,
                approved_at  REAL
            )
            """
        )
        conn.commit()

        class _RacingConn:
            """Wraps the real connection so the ALTER _init_db() is about to run
            loses a race to a 'second worker' — a fresh connection to the same
            on-disk DB file — that adds the column first."""

            def __init__(self, real):
                self._real = real

            def execute(self, sql, *args, **kwargs):
                if "ALTER TABLE cab_changes ADD COLUMN decided_at" in sql:
                    other_worker = cab_gate_module._get_conn()
                    try:
                        other_worker.execute("ALTER TABLE cab_changes ADD COLUMN decided_at REAL")
                        other_worker.commit()
                    finally:
                        other_worker.close()
                return self._real.execute(sql, *args, **kwargs)

            def commit(self):
                self._real.commit()

        cab_gate_module._init_db(_RacingConn(conn))  # must not raise

        existing_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(cab_changes)").fetchall()
        }
    assert "decided_at" in existing_cols


def test_cab_gate_alter_table_duplicate_column_error_message(fsm):
    """cubic P3: the previous name/docstring here claimed to prove the duplicate-
    column ALTER 'must be swallowed, not raised', but the assertion was
    pytest.raises(...) — i.e. it proved the opposite, that raw SQLite raises. It also
    never called _init_db(), so it exercised no production code at all.

    What this test actually documents: sqlite3's exact wording for a duplicate-column
    ALTER, which is what _init_db()'s except-clause substring-matches against
    ("duplicate column name" not in str(exc)) to decide whether to swallow an
    OperationalError or let it propagate. If a future sqlite3 version changed that
    wording, _init_db()'s match would silently stop working — this pins the string so
    that change fails loudly here instead. The actual swallow-and-continue behavior is
    exercised end-to-end by
    test_cab_gate_init_db_tolerates_concurrent_duplicate_column_race above.
    """
    import sqlite3

    with cab_gate_module._get_conn() as conn:
        # decided_at already exists via the fsm fixture's _init_db() call.
        with pytest.raises(sqlite3.OperationalError, match="duplicate column name: decided_at"):
            conn.execute("ALTER TABLE cab_changes ADD COLUMN decided_at REAL")


def test_resolve_cab_without_cab_change_id_raises(fsm, monkeypatch):
    """Defensive: a pending_cab record with no cab_change_id (shouldn't happen via
    submit(), but guards against future callers constructing records another way)
    must not silently succeed."""
    record = fsm.submit(
        ActionRequest(tier=3, domain="CommPrime", action="transfer_funds", requestor="agent-2")
    )
    with fsm_module._get_conn() as conn:
        conn.execute(
            "UPDATE escalation_records SET cab_change_id = NULL WHERE record_id = ?",
            (record.record_id,),
        )
        conn.commit()
    with pytest.raises(EscalationError, match="no associated cab_change_id"):
        fsm.resolve_cab(record.record_id, approver="human-1", approved=True)


def test_resolve_cab_retry_after_partial_failure_reconciles_instead_of_wedging(fsm):
    """cubic P2: simulates a process crash between cab_gate committing its decision
    and _update_state() completing — the escalation_records row is manually forced
    back to 'pending_cab' (as if the crash happened before that column updated) while
    cab_changes already shows 'approved'. A naive retry would call
    cab_gate.approve_change() again, which no-ops (WHERE status='pending' matches
    nothing) and previously raised as if nothing had been applied. It must instead
    recognize the already-persisted decision and complete the FSM transition."""
    record = fsm.submit(
        ActionRequest(tier=3, domain="CommPrime", action="transfer_funds", requestor="agent-2")
    )
    change_id = record.cab_change_id

    resolved = fsm.resolve_cab(record.record_id, approver="human-1", approved=True)
    assert resolved.state == "approved"

    # Force the FSM record back to pending_cab, simulating a crash between cab_gate's
    # commit and this FSM transition — cab_changes itself is left untouched (still
    # 'approved').
    with fsm_module._get_conn() as conn:
        conn.execute(
            "UPDATE escalation_records SET state = 'pending_cab' WHERE record_id = ?",
            (record.record_id,),
        )
        conn.commit()

    # cubic P2: retried by a *different* approver than the one who actually made the
    # persisted decision (human-1) — a reconciliation retry recognizing the
    # already-applied cab_changes row must not credit human-2 with a decision they
    # didn't make in the durable transition-history audit trail.
    retried = fsm.resolve_cab(record.record_id, approver="human-2", approved=True)
    assert retried.state == "approved"
    assert "human-2" not in retried.reason
    assert "Reconciled" in retried.reason
    # cubic P2 follow-up: the reconciled reason must still name who actually
    # decided (human-1), not drop accountability entirely.
    assert "human-1" in retried.reason

    with cab_gate_module._get_conn() as conn:
        row = conn.execute(
            "SELECT status, approver FROM cab_changes WHERE change_id = ?", (change_id,)
        ).fetchone()
    assert row["status"] == "approved"
    assert row["approver"] == "human-1"


def test_resolve_cab_conflicting_decision_raises(fsm):
    """A record already resolved the opposite way in cab_changes is a genuine
    conflict — not a safe retry — and must not be silently overwritten."""
    record = fsm.submit(
        ActionRequest(tier=3, domain="CommPrime", action="transfer_funds", requestor="agent-2")
    )
    fsm.resolve_cab(record.record_id, approver="human-1", approved=True)

    with fsm_module._get_conn() as conn:
        conn.execute(
            "UPDATE escalation_records SET state = 'pending_cab' WHERE record_id = ?",
            (record.record_id,),
        )
        conn.commit()

    with pytest.raises(EscalationError, match="conflicts with the requested decision"):
        fsm.resolve_cab(record.record_id, approver="human-2", approved=False)


def test_cab_gate_get_status_returns_none_for_unknown_change(fsm):
    assert cab_gate_module.cab_gate.get_status("CAB-DOESNOTEXIST") is None


def test_cab_gate_get_status_returns_raw_status(fsm):
    change_id = cab_gate_module.cab_gate.register_change(
        change_type="test", description="test", requestor="agent-1", risk="low"
    )
    assert cab_gate_module.cab_gate.get_status(change_id) == "pending"
    cab_gate_module.cab_gate.approve_change(change_id, approver="human-1")
    assert cab_gate_module.cab_gate.get_status(change_id) == "approved"


def test_ecdsa_check_catches_submodule_import(tmp_path):
    """cubic P1: `from ecdsa.keys import SigningKey` previously bypassed the regex,
    which only matched a bare `from ecdsa import ...`."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_ecdsa_direct_usage", "scripts/check_ecdsa_direct_usage.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    (tmp_path / "bad.py").write_text("from ecdsa.keys import SigningKey\n")
    mod.REPO_ROOT = tmp_path
    violations, errors = mod._scan_file(tmp_path / "bad.py")
    assert violations
    assert not errors


def test_ecdsa_check_ignores_comment_and_docstring(tmp_path):
    """cubic P2: the old line-based regex flagged ES256 mentioned in a comment or
    docstring (it flagged this very script's own module docstring)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_ecdsa_direct_usage", "scripts/check_ecdsa_direct_usage.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    (tmp_path / "good.py").write_text(
        "# mentions ES256 in a comment\n"
        "def f():\n"
        '    """Docstring mentioning ES256 for documentation only."""\n'
        "    return 1\n"
    )
    mod.REPO_ROOT = tmp_path
    violations, errors = mod._scan_file(tmp_path / "good.py")
    assert not violations
    assert not errors


def test_ecdsa_check_fails_closed_on_unparseable_file(tmp_path):
    """cubic P2: an unreadable/unparseable file was previously silently skipped
    (treated as clean); it must now be reported as an error instead."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_ecdsa_direct_usage", "scripts/check_ecdsa_direct_usage.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    (tmp_path / "broken.py").write_text("def broken(:\n")
    mod.REPO_ROOT = tmp_path
    violations, errors = mod._scan_file(tmp_path / "broken.py")
    assert not violations
    assert errors


def test_ecdsa_check_ignores_package_relative_import(tmp_path):
    """cubic P2: `from .ecdsa import ...` / `from ..ecdsa import ...` resolve within the
    current package, never to the third-party 'ecdsa' distribution this check is scoped
    to — node.level > 0 must not be treated as the real dependency."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_ecdsa_direct_usage", "scripts/check_ecdsa_direct_usage.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    (tmp_path / "local.py").write_text("from .ecdsa import helper\nfrom ..ecdsa import other\n")
    mod.REPO_ROOT = tmp_path
    violations, errors = mod._scan_file(tmp_path / "local.py")
    assert not violations
    assert not errors


def test_ecdsa_check_catches_constant_folded_algorithm(tmp_path):
    """cubic P1: a runtime ES256 literal assembled from constant pieces (string
    concatenation or an all-constant f-string) can bypass a bare-literal check while
    still exercising the vulnerable JWT path."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_ecdsa_direct_usage", "scripts/check_ecdsa_direct_usage.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    (tmp_path / "sneaky.py").write_text('ALG = "ES" + "256"\nALG2 = f"ES{\'256\'}"\n')
    mod.REPO_ROOT = tmp_path
    violations, errors = mod._scan_file(tmp_path / "sneaky.py")
    assert len(violations) == 2
    assert not errors


def test_ecdsa_check_literal_only_fstring_reports_once(tmp_path):
    """cubic P3: f"ES256" (no interpolation) parses as JoinedStr(values=[Constant
    ('ES256')]) — ast.walk visits both the JoinedStr and its child Constant, so
    without deduplication this one source occurrence was reported twice."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_ecdsa_direct_usage", "scripts/check_ecdsa_direct_usage.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    (tmp_path / "literal_fstring.py").write_text('ALG = f"ES256"\n')
    mod.REPO_ROOT = tmp_path
    violations, errors = mod._scan_file(tmp_path / "literal_fstring.py")
    assert len(violations) == 1
    assert not errors


def test_ecdsa_check_constant_folding_does_not_false_positive_on_partial_strings(tmp_path):
    """Concatenating unrelated strings must not trip the folded-constant check."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_ecdsa_direct_usage", "scripts/check_ecdsa_direct_usage.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    (tmp_path / "unrelated.py").write_text('GREETING = "hello" + "world"\n')
    mod.REPO_ROOT = tmp_path
    violations, errors = mod._scan_file(tmp_path / "unrelated.py")
    assert not violations
    assert not errors


def test_ecdsa_check_catches_algorithm_as_attribute(tmp_path):
    """cubic P1: `jwt.encode(..., algorithm=Algorithms.ES256)` selects the ECDSA path
    while a bare-literal-only check passes — the algorithm is an attribute access, not
    a string literal."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_ecdsa_direct_usage", "scripts/check_ecdsa_direct_usage.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    (tmp_path / "attr.py").write_text(
        "import jwt\njwt.encode({}, key, algorithm=Algorithms.ES256)\n"
    )
    mod.REPO_ROOT = tmp_path
    violations, errors = mod._scan_file(tmp_path / "attr.py")
    assert violations
    assert not errors


def test_ecdsa_check_catches_algorithm_as_bare_name(tmp_path):
    """A constant imported and referenced directly (`from jose.constants import
    ES256`) is a bare Name, not a string literal or an attribute access."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_ecdsa_direct_usage", "scripts/check_ecdsa_direct_usage.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    (tmp_path / "name.py").write_text("ALG = ES256\n")
    mod.REPO_ROOT = tmp_path
    violations, errors = mod._scan_file(tmp_path / "name.py")
    assert violations
    assert not errors


def test_ecdsa_check_catches_aliased_algorithm_import(tmp_path):
    """cubic P1: `from jose.constants import ES256 as ALG` binds the local name to
    'ALG', so every later reference to it is the identifier 'ALG', not 'ES256' — the
    ast.Name/Attribute checks (which match on the *local* identifier) would never see
    the literal 'ES256' again after this rename. The import statement itself, where
    the original imported name still appears as alias.name, is the only place left to
    catch it."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_ecdsa_direct_usage", "scripts/check_ecdsa_direct_usage.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    (tmp_path / "aliased.py").write_text("from jose.constants import ES256 as ALG\nx = ALG\n")
    mod.REPO_ROOT = tmp_path
    violations, errors = mod._scan_file(tmp_path / "aliased.py")
    assert violations
    assert not errors


def test_ecdsa_check_aliased_import_ignores_relative_import(tmp_path):
    """The aliased-import check should stay scoped like the ecdsa-module check —
    a package-relative import can't be the third-party dependency this check is
    scoped to."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_ecdsa_direct_usage", "scripts/check_ecdsa_direct_usage.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    (tmp_path / "relative.py").write_text("from .constants import ES256 as ALG\n")
    mod.REPO_ROOT = tmp_path
    violations, errors = mod._scan_file(tmp_path / "relative.py")
    assert not violations
    assert not errors


def test_escalation_transitions_index_created(fsm):
    """Supports list_transitions()'s per-record_id lookup without a full table scan
    as the append-only table grows."""
    with fsm_module._get_conn() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name='idx_escalation_transitions_record_id'"
        ).fetchone()
    assert row is not None


def test_update_state_does_not_insert_phantom_transition_for_unknown_record(fsm):
    """cubic P2: halt()/resolve_cab() etc. on a bogus record_id previously still
    appended a transition row for a record_id that was never inserted into
    escalation_records, polluting escalation_transitions without a parent action."""
    with pytest.raises(RecordNotFoundError):
        fsm.halt("ESC-DOESNOTEXIST", reason="test")

    with fsm_module._get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM escalation_transitions WHERE record_id = ?",
            ("ESC-DOESNOTEXIST",),
        ).fetchone()
    assert row["n"] == 0


def test_transitions_table_backfills_existing_records_on_upgrade(registry, tmp_path, monkeypatch):
    """cubic P2: a DB that already has escalation_records rows from before the
    escalation_transitions table existed must not silently report an empty history for
    them once the table is created."""
    db_path = tmp_path / "escalation_fsm.db"
    monkeypatch.setattr(fsm_module, "_DB_PATH", db_path)
    monkeypatch.setattr(cab_gate_module, "_DB_PATH", tmp_path / "cab_changes.db")
    monkeypatch.setattr(ai_governance_module, "_DB_PATH", tmp_path / "ai_governance.db")
    with cab_gate_module._get_conn() as conn:
        cab_gate_module._init_db(conn)

    # Simulate a pre-upgrade DB: escalation_records exists and has a row, but
    # escalation_transitions does not exist yet.
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE escalation_records (
            record_id     TEXT PRIMARY KEY,
            charter_id    TEXT NOT NULL,
            action        TEXT NOT NULL,
            requestor     TEXT NOT NULL,
            state         TEXT NOT NULL,
            created_at    REAL NOT NULL,
            updated_at    REAL NOT NULL,
            cab_change_id TEXT,
            reason        TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO escalation_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "ESC-PREEXISTING",
            "test-allowed-only",
            "read_thing",
            "agent-1",
            "approved",
            1.0,
            2.0,
            None,
            None,
        ),
    )
    conn.commit()
    conn.close()

    pre_upgrade_fsm = EscalationFSM(registry)
    transitions = pre_upgrade_fsm.list_transitions("ESC-PREEXISTING")
    assert len(transitions) == 1
    assert transitions[0]["state"] == "approved"
    assert transitions[0]["ts"] == 2.0


def test_transitions_backfill_sql_is_idempotent_under_concurrent_workers(fsm):
    """cubic P2: two Uvicorn workers can both observe the transitions table missing
    before either's CREATE TABLE commits, and both then run the backfill — the
    WHERE NOT EXISTS guard must make running it twice a no-op the second time,
    not duplicate every backfilled row."""
    record = fsm.submit(
        ActionRequest(tier=4, domain="ArchPrime", action="read_thing", requestor="agent-1")
    )
    backfill_sql = """
        INSERT INTO escalation_transitions (record_id, state, reason, ts)
        SELECT er.record_id, er.state, er.reason, er.updated_at
        FROM escalation_records er
        WHERE NOT EXISTS (
            SELECT 1 FROM escalation_transitions et WHERE et.record_id = er.record_id
        )
        """
    with fsm_module._get_conn() as conn:
        # The real submit() flow already populated transitions for this record, so
        # running the (idempotent) backfill again must insert nothing further.
        conn.execute(backfill_sql)
        conn.execute(backfill_sql)
        conn.commit()

    transitions = fsm.list_transitions(record.record_id)
    states = [t["state"] for t in transitions]
    assert states == ["validated", "policy_checked", "approved"]


def test_ecdsa_check_reports_nul_byte_file_as_error_not_crash(tmp_path):
    """cubic P2: ast.parse() raises ValueError (not SyntaxError) for source
    containing NUL bytes — that must be caught as a handled parse failure, not
    crash the whole CI job with an uncaught traceback."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_ecdsa_direct_usage", "scripts/check_ecdsa_direct_usage.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    (tmp_path / "nul.py").write_bytes(b"x = 1\x00\n")
    mod.REPO_ROOT = tmp_path
    violations, errors = mod._scan_file(tmp_path / "nul.py")
    assert not violations
    assert errors
