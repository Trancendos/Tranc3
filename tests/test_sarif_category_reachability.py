"""A code-scanning category main can produce and a PR cannot makes CI lie.

GitHub compares the categories a pull request uploaded against the categories
`refs/heads/main` has, and concludes FAILURE when one is missing. `trivy.yml`'s
`trivy-enforce` job was gated to pushes on main, so `trivy-fs-enforce` existed
only there and the generated "Trivy" check was red on **every pull request in
this repository** -- identically on a clean branch and a filthy one.

That is the shape this estate keeps finding: a control that reports the same
thing whatever it is looking at. The second cost was quieter and larger. That
job is the strict pass, the one whose exit code answers to HIGH,CRITICAL, and it
only ever ran after the merge it exists to gate.

These tests pin the guard at both ends: that it fails on the arrangement that
caused this, and that it is not passing merely by looking at nothing.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "check_sarif_categories_reach_prs",
    REPO / "scripts" / "check_sarif_categories_reach_prs.py",
)
assert _SPEC and _SPEC.loader
guard = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(guard)

_JOB_GATED = """\
name: Example
on:
  push:
    branches: ["main"]
  pull_request:
    branches: ["main"]
jobs:
  scan:
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    steps:
      - name: Upload SARIF
        uses: github/codeql-action/upload-sarif@v4
        with:
          sarif_file: "scan.sarif"
          category: "example-enforce"
"""

_STEP_GATED = _JOB_GATED.replace(
    "    if: github.event_name == 'push' && github.ref == 'refs/heads/main'\n", ""
).replace(
    "        uses: github/codeql-action/upload-sarif@v4\n",
    "        uses: github/codeql-action/upload-sarif@v4\n        if: github.ref == 'refs/heads/main'\n",
)

_REACHABLE = _JOB_GATED.replace(
    "    if: github.event_name == 'push' && github.ref == 'refs/heads/main'\n", ""
)


class TestTheGuardSeesTheDefect:
    @pytest.mark.parametrize(
        "workflow,label",
        [(_JOB_GATED, "job-level gate"), (_STEP_GATED, "step-level gate")],
    )
    def test_a_main_only_category_is_reported(self, tmp_path, workflow, label):
        (tmp_path / "example.yml").write_text(workflow, encoding="utf-8")
        problems = guard.findings(tmp_path)
        assert problems, f"{label}: a main-only category was not reported"
        assert "example-enforce" in problems[0]

    def test_an_unguarded_category_is_not_reported(self, tmp_path):
        (tmp_path / "example.yml").write_text(_REACHABLE, encoding="utf-8")
        assert guard.findings(tmp_path) == []

    def test_a_workflow_that_never_runs_on_a_pr_is_not_reported(self, tmp_path):
        """Nothing is missing from a PR that the workflow never runs on."""
        push_only = _REACHABLE.replace('  pull_request:\n    branches: ["main"]\n', "")
        (tmp_path / "example.yml").write_text(push_only, encoding="utf-8")
        assert guard.findings(tmp_path) == []


class TestTheGuardCannotPassBlind:
    def test_an_empty_directory_refuses_rather_than_reporting_clean(self, tmp_path):
        with pytest.raises(guard.CannotReadWorkflows):
            guard.findings(tmp_path)

    def test_a_missing_directory_refuses(self, tmp_path):
        with pytest.raises(guard.CannotReadWorkflows):
            guard.findings(tmp_path / "nope")

    def test_it_actually_examines_this_repository(self):
        """It must find categorised uploads here, or it is checking nothing."""
        workflows = REPO / ".github" / "workflows"
        categorised = [
            path
            for path in workflows.glob("*.yml")
            if "upload-sarif" in path.read_text(encoding="utf-8")
            and "category:" in path.read_text(encoding="utf-8")
        ]
        assert categorised, "no workflow uploads a categorised SARIF — guard has no subject"


def test_this_repository_has_no_main_only_categories():
    assert guard.findings() == []
