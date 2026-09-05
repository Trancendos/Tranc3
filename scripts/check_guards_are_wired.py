#!/usr/bin/env python3
"""Fail when a guard script exists in the tree but no workflow ever runs it.

This is the estate's most persistent defect class, turned on the guards
themselves: a control that is written, reviewed, documented and merged, and
then never invoked. `scripts/check_lab_languages.py` shipped that way — its own
docstring and its commit message both said it ran in the Service Topology job,
and it did not. Nothing caught that, because the only thing that could have was
somebody re-reading the workflow file.

A guard nobody runs is worse than no guard. It reports PASSED whenever a human
runs it by hand, it appears in the documentation as coverage, and it holds the
place where a real check would otherwise be missed.

What this checks
----------------
Every guard in `scripts/` — a `check_*.py`, or a generator that accepts
`--check` so it can fail on drift — must be named in a `run:` line of at least
one workflow under `.github/workflows/` or `.forgejo/workflows/`.

Being named in the Forgejo tree alone counts: those workflows are dormant, not
deleted, and the drift checker already governs the seven duplicated files. What
this refuses is a guard named in neither.

A guard that genuinely should not run in CI is listed in UNWIRED_BY_DESIGN with
a written reason. The allowlist is checked in both directions: a listed guard
that has since been wired fails too, so the reason cannot outlive the fact it
describes.

Usage:
    python3 scripts/check_guards_are_wired.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
WORKFLOW_DIRS = (REPO / ".github" / "workflows", REPO / ".forgejo" / "workflows")

#: Guards that are deliberately not wired, and why. A reason has to say what
#: makes CI the wrong place to run it — "not needed" is not a reason, and the
#: length floor below is there to stop one being written.
UNWIRED_BY_DESIGN: dict[str, str] = {
    "check_deps.py": (
        "Imports torch, transformers and faiss to prove the optional ML stack is "
        "functional. CI installs none of them — the whole test suite runs in "
        "bootstrap mode without model weights — so in CI it would report the "
        "absence of packages CI is designed not to have. It is a local "
        "environment check for a machine that runs inference."
    ),
    "check_python314_readiness.py": (
        "Queries pypi.org for every pinned version of every worker to ask whether "
        "a 3.14-usable artifact exists. A gate whose verdict depends on a third "
        "party's uptime fails for reasons unrelated to the tree, and the 3.14 "
        "upgrade is a scheduled migration rather than a per-PR invariant. Run it "
        "when planning an upgrade batch, per "
        "docs/architecture/PYTHON-3.14-UPGRADE-ASSESSMENT.md."
    ),
}

#: Long enough that a reason has to be a sentence about this specific script.
_MIN_REASON = 80

_CHECK_FLAG = re.compile(r'["\']--check["\']')


def _accepts_check_flag(path: Path) -> bool:
    """True for a generator that can be asked to fail on drift instead of writing."""
    try:
        return bool(_CHECK_FLAG.search(path.read_text(encoding="utf-8")))
    except OSError:
        return False


def discover_guards() -> list[str]:
    """Every script whose job is to fail when the tree is wrong."""
    guards = set()
    for path in sorted(SCRIPTS.glob("*.py")):
        # This checker is NOT excluded. Excluding it was the first version,
        # and it meant the one guard that detects an unwired guard could not
        # detect its own — the failure mode it exists for, applied to itself.
        name = path.name
        if name.startswith("check_") or _accepts_check_flag(path):
            guards.add(name)
    return sorted(guards)


def _run_bodies(workflow: dict) -> list[str]:
    """Every `run:` shell body in a workflow, at any job."""
    bodies: list[str] = []
    for job in (workflow.get("jobs") or {}).values():
        if not isinstance(job, dict):
            continue
        for step in job.get("steps") or []:
            if isinstance(step, dict) and isinstance(step.get("run"), str):
                bodies.append(step["run"])
    return bodies


def wired_guards() -> set[str]:
    """Guard filenames a workflow step actually executes.

    Reads `run:` bodies, and within them the *invocation* shape
    (`python scripts/<guard>`) rather than the bare filename. Searching the
    whole file counted a guard as wired when a workflow merely named it in a
    comment; searching the body alone still counted an `echo` that mentioned
    it. Both are the defect this checker exists to catch, one level up: a
    mention that looks like a control and runs nothing. The steps in this
    estate carry long explanatory comments naming neighbouring guards, so
    neither case was theoretical.

    The honest limit: `echo "python scripts/x.py"` would still read as wired.
    That is a contrived line nobody writes, and chasing it would mean parsing
    shell rather than reading it.
    """
    guards = discover_guards()
    named: set[str] = set()
    for directory in WORKFLOW_DIRS:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.yml")) + sorted(directory.glob("*.yaml")):
            try:
                workflow = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError:
                continue
            if not isinstance(workflow, dict):
                continue
            for body in _run_bodies(workflow):
                for guard in guards:
                    if re.search(rf"python3?\s+(?:-\S+\s+)*scripts/{re.escape(guard)}\b", body):
                        named.add(guard)
    return named


def evaluate(guards: list[str], wired: set[str], exceptions: dict[str, str]) -> list[str]:
    """The whole decision, over plain data, so it can be tested without a repo."""
    failures: list[str] = []

    for guard in guards:
        if guard in wired:
            if guard in exceptions:
                failures.append(
                    f"{guard}: listed in UNWIRED_BY_DESIGN but a workflow runs it. "
                    f"Remove the entry — a written reason must not outlive the fact "
                    f"it describes."
                )
            continue
        reason = exceptions.get(guard)
        if reason is None:
            failures.append(
                f"{guard}: exists in scripts/ but no workflow runs it. Add a step "
                f"to a workflow, or list it in UNWIRED_BY_DESIGN with a written "
                f"reason. A guard nobody runs reports PASSED by hand and gates "
                f"nothing."
            )
        elif len(reason.strip()) < _MIN_REASON:
            failures.append(
                f"{guard}: UNWIRED_BY_DESIGN reason is {len(reason.strip())} "
                f"characters; at least {_MIN_REASON} are needed to say what makes "
                f"CI the wrong place to run it."
            )

    for listed in sorted(exceptions):
        if listed not in guards:
            failures.append(
                f"{listed}: listed in UNWIRED_BY_DESIGN but no such guard exists "
                f"in scripts/. Delete the entry."
            )

    return failures


def main() -> int:
    guards = discover_guards()
    wired = wired_guards()
    failures = evaluate(guards, wired, UNWIRED_BY_DESIGN)

    if failures:
        print("Guard wiring check: FAILED")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print(
        f"Guard wiring check: PASSED — {len(wired)} of {len(guards)} guard(s) run in "
        f"a workflow, {len(UNWIRED_BY_DESIGN)} unwired with a written reason"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
