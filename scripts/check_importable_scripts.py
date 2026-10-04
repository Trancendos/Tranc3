#!/usr/bin/env python3
"""Nothing a test imports may terminate the interpreter at import time.

`scripts/estate_lint.py` called `sys.exit(1)` in its module body when PyYAML
was missing. `tests/test_estate_lint.py` imports that module, so during
collection the call raised SystemExit -- which pytest reports as
INTERNALERROR and then abandons the whole run. One absent dependency took
down all ~1000 tests with exit code 3, and because the failure arrived as an
internal error rather than a test failure, nothing in the output named the
cause. `main` stayed red for six days.

The property this check enforces is narrow and mechanical: a script that a
test imports must not call `sys.exit`, `exit`, `quit` or `os._exit` anywhere
outside a function body. A top-level `if __name__ == "__main__":` block is
fine -- it does not run on import.

This is deliberately a syntactic check rather than an import-and-see: the
whole point is to catch the pattern in a script whose dependencies are
missing, which is exactly when importing it would fail.

Usage:
    python scripts/check_importable_scripts.py
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
SCRIPTS = ROOT / "scripts"

_EXITS = {"exit", "quit", "_exit"}

# `spec_from_file_location(..., <root> / "scripts" / "estate_lint.py")` and
# friends -- how these tests reach a script that is not an installed module.
_IMPORTED_SCRIPT = re.compile(r"""["']scripts["']\s*/\s*["']([A-Za-z0-9_.-]+\.py)["']""")


def _scripts_imported_by_tests() -> dict:
    """Which scripts the test suite loads, and which test loads each."""
    importers: dict = {}
    for test in sorted(TESTS.rglob("test_*.py")):
        for name in set(_IMPORTED_SCRIPT.findall(test.read_text(encoding="utf-8"))):
            importers.setdefault(name, []).append(test.relative_to(ROOT).as_posix())
    return importers


def _is_main_guard(node: ast.stmt) -> bool:
    """`if __name__ == "__main__":` -- the one top-level block that may exit."""
    if not isinstance(node, ast.If):
        return False
    test = node.test
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "__name__"
    )


def _module_level_exits(path: Path) -> list:
    """Every exit call reachable by merely importing this file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = []
    for top in tree.body:
        if isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue  # a body that only runs when called
        if _is_main_guard(top):
            continue
        for node in ast.walk(top):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name in _EXITS:
                found.append((node.lineno, name))
    return found


def main() -> int:
    importers = _scripts_imported_by_tests()
    if not importers:
        # A check that finds nothing to check must say so rather than pass.
        print(
            "No test imports any script by path. Either the suite changed shape "
            "or this check's detection pattern no longer matches it; a check "
            "with an empty scope reports the same PASSED as a clean estate."
        )
        return 1

    problems = []
    for name, tests in sorted(importers.items()):
        script = SCRIPTS / name
        if not script.is_file():
            problems.append(f"  {name}: imported by {', '.join(tests)} but not in scripts/")
            continue
        for lineno, call in _module_level_exits(script):
            problems.append(
                f"  scripts/{name}:{lineno}: `{call}()` runs on import, and "
                f"{', '.join(tests)} imports this module.\n"
                f"        SystemExit during collection is an INTERNALERROR: "
                f"pytest abandons the\n        entire run, so this would fail "
                f"every test rather than this one file.\n"
                f"        Raise instead, or move it under "
                f'`if __name__ == "__main__":`.'
            )

    if problems:
        print(f"Importable-script check: FAILED — {len(problems)} problem(s)")
        print("\n".join(problems))
        return 1

    print(
        f"Importable-script check: PASSED — {len(importers)} script(s) imported by "
        f"tests, none exits on import"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
