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

Derived rather than listed, so adding a submodule does not quietly widen every
count in the estate.

WHY IT IS DERIVED FROM GITLINKS AND NOT FROM `.gitmodules`

The first version of this read `path =` lines out of `.gitmodules`, and that
made the boundary assertable by anyone who can edit a tracked text file.
`.gitmodules` is repository content; a gitlink is repository structure. An
entry reading `path = src` would have excluded all of `src/` from the inert
ratchet, the bandit ceiling and the SEC-006/020/021 manifest scans at once.

Nothing else would have noticed. `scripts/validate_submodule_pins.py` iterates
the GITLINKS from `git ls-tree` and only asked whether each one has a URL, so a
`.gitmodules` entry with no gitlink behind it was never examined — the extra
key sat in its `urls` map unread. Verified by reading its `main()`, not
assumed. Raised by cubic on #1403 and it is right.

Both halves are closed. That script now REFUSES a declaration with no gitlink,
so the evasion fails the "Validate submodule pins are reachable" check as well
as being distrusted here; one place reports the shape, another rejects it.

So the boundary now comes from `git ls-files --stage` mode `160000`: a path is
a different repository because git records it as one, not because a file says
so. `.gitmodules` is kept only to CORROBORATE — `undeclared_gitlinks()` and
`declared_non_gitlinks()` report the two ways the pair can disagree, and the
second is the evasion shape above.

When git cannot be consulted at all (no git, or a subject tree that is not a
repository — which is every test fixture) this returns NOTHING, so every file
is scanned. That is the safe direction: a boundary that cannot be established
must not become an exclusion. IMMUNE-SYSTEM.md's rule for sensors, pointed at
a sensor's own scope.
"""

from __future__ import annotations

import re
import shutil
import subprocess  # nosec B404 - absolute argv[0], no shell; see _gitlinks
from pathlib import Path

_PATH_LINE = re.compile(r"^\s*path\s*=\s*(.+?)\s*$", re.MULTILINE)

# `<mode> <object> <stage>\t<path>`; 160000 is the gitlink mode.
_STAGE_LINE = re.compile(r"^160000 [0-9a-f]{40} [0-3]\t(?P<path>.+)$")


def _gitlinks(root: Path) -> frozenset[str]:
    """Paths git records as gitlinks (mode 160000) in `root`'s index.

    Fixed argv and no shell, so nothing here is interpolated from repository
    content. A non-repository, a missing git, or any failure reads as "no
    gitlinks" — see this module's docstring for why that is the safe answer
    rather than a silent exclusion.
    """
    # Resolved to an absolute path rather than relying on PATH lookup, which is
    # what bandit's B607 is about and is worth fixing rather than suppressing:
    # a missing git is answered here, without spawning anything, by the same
    # "no gitlinks" that every other failure gives.
    git = shutil.which("git")
    if git is None:
        return frozenset()
    try:
        proc = subprocess.run(  # nosec B603 - absolute argv[0] from shutil.which, shell=False, fixed arguments
            [git, "-C", str(root), "ls-files", "--stage"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return frozenset()
    if proc.returncode != 0:
        return frozenset()
    found = set()
    for line in proc.stdout.splitlines():
        match = _STAGE_LINE.match(line)
        if match:
            found.add(match.group("path").strip().strip("/"))
    return frozenset(found)


def declared_paths(root: Path) -> frozenset[str]:
    """Paths `.gitmodules` DECLARES as submodules. Not a boundary by itself.

    Kept separate from `submodule_paths` deliberately: this is content a change
    can assert, and the whole point of the split is that an assertion is not a
    boundary.
    """
    try:
        text = (root / ".gitmodules").read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return frozenset()
    return frozenset(
        match.group(1).strip().strip("/") for match in _PATH_LINE.finditer(text) if match.group(1)
    )


def submodule_paths(root: Path) -> frozenset[str]:
    """Repository-relative paths of every submodule, POSIX-style.

    A path is here because git records a gitlink at it. An entry in
    `.gitmodules` alone never gets a path excluded, and an exclusion is never
    invented when git cannot be asked.
    """
    return _gitlinks(root)


def declared_non_gitlinks(root: Path) -> frozenset[str]:
    """Declared in `.gitmodules` with no gitlink behind it.

    This is the shape that would have evaded every tree-walking control, so it
    is reported rather than merely not-trusted. Empty when git cannot be
    consulted, because then there is no gitlink set to compare against and
    "every declaration is unbacked" would be a false alarm, not a finding.
    """
    links = _gitlinks(root)
    if not links:
        return frozenset()
    return declared_paths(root) - links


def undeclared_gitlinks(root: Path) -> frozenset[str]:
    """A gitlink with no `.gitmodules` entry.

    The benign-looking half of the same disagreement, and the one
    `validate_submodule_pins.py` already fails on ("no url in .gitmodules for
    this gitlink"). Reported here so both directions are visible from one
    place.
    """
    return _gitlinks(root) - declared_paths(root)


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
