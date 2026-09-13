#!/usr/bin/env python3
"""Fail when a code-scanning category exists on main but can never exist on a PR.

Why this exists
---------------
GitHub generates one check per code-scanning tool on a pull request, and it
compares the categories the PR produced against the categories `refs/heads/main`
has. A category present on main and absent from the PR is reported as
`N configurations not found`, and the check concludes FAILURE.

`trivy.yml`'s `trivy-enforce` job carried `if: github.event_name == 'push' &&
github.ref == 'refs/heads/main'`, so its `trivy-fs-enforce` category existed only
on main. The consequence was not a one-off: the Trivy check concluded FAILURE on
**every pull request in this repository**, permanently, whatever the code did.

That is this estate's recurring defect wearing its plainest face. A control that
reports the same thing on a clean branch and a filthy one carries no
information; the only lesson available to a reader is to stop reading it. And
the second cost is larger than the noise -- the enforcing pass was running only
AFTER the merge it exists to gate.

What this checks, and what it does not
--------------------------------------
This is deliberately a textual rule, not an expression evaluator. It flags a
categorised `upload-sarif` step whose own `if`, or whose job's `if`, restricts
the run to pushes or to `refs/heads/main`. Those two forms are what produce the
defect; a general GitHub-expression evaluator would be a larger and less
trustworthy thing than the problem warrants, and this file says so rather than
implying coverage it does not have.

An intentional main-only category must be listed in ACCEPTED_MAIN_ONLY with a
written reason, so the decision is visible in a diff instead of implicit in a
skipped job.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO / ".github" / "workflows"

#: Conditions that make a step unreachable on a pull_request event.
MAIN_ONLY = (
    re.compile(r"github\.event_name\s*==\s*'push'"),
    re.compile(r"github\.ref\s*==\s*'refs/heads/main'"),
)

#: category -> written reason. Empty on purpose: every category this repository
#: uploads should be reachable on a PR, and an addition here is a decision
#: someone has to justify in review.
ACCEPTED_MAIN_ONLY: dict[str, str] = {}


class CannotReadWorkflows(RuntimeError):
    """Raised when the workflow directory cannot be enumerated.

    Without it every category looks reachable, so the guard would report a clean
    estate having examined nothing. See docs/governance/IMMUNE-SYSTEM.md.
    """


def _pull_request_triggered(text: str) -> bool:
    """True when the workflow runs on pull_request at all."""
    return re.search(r"^\s{0,4}pull_request:", text, re.MULTILINE) is not None


def _blocking_condition(text: str) -> str | None:
    for pattern in MAIN_ONLY:
        found = pattern.search(text)
        if found:
            return found.group(0)
    return None


def _label(path: Path, root: Path) -> str:
    """Repo-relative where that exists, root-relative otherwise (tests, forks)."""
    for base in (REPO, root):
        try:
            return path.relative_to(base).as_posix()
        except ValueError:
            continue
    return path.as_posix()


def findings(root: Path = WORKFLOWS) -> list[str]:
    """Categories uploaded by a PR-triggered workflow that a PR can never reach."""
    if not root.is_dir():
        raise CannotReadWorkflows(f"{root} is not a directory, so nothing was examined.")
    files = sorted(list(root.glob("*.yml")) + list(root.glob("*.yaml")))
    if not files:
        raise CannotReadWorkflows(f"{root} holds no workflow files, which cannot be right.")

    problems: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        if not _pull_request_triggered(text):
            continue
        # Split on job headers (two-space indent under `jobs:`) so a step can be
        # attributed to the job whose `if` governs it.
        jobs = re.split(r"\n(?=  [A-Za-z0-9_-]+:\n)", text)
        for job in jobs:
            job_head = job.split("steps:", 1)[0]
            job_guard = _blocking_condition(job_head)
            for step in re.split(r"\n(?=      - name:)", job):
                match = re.search(r'category:\s*["\']?([\w.-]+)', step)
                if not match or "upload-sarif" not in step:
                    continue
                category = match.group(1)
                guard = _blocking_condition(step) or job_guard
                if not guard:
                    continue
                if category in ACCEPTED_MAIN_ONLY:
                    continue
                problems.append(
                    f"{_label(path, root)}: category '{category}' is "
                    f"gated by `{guard}`, so it exists on main and never on a pull "
                    f"request.\n        GitHub then reports 'configuration not found' "
                    f"and fails the generated check on EVERY PR, whatever the code "
                    f"does.\n        Run the scan on pull requests too (blocking only "
                    f"on main), or list it in ACCEPTED_MAIN_ONLY with a reason."
                )
    return problems


def main(argv: list[str] | None = None) -> int:
    try:
        problems = findings()
    except CannotReadWorkflows as exc:
        print(f"cannot check SARIF category reachability: {exc}", file=sys.stderr)
        return 1
    if problems:
        print("SARIF category reachability: FAILED")
        for problem in problems:
            print(f"  [MAIN-ONLY] {problem}")
        return 1
    print("SARIF category reachability: PASSED — every uploaded category reaches a PR")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
