#!/usr/bin/env python3
"""A suppression that silences nothing still reads as an adjudication.

WHY THIS EXISTS
---------------
Found by following one CodeFactor finding to its root, 2026-10-16.

`scripts/check_app_inventory.py` carried this line, written in this
repository, in the commit that added it:

    with urllib.request.urlopen(request, timeout=30) as response:  noqa: S310 - fixed host (with a leading hash)

Three things were true of it at once, and all three were invisible:

1. **The suppression silenced nothing.** `[tool.ruff] select` here is
   `["E", "F", "W", "C", "B", "I"]`. `S` -- flake8-bandit, the security
   family -- is absent, so ruff never raises S310 and the `noqa` had nothing
   to suppress. Probed rather than inferred: a file containing
   `os.system(user_input)`, `subprocess.call(user_input, shell=True)`,
   `exec(user_input)` and `eval(user_input)` passes this repository's ruff
   configuration with `All checks passed!`, and reports four findings under
   `--select S`.

2. **The reason was false.** "fixed host" described `GITHUB_API`, a constant.
   It did not describe the `path` concatenated onto it, which `--repo` and
   `$GITHUB_REPOSITORY` both reach. Nothing enforced the sentence.

3. **Nothing in this estate could see any of it.** bandit is the lane that
   does run, and `[tool.bandit]` sets `targets = ["src", "api.py"]`, lists
   `scripts` in `exclude_dirs`, and carries `B310` in its global `skips`. So
   the file was out of scope, and the rule was skipped anyway. The finding
   surfaced because `codefactor-io` runs bandit with its own configuration
   and ignores this repository's -- an App that, until this branch, was named
   in no document in the tree.

That is this estate's recurring defect class with a new surface: a control
that is present, readable, and looking at nothing. `check_nosec_specificity.py`
already guards the bandit half of it, and found that ``nosec-free`` silences
every bandit rule on its line. This is the ruff half, which nothing guarded.

WHAT IT ENFORCES
----------------
1. **A bare directive is counted and ceilinged.** With no code it silences
   every ruff rule on that line, now and for every rule added later. A line
   adjudicated safe for one thing has not been adjudicated safe for the next.

2. **An INERT code is counted and ceilinged.** A code is inert when ruff
   cannot raise it here: its family is not in `select`/`extend-select`, or
   the code itself is in `ignore`. Measured 2026-10-16: **172** of the
   repository's 803 `noqa` codes are inert -- 21% -- including 61 in the
   security family and 80 `PLC0415`.

Both are ratcheted rather than refused, which is deliberate and follows
`check_nosec_specificity.py`'s reasoning verbatim: "a guard that fails on the
backlog fails on every pull request, which is how a guard gets bypassed
rather than satisfied". The counts may fall and may never rise.

WHAT IT DOES NOT DO
-------------------
It does not decide whether `S` should be selected. Measured, that change
would raise 14,437 findings, 13,389 of them `assert` in tests, which bandit
already skips as B101 with a written reason. The number that should drive the
decision is narrower: **263** findings on `scripts/` and `workers/` in rule
classes bandit does *not* globally skip, against **37** on `src/` and
`api.py` where bandit does look. Seven times as many on the surface three
lanes each decline to scan. Choosing what to do about that is an owner's
decision with a real cost, not a checker's.
"""

from __future__ import annotations

import argparse
import re
import tomllib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CEILING = ROOT / "config/immune/noqa_ceiling.txt"

#: Directories that are not this repository's Python.
_SKIP_PARTS = ("target", "node_modules", ".git", ".venv", "venv", "build", "dist")

#: The directive, with or without codes. Mirrors ruff's own tolerance for spacing
#: and case so this sees exactly what ruff sees.
#: Built from parts on purpose. Written as one literal, the pattern contains
#: the directive token itself -- ruff would read this line as a suppression,
#: and this checker would count its own source as part of its subject. A
#: measuring instrument that appears in its own measurement is the defect
#: this file exists to catch, so it must not be one.
_TOKEN = "no" + "qa"
_NOQA = re.compile(
    r"#\s*" + _TOKEN + r"(?::\s*(?P<codes>[A-Z]+[0-9]+(?:\s*,\s*[A-Z]+[0-9]+)*))?",
    re.IGNORECASE,
)

INERT_NOT_SELECTED = "rule family is not selected, so ruff never raises it"
INERT_IGNORED = "code is in the global ignore list, so ruff never raises it"


@dataclass(frozen=True)
class Suppression:
    """One `noqa` code at one place, and whether ruff can act on it."""

    path: str
    line: int
    code: str
    inert_because: str = ""

    @property
    def inert(self) -> bool:
        return bool(self.inert_because)

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.code} — {self.inert_because}"


def ruff_rule_config(pyproject: Path) -> tuple[list[str], set[str]]:
    """The selected prefixes and the globally ignored codes.

    Reads `[tool.ruff.lint]` and falls back to `[tool.ruff]`, because ruff
    accepts both and this repository still uses the older top-level form.
    Reading only one would make the checker report on a configuration that is
    not in force -- the defect it exists to catch.
    """
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return [], set()
    ruff = (data.get("tool") or {}).get("ruff") or {}
    lint = ruff.get("lint") or ruff
    select = list(lint.get("select") or []) + list(lint.get("extend-select") or [])
    ignore = set(lint.get("ignore") or []) | set(lint.get("extend-ignore") or [])
    return select, ignore


def classify(code: str, select: list[str], ignore: set[str]) -> str:
    """Why ruff cannot raise this code here, or "" if it can.

    `ALL` selects everything, so nothing is inert under it. Otherwise a code
    is reachable when any selected prefix is a prefix of it -- ruff's own
    matching -- and unreachable codes are the subject of this checker.
    """
    if "ALL" in select:
        return INERT_IGNORED if code in ignore else ""
    if not any(code.startswith(prefix) for prefix in select):
        return INERT_NOT_SELECTED
    if code in ignore:
        return INERT_IGNORED
    return ""


def _python_files(root: Path) -> list[Path]:
    return [
        path
        for path in sorted(root.rglob("*.py"))
        if not any(part in _SKIP_PARTS for part in path.relative_to(root).parts)
    ]


def scan(root: Path = ROOT) -> tuple[list[Suppression], list[str], int]:
    """Every inert suppression, every bare directive, and the live count."""
    select, ignore = ruff_rule_config(root / "pyproject.toml")
    inert: list[Suppression] = []
    bare: list[str] = []
    live = 0
    for path in _python_files(root):
        shown = str(path.relative_to(root))
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for number, text in enumerate(lines, 1):
            match = _NOQA.search(text)
            if not match:
                continue
            codes = match.group("codes")
            if not codes:
                bare.append(f"{shown}:{number}")
                continue
            for code in (c.strip().upper() for c in codes.split(",")):
                because = classify(code, select, ignore)
                if because:
                    inert.append(Suppression(shown, number, code, because))
                else:
                    live += 1
    return inert, bare, live


def read_ceiling(path: Path = CEILING) -> dict[str, int]:
    """The recorded ceilings, or {} when none is recorded.

    An unreadable or malformed ceiling returns {} rather than zeros. Zeros
    would read as "nothing is wrong" and fail every pull request at once;
    absent reads as "nothing has been recorded", which is the truth.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    found: dict[str, int] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        try:
            found[key.strip()] = int(value.strip())
        except ValueError:
            continue
    return found if {"inert", "bare"} <= found.keys() else {}


def write_ceiling(inert: int, bare: int, path: Path = CEILING) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Suppressions that silence nothing, and suppressions that silence\n"
        "# everything. Both numbers may go down and may never go up. Lower one\n"
        "# in the same commit that removes the suppressions, so the diff shows\n"
        "# the work. See scripts/check_inert_suppressions.py for why.\n"
        f"inert={inert}\n"
        f"bare={bare}\n",
        encoding="utf-8",
    )


def _report(inert: list[Suppression], bare: list[str], live: int) -> None:
    total = live + len(inert)
    print(f"noqa suppressions: {total} codes across this repository")
    print(f"  live (ruff can raise the rule):      {live}")
    print(f"  INERT (ruff never raises the rule):  {len(inert)}")
    print(f"  bare, no code (silences every rule):  {len(bare)}")
    if inert:
        print("\n  inert by code:")
        for code, count in Counter(s.code for s in inert).most_common(12):
            print(f"      {code:10s} {count}")
        families = Counter(re.match(r"[A-Z]+", s.code).group() for s in inert)
        security = families.get("S", 0)
        if security:
            print(
                f"\n  {security} of them are in the security family (S). Those read as "
                "security\n  adjudications and are not enforced by anything here."
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--set-ceiling",
        action="store_true",
        help="record the current counts as the new ceilings",
    )
    parser.add_argument("--list", action="store_true", help="print every inert suppression")
    args = parser.parse_args(argv)

    inert, bare, live = scan(args.root)
    _report(inert, bare, live)

    if args.list:
        print()
        for suppression in inert:
            print(f"  {suppression}")
        for place in bare:
            print(f"  {place}: bare directive — silences every rule on this line")

    ceiling_path = args.root / "config/immune/noqa_ceiling.txt"
    if args.set_ceiling:
        write_ceiling(len(inert), len(bare), ceiling_path)
        print(f"\nCeilings set: inert={len(inert)}, bare={len(bare)}")
        return 0

    ceiling = read_ceiling(ceiling_path)
    if not ceiling:
        print(
            "\nInert suppressions: UNKNOWN — no ceiling recorded, so nothing was "
            "compared.\nRun --set-ceiling to freeze the current counts. This is not "
            "a pass: an\nunrecorded ceiling cannot tell a clean tree from an "
            "unmeasured one."
        )
        return 1

    failed = False
    for name, now, limit in (
        ("inert", len(inert), ceiling["inert"]),
        ("bare", len(bare), ceiling["bare"]),
    ):
        if now > limit:
            failed = True
            print(
                f"\nInert suppressions: FAILED — {name} rose to {now}, ceiling {limit}.\n"
                f"A new suppression that silences nothing is a comment claiming an\n"
                f"adjudication nobody made. Remove it, or select the rule it names."
            )
        elif now < limit:
            failed = True
            print(
                f"\nInert suppressions: FAILED — {name} fell to {now} (ceiling {limit}).\n"
                f"Lower the ceiling in this commit so the diff shows the work:\n"
                f"  python scripts/check_inert_suppressions.py --set-ceiling"
            )
    if failed:
        return 1
    print(
        f"\nInert suppressions: PASSED — holding at the ceilings "
        f"(inert={ceiling['inert']}, bare={ceiling['bare']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
