"""Containment tests for PersonalitySpawner's output-directory validator.

These cover the two CodeQL py/path-injection alerts on
``src/personality/spawner.py`` (SEC-015). The sinks CodeQL flagged were not the
scaffold write — ``safe_join`` already guarded that — but the validator's own
``Path(output_dir).resolve()`` and ``parent.exists()`` calls, which ran on raw
caller input before any containment check.

Two properties are asserted here that the previous implementation did not hold:

* a symlink *inside* an allowed root that points out of it is refused, and
* a path outside every allowed root is refused without the filesystem ever
  being touched — so the validator is not an existence oracle.
"""

from __future__ import annotations

import os
import pathlib
import tempfile
from pathlib import Path

import pytest

from Dimensional.path_validation import PathTraversalError
from src.personality.spawner import _ALLOWED_OUTPUT_ROOTS, _resolve_output_base


def _under_allowed_root(path: Path) -> bool:
    return any(path.is_relative_to(root) for root in _ALLOWED_OUTPUT_ROOTS)


@pytest.fixture
def allowed_tmpdir(tmp_path: Path) -> Path:
    """A directory guaranteed to sit under one of the allowed roots.

    ``tmp_path`` usually lands under the system temp dir, which is an allowed
    root — but pytest can be pointed elsewhere, so this is checked rather than
    assumed. A test that silently ran outside the roots would pass for the
    wrong reason.
    """
    if _under_allowed_root(tmp_path):
        return tmp_path
    fallback = Path(tempfile.mkdtemp(dir=tempfile.gettempdir()))
    if not _under_allowed_root(fallback.resolve()):
        pytest.skip("no writable directory under an allowed output root")
    return fallback


class TestAccepts:
    def test_relative_path_under_cwd(self) -> None:
        assert _resolve_output_base("./spawned") == (Path.cwd() / "spawned").resolve()

    def test_nonexistent_path_under_allowed_root(self, allowed_tmpdir: Path) -> None:
        """The common case: the spawn target does not exist yet."""
        target = allowed_tmpdir / "does-not-exist-yet"
        assert _resolve_output_base(str(target)) == target.resolve()

    def test_existing_directory_under_allowed_root(self, allowed_tmpdir: Path) -> None:
        assert _resolve_output_base(str(allowed_tmpdir)) == allowed_tmpdir.resolve()


class TestRefuses:
    @pytest.mark.parametrize(
        "outside",
        [
            "/etc/cron.d/evil",
            "/etc",
            "/usr/lib/python3/site-packages",
            "/",
        ],
    )
    def test_path_outside_every_root(self, outside: str) -> None:
        with pytest.raises(PathTraversalError):
            _resolve_output_base(outside)

    def test_traversal_out_of_cwd(self) -> None:
        """``..`` segments are collapsed lexically, then judged."""
        depth = len(Path.cwd().parts)
        with pytest.raises(PathTraversalError):
            _resolve_output_base("/".join([".."] * depth) + "/etc")

    def test_parent_under_root_does_not_rescue_a_child_outside_it(self) -> None:
        """The removed fallback branch's intent, asserted directly.

        ``/etc``'s parent ``/`` exists, which is what the old second branch
        tested for. It must not make ``/etc`` acceptable.
        """
        assert Path("/").exists()
        with pytest.raises(PathTraversalError):
            _resolve_output_base("/etc")


class TestNotAnOracle:
    """A rejected path must never reach the filesystem."""

    def test_no_filesystem_touch_for_rejected_path(self, monkeypatch) -> None:
        touched: list[str] = []

        real_resolve = pathlib.Path.resolve
        real_exists = pathlib.Path.exists
        real_stat = pathlib.Path.stat

        def spy_resolve(self, *a, **kw):
            touched.append(f"resolve:{self}")
            return real_resolve(self, *a, **kw)

        def spy_exists(self, *a, **kw):
            touched.append(f"exists:{self}")
            return real_exists(self, *a, **kw)

        def spy_stat(self, *a, **kw):
            touched.append(f"stat:{self}")
            return real_stat(self, *a, **kw)

        monkeypatch.setattr(pathlib.Path, "resolve", spy_resolve)
        monkeypatch.setattr(pathlib.Path, "exists", spy_exists)
        monkeypatch.setattr(pathlib.Path, "stat", spy_stat)

        with pytest.raises(PathTraversalError):
            _resolve_output_base("/etc/shadow-probe-target")

        assert touched == [], f"validator probed the filesystem for a rejected path: {touched}"

    def test_accepted_path_is_walked(self, monkeypatch, allowed_tmpdir: Path) -> None:
        """The counterpart: an accepted path IS inspected.

        Without this, the absence asserted above would hold just as well for a
        validator that had been disabled entirely. The walk uses ``os.lstat``
        rather than ``resolve()`` so that a symlink's target is read, not
        followed — see ``_resolve_without_leaving``.
        """
        seen: list[str] = []
        real_lstat = os.lstat

        def spy_lstat(path, *a, **kw):
            seen.append(str(path))
            return real_lstat(path, *a, **kw)

        monkeypatch.setattr(os, "lstat", spy_lstat)
        _resolve_output_base(str(allowed_tmpdir / "ok"))
        assert seen, "accepted path was never inspected — the symlink walk cannot have run"


class TestSymlinkOutOfRootIsReadNotFollowed:
    """cubic's P1 on this file, and it was right.

    The first version of the fix resolved the lexically-checked path in one
    ``Path.resolve()`` call. A symlink planted inside an allowed root redirects
    that resolution outward, so the probe happened before the containment
    verdict could object — while the docstring claimed nothing outside a root
    was ever handed to the filesystem.
    """

    def test_symlink_out_of_root_is_refused(self, allowed_tmpdir: Path) -> None:
        link = allowed_tmpdir / "into-etc"
        link.symlink_to("/etc/shadow")
        with pytest.raises(PathTraversalError):
            _resolve_output_base(str(link))

    def test_the_target_is_never_stat_ed(self, monkeypatch, allowed_tmpdir: Path) -> None:
        """``readlink`` reads the target; nothing follows it."""
        link = allowed_tmpdir / "into-etc"
        link.symlink_to("/etc/shadow")

        stat_calls: list[str] = []
        real_stat = os.stat

        def spy_stat(path, *a, **kw):
            stat_calls.append(str(path))
            return real_stat(path, *a, **kw)

        monkeypatch.setattr(os, "stat", spy_stat)
        with pytest.raises(PathTraversalError):
            _resolve_output_base(str(link))

        outside = [c for c in stat_calls if not _under_allowed_root(Path(c))]
        assert outside == [], f"followed a symlink out of the roots: {outside}"

    def test_symlink_chain_inside_the_root_still_works(self, allowed_tmpdir: Path) -> None:
        """Contained links are legitimate and must keep resolving."""
        real = allowed_tmpdir / "real"
        real.mkdir()
        hop = allowed_tmpdir / "hop"
        hop.symlink_to(real)
        assert _resolve_output_base(str(hop)) == real.resolve()

    def test_symlink_cycle_raises_rather_than_hanging(self, allowed_tmpdir: Path) -> None:
        a = allowed_tmpdir / "a"
        b = allowed_tmpdir / "b"
        a.symlink_to(b)
        b.symlink_to(a)
        with pytest.raises(PathTraversalError):
            _resolve_output_base(str(a))


class TestAllowedRootsAreAbsolute:
    def test_roots_are_resolved_absolute_paths(self) -> None:
        """``is_relative_to`` is lexical; a relative root would silently never match."""
        for root in _ALLOWED_OUTPUT_ROOTS:
            assert root.is_absolute(), f"{root} is not absolute"
            assert root == Path(os.path.normpath(str(root))), f"{root} is not normalised"
