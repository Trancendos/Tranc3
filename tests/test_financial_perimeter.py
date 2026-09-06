"""
Tests for the financial regulatory perimeter enforced by MC-RULE-004
(src/compliance/magna_carta.py).

docs/compliance/FCA-ALIGNMENT.md v1.0.0 §2 stated that four financial uses were
"explicitly blocked by src/compliance/ai_governance.py". They were not. There was
no PROHIBITED_USES constant in that module or anywhere else; the four strings
appeared in that document and nowhere else in the repository. The check that does
exist (MC-RULE-004's prohibited_use_blocked) carried only the EU AI Act Article 5
terms, and could not fire in any case: the middleware sets use_case to None when
no route declares one, `data.get("use_case", "")` returns None for a *present*
key, and `use_case.lower()` raised AttributeError — which the rule engine catches
and, in advisory mode, converts into "passed". The perimeter check reported
success precisely because it had crashed.

These tests pin all three halves of the fix: the None-safety, the financial
terms, and the route coverage.
"""

from __future__ import annotations

import copy
import json

import pytest

RULE_004 = {
    "id": "MC-RULE-004",
    "type": "ai_governance",
    "severity": "high",
    "enabled": True,
    "checks": ["model_registered", "risk_tier_documented", "prohibited_use_blocked"],
    "prohibited_uses": ["social_scoring"],
}

BASE_CONFIG = {
    "profiles": {},
    "enforcement": {"mode": "advisory", "fail_closed_on_violation": False},
    "rules": [RULE_004],
}


def _make_compliance(monkeypatch, tmp_path):
    import src.compliance.magna_carta as mc

    path = tmp_path / "magna_carta_config.json"
    path.write_text(json.dumps(copy.deepcopy(BASE_CONFIG)))
    monkeypatch.setattr(mc, "MAGNA_CARTA_ENABLED", True)
    monkeypatch.setattr(mc, "MAGNA_CARTA_CONFIG_PATH", str(path))
    monkeypatch.setattr(mc, "MAGNA_CARTA_AUDIT", False)
    return mc.MagnaCartaCompliance()


def _violations(compliance, **request_data):
    result = compliance.check_request({"headers": {"authorization": "Bearer x"}, **request_data})
    return [v["rule_id"] for v in result["violations"]]


class TestPerimeterIsNoneSafe:
    def test_absent_use_case_does_not_crash_the_rule(self, monkeypatch, tmp_path):
        """
        The exact payload src/compliance/middleware.py builds for a request no
        route has annotated: both AI keys present, both None. This used to raise
        AttributeError inside the handler.
        """
        compliance = _make_compliance(monkeypatch, tmp_path)
        result = compliance.check_request(
            {
                "path": "/ai/generate",
                "headers": {"authorization": "Bearer x"},
                "model_id": None,
                "use_case": None,
            }
        )
        assert result["compliant"] is True
        # A genuine pass, not the swallowed-exception pass. Before the outcome
        # carried handler_errors those two were indistinguishable to a caller.
        assert result["handler_errors"] == []

    def test_a_raising_handler_is_still_reported_as_a_handler_error(self, monkeypatch, tmp_path):
        """
        The fail-safe path must stay reachable — this asserts that the previous
        test proves None-safety rather than proving the fail-safe was removed.
        """
        import src.compliance.magna_carta as mc

        compliance = _make_compliance(monkeypatch, tmp_path)
        monkeypatch.setattr(
            mc.MagnaCartaCompliance,
            "_rule_ai_governance",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        result = compliance.check_request({"path": "/ai/generate", "headers": {}})
        assert result["handler_errors"] == ["MC-RULE-004"]
        # Advisory mode still lets the request through — the fail-safe is intact,
        # it is just no longer silent.
        assert result["compliant"] is True


class TestFinancialPerimeter:
    @pytest.mark.parametrize(
        "use_case",
        [
            "financial_advice_regulated",
            "autonomous_binding_financial_decisions",
            "investment_recommendation_personal",
            "credit_recommendation_regulated",
        ],
    )
    def test_each_documented_prohibited_financial_use_is_flagged(
        self, monkeypatch, tmp_path, use_case
    ):
        compliance = _make_compliance(monkeypatch, tmp_path)
        assert "MC-RULE-004" in _violations(compliance, path="/ai/generate", use_case=use_case)

    def test_the_perimeter_survives_a_config_that_omits_it(self, monkeypatch, tmp_path):
        """
        BASE_CONFIG's rule declares only "social_scoring". The financial terms
        are held in code precisely so that a config edit cannot widen the
        perimeter without a code review.
        """
        compliance = _make_compliance(monkeypatch, tmp_path)
        assert RULE_004["prohibited_uses"] == ["social_scoring"]
        assert "MC-RULE-004" in _violations(
            compliance, path="/ai/generate", use_case="financial_advice_regulated"
        )

    def test_spaced_prose_matches_the_underscored_term(self, monkeypatch, tmp_path):
        compliance = _make_compliance(monkeypatch, tmp_path)
        assert "MC-RULE-004" in _violations(
            compliance,
            path="/ai/generate",
            use_case="produce an investment recommendation personal to this client",
        )

    def test_eu_ai_act_terms_still_flagged(self, monkeypatch, tmp_path):
        compliance = _make_compliance(monkeypatch, tmp_path)
        assert "MC-RULE-004" in _violations(
            compliance, path="/ai/generate", use_case="social_scoring of citizens"
        )

    def test_an_ordinary_ai_use_is_not_flagged(self, monkeypatch, tmp_path):
        compliance = _make_compliance(monkeypatch, tmp_path)
        assert (
            _violations(compliance, path="/ai/generate", use_case="summarise a support ticket")
            == []
        )


class TestPerimeterCoversRoutesTheAppActuallyServes:
    @pytest.mark.parametrize(
        "path",
        ["/luminous/query", "/models/route", "/tranc3ts/x", "/primes/intelligence"],
    )
    def test_mounted_ai_paths_are_in_scope(self, monkeypatch, tmp_path, path):
        """
        The original prefix tuple ("/ai/", "/infinity-ai/", "/model-router/")
        matched no router mounted by api.py, so MC-RULE-004 skipped every
        in-process request regardless of what it was asked to check.
        """
        compliance = _make_compliance(monkeypatch, tmp_path)
        assert "MC-RULE-004" in _violations(
            compliance, path=path, use_case="financial_advice_regulated"
        )

    def test_the_prefixes_correspond_to_real_mounted_routers(self):
        """
        Guards against the failure this test class exists to fix recurring: a
        prefix list that describes a routing layout nobody serves.
        """
        import re
        from pathlib import Path

        import src.compliance.magna_carta as mc

        repo = Path(__file__).resolve().parents[1]
        sources = list((repo / "src").rglob("*.py"))
        sources += [repo / "t2ance" / "router.py", repo / "trance_one" / "router.py"]
        mounted = set()
        for source in sources:
            if not source.is_file():
                continue
            text = source.read_text(encoding="utf-8", errors="ignore")
            mounted.update(re.findall(r'APIRouter\(\s*prefix="([^"]+)"', text))

        # The three worker-only prefixes are served by infinity-ai (:8009) and
        # model-router-service (:8033), not by api.py — they are exempt here.
        worker_only = {"/ai/", "/infinity-ai/", "/model-router/"}
        for prefix in mc._AI_ROUTE_PREFIXES:
            if prefix in worker_only:
                continue
            assert prefix.rstrip("/") in mounted, f"{prefix} matches no mounted router"


class TestDocumentationMatchesCode:
    def test_fca_alignment_does_not_claim_an_absent_constant(self):
        from pathlib import Path

        doc = (
            Path(__file__).resolve().parents[1] / "docs" / "compliance" / "FCA-ALIGNMENT.md"
        ).read_text(encoding="utf-8")
        assert "PROHIBITED_USES = [" not in doc, (
            "FCA-ALIGNMENT.md prints a PROHIBITED_USES constant that does not "
            "exist in any module; the perimeter lives in "
            "src/compliance/magna_carta.py as _PROHIBITED_FINANCIAL_USES"
        )
        assert "_PROHIBITED_FINANCIAL_USES" in doc
        assert "src/compliance/magna_carta.py" in doc

    def test_every_documented_term_exists_in_code(self):
        import src.compliance.magna_carta as mc

        assert mc._PROHIBITED_FINANCIAL_USES == {
            "financial_advice_regulated",
            "autonomous_binding_financial_decisions",
            "investment_recommendation_personal",
            "credit_recommendation_regulated",
        }
