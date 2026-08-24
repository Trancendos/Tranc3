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


def _fold_str_const(node: ast.AST) -> str | None:
    """Best-effort constant folding for a string literal, simple string
    concatenation (e.g. "ES" + "256"), or an all-constant f-string, so a
    trivially-obfuscated algorithm literal can't silently bypass the scan the
    way a bare 'ES256' string literal would. Deliberately bounded — this is
    not a general constant-propagation pass, just the handful of shapes that
    would otherwise defeat a literal-string check for zero extra cost."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _fold_str_const(node.left)
        right = _fold_str_const(node.right)
        if left is not None and right is not None:
            return left + right
        return None
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            elif (
                isinstance(value, ast.FormattedValue)
                and value.format_spec is None
                and value.conversion in (-1, None)
            ):
                folded = _fold_str_const(value.value)
                if folded is None:
                    return None
                parts.append(folded)
            else:
                return None
        return "".join(parts)
    return None


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


def _joined_str_child_ids(tree: ast.Module) -> set[int]:
    """id() of every Constant that's a literal part of an f-string, at any nesting
    depth — not just JoinedStr.values' immediate Constant entries, but also a
    Constant sitting inside a FormattedValue's .value (e.g. f"{'ES256'}", where the
    interpolated expression is itself just a string literal, not a name/attribute).

    A literal-only f-string like f"ES256" is still walked as both the JoinedStr node
    and its child Constant('ES256') node — without this, the plain-Constant check
    below and the JoinedStr fold-check would each independently flag the same source
    occurrence, reporting it twice in CI output. cubic P3: the original version only
    recorded *direct* JoinedStr.values Constants, so a nested one like f"{'ES256'}"
    was still double-reported — _fold_str_const() folds into FormattedValue.value
    recursively, so this collector must mirror that same recursion to stay in sync.
    The fold-check already covers everything gathered here (and reports the more
    informative "constant-folded" message), so the plain Constant check skips
    anything in this set.

    cubic P1 follow-up: that recursion must only suppress a nested constant when
    the *enclosing* JoinedStr actually folds to a concrete string as a whole — a
    node like f"{'ES256' + suffix}" (suffix non-constant) never folds, so the
    fold-check will never report it, and blindly suppressing 'ES256' here would
    make the whole occurrence invisible to both checks. Only collect when
    _fold_str_const(node) succeeds, so an unfoldable f-string's literal segments
    stay visible to the plain-Constant check instead.
    """
    ids: set[int] = set()

    def _collect(node: ast.AST) -> None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            ids.add(id(node))
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            _collect(node.left)
            _collect(node.right)
        elif isinstance(node, ast.JoinedStr):
            if _fold_str_const(node) is None:
                return
            for value in node.values:
                if isinstance(value, ast.Constant):
                    ids.add(id(value))
                elif (
                    isinstance(value, ast.FormattedValue)
                    and value.format_spec is None
                    and value.conversion in (-1, None)
                ):
                    _collect(value.value)

    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            _collect(node)
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
    except (SyntaxError, ValueError) as exc:
        # ast.parse() raises ValueError (not SyntaxError) for source containing NUL
        # bytes — still a parse failure, not a skip.
        return [], [f"{rel}: could not parse as Python ({exc}) — treated as a failure, not skipped"]

    violations: list[str] = []
    docstring_ids = _docstring_node_ids(tree)
    joined_str_child_ids = _joined_str_child_ids(tree)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_ecdsa_module(alias.name):
                    violations.append(
                        f"{rel}:{node.lineno}: direct ecdsa import — 'import {alias.name}'"
                    )
        elif isinstance(node, ast.ImportFrom):
            # node.level > 0 is a package-relative import ('from .ecdsa import ...' /
            # 'from ..ecdsa import ...') — that resolves within the current package,
            # never to the third-party 'ecdsa' distribution this check is scoped to.
            if node.level == 0 and node.module and _is_ecdsa_module(node.module):
                violations.append(
                    f"{rel}:{node.lineno}: direct ecdsa import — 'from {node.module} import ...'"
                )
            # Independent of which module it's from: `from jose.constants import ES256
            # as ALG` binds the local name to `ALG`, so the later ast.Name check (which
            # matches on the *local* identifier) would never see the literal 'ES256'
            # again — the import itself is the only place that name still appears.
            if node.level == 0:
                aliased = [a.name for a in node.names if a.name in _ES_ALGORITHMS]
                if aliased:
                    violations.append(
                        f"{rel}:{node.lineno}: ES256/384/512 usage (import) — {aliased!r}"
                    )
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstring_ids or id(node) in joined_str_child_ids:
                continue
            if node.value in _ES_ALGORITHMS:
                violations.append(f"{rel}:{node.lineno}: ES256/384/512 usage — {node.value!r}")
        elif isinstance(node, (ast.BinOp, ast.JoinedStr)):
            folded = _fold_str_const(node)
            if folded in _ES_ALGORITHMS:
                violations.append(
                    f"{rel}:{node.lineno}: ES256/384/512 usage (constant-folded) — {folded!r}"
                )
        elif isinstance(node, ast.Name) and node.id in _ES_ALGORITHMS:
            # Catches an algorithm selected via a bare identifier, e.g. a constant
            # imported as `from jose.constants import ES256` and then referenced
            # directly — a bare string literal check alone would miss this.
            violations.append(
                f"{rel}:{node.lineno}: ES256/384/512 usage (identifier) — {node.id!r}"
            )
        elif isinstance(node, ast.Attribute) and node.attr in _ES_ALGORITHMS:
            # Catches e.g. `jwt.encode(..., algorithm=Algorithms.ES256)` — an enum/
            # namespace attribute access that a string-literal-only check would miss.
            violations.append(
                f"{rel}:{node.lineno}: ES256/384/512 usage (attribute) — {node.attr!r}"
            )

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
