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

  * `os.environ["SECRET_KEY"] = ...`          -- overwrites unconditionally
  * `del os.environ["SECRET_KEY"]`            -- removes it
  * `os.environ.pop("SECRET_KEY")`            -- removes it
  * `os.environ.popitem()` / `.clear()`       -- takes it out with the rest
  * `os.environ.update({...})`                -- may overwrite
  * `os.environ.__setitem__("SECRET_KEY", …)` -- the subscript forms written
  * `os.environ.__delitem__("SECRET_KEY")`       as calls, which skipped the
                                                 target scan entirely

The alias forms count too: `import os as o`, `from os import environ as env`
and `env = os.environ` all reach the same mapping, and each was a one-line way
around this check before `_EnvironNames` resolved them.

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
# `setitem` was in this set and could never match: the dunder is `__setitem__`,
# and a subscript assignment is caught by the target scan instead.
# `__setitem__` and `__delitem__` are the dunder forms of the subscript
# assignment and `del` the target scan already catches. Written as calls they
# bypassed that scan entirely, so `os.environ.__setitem__("SECRET_KEY", "x")`
# was a one-line way around this gate.
MUTATING_CALLS = frozenset({"pop", "popitem", "update", "clear", "__setitem__", "__delitem__"})


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
                # Shape, not just truthiness. `_GUARDED_ENV_VARS = "SECRET_KEY"`
                # is a plausible typo and iterating it yields the CHARACTERS
                # 'S', 'E', 'C', ... — a guarded set that matches no real
                # variable, so every module passes and the gate is silently off.
                if not isinstance(value, (list, tuple, set, frozenset)):
                    _fail(
                        "_GUARDED_ENV_VARS is a "
                        f"{type(value).__name__}, not a list/tuple/set — a bare string "
                        "would be read one character at a time, guarding nothing"
                    )
                    raise SystemExit(1)
                if not all(isinstance(item, str) for item in value):
                    _fail("_GUARDED_ENV_VARS contains a non-string entry")
                    raise SystemExit(1)
                names = set(value)
                if not names:
                    _fail("_GUARDED_ENV_VARS is empty")
                    raise SystemExit(1)
                return names
    _fail("no _GUARDED_ENV_VARS assignment found in conftest.py")
    raise SystemExit(1)


class _EnvironNames:
    """The names in one module that actually refer to `os.environ`.

    Matching a bare attribute called `environ` was wrong in both directions:
    it accepted `some_config.environ` (nothing to do with the process
    environment) and missed `import os as o` / `from os import environ as env`,
    either of which lets a module reintroduce the collection-order failure this
    check exists to reject while CI stays green.
    """

    def __init__(self, tree: ast.Module) -> None:
        self.os_modules: set[str] = set()
        self.environs: set[str] = set()
        assignments: list[tuple[list[str], ast.expr]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "os":
                        self.os_modules.add(alias.asname or "os")
            elif isinstance(node, ast.ImportFrom) and node.module == "os":
                for alias in node.names:
                    if alias.name == "environ":
                        self.environs.add(alias.asname or "environ")
            elif isinstance(node, ast.Assign):
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
                if names:
                    assignments.append((names, node.value))

        # Aliases chain, and `ast.walk` is not source order, so one pass over
        # the assignments is not enough: `copy = env` may be visited before
        # `env = os.environ`. Repeat until the alias set stops growing.
        # Without this, `env = os.environ; copy = env; copy["SECRET_KEY"] = "x"`
        # was a two-line way around a gate the one-line version already caught.
        changed = True
        while changed:
            changed = False
            for names, value in assignments:
                if not self.matches(value):
                    continue
                for name in names:
                    if name not in self.environs:
                        self.environs.add(name)
                        changed = True

    def _is_environ_expr(self, node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Attribute)
            and node.attr == "environ"
            and isinstance(node.value, ast.Name)
            and node.value.id in self.os_modules
        )

    def matches(self, node: ast.AST) -> bool:
        """True when `node` evaluates to `os.environ` in this module."""
        if self._is_environ_expr(node):
            return True
        return isinstance(node, ast.Name) and node.id in self.environs


# Bodies that do NOT run when the module is imported.
_DEFERRED = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def _definition_time_children(node: ast.AST):
    """The parts of a `def`/`lambda` that run when the definition is executed.

    Everything except the body: decorators, default values (positional and
    keyword-only), annotations, and a function's return annotation.
    """
    children: list[ast.AST] = []
    children.extend(getattr(node, "decorator_list", []) or [])
    args = getattr(node, "args", None)
    if args is not None:
        children.extend(args.defaults or [])
        children.extend(d for d in (args.kw_defaults or []) if d is not None)
        for group in ("posonlyargs", "args", "kwonlyargs"):
            for arg in getattr(args, group, []) or []:
                if arg.annotation is not None:
                    children.append(arg.annotation)
        for extra in (args.vararg, args.kwarg):
            if extra is not None and extra.annotation is not None:
                children.append(extra.annotation)
    returns = getattr(node, "returns", None)
    if returns is not None:
        children.append(returns)
    return children


def _import_time_nodes(tree: ast.Module):
    """Every node evaluated when the module is imported.

    Descends through module level, class bodies and control flow -- `if`,
    `try`, `with`, `for`, `while` all execute during collection -- and stops at
    `def`/`lambda` bodies, which do not. Looking only at `tree.body`, as the
    first version did, missed a guarded write inside a module-level
    `if os.getenv(...):`, which runs at import time exactly like a bare one.

    A decorator on a module-level `def` is skipped with the function it
    decorates; a decorator that mutates the environment would be a stranger
    thing than this check is built to find.
    """
    stack: list[ast.AST] = list(tree.body)
    while stack:
        node = stack.pop()
        if isinstance(node, _DEFERRED):
            # The BODY is deferred; the definition itself is not. Decorators,
            # default values and annotations are all evaluated when the `def`
            # statement runs -- so `def test_x(v=os.environ.pop("SECRET_KEY")):`
            # mutates the environment during collection exactly like a bare
            # line, and skipping the whole node made that invisible.
            stack.extend(_definition_time_children(node))
            continue
        yield node
        stack.extend(ast.iter_child_nodes(node))


def _update_touches_guarded(call: ast.Call, guarded: set[str]) -> bool:
    """Does this `os.environ.update(...)` provably leave the guarded vars alone?

    Flagging every `update()` made the check reject a module that only sets
    unguarded keys, and a check that reports work it did not do gets weakened
    rather than obeyed. So a literal mapping with entirely literal, unguarded
    keys is allowed; anything the reader cannot see through -- a variable, a
    `**spread`, a comprehension -- is flagged, because it cannot be shown safe.
    """
    for keyword in call.keywords:
        if keyword.arg is None or keyword.arg in guarded:
            return True  # `**mapping`, or a guarded name passed directly
    if not call.args:
        return False  # `update()` with only unguarded keywords
    mapping = call.args[0]
    if not isinstance(mapping, ast.Dict):
        return True  # not a literal — cannot be proven safe
    for key in mapping.keys:
        if key is None:  # `{**other}`
            return True
        if not isinstance(key, ast.Constant):
            return True  # computed key
        if key.value in guarded:
            return True
    return False


def _test_modules() -> list[Path]:
    """Every file pytest collects from the tests tree.

    Both patterns: `test_*.py` AND `*_test.py`. Scanning only the first left
    `tests/integration/cross_ecosystem_bridge_test.py` -- a real, collected
    module -- outside the gate entirely.
    """
    seen = {path for pattern in ("test_*.py", "*_test.py") for path in TEST_ROOT.rglob(pattern)}
    return sorted(seen)


def violations(guarded: set[str]) -> list[str]:
    """Every import-time write to a guarded variable, across the tests tree."""
    found: list[str] = []
    for path in _test_modules():
        rel = path.relative_to(REPO_ROOT)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            found.append(f"{rel} does not parse ({exc.msg}) — cannot verify it")
            continue

        environ = _EnvironNames(tree)
        for node in _import_time_nodes(tree):
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
            elif isinstance(node, ast.AugAssign):
                targets = [node.target]
            elif isinstance(node, ast.Delete):
                targets = list(node.targets)

            for target in targets:
                if (
                    isinstance(target, ast.Subscript)
                    and environ.matches(target.value)
                    and isinstance(target.slice, ast.Constant)
                    and target.slice.value in guarded
                ):
                    verb = "deletes" if isinstance(node, ast.Delete) else "assigns"
                    found.append(
                        f"{rel}:{node.lineno} {verb} os.environ"
                        f"[{target.slice.value!r}] at import time"
                    )

            # Any call, not only a bare expression statement: the environment is
            # mutated by `_ = os.environ.pop("SECRET_KEY")` exactly as much as by
            # the same call on a line of its own.
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (
                isinstance(func, ast.Attribute)
                and func.attr in MUTATING_CALLS
                and environ.matches(func.value)
            ):
                continue

            if func.attr == "update":
                if not _update_touches_guarded(node, guarded):
                    continue
                detail = "update(...)"
            elif func.attr in ("clear", "popitem"):
                detail = f"{func.attr}()"  # removes guarded vars along with the rest
            else:  # pop, __setitem__, __delitem__ — all take the name first
                arg = node.args[0] if node.args else None
                name = arg.value if isinstance(arg, ast.Constant) else None
                if arg is not None and name not in guarded and isinstance(arg, ast.Constant):
                    continue  # a literal, unguarded name
                # Name the method that was actually called. Reporting every one
                # of these as `pop(...)` would send the reader to a line that
                # does not contain the word.
                detail = f"{func.attr}({name!r})"

            found.append(f"{rel}:{node.lineno} calls os.environ.{detail} at import time")
    return found


def main() -> int:
    guarded = guarded_names()
    problems = violations(guarded)
    modules = len(_test_modules())

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
