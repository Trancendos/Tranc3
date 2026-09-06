# Dimensional/path_validation.py
# Path traversal prevention utilities for safe filesystem operations.
#
# All functions use only the Python standard library (3.8+) and enforce
# that resolved paths remain within an allowed base directory.
#
# Usage:
#   from Dimensional.path_validation import validate_path, safe_join

from __future__ import annotations

import errno
import logging
import os
import os.path
import re
import stat
from pathlib import Path, PurePosixPath
from typing import Union

logger = logging.getLogger(__name__)

# Pattern to detect obvious traversal attempts in raw input
_TRAVERSAL_PATTERN = re.compile(r"(?:\.\.)|(?:\x00)")


class PathTraversalError(ValueError):
    """Raised when a path escapes its allowed base directory."""


def validate_path(
    path: Union[str, Path],
    base_dir: Union[str, Path],
    *,
    must_exist: bool = False,
    allow_create: bool = True,
) -> Path:
    """Validate that *path* resolves to a location within *base_dir*.

    Args:
        path: The user-supplied path component to validate.
        base_dir: The directory that *path* must remain within after
            resolution.  Must be an absolute path or resolvable from cwd.
        must_exist: If True, raise FileNotFoundError when the path does
            not yet exist on disk.
        allow_create: If False, reject paths that do not already exist
            (stronger guarantee when writing is not expected).

    Returns:
        The resolved, validated Path object.

    Raises:
        PathTraversalError: If the resolved path escapes *base_dir*.
        FileNotFoundError: If *must_exist* is True and path is missing.
        ValueError: If *path* contains obviously malicious components.
    """
    base = Path(base_dir).resolve()

    if isinstance(path, Path):
        raw = str(path)
    else:
        raw = path

    if not raw or not isinstance(raw, str):
        raise PathTraversalError(f"Invalid path input: {raw!r}")

    if _TRAVERSAL_PATTERN.search(raw):
        raise PathTraversalError(
            f"Path contains disallowed components (null byte or '..'): {raw!r}"
        )

    resolved = (base / raw).resolve()

    try:
        resolved.relative_to(base)
    except ValueError:
        raise PathTraversalError(
            f"Path escapes base directory: {resolved} is not under {base}"
        ) from None

    if must_exist:
        try:
            exists = resolved.exists()
        except OSError as exc:
            raise PathTraversalError(f"Path resolution failed: {resolved}: {exc}") from exc
        if not exists:
            raise FileNotFoundError(f"Validated path does not exist: {resolved}")

    if not allow_create:
        try:
            exists = resolved.exists()
        except OSError as exc:
            raise PathTraversalError(f"Path resolution failed: {resolved}: {exc}") from exc
        if not exists:
            raise FileNotFoundError(f"Path does not exist and creation is not allowed: {resolved}")

    return resolved


def safe_join(
    base_dir: Union[str, Path],
    *components: str,
) -> Path:
    """Safely join path components under *base_dir*, preventing traversal.

    Each component is validated individually so that no single component
    can escape the base directory.  This is the preferred helper for
    constructing paths from user-supplied names (e.g. repo_name, filenames).

    Args:
        base_dir: The root directory that the final path must remain within.
        *components: Individual path segments (e.g. repo_name, "src",
            "personality", "active_profile.json").

    Returns:
        The resolved, validated Path object.

    Raises:
        PathTraversalError: If any component would escape *base_dir*.
        ValueError: If any component is empty or contains malicious input.
    """
    base = Path(base_dir).resolve()

    if not components:
        return base

    for comp in components:
        if not comp:
            raise ValueError("Empty path component provided")
        if _TRAVERSAL_PATTERN.search(comp):
            raise PathTraversalError(f"Path component contains disallowed characters: {comp!r}")
        # Reject absolute components (leading slash or drive letter on Windows)
        if PurePosixPath(comp).is_absolute() or os.path.isabs(comp):
            raise PathTraversalError(f"Absolute path component not allowed: {comp!r}")

    candidate = base
    for comp in components:
        candidate = candidate / comp

    resolved = candidate.resolve()

    try:
        resolved.relative_to(base)
    except ValueError:
        raise PathTraversalError(
            f"Joined path escapes base directory: {resolved} is not under {base}"
        ) from None

    return resolved


# os.open()'s dir_fd parameter is POSIX-only. Where it is missing (Windows), the
# component-by-component walk below cannot be performed at all, and the code
# falls back to the single resolved-path open that preceded it. That fallback is
# named here rather than left implicit: it still carries O_NOFOLLOW, so it keeps
# the final-component guarantee, and it loses only the intermediate-component
# one. Silently degrading a security control is the failure mode this repo keeps
# finding, so callers get the weaker guarantee knowingly, not by accident.
_SUPPORTS_DIR_FD = os.open in getattr(os, "supports_dir_fd", set())


def _is_symlink_at_path(path: Path) -> bool:
    """Is *path* itself a symlink? False if it has since vanished."""
    try:
        return stat.S_ISLNK(os.lstat(str(path)).st_mode)
    except OSError:
        return False


def _is_symlink_at(dir_fd: int, name: str) -> bool:
    """Is *name* a symlink, as seen from *dir_fd*? False if it has since vanished."""
    try:
        return stat.S_ISLNK(os.lstat(name, dir_fd=dir_fd).st_mode)
    except OSError:
        return False


def _open_contained(resolved: Path, base: Path, flags: int) -> int:
    """Open *resolved* by walking down from *base* one component at a time.

    validate_path() resolves the path and checks containment, and the caller
    then opens it by pathname -- which re-resolves the whole thing from scratch.
    O_NOFOLLOW closes that check-to-open window for the FINAL component only,
    because that is the only component open() inspects. A concurrent swap of any
    intermediate parent directory for a symlink still redirects the read outside
    base (issue #337).

    Walking from a trusted base fd removes the pathname re-resolution entirely:
    each component is opened relative to the fd of the component before it, so
    there is no second traversal for an attacker to race. O_NOFOLLOW on every
    component then makes a swapped-in symlink an error rather than a redirect.

    That O_NOFOLLOW is safe for legitimate paths precisely because *resolved*
    came from Path.resolve(): every symlink in it has already been dereferenced,
    so no component of it should be a symlink. One appearing mid-walk means the
    tree changed under us, which is the attack this closes -- so it is reported
    as PathTraversalError rather than a bare OSError.

    Returns an open fd the caller owns and must close.
    """
    # relative_to() is safe here: validate_path() has already established that
    # resolved is inside base, and both are resolved absolute paths.
    parts = resolved.relative_to(base).parts

    if not _SUPPORTS_DIR_FD:
        # Fail closed. The previous version fell back to opening the resolved
        # pathname here, which keeps the final-component guarantee but not the
        # intermediate one -- i.e. exactly the hole this function exists to
        # close, left open on a platform where it happens to be inconvenient.
        # Documenting a security control as partially unenforced is the failure
        # mode this repo keeps finding, so the fallback is refused rather than
        # explained. The estate deploys on Linux throughout (Docker Compose,
        # Dockerfiles, Fly.io), so nothing shipped reaches this branch.
        raise PathTraversalError(
            "Containment cannot be enforced on this platform: os.open() has no "
            "dir_fd support, so intermediate path components cannot be opened "
            "relative to a trusted base and a concurrent symlink swap could "
            f"redirect the read outside {base}."
        )

    dir_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    # O_NOFOLLOW on the base too, not just its children: base is itself the
    # output of Path.resolve(), so it should not be a symlink either, and
    # opening it by name is one more chance for the tree to have changed since
    # validate_path() ran. Without this the walk could start from the wrong
    # root and every careful step below would be relative to it.
    try:
        fd = os.open(str(base), dir_flags | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.ENOTDIR) and _is_symlink_at_path(base):
            raise PathTraversalError(
                f"Base directory {base} is a symlink; the tree changed after validation."
            ) from exc
        raise
    try:
        for i, name in enumerate(parts):
            is_last = i == len(parts) - 1
            step_flags = (flags if is_last else dir_flags) | getattr(os, "O_NOFOLLOW", 0)
            try:
                nxt = os.open(name, step_flags, dir_fd=fd)
            except OSError as exc:
                # O_NOFOLLOW reports a symlink as ELOOP for the final component,
                # but an intermediate one is opened with O_DIRECTORY too and
                # Linux answers ENOTDIR there instead -- the symlink is simply
                # not a directory. ENOTDIR is also what an ordinary file in the
                # middle of a path gives, which is a caller mistake and not an
                # attack, so the errno alone cannot classify this. lstat on the
                # same dir_fd settles it without re-resolving anything.
                if exc.errno in (errno.ELOOP, errno.ENOTDIR) and _is_symlink_at(fd, name):
                    raise PathTraversalError(
                        f"Path component {name!r} is a symlink; the tree changed "
                        f"after validation: {resolved}"
                    ) from exc
                raise
            os.close(fd)
            fd = nxt
            # O_DIRECTORY already enforces this on Linux, but it is not required
            # by POSIX and getattr() degrades it to 0 where it is absent -- in
            # which case an intermediate file would be opened as if it were a
            # directory and the walk would continue past it.
            if not is_last and not getattr(os, "O_DIRECTORY", 0):
                if not stat.S_ISDIR(os.fstat(fd).st_mode):
                    raise NotADirectoryError(
                        f"Path component {name!r} is not a directory: {resolved}"
                    )
    except BaseException:
        os.close(fd)
        raise
    return fd


def read_validated_file_text(
    rel: Union[str, Path],
    base_dir: Union[str, Path],
    *,
    max_bytes: int = 10 * 1024 * 1024,
    encoding: str = "utf-8",
) -> tuple[str, int]:
    """Read a file after validating it stays within *base_dir*.

    Returns:
        (text, size_in_bytes) tuple.

    Raises:
        PathTraversalError: If the path escapes *base_dir*.
        FileNotFoundError: If the file does not exist.
        ValueError: If the file exceeds *max_bytes*.
    """
    base = Path(base_dir).resolve()
    resolved = validate_path(rel, base, must_exist=True)
    if not resolved.is_file():
        raise FileNotFoundError(f"Validated path is not a regular file: {resolved}")
    # Open via file descriptor to keep the validated path object out of the
    # taint flow that static analyzers (CodeQL) track from user-supplied input,
    # and walk down from base so no component of the path is re-resolved by
    # name after validation -- see _open_contained().
    fd = _open_contained(resolved, base, os.O_RDONLY)
    try:
        st = os.fstat(fd)
        # is_file() above tested the pathname; this tests the descriptor that
        # was actually opened. Without it a directory or device swapped in
        # mid-walk would be read as though the earlier check still applied.
        if not stat.S_ISREG(st.st_mode):
            raise FileNotFoundError(f"Validated path is not a regular file: {resolved}")
        size = st.st_size
        if size > max_bytes:
            raise ValueError(f"File too large: {size} bytes > {max_bytes} bytes limit: {resolved}")
        with os.fdopen(fd, "r", encoding=encoding, errors="replace") as fh:
            fd = -1  # fdopen takes ownership; don't double-close
            text = fh.read()
    finally:
        if fd != -1:
            os.close(fd)
    return text, size


def sanitize_filename(name: str, max_length: int = 255) -> str:
    """Sanitize a filename to prevent traversal and injection attacks.

    Strips directory separators, null bytes, and control characters.
    Enforces a maximum length.  Returns a safe filename string.

    Args:
        name: The raw filename to sanitize.
        max_length: Maximum allowed length (default 255, typical FS limit).

    Returns:
        A sanitized filename string.

    Raises:
        ValueError: If the name is empty or entirely invalid after sanitization.
    """
    if not name:
        raise ValueError("Filename must not be empty")

    # Remove path separators, null bytes, and control characters
    sanitized = re.sub(r"[/\\:\x00-\x1f\x7f]", "", name)

    # Remove leading dots (hidden files / traversal)
    sanitized = sanitized.lstrip(".")

    # Collapse whitespace
    sanitized = sanitized.strip()

    if not sanitized:
        raise ValueError(f"Filename {name!r} is invalid after sanitization")

    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]

    return sanitized


def list_validated_children_fd(
    rel: Union[str, Path],
    base_dir: Union[str, Path],
) -> list[dict]:
    """List children of a validated directory path via a file descriptor.

    Same containment guarantee as list_validated_children(), but avoids
    calling exists()/is_dir()/iterdir() on the validated Path object — those
    calls keep the user-supplied path in the taint flow that static analyzers
    (CodeQL) track, the same reason read_validated_file_text() reads through
    an fd instead of Path.open(). os.scandir() accepts a directory fd
    directly, so iteration never touches the tainted string/Path again.

    Returns a list of dicts with keys: name, type ('file'/'directory'), size,
    modified.

    Raises:
        PathTraversalError: If the path escapes *base_dir*.
        FileNotFoundError: If the directory does not exist.
        NotADirectoryError: If the validated path is not a directory.
    """
    base = Path(base_dir).resolve()
    resolved = validate_path(rel, base, must_exist=True)
    try:
        # Walked down from base one component at a time, so no part of the path
        # is re-resolved by name after validation -- see _open_contained().
        fd = _open_contained(resolved, base, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except NotADirectoryError as exc:
        raise NotADirectoryError(f"Validated path is not a directory: {resolved}") from exc
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Validated path does not exist: {resolved}") from exc

    children: list[dict] = []
    try:
        with os.scandir(fd) as it:
            for entry in it:
                try:
                    entry_stat = entry.stat()
                    children.append(
                        {
                            "name": entry.name,
                            "type": "directory" if entry.is_dir() else "file",
                            "size": entry_stat.st_size if entry.is_file() else 0,
                            "modified": entry_stat.st_mtime,
                        }
                    )
                except OSError:
                    continue
    finally:
        os.close(fd)
    return sorted(children, key=lambda c: (c["type"] != "directory", c["name"].lower()))


def list_validated_children(
    rel: Union[str, Path],
    base_dir: Union[str, Path],
) -> list[dict]:
    """List children of a validated directory path.

    Delegates to list_validated_children_fd(). This used to have its own
    implementation -- validate_path() followed by resolved.iterdir() -- which
    is the check-then-use pattern _open_contained() exists to replace. It
    caught a symlink that was already in place at validation time, but it
    re-walked the path by name afterwards, so a component swapped between the
    two steps was followed; and because it never called _open_contained(), it
    kept listing on platforms without os.open() dir_fd support, where the
    read path deliberately refuses. A containment guarantee that the file
    reader honours and the directory lister does not is not a guarantee.

    Returns a list of dicts with keys: name, type ('file'/'directory'), size.
    The 'modified' key from the fd variant is dropped here to keep this
    function's documented contract unchanged.

    Raises:
        PathTraversalError: If the path escapes *base_dir*, or if containment
            cannot be enforced on this platform.
        FileNotFoundError: If the directory does not exist.
        NotADirectoryError: If the validated path is not a directory.
    """
    return [
        {"name": c["name"], "type": c["type"], "size": c["size"]}
        for c in list_validated_children_fd(rel, base_dir)
    ]
