#!/usr/bin/env python3
"""Nothing a test imports may terminate the interpreter at import time.

`scripts/estate_lint.py` called `sys.exit(1)` in its module body when PyYAML
was missing. `tests/test_estate_lint.py` imports that module, so during
collection the call raised SystemExit -- which pytest reports as
INTERNALERROR and then abandons the whole run. One absent dependency took
down all ~1000 tests with exit code 3, and because the failure arrived as an
internal error rather than a test failure, nothing in the output named the
cause. `main` stayed red for six days.

The property enforced here: a script that a test imports must not terminate
the interpreter from any code path that runs on import. That is narrower than
"must not contain an exit" and wider than "must not exit at the top level",
and getting the line right is the whole job -- the first version of this check
drew it in four wrong places at once, each of which let the original defect
through in a different spelling. What actually runs on import:

  * the module body, including every `if`/`try`/`with`/`for`/`while` block in it
  * a **class body** -- `class Guard: sys.exit(1)` runs on import
  * a function's **decorators, default arguments and annotations** -- they are
    evaluated when the `def` executes, not when the function is called
  * the `else`/`elif` branch of `if __name__ == "__main__":`

and what does not:

  * a function body, at any nesting depth
  * the `body` of an exact `if __name__ == "__main__":` block

Both spellings of termination count. `raise SystemExit(main())` is the
dominant CLI-exit idiom in this repository -- `ai_bom.py`,
`build_ci_register.py` and `build_container_sboms.py` among others -- so a
check that only looked for `sys.exit` would have missed the most likely way
for someone to reintroduce the defect it exists to prevent.

Discovery reads the tests' syntax, not their text. Tests reach a script two
ways here: a normal `from scripts.foo import ...`, and
`spec_from_file_location(..., <root> / "scripts" / "foo.py")` for a script
that is not importable as a module. The first version matched only the second,
by regex over raw source, so `tests/test_ci_job_dependencies.py` and five
other files were outside its scope entirely while prose mentioning a path
would have pulled an unrelated script in.

This stays a syntactic check rather than an import-and-see: the pattern
matters precisely when the script's dependencies are missing, which is
exactly when importing it would fail.

Usage:
    python scripts/check_importable_scripts.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
SCRIPTS = ROOT / "scripts"

_EXIT_CALLS = {"exit", "quit", "_exit"}


def _script_from_module(dotted: str) -> str | None:
    """`scripts.check_foo` -> `check_foo.py`; anything else -> None."""
    parts = dotted.split(".")
    if len(parts) == 2 and parts[0] == "scripts":
        return f"{parts[1]}.py"
    return None


def _imports_in(tree: ast.AST) -> set:
    """Scripts this test reaches, by either route the suite actually uses."""
    found = set()
    for node in ast.walk(tree):
        # from scripts.foo import x  /  from scripts import foo, bar
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "scripts":
                for alias in node.names:
                    found.add(f"{alias.name}.py")
            elif (name := _script_from_module(node.module)) is not None:
                found.add(name)
        # import scripts.foo
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if (name := _script_from_module(alias.name)) is not None:
                    found.add(name)
    return found


def _loaded_paths_in(tree: ast.AST) -> set:
    """`... / "scripts" / "foo.py"` built as a path expression, per statement.

    Scoped to one statement so a `.py` constant in one place and the word
    "scripts" in an unrelated line cannot combine into a false hit, and read
    from the AST so a path named in a comment or docstring is not a hit at all.
    """
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.stmt):
            continue
        constants = [
            child.value
            for child in ast.walk(node)
            if isinstance(child, ast.Constant) and isinstance(child.value, str)
        ]
        if "scripts" not in constants:
            continue
        found.update(c for c in constants if c.endswith(".py"))
    return found


def _scripts_imported_by_tests() -> dict:
    """Which scripts the test suite loads, and which test loads each."""
    importers: dict = {}
    for test in sorted(TESTS.rglob("test_*.py")):
        tree = ast.parse(test.read_text(encoding="utf-8"), filename=str(test))
        for name in _imports_in(tree) | _loaded_paths_in(tree):
            importers.setdefault(name, []).append(test.relative_to(ROOT).as_posix())
    return importers


def _is_main_guard(node: ast.stmt) -> bool:
    """Exactly `if __name__ == "__main__":`, nothing looser.

    A looser test treated `if __name__ != "__main__": sys.exit(1)` -- which
    exits on import and only on import -- as the safe case.
    """
    if not isinstance(node, ast.If):
        return False
    test = node.test
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "__name__"
        and len(test.ops) == 1
        and isinstance(test.ops[0], ast.Eq)
        and len(test.comparators) == 1
        and isinstance(test.comparators[0], ast.Constant)
        and test.comparators[0].value == "__main__"
    )


class _ImportTimeExits(ast.NodeVisitor):
    """Collects terminations reachable by importing the module.

    A visitor rather than `ast.walk` because the distinction being drawn is
    about which subtrees execute on import: `walk` descends into every
    function body it finds, which both missed the import-time parts of a
    definition and flagged a deferred body nested inside a module-level
    `if`.
    """

    def __init__(self) -> None:
        self.found: list = []

    def _decorator(self, node) -> None:
        """A bare `@sys.exit` is applied on import without being a Call node."""
        name = None
        if isinstance(node, ast.Name):
            name = node.id
        elif isinstance(node, ast.Attribute):
            name = node.attr
        if name in _EXIT_CALLS:
            self.found.append((node.lineno, f"@{name} decorator"))
        self.visit(node)

    def _definition_time_parts(self, node) -> None:
        """Decorators, defaults and annotations run when the `def` runs."""
        for decorator in node.decorator_list:
            self._decorator(decorator)
        args = node.args
        for default in [*args.defaults, *(d for d in args.kw_defaults if d)]:
            self.visit(default)
        for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs]:
            if arg.annotation:
                self.visit(arg.annotation)
        if node.returns:
            self.visit(node.returns)

    def visit_FunctionDef(self, node) -> None:  # noqa: N802 - ast API
        self._definition_time_parts(node)  # body is deferred

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node) -> None:  # noqa: N802 - ast API
        for decorator in node.decorator_list:
            self._decorator(decorator)
        for base in node.bases:
            self.visit(base)
        for keyword in node.keywords:
            self.visit(keyword.value)
        for statement in node.body:  # a class body runs on import
            self.visit(statement)

    def visit_If(self, node) -> None:  # noqa: N802 - ast API
        self.visit(node.test)
        if _is_main_guard(node):
            for statement in node.orelse:  # the else branch still runs
                self.visit(statement)
            return
        for statement in [*node.body, *node.orelse]:
            self.visit(statement)

    def visit_Call(self, node) -> None:  # noqa: N802 - ast API
        func = node.func
        name = None
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name in _EXIT_CALLS:
            self.found.append((node.lineno, f"{name}()"))
        self.generic_visit(node)

    def visit_Raise(self, node) -> None:  # noqa: N802 - ast API
        exc = node.exc
        target = exc.func if isinstance(exc, ast.Call) else exc
        name = None
        if isinstance(target, ast.Name):
            name = target.id
        elif isinstance(target, ast.Attribute):
            name = target.attr
        if name == "SystemExit":
            self.found.append((node.lineno, "raise SystemExit"))
        self.generic_visit(node)


def _module_level_exits(path: Path) -> list:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    visitor = _ImportTimeExits()
    for statement in tree.body:
        visitor.visit(statement)
    return visitor.found


def main() -> int:
    importers = _scripts_imported_by_tests()
    if not importers:
        # A check that finds nothing to check must say so rather than pass.
        print(
            "No test imports any script. Either the suite changed shape or this "
            "check's discovery no longer matches it; a check with an empty scope "
            "reports the same PASSED as a clean estate."
        )
        return 1

    problems = []
    for name, tests in sorted(importers.items()):
        script = SCRIPTS / name
        if not script.is_file():
            continue  # a module that is not a script in scripts/
        for lineno, call in _module_level_exits(script):
            problems.append(
                f"  scripts/{name}:{lineno}: `{call}` runs on import, and "
                f"{', '.join(sorted(set(tests)))} imports this module.\n"
                f"        SystemExit during collection is an INTERNALERROR: "
                f"pytest abandons the\n        entire run, so this would fail "
                f"every test rather than this one file.\n"
                f"        Raise an ordinary exception instead, or move it under "
                f'`if __name__ == "__main__":`.'
            )

    checked = sum(1 for name in importers if (SCRIPTS / name).is_file())
    if problems:
        print(f"Importable-script check: FAILED — {len(problems)} problem(s)")
        print("\n".join(problems))
        return 1

    print(
        f"Importable-script check: PASSED — {checked} script(s) imported by "
        f"tests, none terminates the interpreter on import"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
