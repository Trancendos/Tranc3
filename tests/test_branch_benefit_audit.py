"""Calibration for the branch benefit audit's diff-stat parser.

`scripts/branch_benefit_audit.py` classifies 166 remote branches as
cherry-pick / review / blocked, and `_verdict` decides on the DELETION count.
That count came back 0 for every branch the audit had ever examined, because
the parser compared whitespace-separated tokens against `"insertions"` while
git writes `249 insertions(+)`. `files` matched only because git spells that
one bare.

So the "mass deletions — likely destructive rebase" rule could never fire, and
every branch fell through to `files <= 15 and deletions < 500`: the audit was
calling branches safe to cherry-pick on a measurement it had not made. Two of
them carried ~900 deletions each and were reclassified `review` the moment the
number became real.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def audit():
    path = REPO / "scripts" / "branch_benefit_audit.py"
    spec = importlib.util.spec_from_file_location("branch_benefit_audit", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["branch_benefit_audit"] = module
    spec.loader.exec_module(module)
    return module


class TestTheDiffStatParser:
    @pytest.mark.parametrize(
        "shortstat,expected",
        [
            # The real shape, suffixes and all. This is the case that failed.
            (" 15 files changed, 249 insertions(+), 118 deletions(-)", (15, 249, 118)),
            (" 1 file changed, 1 insertion(+), 1 deletion(-)", (1, 1, 1)),
            # git omits a side entirely when it is zero.
            (" 3 files changed, 42 insertions(+)", (3, 42, 0)),
            (" 2 files changed, 7 deletions(-)", (2, 0, 7)),
            # Thousands separators.
            (" 1,204 files changed, 66,074 insertions(+), 7,636 deletions(-)", (1204, 66074, 7636)),
        ],
    )
    def test_git_shortstat_is_read_in_the_shape_git_writes_it(
        self, audit, monkeypatch, shortstat, expected
    ):
        monkeypatch.setattr(audit, "_run", lambda *a, **k: shortstat.strip())
        assert audit._diff_stats("main", "some-branch") == expected

    def test_an_empty_stat_is_zero_rather_than_a_crash(self, audit, monkeypatch):
        monkeypatch.setattr(audit, "_run", lambda *a, **k: "")
        assert audit._diff_stats("main", "some-branch") == (0, 0, 0)


class TestTheVerdictActsOnTheDeletionCount:
    """The half that made the parser bug matter rather than merely be untidy."""

    def test_a_mass_deletion_branch_is_blocked(self, audit):
        verdict, _note = audit._verdict("some-branch", ahead=3, files=20, deletions=6000)
        assert verdict == "blocked"

    def test_a_small_branch_with_heavy_deletions_is_not_called_safe(self, audit):
        """The specific misclassification: 9 files, 947 deletions, previously
        reported as "small, reviewable diff — safe to cherry-pick" because the
        deletion count the rule reads was always zero."""
        verdict, _note = audit._verdict("some-branch", ahead=4, files=9, deletions=947)
        assert verdict != "cherry-pick"

    def test_a_genuinely_small_branch_still_reads_as_cherry_pick(self, audit):
        """And the guard must not cry wolf on the branches it exists to find."""
        verdict, _note = audit._verdict("some-branch", ahead=2, files=2, deletions=6)
        assert verdict == "cherry-pick"
