"""The bandit baseline drift check must degrade, never crash.

`_bandit_baseline_drift` reads two files it does not own: `.security-baseline`,
which a human edits, and a bandit JSON report, which a scanner writes. Both can
arrive malformed. A security control that raises on malformed input is worse
than one that reports "cannot measure", because the traceback is indistinguishable
from a broken build and gets muted.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load_module(root: Path, logs: Path):
    """Import security_score with ROOT/LOGS pointed at a temp tree."""
    spec = importlib.util.spec_from_file_location(
        "security_score_under_test", SCRIPTS / "security_score.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    module.ROOT = root
    module.LOGS = logs
    return module


@pytest.fixture()
def score(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    return _load_module(tmp_path, logs)


def _write_report(logs: Path, findings: int) -> None:
    (logs / "bandit-full.json").write_text(
        json.dumps({"results": [{"issue": i} for i in range(findings)]})
    )


def test_non_ascii_numeral_baseline_is_rejected_not_crashed(score, tmp_path):
    """`"²".isdigit()` is True but `int("²")` raises ValueError.

    isdigit() was chosen to reject "-1"; on its own it also admits superscript
    digits straight into the int() that cannot take them.
    """
    (tmp_path / ".security-baseline").write_text("bandit_findings=²\n")
    _write_report(tmp_path / "logs", 5)

    ok, detail = score._bandit_baseline_drift()

    assert ok is None
    assert "not a non-negative integer" in detail


def test_negative_baseline_is_still_rejected(score, tmp_path):
    """The behaviour isdigit() was there for must survive the ASCII fix."""
    (tmp_path / ".security-baseline").write_text("bandit_findings=-1\n")
    _write_report(tmp_path / "logs", 5)

    assert score._bandit_baseline_drift()[0] is None


def test_undecodable_baseline_is_reported_not_raised(score, tmp_path):
    """read_text() raises UnicodeDecodeError, which is not an OSError."""
    (tmp_path / ".security-baseline").write_bytes(b"bandit_findings=\xff\xfe\x00\n")

    ok, detail = score._bandit_baseline_drift()

    assert ok is None
    assert detail == "unreadable .security-baseline"


def test_undecodable_bandit_report_is_reported_not_raised(score, tmp_path):
    (tmp_path / ".security-baseline").write_text("bandit_findings=10\n")
    (tmp_path / "logs" / "bandit-full.json").write_bytes(b"\xff\xfe not json")

    ok, detail = score._bandit_baseline_drift()

    assert ok is None
    assert "unreadable" in detail


def test_a_baseline_in_step_with_the_scan_passes(score, tmp_path):
    """The guard must still be able to say yes -- otherwise it measures nothing."""
    (tmp_path / ".security-baseline").write_text("bandit_findings=100\n")
    _write_report(tmp_path / "logs", 95)

    ok, detail = score._bandit_baseline_drift()

    assert ok is True
    assert "drift 5%" in detail


def test_a_baseline_far_from_the_scan_fails(score, tmp_path):
    (tmp_path / ".security-baseline").write_text("bandit_findings=100\n")
    _write_report(tmp_path / "logs", 50)

    ok, detail = score._bandit_baseline_drift()

    assert ok is False
    assert "drift 50%" in detail
