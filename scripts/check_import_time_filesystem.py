#!/usr/bin/env python3
"""Fail when a module gains a new import-time write to a path outside the repo.

The failure this exists for
---------------------------
`workers/blender-worker`, `workers/ffmpeg-worker` and `workers/triposr-worker`
each created their output directory at module level, defaulting to `/app/...`.
That works in the container, where `/app` exists and is writable, and fails
everywhere else — so nine tests in `tests/test_workers_p5.py` raised
`PermissionError: [Errno 13] Permission denied: '/app'` during collection,
before a single assertion ran, and the Pytest job went red for a reason that
had nothing to do with the code under test.

An import with a filesystem side effect is an import that can fail. The
directory is needed at first use, not at import, and moving it there costs
nothing.

Why a ratchet rather than a rule
--------------------------------
The estate has ~20 more of these, most defaulting to `/data`. They are the
same latent defect, but failing all of them today would put the build red on
day one for work nobody can do that day — which teaches people to wave the
gate through, the outcome this repository has already paid for once (see
`scripts/flow_conformance.py`'s note on the flow baseline).

So the current set is recorded in `config/estate/import_writes_baseline.json`
and this check fails on:

  * a NEW import-time write to an absolute path, and
  * a baselined one that has been fixed without refreshing the baseline.

The second direction matters as much as the first: an improvement that is not
recorded lets the next regression slip in under the old count. Refreshing is
`--write-baseline`, a visible act in the diff.

Repo-relative writes (`Path(__file__).parent / "data"`) are not reported —
they resolve inside the checkout and work wherever the code does.

Usage:
    python3 scripts/check_import_time_filesystem.py
    python3 scripts/check_import_time_filesystem.py --write-baseline
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BASELINE = REPO / "config" / "estate" / "import_writes_baseline.json"

#: Directories whose contents are not this repository's to fix.
_SKIP = (
    ".git",
    "node_modules",
    "__pycache__",
    "compliance/magna-carta",
    "workers/cranbania",
    "aeonmind",
    ".venv",
    "site-packages",
)

#: Calls that create or destroy something on disk.
_WRITE_METHODS = frozenset(
    {"mkdir", "makedirs", "touch", "write_text", "write_bytes", "unlink", "rmtree", "removedirs"}
)


def _module_level(body: list[ast.stmt]) -> list[ast.stmt]:
    """Statements that run on import: everything but function and class bodies."""
    found: list[ast.stmt] = []
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        found.append(node)
        for field in ("body", "orelse", "finalbody"):
            nested = getattr(node, field, None)
            if isinstance(nested, list):
                found.extend(_module_level(nested))
    return found


def _literal_default(node: ast.AST) -> str | None:
    """The string a path expression falls back to, when one is visible.

    Handles the two shapes the estate actually uses:
    `Path("/app/renders")` and `Path(os.environ.get("X", "/app/renders"))`,
    plus `parent`/`/` navigation off either.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return _literal_default(node.left)
    if isinstance(node, ast.Attribute) and node.attr == "parent":
        return _literal_default(node.value)
    if isinstance(node, ast.Call):
        func = node.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name in {"Path", "get", "getenv"}:
            args = node.args
            if name in {"get", "getenv"} and len(args) >= 2:
                return _literal_default(args[1])
            if args:
                return _literal_default(args[0])
    return None


def _base_name(node: ast.AST) -> str | None:
    """The variable a write call is anchored on, e.g. `DB_PATH.parent.mkdir()`."""
    while isinstance(node, (ast.Attribute, ast.Subscript)):
        node = node.value
    if isinstance(node, ast.BinOp):
        return _base_name(node.left)
    return node.id if isinstance(node, ast.Name) else None


def scan_file(path: Path) -> list[str]:
    """Absolute-path import-time writes in one file, as `path:line: method`."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []

    statements = _module_level(tree.body)
    defaults: dict[str, str] = {}
    for node in statements:
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            literal = _literal_default(node.value)
            if literal is None:
                continue
            for target in targets:
                if isinstance(target, ast.Name):
                    defaults[target.id] = literal

    found: list[str] = []
    for node in statements:
        if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)):
            continue
        func = node.value.func
        method = getattr(func, "attr", None) or getattr(func, "id", None)
        if method not in _WRITE_METHODS:
            continue
        anchor = _base_name(func) if isinstance(func, ast.Attribute) else None
        literal = defaults.get(anchor or "")
        if literal is None and node.value.args:
            literal = _literal_default(node.value.args[0])
        if literal is None or not literal.startswith("/"):
            continue
        found.append(f"{path.relative_to(REPO).as_posix()}:{node.lineno}: {method} {literal}")
    return found


def scan() -> list[str]:
    found: list[str] = []
    for path in sorted(REPO.rglob("*.py")):
        posix = path.as_posix()
        if any(skip in posix for skip in _SKIP):
            continue
        found.extend(scan_file(path))
    return sorted(found)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-baseline", action="store_true", help="record the current set as the baseline"
    )
    args = parser.parse_args(argv)

    current = scan()

    if args.write_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
        print(f"baseline written: {len(current)} import-time absolute write(s)")
        return 0

    if not BASELINE.exists():
        print(f"Import-time filesystem check: FAILED — {BASELINE} is missing", file=sys.stderr)
        return 1

    baseline = set(json.loads(BASELINE.read_text(encoding="utf-8")))
    added = sorted(set(current) - baseline)
    fixed = sorted(baseline - set(current))

    if added or fixed:
        print("Import-time filesystem check: FAILED")
        for entry in added:
            print(f"  [NEW] {entry}")
            print("        An import that writes outside the repo cannot succeed off-container.")
            print("        Create the directory at first use instead.")
        for entry in fixed:
            print(f"  [FIXED, UNRECORDED] {entry}")
            print("        Refresh with: python3 scripts/check_import_time_filesystem.py")
            print("        --write-baseline — an improvement nobody records lets the next")
            print("        regression slip in under the old count.")
        return 1

    print(f"Import-time filesystem check: PASSED — {len(current)} recorded, none added or fixed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
