"""A code-scanning configuration main can produce and a PR cannot makes CI lie.

GitHub compares the configurations a pull request uploaded against the ones
`refs/heads/main` has, and concludes FAILURE when one is missing. `trivy.yml`'s
`trivy-enforce` job was gated to pushes on main, so `trivy-fs-enforce` existed
only there and the generated "Trivy" check was red on **every pull request in
this repository** -- identically on a clean branch and a filthy one.

That is the shape this estate keeps finding: a control that reports the same
thing whatever it is looking at. The second cost was quieter and larger. That
job is the strict pass, the one whose exit code answers to HIGH,CRITICAL, and it
only ever ran after the merge it exists to gate.

The first version of the guard had the same disease as the thing it was
guarding. Three reviewers found three ways it reported PASSED about workflows it
had not read:

* its category regex `[\\w.-]+` could not match `/language:${{ matrix.language }}`,
  so `codeql.yml` -- the repository's largest configuration -- was skipped
  entirely;
* substring matching flagged `push || pull_request`, which is reachable;
* and it could not see `!= 'pull_request'`, which is not.

Each of those is pinned below as its own test, so the guard cannot regress into
any of them. The rest pin it at both ends: it fails on the arrangement that
caused this, it does not pass by looking at nothing, and it says so out loud
when it meets a condition it cannot evaluate.
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


def _workflow(tmp_path: Path, body: str, name: str = "example.yml") -> Path:
    root = tmp_path / "workflows"
    root.mkdir(exist_ok=True)
    (root / name).write_text(body, encoding="utf-8")
    return root


def _template(*, triggers: str, job_if: str = "", step_if: str = "", category: str) -> str:
    job_line = f"    if: {job_if}\n" if job_if else ""
    step_line = f"        if: {step_if}\n" if step_if else ""
    return f"""\
name: Example
on:
{triggers}
jobs:
  scan:
    runs-on: ubuntu-latest
{job_line}    steps:
      - name: Upload
        uses: github/codeql-action/upload-sarif@v3
{step_line}        with:
          sarif_file: out.sarif
          category: {category}
"""


BOTH = '  push:\n    branches: ["main"]\n  pull_request:\n    branches: ["main"]\n'
PUSH_ONLY = '  push:\n    branches: ["main"]\n'


class TestTheArrangementThatCausedThis:
    def test_job_gated_to_pushes_on_main_is_reported(self, tmp_path: Path) -> None:
        root = _workflow(
            tmp_path,
            _template(
                triggers=BOTH,
                job_if="github.event_name == 'push' && github.ref == 'refs/heads/main'",
                category="'trivy-fs-enforce'",
            ),
        )
        found = guard.findings(root)
        assert len(found) == 1
        assert "MAIN-ONLY" in found[0]
        assert "trivy-fs-enforce" in found[0]

    def test_a_step_level_gate_is_reported_too(self, tmp_path: Path) -> None:
        root = _workflow(
            tmp_path,
            _template(
                triggers=BOTH,
                step_if="github.ref == 'refs/heads/main'",
                category="'scan'",
            ),
        )
        assert len(guard.findings(root)) == 1

    def test_a_workflow_that_never_runs_on_prs_is_reported(self, tmp_path: Path) -> None:
        """scorecard.yml's shape: the job `if` allows PRs, the trigger list does not."""
        root = _workflow(
            tmp_path,
            _template(
                triggers=PUSH_ONLY,
                job_if=(
                    "github.event.repository.default_branch == github.ref_name "
                    "|| github.event_name == 'pull_request'"
                ),
                category="'scorecard'",
            ),
        )
        found = guard.findings(root)
        assert len(found) == 1, found
        assert "MAIN-ONLY" in found[0]


class TestTheThreeBlindSpotsReviewersFound:
    def test_an_interpolated_category_is_not_skipped(self, tmp_path: Path) -> None:
        """`[\\w.-]+` could not match this, so codeql.yml went unexamined."""
        root = _workflow(
            tmp_path,
            _template(
                triggers=BOTH,
                job_if="github.event_name == 'push'",
                category="'/language:${{ matrix.language }}'",
            ),
        )
        found = guard.findings(root)
        assert len(found) == 1, found
        assert "language" in found[0]

    def test_push_or_pull_request_is_reachable_and_not_flagged(self, tmp_path: Path) -> None:
        """Substring matching flagged this; it runs on pull requests."""
        root = _workflow(
            tmp_path,
            _template(
                triggers=BOTH,
                job_if="github.event_name == 'push' || github.event_name == 'pull_request'",
                category="'reachable'",
            ),
        )
        assert guard.findings(root) == []

    def test_not_equal_pull_request_is_flagged(self, tmp_path: Path) -> None:
        """Substring matching could not see this, and it is the same defect."""
        root = _workflow(
            tmp_path,
            _template(
                triggers=BOTH,
                job_if="github.event_name != 'pull_request'",
                category="'inverted'",
            ),
        )
        found = guard.findings(root)
        assert len(found) == 1, found
        assert "MAIN-ONLY" in found[0]


class TestWhatItLeavesAlone:
    def test_an_ungated_upload_is_fine(self, tmp_path: Path) -> None:
        root = _workflow(tmp_path, _template(triggers=BOTH, category="'plain'"))
        assert guard.findings(root) == []

    def test_always_is_fine(self, tmp_path: Path) -> None:
        root = _workflow(tmp_path, _template(triggers=BOTH, step_if="always()", category="'plain'"))
        assert guard.findings(root) == []

    def test_a_runtime_unknown_is_symmetric_and_not_flagged(self, tmp_path: Path) -> None:
        """`steps.*` outputs are equally unknown on both sides, so no asymmetry."""
        root = _workflow(
            tmp_path,
            _template(
                triggers=BOTH,
                step_if="steps.credentials.outputs.configured == 'true'",
                category="'gated-on-a-secret'",
            ),
        )
        assert guard.findings(root) == []

    def test_a_workflow_with_no_sarif_upload_is_ignored(self, tmp_path: Path) -> None:
        root = _workflow(
            tmp_path,
            "name: X\non:\n  pull_request:\njobs:\n  a:\n    runs-on: ubuntu-latest\n"
            "    steps:\n      - run: echo hi\n",
        )
        assert guard.findings(root) == []


class TestItSaysWhenItCannotSee:
    def test_an_unparseable_condition_is_reported_not_skipped(self, tmp_path: Path) -> None:
        root = _workflow(
            tmp_path,
            _template(
                triggers=BOTH,
                job_if="fromJSON(needs.a.outputs.b)[0].c == 'x' ? 'y' : 'z'",
                category="'weird'",
            ),
        )
        found = guard.findings(root)
        assert len(found) == 1, found
        assert "UNREADABLE" in found[0]

    def test_a_missing_directory_raises_rather_than_passing(self, tmp_path: Path) -> None:
        with pytest.raises(guard.CannotReadWorkflows):
            guard.findings(tmp_path / "nope")

    def test_an_empty_directory_raises_rather_than_passing(self, tmp_path: Path) -> None:
        root = tmp_path / "workflows"
        root.mkdir()
        with pytest.raises(guard.CannotReadWorkflows):
            guard.findings(root)


class TestTheExceptionListHasToSayWhy:
    def test_a_blank_reason_is_rejected(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setitem(guard.ACCEPTED_MAIN_ONLY, "silenced", "   ")
        root = _workflow(
            tmp_path,
            _template(
                triggers=BOTH,
                job_if="github.event_name == 'push'",
                category="'silenced'",
            ),
        )
        found = guard.findings(root)
        assert any("has no written reason" in problem for problem in found), found

    def test_a_written_reason_suppresses_the_finding(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setitem(
            guard.ACCEPTED_MAIN_ONLY, "silenced", "Runs against the published image only."
        )
        root = _workflow(
            tmp_path,
            _template(
                triggers=BOTH,
                job_if="github.event_name == 'push'",
                category="'silenced'",
            ),
        )
        assert guard.findings(root) == []


class TestTheRealTree:
    def test_this_repository_passes(self) -> None:
        assert guard.findings() == []

    def test_every_accepted_entry_carries_a_reason(self) -> None:
        for category, reason in guard.ACCEPTED_MAIN_ONLY.items():
            assert isinstance(reason, str) and reason.strip(), category
