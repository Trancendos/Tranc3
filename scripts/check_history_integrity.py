#!/usr/bin/env python3
"""Pin `main`'s root commit, and refuse to pass on history it could not read.

WHY THIS EXISTS — AND THE MISTAKE THAT PRODUCED IT

A branch-salvage investigation on 2026-08-18 concluded that `main` had been
re-rooted, because in the analysis environment:

    git merge-base origin/main origin/<any-branch>   ->  exit 1, no output

for all 59 non-bot branches, `main` appeared to hold only 92 commits, and
`rev-list --max-parents=0 origin/main` reported 902a5a91 (2026-07-18) while the
branches reported 5addbf11 (2026-04-21). Two roots, no shared commit: an obvious
history rewrite.

None of it was true. **The clone was shallow.** 902a5a91 was the shallow graft
boundary, not a root, and `merge-base` failed because the shared history had
simply never been fetched. After `git fetch --unshallow`, `main` has 1,392
commits back to the same 5addbf11 the branches descend from, and all 60 branches
share a merge-base. No rewrite ever happened.

The lesson is the reason this script is worth keeping: on a shallow clone, git's
history commands answer confidently and wrongly. `rev-list --max-parents=0`
returns a graft boundary that looks exactly like a root, and `merge-base` reports
"unrelated" for branches that are perfectly related. Nothing errors; you just get
a false story with real-looking commit hashes attached.

WHAT IT CHECKS

  1. `main`'s root commit still matches EXPECTED_ROOT — 5addbf11, the real one.
     A genuine change means history really was rewritten (re-root, whole-graph
     squash, filter-branch, force push of an unrelated tree). Hard failure.
  2. How many branches have no merge-base with `main`, reported for triage.
     On a correctly-deepened clone this should be zero.

WHY IT FETCHES, AND WHY IT FAILS RATHER THAN SKIPS

`actions/checkout` clones shallow and single-branch, so `refs/remotes/origin/main`
does not exist and any root it could compute would be a graft boundary. The first
revision of this script treated that as "nothing to check" and exited 0 — a green
tick over an unread history, which is how the shallow-clone trap gets
institutionalised rather than caught. It now deepens `main` itself, and if it
still cannot read complete history it exits non-zero: an unverifiable guard must
not report success, the same fail-open shape this estate removed from its auth
gates.

Only `main` is deepened, not `fetch-depth: 0`, which would also pull every
branch's full history for no benefit here.

WHY NOT PIN A COMMIT COUNT OR A DATE

Both move legitimately on every merge. The root commit is the one identifier
stable for the life of a repository, changing *only* on a rewrite — exactly, and
only, the event worth alarming on. It is also the value a shallow clone gets
wrong, which is the second thing this catches.

UPDATING THE BASELINE

If a rewrite is ever deliberate, update EXPECTED_ROOT in the same commit that
performs it, so the new value is reviewed alongside the reason. Never update it
to make a red build go green — and before assuming a mismatch means a rewrite,
check `git rev-parse --is-shallow-repository` first. That is the mistake this
docstring exists to stop anyone repeating.

Exit 0 when the root is intact, 1 when it has changed or cannot be verified.
Orphan counts are reported but do not fail the build.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

# Root commit of `main` as of the 2026-07-18 re-root. See the module docstring
# before changing this value.
EXPECTED_ROOT = "5addbf114ddb837385d34dba786c9bb6317eab44"

DEFAULT_MAIN_REF = "origin/main"
DEFAULT_MAIN_BRANCH = "main"

# Matched as a path segment, not a substring: a human branch legitimately named
# `claude/fix-renovate-config` is not a bot branch, and `"renovate" in name`
# would silently drop it from the orphan report.
BOT_OWNERS = ("dependabot", "renovate")


def git(*args: str) -> tuple[int, str]:
    p = subprocess.run(["git", *args], capture_output=True, text=True)
    return p.returncode, p.stdout.strip()


def is_bot_branch(remote_ref: str) -> bool:
    """True for `origin/dependabot/...` and `origin/renovate/...`."""
    _, _, name = remote_ref.partition("/")
    return name.split("/", 1)[0] in BOT_OWNERS


def root_commits(ref: str) -> list[str]:
    code, out = git("rev-list", "--max-parents=0", ref)
    return out.split() if code == 0 and out else []


def branches(main_ref: str) -> list[str]:
    code, out = git("branch", "-r", "--format=%(refname:short)")
    if code != 0:
        return []
    return [
        b.strip()
        for b in out.splitlines()
        if b.strip() and "HEAD" not in b and b.strip() != main_ref and not is_bot_branch(b.strip())
    ]


def ensure_main_history(main_ref: str, main_branch: str) -> bool:
    """Make `main_ref` exist with complete history, deepening if necessary."""
    have_ref = git("rev-parse", "--verify", main_ref)[0] == 0
    shallow = git("rev-parse", "--is-shallow-repository")[1] == "true"
    if have_ref and not shallow:
        return True

    # --unshallow errors on a complete repository, so fall back to a plain fetch.
    if git("fetch", "--no-tags", "--unshallow", "origin", main_branch)[0] != 0:
        git("fetch", "--no-tags", "origin", main_branch)

    if git("rev-parse", "--verify", main_ref)[0] != 0:
        # A single-branch clone fetches into FETCH_HEAD without creating the
        # remote-tracking ref; point it there so the rest of the check works.
        code, sha = git("rev-parse", "--verify", "FETCH_HEAD")
        if code == 0 and sha:
            git("update-ref", f"refs/remotes/{main_ref}", sha)

    return git("rev-parse", "--verify", main_ref)[0] == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list-orphans",
        action="store_true",
        help="print every orphaned branch, not just the count",
    )
    parser.add_argument(
        "--main-ref",
        default=DEFAULT_MAIN_REF,
        help=f"remote-tracking ref for the trunk (default: {DEFAULT_MAIN_REF})",
    )
    parser.add_argument(
        "--main-branch",
        default=DEFAULT_MAIN_BRANCH,
        help=f"branch name to fetch when deepening (default: {DEFAULT_MAIN_BRANCH})",
    )
    args = parser.parse_args()

    if not ensure_main_history(args.main_ref, args.main_branch):
        print(
            f"[ERROR] cannot resolve {args.main_ref}, so the root commit cannot be verified.\n"
            f"        This check refuses to report success on history it could not read.\n"
            f"        In CI, ensure the runner can fetch `{args.main_branch}` from origin.",
            file=sys.stderr,
        )
        return 1

    roots = root_commits(args.main_ref)
    if not roots:
        print(
            f"[ERROR] no root commit reachable from {args.main_ref} — history is still "
            f"incomplete, so a rewrite could not be detected either way.",
            file=sys.stderr,
        )
        return 1

    all_branches = branches(args.main_ref)
    orphans, broken = [], []
    for b in all_branches:
        # git distinguishes these, and so must we: exit 1 means "no merge base",
        # a real answer; 128 means a bad object or unreadable ref, which is a
        # failure to look. Treating 128 as "orphan" is how a corrupt or
        # unfetched ref gets silently reported as a finding about history.
        code, _ = git("merge-base", args.main_ref, b)
        if code == 1:
            orphans.append(b)
        elif code != 0:
            broken.append(b)

    if broken:
        print(
            f"[ERROR] could not read history for {len(broken)} ref(s) — git failed rather than\n"
            f"        answering. These are unverified, not orphaned: "
            f"{', '.join(broken[:5])}{' …' if len(broken) > 5 else ''}",
            file=sys.stderr,
        )
        return 1

    if orphans:
        print(
            f"[INFO] {len(orphans)} of {len(all_branches)} non-bot branch(es) share no merge-base "
            f"with {args.main_ref}. A default `git merge` and any three-dot diff will refuse; "
            f"`git cherry-pick <commit>` still works (conflicts aside), and a deliberate merge "
            f"needs `--allow-unrelated-histories`."
        )
        if args.list_orphans:
            for b in orphans:
                print(f"        {b}")

    # Exact set, not membership: an unrelated-history merge grafts a second root
    # onto main while leaving EXPECTED_ROOT reachable, so `in` would pass over
    # precisely the event this is meant to catch.
    if set(roots) != {EXPECTED_ROOT}:
        print(
            f"\n[ERROR] {args.main_ref}'s history was rewritten.\n"
            f"        expected root : {EXPECTED_ROOT}\n"
            f"        actual root(s): {', '.join(roots)}\n\n"
            f"        Every branch based on the previous root is now orphaned: no merge-base, so\n"
            f"        no merge, rebase or cherry-pick will work against it. If this rewrite was\n"
            f"        deliberate, update EXPECTED_ROOT in this script in the same commit that\n"
            f"        performs it. If it was not, recover {args.main_ref} before further work\n"
            f"        lands on it.",
            file=sys.stderr,
        )
        return 1

    print(f"History integrity check: PASSED (root {EXPECTED_ROOT[:10]} intact)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
