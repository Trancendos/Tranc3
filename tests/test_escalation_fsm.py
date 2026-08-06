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


@pytest.fixture
def charters_dir(tmp_path):
    d = tmp_path / "charters"
    d.mkdir()
    for charter in (ALLOWED_ONLY, APPROVAL_REQUIRED, CONFIDENCE_GATED):
        with open(d / f"{charter['charter_id']}.json", "w", encoding="utf-8") as f:
            json.dump(charter, f)
    return d


@pytest.fixture
def registry(charters_dir):
    return CharterRegistry(charters_dir)


@pytest.fixture
def fsm(registry, tmp_path, monkeypatch):
    monkeypatch.setattr(fsm_module, "_DB_PATH", tmp_path / "escalation_fsm.db")
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
    assert len(registry.list_all()) == 3


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
