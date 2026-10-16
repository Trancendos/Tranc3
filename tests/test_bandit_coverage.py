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
import json
import subprocess
import sys
from pathlib import Path

import pytest

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


# ---------------------------------------------------------------------------
# Reported by cubic on #1403: the runner tallied whatever `results` it was
# handed, so a scan that half-failed reported the half it managed -- and it
# read its report from a fixed path that a previous or concurrent run could
# have written.
# ---------------------------------------------------------------------------


class _Completed:
    def __init__(self, returncode: int) -> None:
        self.returncode = returncode
        self.stdout = ""
        self.stderr = "diagnostic tail"


def _runner(report, returncode=1):
    """A fake `subprocess.run` that writes `report` where bandit would."""

    def run(argv, **kwargs):
        if report is not None:
            Path(argv[argv.index("-o") + 1]).write_text(json.dumps(report), encoding="utf-8")
        return _Completed(returncode)

    return run


@pytest.mark.parametrize(
    ("report", "returncode", "expected"),
    [
        ({"results": [], "errors": [{"filename": "workers/x.py"}]}, 1, "could not scan 1 file"),
        ({"results": []}, 1, "no `errors` list"),
        ({"results": [], "errors": "boom"}, 1, "no `errors` list"),
        ({"results": [], "errors": []}, 2, "exited 2"),
        (None, 1, "no parseable JSON"),
    ],
    ids=["per-file-errors", "errors-key-absent", "errors-not-a-list", "usage-error", "no-report"],
)
def test_a_scan_that_did_not_fully_run_is_unknown(monkeypatch, report, returncode, expected):
    """Tallying `results` while ignoring `errors` is a sensor reporting clean
    over the files it could read and silent about the ones it could not --
    which `docs/governance/IMMUNE-SYSTEM.md` forbids. A syntax error in one
    file under `workers/` would have lowered the count and passed the ratchet.
    """
    monkeypatch.setattr(cbc.subprocess, "run", _runner(report, returncode))
    results, blind = cbc._run_bandit(Path("."), ["src"])
    assert results == []
    assert expected in blind


@pytest.mark.parametrize(
    ("report", "returncode", "count"),
    [({"results": [], "errors": []}, 0, 0), ({"results": [{"a": 1}], "errors": []}, 1, 1)],
    ids=["clean", "findings"],
)
def test_a_scan_that_ran_reports_its_findings_with_no_reason(
    monkeypatch, report, returncode, count
):
    """The control, and the distinction the whole function turns on: an empty
    list with no reason is a clean scan; an empty list with a reason is UNKNOWN.
    """
    monkeypatch.setattr(cbc.subprocess, "run", _runner(report, returncode))
    results, blind = cbc._run_bandit(Path("."), ["src"])
    assert len(results) == count
    assert blind == ""


def test_the_report_path_is_not_shared_between_runs(monkeypatch):
    """It was a fixed name in the system temp directory.

    A run whose bandit failed to write could read a PREVIOUS run's report and
    tally it as its own -- a stale green with nothing to show it -- and on a
    shared runner two runs raced for one file. A predictable path in a
    world-writable directory is also one another process can plant.
    """
    seen: list[str] = []

    def run(argv, **kwargs):
        out = argv[argv.index("-o") + 1]
        seen.append(out)
        Path(out).write_text(json.dumps({"results": [], "errors": []}), encoding="utf-8")
        return _Completed(0)

    monkeypatch.setattr(cbc.subprocess, "run", run)
    cbc._run_bandit(Path("."), ["src"])
    cbc._run_bandit(Path("."), ["src"])
    assert len(seen) == 2
    assert seen[0] != seen[1], "two runs must not write to the same report path"
    assert not Path(seen[0]).exists(), "and the file must not outlive the run that made it"


# --- the two bandit lanes --------------------------------------------------


def test_the_configured_and_pre_commit_lanes_stand_as_recorded():
    """The hook scans fewer targets than `[tool.bandit]`, on purpose.

    Measured medium+ findings are src 0, api.py 0, scripts 4, workers 77, and
    the hook runs with `-ll`, so widening it would fail every commit here on 81
    inherited findings. Deliberate is not the same as unstated: this is what
    holds the pair to the reason written beside them.
    """
    root = Path(__file__).resolve().parents[1]
    targets, _ = cbc.configured_scope(root / "pyproject.toml")
    assert cbc.lane_divergence(root, targets) == []
    assert set(cbc._PRECOMMIT_BANDIT_TARGETS) < set(targets), "narrower, and a subset"


def test_widening_the_hook_without_recording_it_fails(tmp_path):
    config = tmp_path / ".pre-commit-config.yaml"
    config.write_text(
        "repos:\n  - repo: x\n    hooks:\n      - id: bandit\n"
        "        args: [-c, pyproject.toml, -r, src, api.py, workers]\n",
        encoding="utf-8",
    )
    problems = cbc.lane_divergence(tmp_path, ["src", "api.py", "workers"])
    assert len(problems) == 1
    assert "recorded divergence" in problems[0]


def test_a_hook_target_outside_the_gated_scope_fails(tmp_path):
    """The local lane must be a subset: otherwise a commit can pass locally
    over a surface CI never measures."""
    config = tmp_path / ".pre-commit-config.yaml"
    config.write_text(
        "repos:\n  - repo: x\n    hooks:\n      - id: bandit\n        args: [-r, src, api.py]\n",
        encoding="utf-8",
    )
    problems = cbc.lane_divergence(tmp_path, ["src"])
    assert any("does not cover" in p for p in problems)


def test_an_unreadable_hook_is_unknown_not_agreed(tmp_path):
    """No file to compare is not agreement."""
    problems = cbc.lane_divergence(tmp_path, ["src"])
    assert len(problems) == 1
    assert "could not be read" in problems[0]
