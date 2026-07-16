#!/usr/bin/env python3
"""Validate docs/architecture/ea-workbook/*.csv structural integrity.

Checks every row in every workbook CSV has the same column count as its
header row. Run manually with `python scripts/validate_ea_workbook.py`, or
via the pre-commit hook wired in .pre-commit-config.yaml.
"""

from __future__ import annotations

import csv
import glob
import os
import sys

WORKBOOK_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "docs",
    "architecture",
    "ea-workbook",
)


def validate() -> int:
    failures: list[str] = []
    csv_files = sorted(glob.glob(os.path.join(WORKBOOK_DIR, "*.csv")))
    if not csv_files:
        print(f"No CSV files found under {WORKBOOK_DIR}")
        return 1

    for path in csv_files:
        try:
            with open(path, newline="", encoding="utf-8") as fh:
                rows = list(csv.reader(fh, strict=True))
        except csv.Error as exc:
            failures.append(f"{os.path.basename(path)}: CSV parse error — {exc}")
            continue

        if not rows or not rows[0]:
            failures.append(f"{os.path.basename(path)}: missing or empty header row")
            continue
        header_len = len(rows[0])
        for i, row in enumerate(rows[1:], start=2):
            if row and len(row) != header_len:
                failures.append(
                    f"{os.path.basename(path)}:{i} — expected {header_len} columns, "
                    f"got {len(row)} (likely an unescaped comma in a free-text field)"
                )

    if failures:
        print("EA workbook CSV validation failed:")
        for f in failures:
            print(f"  {f}")
        return 1

    print(f"EA workbook CSV validation passed ({len(csv_files)} files checked).")
    return 0


if __name__ == "__main__":
    sys.exit(validate())
