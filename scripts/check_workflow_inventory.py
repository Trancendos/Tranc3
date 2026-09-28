#!/usr/bin/env python3
"""CLAUDE.md's workflow counts must be measured, not remembered.

CLAUDE.md is the governing document for this repository, and it carried a
count of `.github/workflows/` that had been maintained by hand: it records
that the figure "said 12 until 2026-08-28 and 20 until 2026-09-03". That is a
register someone tended carefully and then stopped -- by 2026-09-28 it read
19 against 28 files on disk, and eleven workflows were named nowhere in it,
most of them vendor security scanners nobody had written down.

The same paragraph's Forgejo figure had drifted by one (32 against 33), while
its job counts were still right. A number that is right three times and wrong
twice is not a number a reader can use.

So the counts are derived here and compared with what the document claims.
A workflow added without a line in CLAUDE.md fails this check, which is the
point: `docs/governance/IMMUNE-SYSTEM.md` says to read it before adding any
scanner to this estate, and that instruction only binds if adding one is
visible.

Run with --list to print the inventory instead of checking it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
CLAUDE_MD = REPO / "CLAUDE.md"
GITHUB_DIR = REPO / ".github/workflows"
FORGEJO_DIR = REPO / ".forgejo/workflows"

#: The sentence in CLAUDE.md that states how many GitHub workflow files exist.
_GITHUB_COUNT = re.compile(r"`\.github/workflows/` has \*\*(\d+)\*\* files")

#: The sentence that states the Forgejo file, job and self-hosted-job counts.
_FORGEJO_COUNTS = re.compile(
    r"`\.forgejo/workflows/` holds (\d+) files and (\d+) of their (\d+) jobs"
)

#: Other documents state the Forgejo file count in their own words, and they
#: disagreed: CLAUDE.md said 32, SWOT-FORENSIC-ASSESSMENT said 32,
#: CODE-COMPLIANCE-MATRIX said 30, and there are 33. Four registers, three
#: numbers, one estate. Each live claim is matched by an exact pattern rather
#: than a general search, because several documents state *historical* counts
#: on purpose -- CI-ESTATE-CONSOLIDATION's "48 -> 27" is a record of what was
#: done, and a check that flagged it would be teaching people to ignore it.
_ALSO_CLAIM_FORGEJO_FILES = {
    "docs/governance/SWOT-FORENSIC-ASSESSMENT.md": re.compile(
        r"dormant\.\*\* (\d+) workflow files"
    ),
    "docs/governance/CODE-COMPLIANCE-MATRIX.md": re.compile(
        r"^(\d+) Forgejo workflow files", re.MULTILINE
    ),
}


def _workflow_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.iterdir() if p.suffix in {".yml", ".yaml"})


def _job_counts(directory: Path) -> tuple[int, int]:
    """(total jobs, jobs pinning a self-hosted runner)."""
    total = pinned = 0
    for path in _workflow_files(directory):
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        for job in (document.get("jobs") or {}).values():
            if not isinstance(job, dict):
                continue
            total += 1
            runs_on = job.get("runs-on")
            text = runs_on if isinstance(runs_on, str) else " ".join(runs_on or [])
            if "self-hosted" in str(text):
                pinned += 1
    return total, pinned


def _undocumented(prose: str) -> list[str]:
    """GitHub workflow files CLAUDE.md never names.

    Matched on the full filename rather than the stem: a bare-stem search
    reports `ci.yml`, `go.yml` and `test.yml` as documented from any prose
    containing those letters, and reports `label.yml` as documented because
    the file discusses `actions/labeler`. Both directions were wrong when
    this was first measured by hand.
    """
    return [p.name for p in _workflow_files(GITHUB_DIR) if p.name not in prose]


def main() -> int:
    prose = CLAUDE_MD.read_text(encoding="utf-8")

    github_files = _workflow_files(GITHUB_DIR)
    forgejo_files = _workflow_files(FORGEJO_DIR)
    forgejo_jobs, forgejo_pinned = _job_counts(FORGEJO_DIR)
    undocumented = _undocumented(prose)

    if "--list" in sys.argv:
        print(f".github/workflows/  : {len(github_files)} files")
        print(
            f".forgejo/workflows/ : {len(forgejo_files)} files, {forgejo_jobs} jobs, "
            f"{forgejo_pinned} pinning self-hosted"
        )
        print(f"not named in CLAUDE.md: {len(undocumented)}")
        for name in undocumented:
            print(f"  {name}")
        return 0

    problems: list[str] = []

    stated = _GITHUB_COUNT.search(prose)
    if not stated:
        problems.append(
            "CLAUDE.md no longer states a `.github/workflows/` file count in the "
            "form this check reads (```.github/workflows/` has **N** files```). "
            "Restore the sentence or update this script -- a count that cannot be "
            "found is the same as a count nobody checks."
        )
    elif int(stated.group(1)) != len(github_files):
        problems.append(
            f"CLAUDE.md says .github/workflows/ has {stated.group(1)} files; "
            f"there are {len(github_files)}."
        )

    forgejo = _FORGEJO_COUNTS.search(prose)
    if not forgejo:
        problems.append(
            "CLAUDE.md no longer states the `.forgejo/workflows/` counts in the "
            "form this check reads. Restore the sentence or update this script."
        )
    else:
        claimed_files, claimed_pinned, claimed_jobs = (int(g) for g in forgejo.groups())
        if claimed_files != len(forgejo_files):
            problems.append(
                f"CLAUDE.md says .forgejo/workflows/ holds {claimed_files} files; "
                f"there are {len(forgejo_files)}."
            )
        if claimed_jobs != forgejo_jobs:
            problems.append(
                f"CLAUDE.md says those workflows hold {claimed_jobs} jobs; "
                f"there are {forgejo_jobs}."
            )
        if claimed_pinned != forgejo_pinned:
            problems.append(
                f"CLAUDE.md says {claimed_pinned} Forgejo jobs pin self-hosted; "
                f"{forgejo_pinned} do."
            )

    for relative, pattern in sorted(_ALSO_CLAIM_FORGEJO_FILES.items()):
        path = REPO / relative
        if not path.is_file():
            problems.append(f"{relative} is gone; update this script's claim table.")
            continue
        found = pattern.search(path.read_text(encoding="utf-8"))
        if not found:
            problems.append(
                f"{relative} no longer states a Forgejo workflow file count where "
                "this check reads it. Restore the sentence or update the script."
            )
        elif int(found.group(1)) != len(forgejo_files):
            problems.append(
                f"{relative} says there are {found.group(1)} Forgejo workflow "
                f"files; there are {len(forgejo_files)}."
            )

    if undocumented:
        problems.append(
            "these GitHub workflows are named nowhere in CLAUDE.md, so the "
            "governing document does not describe what runs against this "
            f"repository: {undocumented}"
        )

    if problems:
        print("WORKFLOW INVENTORY DRIFT\n")
        for problem in problems:
            print(f"  - {problem}")
        print(
            "\nCLAUDE.md is what a contributor reads to learn what gates this "
            "repository. Add the workflow to it, with a line on what it does and "
            "whether it can fail, and correct the counts."
        )
        return 1

    print(
        f"Workflow inventory: {len(github_files)} GitHub, {len(forgejo_files)} Forgejo "
        f"({forgejo_jobs} jobs, {forgejo_pinned} self-hosted). "
        "Every GitHub workflow is named in CLAUDE.md and every count matches."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
