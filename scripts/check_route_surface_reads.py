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


def _reads_app_routes(node: ast.AST) -> bool:
    """`<anything ending in `app`>.routes` — bare, `api.app`, `mod.app`."""
    if not (isinstance(node, ast.Attribute) and node.attr == "routes"):
        return False
    base = node.value
    name = getattr(base, "id", None) or getattr(base, "attr", None)
    return name == "app"


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
