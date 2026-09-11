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

    # Staleness is checked against the record we are about to write, not the one
    # we read, so a run that fixes the staleness is not also punished for it.
    if args.max_age is not None:
        stale = stale_sensors([r for r in report.records if r.probed], max_age_days=args.max_age)
        for record in stale:
            age = record.days_since_proven()
            failures.append(
                f"'{record.sensor}' has not proved sight "
                + ("ever" if age is None else f"for {age} days")
                + f" (limit {args.max_age})"
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
