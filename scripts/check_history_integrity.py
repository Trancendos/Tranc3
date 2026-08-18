#!/usr/bin/env python3
"""Detect a history rewrite of `main`, and report branches orphaned by one.

THE FAILURE THIS CATCHES

On 2026-07-18 this repository's `main` was re-rooted. Today `main` holds 92
commits, every one of them dated 2026-07-18 or later, under root commit
902a5a91. The 59 non-bot branches still carry 763+ commits under a *different*
root, 5addbf11, dated 2026-04-21. The two graphs share no commit at all, so:

    git merge-base origin/main origin/<any-branch>   ->  exit 1, no output

and every ancestry-based operation fails with it. You cannot merge, rebase,
cherry-pick or three-way diff a branch against a trunk it has no basis in. That
is why those branches sat unmergeable: not because the work was bad, but because
the ground they were standing on was removed.

The damage was quiet. Nothing failed at the moment of the rewrite — it only
showed up months later as "why does every branch look unmerged?", by which time
the cause was long out of sight. This check makes the same event loud and
immediate.

WHAT IT CHECKS

  1. `main`'s root commit still matches EXPECTED_ROOT. A change means history
     was rewritten (re-root, squash of the whole graph, filter-branch, a force
     push of an unrelated tree). This is the hard failure.
  2. How many branches have no merge-base with `main`. Orphans cannot be merged
     by any normal means, so they are reported for triage rather than left to be
     rediscovered one confusing branch at a time.

WHY NOT JUST PIN A COMMIT COUNT OR A DATE

Both move legitimately every time anyone merges. The root commit is the one
identifier that is stable for the life of a repository and changes *only* when
history is rewritten — which is exactly, and only, the event worth alarming on.

UPDATING THE BASELINE

If a rewrite is ever deliberate, update EXPECTED_ROOT in the same commit that
performs it, so the new value is reviewed alongside the reason. Never update it
to make a red build go green: a surprise here means the trunk moved under
everyone's feet, and the branches that were based on the old one are now
orphaned whether or not this check passes.

Exit 0 when the root is intact, 1 when it has changed. Orphan branches are
reported but do not fail the build -- they are a backlog, not a regression.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

# Root commit of `main` as of the 2026-07-18 re-root. See the module docstring
# before changing this value.
EXPECTED_ROOT = "902a5a910cf4c7f4348796ef331140ed1b170fb9"

MAIN = "origin/main"
BOT_PREFIXES = ("dependabot", "renovate")


def git(*args: str) -> tuple[int, str]:
    p = subprocess.run(["git", *args], capture_output=True, text=True)
    return p.returncode, p.stdout.strip()


def root_commits(ref: str) -> list[str]:
    code, out = git("rev-list", "--max-parents=0", ref)
    return out.split() if code == 0 and out else []


def branches() -> list[str]:
    code, out = git("branch", "-r", "--format=%(refname:short)")
    if code != 0:
        return []
    return [
        b.strip()
        for b in out.splitlines()
        if b.strip()
        and "HEAD" not in b
        and b.strip() != MAIN
        and not any(p in b for p in BOT_PREFIXES)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list-orphans",
        action="store_true",
        help="print every orphaned branch, not just the count",
    )
    args = parser.parse_args()

    if git("rev-parse", "--verify", MAIN)[0] != 0:
        print(f"[SKIP] {MAIN} not present — nothing to check (shallow or partial clone?)")
        return 0

    roots = root_commits(MAIN)
    if not roots:
        print(f"[SKIP] could not resolve a root commit for {MAIN}")
        return 0

    orphans = [b for b in branches() if git("merge-base", MAIN, b)[0] != 0]
    total = len(branches())

    if orphans:
        print(
            f"[INFO] {len(orphans)} of {total} non-bot branch(es) share no history with {MAIN}. "
            f"They cannot be merged, rebased or cherry-picked by ancestry — recovery has to go "
            f"through content, not commits."
        )
        if args.list_orphans:
            for b in orphans:
                print(f"        {b}")

    if EXPECTED_ROOT not in roots:
        print(
            f"\n[ERROR] {MAIN}'s history was rewritten.\n"
            f"        expected root : {EXPECTED_ROOT}\n"
            f"        actual root(s): {', '.join(roots)}\n\n"
            f"        Every branch based on the previous root is now orphaned: no merge-base, so\n"
            f"        no merge, rebase or cherry-pick will work against it. If this rewrite was\n"
            f"        deliberate, update EXPECTED_ROOT in this script in the same commit that\n"
            f"        performs it. If it was not, recover {MAIN} before any further work lands on it.",
            file=sys.stderr,
        )
        return 1

    print(f"History integrity check: PASSED (root {EXPECTED_ROOT[:10]} intact)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
