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

import functools
import re
import shutil
import subprocess  # nosec B404 - absolute argv[0], no shell; see _gitlinks
from pathlib import Path

# `<mode> <object> <stage>\t<path>` from `ls-files --stage -z`: NUL-separated,
# so there is no trailing newline and no C-quoting to undo, and matched with
# `fullmatch` -- see `_gitlinks`.
_STAGE_RECORD = re.compile(r"160000 [0-9a-f]{40} [0-3]\t(?P<path>.+)", re.DOTALL)


def _git(root: Path, *args: str) -> str | None:
    """Run one git command in `root`, or None if it cannot be run.

    argv[0] comes from `shutil.which` rather than a PATH lookup (bandit B607,
    worth fixing rather than suppressing), the argument list is fixed, and
    `shell=False`. A missing git, a non-repository, a timeout or a non-zero
    exit all read as None, which every caller turns into "no boundary" rather
    than into an exclusion.
    """
    git = shutil.which("git")
    if git is None:
        return None
    try:
        proc = subprocess.run(  # nosec B603 - absolute argv[0] from which, shell=False, fixed args
            [git, "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout if proc.returncode == 0 else None


@functools.lru_cache(maxsize=None)
def _gitlinks_for(resolved: str) -> frozenset[str]:
    """`_gitlinks` keyed by resolved path, so git is asked once per root.

    MEASURED, because the first version asked per call and that is not a
    detail: `check_sec_021()` alone calls `_in_submodule` 1,771 times on this
    tree, each spawning `git ls-files` at ~4ms, and SEC-006 and SEC-020 walk
    the tree too -- roughly twenty seconds of subprocesses added to the
    production gate by a function that returns the same two paths every time.
    Reading `.gitmodules` from disk per call was merely wasteful; spawning a
    process per call is a latency regression. Raised by cubic on #1403.

    The cache lasts for the process, which is the right lifetime for a checker
    run -- the tree does not grow a submodule mid-run. A long-lived process
    that adds one would see the old answer, so `reset_boundary_cache()` exists
    for that and for tests that need it; nothing in this estate's checkers
    does, because each is a short-lived command.
    """
    out = _git(Path(resolved), "ls-files", "--stage", "-z")
    if out is None:
        return frozenset()
    found = set()
    for record in out.split("\0"):
        # `fullmatch`, not `match`: an anchored pattern used with `match`
        # accepts a trailing newline its own character class forbids, which is
        # what scripts/check_anchored_validators.py exists to catch -- and it
        # caught this, in CI, on the commit that introduced it.
        matched = _STAGE_RECORD.fullmatch(record)
        if matched:
            found.add(matched.group("path").strip("/"))
    return frozenset(found)


def _gitlinks(root: Path) -> frozenset[str]:
    """Paths git records as gitlinks (mode 160000) in `root`'s index."""
    return _gitlinks_for(str(Path(root).resolve()))


@functools.lru_cache(maxsize=None)
def _declared_for(resolved: str) -> frozenset[str]:
    """`declared_paths` keyed by resolved path. Cached for the same reason as
    `_gitlinks_for`: it also spawns git, and the mismatch reporters call both."""
    root = Path(resolved)
    if not (root / ".gitmodules").is_file():
        return frozenset()
    out = _git(root, "config", "--file", ".gitmodules", "--list", "-z")
    if out is None:
        return frozenset()
    found = set()
    for record in out.split("\0"):
        if not record:
            continue
        # `git config -z` emits `key\nvalue` per record, so a value holding a
        # newline cannot be split into two records.
        key, _, value = record.partition("\n")
        if key.lower().endswith(".path") and value.strip():
            found.add(value.strip().strip("/"))
    return frozenset(found)


def reset_boundary_cache() -> None:
    """Forget the per-root answers. For a process that outlives a tree change."""
    _gitlinks_for.cache_clear()
    _declared_for.cache_clear()


def declared_paths(root: Path) -> frozenset[str]:
    """Paths `.gitmodules` DECLARES as submodules. Not a boundary by itself.

    Kept separate from `submodule_paths` deliberately: this is content a change
    can assert, and the whole point of the split is that an assertion is not a
    boundary.

    Parsed by `git config`, not by a regex over the text. `.gitmodules` holds
    git-config keys, so `PATH =` is as valid as `path =`, values may be quoted,
    and a path may contain a space or a tab. A line scan keeps the surrounding
    quotes and mis-reads all three -- raised by cubic on #1403, and measured:
    `git ls-files` C-quotes a tab-containing path to `"vendor/tab\\todd"`, which
    no relative path ever equals. It is also the parser
    `scripts/validate_submodule_pins.py` already uses on this same file, so the
    two can no longer disagree about what it says.
    """
    return _declared_for(str(Path(root).resolve()))


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
