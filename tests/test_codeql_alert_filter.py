"""Tests for scripts/filter_codeql_alerts.py.

The behaviour under test is a suppression, and the case that matters most is
`test_a_non_path_injection_alert_in_a_listed_file_survives`: the filter this
replaced deleted every rule at every severity in three files, so a SQL
injection or a hardcoded credential introduced there would have been removed
from the SARIF before upload, leaving nothing in the Security tab to show it
had ever been raised.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "filter_codeql_alerts.py"

LISTED = "src/agents/goal_manager.py"
UNLISTED = "src/core/tranc3_inference.py"


def _load():
    spec = importlib.util.spec_from_file_location("_cqf", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["_cqf"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def filterer():
    return _load()


def _sarif(*results):
    return {"runs": [{"results": list(results)}]}


def _result(rule, path):
    return {
        "ruleId": rule,
        "locations": [{"physicalLocation": {"artifactLocation": {"uri": path}}}],
    }


def test_a_path_injection_alert_in_a_listed_file_is_dropped(filterer):
    sarif, dropped, surprises = filterer.filter_sarif(_sarif(_result("py/path-injection", LISTED)))
    assert sarif["runs"][0]["results"] == []
    assert len(dropped) == 1
    assert surprises == []


def test_a_non_path_injection_alert_in_a_listed_file_survives(filterer):
    """The defect this replaced.

    The adjudication covered path injection. It did not cover SQL injection,
    and a filter that removes both is suppressing a decision nobody made.
    """
    sarif, dropped, surprises = filterer.filter_sarif(_sarif(_result("py/sql-injection", LISTED)))
    assert len(sarif["runs"][0]["results"]) == 1
    assert dropped == []
    assert len(surprises) == 1
    assert "NOT covered" in surprises[0]


def test_a_path_injection_alert_in_an_unlisted_file_survives(filterer):
    """Only the three adjudicated files are in scope."""
    sarif, dropped, _ = filterer.filter_sarif(_sarif(_result("py/path-injection", UNLISTED)))
    assert len(sarif["runs"][0]["results"]) == 1
    assert dropped == []


def test_a_renamed_path_traversal_rule_is_still_covered(filterer):
    """CodeQL renames query ids between releases.

    Matching a substring rather than an exact id means a rename fails in the
    SAFE direction if it ever stops matching — the alert reappears — which is
    the right way round to be imprecise about a suppression.
    """
    sarif, dropped, _ = filterer.filter_sarif(
        _sarif(_result("py/uncontrolled-path-traversal", LISTED))
    )
    assert sarif["runs"][0]["results"] == []
    assert len(dropped) == 1


def test_every_suppressed_path_carries_a_reason(filterer):
    """A suppression without a reason cannot be told from silencing a red build."""
    for path, reason in filterer.SUPPRESSED_PATHS.items():
        assert len(reason.split()) >= 8, path


def test_every_suppressed_path_still_exists(filterer):
    """A listed file that has gone is a suppression nobody has revisited."""
    assert filterer.stale_paths() == []


def test_a_stale_path_fails_the_run(filterer, tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(filterer.SUPPRESSED_PATHS, "gone/away.py", "a written reason here ok")
    target = tmp_path / "python.sarif"
    target.write_text(json.dumps(_sarif()), encoding="utf-8")
    assert filterer.main([str(target)]) == 1
    assert "no longer exists" in capsys.readouterr().err


def test_a_missing_sarif_is_not_a_failure(filterer, tmp_path):
    """The analyze step skips languages it did not run."""
    assert filterer.main([str(tmp_path / "absent.sarif")]) == 0


def test_the_file_is_rewritten_in_place(filterer, tmp_path):
    target = tmp_path / "python.sarif"
    target.write_text(
        json.dumps(
            _sarif(_result("py/path-injection", LISTED), _result("py/sql-injection", LISTED))
        ),
        encoding="utf-8",
    )
    assert filterer.main([str(target)]) == 0
    remaining = json.loads(target.read_text(encoding="utf-8"))["runs"][0]["results"]
    assert [r["ruleId"] for r in remaining] == ["py/sql-injection"]


def test_strict_surprises_can_fail_the_run(filterer, tmp_path):
    """Available for the day the estate wants an unadjudicated rule to block."""
    target = tmp_path / "python.sarif"
    target.write_text(json.dumps(_sarif(_result("py/sql-injection", LISTED))), encoding="utf-8")
    assert filterer.main([str(target)]) == 0
    assert filterer.main([str(target), "--strict-surprises"]) == 1
