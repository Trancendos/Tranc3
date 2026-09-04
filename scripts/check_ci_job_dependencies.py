#!/usr/bin/env python3
"""Every script a CI job runs must be importable with what that job installs.

The break this prevents
-----------------------
`ci.yml`'s Service Topology job installed PyYAML and nothing else, which was
right when its steps only parsed compose. The guards grew: they now import
real platform modules, because reading the language registry is the only way
to check the language registry. The day `src/townhall/plm.py` started importing
the event-type enum — a pure `str, Enum` living in a module built on pydantic —
the job broke, and the failure said `ModuleNotFoundError: No module named
'pydantic'` several import hops from anything the change touched.

Nothing connected the job's `pip install` line to what its steps need, so the
two drifted silently until a run failed. This is that connection.

How it decides
--------------
For each `python scripts/x.py` step in a job, it walks the script's imports,
follows the ones that resolve to files in this repository, and collects the
top-level names that do not. Whatever is left, minus the standard library, is
what the job must install.

What it checks, and what it deliberately does not
------------------------------------------------
Only imports that execute when the module is *imported*: module level, and
inside class bodies, which also run.

An import inside a function is skipped, because whether it runs is not
statically knowable — `src/event_bus/bus.py` imports httpx inside a webhook
branch that a documentation render never reaches, and failing on that would
report a break that cannot happen. An import wrapped in `try/except
ImportError` is skipped too: that is how this repository declares an optional
dependency, and `src/event_bus/nats_transport.py` says so in as many words.

A name it cannot classify is reported rather than assumed present. Being noisy
about a real import is recoverable; being silent about a missing one is the
drift this exists to end.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"

#: Distribution name -> the top-level module it provides, where they differ.
_DISTRIBUTION_MODULES = {
    "pyyaml": "yaml",
    "python-dateutil": "dateutil",
    "pytest-asyncio": "pytest_asyncio",
    "pytest-cov": "pytest_cov",
    "beautifulsoup4": "bs4",
}


def _installed_modules(job: dict) -> set[str]:
    """Top-level module names the job's pip install steps provide."""
    provided: set[str] = set()
    for step in job.get("steps", []):
        run = step.get("run") or ""
        for match in re.finditer(r"pip install\s+([^\n&|]+)", run):
            for token in match.group(1).split():
                if token.startswith("-") or token.endswith(".txt"):
                    continue
                name = re.split(r"[=<>\[]", token)[0].strip().lower()
                provided.add(_DISTRIBUTION_MODULES.get(name, name.replace("-", "_")))
    return provided


def _scripts_run(job: dict) -> list[Path]:
    scripts: list[Path] = []
    for step in job.get("steps", []):
        for match in re.finditer(r"python3?\s+(scripts/[\w./-]+\.py)", step.get("run") or ""):
            path = REPO / match.group(1)
            if path.exists() and path not in scripts:
                scripts.append(path)
    return scripts


def _module_file(dotted: str) -> Path | None:
    """Resolve a dotted name to a file in this repository, or None."""
    parts = dotted.split(".")
    for candidate in (
        REPO.joinpath(*parts).with_suffix(".py"),
        REPO.joinpath(*parts, "__init__.py"),
    ):
        if candidate.exists():
            return candidate
    return None


def _guarded(handlers: list[ast.ExceptHandler]) -> bool:
    """Does this try block treat a missing module as an expected outcome?"""
    for handler in handlers:
        if handler.type is None:
            return True
        candidates = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
        for candidate in candidates:
            name = getattr(candidate, "id", None) or getattr(candidate, "attr", None)
            if name in {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}:
                return True
    return False


def _import_time_nodes(body: list[ast.stmt]) -> list[ast.stmt]:
    """Statements that run when the module is imported.

    Descends into `if`, `with`, `for`, `while` and class bodies — all of which
    execute — and stops at function boundaries, which do not. A `try` whose
    handlers catch an import failure is skipped entirely: that is an optional
    dependency, declared the way this repository declares them.
    """
    found: list[ast.stmt] = []
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if isinstance(node, ast.Try):
            if _guarded(node.handlers):
                continue
            found.extend(_import_time_nodes(node.body + node.orelse + node.finalbody))
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            found.append(node)
            continue
        for field in ("body", "orelse", "finalbody"):
            nested = getattr(node, field, None)
            if isinstance(nested, list):
                found.extend(_import_time_nodes(nested))
    return found


def external_imports(entry: Path, _seen: set[Path] | None = None) -> set[str]:
    """Top-level names imported from outside this repository, transitively."""
    seen = _seen if _seen is not None else set()
    if entry in seen:
        return set()
    seen.add(entry)

    external: set[str] = set()
    tree = ast.parse(entry.read_text(), filename=str(entry))
    for node in _import_time_nodes(tree.body):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        else:
            # A relative import is local by construction.
            if node.level or not node.module:
                continue
            names = [node.module]
        for dotted in names:
            local = _module_file(dotted)
            if local is not None:
                external |= external_imports(local, seen)
            else:
                external.add(dotted.split(".")[0])
    return external


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", default="topology", help="Job id in ci.yml to check.")
    args = parser.parse_args(argv)

    import yaml  # noqa: PLC0415 - the only dependency this checker itself has

    workflow = yaml.safe_load(WORKFLOW.read_text())
    job = workflow["jobs"].get(args.job)
    if job is None:
        print(f"check_ci_job_dependencies: no job {args.job!r} in {WORKFLOW.name}")
        return 1

    provided = _installed_modules(job) | set(sys.stdlib_module_names) | {"__future__"}
    scripts = _scripts_run(job)
    if not scripts:
        print(f"check_ci_job_dependencies: job {args.job!r} runs no scripts to check")
        return 1

    problems: list[str] = []
    for script in scripts:
        for name in sorted(external_imports(script) - provided):
            problems.append(
                f"{script.relative_to(REPO)} imports {name!r}, "
                f"which job {args.job!r} does not install"
            )

    if problems:
        print("CI job dependency check: FAILED")
        for problem in problems:
            print(f"  [ERROR] {problem}")
        print()
        print(f"Add the missing package to job {args.job!r}'s pip install step in ci.yml.")
        return 1

    print(
        f"CI job dependency check: PASSED — {len(scripts)} script(s) in job "
        f"{args.job!r} import nothing it does not install"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
