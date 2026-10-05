"""The pin guard must reject every spelling of the drift it was built for.

The four-way drift it caught went unnoticed because the condition was written in
a comment and never measured. A guard whose rejection path has never run is the
same defect one layer up, so each case below is a tree the check must fail on,
and `test_the_real_repository_is_consistent` is the only one it must pass.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_security_toolchain_pins.py"
_spec = importlib.util.spec_from_file_location("check_security_toolchain_pins", _SCRIPT)
assert _spec and _spec.loader
check = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = check
_spec.loader.exec_module(check)


def _tree(
    tmp_path: Path,
    *,
    requirements: str = "semgrep==1.179.0  # SAST\n",
    pre_commit: str = (
        "repos:\n  - repo: https://github.com/semgrep/pre-commit\n"
        "    rev: v1.179.0\n    hooks:\n      - id: semgrep\n"
    ),
    makefile: str = "security-install:\n\t$(PIP) install -r requirements-security.txt --quiet\n",
    forgejo: str = "      - name: Install semgrep\n        run: pip install -r requirements-security.txt\n",
    dockerfile: str = "RUN pip install --no-cache-dir -r /tmp/requirements-security.txt\n",
) -> Path:
    (tmp_path / "requirements-security.txt").write_text(requirements, encoding="utf-8")
    (tmp_path / ".pre-commit-config.yaml").write_text(pre_commit, encoding="utf-8")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    workflow = tmp_path / ".forgejo" / "workflows"
    workflow.mkdir(parents=True, exist_ok=True)
    (workflow / "security-scan.yml").write_text(forgejo, encoding="utf-8")
    runner = tmp_path / "deploy" / "forgejo"
    runner.mkdir(parents=True, exist_ok=True)
    (runner / "runner.Dockerfile").write_text(dockerfile, encoding="utf-8")
    return tmp_path


@pytest.fixture
def at(monkeypatch):
    def _at(path: Path) -> int:
        monkeypatch.setattr(check, "ROOT", path)
        return check.main()

    return _at


def test_a_consistent_synthetic_tree_passes(tmp_path, at):
    assert at(_tree(tmp_path)) == 0


def test_the_real_repository_is_consistent():
    assert check.main() == 0


# ── The drift that actually happened ──────────────────────────────────────────


@pytest.mark.parametrize("rev", ["v1.174.0", "v1.172.0", "v1.178.0", "1.174.0"])
def test_a_lagging_pre_commit_hook_is_rejected(tmp_path, at, rev):
    tree = _tree(
        tmp_path,
        pre_commit=(
            "repos:\n  - repo: https://github.com/semgrep/pre-commit\n"
            f"    rev: {rev}\n    hooks:\n      - id: semgrep\n"
        ),
    )
    assert at(tree) == 1


def test_a_makefile_that_restates_the_pin_is_rejected(tmp_path, at):
    tree = _tree(
        tmp_path,
        makefile="security-install:\n\t$(PIP) install semgrep==1.172.0 --quiet\n",
    )
    assert at(tree) == 1


def test_a_forgejo_job_that_restates_the_pin_is_rejected(tmp_path, at):
    tree = _tree(tmp_path, forgejo="        run: pip install semgrep==1.172.0 --quiet\n")
    assert at(tree) == 1


def test_a_restated_pin_is_rejected_even_when_it_agrees_today(tmp_path, at):
    """Agreement now is not the property; a second pin is."""
    tree = _tree(tmp_path, makefile="\t$(PIP) install semgrep==1.179.0 --quiet\n")
    assert at(tree) == 1


def test_a_commented_out_pin_is_rejected(tmp_path, at):
    """Someone will uncomment it, and it will be seven releases behind."""
    tree = _tree(tmp_path, makefile="# \t$(PIP) install semgrep==1.172.0 --quiet\n")
    assert at(tree) == 1


# ── Things that are prose, not pins ───────────────────────────────────────────


def test_prose_naming_a_version_is_not_a_pin(tmp_path, at):
    tree = _tree(
        tmp_path,
        forgejo=(
            "      # semgrep 1.172.0 was the version this said for seven releases.\n"
            "      # See requirements-security.txt, which pins semgrep 1.179.0.\n"
            "        run: pip install -r requirements-security.txt\n"
        ),
    )
    assert at(tree) == 0


def test_a_longer_package_name_is_not_a_semgrep_pin(tmp_path, at):
    tree = _tree(tmp_path, makefile="\t$(PIP) install my-semgrep==1.0.0 --quiet\n")
    assert at(tree) == 0


# ── The source of truth itself ────────────────────────────────────────────────


def test_requirements_with_no_semgrep_pin_is_rejected(tmp_path, at):
    assert at(_tree(tmp_path, requirements="bandit==1.9.4\n")) == 1


def test_requirements_with_two_semgrep_pins_is_rejected(tmp_path, at):
    tree = _tree(tmp_path, requirements="semgrep==1.179.0\nsemgrep==1.178.0\n")
    assert at(tree) == 1


def test_a_missing_requirements_file_is_rejected(tmp_path, at):
    tree = _tree(tmp_path)
    (tree / "requirements-security.txt").unlink()
    assert at(tree) == 1


def test_a_missing_pre_commit_config_is_rejected(tmp_path, at):
    tree = _tree(tmp_path)
    (tree / ".pre-commit-config.yaml").unlink()
    assert at(tree) == 1


def test_a_missing_install_site_is_rejected(tmp_path, at):
    tree = _tree(tmp_path)
    (tree / "Makefile").unlink()
    assert at(tree) == 1


def test_two_semgrep_hooks_are_rejected(tmp_path, at):
    tree = _tree(
        tmp_path,
        pre_commit=(
            "repos:\n  - repo: https://github.com/semgrep/pre-commit\n"
            "    rev: v1.179.0\n    hooks:\n      - id: semgrep\n"
            "  - repo: https://github.com/semgrep/pre-commit\n"
            "    rev: v1.179.0\n    hooks:\n      - id: semgrep\n"
        ),
    )
    assert at(tree) == 1


def test_a_version_marker_does_not_defeat_the_requirement_parse(tmp_path, at):
    tree = _tree(tmp_path, requirements='semgrep==1.179.0 ; python_version >= "3.11"\n')
    assert at(tree) == 0


def test_the_act_runner_image_restating_the_pin_is_rejected(tmp_path, at):
    """The fifth site, and the one this check missed when it was written.

    `deploy/forgejo/runner.Dockerfile` builds `trancendos/act-runner:latest`,
    which the `self-hosted` label resolves to — the label the Forgejo semgrep job
    runs on. It pinned semgrep 1.100.0, seventy-nine releases behind the
    requirements file, and the first version of this guard enumerated four sites
    and did not include it. A guard that names four of five measures nothing
    about the fifth.
    """
    tree = _tree(
        tmp_path,
        dockerfile="RUN python3 -m pip install --no-cache-dir semgrep==1.100.0\n",
    )
    assert at(tree) == 1


def test_a_missing_act_runner_image_is_rejected(tmp_path, at):
    tree = _tree(tmp_path)
    (tree / "deploy" / "forgejo" / "runner.Dockerfile").unlink()
    assert at(tree) == 1
