#!/usr/bin/env python3
"""Refuse a test module that overwrites a shared auth env var at import time.

WHY THIS EXISTS

`conftest.py` guards four variables -- INTERNAL_SECRET, SECRET_KEY, JWT_SECRET,
MASTER_KEY_SEED -- because later-imported modules capture them into module-level
constants, so a module that changes one and does not put it back makes unrelated
tests fail depending on collection order.

That guard works, and it caught this. What it cannot do is say WHICH module is
responsible. It is module-scoped, so it fires at the teardown of whichever
module *finishes* with the value wrong -- and when the write happens at import
time, that is a module chosen by collection order, not the one at fault. On
2026-09-03 it failed at `tests/core/test_dependencies.py`, which had done
nothing wrong; the write was in `tests/test_backup_service.py`.

The cost was not a confusing message. `ci.yml`'s Pytest job ran with `-x`, so
that one teardown error stopped the run after FOUR tests, and `|| true` reported
the job green. Measured on run 33808374262: the entire pytest output was
`....E`. The suite had not been running.

`tests/test_encrypted_sqlite.py` had exactly this bug, was fixed, and carries a
long comment explaining it. `tests/test_backup_service.py` had the same bug and
was missed -- which is the argument for a check rather than a comment.

WHAT COUNTS AS A VIOLATION

Only writes that actually change a value already set:

  * `os.environ["SECRET_KEY"] = ...`  -- overwrites unconditionally
  * `os.environ.pop("SECRET_KEY")`    -- removes it
  * `os.environ.update({...})`        -- may overwrite

`os.environ.setdefault(...)` is NOT a violation. `conftest.py` sets all four
before collection, so setdefault is a no-op there; 20 test modules use it and
they are all correct. Flagging them would have made this check noise, and a
noisy check gets weakened.

Only module level counts. The same write inside a fixture that restores it is
the documented, correct pattern -- `tests/test_encrypted_sqlite.py::_shared_env`
is the reference implementation.

It fails closed: a test file that cannot be parsed is a failure, never a pass.

Usage:
    python scripts/check_test_env_isolation.py      # exit 1 on a violation
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_ROOT = REPO_ROOT / "tests"

# Kept in step with conftest.py's _GUARDED_ENV_VARS. Read from there rather than
# duplicated, so the two cannot drift.
CONFTEST = REPO_ROOT / "conftest.py"

# Mutating calls. `setdefault` is deliberately absent -- see the module docstring.
MUTATING_CALLS = frozenset({"pop", "update", "clear", "setitem"})


def _fail(msg: str) -> None:
    print(f"FAIL {msg}", file=sys.stderr)


def guarded_names() -> set[str]:
    """Read `_GUARDED_ENV_VARS` out of conftest.py without importing it."""
    if not CONFTEST.is_file():
        _fail("conftest.py is missing — cannot determine which vars are guarded")
        raise SystemExit(1)
    try:
        tree = ast.parse(CONFTEST.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        _fail(f"conftest.py does not parse ({exc.msg})")
        raise SystemExit(1) from exc
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "_GUARDED_ENV_VARS":
                try:
                    value = ast.literal_eval(node.value)
                except (ValueError, SyntaxError) as exc:
                    _fail("_GUARDED_ENV_VARS is not a literal — cannot verify isolation")
                    raise SystemExit(1) from exc
                names = {str(v) for v in value}
                if not names:
                    _fail("_GUARDED_ENV_VARS is empty")
                    raise SystemExit(1)
                return names
    _fail("no _GUARDED_ENV_VARS assignment found in conftest.py")
    raise SystemExit(1)


def _is_environ(node: ast.AST) -> bool:
    """True for `os.environ` (or a bare `environ` imported from os)."""
    if isinstance(node, ast.Attribute) and node.attr == "environ":
        return True
    return isinstance(node, ast.Name) and node.id == "environ"


def violations(guarded: set[str]) -> list[str]:
    found: list[str] = []
    for path in sorted(TEST_ROOT.rglob("test_*.py")):
        rel = path.relative_to(REPO_ROOT)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            found.append(f"{rel} does not parse ({exc.msg}) — cannot verify it")
            continue

        for node in tree.body:  # module level only; fixtures are fine
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
            elif isinstance(node, ast.AugAssign):
                targets = [node.target]

            for target in targets:
                if (
                    isinstance(target, ast.Subscript)
                    and _is_environ(target.value)
                    and isinstance(target.slice, ast.Constant)
                    and target.slice.value in guarded
                ):
                    found.append(
                        f"{rel}:{node.lineno} assigns os.environ[{target.slice.value!r}] "
                        "at import time"
                    )

            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                func = node.value.func
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr in MUTATING_CALLS
                    and _is_environ(func.value)
                ):
                    arg = node.value.args[0] if node.value.args else None
                    name = arg.value if isinstance(arg, ast.Constant) else None
                    if name in guarded or func.attr in ("update", "clear"):
                        found.append(
                            f"{rel}:{node.lineno} calls os.environ.{func.attr}"
                            f"({name!r}) at import time"
                        )
    return found


def main() -> int:
    guarded = guarded_names()
    problems = violations(guarded)
    modules = len(list(TEST_ROOT.rglob("test_*.py")))

    print(f"Guarded vars: {', '.join(sorted(guarded))}")
    print(f"Test modules scanned: {modules}")
    if problems:
        print()
        for problem in problems:
            _fail(problem)
        print(
            "\nTest env isolation: FAILED — a module-level write to a guarded var runs "
            "during COLLECTION, before any fixture, so it is live for every module "
            "imported after it. Move it into a module-scoped fixture that restores the "
            "prior value; tests/test_encrypted_sqlite.py::_shared_env is the reference. "
            "os.environ.setdefault(...) is fine and is not what this reports.",
            file=sys.stderr,
        )
        return 1
    print("Test env isolation: PASSED — no module overwrites a guarded var at import")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
