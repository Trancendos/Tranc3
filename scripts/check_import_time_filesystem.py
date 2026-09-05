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

What it can and cannot see
--------------------------
It resolves a path only when the default is visible in the source: a string
literal, or `Path(os.environ.get("X", "/default"))`. A path assembled at run
time — from a config object, a function call, an f-string — is invisible to
it, and it says so rather than implying the invariant is total. What it does
cover is every shape the estate actually writes: `mkdir`/`makedirs`/`touch`/
`write_text`/`write_bytes`/`unlink`/`rmtree` on a module- or class-level
name, on a `Path("...")` built in place, and `open(..., "w")` including as a
`with` subject.

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


def _same_scope(body: list[ast.stmt]) -> list[ast.stmt]:
    """Statements that run on import in ONE scope.

    Function bodies do not run on import and are skipped — creating the
    directory in one is the remedy, so flagging it would reject the fix.
    Class bodies DO run on import, but they are a different *scope*, so they
    are not gathered here; `_scopes` walks them separately with their own
    name table. An `if`/`try`/`with` body is the same scope and is gathered.

    A `try`'s handlers run on import too, on the branch the exception takes.
    """
    found: list[ast.stmt] = []
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        found.append(node)
        for field in ("body", "orelse", "finalbody"):
            nested = getattr(node, field, None)
            if isinstance(nested, list):
                found.extend(_same_scope(nested))
        for handler in getattr(node, "handlers", []) or []:
            found.extend(_same_scope(handler.body))
    return found


def _classes(body: list[ast.stmt]) -> list[ast.ClassDef]:
    """Class definitions reachable on import from one scope's statements."""
    found: list[ast.ClassDef] = []
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if isinstance(node, ast.ClassDef):
            found.append(node)
            continue
        for field in ("body", "orelse", "finalbody"):
            nested = getattr(node, field, None)
            if isinstance(nested, list):
                found.extend(_classes(nested))
        for handler in getattr(node, "handlers", []) or []:
            found.extend(_classes(handler.body))
    return found


def _bindings(statements: list[ast.stmt]) -> dict[str, str]:
    """Name -> literal path, for the assignments in one scope."""
    bound: dict[str, str] = {}
    for node in statements:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
            continue
        literal = _literal_default(node.value)
        if literal is None:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                bound[target.id] = literal
    return bound


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


def _calls_in(node: ast.stmt) -> list[tuple[ast.Call, int]]:
    """Calls this statement makes directly — expression, assignment, or `with`.

    `Path(...).mkdir()` as a bare expression was the only shape the first
    version looked at. A write can also be the subject of a `with` (an
    `open(..., "w")` context manager) or the right-hand side of an
    assignment, and neither is any less an import-time write.
    """
    found: list[tuple[ast.Call, int]] = []
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
        found.append((node.value, node.lineno))
    elif isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(node.value, ast.Call):
        found.append((node.value, node.lineno))
    elif isinstance(node, (ast.With, ast.AsyncWith)):
        for item in node.items:
            if isinstance(item.context_expr, ast.Call):
                found.append((item.context_expr, node.lineno))
    return found


#: `open(path, "w")` and friends. Reading is not a write; appending is.
_WRITE_MODES = ("w", "a", "x", "+")


def _write_target(call: ast.Call, defaults: dict[str, str]) -> tuple[str, str] | None:
    """(method, literal path) when this call writes to a path we can resolve."""
    func = call.func
    method = getattr(func, "attr", None) or getattr(func, "id", None)

    if method in {"open"} or (method == "open" and isinstance(func, ast.Attribute)):
        # Only a write mode counts. `open(p)` and `open(p, "r")` read.
        mode = ""
        if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant):
            mode = str(call.args[1].value)
        for keyword in call.keywords:
            if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
                mode = str(keyword.value.value)
        if not any(flag in mode for flag in _WRITE_MODES):
            return None
        target = call.args[0] if call.args else None
        literal = _literal_default(target) if target is not None else None
        if literal is None and isinstance(target, ast.Name):
            literal = defaults.get(target.id)
        return ("open", literal) if literal else None

    if method not in _WRITE_METHODS:
        return None

    literal: str | None = None
    if isinstance(func, ast.Attribute):
        anchor = _base_name(func)
        literal = defaults.get(anchor or "")
        if literal is None:
            # `Path("/app/renders").mkdir()` anchors on a call, not a name.
            literal = _literal_default(func.value)
    if literal is None and call.args:
        literal = _literal_default(call.args[0])
    return (method or "", literal) if literal else None


def scan_file(path: Path) -> list[str]:
    """Absolute-path import-time writes in one file, as `path:line: method`."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []

    # Scope by scope, not one file-wide name table. A class body executes on
    # import, so its writes ARE import-time writes — but its names are its
    # own. Pooling them into one table let `class C: DB_PATH = Path("/tmp/x")`
    # rebind the module's `DB_PATH` and hide the real write behind a
    # harmless-looking path; excluding class bodies from the table instead
    # traded that for the opposite hole, where a class that both binds and
    # writes its own name — `class C: OUT = Path("/app/x"); OUT.mkdir()` —
    # reported nothing at all. A scope inherits the names above it and
    # shadows them locally, which is what Python itself does.
    found: list[str] = []
    relative = path.relative_to(REPO).as_posix()

    def walk(body: list[ast.stmt], inherited: dict[str, str]) -> None:
        statements = _same_scope(body)
        defaults = {**inherited, **_bindings(statements)}
        for node in statements:
            for call, lineno in _calls_in(node):
                report = _write_target(call, defaults)
                if report is None:
                    continue
                method, literal = report
                if not literal.startswith("/"):
                    continue
                found.append(f"{relative}:{lineno}: {method} {literal}")
        for klass in _classes(body):
            walk(klass.body, defaults)

    walk(tree.body, {})
    return found


def scan() -> list[str]:
    """Every import-time absolute-path write in the tree, sorted for stable diffs."""
    found: list[str] = []
    for path in sorted(REPO.rglob("*.py")):
        posix = path.as_posix()
        if any(skip in posix for skip in _SKIP):
            continue
        found.extend(scan_file(path))
    return sorted(found)


def main(argv: list[str] | None = None) -> int:
    """Run the ratchet, or rewrite the baseline. Returns a process exit code."""
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
