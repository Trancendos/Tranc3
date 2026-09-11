#!/usr/bin/env python3
"""Prove, on a clock, that this estate's sensors can still see.

    python scripts/vaccinate.py              # probe everything, report, fail on blindness
    python scripts/vaccinate.py --record     # ...and write the result as the new record
    python scripts/vaccinate.py --max-age 3  # also fail if the record has gone stale

Runs daily from `.github/workflows/supply-chain-watch.yml`, alongside the
dependency censuses, for the reason that workflow already sets out at length:
some things change in the world rather than in the repository, and a
push-triggered check cannot see them. A sensor going blind is one of those.

See `src/immune/vaccination.py` for why sight and cleanliness are different
questions, and `docs/governance/IMMUNE-SYSTEM.md` for the whole mechanism.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.immune.sensors import load_manifest  # noqa: E402
from src.immune.vaccination import (  # noqa: E402
    DEFAULT_RECORD,
    load_record,
    render,
    stale_sensors,
    vaccinate,
    write_record,
)


def _head() -> str:
    try:
        proc = subprocess.run(  # noqa: S603,S607 - fixed argv, no shell
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--record", action="store_true", help="write the result as the new record")
    ap.add_argument(
        "--max-age",
        type=int,
        default=None,
        metavar="DAYS",
        help="also fail when a sensor's last proof of sight is older than DAYS",
    )
    ap.add_argument("--record-path", type=Path, default=DEFAULT_RECORD)
    ap.add_argument("--timeout", type=int, default=180)
    args = ap.parse_args()

    sensors = load_manifest()
    previous = load_record(args.record_path)
    report = vaccinate(sensors, previous=previous, timeout=args.timeout)

    print(render(report))

    failures = report.failing()

    # Staleness is measured on the PREVIOUS record -- the one on disk -- and
    # never on the report this run just produced.
    #
    # The first version checked the fresh report, which cannot work: every
    # sensor that passes its probe is stamped with today's date a few lines
    # earlier, so nothing is ever stale and the check could not fire at all.
    # A control structurally incapable of reporting is the exact defect this
    # subsystem exists to find, and it was sitting in the one check whose job
    # is noticing that the schedule stopped. Measured: a record dated five
    # weeks back passed `--max-age 3` cleanly. Reported by cubic on PR #1150.
    #
    # Read against the committed record it means something real: "no fresh
    # proof of sight has been recorded for N days". The remedy it points at is
    # a person or an agent running `--record` and committing the result.
    #
    # WHICH IS WHY THE DAILY JOB NO LONGER PASSES IT. That job runs the probes
    # itself, so the committed record's age tells it nothing about sight, and it
    # holds no write token by design, so it cannot perform the remedy. Given
    # enough calendar its only possible outcome was a permanent red nobody
    # inside the job could clear -- a control shaped exactly like the `label`
    # check this repository already had to stop believing. It was removed from
    # `supply-chain-watch.yml` and the reason is written there.
    #
    # The flag stays for the caller who CAN act: a person at a terminal, or a
    # PR-time check where a human is present and the fix is one command.
    if args.max_age is not None:
        if not previous:
            failures.append(
                f"no immunity record at {args.record_path} — nothing has ever "
                "recorded that these sensors could see"
            )
        # Only sensors the manifest still declares. A record for a sensor that
        # has since been removed describes a scanner this estate no longer runs,
        # and failing on its age asks a deleted thing to keep proving itself.
        # Reported by cubic on PR #1150.
        current = {r.sensor for r in report.records}
        candidates = [r for r in previous.values() if r.probed and r.sensor in current]
        for record in stale_sensors(candidates, max_age_days=args.max_age):
            age = record.days_since_proven()
            failures.append(
                f"'{record.sensor}' has no recorded proof of sight "
                # "newer than N days" read backwards -- it described the proof
                # as recent when N is how long the estate has gone without one.
                + ("at all" if age is None else f"for {age} days")
                + f" (limit {args.max_age}) — rerun with --record and commit the result"
            )

    if args.record:
        write_record(report, path=args.record_path, commit=_head())
        print(f"\nrecorded to {args.record_path}")

    if failures:
        print("\nIMMUNITY LOST:", file=sys.stderr)
        for reason in failures:
            print(f"  - {reason}", file=sys.stderr)
        print(
            "\nA sensor that cannot see reports exactly what a clean estate reports.\n"
            "Fix the sensor before trusting any scan that included it.",
            file=sys.stderr,
        )
        return 1

    if report.unprobed:
        # Not a failure — a written gap. Printed every run so it stays visible
        # rather than becoming background, because the number that matters over
        # time is this one going down.
        print(
            f"\n{len(report.unprobed)} sensor(s) have never been asked to demonstrate "
            "anything. That is coverage the estate does not have yet, not immunity it does."
        )

    print("\nIMMUNITY HELD: every required sensor demonstrated it can see.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
