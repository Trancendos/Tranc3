#!/usr/bin/env python3
"""bandit, over the whole configured surface, ratcheted -- and honest when blind.

WHY THIS EXISTS
---------------
Measured 2026-10-16, following a CodeFactor B310 finding to its root.

`[tool.bandit]` scoped the Python security lane to `targets = ["src", "api.py"]`
and additionally listed `scripts` in `exclude_dirs`, so `scripts/` was doubly
out of scope. At the gate's own `-ll --confidence-level medium` threshold:

    src/ + api.py          136,879 lines      36 Low,  0 Medium
    scripts/ + workers/     85,824 lines     153 Low, 79 Medium

The entire medium-severity population of this repository sat outside the lane,
including two unpinned Hugging Face Hub downloads at HIGH confidence in
`scripts/prepare_data.py` -- in a repository carrying FOUR separate pin guards
(`check_canonical_pin_governance.py`, `check_security_toolchain_pins.py`,
`validate_submodule_pins.py`, `audit_action_versions.py`), none of which looks
at Hub revisions.

WHY THIS IS NOT A FOURTH CONTROL
--------------------------------
The estate already had a bandit ratchet: `.forgejo/workflows/security-baseline.yml`,
with its count in `.security-baseline`. Measured, it had four problems at once:

1. **It has never run.** Its four jobs pin `runs-on: self-hosted`, and CLAUDE.md
   records that the Forgejo act-runner is deferred for the cloud-only phase.
   There is no GitHub Actions equivalent.
2. **It does not pass `-c pyproject.toml`**, so `[tool.bandit] skips` never
   applied. Of the 309 findings its documented command reports today, **147 are
   B311 and 101 are B110** -- both skipped in `pyproject.toml` with written
   reasons. 248 of 309 were findings the estate had already adjudicated. With
   the config loaded, the same scope reports **37**.
3. **Its baseline had drifted undetected**: `.security-baseline` records 307;
   the same command measures 309 today. The workflow that would have caught
   that is the one that never runs.
4. **Its scope was `src api.py workers/tateking/main.py`** -- one worker file
   out of roughly eighty.

So this script replaces that mechanism rather than joining it, and the Forgejo
workflow now calls this script instead of carrying its own copy. One
implementation, two callers, and they cannot disagree about what "holding"
means.

HOW IT STAYS HONEST
-------------------
Scope is read from `[tool.bandit] targets` rather than hardcoded, so the
configuration is the single source of truth for what is scanned and this
checker cannot quietly cover less than the config claims.

If bandit is missing, errors, or returns output that cannot be parsed, this
reports UNKNOWN and exits non-zero. It never reports a clean surface it did not
scan. That rule is the estate's founding one, and the reason this file exists at
all is a chain of three controls that broke it.
"""

from __future__ import annotations

import argparse
import collections
import json
import subprocess  # nosec B404 - fixed argv, no shell; see _run_bandit
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.immune.ratchet import (  # noqa: E402  - path set above
    compare,
    describe,
    read_ceiling,
    write_ceiling,
)

CEILING = ROOT / "config/immune/bandit_ceiling.txt"

#: The counts this ratchet holds. Severity bands rather than a single total,
#: because a total lets a medium finding arrive while two lows leave.
_REQUIRED = ("medium_plus", "low")

_HEADER = """\
bandit findings over the whole [tool.bandit] targets surface, with
-c pyproject.toml so the configured skips apply.

Both numbers may go down and may never go up. Lower one in the same
commit that fixes the findings, so the diff carries the work.

medium_plus is the band the gate blocks on elsewhere; low is tracked
so it cannot grow unwatched. See scripts/check_bandit_coverage.py for
why this replaced .forgejo/workflows/security-baseline.yml."""


def configured_scope(pyproject: Path) -> tuple[list[str], list[str]]:
    """`targets` and `exclude_dirs` from `[tool.bandit]`.

    Read rather than hardcoded so the config is the one place that decides
    what is scanned. A checker with its own copy of the scope is how a lane
    comes to cover less than its configuration says it does.
    """
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return [], []
    section = (data.get("tool") or {}).get("bandit") or {}
    return list(section.get("targets") or []), list(section.get("exclude_dirs") or [])


def _run_bandit(root: Path, targets: list[str]) -> tuple[list[dict], str]:
    """bandit's findings, or an explanation of why there are none to report.

    The second element is empty on success and carries the reason on failure.
    An empty list with an empty reason means a genuinely clean scan; an empty
    list with a reason means UNKNOWN, and the caller must not treat the two
    alike.
    """
    if not targets:
        return [], "[tool.bandit] names no targets, so nothing would be scanned"
    # Written to a file rather than read from stdout: bandit emits manager
    # WARNINGs (e.g. for a nosec comment naming something that is not a test
    # id) onto the same stream as the report, and a checker that parsed stdout
    # would report UNKNOWN whenever one appeared.
    report_path = Path(tempfile.gettempdir()) / "bandit-coverage.json"
    argv = [
        sys.executable,
        "-m",
        "bandit",
        "-c",
        "pyproject.toml",
        "-r",
        *targets,
        "-f",
        "json",
        "-o",
        str(report_path),
    ]
    try:
        # Fixed argv, no shell, cwd pinned to the repository root.
        proc = subprocess.run(  # nosec B603 - fixed argv built above, shell=False
            argv, cwd=root, capture_output=True, text=True, timeout=900, check=False
        )
    except FileNotFoundError:
        return [], "bandit is not installed (pip install 'bandit[toml]')"
    except subprocess.TimeoutExpired:
        return [], "bandit did not finish within 900s"

    # bandit exits 1 when it finds something, which is not an error. Only an
    # unparseable or absent report is.
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        tail = detail[-1] if detail else "no output"
        return [], f"bandit produced no parseable JSON ({tail})"
    results = report.get("results")
    if not isinstance(results, list):
        return [], "bandit JSON had no `results` list"
    return results, ""


def tally(results: list[dict]) -> dict[str, int]:
    medium_plus = sum(1 for r in results if r.get("issue_severity") in ("MEDIUM", "HIGH"))
    low = sum(1 for r in results if r.get("issue_severity") == "LOW")
    return {"medium_plus": medium_plus, "low": low}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--set-ceiling", action="store_true", help="record the current counts as the ceilings"
    )
    parser.add_argument("--list", action="store_true", help="print medium+ findings")
    args = parser.parse_args(argv)

    targets, excluded = configured_scope(args.root / "pyproject.toml")
    print(f"bandit scope (from [tool.bandit]): {', '.join(targets) or '(none)'}")
    if excluded:
        print(f"  excluded: {', '.join(excluded)}")

    results, blind = _run_bandit(args.root, targets)
    if blind:
        print(
            f"\nbandit coverage: UNKNOWN — {blind}.\n"
            "This is not a pass. A security lane that could not run reports the "
            "same thing\na clean one does unless it says so, which is the defect "
            "this checker exists for."
        )
        return 1

    counts = tally(results)
    ceiling = read_ceiling(args.root / "config/immune/bandit_ceiling.txt", require=_REQUIRED)

    print(f"\n{len(results)} findings over the configured surface")
    print(describe(counts, ceiling))
    # `or "?"` rather than the bare value: a result without a test_id crashed
    # the report formatter. Real bandit output always carries one, so this
    # path was unreachable in production and reachable in a test -- which is
    # exactly the kind of crash a security checker must not have, since it
    # turns a findings report into a traceback.
    worst = collections.Counter(
        (r.get("test_id") or "?") for r in results if r.get("issue_severity") in ("MEDIUM", "HIGH")
    )
    if worst:
        print("\n  medium+ by rule:")
        for rule, n in worst.most_common():
            print(f"      {rule:8s} {n}")

    if args.list:
        print()
        for r in results:
            if r.get("issue_severity") in ("MEDIUM", "HIGH"):
                print(
                    f"  {r.get('test_id')} {r.get('issue_severity')}/{r.get('issue_confidence')} "
                    f"{r.get('filename')}:{r.get('line_number')} {str(r.get('issue_text'))[:80]}"
                )

    if args.set_ceiling:
        write_ceiling(args.root / "config/immune/bandit_ceiling.txt", counts, header=_HEADER)
        print(f"\nCeilings set: {counts}")
        return 0

    if not ceiling:
        print(
            "\nbandit coverage: UNKNOWN — no ceiling recorded, so nothing was compared.\n"
            "Run --set-ceiling to freeze the current counts. An unrecorded ceiling "
            "cannot\ntell an improving surface from an unmeasured one."
        )
        return 1

    problems = compare(counts, ceiling, what="bandit finding")
    if problems:
        print("\nbandit coverage: FAILED")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(
        f"\nbandit coverage: PASSED — holding at the ceilings "
        f"(medium_plus={ceiling['medium_plus']}, low={ceiling['low']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
