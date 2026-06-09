# tests/test_security_remediation.py
# Tests for Phase 10 security remediation: path validation, error handlers,
# log sanitization, and information exposure prevention.

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ─── Path Validation ─────────────────────────────────────────────────────────


class TestPathValidation:
    """Tests for Dimensional.path_validation module."""

    def test_validate_path_normal(self):
        from Dimensional.path_validation import validate_path

        with tempfile.TemporaryDirectory() as tmpdir:
            result = validate_path("subdir", tmpdir)
            assert str(result).startswith(tmpdir)

    def test_validate_path_traversal_blocked(self):
        from Dimensional.path_validation import PathTraversalError, validate_path

        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(PathTraversalError):
                validate_path("../../../etc/passwd", tmpdir)

    def test_validate_path_null_byte_blocked(self):
        from Dimensional.path_validation import PathTraversalError, validate_path

        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(PathTraversalError):
                validate_path("file\x00.txt", tmpdir)

    def test_validate_path_double_dot_blocked(self):
        from Dimensional.path_validation import PathTraversalError, validate_path

        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(PathTraversalError):
                validate_path("..", tmpdir)

    def test_validate_path_absolute_escaped(self):
        from Dimensional.path_validation import PathTraversalError, validate_path

        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(PathTraversalError):
                validate_path("/etc/passwd", tmpdir)

    def test_safe_join_normal(self):
        from Dimensional.path_validation import safe_join

        with tempfile.TemporaryDirectory() as tmpdir:
            result = safe_join(tmpdir, "repo", "src", "file.py")
            assert str(result).startswith(tmpdir)
            assert "repo/src/file.py" in str(result)

    def test_safe_join_traversal_blocked(self):
        from Dimensional.path_validation import PathTraversalError, safe_join

        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(PathTraversalError):
                safe_join(tmpdir, "..", "etc", "passwd")

    def test_safe_join_null_byte_blocked(self):
        from Dimensional.path_validation import PathTraversalError, safe_join

        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(PathTraversalError):
                safe_join(tmpdir, "file\x00name")

    def test_safe_join_absolute_component_blocked(self):
        from Dimensional.path_validation import PathTraversalError, safe_join

        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(PathTraversalError):
                safe_join(tmpdir, "/absolute/path")

    def test_safe_join_empty_component_blocked(self):
        from Dimensional.path_validation import safe_join

        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError):
                safe_join(tmpdir, "")

    def test_sanitize_filename_normal(self):
        from Dimensional.path_validation import sanitize_filename

        assert sanitize_filename("my-repo") == "my-repo"

    def test_sanitize_filename_traversal(self):
        from Dimensional.path_validation import sanitize_filename

        # Path separators should be stripped
        result = sanitize_filename("../evil")
        assert "/" not in result
        assert ".." not in result

    def test_sanitize_filename_null_byte(self):
        from Dimensional.path_validation import sanitize_filename

        result = sanitize_filename("file\x00name")
        assert "\x00" not in result

    def test_sanitize_filename_empty_raises(self):
        from Dimensional.path_validation import sanitize_filename

        with pytest.raises(ValueError):
            sanitize_filename("")

    def test_sanitize_filename_only_dots(self):
        from Dimensional.path_validation import sanitize_filename

        with pytest.raises(ValueError):
            sanitize_filename("...")


# ─── URL / SSRF Validation ───────────────────────────────────────────────────


class TestUrlValidation:
    """Tests for Dimensional.url_validation SSRF helpers."""

    def test_validate_ip_address_rejects_ipv4_mapped_loopback(self):
        from Dimensional.url_validation import SSRFError, validate_ip_address

        with pytest.raises(SSRFError, match="Private/reserved"):
            validate_ip_address("::ffff:127.0.0.1")

    def test_validate_ip_address_accepts_public_ipv4(self):
        from Dimensional.url_validation import validate_ip_address

        assert validate_ip_address("8.8.8.8") == "8.8.8.8"

    def test_validate_ip_address_rejects_private_ipv4(self):
        from Dimensional.url_validation import SSRFError, validate_ip_address

        with pytest.raises(SSRFError, match="Private/reserved"):
            validate_ip_address("10.0.0.1")

    def test_validate_workflow_id_rejects_traversal(self):
        from Dimensional.url_validation import SSRFError, validate_workflow_id

        with pytest.raises(SSRFError):
            validate_workflow_id("../etc/passwd")

    def test_validate_workflow_id_accepts_safe_id(self):
        from Dimensional.url_validation import validate_workflow_id

        assert validate_workflow_id("wf-123_abc") == "wf-123_abc"

    @patch("socket.getaddrinfo")
    def test_validate_url_rejects_private_resolution(self, mock_getaddrinfo):
        from Dimensional.url_validation import SSRFError, validate_url

        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("127.0.0.1", 443)),
        ]
        with pytest.raises(SSRFError, match="private/reserved"):
            validate_url("https://example.com/webhook")

    @patch("socket.getaddrinfo")
    def test_validate_webhook_url_accepts_public_resolution(self, mock_getaddrinfo):
        from Dimensional.url_validation import validate_webhook_url

        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("93.184.216.34", 443)),
        ]
        url = validate_webhook_url("https://example.com/hook")
        assert url == "https://example.com/hook"


# ─── Error Handlers ───────────────────────────────────────────────────────────


class TestErrorHandlers:
    """Tests for Dimensional.error_handlers module."""

    def test_safe_error_detail_production(self):
        from Dimensional.error_handlers import safe_error_detail

        with patch("Dimensional.error_handlers._IS_PROD", True):
            result = safe_error_detail(Exception("DB connection failed: /var/lib/db/data"), 500)
            # In production, should not expose internal paths
            assert "/var/lib/db/data" not in result
            assert "ref:" in result  # Should have a reference ID

    def test_safe_error_detail_development(self):
        from Dimensional.error_handlers import safe_error_detail

        with patch("Dimensional.error_handlers._IS_PROD", False):
            result = safe_error_detail(Exception("test error"), 500)
            # In development, the error message should be included but sanitized
            assert "test error" in result

    def test_safe_error_detail_strips_paths(self):
        from Dimensional.error_handlers import safe_error_detail

        with patch("Dimensional.error_handlers._IS_PROD", False):
            exc = Exception("Error loading /home/user/secret/config.yaml")
            result = safe_error_detail(exc, 500)
            assert "[PATH]" in result
            assert "/home/user/secret" not in result

    def test_safe_error_detail_no_exception(self):
        from Dimensional.error_handlers import safe_error_detail

        result = safe_error_detail(status_code=404)
        assert "not found" in result.lower()

    def test_safe_error_detail_truncation(self):
        from Dimensional.error_handlers import safe_error_detail

        with patch("Dimensional.error_handlers._IS_PROD", False):
            long_error = Exception("x" * 500)
            result = safe_error_detail(long_error, 500)
            assert len(result) <= 210  # 200 + "..."


# ─── Log Sanitization ────────────────────────────────────────────────────────


class TestLogSanitization:
    """Tests for Dimensional.sanitize module."""

    def test_sanitize_for_log_newlines(self):
        from Dimensional.sanitize import sanitize_for_log

        result = sanitize_for_log("hello\nworld\r\nmore")
        assert "\n" not in result
        assert "\r" not in result

    def test_sanitize_for_log_null_bytes(self):
        from Dimensional.sanitize import sanitize_for_log

        result = sanitize_for_log("hello\x00world")
        assert "\x00" not in result

    def test_sanitize_for_log_control_chars(self):
        from Dimensional.sanitize import sanitize_for_log

        result = sanitize_for_log("hello\x01\x02\x1bworld")
        assert "\x01" not in result
        assert "\x02" not in result
        assert "\x1b" not in result

    def test_sanitize_for_log_truncation(self):
        from Dimensional.sanitize import sanitize_for_log

        result = sanitize_for_log("x" * 2000, max_length=100)
        assert len(result) < 200
        assert "truncated" in result

    def test_sanitize_for_log_injection_attempt(self):
        from Dimensional.sanitize import sanitize_for_log

        # Classic log injection: inject a fake ERROR line
        malicious = "user\nERROR - Admin login successful from 10.0.0.1"
        result = sanitize_for_log(malicious)
        assert "\n" not in result
        assert "ERROR" not in result or "_" in result  # newline replaced with _

    def test_sanitize_dict_for_log_redaction(self):
        from Dimensional.sanitize import sanitize_dict_for_log

        data = {
            "username": "alice",
            "password": "secret123",
            "api_key": "sk-12345",
            "normal_field": "safe_value",
        }
        result = sanitize_dict_for_log(data)
        assert result["username"] == "alice"
        assert result["password"] == "[REDACTED]"
        assert result["api_key"] == "[REDACTED]"
        assert result["normal_field"] == "safe_value"

    def test_safe_logger_info(self):
        from Dimensional.sanitize import SafeLogger

        mock_logger = MagicMock()
        safe = SafeLogger(mock_logger)

        safe.info("User %s logged in", "alice\nFAKE ERROR")
        mock_logger.info.assert_called_once()
        args = mock_logger.info.call_args
        # The argument should be sanitized (no newlines)
        assert "\n" not in args[0][1]

    def test_safe_logger_warning(self):
        from Dimensional.sanitize import SafeLogger

        mock_logger = MagicMock()
        safe = SafeLogger(mock_logger)

        safe.warning("Failed: %s", "error\r\nINJECTED")
        args = mock_logger.warning.call_args
        assert "\r" not in args[0][1]
        assert "\n" not in args[0][1]


# ─── PersonalitySpawner Path Traversal Prevention ────────────────────────────


class TestSpawnerSecurity:
    """Tests for the path traversal fix in PersonalitySpawner."""

    def test_spawner_sanitizes_traversal_repo_name(self):
        """sanitize_filename strips traversal sequences; safe_join prevents escape."""
        from Dimensional.path_validation import sanitize_filename

        # "../../etc" gets sanitized to "..etc" (dots preserved, slashes stripped)
        result = sanitize_filename("../../etc")
        assert "/" not in result
        assert "\\" not in result

    def test_spawner_sanitizes_null_byte_repo_name(self):
        """sanitize_filename strips null bytes from filenames."""
        from Dimensional.path_validation import sanitize_filename

        result = sanitize_filename("repo\x00name")
        assert "\x00" not in result
        assert result == "reponame"

    def test_spawner_sanitizes_path_separators_in_name(self):
        """sanitize_filename strips path separators from filenames."""
        from Dimensional.path_validation import sanitize_filename

        result = sanitize_filename("repo/../../../etc")
        assert "/" not in result
        assert "\\" not in result


class TestSpawnerEndToEnd:
    """End-to-end tests for _resolve_output_base and safe_join in spawner."""

    def test_resolve_output_base_rejects_disallowed_dir(self):
        """_resolve_output_base should reject dirs outside _ALLOWED_OUTPUT_ROOTS."""
        from src.personality.spawner import PathTraversalError, _resolve_output_base

        with pytest.raises(PathTraversalError):
            _resolve_output_base("/etc")

    def test_resolve_output_base_accepts_cwd_subdir(self):
        """_resolve_output_base should accept a subdir of CWD."""
        import tempfile

        from src.personality.spawner import _resolve_output_base

        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            result = _resolve_output_base(tmpdir)
            assert result.is_absolute()

    def test_resolve_output_base_rejects_strict_outside(self):
        """_resolve_output_base should reject /var/log (outside allowed roots)."""
        from src.personality.spawner import PathTraversalError, _resolve_output_base

        with pytest.raises(PathTraversalError):
            _resolve_output_base("/var/log")

    def test_spawn_end_to_end_with_safe_dir(self):
        """spawn() should succeed with a safe output directory."""
        import tempfile

        from src.personality.spawner import PersonalitySpawner

        spawner = PersonalitySpawner()
        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            spawner.spawn("dorris-fontaine", "test-repo", tmpdir)
            target = Path(tmpdir) / "test-repo"
            assert target.exists()

    def test_spawn_end_to_end_rejects_outside_dir(self):
        """spawn() should raise when output_dir is outside allowed roots."""
        from src.personality.spawner import PathTraversalError, PersonalitySpawner

        spawner = PersonalitySpawner()
        with pytest.raises(PathTraversalError):
            spawner.spawn("dorris-fontaine", "test-repo", "/etc/tranc3-output")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
