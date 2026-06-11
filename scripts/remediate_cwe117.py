#!/usr/bin/env python3
"""Batch CWE-117 log injection remediation for CodeQL-flagged files.

Wraps dynamic logger arguments with sanitize_for_log() and converts common
f-string logger calls to %-style formatting.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Files under shared_core use shared_core.sanitize
SHARED_CORE_IMPORT = "from shared_core.sanitize import sanitize_for_log"
DIMENSIONAL_IMPORT = "from Dimensional.sanitize import sanitize_for_log"

# Per-file line-oriented replacements (old substring -> new substring)
REPLACEMENTS: dict[str, list[tuple[str, str]]] = {
    "Dimensional/error_handlers.py": [
        (
            '        log_fn(\n            "Error ref=%s status=%d: %s: %s",\n            ref_id,\n            status_code,\n            type(exc).__name__,\n            exc,\n        )',
            '        log_fn(\n            "Error ref=%s status=%d: %s: %s",\n            ref_id,\n            status_code,\n            sanitize_for_log(type(exc).__name__),\n            sanitize_for_log(exc),\n        )',
        ),
        (
            '        prefix = f"{context}: " if context else ""\n        log_fn(\n            "Error ref=%s status=%d %s%s: %s",\n            ref_id,\n            status_code,\n            prefix,\n            type(exc).__name__,\n            exc,\n        )',
            '        prefix = f"{sanitize_for_log(context)}: " if context else ""\n        log_fn(\n            "Error ref=%s status=%d %s%s: %s",\n            ref_id,\n            status_code,\n            prefix,\n            sanitize_for_log(type(exc).__name__),\n            sanitize_for_log(exc),\n        )',
        ),
    ],
    "shared_core/error_handlers.py": [
        (
            '        log_fn(\n            "Error ref=%s status=%d: %s: %s",\n            ref_id,\n            status_code,\n            type(exc).__name__,\n            exc,\n        )',
            '        log_fn(\n            "Error ref=%s status=%d: %s: %s",\n            ref_id,\n            status_code,\n            sanitize_for_log(type(exc).__name__),\n            sanitize_for_log(exc),\n        )',
        ),
        (
            '        prefix = f"{context}: " if context else ""\n        log_fn(\n            "Error ref=%s status=%d %s%s: %s",\n            ref_id,\n            status_code,\n            prefix,\n            type(exc).__name__,\n            exc,\n        )',
            '        prefix = f"{sanitize_for_log(context)}: " if context else ""\n        log_fn(\n            "Error ref=%s status=%d %s%s: %s",\n            ref_id,\n            status_code,\n            prefix,\n            sanitize_for_log(type(exc).__name__),\n            sanitize_for_log(exc),\n        )',
        ),
    ],
    "src/workflow/routes.py": [
        (
            'logger.error("grid: execution error workflow=%s: %s", workflow_id, exc)',
            'logger.error(\n            "grid: execution error workflow=%s: %s",\n            sanitize_for_log(workflow_id),\n            sanitize_for_log(exc),\n        )',
        ),
    ],
    "workers/blender-worker/worker.py": [
        (
            '            result["stderr"],\n        )',
            '            sanitize_for_log(result["stderr"]),\n        )',
        ),
        (
            'logger.info("Blender found at: %s", blender_path)',
            'logger.info("Blender found at: %s", sanitize_for_log(blender_path))',
        ),
        (
            'logger.info("Running render script (timeout=%ds)", req.timeout)',
            'logger.info("Running render script (timeout=%ds)", sanitize_for_log(req.timeout))',
        ),
    ],
    "src/mcp/server.py": [
        (
            '        client_info.get("name", "unknown"),\n        client_info.get("version", "unknown"),',
            '        sanitize_for_log(client_info.get("name", "unknown")),\n        sanitize_for_log(client_info.get("version", "unknown")),',
        ),
    ],
    "workers/notifications/worker.py": [
        (
            'logger.warning("Webhook URL blocked by SSRF protection: %s", e)',
            'logger.warning("Webhook URL blocked by SSRF protection: %s", sanitize_for_log(e))',
        ),
        (
            'logger.error("Webhook dispatch failed: %s", e)',
            'logger.error("Webhook dispatch failed: %s", sanitize_for_log(e))',
        ),
    ],
    "workers/infinity-auth/worker.py": [
        (
            'logger.exception("Password rehash failed for user=%s", row["user_id"])',
            'logger.exception("Password rehash failed for user=%s", sanitize_for_log(row["user_id"]))',
        ),
    ],
}

# F-string logger conversions for hive_core
FSTRING_LOGGER_RE = re.compile(
    r'logger\.(debug|info|warning|error|exception)\(f"([^"]*)"\)'
)


def _ensure_import(content: str, import_line: str) -> str:
    if import_line in content:
        return content
    if "import logging" in content:
        return content.replace(
            "import logging",
            f"import logging\n\n{import_line}",
            1,
        )
    lines = content.splitlines()
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith(("import ", "from ")):
            insert_at = i + 1
    lines.insert(insert_at, import_line)
    return "\n".join(lines) + ("\n" if content.endswith("\n") else "")


def _convert_fstring_logger(match: re.Match[str]) -> str:
    level = match.group(1)
    template = match.group(2)
    # Split on {expr} — simple brace matching
    parts: list[str] = []
    args: list[str] = []
    i = 0
    while i < len(template):
        if template[i] == "{":
            j = template.find("}", i)
            if j == -1:
                parts.append(template[i:])
                break
            parts.append("%s")
            expr = template[i + 1 : j]
            args.append(f"sanitize_for_log({expr})")
            i = j + 1
        else:
            # literal run until next {
            j = template.find("{", i)
            if j == -1:
                parts.append(template[i:])
                break
            parts.append(template[i:j])
            i = j
    fmt = "".join(parts).replace("%", "%%").replace("%%s", "%s")
    if args:
        return f'logger.{level}("{fmt}", {", ".join(args)})'
    return f'logger.{level}("{fmt}")'


def fix_hive_core(path: Path) -> bool:
    content = path.read_text()
    original = content
    content = _ensure_import(content, DIMENSIONAL_IMPORT)

    def repl(m: re.Match[str]) -> str:
        return _convert_fstring_logger(m)

    content = FSTRING_LOGGER_RE.sub(repl, content)
    if content != original:
        path.write_text(content)
        return True
    return False


def apply_replacements(rel_path: str) -> bool:
    path = REPO / rel_path
    if not path.exists():
        print(f"SKIP missing: {rel_path}")
        return False
    content = path.read_text()
    original = content
    import_line = (
        SHARED_CORE_IMPORT if rel_path.startswith("shared_core/") else DIMENSIONAL_IMPORT
    )
    for old, new in REPLACEMENTS.get(rel_path, []):
        if old in content:
            content = content.replace(old, new)
        else:
            print(f"  NOT FOUND in {rel_path}: {old[:50]}...")
    if content != original:
        content = _ensure_import(content, import_line)
        path.write_text(content)
        print(f"FIXED: {rel_path}")
        return True
    return False


def main() -> int:
    changed = 0
    for rel_path in REPLACEMENTS:
        if apply_replacements(rel_path):
            changed += 1
    hive = REPO / "Dimensional/hive/hive_core.py"
    if hive.exists() and fix_hive_core(hive):
        print("FIXED: Dimensional/hive/hive_core.py (f-strings)")
        changed += 1
    print(f"\n=== Updated {changed} files ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
