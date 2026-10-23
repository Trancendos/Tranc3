"""Server-owned policy bundles for advisory Townhall decision previews."""

from __future__ import annotations

import pytest

from src.townhall.decision_bundles import DecisionIntent, get_bundle, validate_context


def test_release_bundle_includes_non_optional_stage_gate():
    bundle = get_bundle(DecisionIntent.RELEASE)
    assert bundle.policy_ids == ("zero-cost", "gdpr", "prince2")
    assert bundle.version == 1


def test_change_bundle_cannot_be_reduced_by_client_policy_ids():
    bundle = get_bundle("change")
    assert bundle.policy_ids == ("zero-cost", "gdpr")
    assert "policy_ids" not in bundle.required_fields


@pytest.mark.parametrize("action", ["invalid", "", "RELEASE", "production-lockdown"])
def test_unknown_action_is_rejected(action):
    with pytest.raises(ValueError, match="unsupported Townhall decision intent"):
        get_bundle(action)


def test_missing_context_reports_fields_without_guessing_default_values():
    missing = validate_context("change", {})
    assert missing == (
        "monthly_cost_usd:required",
        "personal_data:required",
        "cross_border_transfer:required",
    )


@pytest.mark.parametrize("cost", [None, -1, "0", True, float("inf"), float("nan")])
def test_invalid_cost_is_blocked(cost):
    assert "monthly_cost_usd:invalid" in validate_context(
        "change", {"monthly_cost_usd": cost, "personal_data": False, "cross_border_transfer": False}
    )


def test_valid_non_sensitive_change_context():
    context = {"monthly_cost_usd": 0, "personal_data": False, "cross_border_transfer": False}
    assert validate_context("change", context) == ()


def test_personal_data_requires_nonempty_lawful_basis():
    context = {"monthly_cost_usd": 0, "personal_data": True, "cross_border_transfer": False}
    assert validate_context("change", context) == ("lawful_basis:required",)
    context["lawful_basis"] = "   "
    assert validate_context("change", context) == ("lawful_basis:invalid",)
    context["lawful_basis"] = "contract"
    assert validate_context("change", context) == ()


def test_cross_border_transfer_requires_explicit_adequacy_decision():
    context = {"monthly_cost_usd": 0, "personal_data": False, "cross_border_transfer": True}
    assert validate_context("change", context) == ("adequacy_decision:required",)
    context["adequacy_decision"] = "approved"
    assert validate_context("change", context) == ("adequacy_decision:invalid",)
    context["adequacy_decision"] = True
    assert validate_context("change", context) == ()


def test_release_requires_evidence_identifiers_but_does_not_verify_them():
    context = {"monthly_cost_usd": 0, "personal_data": False, "cross_border_transfer": False}
    assert validate_context("release", context) == (
        "build_evidence_id:required",
        "test_evidence_id:required",
    )
    context.update(build_evidence_id="artifact-001", test_evidence_id="run-456")
    assert validate_context("release", context) == ()


def test_policy_bundle_is_frozen():
    from dataclasses import FrozenInstanceError

    with pytest.raises(FrozenInstanceError):
        get_bundle("change").policy_ids = ("zero-cost",)


@pytest.mark.asyncio
async def test_change_preview_uses_server_mandatory_policies(monkeypatch):
    from src.townhall import routes
    from src.townhall.governance import ComplianceResult

    observed = {}

    class FakeHall:
        def check(self, context, policy_ids=None, actor=None):
            observed.update(policy_ids=policy_ids, actor=actor)
            return {"zero-cost": ComplianceResult.PASS, "gdpr": ComplianceResult.PASS}

    monkeypatch.setattr(routes, "get_townhall", lambda: FakeHall())
    response = await routes.townhall_decision_preview(
        DecisionIntent.CHANGE,
        {"monthly_cost_usd": 0, "personal_data": False, "cross_border_transfer": False,
         "policy_ids": ["zero-cost"]},
        actor="reviewer",
    )
    assert observed["policy_ids"] == ["zero-cost", "gdpr"]
    assert observed["actor"] == "reviewer"
    assert response["overall"] == "pass"
    assert response["authorization_granted"] is False
    assert response["preview_only"] is True


@pytest.mark.asyncio
async def test_incomplete_preview_never_calls_evaluator(monkeypatch):
    from src.townhall import routes

    class FailIfCalled:
        def check(self, context, policy_ids=None, actor=None):
            raise AssertionError("Invalid context must not be assessed")

    monkeypatch.setattr(routes, "get_townhall", lambda: FailIfCalled())
    response = await routes.townhall_decision_preview(DecisionIntent.CHANGE, {})
    assert response["overall"] == "fail"
    assert response["results"] == {"zero-cost": "unknown", "gdpr": "unknown"}
    assert "monthly_cost_usd:required" in response["input_errors"]
    assert response["authorization_granted"] is False


@pytest.mark.asyncio
async def test_release_preview_blocks_unimplemented_stage_gate(monkeypatch):
    from src.townhall import routes
    from src.townhall.governance import ComplianceResult

    class FakeHall:
        def check(self, context, policy_ids=None, actor=None):
            assert policy_ids == ["zero-cost", "gdpr", "prince2"]
            return {
                "zero-cost": ComplianceResult.PASS,
                "gdpr": ComplianceResult.PASS,
                "prince2": ComplianceResult.UNKNOWN,
            }

    monkeypatch.setattr(routes, "get_townhall", lambda: FakeHall())
    response = await routes.townhall_decision_preview(
        DecisionIntent.RELEASE,
        {"monthly_cost_usd": 0, "personal_data": False,
         "cross_border_transfer": False, "build_evidence_id": "a1", "test_evidence_id": "t1"},
    )
    assert response["overall"] == "fail"
    assert response["authorization_granted"] is False


@pytest.mark.asyncio
async def test_preview_does_not_pass_if_evaluator_omits_mandatory_policy(monkeypatch):
    from src.townhall import routes
    from src.townhall.governance import ComplianceResult

    class IncompleteHall:
        def check(self, context, policy_ids=None, actor=None):
            return {"zero-cost": ComplianceResult.PASS}

    monkeypatch.setattr(routes, "get_townhall", lambda: IncompleteHall())
    response = await routes.townhall_decision_preview(
        DecisionIntent.CHANGE,
        {"monthly_cost_usd": 0, "personal_data": False, "cross_border_transfer": False},
    )
    assert response["overall"] == "fail"
    assert response["results"]["gdpr"] == "unknown"


@pytest.mark.asyncio
async def test_preview_normalizes_malformed_policy_result(monkeypatch):
    from src.townhall import routes
    from src.townhall.governance import ComplianceResult

    class MalformedHall:
        def check(self, context, policy_ids=None, actor=None):
            return {"zero-cost": ComplianceResult.PASS, "gdpr": "pass"}

    monkeypatch.setattr(routes, "get_townhall", lambda: MalformedHall())
    response = await routes.townhall_decision_preview(
        DecisionIntent.CHANGE,
        {"monthly_cost_usd": 0, "personal_data": False, "cross_border_transfer": False},
    )
    assert response["overall"] == "fail"
    assert response["results"]["gdpr"] == "unknown"


@pytest.mark.asyncio
async def test_preview_policy_evaluator_exception_fails_closed(monkeypatch):
    from src.townhall import routes

    class BrokenHall:
        def check(self, context, policy_ids=None, actor=None):
            raise RuntimeError("system unavailable")

    monkeypatch.setattr(routes, "get_townhall", lambda: BrokenHall())
    response = await routes.townhall_decision_preview(
        DecisionIntent.CHANGE,
        {"monthly_cost_usd": 0, "personal_data": False, "cross_border_transfer": False},
    )
    assert response["overall"] == "fail"
    assert response["assessment_error"] is True
    assert response["authorization_granted"] is False
