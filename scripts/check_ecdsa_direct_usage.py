#!/usr/bin/env python3
"""Fail if any service starts using ecdsa directly.

The accepted-risk entry for CVE-2024-23342 (.trivyignore) is scoped to a specific
claim: ecdsa is only ever reached transitively via python-jose's native-python
backend, and every affected service's JWT usage is HS256/RS256-only, so the
vulnerable ECDSA sign/ECDH/keygen paths are never invoked. That claim was
verified once by hand; this script re-verifies it on every CI run so it can't
silently go stale as the codebase changes.

Scans for: direct `import ecdsa` / `from ecdsa import ...` (including submodules,
e.g. `from ecdsa.keys import SigningKey`), and ES256/ES384/ES512 JWT algorithm
usage (the one thing that would actually exercise the vulnerable code paths).
Exits non-zero — failing the CI job — if either is found.

Uses `ast` rather than line-based regex for both checks: comments never appear in
the parsed tree at all, and module/class/function docstrings are explicitly
excluded, so an ES256 mention in prose (like this docstring) can't trigger a
false positive — only an appearance in actual code (an import statement, a
string literal passed as an argument, etc.) counts. A file that fails to parse
is treated as a violation, not skipped — this check is fail-closed: an unreadable
or unparseable file must not silently pass the accepted-risk gate.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

_ES_ALGORITHMS = {"ES256", "ES384", "ES512"}

# aeonmind/ is a separate, undeployed framework spec — not in scope for this
# platform's JWT/ecdsa accepted-risk claim (see CLAUDE.md's AeonMind naming rule).
_EXCLUDE_DIRS = {".git", "node_modules", "aeonmind", "__pycache__", ".venv", "venv"}


def _iter_python_files() -> list[Path]:
    files = []
    for path in REPO_ROOT.rglob("*.py"):
        if any(part in _EXCLUDE_DIRS for part in path.parts):
            continue
        if path == Path(__file__).resolve():
            continue
        files.append(path)
    return files


def _is_ecdsa_module(name: str) -> bool:
    return name == "ecdsa" or name.startswith("ecdsa.")


def _docstring_node_ids(tree: ast.Module) -> set[int]:
    """id() of every Constant node that's a module/class/function docstring."""
    ids: set[int] = set()
    candidates: list[ast.AST] = [tree]
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            candidates.append(node)
    for node in candidates:
        body = getattr(node, "body", None)
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            if isinstance(body[0].value.value, str):
                ids.add(id(body[0].value))
    return ids


def _scan_file(path: Path) -> tuple[list[str], list[str]]:
    """Returns (violations, errors) for one file."""
    rel = str(path.relative_to(REPO_ROOT))
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [], [f"{rel}: could not read file ({exc}) — treated as a failure, not skipped"]

    try:
        tree = ast.parse(source, filename=rel)
    except SyntaxError as exc:
        return [], [f"{rel}: could not parse as Python ({exc}) — treated as a failure, not skipped"]

    violations: list[str] = []
    docstring_ids = _docstring_node_ids(tree)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_ecdsa_module(alias.name):
                    violations.append(
                        f"{rel}:{node.lineno}: direct ecdsa import — 'import {alias.name}'"
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.module and _is_ecdsa_module(node.module):
                violations.append(
                    f"{rel}:{node.lineno}: direct ecdsa import — 'from {node.module} import ...'"
                )
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstring_ids:
                continue
            if node.value in _ES_ALGORITHMS:
                violations.append(f"{rel}:{node.lineno}: ES256/384/512 usage — {node.value!r}")

    return violations, []


def main() -> int:
    violations: list[str] = []
    errors: list[str] = []
    for path in _iter_python_files():
        file_violations, file_errors = _scan_file(path)
        violations.extend(file_violations)
        errors.extend(file_errors)

    if violations or errors:
        print(
            "ecdsa accepted-risk assumption violated — the .trivyignore entry for "
            "CVE-2024-23342 assumes no direct ecdsa usage and no ES256/384/512 JWT "
            "algorithms. Update SECURITY.md and .trivyignore's justification (or "
            "remove the ignore) before merging:",
            file=sys.stderr,
        )
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        for e in errors:
            print(f"  ERROR: {e}", file=sys.stderr)
        return 1

    print("OK: no direct ecdsa usage or ES256/384/512 JWT algorithms found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
