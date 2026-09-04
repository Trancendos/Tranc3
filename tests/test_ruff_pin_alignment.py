"""Tests for scripts/check_ruff_pin_alignment.py.

Each test is a fault that was injected against the real files to confirm the
check fires, then restored. Synthetic trees under `tmp_path` keep the suite from
depending on whichever ruff the estate is currently pinned to, which moves.

The unpinned-install and Dockerfile cases are not hypothetical: the first
version of this check scanned only `ruff==<version>` inside `*.yml` under the
two workflow directories and skipped everything else in silence, so it reported
"5 surfaces, all on ruff 0.15.8" while `.forgejo/workflows/ci.yml`,
`.forgejo/workflows/nightly.yml`, `.forgejo/workflows/security-scan.yml` and
`.woodpecker.yml` installed ruff unpinned and `deploy/forgejo/runner.Dockerfile`
pinned a third version, 0.4.4.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_ruff_pin_alignment.py"

# The comment sits BETWEEN the repo line and its rev, which is the branch of
# PRE_COMMIT_REV that a comment above the repo line would never exercise.
PRE_COMMIT_TEMPLATE = """\
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0
    hooks:
      - id: check-yaml
  - repo: https://github.com/astral-sh/ruff-pre-commit
    # a comment between the repo and its rev
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

    def _build(*, workflow_versions=("0.15.8",), rev="v0.15.8", pre_commit_body=None, files=None):
        gh = tmp_path / ".github" / "workflows"
        gh.mkdir(parents=True, exist_ok=True)
        for i, version in enumerate(workflow_versions):
            (gh / f"wf{i}.yml").write_text(
                WORKFLOW_TEMPLATE.format(version=version), encoding="utf-8"
            )
        for name, body in (files or {}).items():
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")

        pre_commit = tmp_path / ".pre-commit-config.yaml"
        if pre_commit_body is None:
            pre_commit_body = PRE_COMMIT_TEMPLATE.format(rev=rev)
        pre_commit.write_text(pre_commit_body, encoding="utf-8")

        module = _load()
        monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(module, "PRE_COMMIT", pre_commit)
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


def test_fails_when_nothing_installs_ruff(checker):
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
    assert module.main() == 1


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


# ── the gap the first version of this check could not see ────────────────────


def test_fails_on_an_unpinned_install(checker):
    """`.forgejo/workflows/ci.yml`: `uv pip install --system ruff --quiet`.

    The original check's `if not found: continue` skipped this file entirely
    and still printed PASSED.
    """
    module = checker(
        files={
            ".forgejo/workflows/ci.yml": (
                "jobs:\n  lint:\n    steps:\n      - run: |\n"
                "          uv pip install --system ruff --quiet\n"
                "          ruff check src/\n"
            )
        }
    )
    assert module.main() == 1


def test_a_yaml_extension_is_scanned_too(checker):
    """Renaming a workflow `.yaml` must not drop it out of the gate."""
    module = checker(
        workflow_versions=(),
        files={".github/workflows/lint.yaml": WORKFLOW_TEMPLATE.format(version="0.16.4")},
    )
    assert module.main() == 1


def test_woodpecker_is_scanned(checker):
    """`.woodpecker.yml` sits under no workflows directory and was invisible."""
    module = checker(
        files={
            ".woodpecker.yml": (
                "steps:\n  ruff-lint:\n    commands:\n"
                '      - pip install --quiet "ruff==0.16.4"\n'
                "      - ruff check .\n"
            )
        }
    )
    assert module.main() == 1


def test_a_dockerfile_pin_is_scanned_across_line_continuations(checker):
    """`deploy/forgejo/runner.Dockerfile` pinned 0.4.4 inside a multi-line RUN."""
    module = checker(
        files={
            "deploy/forgejo/runner.Dockerfile": (
                "FROM python:3.11\n"
                "RUN python3 -m pip install --no-cache-dir \\\n"
                "        bandit==1.8.3 \\\n"
                "        ruff==0.4.4 \\\n"
                "        mypy==1.10.0\n"
            )
        }
    )
    assert module.main() == 1


def test_the_dockerfile_finding_points_at_the_ruff_line(checker, tmp_path, capsys):
    """A finding inside a 25-line RUN block must not name the line it opens on."""
    module = checker(
        workflow_versions=(),
        files={
            "deploy/forgejo/runner.Dockerfile": (
                "FROM python:3.11\n"
                "RUN python3 -m pip install --no-cache-dir \\\n"
                "        bandit==1.8.3 \\\n"
                "        ruff==0.4.4 \\\n"
                "        mypy==1.10.0\n"
            )
        },
    )
    module.main()
    assert "runner.Dockerfile:4" in capsys.readouterr().out


def test_a_file_that_runs_ruff_without_installing_it_is_a_failure(checker):
    """It inherits whatever the runner image carries -- an unpinned surface."""
    module = checker(
        files={
            ".forgejo/workflows/nightly.yml": (
                "jobs:\n  lint:\n    steps:\n      - run: ruff check src/ api.py\n"
            )
        }
    )
    assert module.main() == 1


def test_an_install_and_an_invocation_on_one_line_is_not_read_as_unpinned(checker):
    """`pip install "ruff==X" && ruff check .` installs once, pinned."""
    module = checker(
        workflow_versions=(),
        files={
            ".github/workflows/lint.yml": (
                "jobs:\n  lint:\n    steps:\n"
                '      - run: pip install "ruff==0.15.8" && ruff check .\n'
            )
        },
    )
    assert module.main() == 0


def test_prose_and_step_names_are_not_surfaces(checker):
    """Only installs and invocations count; a mention in a comment does not."""
    module = checker(
        files={
            ".forgejo/workflows/docs.yml": (
                "# ruff is documented here but never installed or run\n"
                "jobs:\n  docs:\n    steps:\n"
                "      - name: ruff-lint results\n"
                "        run: cat logs/ruff-results.json\n"
            )
        }
    )
    assert module.main() == 0


def test_ruff_pre_commit_is_not_mistaken_for_the_ruff_package(checker):
    """`ruff-pre-commit` is a different name and must not read as a ruff pin."""
    module = checker(
        files={
            ".github/workflows/other.yml": (
                "jobs:\n  x:\n    steps:\n      - run: pip install ruff-pre-commit\n"
            )
        }
    )
    assert module.main() == 0


def test_fails_closed_on_a_file_it_cannot_read(checker, tmp_path, monkeypatch):
    """An unreadable surface is a file it did not verify, so it is a failure.

    The permission is simulated rather than applied: CI runs this suite as
    root, for whom `chmod 000` is not a denial, so the real mode bits would
    prove nothing.
    """
    module = checker()
    unreadable = tmp_path / ".github" / "workflows" / "locked.yml"
    unreadable.write_text("jobs: {}\n", encoding="utf-8")

    real_read_text = Path.read_text

    def _deny(self, *args, **kwargs):
        if self.name == "locked.yml":
            raise PermissionError(13, "Permission denied")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _deny)
    with pytest.raises(SystemExit) as excinfo:
        module.main()
    assert excinfo.value.code == 1


def test_the_real_repo_surfaces_agree():
    """The estate's actual files, not a synthetic stand-in."""
    module = _load()
    assert module.main() == 0
