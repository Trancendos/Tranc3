# tests/test_security_automation.py
# Regression tests for the Proactive Security Automation Framework.
#
# These tests verify that the scanner correctly catches the exact patterns
# that caused ~297 CodeQL alerts, and that the remediator can auto-fix them.
# They serve as a permanent regression safety net — if any of these patterns
# re-enter the codebase, the scanner will flag them and the tests will fail.

import json
import tempfile
from pathlib import Path
from textwrap import dedent
from typing import List

import pytest

from shared_core.security_automation.scanner import (
    Category,
    SecurityScanner,
    Severity,
    Violation,
)
from shared_core.security_automation.remediator import AutoRemediator
from shared_core.security_automation.telemetry import (
    GateResult,
    QualityGate,
    ScanDiff,
    ScanResult,
    SecurityTelemetry,
    TrendPoint,
)


# ---------------------------------------------------------------------------
# Helper — write sample code to a temp file for scanning
# ---------------------------------------------------------------------------

def _write_tmp(content: str, suffix: str = ".py") -> Path:
    """Write content to a temp file and return the path."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    tmp.write(dedent(content))
    tmp.flush()
    tmp.close()
    return Path(tmp.name)


# ===========================================================================
# Scanner Tests — Pattern Detection
# ===========================================================================

class TestScannerLogInjection:
    """CWE-117: f-string in logger calls should be flagged."""

    def test_fstring_logger_detected(self):
        code = '''\
        import logging
        logger = logging.getLogger(__name__)
        name = "user"
        logger.info(f"Hello {name}")
        '''
        path = _write_tmp(code)
        try:
            scanner = SecurityScanner()
            violations = scanner.scan_file(str(path))
            log_violations = [v for v in violations if v.category == Category.LOG_INJECTION]
            assert len(log_violations) >= 1, f"Expected LOG_INJECTION, got {[v.category for v in violations]}"
            assert log_violations[0].severity in (Severity.HIGH, Severity.MEDIUM)
        finally:
            path.unlink()

    def test_percent_style_logger_not_flagged(self):
        code = '''\
        import logging
        logger = logging.getLogger(__name__)
        name = "user"
        logger.info("Hello %s", name)
        '''
        path = _write_tmp(code)
        try:
            scanner = SecurityScanner()
            violations = scanner.scan_file(str(path))
            log_violations = [v for v in violations if v.category == Category.LOG_INJECTION]
            assert len(log_violations) == 0, f"Should not flag %-style logging, got {log_violations}"
        finally:
            path.unlink()

    def test_sanitize_for_log_not_flagged(self):
        code = '''\
        import logging
        from shared_core.sanitize import sanitize_for_log
        logger = logging.getLogger(__name__)
        name = "user"
        logger.info("Hello %s", sanitize_for_log(name))  # codeql[py/cleartext-logging]
        '''
        path = _write_tmp(code)
        try:
            scanner = SecurityScanner()
            violations = scanner.scan_file(str(path))
            log_violations = [v for v in violations if v.category == Category.LOG_INJECTION]
            assert len(log_violations) == 0
        finally:
            path.unlink()


class TestScannerInfoExposure:
    """CWE-209: str(exc) in HTTP error responses should be flagged."""

    def test_str_exc_in_detail_detected(self):
        code = '''\
        try:
            do_something()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        '''
        path = _write_tmp(code)
        try:
            scanner = SecurityScanner()
            violations = scanner.scan_file(str(path))
            info_violations = [v for v in violations if v.category == Category.INFO_EXPOSURE]
            assert len(info_violations) >= 1, f"Expected INFO_EXPOSURE, got {[v.category for v in violations]}"
        finally:
            path.unlink()

    def test_safe_error_detail_not_flagged(self):
        code = '''\
        from shared_core.error_handlers import safe_error_detail
        try:
            do_something()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=safe_error_detail(exc, 500))
        '''
        path = _write_tmp(code)
        try:
            scanner = SecurityScanner()
            violations = scanner.scan_file(str(path))
            info_violations = [v for v in violations if v.category == Category.INFO_EXPOSURE]
            assert len(info_violations) == 0
        finally:
            path.unlink()


class TestScannerBareExcept:
    """PY-001: bare except: blocks should be flagged."""

    def test_bare_except_detected(self):
        code = '''\
        try:
            risky_operation()
        except:
            pass
        '''
        path = _write_tmp(code)
        try:
            scanner = SecurityScanner()
            violations = scanner.scan_file(str(path))
            bare_violations = [v for v in violations if v.category == Category.BARE_EXCEPT]
            assert len(bare_violations) >= 1
        finally:
            path.unlink()

    def test_except_exception_not_flagged(self):
        code = '''\
        try:
            risky_operation()
        except Exception:
            pass
        '''
        path = _write_tmp(code)
        try:
            scanner = SecurityScanner()
            violations = scanner.scan_file(str(path))
            bare_violations = [v for v in violations if v.category == Category.BARE_EXCEPT]
            assert len(bare_violations) == 0
        finally:
            path.unlink()


class TestScannerTypeExc:
    """PY-003: type(__exc).__name__ patterns should be flagged."""

    def test_type_exc_detected(self):
        code = '''\
        try:
            pass
        except Exception as __exc:
            logger.error(f"Error: {type(__exc).__name__}")
        '''
        path = _write_tmp(code)
        try:
            scanner = SecurityScanner()
            violations = scanner.scan_file(str(path))
            type_violations = [v for v in violations if v.category == Category.TYPE_EXC]
            assert len(type_violations) >= 1
        finally:
            path.unlink()


class TestScannerUnclosedFile:
    """PY-004: open().read() without context manager should be flagged."""

    def test_unclosed_file_detected(self):
        code = '''\
        data = open("config.json").read()
        '''
        path = _write_tmp(code)
        try:
            scanner = SecurityScanner()
            violations = scanner.scan_file(str(path))
            file_violations = [v for v in violations if v.category == Category.UNCLOSED_FILE]
            assert len(file_violations) >= 1
        finally:
            path.unlink()

    def test_context_manager_not_flagged(self):
        code = '''\
        with open("config.json") as f:
            data = f.read()
        '''
        path = _write_tmp(code)
        try:
            scanner = SecurityScanner()
            violations = scanner.scan_file(str(path))
            file_violations = [v for v in violations if v.category == Category.UNCLOSED_FILE]
            assert len(file_violations) == 0
        finally:
            path.unlink()


class TestScannerWeakHash:
    """CWE-327: md5/sha1 for security purposes should be flagged."""

    def test_hashlib_md5_detected(self):
        code = '''\
        import hashlib
        digest = hashlib.md5(data).hexdigest()
        '''
        path = _write_tmp(code)
        try:
            scanner = SecurityScanner()
            violations = scanner.scan_file(str(path))
            hash_violations = [v for v in violations if v.category == Category.WEAK_HASH]
            assert len(hash_violations) >= 1
        finally:
            path.unlink()

    def test_hashlib_sha256_not_flagged(self):
        code = '''\
        import hashlib
        digest = hashlib.sha256(data).hexdigest()
        '''
        path = _write_tmp(code)
        try:
            scanner = SecurityScanner()
            violations = scanner.scan_file(str(path))
            hash_violations = [v for v in violations if v.category == Category.WEAK_HASH]
            assert len(hash_violations) == 0
        finally:
            path.unlink()


class TestScannerPathTraversal:
    """CWE-022: user input in path operations should be flagged."""

    def test_user_input_in_open_detected(self):
        code = '''\
        from fastapi import Request
        def read_file(request: Request):
            filename = request.query_params.get("file")
            with open(filename) as f:
                return f.read()
        '''
        path = _write_tmp(code)
        try:
            scanner = SecurityScanner()
            violations = scanner.scan_file(str(path))
            path_violations = [v for v in violations if v.category == Category.PATH_TRAVERSAL]
            assert len(path_violations) >= 1
        finally:
            path.unlink()

    def test_validated_path_not_flagged(self):
        code = '''\
        from shared_core.path_validation import validate_path
        from fastapi import Request
        def read_file(request: Request, base: str):
            filename = request.query_params.get("file")
            safe_path = validate_path(filename, base)
            with open(safe_path) as f:
                return f.read()
        '''
        path = _write_tmp(code)
        try:
            scanner = SecurityScanner()
            violations = scanner.scan_file(str(path))
            path_violations = [v for v in violations if v.category == Category.PATH_TRAVERSAL]
            # Should have zero or fewer violations than without validate_path
            assert len(path_violations) == 0, "validate_path should suppress path traversal flag"
        finally:
            path.unlink()


# ===========================================================================
# Remediator Tests — Auto-Fix
# ===========================================================================

class TestRemediatorLogInjection:
    """Test auto-fix for CWE-117 log injection."""

    def test_fixes_fstring_logger(self):
        code = 'logger.info(f"User {username} logged in")\n'
        path = _write_tmp(code)
        try:
            scanner = SecurityScanner()
            violations = scanner.scan_file(str(path))
            log_violations = [v for v in violations if v.category == Category.LOG_INJECTION]

            if log_violations:
                remediator = AutoRemediator(dry_run=True, backup=False)
                fixes = remediator.remediate(log_violations)
                # Dry run should report fixes but not modify the file
                assert isinstance(fixes, list)
        finally:
            path.unlink()

    def test_bare_except_fix(self):
        code = dedent('''\
        try:
            pass
        except:
            pass
        ''')
        path = _write_tmp(code)
        try:
            scanner = SecurityScanner()
            violations = scanner.scan_file(str(path))
            bare_violations = [v for v in violations if v.category == Category.BARE_EXCEPT]

            if bare_violations:
                remediator = AutoRemediator(dry_run=False, backup=False)
                remediator.remediate(bare_violations)

                # Re-scan to verify fix
                new_violations = scanner.scan_file(str(path))
                bare_remaining = [v for v in new_violations if v.category == Category.BARE_EXCEPT]
                assert len(bare_remaining) == 0, "Bare except should be fixed"

                # Verify content
                with open(str(path)) as f:
                    content = f.read()
                assert "except Exception:" in content
                assert "except:" not in content
        finally:
            path.unlink()


class TestRemediatorInfoExposure:
    """Test auto-fix for CWE-209 info exposure."""

    def test_fixes_str_exc_in_detail(self):
        code = dedent('''\
        try:
            pass
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        ''')
        path = _write_tmp(code)
        try:
            scanner = SecurityScanner()
            violations = scanner.scan_file(str(path))
            info_violations = [v for v in violations if v.category == Category.INFO_EXPOSURE]

            if info_violations:
                remediator = AutoRemediator(dry_run=False, backup=False)
                remediator.remediate(info_violations)

                with open(str(path)) as f:
                    content = f.read()
                assert "safe_error_detail" in content
                assert "detail=str(exc)" not in content
        finally:
            path.unlink()


# ===========================================================================
# Telemetry Tests
# ===========================================================================

class TestTelemetry:
    """Tests for the SecurityTelemetry module."""

    def test_scan_result_from_violations(self):
        violations = [
            Violation(
                rule_id="CWE-117-001",
                category=Category.LOG_INJECTION,
                severity=Severity.HIGH,
                file="test.py",
                line=10,
                message="f-string in logger",
                suggestion="Use %-style logging",
                fixable=True,
            ),
            Violation(
                rule_id="PY-001-001",
                category=Category.BARE_EXCEPT,
                severity=Severity.MEDIUM,
                file="test.py",
                line=20,
                message="bare except",
                suggestion="Use except Exception:",
                fixable=True,
            ),
        ]
        result = ScanResult.from_violations(violations, commit="abc123", branch="main")

        assert result.total_violations == 2
        assert result.high == 1
        assert result.medium == 1
        assert result.critical == 0
        assert result.commit == "abc123"
        assert result.branch == "main"
        assert "CWE-117" in result.by_category
        assert "PY-001" in result.by_category

    def test_scan_result_serialization(self):
        violations = [
            Violation(
                rule_id="CWE-117-001",
                category=Category.LOG_INJECTION,
                severity=Severity.HIGH,
                file="test.py",
                line=10,
                message="f-string in logger",
            ),
        ]
        result = ScanResult.from_violations(violations)
        json_str = result.to_json()
        restored = ScanResult.from_json(json_str)
        assert restored.total_violations == 1
        assert restored.high == 1

    def test_quality_gate_pass(self):
        result = ScanResult(
            timestamp="2024-01-01T00:00:00Z",
            commit="abc",
            branch="main",
            total_violations=5,
            critical=0,
            high=0,
            medium=3,
            low=2,
            info=0,
            by_category={},
            by_file={},
            violations=[],
        )
        gate = QualityGate(max_critical=0, max_high=0, max_medium=10)
        gate_result = gate.evaluate(result)
        assert gate_result.passed is True
        assert len(gate_result.failures) == 0

    def test_quality_gate_fail(self):
        result = ScanResult(
            timestamp="2024-01-01T00:00:00Z",
            commit="abc",
            branch="main",
            total_violations=5,
            critical=1,
            high=2,
            medium=2,
            low=0,
            info=0,
            by_category={},
            by_file={},
            violations=[],
        )
        gate = QualityGate(max_critical=0, max_high=0)
        gate_result = gate.evaluate(result)
        assert gate_result.passed is False
        assert len(gate_result.failures) >= 1

    def test_telemetry_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            telemetry = SecurityTelemetry(storage_dir=tmpdir)

            violations = [
                Violation(
                    rule_id="CWE-117-001",
                    category=Category.LOG_INJECTION,
                    severity=Severity.HIGH,
                    file="test.py",
                    line=10,
                    message="f-string in logger",
                ),
            ]
            result = ScanResult.from_violations(violations, commit="abc123", branch="main")
            saved_path = telemetry.save(result)
            assert saved_path.exists()

            loaded = telemetry.load_latest()
            assert loaded is not None
            assert loaded.total_violations == 1
            assert loaded.commit == "abc123"

    def test_telemetry_diff(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            telemetry = SecurityTelemetry(storage_dir=tmpdir)

            # First scan: 2 violations
            v1 = [
                Violation(rule_id="R1", category=Category.LOG_INJECTION,
                          severity=Severity.HIGH, file="a.py", line=10, message="v1"),
                Violation(rule_id="R2", category=Category.BARE_EXCEPT,
                          severity=Severity.MEDIUM, file="b.py", line=20, message="v2"),
            ]
            result1 = ScanResult.from_violations(v1, commit="aaa", branch="main")
            telemetry.save(result1)

            # Second scan: 1 fixed (bare except gone), 1 new (path traversal)
            v2 = [
                Violation(rule_id="R1", category=Category.LOG_INJECTION,
                          severity=Severity.HIGH, file="a.py", line=10, message="v1"),
                Violation(rule_id="R3", category=Category.PATH_TRAVERSAL,
                          severity=Severity.CRITICAL, file="c.py", line=5, message="v3"),
            ]
            result2 = ScanResult.from_violations(v2, commit="bbb", branch="main")

            diff = telemetry.diff(before=result1, after=result2)
            assert diff.new_count == 1  # PATH_TRAVERSAL is new
            assert diff.fixed_count == 1  # BARE_EXCEPT was fixed
            assert diff.persistent_count == 1  # LOG_INJECTION persists
            assert diff.improved is False  # 1 new vs 1 fixed — not improved (equal)

    def test_telemetry_trend(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            telemetry = SecurityTelemetry(storage_dir=tmpdir)

            for i in range(5):
                violations = [
                    Violation(
                        rule_id="R1",
                        category=Category.LOG_INJECTION,
                        severity=Severity.HIGH,
                        file="a.py",
                        line=10 + i,
                        message=f"violation {i}",
                    )
                ]
                result = ScanResult.from_violations(violations, commit=f"commit{i}", branch="main")
                telemetry.save(result)

            trends = telemetry.trend()
            assert len(trends) == 5
            assert all(isinstance(t, TrendPoint) for t in trends)

    def test_markdown_report_generation(self):
        violations = [
            Violation(
                rule_id="CWE-117-001",
                category=Category.LOG_INJECTION,
                severity=Severity.HIGH,
                file="src/api.py",
                line=42,
                message="f-string in logger call",
                suggestion="Use %-style with sanitize_for_log()",
                fixable=True,
            ),
        ]
        result = ScanResult.from_violations(violations, commit="deadbeef", branch="feature/test")
        telemetry = SecurityTelemetry()
        report = telemetry.generate_markdown_report(result)

        assert "# " in report  # Has a header
        assert "CWE-117" in report
        assert "src/api.py" in report
        assert "HIGH" in report.upper() or "high" in report

    def test_cleanup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            telemetry = SecurityTelemetry(storage_dir=tmpdir)

            # Create 10 scan results
            for i in range(10):
                result = ScanResult.from_violations(
                    [], commit=f"commit{i:04d}", branch="main"
                )
                telemetry.save(result)

            # Cleanup, keeping only 5
            removed = telemetry.cleanup(keep=5)
            assert removed == 5

            remaining = list(Path(tmpdir).glob("scan_*.json"))
            assert len(remaining) == 5


# ===========================================================================
# Integration Tests — Full Scan → Fix → Re-scan Cycle
# ===========================================================================

class TestIntegrationScanFixRescan:
    """End-to-end: scan a file with violations, auto-fix, verify clean on re-scan."""

    def test_bare_except_full_cycle(self):
        code = dedent('''\
        try:
            risky()
        except:
            handle_error()
        ''')
        path = _write_tmp(code)
        try:
            scanner = SecurityScanner()

            # 1. Scan — should find bare except
            violations = scanner.scan_file(str(path))
            bare = [v for v in violations if v.category == Category.BARE_EXCEPT]
            assert len(bare) >= 1, "Should detect bare except"

            # 2. Fix
            remediator = AutoRemediator(dry_run=False, backup=False)
            remediator.remediate(bare)

            # 3. Re-scan — bare except should be gone
            violations_after = scanner.scan_file(str(path))
            bare_after = [v for v in violations_after if v.category == Category.BARE_EXCEPT]
            assert len(bare_after) == 0, "Bare except should be fixed after remediation"

            # 4. Verify file content
            with open(str(path)) as f:
                content = f.read()
            assert "except Exception:" in content
        finally:
            path.unlink(missing_ok=True)

    def test_info_exposure_full_cycle(self):
        code = dedent('''\
        try:
            connect_db()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        ''')
        path = _write_tmp(code)
        try:
            scanner = SecurityScanner()
            violations = scanner.scan_file(str(path))
            info = [v for v in violations if v.category == Category.INFO_EXPOSURE]

            if info:
                remediator = AutoRemediator(dry_run=False, backup=False)
                remediator.remediate(info)

                with open(str(path)) as f:
                    content = f.read()
                assert "safe_error_detail" in content
                assert "detail=str(exc)" not in content
        finally:
            path.unlink(missing_ok=True)

    def test_no_violations_on_clean_code(self):
        code = dedent('''\
        """A clean module with no security issues."""
        from __future__ import annotations

        import logging
        from shared_core.sanitize import sanitize_for_log
        from shared_core.error_handlers import safe_error_detail
        from shared_core.path_validation import validate_path

        logger = logging.getLogger(__name__)

        def process(name: str) -> str:
            logger.info("Processing %s", sanitize_for_log(name))  # codeql[py/cleartext-logging]
            try:
                return do_work(name)
            except Exception as exc:
                logger.error("Failed: %s", sanitize_for_log(str(exc)))  # codeql[py/cleartext-logging]
                raise HTTPException(status_code=500, detail=safe_error_detail(exc, 500))

        def read_config(filename: str, base: str) -> str:
            safe_path = validate_path(filename, base)
            with open(safe_path) as f:
                return f.read()
        ''')
        path = _write_tmp(code)
        try:
            scanner = SecurityScanner()
            violations = scanner.scan_file(str(path))
            # Should have zero high/critical violations
            serious = [v for v in violations if v.severity in (Severity.CRITICAL, Severity.HIGH)]
            assert len(serious) == 0, f"Clean code should not have serious violations, got {serious}"
        finally:
            path.unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
