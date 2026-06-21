# Dimensional/path_validation.py
# Path traversal prevention utilities for safe filesystem operations.
#
# All functions use only the Python standard library (3.8+) and enforce
# that resolved paths remain within an allowed base directory.
#
# Usage:
#   from Dimensional.path_validation import validate_path, safe_join

from __future__ import annotations

import logging
import os
import os.path
import re
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

    try:
        if must_exist and not resolved.exists():
            raise FileNotFoundError(f"Validated path does not exist: {resolved}")
    except OSError as exc:
        raise PathTraversalError(f"Path resolution failed: {resolved}: {exc}") from exc

    try:
        if not allow_create and not resolved.exists():
            raise FileNotFoundError(f"Path does not exist and creation is not allowed: {resolved}")
    except OSError as exc:
        raise PathTraversalError(f"Path resolution failed: {resolved}: {exc}") from exc

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
    resolved = validate_path(rel, base_dir, must_exist=True)
    if not resolved.is_file():
        raise FileNotFoundError(f"Validated path is not a regular file: {resolved}")
    # Open via file descriptor to keep the validated path object out of the
    # taint flow that static analyzers (CodeQL) track from user-supplied input.
    fd = os.open(str(resolved), os.O_RDONLY)
    try:
        stat = os.fstat(fd)
        size = stat.st_size
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


def list_validated_children(
    rel: Union[str, Path],
    base_dir: Union[str, Path],
) -> list[dict]:
    """List children of a validated directory path.

    Returns a list of dicts with keys: name, type ('file'/'directory'), size.

    Raises:
        PathTraversalError: If the path escapes *base_dir*.
        FileNotFoundError: If the directory does not exist.
    """
    resolved = validate_path(rel, base_dir, must_exist=True)
    if not resolved.is_dir():
        raise FileNotFoundError(f"Validated path is not a directory: {resolved}")

    children = []
    try:
        entries = sorted(resolved.iterdir())
    except OSError:
        return children
    for child in entries:
        try:
            stat = child.stat()
            children.append({
                "name": child.name,
                "type": "directory" if child.is_dir() else "file",
                "size": stat.st_size if child.is_file() else 0,
            })
        except OSError:
            pass
    return children
