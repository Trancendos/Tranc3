"""The Python security lane must cover what its config says, and say when blind.

Measured 2026-10-16, following one CodeFactor B310 finding to its root.
`[tool.bandit]` scoped the lane to `targets = ["src", "api.py"]` and ALSO listed
`scripts` in `exclude_dirs`, so `scripts/` was doubly out of scope. At the
gate's own `-ll --confidence-level medium` threshold:

    src/ + api.py        136,879 lines     36 Low,  0 Medium
    scripts/ + workers/   85,824 lines    153 Low, 79 Medium

The whole medium-severity population of the repository was outside the lane,
including two unpinned Hugging Face Hub downloads at HIGH confidence.

The test that matters most is not the counting one. It is
`test_a_lane_that_could_not_run_reports_unknown_not_clean`: a security control
that cannot scan reports exactly what a clean one reports unless it says
otherwise, and the chain of three controls that produced this file all broke
that rule.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("cbc", REPO / "scripts" / "check_bandit_coverage.py")
assert _SPEC and _SPEC.loader
cbc = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = cbc
_SPEC.loader.exec_module(cbc)


def _repo(tmp_path: Path, pyproject: str) -> Path:
    (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# The property this file exists for.
# ---------------------------------------------------------------------------


def test_a_lane_that_could_not_run_reports_unknown_not_clean(tmp_path, capsys, monkeypatch):
    """REGRESSION, and the whole point.

    bandit missing, erroring, or returning unparseable output must never be
    reported as a surface with no findings. It is the same rule grade.py
    applies to sensors and check_app_inventory.py applies to its register.
    """
    root = _repo(tmp_path, '[tool.bandit]\ntargets = ["src"]\n')
    monkeypatch.setattr(cbc, "_run_bandit", lambda *a, **k: ([], "bandit is not installed"))
    code = cbc.main(["--root", str(root)])
    out = capsys.readouterr().out
    assert code == 1, "a lane that could not run must not exit 0"
    assert "UNKNOWN" in out
    assert "PASSED" not in out


def test_an_empty_target_list_is_blind_not_clean(tmp_path):
    """A config naming no targets would otherwise scan nothing and pass."""
    root = _repo(tmp_path, "[tool.bandit]\ntargets = []\n")
    results, blind = cbc._run_bandit(root, [])
    assert results == [] and "no targets" in blind


def test_bandit_missing_is_reported_rather_than_raised(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError

    monkeypatch.setattr(cbc.subprocess, "run", boom)
    results, blind = cbc._run_bandit(tmp_path, ["src"])
    assert results == [] and "not installed" in blind


def test_a_timeout_is_reported_rather_than_raised(tmp_path, monkeypatch):
    def slow(*a, **k):
        raise subprocess.TimeoutExpired(cmd="bandit", timeout=900)

    monkeypatch.setattr(cbc.subprocess, "run", slow)
    results, blind = cbc._run_bandit(tmp_path, ["src"])
    assert results == [] and "900s" in blind


# ---------------------------------------------------------------------------
# Scope comes from the config, so the control cannot cover less than it claims.
# ---------------------------------------------------------------------------


def test_scope_is_read_from_the_config_not_hardcoded(tmp_path):
    root = _repo(
        tmp_path,
        '[tool.bandit]\ntargets = ["src", "api.py", "scripts", "workers"]\n'
        'exclude_dirs = ["tests"]\n',
    )
    targets, excluded = cbc.configured_scope(root / "pyproject.toml")
    assert targets == ["src", "api.py", "scripts", "workers"]
    assert excluded == ["tests"]


def test_this_repository_actually_covers_scripts_and_workers():
    """REGRESSION for the finding: `scripts` was in exclude_dirs AND absent
    from targets, so it was doubly out of scope."""
    targets, excluded = cbc.configured_scope(REPO / "pyproject.toml")
    for needed in ("src", "api.py", "scripts", "workers"):
        assert needed in targets, f"{needed} must be in the bandit lane"
    assert "scripts" not in excluded, "scripts must not be excluded and targeted at once"


def test_an_unreadable_config_yields_no_scope_rather_than_a_guess(tmp_path):
    assert cbc.configured_scope(tmp_path / "absent.toml") == ([], [])
    bad = tmp_path / "pyproject.toml"
    bad.write_text("= = not toml", encoding="utf-8")
    assert cbc.configured_scope(bad) == ([], [])


# ---------------------------------------------------------------------------
# Counting, in bands rather than a total.
# ---------------------------------------------------------------------------


def test_severity_bands_are_counted_separately():
    """A single total would let a MEDIUM arrive while two LOWs leave."""
    results = [
        {"issue_severity": "HIGH"},
        {"issue_severity": "MEDIUM"},
        {"issue_severity": "LOW"},
        {"issue_severity": "LOW"},
    ]
    assert cbc.tally(results) == {"medium_plus": 2, "low": 2}


def test_a_clean_surface_counts_zero_in_both_bands():
    assert cbc.tally([]) == {"medium_plus": 0, "low": 0}


# ---------------------------------------------------------------------------
# The ratchet, through the shared module.
# ---------------------------------------------------------------------------


def test_no_recorded_ceiling_is_unknown_and_fails(tmp_path, capsys, monkeypatch):
    root = _repo(tmp_path, '[tool.bandit]\ntargets = ["src"]\n')
    monkeypatch.setattr(cbc, "_run_bandit", lambda *a, **k: ([], ""))
    assert cbc.main(["--root", str(root)]) == 1
    assert "UNKNOWN" in capsys.readouterr().out


def test_holding_at_the_ceiling_passes(tmp_path, capsys, monkeypatch):
    root = _repo(tmp_path, '[tool.bandit]\ntargets = ["src"]\n')
    (root / "config" / "immune").mkdir(parents=True)
    (root / "config/immune/bandit_ceiling.txt").write_text(
        "medium_plus=1\nlow=0\n", encoding="utf-8"
    )
    monkeypatch.setattr(cbc, "_run_bandit", lambda *a, **k: ([{"issue_severity": "MEDIUM"}], ""))
    assert cbc.main(["--root", str(root)]) == 0
    assert "PASSED" in capsys.readouterr().out


def test_a_new_medium_finding_fails_the_ratchet(tmp_path, capsys, monkeypatch):
    root = _repo(tmp_path, '[tool.bandit]\ntargets = ["src"]\n')
    (root / "config" / "immune").mkdir(parents=True)
    (root / "config/immune/bandit_ceiling.txt").write_text(
        "medium_plus=0\nlow=0\n", encoding="utf-8"
    )
    monkeypatch.setattr(cbc, "_run_bandit", lambda *a, **k: ([{"issue_severity": "MEDIUM"}], ""))
    assert cbc.main(["--root", str(root)]) == 1
    assert "ROSE" in capsys.readouterr().out


def test_the_real_repository_holds_at_its_recorded_ceiling():
    """Skipped rather than failed when bandit is absent: this suite runs in a
    job that may not install it, and a missing tool is not a finding."""
    import shutil

    if shutil.which("bandit") is None and importlib.util.find_spec("bandit") is None:
        import pytest

        pytest.skip("bandit not installed in this environment")
    assert cbc.main([]) == 0
