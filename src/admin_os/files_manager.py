"""Sandboxed file and folder operations for Infinity Admin OS."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any

from Dimensional.path_validation import (
    PathTraversalError,
    list_validated_children_fd,
    read_validated_file_text,
    validate_path,
)

_SAFE_PATH_RE = re.compile(r"[^A-Za-z0-9_./-]")

_ROOT = Path(os.environ.get("ADMIN_OS_WORKSPACE_ROOT", "data/admin_os_workspace")).resolve()


def workspace_root() -> Path:
    root = _ROOT
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_path(relative: str) -> Path:
    rel = (relative or "").strip().replace("\\", "/").lstrip("/")
    if not rel or rel == "/":
        rel = "."
    sanitized = _SAFE_PATH_RE.sub("_", rel)
    if sanitized != rel:
        raise PermissionError("Path contains invalid characters")
    try:
        return validate_path(sanitized, workspace_root(), allow_create=True)
    except PathTraversalError as exc:
        raise PermissionError("Path escapes workspace root") from exc


def list_dir(relative: str = "") -> dict[str, Any]:
    rel = (relative or "").strip().replace("\\", "/").lstrip("/")
    sanitized = _SAFE_PATH_RE.sub("_", rel) if rel else rel
    if sanitized != rel:
        raise PermissionError("Path contains invalid characters")
    prefix = rel.rstrip("/") if rel and rel != "." else ""
    try:
        children = list_validated_children_fd(rel or ".", workspace_root())
    except PathTraversalError as exc:
        raise PermissionError("Path escapes workspace root") from exc
    except FileNotFoundError as exc:
        raise FileNotFoundError(relative or "/") from exc
    except NotADirectoryError as exc:
        raise NotADirectoryError(relative) from exc
    entries = [
        {
            "name": child["name"],
            "path": f"{prefix}/{child['name']}" if prefix else child["name"],
            "type": child["type"],
            "size": child["size"] if child["type"] == "file" else None,
            "modified": child["modified"],
        }
        for child in children
    ]
    return {
        "path": relative or "/",
        "root": str(workspace_root()),
        "entries": entries,
    }


def read_file(relative: str, *, max_bytes: int = 512_000) -> dict[str, Any]:
    rel = (relative or "").strip().replace("\\", "/").lstrip("/")
    try:
        text, size = read_validated_file_text(rel, workspace_root(), max_bytes=max_bytes)
    except PathTraversalError as exc:
        raise PermissionError("Path escapes workspace root") from exc
    except FileNotFoundError as exc:
        raise FileNotFoundError(relative) from exc
    return {"path": relative, "size": size, "content": text, "encoding": "utf-8"}


def write_file(relative: str, content: str, *, create: bool = True) -> dict[str, Any]:
    path = _safe_path(relative)
    if path.exists() and path.is_dir():
        raise IsADirectoryError(relative)
    if not create and not path.exists():
        raise FileNotFoundError(relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {"path": relative, "size": path.stat().st_size, "written": True}


def mkdir(relative: str) -> dict[str, Any]:
    path = _safe_path(relative)
    path.mkdir(parents=True, exist_ok=True)
    return {"path": relative, "created": True}


def delete_path(relative: str) -> dict[str, Any]:
    path = _safe_path(relative)
    if not path.exists():
        raise FileNotFoundError(relative)
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    return {"path": relative, "deleted": True}
