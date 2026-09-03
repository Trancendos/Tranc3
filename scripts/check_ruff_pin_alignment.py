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

WHAT IT CHECKS

Every `ruff==<version>` pinned in a workflow, and the `rev:` of the
`ruff-pre-commit` repo in `.pre-commit-config.yaml`, resolve to one version.
The pre-commit rev is written `vX.Y.Z` and the workflow pin `X.Y.Z`; the
leading `v` is the only difference tolerated.

It fails closed. A file it cannot parse, or a ruff surface it cannot find a
version in, is a failure -- never a pass. A check that reports alignment across
files it did not actually read is worse than no check.

Usage:
    python scripts/check_ruff_pin_alignment.py      # exit 1 on drift
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PRE_COMMIT = REPO_ROOT / ".pre-commit-config.yaml"
WORKFLOW_DIRS = (REPO_ROOT / ".github" / "workflows", REPO_ROOT / ".forgejo" / "workflows")

# `pip install "ruff==0.15.8"`, `pip install ruff==0.15.8 mypy`, etc.
WORKFLOW_PIN = re.compile(r"""ruff==(\d+\.\d+\.\d+)""")

# The ruff-pre-commit repo block's `rev:`. Anchored to the repo URL so an
# unrelated `rev:` in the file cannot be mistaken for ruff's.
PRE_COMMIT_REV = re.compile(
    r"""-\s*repo:\s*https://github\.com/astral-sh/ruff-pre-commit\s*\n(?:\s*#.*\n)*\s*rev:\s*v?(\d+\.\d+\.\d+)""",
)


def _fail(msg: str) -> None:
    print(f"FAIL {msg}", file=sys.stderr)


def workflow_pins() -> dict[str, str]:
    """Map "<relative path>" -> pinned ruff version, for every workflow that pins one."""
    pins: dict[str, str] = {}
    for directory in WORKFLOW_DIRS:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.yml")):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as exc:
                _fail(f"{path.relative_to(REPO_ROOT)} could not be read ({exc.__class__.__name__})")
                raise SystemExit(1) from exc
            found = set(WORKFLOW_PIN.findall(text))
            if not found:
                continue
            rel = str(path.relative_to(REPO_ROOT))
            if len(found) > 1:
                _fail(f"{rel} pins more than one ruff version: {', '.join(sorted(found))}")
                raise SystemExit(1)
            pins[rel] = found.pop()
    return pins


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
    pins = workflow_pins()
    if not pins:
        _fail("no workflow pins ruff -- expected at least one `ruff==<version>`")
        return 1

    hook = pre_commit_pin()
    surfaces = dict(pins)
    surfaces[".pre-commit-config.yaml"] = hook

    versions = sorted(set(surfaces.values()))
    width = max(len(name) for name in surfaces)
    for name in sorted(surfaces):
        print(f"  {name:{width}}  ruff {surfaces[name]}")

    if len(versions) > 1:
        print()
        _fail(
            "ruff is pinned to more than one version across the surfaces that lint "
            f"this tree: {', '.join(versions)}"
        )
        print(
            "\nTwo ruff versions formatting one tree is a split gate: a file that "
            "pre-commit rewrites can be rejected by CI, and vice versa. Move every "
            "surface above to one version -- workflow pins are written `ruff==X.Y.Z` "
            "and the pre-commit rev `vX.Y.Z`.",
            file=sys.stderr,
        )
        return 1

    print(f"\nRuff pin alignment: PASSED — {len(surfaces)} surfaces, all on ruff {versions[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
