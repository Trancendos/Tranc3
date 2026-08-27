#!/usr/bin/env python3
"""Fail if a workflow's github/codeql-action/* steps disagree on their pin.

`github/codeql-action/init` writes a configuration file stamped with its own
release version, and `analyze` refuses to load a config written by a different
one:

    Loaded a configuration file for version '4.36.2',
    but running version '4.37.7'

So init, analyze and upload-sarif inside a single workflow must all resolve to
the same ref. Nothing in GitHub Actions enforces that, and dependency bots bump
action pins one `uses:` line at a time -- which is exactly how CodeQL went red
on main from 2026-08-22 to 2026-08-25.

A comment in codeql.yml used to carry this rule. A pin bump dropped the comment
while leaving the SHAs aligned by luck, which is the reason this file exists:
the invariant is checked rather than described.

Scope note: the constraint is per *workflow file*, not repo-wide. Two different
workflows may legitimately sit on different codeql-action releases, because each
runs its own init/analyze pair. Only disagreement within one file is a defect.

Exit 0 when consistent, 1 otherwise. No third-party dependencies.
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

WORKFLOW_DIR = Path(__file__).resolve().parent.parent / ".github" / "workflows"

# `uses: github/codeql-action/<sub-action>@<ref>` with an optional trailing
# `# comment`. Kept as a regex rather than a YAML parse on purpose: this must
# work on a file that does not parse cleanly, and `uses:` is unambiguous.
USES_RE = re.compile(
    r"^\s*(?:-\s*)?uses:\s*github/codeql-action/(?P<sub>[\w-]+)@(?P<ref>[^\s#]+)",
)


def collect(path: Path) -> dict[str, list[tuple[int, str]]]:
    """Map each distinct ref in `path` to the (line, sub-action) using it."""
    by_ref: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        m = USES_RE.match(line)
        if m:
            by_ref[m.group("ref")].append((lineno, m.group("sub")))
    return by_ref


def main() -> int:
    if not WORKFLOW_DIR.is_dir():
        print(f"No workflow directory at {WORKFLOW_DIR}", file=sys.stderr)
        return 1

    failures = 0
    checked = 0

    for path in sorted(WORKFLOW_DIR.glob("*.yml")) + sorted(WORKFLOW_DIR.glob("*.yaml")):
        by_ref = collect(path)
        if not by_ref:
            continue
        checked += 1
        if len(by_ref) == 1:
            continue

        failures += 1
        rel = path.relative_to(WORKFLOW_DIR.parent.parent)
        print(f"FAIL {rel}: github/codeql-action pins disagree", file=sys.stderr)
        for ref, uses in sorted(by_ref.items()):
            for lineno, sub in uses:
                print(f"    line {lineno}: {sub}@{ref}", file=sys.stderr)
        print(
            "    init stamps its config with its own version and analyze "
            "rejects a config from a different one -- align every "
            "github/codeql-action/* pin in this file to one ref.",
            file=sys.stderr,
        )

    if failures:
        print(
            f"\n{failures} workflow(s) with inconsistent codeql-action pins.",
            file=sys.stderr,
        )
        return 1

    print(f"OK: codeql-action pins consistent in {checked} workflow(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
