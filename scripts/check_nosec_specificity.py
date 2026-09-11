#!/usr/bin/env python3
"""Every `# nosec` must name the rule it silences and say why.

WHY THIS EXISTS
---------------
Found by accident, while calibrating the immune gate. A probe file was planted
in `src/` with a deliberate shell injection and this comment beside it:

    return subprocess.call(user_input, shell=True)  # nosec-free on purpose

bandit reported B404 (importing subprocess) and said nothing about B602 (the
actual shell injection, HIGH severity). Measured on bandit 1.9.4: the token
`nosec` followed by a hyphen still triggers suppression, because bandit splits
the comment on non-word characters. `# nosec-free`, `# nosec-style`,
`# nosec: see ticket` all silence the line. `# nosecure` does not -- that is one
word. So an English phrase can disable a security check, and the check's own
absence is the only evidence.

That is the estate's recurring defect class in its purest form: a control that
is present, configured and reporting, and is not looking at the thing everyone
believes it is looking at.

WHAT IT ENFORCES
----------------
1. **A bare `# nosec` is refused.** With no rule id it silences EVERY bandit
   rule on that line, now and forever. A line adjudicated safe for B108 has not
   been adjudicated safe for the SQL injection someone adds to it next year.
   This is the same defect already fixed once in this repository, in
   `scripts/filter_codeql_alerts.py`: a suppression broader than its own name.

2. **A `# nosec` with no reason is ratcheted, not refused.** `# nosec B108`
   says what was silenced; it does not say why anyone should believe that was
   right. There are 80 of these already, and a guard that fails on the backlog
   fails on every pull request, which is how a guard gets bypassed rather than
   satisfied. So the count is a ceiling in `config/immune/nosec_ceiling.txt`:
   adding another fails, removing one lowers the ceiling. The backlog can only
   shrink, and it shrinks in commits that argue for each line.

   The README describes "80 documented nosec suppressions". Measured, 80 is
   exactly the count of the UNdocumented ones -- 267 of the 347 carry a written
   reason, 80 do not. Not a contradiction anyone introduced deliberately; a
   figure that was true of something once and kept its wording.

3. **`nosec` immediately followed by a word character is refused** as a likely
   accident -- it reads like prose and behaves like a suppression, or reads
   like a suppression and does nothing. Either way the writer's intent and the
   tool's behaviour have come apart.

Measured at introduction: 347 suppressions, 0 bare, 0 accidental, 80 without a
reason. The blocking half of this guard is green on the day it lands and its
job is to stay that way -- closing a door while it is still shut, which is the
only time closing it is cheap.

    python scripts/check_nosec_specificity.py              # check
    python scripts/check_nosec_specificity.py --list       # every suppression
    python scripts/check_nosec_specificity.py --set-ceiling  # after removing some
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# bandit splits the comment on non-word characters, so `nosec` is a token.
# This matches the same way: the word, then whatever follows it.
_NOSEC = re.compile(r"#\s*nosec(?P<rest>.*)$", re.IGNORECASE)
_RULE = re.compile(r"\bB\d{3}\b")
# A reason is prose. A rule list is not a reason, so the rule ids are stripped
# before measuring what is left.
_MIN_REASON_CHARS = 8

# Files that manipulate nosec comments as data rather than carrying them.
# Each is listed with the reason it is exempt, because an unexplained exemption
# is how a guard's scope quietly shrinks.
CEILING = Path("config/immune/nosec_ceiling.txt")

EXEMPT = {
    "scripts/fix_bandit_issues.py": "rewrites nosec comments; the string literals are its input",
    "scripts/check_nosec_specificity.py": "this file, which necessarily contains the pattern",
}


@dataclass
class Suppression:
    path: str
    line: int
    text: str
    rules: list[str]
    reason: str

    def blocking_problems(self) -> list[str]:
        """Defects that must never land. Currently zero in this repository."""
        if not self.rules:
            return [
                "bare `# nosec` — silences every bandit rule on this line, "
                "including the vulnerability nobody has introduced yet"
            ]
        return []

    def unreasoned(self) -> bool:
        """Names its rule but not its justification. Ratcheted, not blocked."""
        return bool(self.rules) and len(self.reason) < _MIN_REASON_CHARS


def _tracked_python(root: Path) -> list[str]:
    proc = subprocess.run(  # noqa: S603,S607 - fixed argv, no shell
        ["git", "ls-files", "*.py"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    return sorted({line.strip() for line in proc.stdout.splitlines() if line.strip()})


def scan(root: Path = ROOT) -> tuple[list[Suppression], list[Suppression]]:
    """Return (all suppressions, the ones with problems)."""
    every: list[Suppression] = []
    for rel in _tracked_python(root):
        if rel in EXEMPT:
            continue
        try:
            lines = (root / rel).read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for number, line in enumerate(lines, 1):
            match = _NOSEC.search(line)
            if not match:
                continue
            rest = match.group("rest")
            # `# nosecure` is prose, not a suppression, and bandit agrees --
            # measured. Skip it rather than reporting a finding on English.
            if rest[:1].isalnum() or rest[:1] == "_":
                every.append(Suppression(rel, number, line.strip()[:120], [], ""))
                continue
            rules = _RULE.findall(rest)
            reason = _RULE.sub("", rest).strip(" :,-–—").strip()
            every.append(Suppression(rel, number, line.strip()[:120], rules, reason))
    return every, [s for s in every if s.blocking_problems()]


def read_ceiling(root: Path = ROOT) -> int | None:
    path = root / CEILING
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            try:
                return int(stripped)
            except ValueError:
                return None
    return None


def write_ceiling(count: int, root: Path = ROOT) -> None:
    path = root / CEILING
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Suppressions that name a bandit rule but give no written reason.\n"
        "# This number may go down and may never go up. Lower it in the same\n"
        "# commit that writes the reasons, so the diff shows the work.\n"
        f"{count}\n",
        encoding="utf-8",
    )


def _report(
    blocking: list[Suppression],
    unreasoned: list[Suppression],
    ceiling: int | None,
) -> bool:
    """Print the verdicts and return whether any of them fails the run.

    Split out of main() because ruff C901 scored main at 17 against a threshold
    of 10, and CodeFactor's public page independently flagged the same function
    -- two different tools, same finding, which is the whole argument for
    keeping a vendor cross-check rather than only replacing it.
    """
    failed = False

    if blocking:
        failed = True
        print("\nBARE SUPPRESSIONS — these silence rules nobody has chosen:\n", file=sys.stderr)
        for item in blocking:
            print(f"  {item.path}:{item.line}", file=sys.stderr)
            print(f"    {item.text}", file=sys.stderr)
            for problem in item.blocking_problems():
                print(f"    → {problem}", file=sys.stderr)

    if ceiling is None:
        print(
            f"\nNo ceiling recorded. Run --set-ceiling to freeze the current "
            f"{len(unreasoned)} unreasoned suppressions as a maximum."
        )
    elif len(unreasoned) > ceiling:
        failed = True
        print(
            f"\nUNREASONED SUPPRESSIONS ROSE: {len(unreasoned)} now, ceiling {ceiling}.\n"
            "Every `# nosec Bxxx` needs a reason a stranger can evaluate. Write it as\n"
            "`# nosec B602 - <why this line is safe>`.",
            file=sys.stderr,
        )
        for item in unreasoned[-8:]:
            print(f"  {item.path}:{item.line}  {item.text}", file=sys.stderr)
    elif len(unreasoned) < ceiling:
        print(
            f"\nunreasoned suppressions fell to {len(unreasoned)} (ceiling {ceiling}). "
            "Lower the ceiling in this commit: --set-ceiling"
        )
    else:
        print(f"\nunreasoned suppressions holding at the ceiling ({ceiling}).")

    return failed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--list", action="store_true", help="print every suppression found")
    parser.add_argument(
        "--set-ceiling",
        action="store_true",
        help="record the current unreasoned count as the new ceiling",
    )
    args = parser.parse_args(argv)

    every, blocking = scan()
    unreasoned = [s for s in every if s.unreasoned()]

    if args.list:
        for item in every:
            if item.blocking_problems():
                marker = "!!"
            elif item.unreasoned():
                marker = "--"
            else:
                marker = "ok"
            rules = ",".join(item.rules) or "(none)"
            print(f"  {marker} {item.path}:{item.line}  {rules}  {item.reason[:60]}")

    ceiling = read_ceiling()
    print(
        f"nosec suppressions: {len(every)} total — "
        f"{len(every) - len(unreasoned) - len(blocking)} scoped and explained, "
        f"{len(unreasoned)} scoped without a reason, {len(blocking)} bare"
    )
    for path, why in sorted(EXEMPT.items()):
        print(f"  exempt: {path} — {why}")

    if args.set_ceiling:
        if blocking:
            print("\nRefusing to set a ceiling while bare suppressions exist.", file=sys.stderr)
            return 2
        write_ceiling(len(unreasoned))
        print(f"\nceiling set to {len(unreasoned)}")
        return 0

    failed = _report(blocking, unreasoned, ceiling)

    if failed:
        return 1
    if not blocking:
        print("No suppression silences a rule it does not name.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
