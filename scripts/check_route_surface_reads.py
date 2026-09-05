#!/usr/bin/env python3
"""Fail when a test reads the application's route surface through `app.routes`.

The change that broke three tests and silenced two more
------------------------------------------------------
FastAPI 0.141 stopped copying a router's routes into `app.routes` on
`include_router`. It appends one lazy `_IncludedRouter` marker instead and
resolves the real routes at request time. Routing is unaffected: every
endpoint answers exactly as before, and `app.openapi()` lists all 315 paths.

What changed is what `app.routes` shows. It went from the whole surface to
only the routes declared directly on the app — 83 objects out of 342.

Three mount assertions failed loudly on an application that was working
(`/exchange/inventory` answers 200 while the assertion saw an empty set).
Two other scans failed silently, which is worse: `tests/test_rbac.py`'s
mutable-default sweep and `tests/test_api.py`'s handler search kept running,
kept passing, and inspected 24% of what they claimed to.

`tests/support/routes.py` provides `mounted_paths` (from the OpenAPI schema,
the public surface) and `mounted_routes` (route objects, walking
`_IncludedRouter.original_router`). This check keeps the raw attribute from
coming back.

Reading `app.routes` inside `tests/support/routes.py` itself is the point of
that module, so it is the one exemption.

Usage:
    python3 scripts/check_route_surface_reads.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TESTS = REPO / "tests"

#: The two files where reading the attribute is the point: the helper that
#: wraps it, and the test that proves the gap between it and the real surface
#: by comparing the two. Everywhere else, reading it is the defect.
_EXEMPT = {"tests/support/routes.py", "tests/test_route_surface.py"}


def _is_app(node: ast.AST) -> bool:
    """Does this expression name something called `app`?"""
    name = getattr(node, "id", None) or getattr(node, "attr", None)
    return name == "app"


def _reads_app_routes(node: ast.AST) -> bool:
    """`app.routes`, however it is spelled.

    Covers the direct attribute — bare, `api.app`, `mod.app` — and
    `getattr(app, "routes")`, which reaches the same object and would
    otherwise walk straight past a check that only looked for attributes.
    A guard with a documented spelling is a guard with a documented bypass.
    """
    if isinstance(node, ast.Attribute) and node.attr == "routes":
        return _is_app(node.value)
    if isinstance(node, ast.Call):
        func = node.func
        if (getattr(func, "id", None) or getattr(func, "attr", None)) != "getattr":
            return False
        if len(node.args) < 2:
            return False
        target, attribute = node.args[0], node.args[1]
        return (
            _is_app(target) and isinstance(attribute, ast.Constant) and attribute.value == "routes"
        )
    return False


def offenders() -> list[str]:
    """Read with AST, not a regex.

    The first version of this matched source lines and flagged the comment in
    its own explanation. A check that cannot tell code from prose is a check
    people route around by rewording.
    """
    found: list[str] = []
    for path in sorted(TESTS.rglob("*.py")):
        rel = path.relative_to(REPO).as_posix()
        if rel in _EXEMPT or "__pycache__" in rel:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if _reads_app_routes(node):
                found.append(f"{rel}:{node.lineno}: reads app.routes directly")
    return found


def main() -> int:
    found = offenders()
    if found:
        print("Route surface check: FAILED")
        for entry in found:
            print(f"  - {entry}")
        print()
        print("  `app.routes` no longer holds a router's routes — FastAPI 0.141 keeps")
        print("  them behind a lazy marker. A scan over it reports success while")
        print("  inspecting a quarter of the surface.")
        print("  Use tests.support.routes.mounted_paths (paths) or mounted_routes")
        print("  (route objects) instead.")
        return 1
    print("Route surface check: PASSED — no test reads app.routes directly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
