# tests/test_errors.py
# Tests for src/errors/error_catalog.py
# Covers ErrorCode enum, ErrorDefinition, CATALOG, get_error,
# format_error_response, and ERROR_DEFINITIONS.

from __future__ import annotations

from src.errors.error_catalog import (
    CATALOG,
    ERROR_DEFINITIONS,
    ErrorCode,
    ErrorDefinition,
    format_error_response,
    get_error,
)

# ── ErrorCode enum ───────────────────────────────────────────────────


class TestErrorCode:
    def test_enum_is_str(self):
        assert isinstance(ErrorCode.AUTH_TOKEN_EXPIRED, str)

    def test_code_format(self):
        """All error codes follow the TRANC3-{DOMAIN}-{NNN} pattern."""
        for code in ErrorCode:
            parts = code.value.split("-")
            assert parts[0] == "TRANC3", f"Bad prefix in {code.value}"
            assert len(parts) == 3, f"Wrong segment count in {code.value}"
            assert parts[2].isdigit(), f"Non-numeric suffix in {code.value}"

    def test_all_values_unique(self):
        values = [c.value for c in ErrorCode]
        assert len(values) == len(set(values)), "Duplicate ErrorCode values"

    def test_domains_represented(self):
        """Every ErrorCode domain should appear in at least one member."""
        domains = {c.value.split("-")[1] for c in ErrorCode}
        expected = {
            "AUTH",
            "RATE",
            "MODEL",
            "DB",
            "QUANT",
            "CONS",
            "EVOL",
            "SWARM",
            "HOLO",
            "SEC",
            "COMP",
            "SYS",
            "WF",
            "VAL",
            "ENT",
        }
        assert domains == expected

    def test_known_auth_codes(self):
        assert ErrorCode.AUTH_TOKEN_EXPIRED.value == "TRANC3-AUTH-001"
        assert ErrorCode.AUTH_TOKEN_INVALID.value == "TRANC3-AUTH-002"
        assert ErrorCode.AUTH_TOKEN_MISSING.value == "TRANC3-AUTH-003"
        assert ErrorCode.AUTH_USER_NOT_FOUND.value == "TRANC3-AUTH-004"
        assert ErrorCode.AUTH_WRONG_PASSWORD.value == "TRANC3-AUTH-005"
        assert ErrorCode.AUTH_ACCOUNT_DISABLED.value == "TRANC3-AUTH-006"
        assert ErrorCode.AUTH_WEAK_PASSWORD.value == "TRANC3-AUTH-007"
        assert ErrorCode.AUTH_USER_EXISTS.value == "TRANC3-AUTH-008"

    def test_system_unknown(self):
        assert ErrorCode.SYS_UNKNOWN.value == "TRANC3-SYS-999"


# ── ErrorDefinition ──────────────────────────────────────────────────


class TestErrorDefinition:
    def test_fields_present(self):
        defn = ErrorDefinition(
            code=ErrorCode.SYS_UNKNOWN,
            http_status=500,
            title="Internal Server Error",
            message="An unexpected error occurred.",
            guidance="Check the application logs for details.",
            docs_url="/docs/errors/TRANC3-SYS-999",
        )
        assert defn.code == ErrorCode.SYS_UNKNOWN
        assert defn.http_status == 500
        assert defn.severity == "error"
        assert defn.retryable is False
        assert defn.self_heal is None

    def test_optional_fields(self):
        defn = ErrorDefinition(
            code=ErrorCode.RATE_HOURLY_EXCEEDED,
            http_status=429,
            title="Hourly Rate Limit Exceeded",
            message="You have exceeded your hourly request limit.",
            guidance="Upgrade your tier.",
            docs_url="/docs/errors/TRANC3-RATE-001",
            self_heal="show_upgrade_prompt",
            severity="warning",
            retryable=True,
        )
        assert defn.self_heal == "show_upgrade_prompt"
        assert defn.retryable is True
        assert defn.severity == "warning"


# ── CATALOG ──────────────────────────────────────────────────────────


class TestCatalog:
    def test_catalog_covers_all_error_codes(self):
        """Every ErrorCode member should have a CATALOG entry."""
        for code in ErrorCode:
            assert code in CATALOG, f"Missing CATALOG entry for {code}"

    def test_catalog_entries_match_code(self):
        """Each ErrorDefinition.code should match its CATALOG key."""
        for code, defn in CATALOG.items():
            assert defn.code is code

    def test_http_status_ranges(self):
        """All http_status values should be valid HTTP status codes."""
        for code, defn in CATALOG.items():
            assert 200 <= defn.http_status <= 599, (
                f"Invalid http_status {defn.http_status} for {code}"
            )

    def test_severity_values(self):
        """All severity values should be from the documented set."""
        valid = {"debug", "info", "warning", "error", "critical"}
        for code, defn in CATALOG.items():
            assert defn.severity in valid, f"Invalid severity '{defn.severity}' for {code}"

    def test_docs_url_format(self):
        """All docs_url entries start with /docs/errors/."""
        for code, defn in CATALOG.items():
            assert defn.docs_url.startswith("/docs/errors/"), (
                f"Bad docs_url for {code}: {defn.docs_url}"
            )

    def test_retryable_entries(self):
        """Verify specific entries that should be retryable."""
        retryable_codes = {
            ErrorCode.AUTH_TOKEN_EXPIRED,
            ErrorCode.RATE_HOURLY_EXCEEDED,
            ErrorCode.RATE_DAILY_EXCEEDED,
            ErrorCode.MODEL_NOT_LOADED,
            ErrorCode.MODEL_INFERENCE_FAILED,
            ErrorCode.DB_CONNECTION_FAILED,
        }
        for code in retryable_codes:
            assert CATALOG[code].retryable is True, f"{code} should be retryable"

    def test_self_heal_entries(self):
        """Verify specific entries that have self-heal actions."""
        assert CATALOG[ErrorCode.RATE_HOURLY_EXCEEDED].self_heal == "show_upgrade_prompt"
        assert CATALOG[ErrorCode.MODEL_NOT_LOADED].self_heal == "attempt_model_reload"
        assert CATALOG[ErrorCode.DB_CONNECTION_FAILED].self_heal == "use_sqlite_fallback"
        assert CATALOG[ErrorCode.DB_MIGRATION_NEEDED].self_heal == "run_migrations"


# ── get_error() ──────────────────────────────────────────────────────


class TestGetError:
    def test_known_code(self):
        defn = get_error(ErrorCode.AUTH_TOKEN_EXPIRED)
        assert defn.title == "Token Expired"

    def test_unknown_code_returns_sys_unknown(self):
        """get_error with a code not in CATALOG returns SYS_UNKNOWN."""
        defn = get_error(ErrorCode.SYS_UNKNOWN)
        assert defn.code == ErrorCode.SYS_UNKNOWN


# ── format_error_response() ─────────────────────────────────────────


class TestFormatErrorResponse:
    def test_basic_structure(self):
        result = format_error_response(ErrorCode.AUTH_TOKEN_EXPIRED)
        assert "error" in result
        err = result["error"]
        assert err["code"] == "TRANC3-AUTH-001"
        assert err["title"] == "Token Expired"
        assert "message" in err
        assert "guidance" in err
        assert "docs_url" in err
        assert "retryable" in err
        assert "severity" in err

    def test_custom_detail_overrides_message(self):
        result = format_error_response(
            ErrorCode.AUTH_TOKEN_INVALID,
            detail="Token is base64 garbage",
        )
        assert result["error"]["message"] == "Token is base64 garbage"

    def test_default_message_used_when_no_detail(self):
        result = format_error_response(ErrorCode.SYS_UNKNOWN)
        assert result["error"]["message"] == "An unexpected error occurred."

    def test_all_codes_produce_valid_response(self):
        """Every ErrorCode should produce a well-formed response."""
        for code in ErrorCode:
            result = format_error_response(code)
            err = result["error"]
            assert err["code"] == code.value
            assert isinstance(err["title"], str) and len(err["title"]) > 0
            assert isinstance(err["message"], str) and len(err["message"]) > 0
            assert isinstance(err["guidance"], str) and len(err["guidance"]) > 0
            assert isinstance(err["retryable"], bool)
            assert isinstance(err["severity"], str)


# ── ERROR_DEFINITIONS ────────────────────────────────────────────────


class TestErrorDefinitions:
    def test_has_entry_for_every_catalog_code(self):
        for code in CATALOG:
            assert code.value in ERROR_DEFINITIONS

    def test_entry_fields(self):
        entry = ERROR_DEFINITIONS["TRANC3-AUTH-001"]
        assert "guidance" in entry
        assert "action" in entry
        assert "http_status" in entry
        assert "severity" in entry
        assert "retryable" in entry
        assert "title" in entry

    def test_action_matches_self_heal(self):
        """The 'action' field should equal the ErrorDefinition's self_heal."""
        for code, defn in CATALOG.items():
            entry = ERROR_DEFINITIONS[code.value]
            assert entry["action"] == defn.self_heal

    def test_http_status_matches(self):
        for code, defn in CATALOG.items():
            entry = ERROR_DEFINITIONS[code.value]
            assert entry["http_status"] == defn.http_status
