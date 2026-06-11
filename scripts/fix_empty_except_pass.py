#!/usr/bin/env python3
"""Replace empty ``except: pass`` handlers with debug logging for CodeQL compliance.

Targets shared_core/, Dimensional/, and archive/ trees. Idempotent: skips handlers
that already contain logging or non-pass statements.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

LOG_STUB_IMPORT = "import logging"
LOG_STUB_LOGGER = "logger = logging.getLogger(__name__)"


def _has_logger(lines: list[str]) -> tuple[bool, str]:
    for line in lines:
        m = re.match(r"^(\w+)\s*=\s*logging\.getLogger\(", line)
        if m:
            return True, m.group(1)
    return False, "logger"


def _code_insert_index(lines: list[str]) -> int:
    """Index after shebang, module docstring, and ``from __future__`` imports."""
    insert_at = 0
    if lines and lines[0].startswith("#!"):
        insert_at = 1

    if insert_at < len(lines):
        stripped = lines[insert_at].strip()
        if stripped.startswith('"""') or stripped.startswith("'''"):
            quote = '"""' if stripped.startswith('"""') else "'''"
            if stripped.count(quote) >= 2 and stripped.endswith(quote):
                insert_at += 1
            else:
                insert_at += 1
                while insert_at < len(lines) and quote not in lines[insert_at]:
                    insert_at += 1
                insert_at += 1

    while insert_at < len(lines) and lines[insert_at].strip() == "":
        insert_at += 1
    while insert_at < len(lines) and lines[insert_at].startswith("from __future__"):
        insert_at += 1
    while insert_at < len(lines) and lines[insert_at].strip() == "":
        insert_at += 1
    return insert_at


def _ensure_logging(lines: list[str]) -> list[str]:
    insert_at = _code_insert_index(lines)
    code_lines = lines[insert_at:]
    has_import = any(
        line.startswith("import logging") or line.startswith("from logging import")
        for line in code_lines
    )
    has_logger, _ = _has_logger(code_lines)
    if has_import and has_logger:
        return lines

    new_lines: list[str] = []
    if not has_import:
        new_lines.append(LOG_STUB_IMPORT)
    if not has_logger:
        if new_lines:
            new_lines.append("")
        new_lines.append(LOG_STUB_LOGGER)

    if new_lines:
        return lines[:insert_at] + new_lines + lines[insert_at:]
    return lines


def _find_empty_except_pass(tree: ast.AST) -> list[tuple[int, int]]:
    """Return list of (except_lineno, pass_lineno) for handlers with only pass."""
    hits: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if len(node.body) != 1 or not isinstance(node.body[0], ast.Pass):
            continue
        hits.append((node.lineno, node.body[0].lineno))
    return hits


def _add_exc_alias(except_line: str) -> str:
    if " as " in except_line:
        return except_line
    stripped = except_line.rstrip()
    if stripped.endswith(":"):
        return stripped[:-1] + " as _exc:"
    return except_line


def fix_file(path: Path, *, dry_run: bool = False) -> int:
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return 0

    hits = _find_empty_except_pass(tree)
    if not hits:
        return 0

    lines = src.splitlines()
    code_start = _code_insert_index(lines)
    has_logger, log_name = _has_logger(lines[code_start:])
    if not has_logger:
        lines = _ensure_logging(lines)
        _, log_name = _has_logger(lines)
        tree = ast.parse("\n".join(lines) + "\n")
        hits = _find_empty_except_pass(tree)

    # Process bottom-up to preserve line numbers
    fixed = 0
    for except_lineno, pass_lineno in sorted(hits, key=lambda x: x[1], reverse=True):
        idx_except = except_lineno - 1
        idx_pass = pass_lineno - 1
        if idx_pass >= len(lines):
            continue
        if lines[idx_pass].strip() != "pass" and not lines[idx_pass].strip().startswith("pass "):
            # pass with trailing comment on same line
            if not re.match(r"^\s*pass\s*(#.*)?$", lines[idx_pass]):
                continue

        indent = re.match(r"^(\s*)", lines[idx_pass]).group(1)
        comment = ""
        m = re.match(r"^\s*pass\s*(#.*)$", lines[idx_pass])
        if m:
            comment = " " + m.group(1)

        lines[idx_except] = _add_exc_alias(lines[idx_except])
        lines[idx_pass] = (
            f'{indent}{log_name}.debug("suppressed %s", _exc, exc_info=False){comment}'
        )
        fixed += 1

    if fixed and not dry_run:
        path.write_text("\n".join(lines) + ("\n" if src.endswith("\n") else ""), encoding="utf-8")
    return fixed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="*", default=["shared_core", "Dimensional", "archive"])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    total = 0
    for root in args.roots:
        root_path = Path(root)
        if not root_path.is_dir():
            continue
        for path in sorted(root_path.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            n = fix_file(path, dry_run=args.dry_run)
            if n:
                print(f"{path}: {n}")
                total += n
    print(f"Total handlers fixed: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
