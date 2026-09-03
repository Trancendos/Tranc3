"""Tests for scripts/check_ruff_pin_alignment.py.

Each test is a fault that was injected against the real files to confirm the
check fires, then restored. Synthetic trees under `tmp_path` keep the suite from
depending on whichever ruff the estate is currently pinned to, which moves.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_ruff_pin_alignment.py"

PRE_COMMIT_TEMPLATE = """\
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0
    hooks:
      - id: check-yaml
  # a comment between the repo and its rev, as the real file has
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: {rev}
    hooks:
      - id: ruff-format
"""

WORKFLOW_TEMPLATE = """\
name: Example
jobs:
  lint:
    steps:
      - name: Install ruff
        run: pip install "ruff=={version}"
"""


def _load():
    """Load the checker by path; it is a script, not an installed module."""
    spec = importlib.util.spec_from_file_location("_rpa", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["_rpa"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def checker(tmp_path, monkeypatch):
    """The checker pointed at a synthetic repo under tmp_path."""

    def _build(*, workflow_versions=("0.15.8",), rev="v0.15.8", pre_commit_body=None):
        gh = tmp_path / ".github" / "workflows"
        gh.mkdir(parents=True, exist_ok=True)
        for i, version in enumerate(workflow_versions):
            (gh / f"wf{i}.yml").write_text(
                WORKFLOW_TEMPLATE.format(version=version), encoding="utf-8"
            )
        pre_commit = tmp_path / ".pre-commit-config.yaml"
        if pre_commit_body is None:
            pre_commit_body = PRE_COMMIT_TEMPLATE.format(rev=rev)
        pre_commit.write_text(pre_commit_body, encoding="utf-8")

        module = _load()
        monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(module, "PRE_COMMIT", pre_commit)
        monkeypatch.setattr(module, "WORKFLOW_DIRS", (gh,))
        return module

    return _build


def test_passes_when_every_surface_agrees(checker):
    module = checker(workflow_versions=("0.15.8", "0.15.8", "0.15.8"), rev="v0.15.8")
    assert module.main() == 0


def test_fails_when_pre_commit_diverges_from_the_workflows(checker):
    """The real defect: pre-commit on v0.16.4 while the workflows ran 0.15.8."""
    module = checker(workflow_versions=("0.15.8", "0.15.8"), rev="v0.16.4")
    assert module.main() == 1


def test_fails_when_two_workflows_disagree(checker):
    """Drift between workflows is the same split gate, in the other direction."""
    module = checker(workflow_versions=("0.15.8", "0.16.4"), rev="v0.15.8")
    assert module.main() == 1


def test_the_leading_v_on_the_pre_commit_rev_is_not_a_divergence(checker):
    """`vX.Y.Z` and `X.Y.Z` name the same ruff; only that difference is tolerated."""
    module = checker(workflow_versions=("0.15.8",), rev="0.15.8")
    assert module.main() == 0


def test_fails_closed_when_the_ruff_rev_cannot_be_read(checker):
    """A file it cannot understand is a failure, never a pass."""
    module = checker(
        workflow_versions=("0.15.8",),
        pre_commit_body="repos:\n  - repo: https://example.invalid/other\n    rev: v1.0.0\n",
    )
    with pytest.raises(SystemExit) as excinfo:
        module.main()
    assert excinfo.value.code == 1


def test_fails_when_no_workflow_pins_ruff(checker, tmp_path):
    """An empty surface set must not read as 'all surfaces agree'."""
    module = checker(workflow_versions=(), rev="v0.15.8")
    assert module.main() == 1


def test_fails_when_one_workflow_pins_two_ruff_versions(checker, tmp_path):
    """A single file disagreeing with itself is drift too."""
    module = checker(workflow_versions=("0.15.8",), rev="v0.15.8")
    wf = tmp_path / ".github" / "workflows" / "wf0.yml"
    wf.write_text(
        wf.read_text(encoding="utf-8") + '      - run: pip install "ruff==0.16.4"\n',
        encoding="utf-8",
    )
    with pytest.raises(SystemExit) as excinfo:
        module.main()
    assert excinfo.value.code == 1


def test_a_rev_for_a_different_repo_is_not_mistaken_for_ruffs(checker):
    """The rev must be read from the ruff-pre-commit block, not the nearest one."""
    body = (
        "repos:\n"
        "  - repo: https://github.com/pre-commit/pre-commit-hooks\n"
        "    rev: v0.16.4\n"
        "    hooks:\n"
        "      - id: check-yaml\n"
        "  - repo: https://github.com/astral-sh/ruff-pre-commit\n"
        "    rev: v0.15.8\n"
        "    hooks:\n"
        "      - id: ruff-format\n"
    )
    module = checker(workflow_versions=("0.15.8",), pre_commit_body=body)
    assert module.main() == 0


def test_the_real_repo_surfaces_agree():
    """The estate's actual files, not a synthetic stand-in."""
    module = _load()
    assert module.main() == 0
