"""External GitHub Actions verification never grants release authority."""

from __future__ import annotations

import pytest

from src.townhall.ci_evidence import verify_run_reference

SHA = "a" * 40
REF = f"gha:12345:{SHA}"


def _run(**overrides):
    payload = {
        "id": 12345,
        "status": "completed",
        "conclusion": "success",
        "head_sha": SHA,
        "workflow_id": 77,
        "repository": {"full_name": "Trancendos/Tranc3"},
    }
    payload.update(overrides)
    return payload


def _check(ref=REF, *, run=None, workflows=frozenset({77}), repo="Trancendos/Tranc3"):
    return verify_run_reference(
        ref,
        trusted_repository=repo,
        permitted_workflow_ids=workflows,
        fetch=lambda _repo, _run_id: _run() if run is None else run,
    )


def test_exact_successful_workflow_run_is_verified():
    result = _check()
    assert result["status"] == "verified"
    assert result["repository"] == "Trancendos/Tranc3"
    assert result["run_id"] == 12345
    assert result["authorization_granted"] is False


@pytest.mark.parametrize(
    ("altered", "reason"),
    [
        ({"head_sha": "b" * 40}, "commit_mismatch"),
        ({"workflow_id": 999}, "workflow_not_allowed"),
        ({"status": "in_progress"}, "not_successful"),
        ({"conclusion": "failure"}, "not_successful"),
        ({"conclusion": None}, "not_successful"),
        ({"id": 12346}, "run_mismatch"),
        ({"repository": {"full_name": "attacker/project"}}, "repository_mismatch"),
    ],
)
def test_untrusted_or_unsuccessful_run_is_rejected(altered, reason):
    result = _check(run=_run(**altered))
    assert result["status"] == "rejected"
    assert result["reason"] == reason
    assert result["authorization_granted"] is False


@pytest.mark.parametrize(
    "reference",
    [
        "",
        "https://attacker.example",
        "gha:0:" + SHA,
        "gha:1234:" + "a" * 39,
        "gha:1234:" + "x" * 40,
        "gha:1234:" + SHA + ":extra",
        "gha:-1:" + SHA,
    ],
)
def test_invalid_reference_is_unsupported_without_fetch(reference):
    def refuse(*args):
        raise AssertionError("network must not run")

    result = verify_run_reference(
        reference,
        trusted_repository="Trancendos/Tranc3",
        permitted_workflow_ids=frozenset({77}),
        fetch=refuse,
    )
    assert result["status"] == "unsupported"
    assert result["authorization_granted"] is False


def test_unconfigured_allowlist_fails_closed_without_fetch():
    def refuse(*args):
        raise AssertionError("network must not run")

    result = verify_run_reference(
        REF, trusted_repository="", permitted_workflow_ids=frozenset(), fetch=refuse
    )
    assert result["status"] == "unavailable"


def test_external_api_exception_is_unavailable_not_pass():
    result = verify_run_reference(
        REF,
        trusted_repository="Trancendos/Tranc3",
        permitted_workflow_ids=frozenset({77}),
        fetch=lambda repo, run_id: (_ for _ in ()).throw(RuntimeError("outage")),
    )
    assert result["status"] == "unavailable"
    assert result["authorization_granted"] is False


def test_malformed_provider_payload_is_not_verified():
    result = _check(run={"status": "completed", "conclusion": "success"})
    assert result["status"] == "rejected"


def test_no_token_leaks_through_api_result():
    result = _check(run={"message": "token secret", "status": "error"})
    assert "token secret" not in repr(result)


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from auth import get_current_user
    from src.townhall import plm_routes
    from src.townhall.plm import DeliverableKind, Outcome, PlmService, Stage

    service = PlmService(db_path=tmp_path / "ci-readiness.db")
    monkeypatch.setattr(plm_routes, "get_plm", lambda: service)
    app = FastAPI()
    app.include_router(plm_routes.router)
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "operator",
        "username": "operator",
        "role": "admin",
    }
    item = service.create("Pilot", DeliverableKind.DOCUMENT, "The Library")
    while service.get(item.id).stage != Stage.VALIDATION:
        for entry in service.gate_status(item.id).criteria:
            if entry.criterion.mandatory:
                service.submit_evidence(
                    item.id,
                    entry.criterion.id,
                    "existing-proof",
                    Outcome.PASS,
                    "operator",
                )
        service.advance(item.id, approver="operator")
    yield TestClient(app), app, service, item, get_current_user, plm_routes
    service.close()


def test_http_verifies_current_test_run_without_advancing(client, monkeypatch):
    request, _, service, item, _, routes = client
    service.submit_evidence(item.id, "validation.tested", REF, "pass", recorded_by="operator")
    monkeypatch.setattr(routes, "configured_run_verification", lambda ref: _check(ref))
    response = request.get(
        f"/townhall/plm/deliverables/{item.id}/evidence/validation.tested/verify-ci"
    )
    assert response.status_code == 200
    assert response.json()["status"] == "verified"
    assert response.json()["authorization_granted"] is False
    assert service.get(item.id).stage.value == "validation"


def test_http_blocks_non_admin_without_external_request(client, monkeypatch):
    request, app, service, item, auth, routes = client
    service.submit_evidence(item.id, "validation.tested", REF, "pass", "operator")
    app.dependency_overrides[auth] = lambda: {"sub": "viewer", "role": "viewer"}
    monkeypatch.setattr(
        routes,
        "configured_run_verification",
        lambda ref: (_ for _ in ()).throw(AssertionError("unexpected outbound request")),
    )
    response = request.get(
        f"/townhall/plm/deliverables/{item.id}/evidence/validation.tested/verify-ci"
    )
    assert response.status_code == 403


def test_http_failed_record_never_contacts_github(client, monkeypatch):
    request, _, service, item, _, routes = client
    service.submit_evidence(item.id, "validation.tested", REF, "fail", "operator")
    monkeypatch.setattr(
        routes,
        "configured_run_verification",
        lambda ref: (_ for _ in ()).throw(AssertionError("unexpected outbound request")),
    )
    response = request.get(
        f"/townhall/plm/deliverables/{item.id}/evidence/validation.tested/verify-ci"
    )
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert response.json()["authorization_granted"] is False
