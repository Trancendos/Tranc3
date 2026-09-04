#!/usr/bin/env python3
"""No statement in `src/` may sit after one that always leaves the frame.

WHY THIS EXISTS

CodeQL raised twelve `py/unreachable-statement` alerts in
`src/agents/goal_manager.py` and the SARIF filter refused to pass them, which
is how they were found. All twelve were the same shape:

    async def remove_goal(self, goal_id: str) -> bool:
        async with self._lock:
            if goal_id in self._goals:
                return True
            return False
        return None          # <- never runs, and contradicts `-> bool`

A sweep of the rest of the tree found twelve MORE, in five other files, that
nothing had ever reported: `src/core/ollama_adapter.py`, `src/mcp/client.py`,
`src/mcp/server.py`, `src/mcp/tools.py` and `src/nanoservices/nano_server.py`.
CodeQL had raised those too — they simply went into the Security tab and
nobody read them, which is the ordinary fate of an alert that blocks nothing.

WHY A LOCAL GATE RATHER THAN LEAVING IT TO CodeQL

CodeQL runs on a schedule and on PRs, reports into a tab, and gates nothing.
This runs in the Service Topology job in about a second and FAILS. The
difference is not coverage; it is whether the finding stops anything, and the
recurring defect on this platform is a control that reports without acting.

WHAT IT DETECTS, AND WHAT IT DELIBERATELY DOES NOT

It walks each statement list and asks whether a statement always leaves the
frame — a `return` or `raise` directly, a `with` whose body does, an `if` whose
branches BOTH do, a `try` whose body and every handler do. Anything after that
is unreachable.

It deliberately does NOT try to prove a condition statically false, or reason
about loops that never terminate, or follow calls to `sys.exit`. Those are the
cases where a checker starts guessing, and a guessing gate that fails a build
gets disabled. Everything it reports is unreachable by the language's own
rules, so a finding is never a matter of opinion.

Usage:
    python scripts/check_unreachable_code.py            # exit 1 on any finding
    python scripts/check_unreachable_code.py --json
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from typing import List, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Trees that are somebody else's to fix, or generated.
EXCLUDED = (
    "compliance/magna-carta",
    "workers/cranbania",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "migrations/versions",
)

#: Where the rule applies. `tests/` is out of scope on purpose: a test may put
#: an unreachable statement in a fixture module ON PURPOSE, as the input to a
#: checker like this one, and failing on it would make this gate unable to be
#: tested.
SCANNED_ROOTS = ("src", "scripts", "api.py")


def _always_leaves(statement: ast.stmt) -> bool:
    """Does control never continue past this statement?"""
    if isinstance(statement, (ast.Return, ast.Raise, ast.Continue, ast.Break)):
        return True
    if isinstance(statement, (ast.With, ast.AsyncWith)):
        return _body_leaves(statement.body)
    if isinstance(statement, ast.If):
        # Only when BOTH arms do. An `if` with no `else` always has a path
        # through it, and treating one as terminal is how a checker like this
        # starts reporting reachable code and gets switched off.
        return (
            bool(statement.orelse)
            and _body_leaves(statement.body)
            and _body_leaves(statement.orelse)
        )
    if isinstance(statement, ast.Try):
        # `finally` can swallow, and an unhandled exception type can escape, so
        # this asks only the narrow question: does every written path leave?
        if statement.orelse and not _body_leaves(statement.orelse):
            return False
        return _body_leaves(statement.body) and all(
            _body_leaves(handler.body) for handler in statement.handlers
        )
    return False


def _body_leaves(body: List[ast.stmt]) -> bool:
    return bool(body) and _always_leaves(body[-1])


def scan_source(text: str, name: str = "<memory>") -> List[Tuple[int, int]]:
    """(unreachable_line, line_of_the_statement_before_it) pairs."""
    try:
        tree = ast.parse(text, filename=name)
    except SyntaxError:
        # A file this cannot parse is not a file with no unreachable code, but
        # ruff and the compile step already fail on it, so reporting it here
        # twice adds noise rather than coverage.
        return []
    findings: List[Tuple[int, int]] = []
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            block = getattr(node, field, None)
            if not isinstance(block, list):
                continue
            for index, statement in enumerate(block[:-1]):
                if _always_leaves(statement):
                    findings.append((block[index + 1].lineno, statement.lineno))
    return sorted(set(findings))


def _files() -> List[str]:
    out: List[str] = []
    for root in SCANNED_ROOTS:
        full = os.path.join(REPO_ROOT, root)
        if os.path.isfile(full):
            out.append(root)
            continue
        for base, dirs, names in os.walk(full):
            dirs[:] = [d for d in dirs if d not in {"__pycache__", "node_modules", ".venv"}]
            for name in names:
                if not name.endswith(".py"):
                    continue
                rel = os.path.relpath(os.path.join(base, name), REPO_ROOT).replace(os.sep, "/")
                if any(prefix in rel for prefix in EXCLUDED):
                    continue
                out.append(rel)
    return sorted(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit findings as JSON")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    problems = []
    for rel in _files():
        try:
            with open(os.path.join(REPO_ROOT, rel), encoding="utf-8") as handle:
                text = handle.read()
        except OSError:
            continue
        for line, after in scan_source(text, rel):
            problems.append(
                {
                    "file": rel,
                    "line": line,
                    "unreachable_because": after,
                }
            )

    if args.json:
        print(json.dumps({"findings": problems}, indent=2, sort_keys=True))
        return 1 if problems else 0

    print(f"Python files scanned: {len(_files())}")
    if not problems:
        print("Unreachable code: PASSED — nothing sits after a statement that always returns")
        return 0
    for problem in problems:
        print(
            f"FAIL {problem['file']}:{problem['line']} is unreachable — the statement at "
            f"line {problem['unreachable_because']} always leaves the frame",
            file=sys.stderr,
        )
    print(
        f"\nUnreachable code: FAILED — {len(problems)} statement(s) can never run. "
        "Delete them; a `return None` under a `-> bool` is not a safety net, it is a "
        "claim about the function that is not true.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
