# workers/infinity-ai/sanitize.py
# Vendored copy of Dimensional/sanitize.py's sanitize_for_log().
#
# service.py imported this unconditionally from the repo-root `Dimensional`
# package, but this worker's Docker build context is `./workers/infinity-ai`
# only (see docker-compose.production.yml) — a path outside that context is
# never visible to the build, so the import raised ModuleNotFoundError on
# every container start. Vendoring the one function actually used keeps this
# worker self-contained within its own build context, matching every other
# worker in this repo. Keep in sync with Dimensional/sanitize.py if that
# module's sanitize_for_log() changes.

from __future__ import annotations

import re
from typing import Any

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_NEWLINE_RE = re.compile(r"[\r\n]+")
_MAX_LOG_FIELD_LENGTH = 1024


def sanitize_for_log(
    value: Any,
    *,
    max_length: int = _MAX_LOG_FIELD_LENGTH,
    replacement: str = "_",
) -> str:
    """Sanitize a value for safe inclusion in log messages (strips control
    chars, collapses newlines, truncates) to prevent log injection."""
    text = str(value)
    text = _CONTROL_CHAR_RE.sub("", text)
    text = _NEWLINE_RE.sub(replacement, text)
    if len(text) > max_length:
        text = text[:max_length] + "...[truncated]"
    return text
