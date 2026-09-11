#!/usr/bin/env python3
r"""An anchored `^...$` validator called with `.match()` accepts a trailing newline.

WHY THIS EXISTS
---------------
Found while adjudicating the two `py/sql-injection` alerts at CodeQL severity
8.8 in `src/vector/adapter.py`. The alert is a false positive — the code
validates the derived table name against `^[a-z][a-z0-9_]{0,62}$` and raises,
and measured against every injection shape (quotes, semicolons, spaces,
parentheses, a full `'; DROP TABLE t; --` payload) the validator holds.

But the validator does not enforce what it says, because of a Python detail:

    re.compile(r"^[a-z][a-z0-9_]{0,62}$").match("vec_abc\n")   ->  MATCHES

`$` matches at the end of the string **or immediately before a trailing
newline**. So every `^...$` pattern used with `.match()` silently admits one
trailing `\n`, no matter how strict its character class reads.

`re.fullmatch` has no such exemption:

    re.compile(r"^[a-z][a-z0-9_]{0,62}$").fullmatch("vec_abc\n")  ->  None

MEASURED, NOT PATTERN-MATCHED
-----------------------------
Seven validators in this estate had the combination, and **none of them was
exploitable** at the time it was found:

    src/vector/adapter.py            SQL table name  — \n is SQL whitespace
    src/database/encrypted_sqlite.py SQL table name  — same
    workers/vault-service/worker.py  URL segment     — percent-encoded after
    workers/tateking/main.py         output filename
    workers/tateking/worker.py       ffmpeg argv     — list argv, no shell
    src/dvms/native_ecosystems.py    advisory id
    scripts/check_trivyignore_governance.py  a guard's own input

That is the honest summary and it is why this file exists rather than a row in
the security register: it is not seven vulnerabilities, it is seven controls
whose stated contract is not the one they enforce, each one character from
being correct, with nothing anywhere that would notice if one of them became
exploitable. A validator that admits a character its own character class
forbids is the estate's recurring defect in miniature.

WHAT IT ENFORCES
----------------
A module- or class-level `re.compile` whose pattern starts `^` and ends `$`
must not be used with `.match(`. Use `.fullmatch(`.

Line-oriented parsers are the legitimate exception and are exempted two ways:
a `re.MULTILINE` flag on the compile (where `$` before a newline is the entire
point), or an explicit `# anchored-ok: <reason>` on the call line.

    python scripts/check_anchored_validators.py           # check
    python scripts/check_anchored_validators.py --list    # every anchored pattern
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: `NAME = <anything>.compile(r"^...$")`, capturing the binding name.
#: Deliberately does not try to parse Python — a regex over source is enough to
#: find a naming convention, and an AST walk would still have to guess at
#: re-exports.
#:
#: `<anything>.compile` rather than `re.compile` because the first version of
#: this guard required the literal `re.compile(` and therefore could not see
#: the validator it was written for:
#:
#:      _SAFE_IDENT = __import__("re").compile(r"^[a-z][a-z0-9_]{0,62}$")
#:
#: Caught by calibration — planting `.match()` back into `src/vector/adapter.py`
#: and finding the guard still green. A guard blind to its own motivating case
#: is the defect this estate keeps finding, and it had one run of existing
#: before doing it too.
_COMPILE = re.compile(
    r"^\s*(?P<name>_?[A-Za-z][A-Za-z0-9_]*)\s*=\s*[\w.\"'()\[\]]*compile\(\s*r?(?P<q>['\"])"
    r"(?P<pat>\^.*\$)(?P=q)(?P<rest>[^)]*)\)",
    re.MULTILINE,
)
_EXEMPT_COMMENT = re.compile(r"#\s*anchored-ok:\s*\S")


@dataclass
class Offence:
    path: str
    line: int
    name: str
    text: str


def _tracked_python(root: Path = ROOT) -> list[str]:
    proc = subprocess.run(  # noqa: S603,S607 - fixed argv, no shell
        # `--cached --others --exclude-standard`: tracked files AND untracked
        # ones that are not gitignored. `git ls-files` alone lists only
        # tracked files, so a file added but not yet committed was
        # invisible to this guard -- a green local run and a red CI run
        # for exactly the files someone just wrote, which is the worst
        # possible place for a guard to be blind. Measured: this guard
        # passed locally on its own new test file and failed in CI the
        # moment that file was committed.
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.py"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    return sorted({ln.strip() for ln in proc.stdout.splitlines() if ln.strip()})


def scan(root: Path = ROOT) -> tuple[list[Offence], int]:
    """Return (offences, total anchored patterns seen)."""
    offences: list[Offence] = []
    anchored_total = 0
    for rel in _tracked_python(root):
        if rel == "scripts/check_anchored_validators.py":
            continue  # this file, which necessarily contains the pattern
        try:
            source = (root / rel).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        anchored: set[str] = set()
        for m in _COMPILE.finditer(source):
            # `re.MULTILINE` is the line-parser case: `$` before a newline is
            # the whole point, and `.match()` is correct there.
            if "MULTILINE" in m.group("rest"):
                continue
            anchored.add(m.group("name"))
        anchored_total += len(anchored)
        if not anchored:
            continue
        for number, line in enumerate(source.splitlines(), 1):
            if _EXEMPT_COMMENT.search(line):
                continue
            for name in anchored:
                if re.search(rf"(?:\b|\.){re.escape(name)}\.match\(", line):
                    offences.append(Offence(rel, number, name, line.strip()[:110]))
    return offences, anchored_total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--list", action="store_true", help="print every anchored pattern found")
    args = parser.parse_args(argv)

    offences, total = scan()
    print(
        f"anchored `^...$` patterns (non-MULTILINE): {total}; used with .match(): {len(offences)}"
    )

    if args.list:
        for off in offences:
            print(f"  {off.path}:{off.line}  {off.name}")

    if offences:
        print(
            "\nANCHORED VALIDATOR CALLED WITH .match() — each of these accepts a\n"
            "trailing newline that its own character class forbids:\n",
            file=sys.stderr,
        )
        for off in offences:
            print(f"  {off.path}:{off.line}", file=sys.stderr)
            print(f"    {off.text}", file=sys.stderr)
            print(f"    → use {off.name}.fullmatch(...)", file=sys.stderr)
        print(
            "\nIf `$`-before-newline is genuinely wanted (a line parser), say so on\n"
            "the call line: `# anchored-ok: <why>`.",
            file=sys.stderr,
        )
        return 1

    print("No anchored validator enforces less than it states.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
