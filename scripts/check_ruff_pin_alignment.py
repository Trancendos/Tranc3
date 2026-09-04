#!/usr/bin/env python3
"""Keep every surface that runs ruff on this tree pinned to the same ruff.

WHY THIS EXISTS

`production-gate.yml` states the intent in its own comment:

    ruff matches the 0.15.8 already pinned in ci.yml, python.yml and test.yml,
    so the gate and the lint checks cannot disagree about what passes.

That was true across the workflows and false across the full lint surface.
`.pre-commit-config.yaml` pinned `ruff-pre-commit` at v0.16.4 while all four
workflows installed `ruff==0.15.8` -- two different formatters governing one
tree, one of them running on every local commit and as a pull-request status
via pre-commit.ci.

The divergence was real and measurable: ruff 0.16.x formats Python inside
Markdown fences and 0.15.8 does not, a ten-file difference on this repository.
It had not yet bitten only because the ruff hooks are typed to Python, so `.md`
never reached them -- a latent split held closed by an unrelated detail, which
is not a guarantee.

It did bite during the audit that found it: an ambient ruff 0.16.5 reported ten
formatting failures on `main` that the pinned 0.15.8 does not, and those were
nearly filed as real.

WHY THE FIRST VERSION OF THIS CHECK WAS ITSELF THE DEFECT IT HUNTS

The original implementation scanned `.github/workflows/*.yml` and
`.forgejo/workflows/*.yml` for the literal `ruff==<version>`, and skipped --
silently, with `if not found: continue` -- any file that had no such string. So
it reported "PASSED, 5 surfaces, all on ruff 0.15.8" while the estate actually
carried five more ruff surfaces it had never looked at:

  * `.forgejo/workflows/ci.yml`            `uv pip install --system ruff`
  * `.forgejo/workflows/nightly.yml`       `pip install ruff mypy`
  * `.forgejo/workflows/security-scan.yml` `pip install ... ruff ...`
  * `.woodpecker.yml`                      `pip install --quiet ruff`  (whole
    file unscanned -- it is not under either workflows directory)
  * `deploy/forgejo/runner.Dockerfile`     `ruff==0.4.4`, a THIRD version, and
    the image the Forgejo jobs above would have run inside

Four of those install whatever ruff is latest on the day the job runs, which is
the split gate this check exists to prevent, arriving by a route the check was
structurally unable to see. A check that reports alignment across files it did
not read is worse than no check, because it is believed.

WHAT IT CHECKS NOW

Across GitHub workflows, Forgejo workflows, Woodpecker pipelines and
Dockerfiles:

  1. Every command that INSTALLS ruff must pin it exactly (`ruff==X.Y.Z`).
     An unpinned install is a failure, not a skip.
  2. Every pinned version, plus the `rev:` of the `ruff-pre-commit` repo in
     `.pre-commit-config.yaml`, must resolve to one version. The pre-commit rev
     is written `vX.Y.Z` and a pip pin `X.Y.Z`; the leading `v` is the only
     difference tolerated.
  3. A file that INVOKES ruff but never installs it is a failure too: it runs
     whatever the runner image happens to carry, which is the same unpinned
     surface wearing a different hat.

Files that only mention ruff in prose or a step name are not surfaces and are
not reported. `scripts/security_scan.sh` is deliberately out of scope: it runs
ruff only `--exit-zero` when one is already on PATH, gates nothing, and pinning
it would mean installing a second ruff for a warn-only local helper.

It fails closed. A file it cannot read is a failure, never a pass.

Usage:
    python scripts/check_ruff_pin_alignment.py      # exit 1 on drift
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PRE_COMMIT = REPO_ROOT / ".pre-commit-config.yaml"

# Every place a ruff can be installed or invoked on this estate. `.yaml` is
# scanned alongside `.yml` because GitHub, Forgejo and Woodpecker all accept it
# and a renamed file must not fall out of the gate.
SCAN_GLOBS: tuple[str, ...] = (
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    ".forgejo/workflows/*.yml",
    ".forgejo/workflows/*.yaml",
    ".woodpecker.yml",
    ".woodpecker.yaml",
    ".woodpecker/*.yml",
    ".woodpecker/*.yaml",
    "**/*Dockerfile*",
)

# Vendored trees are not this estate's lint surface, and walking them is the
# difference between a check that runs in CI and one that times out in it.
EXCLUDED_DIRS = frozenset({".git", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache"})

# A command that adds a package to an environment. Anchored on the verb so a
# bare package list on a continuation line is only read as an install once the
# continuation has been joined back onto the verb that owns it.
INSTALL_VERB = re.compile(
    r"""(?:uv\s+pip\s+install|uv\s+tool\s+install|pipx\s+install"""
    r"""|python3?\s+-m\s+pip\s+install|pip3?\s+install|poetry\s+add)\b"""
)

# `ruff` as its own token: not `ruff-pre-commit`, not `logs/ruff-results.json`,
# not `ruff-lint` (a step name). Captures an exact pin when one is present.
RUFF_TOKEN = re.compile(r"""(?<![\w.\-/])ruff(?![\w\-])(?:\s*==\s*(?P<pin>\d+\.\d+(?:\.\d+)?))?""")

# A segment that runs the ruff binary rather than installing it. The leading
# prefix absorbs YAML's two ways of introducing a command -- `- run: ruff check`
# and a bare line inside a `run: |` block -- so an invocation is recognised in
# both without `- name: ruff-lint results` counting as one.
RUFF_INVOCATION = re.compile(r"""^\s*(?:-\s*)?(?:[\w.\-]+:\s*)?ruff(?![\w\-])""")

# The ruff-pre-commit repo block's `rev:`. Anchored to the repo URL so an
# unrelated `rev:` in the file cannot be mistaken for ruff's.
PRE_COMMIT_REV = re.compile(
    r"""-\s*repo:\s*https://github\.com/astral-sh/ruff-pre-commit\s*\n(?:\s*#.*\n)*\s*rev:\s*v?(\d+\.\d+\.\d+)""",
)

# `#` at line start or after whitespace opens a comment in YAML and Dockerfiles.
COMMENT = re.compile(r"(?:^|\s)#")

# Shell separators. Splitting on these keeps `pip install "ruff==0.15.8" &&
# ruff check .` from reading its own invocation as a second, unpinned install.
SEPARATOR = re.compile(r"&&|\|\||[;|]")


def _fail(msg: str) -> None:
    print(f"FAIL {msg}", file=sys.stderr)


def _logical_lines(text: str) -> list[tuple[str, list[tuple[int, int]]]]:
    """Comment-stripped lines with `\\` continuations joined, plus a line map.

    The map is `[(offset, line number), ...]` marking where each physical line
    begins inside the joined text, so a finding inside a 25-line `RUN pip
    install ... \\` block is reported against the line that actually names
    ruff rather than the line the block opens on.
    """
    joined: list[tuple[str, list[tuple[int, int]]]] = []
    buffer = ""
    line_map: list[tuple[int, int]] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        match = COMMENT.search(raw)
        line = (raw[: match.start()] if match else raw).rstrip()
        line_map.append((len(buffer), number))
        if line.endswith("\\"):
            buffer += line[:-1] + " "
            continue
        buffer += line
        joined.append((buffer, line_map))
        buffer = ""
        line_map = []
    if buffer:
        joined.append((buffer, line_map))
    return joined


def _line_at(line_map: list[tuple[int, int]], offset: int) -> int:
    """The physical line number that `offset` in the joined text came from."""
    number = line_map[0][1]
    for start, candidate in line_map:
        if start > offset:
            break
        number = candidate
    return number


def _segments(line: str):
    """Shell segments of a logical line, with each one's offset into it."""
    position = 0
    for match in SEPARATOR.finditer(line):
        yield position, line[position : match.start()]
        position = match.end()
    yield position, line[position:]


def scan_file(path: Path, rel: str) -> tuple[list[tuple[str, str | None]], bool]:
    """Ruff installs found in one file, and whether it also invokes ruff.

    Each install is `(location, version or None)`; None means the install did
    not pin a version.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        _fail(f"{rel} could not be read ({exc.__class__.__name__})")
        raise SystemExit(1) from exc

    installs: list[tuple[str, str | None]] = []
    invokes = False
    for line, line_map in _logical_lines(text):
        for offset, segment in _segments(line):
            verb = INSTALL_VERB.search(segment)
            if verb:
                for token in RUFF_TOKEN.finditer(segment, verb.end()):
                    number = _line_at(line_map, offset + token.start())
                    installs.append((f"{rel}:{number}", token.group("pin")))
            elif RUFF_INVOCATION.search(segment):
                invokes = True
    return installs, invokes


def ruff_surfaces() -> tuple[dict[str, str], list[str]]:
    """Map "<location>" -> pinned version, plus a list of problems found."""
    pins: dict[str, str] = {}
    problems: list[str] = []
    seen: set[Path] = set()

    for pattern in SCAN_GLOBS:
        for path in sorted(REPO_ROOT.glob(pattern)):
            if not path.is_file() or path in seen:
                continue
            if EXCLUDED_DIRS.intersection(path.parts):
                continue
            seen.add(path)
            rel = str(path.relative_to(REPO_ROOT))
            installs, invokes = scan_file(path, rel)

            for location, version in installs:
                if version is None:
                    problems.append(
                        f"{location} installs ruff without pinning a version — it will "
                        "run whatever ruff is latest on the day the job runs"
                    )
                else:
                    pins[location] = version

            if invokes and not installs:
                problems.append(
                    f"{rel} runs ruff but never installs it — it inherits whatever "
                    "version the runner image happens to carry"
                )

    return pins, problems


def pre_commit_pin() -> str:
    """The ruff version `.pre-commit-config.yaml` resolves to."""
    if not PRE_COMMIT.is_file():
        _fail(".pre-commit-config.yaml is missing")
        raise SystemExit(1)
    text = PRE_COMMIT.read_text(encoding="utf-8")
    match = PRE_COMMIT_REV.search(text)
    if not match:
        _fail(
            ".pre-commit-config.yaml has no readable rev for astral-sh/ruff-pre-commit "
            "-- cannot verify it agrees with the workflows"
        )
        raise SystemExit(1)
    return match.group(1)


def main() -> int:
    pins, problems = ruff_surfaces()
    if not pins and not problems:
        _fail("no scanned file installs ruff -- expected at least one `ruff==<version>`")
        return 1

    hook = pre_commit_pin()
    surfaces = dict(pins)
    surfaces[".pre-commit-config.yaml"] = hook

    width = max(len(name) for name in surfaces)
    for name in sorted(surfaces):
        print(f"  {name:{width}}  ruff {surfaces[name]}")

    versions = sorted(set(surfaces.values()))
    if len(versions) > 1:
        problems.append(
            "ruff is pinned to more than one version across the surfaces that lint "
            f"this tree: {', '.join(versions)}"
        )

    if problems:
        print()
        for problem in problems:
            _fail(problem)
        print(
            "\nTwo ruff versions formatting one tree is a split gate: a file that "
            "pre-commit rewrites can be rejected by CI, and vice versa. An unpinned "
            "install is the same split with the second version chosen for you at run "
            "time. Pin every surface above to one version -- pip pins are written "
            "`ruff==X.Y.Z` and the pre-commit rev `vX.Y.Z`.",
            file=sys.stderr,
        )
        return 1

    print(f"\nRuff pin alignment: PASSED — {len(surfaces)} surfaces, all on ruff {versions[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
