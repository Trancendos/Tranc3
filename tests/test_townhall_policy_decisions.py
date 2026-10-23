"""Fail-closed decisions for Town Hall policy evaluation."""

from __future__ import annotations

import pytest

from src.townhall.governance import (
    ComplianceResult,
    Policy,
    TownHall,
    overall_compliance_result,
)


@pytest.mark.parametrize(
    ("results", "expected"),
    [
        ({"gdpr": ComplianceResult.PASS}, ComplianceResult.PASS),
        ({"gdpr": ComplianceResult.PASS, "cost": ComplianceResult.WARN}, ComplianceResult.WARN),
        ({"gdpr": ComplianceResult.FAIL, "cost": ComplianceResult.WARN}, ComplianceResult.FAIL),
        ({"gdpr": ComplianceResult.UNKNOWN}, ComplianceResult.FAIL),
        (
            {"gdpr": ComplianceResult.PASS, "prince2": ComplianceResult.UNKNOWN},
            ComplianceResult.FAIL,
        ),
        ({}, ComplianceResult.FAIL),
        ({"invalid": "pass"}, ComplianceResult.FAIL),
    ],
)
def test_overall_decision_never_passes_incomplete_evidence(results, expected):
    assert overall_compliance_result(results) is expected


def test_unknown_requested_policy_is_not_silently_dropped():
    townhall = TownHall()
    requested = ["zero-cost", "nonexistent-mandatory-gate"]
    results = townhall.check({"monthly_cost_usd": 0}, policy_ids=requested, actor="test-actor")
    assert results == {
        "zero-cost": ComplianceResult.PASS,
        "nonexistent-mandatory-gate": ComplianceResult.UNKNOWN,
    }
    assert overall_compliance_result(results) is ComplianceResult.FAIL
    assert any(
        entry.policy_id == "nonexistent-mandatory-gate" and entry.result is ComplianceResult.UNKNOWN
        for entry in townhall._history
    )


def test_policy_returning_unrecognised_status_is_unknown():
    policy = Policy(
        id="malformed-check",
        name="Malformed check",
        framework="test",
        check=lambda context: "pass",
    )
    assert policy.evaluate({}) is ComplianceResult.UNKNOWN


@pytest.mark.asyncio
async def test_http_check_fails_closed_when_policy_cannot_be_evaluated(monkeypatch):
    from src.townhall import routes

    class IncompleteTownHall:
        def check(self, context, policy_ids=None, actor=None):
            return {"gdpr": ComplianceResult.PASS, "prince2": ComplianceResult.UNKNOWN}

    monkeypatch.setattr(routes, "get_townhall", lambda: IncompleteTownHall())
    response = await routes.compliance_check(
        {"personal_data": False}, policy_ids=["gdpr", "prince2"], actor="test-actor"
    )
    assert response["overall"] == "fail"
    assert response["results"] == {"gdpr": "pass", "prince2": "unknown"}
