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
on a normalised *skeleton*: for each job, its `if`, `permissions` and effective
environment, and for each step in order, its name, the action it uses (without
the version pin), its shell body compared losslessly, and the `if`, `with`,
`env` and `continue-on-error` that decide whether and how it runs.

Comparing only names and bodies -- which is all this did until CodeRabbit's
review of #992 -- would report parity for a Forgejo copy of the dependency
census that kept its name and script and added `if: false`. Every one of those
fields can silently turn a check off while leaving it looking present, which is
the exact failure this script exists to detect.

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
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
GH_DIR = REPO / ".github" / "workflows"
FJ_DIR = REPO / ".forgejo" / "workflows"

# The workflows that must exist under BOTH .github/workflows/ and
# .forgejo/workflows/. Declared rather than discovered: see the comment in
# main() -- a set derived from the directory intersection cannot notice that
# one of the two copies has been deleted.
REQUIRED_DUPLICATED_WORKFLOWS: frozenset[str] = frozenset(
    {
        "bot-health-watchdog.yml",
        "ci.yml",
        "deploy-cloudflare.yml",
        "deploy-fly.yml",
        "frontend-build.yml",
        "perf-smoke.yml",
        "production-gate.yml",
    }
)

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
    "bot-health-watchdog.yml::watchdog::Run bot health watchdog": (
        "The same variable, from the only place each platform can get it. "
        "GitHub Actions injects `secrets.GITHUB_TOKEN` automatically for every "
        "run; Forgejo has no equivalent auto-provided token, so its copy reads "
        "the `GH_API_TOKEN` org secret described in CLAUDE.md alongside "
        "CF_API_TOKEN and FLY_API_TOKEN. Making the two identical is not "
        "possible in either direction -- GITHUB_TOKEN does not exist on "
        "Forgejo, and hardcoding a named secret on GitHub would replace a "
        "scoped, per-run token with a long-lived one."
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
    """A shell body reduced for comparison, losslessly.

    Only two things are removed, and neither can change what a command does:
    trailing whitespace on each line, and trailing blank lines at the end of
    the body. Everything else -- leading indentation, runs of internal
    whitespace, blank lines, comment lines -- is preserved and compared.

    An earlier version of this function collapsed internal whitespace and
    dropped blank and comment lines, on the reasoning that neither matters in
    shell. That reasoning does not survive contact with these workflows.
    `.forgejo/workflows/ci.yml` embeds Python through three heredocs, and
    inside those, leading indentation *is* syntax:

        for m in ok:
          print(f'  \u2713 {m}')

    Collapsing whitespace makes two structurally different Python programs
    compare equal, and stripping a line beginning with `#` removes a Python
    comment from the middle of a block. Both are false negatives, and a false
    negative in a drift gate is the failure this whole script exists to
    prevent: it reports parity that is not there.

    The cost is that a genuinely different comment between the two copies now
    shows up as drift. That is the right trade -- a false positive is visible,
    gets an ACCEPTED_DIVERGENCES entry with a written reason, and the reason
    is then reviewable. A false negative is silent.
    """
    lines = [line.rstrip() for line in (body or "").splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    return tuple(lines)


def canonical(value: object) -> object:
    """A hashable, order-insensitive form of a YAML fragment.

    Mapping key order carries no meaning in YAML, so `with: {a: 1, b: 2}` and
    `with: {b: 2, a: 1}` must compare equal. Sequences keep their order, which
    does matter.
    """
    if isinstance(value, dict):
        return tuple(sorted((str(k), canonical(v)) for k, v in value.items()))
    if isinstance(value, list):
        return tuple(canonical(v) for v in value)
    return value


def effective_env(*layers: object) -> object:
    """A step's environment after workflow, job and step blocks are merged.

    GitHub Actions and Forgejo both resolve `env` by layering
    workflow -> job -> step, with the innermost winning. Comparing the raw
    step block alone therefore reports drift where there is none: the GitHub
    production gate declares its five test variables once at workflow level,
    the Forgejo copy repeats them on three individual steps, and the
    environment each step actually runs with is identical.

    Merging first means a divergence reported here is one that changes what
    a step sees -- which is the only kind worth failing a build over -- while
    still catching a step that genuinely lacks a variable its counterpart has.
    """
    merged: dict[str, object] = {}
    for layer in layers:
        if isinstance(layer, dict):
            merged.update({str(k): v for k, v in layer.items()})
    return canonical(merged) if merged else None


def skeleton(doc: dict) -> dict[str, list[tuple]]:
    """Job id -> ordered steps, each reduced to what determines its behaviour.

    A step is more than its name and its script. `if: false` disables it,
    `continue-on-error: true` stops it failing the job, `with:` supplies the
    action's inputs, `env:` supplies its environment, and `permissions:`
    decides what the job's token can do. Comparing only name/action/run would
    report parity for a Forgejo copy of the `Dependency vulnerability census`
    that kept its name and body and added `if: false` -- which is precisely
    the class of silent weakening this script was written to catch.

    `runs-on` is deliberately excluded: the runner label is the one thing the
    two platforms are always meant to differ on.
    """
    jobs = {}
    workflow_env = doc.get("env")
    for job_id, job in (doc.get("jobs") or {}).items():
        job_env = job.get("env")
        steps = []
        for step in job.get("steps") or []:
            uses = step.get("uses")
            if uses:
                # Compare the action, not the pin. Version drift between the two
                # copies is real but belongs to the action-version audit, which
                # already owns it; duplicating that here would report it twice.
                uses = uses.split("@")[0]
            steps.append(
                (
                    step.get("name"),
                    uses,
                    normalise_run(step.get("run")),
                    canonical(step.get("if")),
                    canonical(step.get("with")),
                    effective_env(workflow_env, job_env, step.get("env")),
                    canonical(step.get("continue-on-error")),
                )
            )
        jobs[job_id] = [
            # Job-level controls ride in a synthetic leading entry so a job
            # whose steps are identical but whose `if:` or `permissions:`
            # differ is still reported.
            (
                "(job controls)",
                None,
                (),
                canonical(job.get("if")),
                canonical(job.get("permissions")),
                effective_env(workflow_env, job_env),
                canonical(job.get("continue-on-error")),
            ),
            *steps,
        ]
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

        names_accepted = f"{name}::{job_id}::step-names" in ACCEPTED_DIVERGENCES

        if gh_names != fj_names and not names_accepted:
            missing = [n for n in gh_names if n not in fj_names and n]
            extra = [n for n in fj_names if n not in gh_names and n]
            detail = f"{name} [{job_id}]: step sequences differ."
            if missing:
                detail += f" Present on GitHub, absent on Forgejo: {missing}."
            if extra:
                detail += f" Present on Forgejo, absent on GitHub: {extra}."
            findings.append(detail)
            continue

        if len(gh_steps) != len(fj_steps):
            # Different lengths means the steps do not pair up, so comparing
            # them positionally would produce noise rather than findings. Only
            # reachable when the name difference was accepted -- an unaccepted
            # one already returned above.
            findings.append(
                f"{name} [{job_id}]: step counts differ ({len(gh_steps)} on "
                f"GitHub, {len(fj_steps)} on Forgejo), so the accepted "
                f"step-name divergence cannot be checked any further. Narrow "
                f"the ACCEPTED_DIVERGENCES entry or align the step lists."
            )
            continue

        # An accepted step-name divergence excuses the *names* and nothing
        # else. Skipping the job outright -- which this did until CodeRabbit
        # pointed it out on #992 -- meant the cosmetic
        # bot-health-watchdog step-name exception silently covered any change
        # to that job's commands or action pins as well. One accepted
        # difference must not become a blanket exemption for its whole job.
        for gh_step, fj_step in zip(gh_steps, fj_steps, strict=True):
            label = gh_step[0] or "(unnamed step)"
            key = f"{name}::{job_id}::{label}"
            accepted = key in ACCEPTED_DIVERGENCES
            if gh_step[1] != fj_step[1]:
                findings.append(
                    f"{name} [{job_id}] {label!r}: different action -- "
                    f"GitHub uses {gh_step[1]}, Forgejo uses {fj_step[1]}"
                )
            if gh_step[2] != fj_step[2] and not accepted:
                findings.append(
                    f"{name} [{job_id}] {label!r}: shell body differs "
                    f"({len(gh_step[2])} vs {len(fj_step[2])} lines)"
                )
            for field, gh_value, fj_value in zip(
                ("if", "with", "env", "continue-on-error"),
                gh_step[3:],
                fj_step[3:],
                strict=True,
            ):
                if gh_value != fj_value and not accepted:
                    findings.append(
                        f"{name} [{job_id}] {label!r}: {field!r} differs -- "
                        f"GitHub {gh_value!r}, Forgejo {fj_value!r}"
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

    findings: list[str] = []

    # A copy that has been deleted is the failure this check most needs to
    # catch, and deriving the checked set from the directory intersection
    # cannot catch it: delete .forgejo/workflows/production-gate.yml and it
    # simply drops out of the intersection, compare() is never called for it,
    # and the run exits 0 having checked six pairs instead of seven. The set
    # is therefore declared, not discovered.
    missing = [
        f"{name}: missing {'GitHub' if not (GH_DIR / name).is_file() else 'Forgejo'} copy "
        f"({'.github' if not (GH_DIR / name).is_file() else '.forgejo'}/workflows/{name})"
        for name in REQUIRED_DUPLICATED_WORKFLOWS
        if not ((GH_DIR / name).is_file() and (FJ_DIR / name).is_file())
    ]
    findings.extend(missing)

    checkable = sorted(
        name
        for name in REQUIRED_DUPLICATED_WORKFLOWS
        if (GH_DIR / name).is_file() and (FJ_DIR / name).is_file()
    )
    for name in checkable:
        findings.extend(compare(name))

    # A newly duplicated workflow is not a failure, but it should not sit
    # unchecked either -- reported so it gets added to the manifest.
    undeclared = sorted(
        ({p.name for p in GH_DIR.glob("*.yml")} & {p.name for p in FJ_DIR.glob("*.yml")})
        - REQUIRED_DUPLICATED_WORKFLOWS
    )
    for name in undeclared:
        findings.append(
            f"{name}: duplicated across both platforms but absent from "
            f"REQUIRED_DUPLICATED_WORKFLOWS, so nothing is comparing the two "
            f"copies. Add it to the manifest in this script."
        )

    print(
        f"Workflows required to exist on both platforms: "
        f"{len(REQUIRED_DUPLICATED_WORKFLOWS)}, of which {len(checkable)} compared"
    )
    for name in sorted(REQUIRED_DUPLICATED_WORKFLOWS):
        print(f"  - {name}{'' if name in checkable else '   [A COPY IS MISSING]'}")
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
