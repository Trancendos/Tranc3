"""Antibodies: automated fixes that propose, never merge, and refuse when blind.

WHY THIS IS THE LAST PIECE AND NOT THE FIRST
--------------------------------------------
An antibody acts on what a sensor reports. So an antibody reading a BLIND
sensor acts on silence — and silence from a sensor that cannot see is
indistinguishable from silence from a healthy estate. It would make confident,
well-formed, wrong changes, and it would make them fastest exactly when the
immune system was least able to notice.

That is autoimmunity, and this codebase has now watched it happen twice in
miniature while being built: a probe left behind by a killed run was rescanned
and reported as a genuine complexity finding, and the obvious fix for that
(excluding the probe prefix in `pyproject.toml`) would have hidden the live
probe from its own scan and recorded every probed sensor as blind. Both were
the machinery attacking itself.

So vaccination came first, and this refuses to run without it.

THE FOUR REFUSALS
-----------------
1. **A sensor that is not `ok` gets no antibody.** Not "warn and continue" —
   refuse. The whole justification for acting automatically is that the finding
   is trustworthy, and a finding from an untrustworthy sensor is not.
2. **Never a security-critical surface.** `src/immune/surfaces.py` already
   names them, for the reviewer's benefit; the same list binds here. A wrong
   automated edit to a gate, an auth path, secret custody or a suppression list
   does not merely introduce a bug — it removes the thing that would have
   caught the bug.
3. **Never more than `max_files` in one run.** An antibody that can touch the
   whole tree in one pass is not a fix, it is a rewrite, and nobody reviews a
   rewrite properly.
4. **Only findings whose fix the TOOL itself supplies.** This does not invent
   repairs. `ruff --fix` knows which of its own rules are safely fixable and
   what the replacement is; that judgement stays with the tool that made the
   finding.

WHAT IT PRODUCES
----------------
A patch and a written case for it. Never a merge, never a push, never a commit
on anyone's behalf — the output is reviewable text, and a human or a reviewing
agent decides. "Proposes, never merges" is not a politeness; it is the property
that keeps a wrong antibody survivable.

Every run leaves an audit record of what it touched, what it refused, and why,
because an automated actor whose refusals are invisible is one nobody can
audit — and refusals are the interesting half.
"""

from __future__ import annotations

import json
import subprocess  # nosec B404 — used once, with a fixed argv and shell=False
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from src.immune.sarif import Finding
from src.immune.sensors import Outcome, SensorResult
from src.immune.surfaces import forbidden_for_automation

#: Nothing larger goes out in one proposal. Deliberately small: the ceiling is
#: about what a reviewer will actually read, not about what the tool can do.
DEFAULT_MAX_FILES = 10


@dataclass
class Refusal:
    """Why an antibody declined to act. The interesting half of the output."""

    reason: str
    detail: str
    paths: list[str] = field(default_factory=list)


@dataclass
class Proposal:
    """A fix an antibody is willing to put in front of a human."""

    rule: str
    paths: list[str] = field(default_factory=list)
    diff: str = ""
    findings: int = 0
    #: Set when the fixer could not run or exited in a way that is not a
    #: verdict. A proposal carrying this is NOT a fix and must never be counted
    #: as one -- see `empty`. It was previously communicated by writing the
    #: error into `diff`, which made `empty` false, which made `acted` true, so
    #: "the tool crashed" rendered as "a fix is proposed" and the audit recorded
    #: an action. That is the precise confusion this module's own comment warns
    #: about, reproduced two lines below the warning. Reported by cubic on
    #: PR #1150.
    failure: str = ""

    @property
    def failed(self) -> bool:
        return bool(self.failure)

    @property
    def empty(self) -> bool:
        """No fix on offer. A failure is empty: it proposed nothing."""
        return self.failed or not self.diff.strip()


@dataclass
class AntibodyRun:
    proposals: list[Proposal] = field(default_factory=list)
    refusals: list[Refusal] = field(default_factory=list)
    considered: int = 0

    @property
    def acted(self) -> bool:
        return any(not p.empty for p in self.proposals)

    def audit(self) -> dict:
        return {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "considered": self.considered,
            "proposed": [
                {"rule": p.rule, "paths": p.paths, "findings": p.findings}
                for p in self.proposals
                if not p.empty
            ],
            "refused": [
                {"reason": r.reason, "detail": r.detail, "paths": r.paths} for r in self.refusals
            ],
            # A fixer that could not run is recorded, because an audit trail
            # that omits "the tool was broken" is one where a run with no
            # proposals reads the same whether the estate was clean or the
            # scanner never answered.
            "could_not_run": [
                {"rule": p.rule, "failure": p.failure} for p in self.proposals if p.failed
            ],
        }


def _sensor_is_trustworthy(results: Sequence[SensorResult], name: str) -> SensorResult | None:
    for result in results:
        if result.name == name:
            return result
    return None


def screen(
    findings: Sequence[Finding],
    *,
    sensor_results: Sequence[SensorResult],
    sensor: str,
    touched: Sequence[str] | None = None,
    max_files: int = DEFAULT_MAX_FILES,
) -> tuple[list[Finding], list[Refusal]]:
    """Decide what an antibody is allowed to act on, and record what it is not.

    Order matters. The sensor check comes first because it invalidates
    everything downstream: if the instrument could not see, the findings it
    produced are not evidence, and filtering unusable evidence by path would be
    theatre.
    """
    refusals: list[Refusal] = []

    result = _sensor_is_trustworthy(sensor_results, sensor)
    if result is None:
        refusals.append(
            Refusal(
                "sensor absent from this run",
                f"'{sensor}' produced no result, so its silence proves nothing",
            )
        )
        return [], refusals
    if result.outcome is not Outcome.OK:
        refusals.append(
            Refusal(
                "sensor not trustworthy",
                f"'{sensor}' reported {result.outcome.value}: {result.detail}. "
                "Acting on a finding from an instrument that could not see is "
                "how an immune system attacks its own tissue.",
            )
        )
        return [], refusals

    candidates = [f for f in findings if f.sensor == sensor or f.tool == sensor]

    if touched is not None:
        allowed = set(touched)
        outside = sorted({f.path for f in candidates if f.path not in allowed})
        if outside:
            refusals.append(
                Refusal(
                    "outside the change",
                    "a fix in a file this change did not touch is unrelated work "
                    "arriving in someone else's review",
                    outside,
                )
            )
        candidates = [f for f in candidates if f.path in allowed]

    forbidden = forbidden_for_automation(sorted({f.path for f in candidates}))
    if forbidden:
        blocked = set()
        for label, why, paths in forbidden:
            blocked.update(paths)
            refusals.append(Refusal(f"security-critical surface: {label}", why, sorted(paths)))
        candidates = [f for f in candidates if f.path not in blocked]

    paths = sorted({f.path for f in candidates})
    if len(paths) > max_files:
        # `max(0, ...)` because a negative ceiling is a negative slice, and
        # `paths[:-3]` keeps everything but the last three rather than keeping
        # nothing. A scope ceiling that widens scope when misconfigured is
        # worse than no ceiling, since the number still reads like a limit.
        # Reported by cubic on PR #1150.
        keep = set(paths[: max(0, max_files)])
        refusals.append(
            Refusal(
                "scope limit",
                f"{len(paths)} files exceed the {max_files}-file ceiling; a proposal "
                "nobody reads carefully is not a fix",
                sorted(set(paths) - keep),
            )
        )
        candidates = [f for f in candidates if f.path in keep]

    return candidates, refusals


def propose_ruff_fix(
    paths: Sequence[str],
    *,
    repo_root: Path = Path("."),
    timeout: int = 300,
) -> Proposal:
    """Ask ruff for its own fix, as a diff. Nothing is written to disk.

    `--diff` rather than `--fix` on purpose: the repair is never applied, only
    described. That keeps the antibody incapable of changing the working tree
    even by accident, which is a stronger guarantee than intending not to.

    Only ruff's own safe fixes -- `--unsafe-fixes` is deliberately not passed.
    Which repairs are safe is a judgement belonging to the tool that made the
    finding, and overriding it here would be this module inventing repairs,
    which is exactly what it must not do.
    """
    if not paths:
        return Proposal(rule="ruff")
    try:
        # Suppression rationale for B603 and B607: shell=False, and the argv is fixed except for
        # `paths`, which `screen()` has already restricted to files inside the
        # change, off every security-critical surface, and under the scope
        # ceiling. `ruff` is resolved from PATH deliberately: pinning an
        # absolute path here would silently disagree with the pin the gate and
        # the pre-commit hook use, and two ruffs is worse than one on PATH.
        # NOTE the space after the comma below. bandit 1.9.4 parses a spaceless
        # id list as ONE unknown id, matches nothing, and silently honours
        # only the first — a suppression that claims two rules and silences
        # one. `scripts/check_nosec_specificity.py` now fails on the spaceless
        # form for exactly that reason.
        proc = subprocess.run(  # nosec B603, B607 # noqa: S603,S607
            ["ruff", "check", "--diff", *paths],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        # A tool that could not run proposes nothing, and says so in `failure`
        # rather than in `diff` -- an empty diff and a crashed scanner look
        # identical to a caller, and this whole codebase exists because those
        # two states kept getting confused. Writing the error into `diff` made
        # them identical in the OTHER direction: non-empty diff, so `acted` was
        # true and the audit recorded a fix that does not exist.
        return Proposal(rule="ruff", paths=list(paths), failure=f"ruff could not run: {exc}")
    # Measured against ruff 0.15.8: `check --diff` exits 0 when there is nothing
    # to fix and 1 when there is a diff to apply, so 1 is a verdict, not an
    # error. Anything else is ruff declining to answer -- a bad argument, a
    # config it cannot parse, an internal failure -- and must not be read as
    # "no fix needed".
    if proc.returncode not in (0, 1):
        detail = (proc.stderr or proc.stdout).strip().splitlines()
        return Proposal(
            rule="ruff",
            paths=list(paths),
            failure=f"ruff exited {proc.returncode}: {detail[-1] if detail else 'no output'}",
        )
    return Proposal(rule="ruff", paths=list(paths), diff=proc.stdout)


def render(run: AntibodyRun) -> str:
    """The proposal a human reads — refusals first, because they are the news."""
    lines = ["── antibody ────────────────────────────────────────────────"]
    lines.append(f"  considered    {run.considered} finding(s)")

    if run.refusals:
        lines.append("")
        lines.append("  REFUSED:")
        for refusal in run.refusals:
            lines.append(f"    - {refusal.reason}: {refusal.detail}")
            for path in refusal.paths[:5]:
                lines.append(f"        {path}")
            if len(refusal.paths) > 5:
                lines.append(f"        ...and {len(refusal.paths) - 5} more")

    # A fixer that could not run is its own line, not silence and not a fix.
    # It reads next to REFUSED because that is what it is operationally -- no
    # change is on offer -- but it is a different fact from a refusal, and the
    # reader is owed the difference.
    failed = [p for p in run.proposals if p.failed]
    if failed:
        lines.append("")
        lines.append("  COULD NOT RUN:")
        for proposal in failed:
            lines.append(f"    - {proposal.rule}: {proposal.failure}")

    acted = [p for p in run.proposals if not p.empty]
    if acted:
        lines.append("")
        lines.append("  PROPOSED (a diff — nothing has been written):")
        for proposal in acted:
            lines.append(
                f"    {proposal.rule}: {len(proposal.paths)} file(s) "
                f"from {proposal.findings} finding(s)"
            )
            for path in proposal.paths:
                lines.append(f"        {path}")
    else:
        lines.append("")
        lines.append("  PROPOSED: nothing.")
    return "\n".join(lines)


def write_audit(run: AntibodyRun, path: Path) -> None:
    """Append one line per run. Refusals are recorded as carefully as actions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(run.audit(), sort_keys=True) + "\n")
