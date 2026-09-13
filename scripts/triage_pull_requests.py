#!/usr/bin/env python3
"""Triage open pull requests against main, locally, before anyone merges one.

Why this exists
---------------
A sweep of the 100 open pull requests on 2026-09-12 found that 72 of them
conflicted with main, and that the conflict was the *least* interesting thing
about them. Three classes were only visible by reading the branches:

1.  **Branches that delete files still live on main.** PR #994, titled
    "Vector similarity calculation optimization", deleted 24 files that exist
    on main -- the whole of ``src/exchange/``, both CMDB modules,
    ``scripts/check_workflow_drift.py`` (the guard holding the two copies of
    the production gate in lockstep) and 8 test suites. Merging it would have
    removed them. Nothing in the title, the diffstat as GitHub renders it, or
    the conflict list says so.

2.  **Dependency bumps main has already passed.** Renovate had not rebased in
    weeks, so #1090 proposed ``lucide-react ^0.577.0`` against a main already
    on ``^1.0.0``, and #1073 proposed a ``@cloudflare/workers-types`` pin 13
    days older than the one in the tree. Both read as "update" and are
    downgrades.

3.  **Duplicate clusters.** Thirteen open PRs optimised the same pure-Python
    vector maths; two implemented the same delete-confirmation dialog.

The first class is the one that needs a machine. A human reading a PR list
sees titles; only a walk of the refs sees that a performance branch drops the
performance test. So this script answers, for every open PR, the question the
merge button does not: *what does main lose if this lands?*

It is deliberately offline. It reads ``refs/remotes/pr/*`` and ``origin/main``
from the local clone, so it costs no API calls and can run in CI, in a hook,
or on a laptop. Fetch the refs first::

    git fetch origin '+refs/pull/*/head:refs/remotes/pr/*'

Exit status is the point: non-zero when any surveyed PR would delete a file
that is live on main, so this can gate a queue rather than merely describe it.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class GitUnavailable(RuntimeError):
    """Raised when the repository cannot be interrogated at all.

    Distinct from "the pull requests are all fine", and that distinction is the
    whole point. A triage tool that returns "0 dangerous PRs" because it could
    not find a single ref reports exactly what a healthy queue reports. See
    docs/governance/IMMUNE-SYSTEM.md.
    """


@dataclass
class Verdict:
    """What one pull request would do to main if it were merged now."""

    number: int
    merges_cleanly: bool
    commits_behind: int
    changed_files: int
    deletes_live: list[str] = field(default_factory=list)
    relocated: list[str] = field(default_factory=list)

    @property
    def deletes_live_tests(self) -> list[str]:
        return [p for p in self.deletes_live if "test" in Path(p).name.lower()]

    @property
    def destructive(self) -> bool:
        """True when merging removes content main has and the head does not.

        `relocated` paths are excluded on purpose: a file whose basename
        reappears elsewhere in the same head has moved, and a mover is not a
        deleter. Keeping the two tiers apart is what stops the sweeper crying
        wolf on a rename -- and a sweeper that flags every large refactor gets
        switched off, which is the failure mode that matters.
        """
        return bool(self.deletes_live)

    def as_dict(self) -> dict:
        return {
            "number": self.number,
            "merges_cleanly": self.merges_cleanly,
            "commits_behind": self.commits_behind,
            "changed_files": self.changed_files,
            "deletes_live": self.deletes_live,
            "relocated": self.relocated,
            "deletes_live_tests": self.deletes_live_tests,
            "destructive": self.destructive,
        }


def _git(*args: str, root: Path = REPO_ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)


def _exists(rev: str, root: Path = REPO_ROOT) -> bool:
    return _git("rev-parse", "--verify", "-q", f"{rev}^{{commit}}", root=root).returncode == 0


def survey(numbers: list[int], base: str = "origin/main", root: Path = REPO_ROOT) -> list[Verdict]:
    """Return a Verdict for every pull request number that has a local ref.

    Raises GitUnavailable when the base ref is missing or no PR ref resolves --
    either means the clone was never fetched, and a silent empty result would be
    indistinguishable from a clean queue.
    """
    if not _exists(base, root):
        raise GitUnavailable(
            f"{base} does not resolve, so no pull request can be compared against it. "
            "Run: git fetch origin main"
        )
    if not numbers:
        raise GitUnavailable("no pull request numbers were supplied, so nothing was surveyed.")

    verdicts: list[Verdict] = []
    found = 0
    for n in numbers:
        ref = f"refs/remotes/pr/{n}"
        if not _exists(ref, root):
            continue
        found += 1
        merge_base = _git("merge-base", base, ref, root=root).stdout.strip()
        behind = _git("rev-list", "--count", f"{merge_base}..{base}", root=root).stdout.strip()
        changed = _git("diff", "--name-only", merge_base, ref, root=root).stdout.split()
        # "-M -l0" is the whole subtlety here. Rename detection is capped by
        # diff.renameLimit, and above the cap git silently stops pairing and
        # reports every move as a plain delete. That cap is why the
        # Dimensional/ -> Dimensionals/ rename in #1207 -- 95 files, renamed
        # AND edited in the same commit, since the rename rewrote the token
        # inside each file -- reads as 95 deletions, while a two-file rename
        # reads correctly. Same operation, opposite verdicts, decided by size.
        # "-l0" removes the cap so similarity is always computed, and content
        # that moved is paired instead of mourned.
        #
        # Blob identity alone is not enough: it catches a pure move, but a
        # rename that also edits the file produces a different blob. Similarity
        # detection is what covers that case, which is the common one.
        deleted = [
            line.split("\t", 1)[1]
            for line in _git(
                "diff",
                "-M",
                "-l0",
                "--diff-filter=D",
                "--name-status",
                merge_base,
                ref,
                root=root,
            ).stdout.splitlines()
            if "\t" in line
        ]
        live = [
            path
            for path in deleted
            if _git("cat-file", "-e", f"{base}:{path}", root=root).returncode == 0
        ]
        # Similarity detection still misses two shapes: a file too small to
        # score above the 50% floor (an empty __init__.py never matches
        # anything) and a move whose content was rewritten wholesale. Both
        # happened in #1207. Fall back to the weaker but sufficient signal --
        # does a file of this name exist anywhere in the head? -- and report
        # those separately rather than counting them as losses.
        head_names = {
            Path(line.split("\t", 1)[-1]).name
            for line in _git("ls-tree", "-r", "--name-only", ref, root=root).stdout.splitlines()
            if line
        }
        relocated = [path for path in live if Path(path).name in head_names]
        live = [path for path in live if Path(path).name not in head_names]
        verdicts.append(
            Verdict(
                number=n,
                merges_cleanly=_git("merge-tree", "--write-tree", base, ref, root=root).returncode
                == 0,
                commits_behind=int(behind or 0),
                changed_files=len(changed),
                deletes_live=sorted(live),
                relocated=sorted(relocated),
            )
        )

    if found == 0:
        raise GitUnavailable(
            f"none of the {len(numbers)} pull request numbers had a local ref. "
            "Run: git fetch origin '+refs/pull/*/head:refs/remotes/pr/*'"
        )
    return verdicts


def render(verdicts: list[Verdict]) -> str:
    lines: list[str] = []
    destructive = [v for v in verdicts if v.destructive]
    if destructive:
        lines.append("Pull requests that would DELETE files live on main:")
        lines.append("")
        for v in sorted(destructive, key=lambda v: -len(v.deletes_live)):
            tests = v.deletes_live_tests
            note = f", {len(tests)} of them test suites" if tests else ""
            lines.append(f"  PR {v.number}: {len(v.deletes_live)} file(s){note}")
            for p in v.deletes_live[:10]:
                lines.append(f"      - {p}")
            if len(v.deletes_live) > 10:
                lines.append(f"      ... and {len(v.deletes_live) - 10} more")
            lines.append("")
    moved = [v for v in verdicts if v.relocated and not v.destructive]
    for v in sorted(moved, key=lambda v: -len(v.relocated)):
        lines.append(
            f"  PR {v.number}: {len(v.relocated)} path(s) removed but reappearing "
            "under the same name elsewhere in the branch -- a move, not a loss."
        )
    if moved:
        lines.append("")
    stale = [v for v in verdicts if not v.merges_cleanly]
    lines.append(
        f"Surveyed {len(verdicts)} pull request(s): "
        f"{len(verdicts) - len(stale)} merge cleanly, {len(stale)} conflict, "
        f"{len(destructive)} would delete live files."
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("numbers", nargs="*", type=int, help="pull request numbers to survey")
    parser.add_argument(
        "--from-json",
        type=Path,
        help="file holding a JSON list of PR numbers, or of objects with a 'number' key",
    )
    parser.add_argument("--base", default="origin/main")
    parser.add_argument(
        "--repo",
        type=Path,
        default=REPO_ROOT,
        help=(
            "repository to triage (default: this one). The estate has four -- "
            "Tranc3, CranBania, Magna-Carta, InfinityStyles -- and the questions "
            "this tool asks are the same in all of them."
        ),
    )
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a report")
    args = parser.parse_args(argv)

    numbers = list(args.numbers)
    if args.from_json:
        payload = json.loads(args.from_json.read_text())
        numbers += [p["number"] if isinstance(p, dict) else int(p) for p in payload]

    try:
        verdicts = survey(sorted(set(numbers)), base=args.base, root=args.repo)
    except GitUnavailable as exc:
        print(f"cannot triage pull requests: {exc}", file=sys.stderr)
        return 1

    print(json.dumps([v.as_dict() for v in verdicts], indent=2) if args.json else render(verdicts))
    return 1 if any(v.destructive for v in verdicts) else 0


if __name__ == "__main__":
    raise SystemExit(main())
