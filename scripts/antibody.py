#!/usr/bin/env python3
"""Propose automated fixes — never apply them, and refuse when the sensor is blind.

    python scripts/antibody.py                 # against the current change
    python scripts/antibody.py --base main     # pick the comparison point
    python scripts/antibody.py --all           # whole tree, not just the change
    python scripts/antibody.py --max-files 3   # tighten the scope ceiling

Prints a diff and the reasoning. Writes nothing to the working tree, commits
nothing, pushes nothing, merges nothing. Apply with `git apply` after reading
it, which is the point: a human or a reviewing agent decides.

The refusals are the interesting output. See `src/immune/antibody.py` for why
an antibody that acts on a blind sensor's silence is autoimmunity, and
`docs/governance/IMMUNE-SYSTEM.md` for how it fits the rest.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.immune.antibody import (  # noqa: E402
    DEFAULT_MAX_FILES,
    AntibodyRun,
    propose_ruff_fix,
    render,
    screen,
    write_audit,
)
from src.immune.sensors import load_manifest, run_sensor  # noqa: E402

AUDIT = Path("logs/antibody.jsonl")

# Which sensors an antibody can actually fix. One entry today, and the table
# exists so that number is visible rather than assumed: `--sensor` used to
# accept any name in the manifest and then run ruff's fixer regardless.
FIXERS = {"ruff": propose_ruff_fix}


class ScopeUnavailable(RuntimeError):
    """The change could not be determined, so there is no honest scope to screen against.

    `_changed()` used to return `[]` when `git merge-base` failed -- an
    unresolvable base fell through to `git diff --name-only <bad-ref> HEAD`,
    which errors, and the empty stdout became an empty scope. An empty scope is
    not neutral here: `screen()` refuses every finding as "outside the change",
    so the antibody reported a clean, careful, entirely fictional run in which
    it declined to act because nothing had changed.

    "The tool could not tell" and "there is nothing to do" produced identical
    output, which is the defect class this whole subsystem exists to refuse,
    sitting in the subsystem. Reported by cubic on PR #1150.
    """


def _changed(base: str) -> list[str]:
    """Files changed against `base`. Raises rather than guessing."""
    try:
        merge_base = subprocess.run(  # noqa: S603,S607 - fixed argv, no shell
            ["git", "merge-base", "HEAD", base],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if merge_base.returncode != 0 or not merge_base.stdout.strip():
            raise ScopeUnavailable(
                f"git merge-base HEAD {base} failed: "
                f"{(merge_base.stderr or '').strip() or 'no common ancestor'}"
            )
        ref = merge_base.stdout.strip()
        proc = subprocess.run(  # noqa: S603,S607 - fixed argv, no shell
            ["git", "diff", "--name-only", ref, "HEAD"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if proc.returncode != 0:
            raise ScopeUnavailable(
                f"git diff --name-only {ref[:12]} HEAD failed: "
                f"{(proc.stderr or '').strip() or 'no output'}"
            )
    except (subprocess.SubprocessError, OSError) as exc:
        raise ScopeUnavailable(f"git could not be run: {exc}") from None
    return [line.strip() for line in proc.stdout.splitlines() if line.strip().endswith(".py")]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default="origin/main", help="comparison point for the change")
    ap.add_argument(
        "--all",
        action="store_true",
        help="consider the whole tree instead of only the change (widens scope deliberately)",
    )
    ap.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES)
    ap.add_argument("--sensor", default="ruff", help="which sensor's findings to act on")
    ap.add_argument("--audit", type=Path, default=AUDIT)
    args = ap.parse_args()

    # One fixer exists, and it is ruff's. Accepting `--sensor bandit` and then
    # calling `propose_ruff_fix` on bandit's files does not fix a bandit finding
    # -- it proposes whatever unrelated lint ruff happens to have on those
    # paths, labelled as the answer to a security finding. Refuse the flag
    # rather than answer the wrong question. Reported by cubic on PR #1150.
    if args.sensor not in FIXERS:
        print(
            f"no antibody knows how to fix '{args.sensor}' findings. "
            f"Fixers exist for: {', '.join(sorted(FIXERS))}.\n"
            "A sensor with no fixer is not a gap to paper over with another "
            "sensor's fixer; it is a fixer somebody has to write.",
            file=sys.stderr,
        )
        return 2

    sensors = [s for s in load_manifest() if s.name == args.sensor]
    if not sensors:
        print(f"no sensor named '{args.sensor}' in the manifest", file=sys.stderr)
        return 2

    # The sensor is run here rather than trusting a stored report, because the
    # verdict that matters is whether it could see JUST NOW -- a cached `ok`
    # from an hour ago is the stale-evidence problem this estate keeps finding.
    results = [run_sensor(sensor, cwd=Path(".")) for sensor in sensors]
    findings = [f for result in results for f in result.findings]

    if args.all:
        touched = None
    else:
        try:
            touched = _changed(args.base)
        except ScopeUnavailable as exc:
            print(f"cannot determine the change: {exc}", file=sys.stderr)
            print(
                "Refusing to run. An undetermined scope screens every finding out "
                "as 'outside the change', which reads exactly like a clean run.\n"
                "Fetch the base ref, or pass --all to widen scope on purpose.",
                file=sys.stderr,
            )
            return 2

    kept, refusals = screen(
        findings,
        sensor_results=results,
        sensor=args.sensor,
        touched=touched,
        max_files=args.max_files,
    )

    run = AntibodyRun(refusals=refusals, considered=len(findings))
    if kept:
        proposal = FIXERS[args.sensor](sorted({f.path for f in kept}))
        # The audit said every proposal came from zero findings, because nothing
        # ever set this. A record that always reports 0 is not a record.
        proposal.findings = len(kept)
        run.proposals.append(proposal)

    print(render(run))

    acted = [p for p in run.proposals if not p.empty]
    if acted:
        print("\n" + "─" * 60)
        for proposal in acted:
            print(proposal.diff)
        print("─" * 60)
        print(
            "Nothing above has been applied. Read it, then `git apply` if you agree.\n"
            "This tool does not write, commit, push, or merge."
        )

    write_audit(run, args.audit)
    # Always 0: proposing a fix is not a failure, and having nothing to propose
    # is not either. A non-zero exit here would turn an advisory into a gate,
    # and a gate that edits code is the thing this design refuses to be.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
