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


@pytest.mark.parametrize("reference", [
    "", "https://attacker.example", "gha:0:" + SHA,
    "gha:1234:" + "a" * 39, "gha:1234:" + "x" * 40,
    "gha:1234:" + SHA + ":extra", "gha:-1:" + SHA,
])
def test_invalid_reference_is_unsupported_without_fetch(reference):
    def refuse(*args):
        raise AssertionError("network must not run")
    result = verify_run_reference(
        reference, trusted_repository="Trancendos/Tranc3",
        permitted_workflow_ids=frozenset({77}), fetch=refuse
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
        REF, trusted_repository="Trancendos/Tranc3",
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
