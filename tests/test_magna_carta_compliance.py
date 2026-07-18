"""
Tests for the Magna Carta compliance rule engine (src/compliance/magna_carta.py)
and its ASGI middleware (src/compliance/middleware.py).

Neither module had any dedicated test coverage before this file (tests/test_compliance.py
only covers the error catalog / MCP protocol / GDPR error codes). The Magna-Carta repo's
own compliance_action_tracker.yaml (ACT-009) claims Tranc3-side enforcement is
"unimplemented" — it isn't; the code exists, it was just never exercised or proven to
actually enforce anything.
"""

from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

BASE_CONFIG = {
    "profiles": {"HIPAA_PROFILE": "disabled"},
    "enforcement": {
        "mode": "advisory",
        "fail_closed_on_violation": False,
    },
    "rules": [
        {
            "id": "MC-RULE-001",
            "type": "authentication",
            "severity": "high",
            "enabled": True,
            "checks": ["jwt_present"],
        },
        {
            "id": "MC-RULE-002",
            "type": "privacy",
            "severity": "medium",
            "enabled": True,
            "blocked_fields": [],
        },
        {
            "id": "MC-RULE-003",
            "type": "rate_limit",
            "severity": "low",
            "enabled": True,
            "tiers": {"free": {"requests_per_hour": 5}},
        },
    ],
}


def _write_config(tmp_path, enforcement_overrides=None):
    cfg = json.loads(json.dumps(BASE_CONFIG))
    cfg["enforcement"].update(enforcement_overrides or {})
    path = tmp_path / "magna_carta_config.json"
    path.write_text(json.dumps(cfg))
    return str(path)


def _make_compliance(monkeypatch, tmp_path, *, enabled=True, enforcement_overrides=None):
    import src.compliance.magna_carta as mc

    config_path = _write_config(tmp_path, enforcement_overrides)
    monkeypatch.setattr(mc, "MAGNA_CARTA_ENABLED", enabled)
    monkeypatch.setattr(mc, "MAGNA_CARTA_CONFIG_PATH", config_path)
    monkeypatch.setattr(mc, "MAGNA_CARTA_AUDIT", False)
    return mc.MagnaCartaCompliance()


class TestMagnaCartaComplianceEngine:
    def test_disabled_is_always_compliant(self, monkeypatch, tmp_path):
        compliance = _make_compliance(monkeypatch, tmp_path, enabled=False)
        result = compliance.check_request({"path": "/api/board"})
        assert result == {"compliant": True, "violations": [], "framework": "inactive"}

    def test_missing_config_file_is_advisory_pass(self, monkeypatch, tmp_path):
        import src.compliance.magna_carta as mc

        monkeypatch.setattr(mc, "MAGNA_CARTA_ENABLED", True)
        monkeypatch.setattr(mc, "MAGNA_CARTA_CONFIG_PATH", str(tmp_path / "does-not-exist.json"))
        compliance = mc.MagnaCartaCompliance()
        result = compliance.check_request({"path": "/api/board"})
        assert result["compliant"] is True
        assert result["framework"] == "inactive"

    def test_mc_rule_001_blocks_missing_jwt_on_protected_path(self, monkeypatch, tmp_path):
        compliance = _make_compliance(monkeypatch, tmp_path)
        result = compliance.check_request({"path": "/api/board", "headers": {}})
        assert result["compliant"] is False
        assert "MC-RULE-001" in [v["rule_id"] for v in result["violations"]]

    def test_mc_rule_001_passes_with_bearer_token(self, monkeypatch, tmp_path):
        compliance = _make_compliance(monkeypatch, tmp_path)
        result = compliance.check_request(
            {"path": "/api/board", "headers": {"authorization": "Bearer x"}}
        )
        assert "MC-RULE-001" not in [v["rule_id"] for v in result["violations"]]

    def test_mc_rule_001_skips_excluded_paths(self, monkeypatch, tmp_path):
        compliance = _make_compliance(monkeypatch, tmp_path)
        result = compliance.check_request({"path": "/health", "headers": {}})
        assert result["compliant"] is True

    def test_mc_rule_002_flags_pii_field_names(self, monkeypatch, tmp_path):
        compliance = _make_compliance(monkeypatch, tmp_path)
        result = compliance.check_request(
            {
                "path": "/api/board",
                "headers": {"authorization": "Bearer x"},
                "body_keys": ["password", "title"],
            }
        )
        assert "MC-RULE-002" in [v["rule_id"] for v in result["violations"]]

    def test_mc_rule_003_enforces_tier_limit(self, monkeypatch, tmp_path):
        compliance = _make_compliance(monkeypatch, tmp_path)
        result = compliance.check_request(
            {
                "path": "/api/board",
                "headers": {"authorization": "Bearer x"},
                "tenant_tier": "free",
                "request_count": 6,
            }
        )
        assert "MC-RULE-003" in [v["rule_id"] for v in result["violations"]]

    def test_disabled_rule_is_skipped(self, monkeypatch, tmp_path):
        import src.compliance.magna_carta as mc

        cfg = json.loads(json.dumps(BASE_CONFIG))
        for rule in cfg["rules"]:
            if rule["id"] == "MC-RULE-001":
                rule["enabled"] = False
        config_path = tmp_path / "magna_carta_config.json"
        config_path.write_text(json.dumps(cfg))

        monkeypatch.setattr(mc, "MAGNA_CARTA_ENABLED", True)
        monkeypatch.setattr(mc, "MAGNA_CARTA_CONFIG_PATH", str(config_path))
        monkeypatch.setattr(mc, "MAGNA_CARTA_AUDIT", False)
        compliance = mc.MagnaCartaCompliance()

        result = compliance.check_request({"path": "/api/board", "headers": {}})
        assert "MC-RULE-001" not in [v["rule_id"] for v in result["violations"]]

    def test_rule_handler_exception_fails_open_by_default(self, monkeypatch, tmp_path):
        compliance = _make_compliance(monkeypatch, tmp_path)

        def _boom(rule, data):
            raise RuntimeError("boom")

        monkeypatch.setattr(compliance, "_rule_authentication", _boom)
        result = compliance.check_request({"path": "/api/board", "headers": {}})
        # A handler crash must not itself surface as a blocking violation
        assert not [v for v in result["violations"] if v["rule_id"] == "MC-RULE-001"]

    def test_outcome_reports_fail_closed_flag(self, monkeypatch, tmp_path):
        """
        Regression test: check_request's outcome dict must expose whether
        enforcement.fail_closed_on_violation is active. MagnaCartaMiddleware.dispatch
        reads result["fail_closed"] to decide whether to actually block a request;
        before this fix that key was never populated, so fail-closed mode could
        never block anything regardless of what magna_carta_config.json said.
        """
        compliance = _make_compliance(
            monkeypatch, tmp_path, enforcement_overrides={"fail_closed_on_violation": True}
        )
        result = compliance.check_request({"path": "/api/board", "headers": {}})
        assert result["compliant"] is False
        assert result["fail_closed"] is True

    def test_outcome_fail_closed_false_by_default(self, monkeypatch, tmp_path):
        compliance = _make_compliance(monkeypatch, tmp_path)
        result = compliance.check_request({"path": "/api/board", "headers": {}})
        assert result["fail_closed"] is False


class TestMagnaCartaMiddleware:
    def _build_app(self, monkeypatch, tmp_path, *, enabled=True, enforcement_overrides=None):
        import src.compliance.magna_carta as mc
        from src.compliance.middleware import MagnaCartaMiddleware

        config_path = _write_config(tmp_path, enforcement_overrides)
        monkeypatch.setattr(mc, "MAGNA_CARTA_ENABLED", enabled)
        monkeypatch.setattr(mc, "MAGNA_CARTA_CONFIG_PATH", config_path)
        monkeypatch.setattr(mc, "MAGNA_CARTA_AUDIT", False)
        monkeypatch.setattr(mc, "compliance", mc.MagnaCartaCompliance())

        app = FastAPI()

        @app.get("/api/board")
        def board():
            return {"ok": True}

        @app.get("/health")
        def health():
            return {"ok": True}

        app.add_middleware(MagnaCartaMiddleware)
        return app

    def test_advisory_mode_adds_headers_but_never_blocks(self, monkeypatch, tmp_path):
        app = self._build_app(monkeypatch, tmp_path)
        client = TestClient(app)
        resp = client.get("/api/board")  # no Authorization header -> MC-RULE-001 violation
        assert resp.status_code == 200
        assert resp.headers["X-MC-Compliant"] == "false"
        assert int(resp.headers["X-MC-Violations"]) >= 1

    def test_skip_paths_bypass_the_engine_entirely(self, monkeypatch, tmp_path):
        app = self._build_app(monkeypatch, tmp_path)
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert "X-MC-Compliant" not in resp.headers

    def test_disabled_bypasses_the_engine_entirely(self, monkeypatch, tmp_path):
        app = self._build_app(monkeypatch, tmp_path, enabled=False)
        client = TestClient(app)
        resp = client.get("/api/board")
        assert resp.status_code == 200
        assert "X-MC-Compliant" not in resp.headers

    def test_fail_closed_blocks_high_severity_violation(self, monkeypatch, tmp_path):
        """
        End-to-end regression test: with enforcement.fail_closed_on_violation=true
        and a high-severity MC-RULE-001 violation (no bearer token on a protected
        path), the middleware must actually return 403 - not just log and pass
        the request through, which is what it silently did before this fix.
        """
        app = self._build_app(
            monkeypatch, tmp_path, enforcement_overrides={"fail_closed_on_violation": True}
        )
        client = TestClient(app)
        resp = client.get("/api/board")
        assert resp.status_code == 403
        body = resp.json()
        assert body["framework"] == "magna_carta_v1"
        assert any(v["rule_id"] == "MC-RULE-001" for v in body["violations"])

    def test_fail_closed_does_not_block_compliant_requests(self, monkeypatch, tmp_path):
        app = self._build_app(
            monkeypatch, tmp_path, enforcement_overrides={"fail_closed_on_violation": True}
        )
        client = TestClient(app)
        resp = client.get("/api/board", headers={"Authorization": "Bearer x"})
        assert resp.status_code == 200
