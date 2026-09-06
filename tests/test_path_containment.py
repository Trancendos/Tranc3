"""Containment of the fd-based readers in Dimensional/path_validation.py.

`validate_path()` resolves a path and checks it is inside a base directory. The
readers then had to *open* it, and did so by pathname -- which re-resolves the
whole path from scratch, opening a check-to-open window. `O_NOFOLLOW` closed
that window for the final component only, because that is the only component
`open()` inspects; a concurrent swap of any intermediate parent directory still
redirected the read outside the base. That is issue #337, and `_open_contained`
is the fix: walk down from a trusted base fd so there is no second traversal to
race.

The interesting tests here drive `_open_contained` directly with a path whose
intermediate component is already a symlink. Racing a real swap is
non-deterministic, but the state *after* a successful swap is exactly this --
a resolved-looking path with a symlink somewhere in the middle -- so testing
that state deterministically tests the property that matters.
"""

from __future__ import annotations

import os

import pytest

import Dimensional.path_validation as path_validation
from Dimensional.path_validation import (
    _SUPPORTS_DIR_FD,
    PathTraversalError,
    _open_contained,
    list_validated_children,
    list_validated_children_fd,
    read_validated_file_text,
)

needs_dir_fd = pytest.mark.skipif(
    not _SUPPORTS_DIR_FD,
    reason="dir_fd walking is POSIX-only; the documented fallback applies instead",
)


@pytest.fixture
def tree(tmp_path):
    """base/ with a nested file, plus an out-of-base secret to aim symlinks at."""
    base = tmp_path / "base"
    (base / "real" / "sub").mkdir(parents=True)
    (base / "real" / "sub" / "file.txt").write_text("contained", encoding="utf-8")

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("escaped", encoding="utf-8")
    return base, outside


class TestOpenContained:
    def test_reads_a_legitimately_contained_file(self, tree):
        base, _ = tree
        fd = _open_contained(base / "real" / "sub" / "file.txt", base, os.O_RDONLY)
        try:
            assert os.read(fd, 64) == b"contained"
        finally:
            os.close(fd)

    def test_base_itself_opens_as_a_directory(self, tree):
        """An empty component list must not fall through to a broken walk."""
        base, _ = tree
        fd = _open_contained(base, base, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            assert "real" in os.listdir(fd)
        finally:
            os.close(fd)

    @needs_dir_fd
    def test_intermediate_symlink_is_refused(self, tree):
        """The gap #337 was filed for: O_NOFOLLOW alone never inspected this.

        `link` is a symlink to a directory outside base. Reaching through it to
        `secret.txt` is precisely what an attacker who wins the race achieves,
        and it must fail rather than return the escaped content.
        """
        base, outside = tree
        os.symlink(outside, base / "link")

        with pytest.raises(PathTraversalError):
            _open_contained(base / "link" / "secret.txt", base, os.O_RDONLY)

    @needs_dir_fd
    def test_final_symlink_is_refused(self, tree):
        """The case O_NOFOLLOW already covered -- it must stay covered."""
        base, outside = tree
        os.symlink(outside / "secret.txt", base / "flink")

        with pytest.raises(PathTraversalError):
            _open_contained(base / "flink", base, os.O_RDONLY)

    @needs_dir_fd
    def test_a_missing_component_still_raises_filenotfound(self, tree):
        """Only the symlink errno becomes PathTraversalError; the rest pass through.

        Mapping every OSError would turn an ordinary missing file into a
        reported attack, which is worse than useless in a log.
        """
        base, _ = tree
        with pytest.raises(FileNotFoundError):
            _open_contained(base / "real" / "nope" / "file.txt", base, os.O_RDONLY)

    @needs_dir_fd
    def test_a_plain_file_mid_path_is_not_reported_as_an_attack(self, tree):
        """ENOTDIR alone cannot classify: a symlink and a regular file share it.

        Opening an intermediate component adds O_DIRECTORY, so Linux answers
        ENOTDIR for a swapped-in symlink rather than ELOOP -- but that is also
        what an ordinary file in the middle of a path gives, and calling a
        caller's typo a traversal attack makes the signal worthless. The lstat
        check is what separates them, and this pins the benign half.
        """
        base, _ = tree
        with pytest.raises(NotADirectoryError):
            _open_contained(base / "real" / "sub" / "file.txt" / "deeper", base, os.O_RDONLY)

    @needs_dir_fd
    def test_the_walk_leaks_no_descriptors_when_it_fails(self, tree):
        """Every intermediate fd is closed as the walk advances, including on error."""
        base, outside = tree
        os.symlink(outside, base / "link")

        before = len(os.listdir("/proc/self/fd")) if os.path.isdir("/proc/self/fd") else None
        if before is None:
            pytest.skip("no /proc/self/fd on this platform")

        for _ in range(25):
            with pytest.raises(PathTraversalError):
                _open_contained(base / "link" / "secret.txt", base, os.O_RDONLY)

        after = len(os.listdir("/proc/self/fd"))
        assert after <= before + 1, f"descriptors leaked: {before} -> {after}"

    @needs_dir_fd
    def test_a_symlinked_base_is_refused(self, tree):
        """The walk must not start from a swapped root.

        Every component below is opened with O_NOFOLLOW, but base itself was
        opened by name without it -- so a base replaced by a symlink after
        validate_path() resolved it would have made every careful step
        afterwards relative to the attacker's directory.
        """
        base, outside = tree
        fake_base = base.parent / "fake_base"
        os.symlink(outside, fake_base)

        with pytest.raises(PathTraversalError):
            _open_contained(fake_base / "secret.txt", fake_base, os.O_RDONLY)

    def test_containment_is_refused_outright_without_dir_fd(self, tree, monkeypatch):
        """No dir_fd must fail closed, not fall back to an unguarded open.

        The earlier version opened the resolved pathname instead, which keeps
        the final-component guarantee and drops the intermediate one -- the
        exact hole this function exists to close.
        """
        import Dimensional.path_validation as pv

        base, _ = tree
        monkeypatch.setattr(pv, "_SUPPORTS_DIR_FD", False)

        with pytest.raises(PathTraversalError, match="dir_fd"):
            pv._open_contained(base / "real" / "sub" / "file.txt", base, os.O_RDONLY)


class TestCallersStillWork:
    """The two public readers keep their existing contracts."""

    def test_read_validated_file_text_reads_contained_content(self, tree):
        base, _ = tree
        text, size = read_validated_file_text("real/sub/file.txt", base)
        assert text == "contained"
        assert size == len("contained")

    def test_read_rejects_traversal_out_of_base(self, tree):
        base, _ = tree
        with pytest.raises((PathTraversalError, ValueError)):
            read_validated_file_text("../outside/secret.txt", base)

    @needs_dir_fd
    def test_read_refuses_to_follow_a_symlink_out_of_base(self, tree):
        base, outside = tree
        os.symlink(outside / "secret.txt", base / "flink")
        with pytest.raises((PathTraversalError, ValueError, FileNotFoundError)):
            read_validated_file_text("flink", base)

    def test_list_validated_children_fd_lists_contained_entries(self, tree):
        base, _ = tree
        names = {c["name"] for c in list_validated_children_fd("real", base)}
        assert names == {"sub"}

    def test_list_sorts_directories_before_files(self, tree):
        base, _ = tree
        (base / "real" / "a.txt").write_text("x", encoding="utf-8")
        children = list_validated_children_fd("real", base)
        assert [c["name"] for c in children] == ["sub", "a.txt"]

    def test_list_rejects_traversal_out_of_base(self, tree):
        base, _ = tree
        with pytest.raises((PathTraversalError, ValueError)):
            list_validated_children_fd("../outside", base)

    def test_reading_a_directory_is_refused(self, tree):
        """The fstat check: the descriptor, not just the pathname, must be a file."""
        base, _ = tree
        with pytest.raises((FileNotFoundError, IsADirectoryError)):
            read_validated_file_text("real", base)


def test_base_dir_accepts_a_str_as_well_as_a_path(tree):
    """Callers pass workspace_root() through; it must not become Path-only."""
    base, _ = tree
    text, _size = read_validated_file_text("real/sub/file.txt", str(base))
    assert text == "contained"


class TestListerHonoursTheSameContainmentAsTheReader:
    """The reader and the lister must refuse in the same conditions.

    list_validated_children() previously had its own implementation that never
    called _open_contained(), so it kept listing on a platform where the reader
    refused. A containment guarantee only one of the two honours is not a
    guarantee, and nothing failed when they disagreed.
    """

    def test_lister_fails_closed_without_dir_fd_support(self, tmp_path, monkeypatch):
        (tmp_path / "ok.txt").write_text("legit")
        monkeypatch.setattr(path_validation, "_SUPPORTS_DIR_FD", False)

        with pytest.raises(PathTraversalError, match="dir_fd"):
            list_validated_children(tmp_path, tmp_path)

    def test_reader_and_lister_agree_without_dir_fd_support(self, tmp_path, monkeypatch):
        (tmp_path / "ok.txt").write_text("legit")
        monkeypatch.setattr(path_validation, "_SUPPORTS_DIR_FD", False)

        for call in (
            lambda: read_validated_file_text(tmp_path / "ok.txt", tmp_path),
            lambda: list_validated_children(tmp_path, tmp_path),
        ):
            with pytest.raises(PathTraversalError):
                call()

    def test_lister_still_works_and_keeps_its_documented_keys(self, tmp_path):
        (tmp_path / "ok.txt").write_text("legit")
        (tmp_path / "sub").mkdir()

        children = list_validated_children(tmp_path, tmp_path)

        assert {c["name"] for c in children} == {"ok.txt", "sub"}
        # 'modified' belongs to the fd variant; this function's contract is
        # name/type/size and delegating must not widen it.
        assert all(set(c) == {"name", "type", "size"} for c in children)
