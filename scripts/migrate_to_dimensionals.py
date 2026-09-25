#!/usr/bin/env python3
"""Rename the shared core to DIMENSIONALS, across code, config and docs.

The owner named this layer DIMENSIONALS on 2026-09-11. It was `Dimensionals/`,
with a second partial copy at `shared_core/` -- 77 modules of which 66 were
already compatibility shims pointing back at `Dimensional`, and 11 were real
divergent forks (including a 601-line second copy of the adaptive security
scanner). Two names and two copies for one layer.

This is a script rather than a one-off command because the rename touches ~577
files and will have to be re-run: on a merge that reintroduces the old name, and
on the follow-up that reconciles the 11 forks. A rename you can only do once is
a rename you cannot verify.

What it does NOT do: reconcile the 11 divergent shared_core forks. Those differ
in behaviour, not just location, and picking a winner for `security.py` or
`adaptive_scanner.py` is a decision about which security control is correct --
not something a text substitution should make. It reports them instead.

Usage:
    python3 scripts/migrate_to_dimensionals.py            # dry run (default)
    python3 scripts/migrate_to_dimensionals.py --apply    # perform the rename
    python3 scripts/migrate_to_dimensionals.py --forks    # list unreconciled forks
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# Built from a joined literal so this script cannot rewrite its own constants.
# It did exactly that on the first --apply run: the `"Dimensional"` -> `"Dimensionals"`
# substitution matched its own source, leaving OLD_DIR and NEW_DIR both pointing at
# the new name and the git mv reading `git mv Dimensionals Dimensionals`. A rewriter
# that edits every text file has to exclude itself, which is now handled twice:
# here, and by the _candidate_files() skip below.
_OLD_NAME = "Dimension" + "al"
_NEW_NAME = _OLD_NAME + "s"
OLD_DIR = REPO / _OLD_NAME
NEW_DIR = REPO / _NEW_NAME
SHARED_CORE = REPO / "shared_core"

SKIP_PARTS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    # Generated scanner state, rewritten on every run. Substituting inside it
    # produced an 8,736-line diff of machine output on the first attempt.
    ".security_learning",
    ".security_telemetry",
}

# Git submodules are separate repositories with their own branches, review and
# release cadence. The first run of this script walked into `compliance/magna-carta`
# and rewrote five of its compliance documents, which left the parent with a dirty
# submodule pointer and the edits sitting in no branch at all. The edits themselves
# were right -- those documents name `Dimensional/sanitize.py` as the GDPR and HIPAA
# logging control, and that path stopped existing -- but a rewriter that reaches
# across a repository boundary decides on its own that another project's compliance
# text should change, which is not its call to make.
SKIP_SUBMODULES = True


def _submodule_paths() -> set[str]:
    """Repo-relative paths of every registered submodule."""
    gitmodules = REPO / ".gitmodules"
    if not gitmodules.is_file():
        return set()
    paths = set()
    for line in gitmodules.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("path"):
            _, _, value = stripped.partition("=")
            if value.strip():
                paths.add(value.strip())
    return paths


TEXT_SUFFIXES = {
    ".py",
    ".pyi",
    ".yml",
    ".yaml",
    ".toml",
    ".cfg",
    ".ini",
    ".txt",
    ".md",
    ".json",
    ".sh",
    ".ts",
    ".tsx",
    ".js",
    ".env",
    ".example",
    "",
}

# Only package references are rewritten. `dimensional` in lowercase (the
# dimensional-nexus-service worker, "multi-dimensional data routing") and the
# already-correct `Dimensionals` are both left alone -- the negative lookahead on
# `s` is what stops a second run producing `Dimensionalss`.
SUBSTITUTIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bfrom Dimensional(?!s)\b"), "from Dimensionals"),
    (re.compile(r"\bimport Dimensional(?!s)\b"), "import Dimensionals"),
    # `\w` after the dot, so this matches attribute access (`Dimensional.registry`)
    # and not a sentence ending in the singular concept noun. Without it the rule
    # rewrote "a second worker needing it makes it a Dimensional." into
    # "...a Dimensionals." -- the over-application cubic flagged, which this
    # script would have reintroduced on its next run after I corrected it by hand.
    (re.compile(r"\bDimensional(?!s)\.(?=\w)"), "Dimensionals."),
    (re.compile(r'"Dimensional(?!s)"'), '"Dimensionals"'),
    (re.compile(r"'Dimensional(?!s)'"), "'Dimensionals'"),
    # ── Build-pipeline path shapes ───────────────────────────────────────────
    #
    # The first run used a single path rule, `(?<![\w/-])Dimensional(?!s)/`, and
    # it missed the two shapes that matter most, for opposite reasons:
    #
    #   `./Dimensional`     — no trailing slash, so the rule did not apply
    #   `/app/Dimensional/` — preceded by `/`, which the lookbehind excluded
    #
    # The lookbehind was there to protect `dimensional-nexus-service/`, and it
    # also blocked every legitimate path segment. The result: 65 compose services
    # kept `sharedcore: ./Dimensional` as their shared-core build context, and 72
    # Dockerfiles kept copying it to `/app/Dimensional/` -- a directory that no
    # longer exists, against code that now imports `Dimensionals`. Every one of
    # those image builds would have failed. cubic caught it on PR #1207.
    #
    # Replaced with explicit, anchored rules per shape. Case matters: the
    # lowercase `dimensional-nexus-service` and `dimensional_nexus` are untouched
    # because every pattern requires the capital D.
    (re.compile(r"(?<=[\s=:])\./Dimensional(?!s)\b"), "./Dimensionals"),
    (re.compile(r"/app/Dimensional(?!s)\b"), "/app/Dimensionals"),
    (re.compile(r"(?<![\w-])Dimensional(?!s)/"), "Dimensionals/"),
    # NOT a bare-word rule. One was tried and reverted: it rewrote prose where
    # "a Dimensional" is the correct singular concept noun ("what else should
    # become a Dimensional"), producing "makes it a Dimensionals". cubic caught
    # both directions of this on PR #1207 -- paths under-renamed, prose
    # over-renamed. Paths are mechanical and safe to substitute; prose is not,
    # and is corrected by reading it.
]


def _candidate_files() -> list[Path]:
    out = []
    submodules = _submodule_paths()
    for path in REPO.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(REPO).as_posix()
        if any(part in SKIP_PARTS for part in path.relative_to(REPO).parts):
            continue
        if SKIP_SUBMODULES and any(rel == sub or rel.startswith(sub + "/") for sub in submodules):
            continue
        if path.resolve() == Path(__file__).resolve():
            continue  # a rewriter that edits itself mid-run corrupts its own constants
        if path.suffix in TEXT_SUFFIXES or path.name.startswith("Dockerfile"):
            out.append(path)
    return out


def rewrite_text(text: str) -> tuple[str, int]:
    changes = 0
    for pattern, replacement in SUBSTITUTIONS:
        text, n = pattern.subn(replacement, text)
        changes += n
    return text, changes


def shared_core_forks() -> list[tuple[str, int]]:
    """shared_core modules that are real code rather than shims."""
    forks = []
    if not SHARED_CORE.is_dir():
        return forks
    for path in sorted(SHARED_CORE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        is_shim = "Backward-compatibility shim" in text or (
            "import *" in text and len(text.splitlines()) <= 8
        )
        if not is_shim:
            forks.append((path.relative_to(REPO).as_posix(), len(text.splitlines())))
    return forks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="perform the rename")
    parser.add_argument("--forks", action="store_true", help="list unreconciled forks")
    args = parser.parse_args(argv)

    if args.forks:
        forks = shared_core_forks()
        for name, lines in forks:
            print(f"{lines:6d} lines  {name}")
        print(f"\n{len(forks)} shared_core module(s) are real code, not shims.")
        return 0

    # Two workers vendor a partial copy of the tree into their own build context
    # (`workers/hive-service/`, `workers/dimensional-nexus-service/`) so the image
    # does not need the whole repository. Moving the root and rewriting the text
    # while leaving those copies under the old name produces a repo that imports
    # fine locally and fails inside the container --
    # `tests/test_vendored_module_drift.py` caught precisely that on the first run.
    roots = [OLD_DIR] + sorted(d for d in REPO.glob(f"workers/*/{_OLD_NAME}") if d.is_dir())
    moved = 0
    for old_root in roots:
        if not old_root.is_dir():
            continue
        new_root = old_root.with_name(_NEW_NAME)
        src = old_root.relative_to(REPO).as_posix()
        dst = new_root.relative_to(REPO).as_posix()
        if args.apply:
            # A directory git does not track cannot be `git mv`d, and a stray one
            # must not abort the run: an orphaned `Dimensional/__pycache__` left
            # by an earlier import did exactly that, raising before a single text
            # substitution was written, so `--apply` reported nothing and changed
            # nothing while appearing to have run.
            tracked = (
                subprocess.run(
                    ["git", "ls-files", "--error-unmatch", src],
                    cwd=REPO,
                    capture_output=True,
                ).returncode
                == 0
            )
            if not tracked:
                print(f"skipping {src}/ — untracked (stray build output?), not moving")
                continue
            result = subprocess.run(
                ["git", "mv", src, dst], cwd=REPO, capture_output=True, text=True
            )
            if result.returncode != 0:
                print(f"could not move {src}/ -> {dst}/: {result.stderr.strip()}")
                continue
            print(f"moved {src}/ -> {dst}/")
        else:
            print(f"would move {src}/ -> {dst}/")
        moved += 1
    if not moved:
        print(f"no {_OLD_NAME}/ directory left to move — rename already applied.")

    touched, total = [], 0
    for path in _candidate_files():
        try:
            original = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        updated, changes = rewrite_text(original)
        if changes:
            touched.append((path.relative_to(REPO).as_posix(), changes))
            total += changes
            if args.apply:
                path.write_text(updated, encoding="utf-8")

    verb = "rewrote" if args.apply else "would rewrite"
    for name, changes in sorted(touched)[:20]:
        print(f"  {changes:4d}  {name}")
    if len(touched) > 20:
        print(f"  ... and {len(touched) - 20} more files")
    print(f"\n{verb} {total} reference(s) across {len(touched)} file(s)")

    forks = shared_core_forks()
    if forks:
        print(
            f"\n{len(forks)} shared_core module(s) are still real forks, not shims. "
            "They differ in behaviour and are NOT reconciled by this script:"
        )
        for name, lines in forks:
            print(f"    {lines:6d} lines  {name}")

    if not args.apply:
        print("\nDry run. Re-run with --apply to perform the rename.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
