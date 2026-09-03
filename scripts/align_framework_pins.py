#!/usr/bin/env python3
"""Hold the shared web-framework stack at one version across every requirements file.

THE PROBLEM THIS SOLVES

Every FastAPI worker in the estate declares the same four or five packages —
`fastapi`, `starlette`, `pydantic`, `uvicorn`, `redis` — in its own
`requirements*.txt`. Nothing keeps those declarations in step, so they drift:
at the time this script was written the estate held 75 files on
`fastapi==0.136.3` and 11 on `0.141.1`, 52 on `pydantic==2.11.5` and 11 on
`2.13.4`, and *five* different `uvicorn` pins (`0.30.6`, `0.34.3`, `0.48.0`,
`0.52.1`, plus the `[standard]` variants of each).

Drift on this particular stack is worse than drift in general, because these
packages are a single coupled unit: `fastapi` constrains `starlette` and
`pydantic`, and the repo pins `starlette` explicitly *because* a transitively
resolved version was once vulnerable (see the note in
`workers/vrar3d/requirements.txt`). Letting the three slide independently is
how you end up with a worker whose pinned `starlette` no longer satisfies its
pinned `fastapi` — a failure that only shows up at image build time.

WHY THIS EXISTS RATHER THAN 300 DEPENDABOT MERGES

Dependabot sees each worker directory as a separate ecosystem, so one upstream
release becomes one PR *per directory*: a single `fastapi` release opened ~75
PRs. Merging them one at a time would mean ~300 CI runs for five distinct
version changes, which runs straight into the rate limits that
`CLAUDE.md` names as the reason for the estate's zero-cost, self-hosted-by-
default posture. This script applies the same five changes in one pass, so the
review and the CI cost are proportional to the decision, not to the number of
directories that happen to restate it.

WHAT IT WILL AND WILL NOT TOUCH

It rewrites the version of an **exact `==` pin** of a canonical package, and
nothing else. Extras are preserved (`uvicorn[standard]==0.30.6` becomes
`uvicorn[standard]==0.52.4`, not `uvicorn==0.52.4`), as are inline comments,
surrounding lines, and line endings.

A non-`==` specifier is reported but never rewritten. The estate's convention
is exact pins ("# Exact-pinned — Do NOT use >= or ~=") and
`scripts/pin_worker_requirements.py` is the tool that converts a floating
specifier into an exact one; deciding what a `>=` line should become is that
script's job, not this one's, and silently collapsing a deliberate range here
would hide the fact that the file is off-convention.

Packages outside `CANONICAL` are never touched, so a worker keeps its own
pins for everything that is genuinely its own.

CHOOSING THE CANONICAL VERSIONS

Each value below is the newest stable release on PyPI, and every one of them
ships a universal `py3-none-any` wheel — so they impose no constraint on the
in-flight 3.11 → 3.14 interpreter migration, which is deliberately staged
elsewhere (`docs/architecture/PYTHON-3.14-UPGRADE-ASSESSMENT.md` §3 explains
why that one is *not* a mass edit). The set is resolver-checked as a unit:
`fastapi==0.141.1` requires `starlette>=0.46.0` and `pydantic>=2.9.0`, which
the pins below satisfy.

Bumping the stack means editing `CANONICAL` and re-running with `--write`.

Usage:
    python scripts/align_framework_pins.py            # report only
    python scripts/align_framework_pins.py --write    # apply
    python scripts/align_framework_pins.py --check    # CI guard, exit 1 on drift
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# The shared web-framework stack. Keep this the single place the estate's
# version of each of these is decided.
CANONICAL: dict[str, str] = {
    "fastapi": "0.141.1",
    "starlette": "1.6.0",
    "pydantic": "2.13.5",
    "uvicorn": "0.52.4",
    "redis": "8.1.0",
}

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "site-packages"}

# name[extras] <op> version [; markers] [# comment]
_REQ_LINE = re.compile(
    r"""^(?P<indent>\s*)
        (?P<name>[A-Za-z0-9._-]+)
        (?P<extras>\[[^\]]*\])?
        (?P<space>\s*)
        (?P<op>==|>=|<=|~=|!=|>|<)
        (?P<vspace>\s*)
        (?P<version>[^\s;#]+)
        (?P<rest>.*)$""",
    re.X,
)


def _canonical_key(name: str) -> str | None:
    """Return the CANONICAL key this requirement name refers to, if any.

    Distribution names are case-insensitive and treat `-`, `_` and `.` as
    equivalent (PEP 503), so `Fast-API` and `fastapi` are the same project.
    """
    normalised = re.sub(r"[-_.]+", "-", name).lower()
    return normalised if normalised in CANONICAL else None


def submodule_paths() -> set[Path]:
    """Absolute paths of every git submodule, read from .gitmodules.

    Submodules are other repositories that happen to be checked out inside
    this working tree. Rewriting a file in one produces a change this repo
    cannot commit — it would show up only as a moved submodule pointer — and
    `--check` would then fail CI over a file this repo does not own. The
    estate has two (`compliance/magna-carta`, `workers/cranbania`), and while
    neither declares a canonical package today, nothing stops one from doing
    so tomorrow, so the boundary is enforced rather than assumed.
    """
    gitmodules = REPO_ROOT / ".gitmodules"
    if not gitmodules.is_file():
        return set()
    return {
        REPO_ROOT / match.strip()
        for match in re.findall(
            r"^\s*path\s*=\s*(.+)$", gitmodules.read_text(encoding="utf-8"), re.M
        )
    }


def requirements_files() -> list[Path]:
    submodules = submodule_paths()

    def in_submodule(path: Path) -> bool:
        return any(sub == path or sub in path.parents for sub in submodules)

    found = [
        p
        for p in REPO_ROOT.rglob("requirements*.txt")
        if not (SKIP_DIRS & set(p.parts)) and p.is_file() and not in_submodule(p)
    ]
    return sorted(found)


class Change:
    __slots__ = ("path", "lineno", "before", "after")

    def __init__(self, path: Path, lineno: int, before: str, after: str) -> None:
        self.path = path
        self.lineno = lineno
        self.before = before
        self.after = after


def align_text(text: str, path: Path) -> tuple[str, list[Change], list[str]]:
    """Return (new_text, changes, notes) for one requirements file.

    Rewrites only the version field of an exact pin of a canonical package.
    Everything else in the line — indentation, extras, spacing around the
    operator, environment markers, trailing comment — is carried through
    untouched, so the diff is confined to the number itself.
    """
    lines = text.splitlines(keepends=True)
    changes: list[Change] = []
    notes: list[str] = []

    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _REQ_LINE.match(line.rstrip("\r\n"))
        if not match:
            continue
        key = _canonical_key(match.group("name"))
        if key is None:
            continue

        if match.group("op") != "==":
            notes.append(
                f"{path.relative_to(REPO_ROOT)}:{index + 1}: `{stripped.rstrip()}` uses "
                f"`{match.group('op')}`, not an exact pin — left alone. Convert it with "
                f"scripts/pin_worker_requirements.py rather than here."
            )
            continue

        target = CANONICAL[key]
        if match.group("version") == target:
            continue

        ending = line[len(line.rstrip("\r\n")) :]
        rebuilt = (
            f"{match.group('indent')}{match.group('name')}{match.group('extras') or ''}"
            f"{match.group('space')}=={match.group('vspace')}{target}{match.group('rest')}"
            f"{ending}"
        )
        changes.append(Change(path, index + 1, line.rstrip("\r\n"), rebuilt.rstrip("\r\n")))
        lines[index] = rebuilt

    return "".join(lines), changes, notes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="apply the changes")
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if any file is off the canonical set (for CI)",
    )
    args = parser.parse_args()

    # Combined, these contradict each other: --write makes the estate canonical
    # and --check reports on what was *not* canonical, so `--write --check`
    # would apply every fix and then exit 1 for having had something to fix.
    # A CI job that reached for both would fail precisely when it succeeded.
    if args.write and args.check:
        parser.error("--write and --check are mutually exclusive: --write fixes, --check reports")

    all_changes: list[Change] = []
    all_notes: list[str] = []
    touched: list[Path] = []

    for path in requirements_files():
        original = path.read_text(encoding="utf-8")
        updated, changes, notes = align_text(original, path)
        all_notes.extend(notes)
        if not changes:
            continue
        all_changes.extend(changes)
        touched.append(path)
        if args.write:
            path.write_text(updated, encoding="utf-8")

    for note in all_notes:
        print(f"[NOTE]  {note}")

    for change in all_changes:
        rel = change.path.relative_to(REPO_ROOT)
        # Deliberately not .strip()ed: indentation and spacing around the
        # operator are meant to survive the rewrite, so the log has to be able
        # to show it if they ever stop doing so.
        print(f"{rel}:{change.lineno}: {change.before}  ->  {change.after}")

    verb = "Aligned" if args.write else "Would align"
    print(
        f"\n{verb} {len(all_changes)} pin(s) across {len(touched)} file(s); "
        f"canonical set: " + ", ".join(f"{k}=={v}" for k, v in sorted(CANONICAL.items()))
    )

    if args.check and all_changes:
        print(
            "\nFramework pin check: FAILED — the files above disagree with the canonical "
            "set in scripts/align_framework_pins.py. Run it with --write.",
            file=sys.stderr,
        )
        return 1
    if args.check:
        print("Framework pin check: PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
