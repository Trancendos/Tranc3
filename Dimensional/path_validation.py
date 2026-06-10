# Dimensional/path_validation.py
# Path traversal prevention utilities for safe filesystem operations.
#
# All functions use only the Python standard library (3.8+) and enforce
# that resolved paths remain within an allowed base directory.
#
# Usage:
#   from Dimensional.path_validation import validate_path, safe_join

from __future__ import annotations

import json
import logging
import os
import re
import shutil
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Union

logger = logging.getLogger(__name__)

# Pattern to detect obvious traversal attempts in raw input
_TRAVERSAL_PATTERN = re.compile(r"(?:\.\.)|(?:\x00)")


class PathTraversalError(ValueError):
    """Raised when a path escapes its allowed base directory."""


def _base_dir_realpath(base_dir: Union[str, Path]) -> str:
    return os.path.realpath(str(base_dir))


def _is_path_under_base(candidate: str, base: str) -> bool:
    """Return True when *candidate* is *base* or a path under *base*."""
    candidate = os.path.normpath(candidate)
    base = os.path.normpath(base)
    if candidate == base:
        return True
    return candidate.startswith(base + os.sep)


def _fs_exists(path: str) -> bool:
    """Probe disk for a path already verified under its allowed base (internal)."""
    # codeql[py/path-injection]
    return os.path.exists(path)


def _fs_isfile(path: str) -> bool:
    """Probe whether a base-verified path is a regular file (internal)."""
    # codeql[py/path-injection]
    return os.path.isfile(path)


def _fs_open_text(path: str, *, encoding: str, errors: str):
    """Open a base-verified path for text reads (internal)."""
    # codeql[py/path-injection]
    return open(path, encoding=encoding, errors=errors)


def _fs_open_write(path: str, *, encoding: str):
    """Open a base-verified path for text writes (internal)."""
    # codeql[py/path-injection]
    return open(path, "w", encoding=encoding)


def _fs_makedirs(path: str) -> None:
    """Create a base-verified directory tree (internal)."""
    # codeql[py/path-injection]
    os.makedirs(path, exist_ok=True)


def _fs_rmtree(path: str) -> None:
    """Remove a base-verified directory tree (internal)."""
    # codeql[py/path-injection]
    shutil.rmtree(path, ignore_errors=True)


def _fs_listdir(path: str) -> list[str]:
    """List entries in a base-verified directory (internal)."""
    # codeql[py/path-injection]
    return os.listdir(path)


def _fs_stat_isdir(path: str) -> bool:
    """Return True when a base-verified path is a directory (internal)."""
    # codeql[py/path-injection]
    return os.path.isdir(path)


def _fs_stat_isfile(path: str) -> bool:
    """Return True when a base-verified path is a regular file (internal)."""
    # codeql[py/path-injection]
    return os.path.isfile(path)


def _fs_stat_size(path: str) -> int:
    """Return size of a base-verified regular file (internal)."""
    # codeql[py/path-injection]
    return os.path.getsize(path)


def _validated_path_str(
    path: Union[str, Path],
    base_dir: Union[str, Path],
    *,
    must_exist: bool = False,
    allow_create: bool = True,
    must_be_file: bool = False,
) -> str:
    """Resolve *path* under *base_dir* using os.path (CodeQL path-injection safe)."""
    raw = str(path) if isinstance(path, Path) else path

    if _TRAVERSAL_PATTERN.search(raw):
        raise PathTraversalError(
            f"Path contains disallowed components (null byte or '..'): {raw!r}"
        )

    base = _base_dir_realpath(base_dir)
    if os.path.isabs(raw):
        candidate = os.path.normpath(raw)
    else:
        candidate = os.path.normpath(os.path.join(base, raw))
    resolved = os.path.realpath(candidate)

    if not _is_path_under_base(resolved, base):
        raise PathTraversalError(f"Path escapes base directory: {resolved} is not under {base}")

    if must_exist and not _fs_exists(resolved):
        raise FileNotFoundError(f"Validated path does not exist: {resolved}")

    if not allow_create and not _fs_exists(resolved):
        raise FileNotFoundError(f"Path does not exist and creation is not allowed: {resolved}")

    if must_be_file and not _fs_isfile(resolved):
        raise FileNotFoundError(f"Validated path is not a file: {resolved}")

    return resolved


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
    return Path(
        _validated_path_str(
            path,
            base_dir,
            must_exist=must_exist,
            allow_create=allow_create,
        )
    )


def validate_existing_file(
    path: Union[str, Path],
    base_dir: Union[str, Path],
) -> Path:
    """Validate that *path* resolves to an existing regular file under *base_dir*.

    Combines ``validate_path`` with an ``is_file()`` check so callers do not
    need to touch user-influenced paths after validation (CodeQL path-injection).
    """
    return Path(
        _validated_path_str(
            path,
            base_dir,
            must_exist=True,
            allow_create=False,
            must_be_file=True,
        )
    )


def existing_file_path_str(
    path: Union[str, Path],
    base_dir: Union[str, Path],
) -> str:
    """Return filesystem path string for an existing file under *base_dir*.

    Use for APIs (e.g. ``FileResponse``) that require ``str`` so callers never
    stringify user-influenced paths outside this module (CodeQL path-injection).
    """
    return _validated_path_str(
        path,
        base_dir,
        must_exist=True,
        allow_create=False,
        must_be_file=True,
    )


def read_validated_file_text(
    path: Union[str, Path],
    base_dir: Union[str, Path],
    *,
    max_bytes: int = 512_000,
    encoding: str = "utf-8",
) -> tuple[str, int]:
    """Read text from an existing file under *base_dir* after validation.

    Keeps ``is_file()`` / ``read_text()`` inside this module so callers never
    touch user-influenced paths after validation (CodeQL path-injection).
    """
    safe_path = existing_file_path_str(path, base_dir)
    with _fs_open_text(safe_path, encoding=encoding, errors="replace") as handle:
        payload = handle.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise ValueError(f"File too large (>{max_bytes} bytes)")
    return payload, len(payload.encode(encoding))


def remove_validated_file(
    path: Union[str, Path],
    base_dir: Union[str, Path],
) -> None:
    """Delete an existing file under *base_dir* after validation."""
    os.remove(existing_file_path_str(path, base_dir))


def ensure_validated_directory(
    path: Union[str, Path],
    base_dir: Union[str, Path],
) -> str:
    """Create (if needed) and return a directory path under *base_dir*."""
    resolved = _validated_path_str(path, base_dir, allow_create=True)
    _fs_makedirs(resolved)
    return resolved


def remove_validated_tree(
    path: Union[str, Path],
    base_dir: Union[str, Path],
) -> None:
    """Remove a directory tree under *base_dir* after validation."""
    resolved = _validated_path_str(path, base_dir, must_exist=False, allow_create=True)
    if _fs_exists(resolved):
        _fs_rmtree(resolved)


def list_validated_children(
    path: Union[str, Path],
    base_dir: Union[str, Path],
) -> list[dict[str, Any]]:
    """List immediate children of a validated directory under *base_dir*."""
    resolved = _validated_path_str(path, base_dir, must_exist=True, allow_create=False)
    if not _fs_stat_isdir(resolved):
        raise FileNotFoundError(f"Validated path is not a directory: {resolved}")

    entries: list[dict[str, Any]] = []
    for name in sorted(_fs_listdir(resolved)):
        child = os.path.join(resolved, name)
        is_dir = _fs_stat_isdir(child)
        entries.append(
            {
                "name": name,
                "is_dir": is_dir,
                "file_size": 0 if is_dir else _fs_stat_size(child),
            }
        )
    return entries


def write_validated_json(
    path: Union[str, Path],
    base_dir: Union[str, Path],
    payload: Any,
    *,
    encoding: str = "utf-8",
) -> None:
    """Write JSON to a file under *base_dir*, creating parent directories."""
    parent = str(Path(path).parent) if str(Path(path).parent) not in (".", "") else ""
    if parent:
        ensure_validated_directory(parent, base_dir)
    resolved = _validated_path_str(path, base_dir, allow_create=True)
    with _fs_open_write(resolved, encoding=encoding) as handle:
        json.dump(payload, handle)


def read_validated_json(
    path: Union[str, Path],
    base_dir: Union[str, Path],
    *,
    encoding: str = "utf-8",
) -> Any:
    """Read JSON from an existing file under *base_dir*."""
    resolved = existing_file_path_str(path, base_dir)
    with _fs_open_text(resolved, encoding=encoding, errors="strict") as handle:
        return json.load(handle)


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
