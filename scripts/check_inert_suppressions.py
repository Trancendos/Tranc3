#!/usr/bin/env python3
"""A suppression that silences nothing still reads as an adjudication.

WHY THIS EXISTS
---------------
Found by following one CodeFactor finding to its root, 2026-10-16.

`scripts/check_app_inventory.py` carried this line, written in this
repository, in the commit that added it:

    with urllib.request.urlopen(request, timeout=30) as response:  noqa: S310 - fixed host (with a leading hash)

Three things were true of it at once, and all three were invisible:

1. **The suppression silenced nothing.** `[tool.ruff.lint] select` here is
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
   the code itself is in `ignore`, or the file's own per-file-ignores cover it.
   Measured 2026-10-16: **177** of the repository's 804 codes are inert -- 22%
   -- including 61 in the
   security family and 80 `PLC0415`.

**What the ratchet does not do:** it reads the ceiling from the working tree, so
raising `noqa_ceiling.txt` in the same commit that adds a suppression passes at
equality. Comparing against the base revision would close that, and
`nosec_ceiling.txt` has the identical property -- so it is a decision about the
pattern rather than this file, and it is recorded here rather than papered over.
What the ratchet does prevent is the silent case: a suppression added without
touching the ceiling.

Both are ratcheted rather than refused, which is deliberate and follows
`check_nosec_specificity.py`'s reasoning verbatim: "a guard that fails on the
backlog fails on every pull request, which is how a guard gets bypassed
rather than satisfied". The counts may fall and may never rise.

WHAT IT DOES NOT DO
-------------------
It does not decide whether `S` should be selected. Measured, that change
would raise 14,473 findings, 13,425 of them `assert` in tests, which bandit
already skips as B101 with a written reason. Both figures move with every test
file added, so they are a scale rather than a tracked number. The number that should drive the
decision is narrower: **263** findings on `scripts/` and `workers/` in rule
classes bandit does *not* globally skip, against **37** on `src/` and
`api.py` where bandit does look. Seven times as many on the surface three
lanes each decline to scan. Choosing what to do about that is an owner's
decision with a real cost, not a checker's.
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import sys
import tokenize
import tomllib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.immune.ratchet import compare  # noqa: E402  - path set above
from src.immune.ratchet import read_ceiling as _read_ceiling  # noqa: E402
from src.immune.ratchet import write_ceiling as _write_ceiling  # noqa: E402
from src.immune.repo import inside_submodule, submodule_paths  # noqa: E402

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


def ruff_rule_config(pyproject: Path) -> tuple[list[str], set[str], dict[str, list[str]]]:
    """The selected prefixes and the globally ignored codes.

    Reads `[tool.ruff.lint]` and falls back to `[tool.ruff]`, because ruff
    accepts both and this repository still uses the older top-level form.
    Reading only one would make the checker report on a configuration that is
    not in force -- the defect it exists to catch.
    """
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return [], set(), {}
    ruff = (data.get("tool") or {}).get("ruff") or {}
    lint = ruff.get("lint") or ruff
    select = list(lint.get("select") or []) + list(lint.get("extend-select") or [])
    ignore = set(lint.get("ignore") or []) | set(lint.get("extend-ignore") or [])
    per_file = {
        str(pattern): [str(c) for c in codes]
        for pattern, codes in (lint.get("per-file-ignores") or {}).items()
    }
    return select, ignore, per_file


def _glob_match(path: str, pattern: str) -> bool:
    """Does `path` match `pattern` the way ruff matches per-file-ignores?

    Plain `fnmatch` lets `*` cross `/`, and ruff's globset does not: `tests/*`
    covers `tests/x.py` and NOT `tests/e2e/x.py`, while `**` is what spans
    directories. This repository's config relies on the difference -- it writes
    both `tests/*` and `src/nanoservices/**` -- so matching with `fnmatch`
    applied the first set of ignores to five nested test files ruff would never
    apply them to, and a live suppression there was counted as inert. Wrong in
    the lenient direction, which inflates the ceiling. Raised by coderabbit
    on #1403.

    A pattern with no separator matches the file NAME at any depth, which is
    also ruff's rule and is what makes `__init__.py` usable as a pattern.
    """
    if "/" not in pattern:
        return fnmatch.fnmatchcase(path.rsplit("/", 1)[-1], pattern)

    parts = path.split("/")
    globs = pattern.split("/")

    def walk(i: int, j: int) -> bool:
        while j < len(globs):
            if globs[j] == "**":
                # Zero or more segments: try every split point from here.
                if j + 1 == len(globs):
                    return True
                return any(walk(k, j + 1) for k in range(i, len(parts) + 1))
            if i >= len(parts) or not fnmatch.fnmatchcase(parts[i], globs[j]):
                return False
            i += 1
            j += 1
        return i == len(parts)

    return walk(0, 0)


def _file_ignores(shown: str, per_file: dict[str, list[str]]) -> set[str]:
    """Codes ruff ignores for THIS file, from `[tool.ruff.lint.per-file-ignores]`.

    Without this, a suppression in `tests/` naming a `B` rule read as live even
    though `"tests/*" = ["S", "B", ...]` means ruff never raises it there -- so
    a whole directory could accumulate inert suppressions under the ceiling.
    Measured on `tests/test_cryptex.py:144`.
    """
    codes: set[str] = set()
    for pattern, ignored in per_file.items():
        if _glob_match(shown, pattern):
            codes.update(ignored)
    return codes


def classify(
    code: str, select: list[str], ignore: set[str], file_ignores: frozenset[str] = frozenset()
) -> str:
    """Why ruff cannot raise this code here, or "" if it can.

    `ALL` selects everything, so nothing is inert under it. Otherwise a code
    is reachable when any selected prefix is a prefix of it -- ruff's own
    matching -- and unreachable codes are the subject of this checker.
    """
    # A per-file ignore matches by PREFIX, as ruff matches it: `["B"]` covers
    # B008, so a suppression naming B008 in that file silences nothing.
    if any(code.startswith(prefix) for prefix in file_ignores):
        return INERT_IGNORED
    if "ALL" in select:
        return INERT_IGNORED if code in ignore else ""
    if not any(code.startswith(prefix) for prefix in select):
        return INERT_NOT_SELECTED
    if code in ignore:
        return INERT_IGNORED
    return ""


def _python_files(root: Path) -> list[Path]:
    """This repository's Python files, excluding every submodule.

    A submodule is a different repository with its own reviewers and its own
    ceilings, and `ci.yml`'s Pytest job is the only one that checks them out
    (`submodules: recursive`). Counting them here made this ratchet measure a
    larger tree in that one job than anywhere else, so a ceiling recorded in a
    normal worktree failed there for a reason nobody's diff caused. See
    `src/immune/repo.py`.
    """
    submodules = submodule_paths(root)
    return [
        path
        for path in sorted(root.rglob("*.py"))
        if not any(part in _SKIP_PARTS for part in path.relative_to(root).parts)
        and not inside_submodule(path.relative_to(root), submodules)
    ]


def _comments(path: Path) -> list[tuple[int, str]]:
    """Every COMMENT token in a file, as (line number, text).

    Tokenizing rather than scanning raw lines, because the directive token
    appears inside string literals in this repository -- test fixtures that
    assert on suppressions, and docstrings explaining them. A raw-line scan
    counted those as real suppressions, so the instrument was measuring its own
    test data. Measured on `tests/test_test_env_isolation.py:339`.

    Falls back to raw lines when the file does not tokenize (genuinely invalid
    Python), where a line scan is still better than silence.
    """
    try:
        with tokenize.open(path) as handle:
            return [
                (tok.start[0], tok.string)
                for tok in tokenize.generate_tokens(handle.readline)
                if tok.type == tokenize.COMMENT
            ]
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return [
            (n, line)
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
            if "#" in line
        ]


def scan(root: Path = ROOT) -> tuple[list[Suppression], list[str], int, list[str]]:
    """Inert suppressions, bare directives, the live count, and unreadable files.

    The fourth element is the point. An unreadable file used to be skipped with
    `continue`, so a file holding a new suppression could drop out of the
    measurement while the ceiling still held -- a gate passing on a count it
    did not take. Unreadable is now reported and the caller fails on it.
    """
    select, ignore, per_file = ruff_rule_config(root / "pyproject.toml")
    inert: list[Suppression] = []
    bare: list[str] = []
    unreadable: list[str] = []
    live = 0
    for path in _python_files(root):
        shown = str(path.relative_to(root))
        try:
            comments = _comments(path)
        except (OSError, UnicodeDecodeError) as exc:
            unreadable.append(f"{shown}: {exc}")
            continue
        file_ignores = frozenset(_file_ignores(shown, per_file))
        for number, text in comments:
            match = _NOQA.search(text)
            if not match:
                continue
            codes = match.group("codes")
            if not codes:
                bare.append(f"{shown}:{number}")
                continue
            for code in (c.strip().upper() for c in codes.split(",")):
                because = classify(code, select, ignore, file_ignores)
                if because:
                    inert.append(Suppression(shown, number, code, because))
                else:
                    live += 1
    return inert, bare, live, unreadable


def read_ceiling(path: Path = CEILING) -> dict[str, int]:
    """Delegates to `src.immune.ratchet`.

    This file had its own copy, which was the third in the estate. The shared
    module carries the semantics and the argument for them -- an unrecorded
    ceiling is UNKNOWN rather than zero, and a FALL fails too, so the ceiling
    is lowered in the commit that does the work. Kept as a named wrapper
    because the tests pin this name and because the required keys belong here,
    not in the shared module.
    """
    return _read_ceiling(path, require=("inert", "bare"))


def write_ceiling(inert: int, bare: int, path: Path = CEILING) -> None:
    _write_ceiling(
        path,
        {"inert": inert, "bare": bare},
        header=(
            "Suppressions that silence nothing, and suppressions that silence\n"
            "everything. Both numbers may go down and may never go up. Lower one\n"
            "in the same commit that removes the suppressions, so the diff shows\n"
            "the work. See scripts/check_inert_suppressions.py for why."
        ),
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

    inert, bare, live, unreadable = scan(args.root)
    _report(inert, bare, live)

    if unreadable:
        print(
            f"\nInert suppressions: UNKNOWN — {len(unreadable)} Python file(s) could "
            "not be read,\nso the count below is not of this repository. A ceiling "
            "that holds against a\npartial scan is not holding against anything."
        )
        for problem in unreadable:
            print(f"  - {problem}")
        return 1

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

    problems = compare({"inert": len(inert), "bare": len(bare)}, ceiling, what="inert suppression")
    if problems:
        print("\nInert suppressions: FAILED")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(
        f"\nInert suppressions: PASSED — holding at the ceilings "
        f"(inert={ceiling['inert']}, bare={ceiling['bare']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
