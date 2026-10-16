"""Where this repository ends and another one begins.

WHY THIS EXISTS

Every counting control in this estate walks the working tree, and the working
tree is not the same shape everywhere. `ci.yml`'s Pytest job checks out with
`submodules: recursive`; most other jobs and every local worktree do not. So a
checker that counts Python files, suppressions or bandit findings across the
tree measures CranBania and Magna Carta in one place and not the other, and a
"ceiling" recorded in the smaller tree fails in the larger one for a reason
that has nothing to do with the code anyone wrote.

Measured: this is what failed `Pytest` on #1403 while the identical commit's
other jobs passed and `main` was green. `workers/cranbania` sits under
`workers`, which `[tool.bandit] targets` names, so with submodules present
bandit scanned a second repository's code into this one's ratchet.

The deeper point is not the checkout flag. A submodule is a DIFFERENT
REPOSITORY with its own governance, its own reviewers and its own ceilings.
Counting its suppressions here would hold Tranc3 to a number only CranBania
can move, and the first person to meet that is someone whose own diff is
clean. Jurisdiction, in the sense `docs/governance/CONTAINER-JURISDICTION.md`
uses it.

Derived from `.gitmodules` rather than listed, so adding a submodule does not
quietly widen every count in the estate.
"""

from __future__ import annotations

import re
from pathlib import Path

_PATH_LINE = re.compile(r"^\s*path\s*=\s*(.+?)\s*$", re.MULTILINE)


def submodule_paths(root: Path) -> frozenset[str]:
    """Repository-relative paths of every submodule, POSIX-style.

    Empty when there is no `.gitmodules` or it cannot be read — which is the
    right answer for a tree that has none, and harmless for one whose file is
    unreadable, since the alternative would be to invent exclusions.
    """
    try:
        text = (root / ".gitmodules").read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return frozenset()
    return frozenset(
        match.group(1).strip().strip("/") for match in _PATH_LINE.finditer(text) if match.group(1)
    )


def inside_submodule(relative: Path | str, submodules: frozenset[str]) -> bool:
    """Is this repository-relative path inside one of `submodules`?

    Compared segment-wise rather than by string prefix: `workers/cranbania`
    must not match a sibling directory named `workers/cranbania-notes`.
    """
    parts = Path(relative).as_posix().split("/")
    for submodule in submodules:
        expected = submodule.split("/")
        if parts[: len(expected)] == expected:
            return True
    return False
