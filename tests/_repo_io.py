"""Cross-platform UTF-8 reads for repo files (Windows defaults to cp1252)."""

from __future__ import annotations

from pathlib import Path


def read_repo_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")
