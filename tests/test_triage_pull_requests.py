"""The PR triage sweeper must flag a branch that deletes a live file.

Each test builds a real throwaway git repository rather than mocking git, so
what is measured is what `git` actually reports -- the bugs this script exists
to catch (a rename read as a deletion, an empty survey read as a clean queue)
only appear against real refs.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.triage_pull_requests import GitUnavailable, Verdict, render, survey


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True
    ).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.invalid")
    git(root, "config", "user.name", "T")
    git(root, "config", "commit.gpgsign", "false")
    (root / "keep.py").write_text("".join(f"CONST_{i} = {i}\n" for i in range(60)))
    (root / "test_thing.py").write_text("def test_x():\n    assert True\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    # 'origin/main' is what the script compares against; fake the remote ref.
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    return root


def branch_from_base(root: Path, pr: int) -> None:
    """Point refs/remotes/pr/<n> at the current HEAD, then reset back to main."""
    git(root, "update-ref", f"refs/remotes/pr/{pr}", "HEAD")
    git(root, "checkout", "-q", "main")


def test_a_branch_deleting_a_live_file_is_flagged_destructive(repo: Path) -> None:
    git(repo, "checkout", "-q", "-b", "work")
    (repo / "test_thing.py").unlink()
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "perf: optimise the thing")
    branch_from_base(repo, 994)

    (verdict,) = survey([994], base="refs/remotes/origin/main", root=repo)

    assert verdict.destructive, "deleting a file main still has must be flagged"
    assert verdict.deletes_live == ["test_thing.py"]
    assert verdict.deletes_live_tests == ["test_thing.py"], "test suites called out separately"


def test_a_branch_that_deletes_nothing_is_not_flagged(repo: Path) -> None:
    """The probe's other half: the same machinery must stay green on a clean PR."""
    git(repo, "checkout", "-q", "-b", "clean")
    (repo / "keep.py").write_text("".join(f"CONST_{i} = {i + 1}\n" for i in range(60)))
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "tweak")
    branch_from_base(repo, 1211)

    (verdict,) = survey([1211], base="refs/remotes/origin/main", root=repo)

    assert not verdict.destructive
    assert verdict.deletes_live == []


def test_a_rename_is_not_reported_as_a_deletion(repo: Path) -> None:
    """PR #1207 renamed Dimensional/ to Dimensionals/.

    The old paths leave and are still on main, which a naive check reads as a
    destructive deletion. It is not one: the content arrives under a new name in
    the same head. Flagging it would have made the sweeper cry wolf on the one
    large PR that was actually correct.
    """
    git(repo, "checkout", "-q", "-b", "rename")
    git(repo, "mv", "keep.py", "kept.py")
    git(repo, "commit", "-qm", "rename keep.py to kept.py")
    branch_from_base(repo, 1207)

    (verdict,) = survey([1207], base="refs/remotes/origin/main", root=repo)

    assert verdict.deletes_live == [], "a rename must not read as a deletion"
    assert not verdict.destructive


def test_an_unfetched_clone_raises_rather_than_reporting_a_clean_queue(repo: Path) -> None:
    """No refs must not be indistinguishable from no problems."""
    with pytest.raises(GitUnavailable, match="had a local ref"):
        survey([4242], base="refs/remotes/origin/main", root=repo)


def test_a_missing_base_raises(repo: Path) -> None:
    with pytest.raises(GitUnavailable, match="does not resolve"):
        survey([994], base="refs/remotes/origin/nonexistent", root=repo)


def test_an_empty_request_raises(repo: Path) -> None:
    with pytest.raises(GitUnavailable, match="nothing was surveyed"):
        survey([], base="refs/remotes/origin/main", root=repo)


def test_render_names_the_deleted_paths() -> None:
    out = render(
        [
            Verdict(
                994,
                merges_cleanly=False,
                commits_behind=168,
                changed_files=65,
                deletes_live=["src/exchange/engine.py", "tests/test_exchange.py"],
            ),
            Verdict(1211, merges_cleanly=True, commits_behind=0, changed_files=2),
        ]
    )
    assert "PR 994: 2 file(s), 1 of them test suites" in out
    assert "src/exchange/engine.py" in out
    assert (
        "Surveyed 2 pull request(s): 1 merge cleanly, 1 conflict, 1 would delete live files." in out
    )


def test_a_rename_survives_a_restrictive_configured_rename_limit(repo: Path) -> None:
    """The real #1207 case: rename detection is capped, so a big PR reports D.

    diff.renameLimit caps how many paths git will pair up; above it, every move
    is reported as a plain deletion. #1207 renamed 95 files and edited each one
    in the same commit, so without "-l0" the sweeper called a rename the single
    most destructive PR in the queue. Pinning the limit to 1 here reproduces
    that on a small branch, and the file is edited as well as moved so blob
    identity cannot rescue it -- similarity detection has to.
    """
    git(repo, "config", "diff.renameLimit", "1")
    git(repo, "checkout", "-q", "-b", "bigrename")
    git(repo, "mv", "keep.py", "kept.py")
    (repo / "kept.py").write_text(
        "".join(f"CONST_{i} = {i}\n" for i in range(60)) + "# edited during the move\n"
    )
    (repo / "second.py").write_text("y = 1\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "rename plus an edit plus unrelated churn")
    branch_from_base(repo, 12071)

    (verdict,) = survey([12071], base="refs/remotes/origin/main", root=repo)

    assert verdict.deletes_live == [], (
        "a renamed-and-edited file has moved, not gone -- main loses nothing"
    )


def test_a_deletion_is_still_caught_under_the_same_restrictive_limit(repo: Path) -> None:
    """The other half of the probe: same config, a real deletion must still flag."""
    git(repo, "config", "diff.renameLimit", "1")
    git(repo, "checkout", "-q", "-b", "realdelete")
    (repo / "test_thing.py").unlink()
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "drop the suite")
    branch_from_base(repo, 9941)

    (verdict,) = survey([9941], base="refs/remotes/origin/main", root=repo)

    assert verdict.deletes_live == ["test_thing.py"]


def test_a_move_git_cannot_pair_is_reported_as_relocated_not_destructive(repo: Path) -> None:
    """#1207's residue: a one-line __init__.py rewritten as it moved.

    Similarity is computed over content, so a single-line file whose single
    line changed scores nothing and git reports a plain deletion however the
    rename flags are set. The basename fallback is what separates this from a
    real loss; without it the sweeper's exit code blocks every package
    reorganisation that touches an __init__.
    """
    (repo / "pkg").mkdir()
    (repo / "pkg" / "__init__.py").write_text("from Dimensional.quantum import core\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "add package")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")

    git(repo, "checkout", "-q", "-b", "reorg")
    (repo / "pkg2").mkdir()
    git(repo, "mv", "pkg/__init__.py", "pkg2/__init__.py")
    # The rename rewrote the token inside the file too, which is exactly what
    # made these two paths unpairable in #1207: the file is one line long, so
    # changing that line leaves 0% similarity for git to find.
    (repo / "pkg2" / "__init__.py").write_text("from Dimensionals.quantum import core\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "move the package and rewrite its import")
    branch_from_base(repo, 12072)

    (verdict,) = survey([12072], base="refs/remotes/origin/main", root=repo)

    assert not verdict.destructive, "a relocated package must not block the queue"
    assert verdict.relocated == ["pkg/__init__.py"]
    assert verdict.deletes_live == []


def test_a_genuinely_removed_file_is_not_excused_by_a_same_named_file(repo: Path) -> None:
    """The fallback must not become a loophole.

    Basename matching is deliberately weak, so the probe has to show it still
    fails closed when the name genuinely disappears.
    """
    git(repo, "checkout", "-q", "-b", "drop")
    (repo / "test_thing.py").unlink()
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "remove the suite outright")
    branch_from_base(repo, 9942)

    (verdict,) = survey([9942], base="refs/remotes/origin/main", root=repo)

    assert verdict.destructive
    assert verdict.deletes_live == ["test_thing.py"]
    assert verdict.relocated == []
