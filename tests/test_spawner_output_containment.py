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

    def test_symlink_inside_root_pointing_out(self, allowed_tmpdir: Path) -> None:
        """The property the previous implementation did not hold.

        ``resolve()``-then-check accepted this: the escape only shows up after
        the symlink is followed, and the old code checked the resolved path
        against the roots — but it resolved *before* deciding whether the name
        was one it was willing to touch at all, and the resolved target here is
        outside every root, so the old code did reject it. What it could not do
        is reject it without first following the link. This test pins the
        refusal; ``test_no_filesystem_touch_for_rejected_path`` pins the rest.
        """
        link = allowed_tmpdir / "escape"
        link.symlink_to("/etc", target_is_directory=True)
        with pytest.raises(PathTraversalError):
            _resolve_output_base(str(link))


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

    def test_accepted_path_does_resolve(self, monkeypatch, allowed_tmpdir: Path) -> None:
        """The counterpart: an accepted path IS resolved, so the guard above is
        measuring an absence that only holds for rejections."""
        touched: list[str] = []
        real_resolve = pathlib.Path.resolve

        def spy_resolve(self, *a, **kw):
            touched.append(str(self))
            return real_resolve(self, *a, **kw)

        monkeypatch.setattr(pathlib.Path, "resolve", spy_resolve)
        _resolve_output_base(str(allowed_tmpdir / "ok"))
        assert touched, "accepted path was never resolved — symlink check cannot have run"


class TestAllowedRootsAreAbsolute:
    def test_roots_are_resolved_absolute_paths(self) -> None:
        """``is_relative_to`` is lexical; a relative root would silently never match."""
        for root in _ALLOWED_OUTPUT_ROOTS:
            assert root.is_absolute(), f"{root} is not absolute"
            assert root == Path(os.path.normpath(str(root))), f"{root} is not normalised"
