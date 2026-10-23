"""Recoverable outbox records for committed PLM stage decisions."""
from __future__ import annotations

import pytest

from src.townhall.plm import DeliverableKind, Outcome, PlmService, Stage


@pytest.fixture
def service(tmp_path):
    service = PlmService(db_path=tmp_path / "outbox.db")
    yield service
    service.close()


def _advance_one(service):
    item = service.create("Operator pilot", DeliverableKind.DOCUMENT, "The Library")
    service.submit_evidence(
        item.id, "concept.business-case", "business-case-1", Outcome.PASS, "tester"
    )
    assert service.advance(item.id, approver="admin").stage is Stage.INITIATION
    return item


def test_committed_gate_has_durable_pending_event(service):
    item = _advance_one(service)
    entries = service.pending_outbox()
    assert len(entries) == 1
    assert entries[0]["event_type"] == "plm.gate.passed"
    assert entries[0]["payload"]["deliverable_id"] == item.id
    assert entries[0]["payload"]["from_stage"] == "concept"
    assert entries[0]["payload"]["to_stage"] == "initiation"
    assert entries[0]["id"]


def test_pending_outbox_survives_restart(tmp_path):
    path = tmp_path / "outbox.db"
    first = PlmService(db_path=path)
    _advance_one(first)
    event_id = first.pending_outbox()[0]["id"]
    first.close()
    second = PlmService(db_path=path)
    try:
        assert second.pending_outbox()[0]["id"] == event_id
    finally:
        second.close()


def test_failed_publish_does_not_ack_event(service):
    _advance_one(service)
    claimed = service.claim_outbox(limit=1, lease_seconds=60)
    assert len(claimed) == 1
    entry = claimed[0]
    assert entry["attempt_count"] == 1
    assert service.ack_outbox(entry["id"], "wrong-claim-token") is False
    assert len(service.pending_outbox()) == 1


def test_successful_ack_removes_from_pending_without_deleting_history(service):
    _advance_one(service)
    event = service.claim_outbox(limit=1)[0]
    assert service.ack_outbox(event["id"], event["claim_token"]) is True
    assert service.pending_outbox() == []
    assert service.ack_outbox(event["id"], event["claim_token"]) is False


def test_claim_is_exclusive_until_lease_expires(service, monkeypatch):
    import src.townhall.plm as mod
    _advance_one(service)
    initial = service.claim_outbox(limit=1, lease_seconds=60)
    assert len(initial) == 1
    assert service.claim_outbox(limit=1, lease_seconds=60) == []
    current = mod.time.time()
    monkeypatch.setattr(mod.time, "time", lambda: current + 61)
    replay = service.claim_outbox(limit=1, lease_seconds=60)
    assert len(replay) == 1
    assert replay[0]["id"] == initial[0]["id"]
    assert replay[0]["attempt_count"] == 2
    assert replay[0]["claim_token"] != initial[0]["claim_token"]
    assert service.ack_outbox(initial[0]["id"], initial[0]["claim_token"]) is False


@pytest.mark.parametrize("limit,lease", [(0, 60), (-1, 60), (501, 60), (1, 0), (1, 601)])
def test_invalid_claim_parameters_rejected(service, limit, lease):
    with pytest.raises(ValueError):
        service.claim_outbox(limit=limit, lease_seconds=lease)


def test_blocked_gate_never_enqueues_transition(service):
    item = service.create("Blocked", DeliverableKind.DOCUMENT, "The Library")
    from src.townhall.plm import GateBlocked
    with pytest.raises(GateBlocked):
        service.advance(item.id, approver="admin")
    assert service.pending_outbox() == []


def test_outbox_payload_does_not_contain_raw_evidence_reference(service):
    _advance_one(service)
    assert "business-case-1" not in repr(service.pending_outbox())
