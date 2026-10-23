"""Non-authorising operator readiness projections over existing PLM records."""

from types import SimpleNamespace as NS

import pytest

from src.townhall.gate_readiness import summarise_gate_readiness


def _criterion(criterion_id="validation.tested", mandatory=True, supplied_by="The Chaos Party"):
    return NS(id=criterion_id, mandatory=mandatory, supplied_by=supplied_by)


def _status(outcome=None, *, waived=False, mandatory=True, satisfied=None):
    evidence = (
        NS(id="EV-123", outcome=NS(value=outcome), reference="run-123", recorded_by="qa")
        if outcome is not None
        else None
    )
    return NS(
        criterion=_criterion(mandatory=mandatory),
        evidence=evidence,
        waiver=NS(approver="lead", reason="temporary exception") if waived else None,
        satisfied=(outcome == "pass" if satisfied is None else satisfied),
        waived=waived,
    )


def _gate(stage="validation", entries=()):
    return NS(
        deliverable_id="PLM-1", stage=NS(value=stage), criteria=list(entries), can_advance=False
    )


def _item(stage="validation"):
    return NS(id="PLM-1", stage=NS(value=stage), kind=NS(value="application"))


def test_missing_evidence_is_blocked_and_names_accountable_location():
    result = summarise_gate_readiness(_item(), _gate(entries=[_status()]))
    assert result["state"] == "blocked"
    assert result["blockers"] == [
        {
            "criterion_id": "validation.tested",
            "reason": "missing_evidence",
            "supplied_by": "The Chaos Party",
        }
    ]
    assert result["authorization_granted"] is False
    assert result["preview_only"] is True


@pytest.mark.parametrize(
    "outcome,reason", [("fail", "failed_evidence"), ("pending", "pending_evidence")]
)
def test_latest_failed_or_pending_record_remains_blocked(outcome, reason):
    result = summarise_gate_readiness(_item(), _gate(entries=[_status(outcome)]))
    assert result["state"] == "blocked"
    assert result["blockers"][0]["reason"] == reason


def test_recorded_pass_remains_unverified_not_authorised():
    result = summarise_gate_readiness(_item(), _gate(entries=[_status("pass")]))
    assert result["state"] == "recorded_evidence_unverified"
    assert result["recorded_evidence"][0]["evidence_id"] == "EV-123"
    assert result["blockers"] == []
    assert result["authorization_granted"] is False
    assert result["independent_evidence_verification"] is False


def test_waiver_is_not_treated_as_recorded_pass():
    result = summarise_gate_readiness(_item(), _gate(entries=[_status(waived=True)]))
    assert result["state"] == "waiver_review"
    assert result["waiver_reviews"] == ["validation.tested"]
    assert result["recorded_evidence"] == []
    assert result["authorization_granted"] is False


def test_pass_after_waiver_records_pass_but_discloses_waiver():
    result = summarise_gate_readiness(_item(), _gate(entries=[_status("pass", waived=True)]))
    assert result["state"] == "waiver_review"
    assert result["waiver_reviews"] == ["validation.tested"]
    assert result["recorded_evidence"][0]["outcome"] == "pass"


def test_inconsistent_satisfied_without_valid_evidence_blocks():
    result = summarise_gate_readiness(_item(), _gate(entries=[_status(satisfied=True)]))
    assert result["state"] == "blocked"
    assert result["blockers"][0]["reason"] == "inconsistent_evidence"


def test_optional_missing_evidence_does_not_block():
    result = summarise_gate_readiness(
        _item(), _gate(entries=[_status(mandatory=False), _status("pass")])
    )
    assert result["state"] == "recorded_evidence_unverified"
    assert result["blockers"] == []


def test_release_snapshot_lists_bundled_policy_requirements_but_does_not_evaluate():
    result = summarise_gate_readiness(_item("release"), _gate("release", [_status("pass")]))
    assert result["policy_bundle"]["policy_ids"] == ["zero-cost", "gdpr", "prince2"]
    assert result["policy_bundle"]["evaluated"] is False
    assert result["authorization_granted"] is False


def test_mismatched_stage_fails_instead_of_blending_snapshots():
    with pytest.raises(ValueError, match="inconsistent PLM snapshot"):
        summarise_gate_readiness(_item("build"), _gate("validation", [_status("pass")]))


def test_mismatched_deliverable_fails_instead_of_blending_snapshots():
    gate = _gate(entries=[_status("pass")])
    gate.deliverable_id = "PLM-OTHER"
    with pytest.raises(ValueError, match="inconsistent PLM snapshot"):
        summarise_gate_readiness(_item(), gate)


def test_terminal_empty_gate_does_not_imply_compliance():
    result = summarise_gate_readiness(_item("closed"), _gate("closed", []))
    assert result["state"] == "no_current_gate"
    assert result["authorization_granted"] is False
    assert result["recorded_evidence"] == []


def test_no_hidden_raw_evidence_reference_in_report():
    result = summarise_gate_readiness(_item(), _gate(entries=[_status("pass")]))
    assert "run-123" not in repr(result)


@pytest.fixture
def readiness_client(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from auth import get_current_user
    from src.townhall import plm_routes
    from src.townhall.plm import DeliverableKind, PlmService

    service = PlmService(db_path=tmp_path / "readiness.db")
    monkeypatch.setattr(plm_routes, "get_plm", lambda: service)
    app = FastAPI()
    app.include_router(plm_routes.router)
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "admin-1",
        "username": "admin-1",
        "role": "admin",
    }
    yield TestClient(app), app, service, DeliverableKind, get_current_user
    service.close()


def test_readiness_http_is_read_only_and_never_grants_authority(readiness_client):
    client, _, service, kinds, _ = readiness_client
    item = service.create("Demo", kinds.APPLICATION, "The Lab")
    r = client.get(f"/townhall/plm/deliverables/{item.id}/readiness")
    assert r.status_code == 200
    assert r.json()["state"] == "blocked"
    assert r.json()["authorization_granted"] is False
    assert service.get(item.id).stage.value == "concept"
    assert service.history(item.id) == []


def test_readiness_http_reports_recorded_pass_as_unverified(readiness_client):
    client, _, service, kinds, _ = readiness_client
    item = service.create("Demo", kinds.APPLICATION, "The Lab")
    service.submit_evidence(item.id, "concept.business-case", "BC-1", "pass", recorded_by="qa")
    r = client.get(f"/townhall/plm/deliverables/{item.id}/readiness")
    assert r.status_code == 200
    assert r.json()["state"] == "recorded_evidence_unverified"
    assert r.json()["independent_evidence_verification"] is False
    assert r.json()["authorization_granted"] is False


def test_readiness_http_denies_non_admin(readiness_client):
    client, app, service, kinds, dependency = readiness_client
    item = service.create("Demo", kinds.APPLICATION, "The Lab")
    app.dependency_overrides[dependency] = lambda: {"username": "reader", "role": "viewer"}
    r = client.get(f"/townhall/plm/deliverables/{item.id}/readiness")
    assert r.status_code == 403


def test_readiness_http_404_for_unknown_deliverable(readiness_client):
    client, _, _, _, _ = readiness_client
    r = client.get("/townhall/plm/deliverables/PLM-MISSING/readiness")
    assert r.status_code == 404
