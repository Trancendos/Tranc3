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


def _changed(base: str) -> list[str]:
    try:
        merge_base = subprocess.run(  # noqa: S603,S607 - fixed argv, no shell
            ["git", "merge-base", "HEAD", base],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        ref = merge_base.stdout.strip() or base
        proc = subprocess.run(  # noqa: S603,S607 - fixed argv, no shell
            ["git", "diff", "--name-only", ref, "HEAD"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return []
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

    sensors = [s for s in load_manifest() if s.name == args.sensor]
    if not sensors:
        print(f"no sensor named '{args.sensor}' in the manifest", file=sys.stderr)
        return 2

    # The sensor is run here rather than trusting a stored report, because the
    # verdict that matters is whether it could see JUST NOW -- a cached `ok`
    # from an hour ago is the stale-evidence problem this estate keeps finding.
    results = [run_sensor(sensor, cwd=Path(".")) for sensor in sensors]
    findings = [f for result in results for f in result.findings]

    touched = None if args.all else _changed(args.base)

    kept, refusals = screen(
        findings,
        sensor_results=results,
        sensor=args.sensor,
        touched=touched,
        max_files=args.max_files,
    )

    run = AntibodyRun(refusals=refusals, considered=len(findings))
    if kept:
        run.proposals.append(propose_ruff_fix(sorted({f.path for f in kept})))

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
