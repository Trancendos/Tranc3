#!/usr/bin/env python3
"""Fail when a workflow duplicated across GitHub Actions and Forgejo drifts apart.

Seven workflows exist under both `.github/workflows/` and `.forgejo/workflows/`.
`production-gate.yml` states the intended contract in its own header:

    keep it in sync with the Forgejo original -- they should differ only in
    this header, the runner, and the hardening added below

Nothing checked that. The contract was already broken when this script was
written: the Forgejo production gate was missing the `Dependency vulnerability
census` step entirely, so the two copies of the platform's merge gate enforced
materially different things. That did not bite, because Forgejo is dormant --
which is exactly the problem. The weaker gate is the one that takes over the
day The Workshop is stood back up, and nothing would have said so.

This is the same defect class the estate keeps producing: a control that is
written down, looks authoritative, and is never evaluated.

What this checks
----------------
Textual equality is the wrong bar -- the two platforms legitimately differ on
runner labels, secret-store naming, and runner identity. So the comparison runs
on a normalised *skeleton*: for each job, the ordered list of step names, the
action each step uses (without its version pin), and the step's shell body with
comments and blank lines stripped.

Differences that are legitimate are not silently tolerated: each one must be
listed in ACCEPTED_DIVERGENCES below with a written reason. An unexplained
difference fails. Adding a reason is a deliberate act that shows up in review,
which is the point -- the allowlist is the record of what the two platforms are
*meant* to disagree about.

Usage:
    python3 scripts/check_workflow_drift.py --check
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
GH_DIR = REPO / ".github" / "workflows"
FJ_DIR = REPO / ".forgejo" / "workflows"

# Each key is "<workflow>::<scope>". The value is why the two platforms are
# meant to differ there. A divergence without an entry here fails the check.
ACCEPTED_DIVERGENCES: dict[str, str] = {
    "ci.yml::jobs": (
        "Deliberately different decompositions, not drift. The GitHub copy "
        "splits into lint/test/topology because those are the PR status checks "
        "GitHub itself gates merges on. The Forgejo copy runs "
        "full-suite/smoke/worker-validation, a heavier sweep that only makes "
        "sense on a self-hosted runner with no per-minute cost. Forcing these "
        "into one shape would either slow every PR or thin the nightly sweep."
    ),
    "bot-health-watchdog.yml::watchdog::step-names": (
        "Cosmetic. The Forgejo step is named 'Notify The Citadel on degraded "
        "bot integration'; the GitHub one omits 'The Citadel'. Same command, "
        "same effect."
    ),
    "deploy-cloudflare.yml::preflight::Check Cloudflare credentials": (
        "The warning text names the secret store the reader must actually go "
        "and fix: 'GitHub repo secrets' on one side, 'org/repo secrets in The "
        "Workshop' on the other. Identical text would send half the readers to "
        "the wrong place."
    ),
    "deploy-fly.yml::deploy-backend::Check Fly credentials": (
        "Same reason as the Cloudflare credential check -- the message names "
        "the platform's own secret store."
    ),
    "deploy-fly.yml::deploy-backend::Validate required deploy secrets": (
        "Same reason -- remediation text names the platform's secret store."
    ),
    "deploy-fly.yml::deploy-bots::Notify The Citadel": (
        "The webhook payload's sender.login identifies which runner sent it "
        "('github-actions' vs 'forgejo-runner'). The Observatory uses that to "
        "attribute the deploy, so making them identical would lose information."
    ),
    "frontend-build.yml::deploy-pages::Check Cloudflare credentials": (
        "Same reason as deploy-cloudflare.yml -- platform-specific secret store."
    ),
    "frontend-build.yml::deploy-pages::Deploy to Cloudflare Pages": (
        'The Forgejo copy guards the write with `if [ -n "$GITHUB_STEP_SUMMARY" ]` '
        "because act-runner does not always set that variable, where GitHub "
        "Actions always does. The guard is correct on both, but only load-"
        "bearing on Forgejo."
    ),
}


def normalise_run(body: str | None) -> tuple[str, ...]:
    """A shell body reduced for comparison.

    Blank lines and **whole-line** comments are dropped, and runs of whitespace
    are collapsed, so that reflowing or re-wording a standalone comment is not
    reported as drift -- comment text differing between the two copies is
    normal, since each explains its own platform.

    A trailing inline comment is deliberately NOT stripped, and is compared as
    part of the command. That is a real limitation: two copies whose only
    difference is `cmd # a` versus `cmd # b` will be reported. It is the safer
    limitation to have, because stripping inline comments correctly needs to
    know when `#` is quoted, and in these workflows it usually is. Measured
    across both trees at the time of writing: of 671 effective shell lines,
    7 contain a `#` beyond the first character, and 6 of those 7 have it
    inside a quote --

        elif [ "${#val}" -lt "$min" ]; then       # parameter expansion
        echo "## Frontend deployed to Cloudflare Pages"   # markdown heading

    Splitting on the first `#` would truncate those to `elif [ "${` and
    `echo "`, so two genuinely different bodies would compare equal. A false
    negative in a drift gate is worse than a false positive: the false positive
    is visible and gets an ACCEPTED_DIVERGENCES entry with a reason, whereas a
    false negative silently reports parity that is not there.

    If an inline comment ever does differ legitimately, record it in
    ACCEPTED_DIVERGENCES rather than making this function shell-aware.
    """
    out = []
    for line in (body or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        out.append(re.sub(r"\s+", " ", stripped))
    return tuple(out)


def skeleton(doc: dict) -> dict[str, list[tuple]]:
    """Job id -> ordered steps as (name, action-without-version, run body)."""
    jobs = {}
    for job_id, job in (doc.get("jobs") or {}).items():
        steps = []
        for step in job.get("steps") or []:
            uses = step.get("uses")
            if uses:
                # Compare the action, not the pin. Version drift between the two
                # copies is real but belongs to the action-version audit, which
                # already owns it; duplicating that here would report it twice.
                uses = uses.split("@")[0]
            steps.append((step.get("name"), uses, normalise_run(step.get("run"))))
        jobs[job_id] = steps
    return jobs


def compare(name: str) -> list[str]:
    """Return unexplained differences between the two copies of `name`."""
    gh = skeleton(yaml.safe_load((GH_DIR / name).read_text()))
    fj = skeleton(yaml.safe_load((FJ_DIR / name).read_text()))
    findings: list[str] = []

    if set(gh) != set(fj):
        key = f"{name}::jobs"
        if key not in ACCEPTED_DIVERGENCES:
            findings.append(
                f"{name}: job sets differ -- "
                f"GitHub-only {sorted(set(gh) - set(fj))}, "
                f"Forgejo-only {sorted(set(fj) - set(gh))}"
            )
        # Job sets differ, so per-step comparison of the shared jobs would be
        # comparing workflows that were never meant to line up. Stop here.
        return findings

    for job_id in sorted(gh):
        gh_steps, fj_steps = gh[job_id], fj[job_id]
        gh_names = [s[0] for s in gh_steps]
        fj_names = [s[0] for s in fj_steps]

        if gh_names != fj_names:
            if f"{name}::{job_id}::step-names" in ACCEPTED_DIVERGENCES:
                continue
            missing = [n for n in gh_names if n not in fj_names and n]
            extra = [n for n in fj_names if n not in gh_names and n]
            detail = f"{name} [{job_id}]: step sequences differ."
            if missing:
                detail += f" Present on GitHub, absent on Forgejo: {missing}."
            if extra:
                detail += f" Present on Forgejo, absent on GitHub: {extra}."
            findings.append(detail)
            continue

        # strict=True is safe and load-bearing: the step-name lists were proven
        # equal just above, so unequal lengths here would mean the skeleton
        # builder had a bug, and silently truncating would hide it.
        for gh_step, fj_step in zip(gh_steps, fj_steps, strict=True):
            label = gh_step[0] or "(unnamed step)"
            key = f"{name}::{job_id}::{label}"
            if gh_step[1] != fj_step[1]:
                findings.append(
                    f"{name} [{job_id}] {label!r}: different action -- "
                    f"GitHub uses {gh_step[1]}, Forgejo uses {fj_step[1]}"
                )
            if gh_step[2] != fj_step[2] and key not in ACCEPTED_DIVERGENCES:
                findings.append(
                    f"{name} [{job_id}] {label!r}: shell body differs "
                    f"({len(gh_step[2])} vs {len(fj_step[2])} effective lines)"
                )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 when an unexplained divergence is found",
    )
    args = parser.parse_args()

    shared = sorted({p.name for p in GH_DIR.glob("*.yml")} & {p.name for p in FJ_DIR.glob("*.yml")})
    if not shared:
        print("No workflow is duplicated across the two platforms; nothing to check.")
        return 0

    findings: list[str] = []
    for name in shared:
        findings.extend(compare(name))

    print(f"Workflows duplicated across GitHub Actions and Forgejo: {len(shared)}")
    for name in shared:
        print(f"  - {name}")
    print(f"Accepted, documented divergences: {len(ACCEPTED_DIVERGENCES)}")

    if not findings:
        print("\nNo unexplained divergence.")
        return 0

    print(f"\n{len(findings)} unexplained divergence(s):\n")
    for f in findings:
        print(f"  {f}")
    print(
        "\nEither bring the two copies back into line, or add the divergence to "
        "ACCEPTED_DIVERGENCES in this script with a written reason. Silence is "
        "not an option here on purpose: an unrecorded difference between two "
        "copies of a gate is how one of them ends up enforcing less than the "
        "other without anyone noticing."
    )
    return 1 if args.check else 0


if __name__ == "__main__":
    sys.exit(main())
