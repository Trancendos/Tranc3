#!/usr/bin/env python3
"""Fail if any service starts using ecdsa directly.

The accepted-risk entry for CVE-2024-23342 (.trivyignore) is scoped to a specific
claim: ecdsa is only ever reached transitively via python-jose's native-python
backend, and every affected service's JWT usage is HS256/RS256-only, so the
vulnerable ECDSA sign/ECDH/keygen paths are never invoked. That claim was
verified once by hand; this script re-verifies it on every CI run so it can't
silently go stale as the codebase changes.

Scans for: direct `import ecdsa` / `from ecdsa import ...`, and ES256/ES384/ES512
JWT algorithm usage (the one thing that would actually exercise the vulnerable
code paths). Exits non-zero — failing the CI job — if either is found.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

_DIRECT_IMPORT = re.compile(r"^\s*(import\s+ecdsa\b|from\s+ecdsa\s+import\b)")
_ES_ALGORITHM = re.compile(r"\bES(256|384|512)\b")

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


def main() -> int:
    violations: list[str] = []
    for path in _iter_python_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = path.relative_to(REPO_ROOT)
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _DIRECT_IMPORT.search(line):
                violations.append(f"{rel}:{lineno}: direct ecdsa import — {line.strip()!r}")
            if _ES_ALGORITHM.search(line):
                violations.append(f"{rel}:{lineno}: ES256/384/512 usage — {line.strip()!r}")

    if violations:
        print(
            "ecdsa accepted-risk assumption violated — the .trivyignore entry for "
            "CVE-2024-23342 assumes no direct ecdsa usage and no ES256/384/512 JWT "
            "algorithms. Update SECURITY.md and .trivyignore's justification (or "
            "remove the ignore) before merging:",
            file=sys.stderr,
        )
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1

    print("OK: no direct ecdsa usage or ES256/384/512 JWT algorithms found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
