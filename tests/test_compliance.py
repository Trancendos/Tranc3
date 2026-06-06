"""
Compliance Tests — error catalog completeness, OWASP Top 10, GDPR codes, rate-limit codes.

Tests verify that the system's declared contracts (error taxonomy, security headers,
compliance error codes) are fully implemented and structurally sound.
"""

from __future__ import annotations

import logging
import re

import pytest

_log = logging.getLogger("tranc3.tests.compliance")

# Expected error code format
_CODE_PATTERN = re.compile(r"^TRANC3-[A-Z]+-\d{3}$")


# ---------------------------------------------------------------------------
# Error catalog compliance
# ---------------------------------------------------------------------------


class TestErrorCatalogCompliance:
    def test_all_error_codes_match_format(self, caplog):
        from src.errors.error_catalog import ErrorCode

        violations = []
        for code in ErrorCode:
            if not _CODE_PATTERN.match(code.value):
                violations.append(code.value)
        _log.info("compliance.error_codes format violations=%d", len(violations))
        assert not violations, f"Bad format: {violations}"

    def test_all_required_domains_present(self, caplog):
        from src.errors.error_catalog import ErrorCode

        domains = {e.value.split("-")[1] for e in ErrorCode}
        required = {"AUTH", "RATE", "MODEL", "DB", "SEC", "COMP", "SYS"}
        missing = required - domains
        _log.info("compliance.error_codes domains=%s missing=%s", sorted(domains), sorted(missing))
        assert not missing, f"Missing error domains: {missing}"

    def test_auth_error_codes_complete(self, caplog):
        """AUTH domain must cover token lifecycle and user management."""
        from src.errors.error_catalog import ErrorCode

        auth = {e.name for e in ErrorCode if "AUTH" in e.value}
        _log.info("compliance.auth codes=%s", sorted(auth))
        for required in (
            "AUTH_TOKEN_EXPIRED",
            "AUTH_TOKEN_INVALID",
            "AUTH_TOKEN_MISSING",
            "AUTH_USER_NOT_FOUND",
            "AUTH_WRONG_PASSWORD",
            "AUTH_WEAK_PASSWORD",
        ):
            assert required in auth, f"Missing auth code: {required}"

    def test_rate_limit_codes_present(self, caplog):
        from src.errors.error_catalog import ErrorCode

        rate = [e for e in ErrorCode if "RATE" in e.value]
        _log.info("compliance.rate codes=%d", len(rate))
        assert len(rate) >= 2, "Need at least HOURLY and DAILY rate codes"

    def test_gdpr_compliance_codes_present(self, caplog):
        from src.errors.error_catalog import ErrorCode

        comp = [e for e in ErrorCode if "COMP" in e.value]
        names = [e.name for e in comp]
        _log.info("compliance.gdpr codes=%s", names)
        assert any("GDPR" in n for n in names), "COMP_GDPR_REQUIRED error code must exist"

    def test_security_codes_cover_owasp_categories(self, caplog):
        """SEC codes must cover: input blocking (A03), CORS (A01), integrity (A08), IP blocking."""
        from src.errors.error_catalog import ErrorCode

        sec = {e.name for e in ErrorCode if "SEC" in e.value}
        _log.info("compliance.owasp sec_codes=%s", sorted(sec))
        assert "SEC_INPUT_BLOCKED" in sec, "A03: injection blocking code required"
        assert "SEC_CORS_VIOLATION" in sec, "A01: CORS violation code required"
        assert "SEC_INTEGRITY_ALERT" in sec, "A08: integrity alert code required"
        assert "SEC_IP_BLOCKED" in sec, "IP blocking code required"

    def test_error_catalog_has_guidance_for_all_codes(self, caplog):
        """Every error must have self-healing or resolution guidance."""
        try:
            from src.errors.error_catalog import ERROR_DEFINITIONS
        except ImportError:
            pytest.skip("ERROR_DEFINITIONS not exported from error_catalog")  # type: ignore[unreachable]
            return  # unreachable, but helps static analysis
        missing_guidance = [
            code
            for code, defn in ERROR_DEFINITIONS.items()
            if not defn.get("guidance") and not defn.get("action")
        ]
        _log.info("compliance.guidance missing=%d", len(missing_guidance))
        assert not missing_guidance, f"No guidance for: {missing_guidance}"

    def test_http_statuses_are_valid(self, caplog):
        """Every error definition must map to a valid HTTP status code."""
        try:
            from src.errors.error_catalog import ERROR_DEFINITIONS
        except ImportError:
            pytest.skip("ERROR_DEFINITIONS not exported from error_catalog")  # type: ignore[unreachable]
            return  # unreachable, but helps static analysis
        # 200 is valid for informational/degraded-mode responses (echo mode, fallback active)
        valid = {200, 400, 401, 403, 404, 409, 422, 429, 500, 502, 503}
        invalid = []
        for code, defn in ERROR_DEFINITIONS.items():
            status = defn.get("http_status")
            if status and status not in valid:
                invalid.append((code, status))
        _log.info("compliance.http_status invalid=%d", len(invalid))
        assert not invalid, f"Invalid HTTP statuses: {invalid}"


# ---------------------------------------------------------------------------
# MCP / JSON-RPC protocol compliance
# ---------------------------------------------------------------------------


class TestMCPProtocolCompliance:
    @pytest.mark.asyncio
    async def test_initialize_returns_required_fields(self, caplog):
        from src.mcp.server import handle_rpc

        resp = await handle_rpc(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "clientInfo": {"name": "compliance", "version": "0"},
                },
            },
        )
        _log.info("compliance.mcp init resp keys=%s", list(resp.get("result", {}).keys()))
        assert "result" in resp
        r = resp["result"]
        assert "protocolVersion" in r
        assert "serverInfo" in r
        assert "capabilities" in r
        assert r["serverInfo"]["name"] == "the-spark"
        assert r["serverInfo"].get("grid") == "the-digital-grid"

    @pytest.mark.asyncio
    async def test_tools_list_schema_valid(self, caplog):
        from src.mcp.server import handle_rpc

        resp = await handle_rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tools = resp["result"]["tools"]
        _log.info("compliance.mcp tools_count=%d", len(tools))
        for t in tools:
            assert "name" in t
            assert "description" in t
            assert "inputSchema" in t

    @pytest.mark.asyncio
    async def test_unknown_method_returns_method_not_found(self, caplog):
        from src.mcp.server import handle_rpc

        resp = await handle_rpc(
            {"jsonrpc": "2.0", "id": 3, "method": "nonexistent_method", "params": {}},
        )
        _log.info("compliance.mcp unknown_method error=%s", resp.get("error", {}).get("code"))
        assert "error" in resp
        assert resp["error"]["code"] == -32601  # Method not found

    @pytest.mark.asyncio
    async def test_invalid_jsonrpc_version_rejected(self, caplog):
        from src.mcp.server import handle_rpc

        resp = await handle_rpc({"jsonrpc": "1.0", "id": 4, "method": "initialize", "params": {}})
        _log.info("compliance.mcp bad_version error_code=%s", resp.get("error", {}).get("code"))
        assert "error" in resp
        assert resp["error"]["code"] == -32600  # Invalid request

    @pytest.mark.asyncio
    async def test_resources_have_spark_and_grid_uris(self, caplog):
        from src.mcp.server import handle_rpc

        resp = await handle_rpc(
            {"jsonrpc": "2.0", "id": 5, "method": "resources/list", "params": {}},
        )
        uris = {r["uri"] for r in resp["result"]["resources"]}
        _log.info("compliance.mcp resource_uris=%s", sorted(uris))
        assert any(u.startswith("spark://") for u in uris)
        assert any(u.startswith("grid://") for u in uris)


# ---------------------------------------------------------------------------
# Digital Grid workflow contract compliance
# ---------------------------------------------------------------------------


class TestDigitalGridContractCompliance:
    def test_workflow_dict_has_engine_field(self, caplog, sample_workflow_definitions):
        from src.workflow.builder import GRID_ENGINE

        for name, wf in sample_workflow_definitions.items():
            d = wf.to_dict()
            _log.info("compliance.grid wf=%s engine=%s", name, d.get("engine"))
            assert d.get("engine") == GRID_ENGINE, f"Workflow {name} missing engine field"

    def test_execution_state_fields_complete(self, caplog):
        import uuid

        from src.workflow.executor import ExecutionState

        state = ExecutionState(
            execution_id=str(uuid.uuid4()),
            workflow_id="test",
            status="running",
        )
        d = {
            "execution_id": state.execution_id,
            "workflow_id": state.workflow_id,
            "status": state.status,
            "elapsed_ms": state.elapsed_ms,
        }
        _log.info("compliance.grid execution_state keys=%s", list(d.keys()))
        for key in ("execution_id", "workflow_id", "status", "elapsed_ms"):
            assert key in d

    def test_node_result_fields_complete(self, caplog):
        from src.workflow.nodes import NodeResult

        r = NodeResult(node_id="n1", success=True, output={"x": 1}, error=None, duration_ms=5.0)
        _log.info("compliance.grid node_result success=%s duration=%.1f", r.success, r.duration_ms)
        assert r.node_id == "n1"
        assert r.success is True
        assert r.duration_ms == 5.0
        assert r.error is None


# ---------------------------------------------------------------------------
# Billing / rate-limit compliance
# ---------------------------------------------------------------------------


class TestBillingCompliance:
    def test_free_tier_rate_limit_enforced(self, caplog):
        try:
            from src.monetisation.billing import BillingTier, check_rate_limit
        except ImportError:
            pytest.skip("billing module not in this environment")
        allowed, err = check_rate_limit("free-user", BillingTier.FREE, 101)
        _log.info("compliance.billing free_tier allowed=%s err=%s", allowed, err)
        assert not allowed

    def test_all_billing_tiers_defined(self, caplog):
        try:
            from src.monetisation.billing import BillingTier
        except ImportError:
            pytest.skip("billing module not in this environment")
        tier_names = [t.name for t in BillingTier]
        _log.info("compliance.billing tiers=%s", tier_names)
        for required in ("FREE", "PRO", "BUSINESS"):
            assert required in tier_names or any(
                required.lower() in n.lower() for n in tier_names
            ), f"Missing billing tier: {required}"


# ---------------------------------------------------------------------------
# DEFSTAN Compliance Checker tests
# ---------------------------------------------------------------------------


class TestDEFSTANComplianceChecker:
    """Tests for the DEFSTAN compliance framework tooling."""

    def test_register_loads_without_error(self):
        """compliance/register.yaml loads cleanly."""
        from src.compliance.checker import load_and_check, REGISTER_PATH

        if not REGISTER_PATH.exists():
            import pytest
            pytest.skip("compliance/register.yaml not found")
        report = load_and_check(REGISTER_PATH)
        assert report is not None
        assert len(report.requirements) > 0

    def test_all_required_fields_present(self):
        """Every requirement has id, standard, title, status."""
        from src.compliance.checker import load_and_check, REGISTER_PATH

        if not REGISTER_PATH.exists():
            import pytest
            pytest.skip("compliance/register.yaml not found")
        report = load_and_check(REGISTER_PATH)
        for r in report.requirements:
            assert r.req_id, f"Missing id in requirement"
            assert r.standard, f"Missing standard in {r.req_id}"
            assert r.title, f"Missing title in {r.req_id}"
            assert r.status in (
                "COMPLIANT", "PARTIAL", "PLANNED", "WAIVED", "NA", "N/A"
            ), f"Invalid status '{r.status}' in {r.req_id}"

    def test_no_duplicate_requirement_ids(self):
        """No two requirements share the same ID."""
        from src.compliance.checker import load_and_check, REGISTER_PATH

        if not REGISTER_PATH.exists():
            import pytest
            pytest.skip("compliance/register.yaml not found")
        report = load_and_check(REGISTER_PATH)
        ids = [r.req_id for r in report.requirements]
        duplicates = [i for i in ids if ids.count(i) > 1]
        assert not duplicates, f"Duplicate requirement IDs: {set(duplicates)}"

    def test_requirement_id_format(self):
        """All IDs match REQ-{AREA}-{NNN} format."""
        import re
        from src.compliance.checker import load_and_check, REGISTER_PATH

        if not REGISTER_PATH.exists():
            import pytest
            pytest.skip("compliance/register.yaml not found")
        pattern = re.compile(r"^REQ-[A-Z]{2,4}-\d{3}$")
        report = load_and_check(REGISTER_PATH)
        bad = [r.req_id for r in report.requirements if not pattern.match(r.req_id)]
        assert not bad, f"Malformed requirement IDs: {bad}"

    def test_compliance_score_is_computed(self):
        """Overall compliance score is a float between 0 and 100."""
        from src.compliance.checker import load_and_check, REGISTER_PATH

        if not REGISTER_PATH.exists():
            import pytest
            pytest.skip("compliance/register.yaml not found")
        report = load_and_check(REGISTER_PATH)
        assert 0.0 <= report.overall_score <= 100.0

    def test_area_scores_computed(self):
        """Area summaries are populated for all 7 standard areas."""
        from src.compliance.checker import load_and_check, REGISTER_PATH, AREA_STANDARDS

        if not REGISTER_PATH.exists():
            import pytest
            pytest.skip("compliance/register.yaml not found")
        report = load_and_check(REGISTER_PATH)
        for area in AREA_STANDARDS:
            assert area in report.areas, f"Area {area} missing from report"
            a = report.areas[area]
            assert a.total > 0, f"Area {area} has no requirements"
            assert 0.0 <= a.score_pct <= 100.0

    def test_report_generation_produces_valid_json(self):
        """generate_json produces valid JSON with required top-level keys."""
        import json
        from src.compliance.checker import load_and_check, REGISTER_PATH
        from src.compliance.report_generator import generate_json

        if not REGISTER_PATH.exists():
            import pytest
            pytest.skip("compliance/register.yaml not found")
        report = load_and_check(REGISTER_PATH)
        json_str = generate_json(report)
        data = json.loads(json_str)
        for key in ("overall_score", "areas", "requirements", "generated_at"):
            assert key in data, f"Missing key '{key}' in JSON report"

    def test_report_generation_produces_markdown(self):
        """generate_markdown returns a non-empty string with expected headings."""
        from src.compliance.checker import load_and_check, REGISTER_PATH
        from src.compliance.report_generator import generate_markdown

        if not REGISTER_PATH.exists():
            import pytest
            pytest.skip("compliance/register.yaml not found")
        report = load_and_check(REGISTER_PATH)
        md = generate_markdown(report)
        assert isinstance(md, str)
        assert len(md) > 500
        assert "# DEFSTAN Compliance Report" in md
        assert "## Overall Compliance Score" in md

    def test_ci_mode_passes_at_expected_threshold(self):
        """CI mode returns exit code 0 when score is above threshold."""
        from src.compliance.checker import run, CI_PASS_THRESHOLD, load_and_check, REGISTER_PATH

        if not REGISTER_PATH.exists():
            import pytest
            pytest.skip("compliance/register.yaml not found")
        report = load_and_check(REGISTER_PATH)
        # Only assert exit code matches expectation — don't assert score value
        expected = 0 if report.overall_score >= CI_PASS_THRESHOLD else 1
        exit_code = run(["--ci", "--register", str(REGISTER_PATH)])
        assert exit_code == expected
