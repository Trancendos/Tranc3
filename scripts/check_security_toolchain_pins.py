#!/usr/bin/env python3
"""Every semgrep invocation must use the version requirements-security.txt pins.

`.forgejo/workflows/security-scan.yml` carried this comment for a long time:

    Pinned to match requirements-security.txt / Makefile's security-install --
    that pin's accepted-risk notes (mcp==1.23.3, SECURITY.md) are only
    authoritative if every semgrep invocation actually uses the same version.

The condition was stated correctly and never measured. Measured 2026-10-04, the
four sites held four different versions: `requirements-security.txt` 1.178.0,
`Makefile` 1.172.0, the Forgejo SAST job 1.172.0, `.pre-commit-config.yaml`
v1.174.0. And the note the comment named as conditional on that agreement --
the mcp==1.23.3 accepted risk -- was by then false: the semgrep that
`requirements-security.txt` actually pinned already required `mcp==1.29.0`.
Whoever last read it was reading the 1.172.0 pin, which is why the file said
"verified: still true as of 1.172.0, the latest release" about a release seven
behind.

So this is not a tidiness check. A security toolchain pinned in four places is
four different scanners, and the accepted-risk notes that say which advisories
this estate has chosen to live with are written against exactly one of them.

The two pip paths now install `requirements-security.txt` directly, so they
cannot drift. The pre-commit hook cannot read a requirements file -- it takes a
git tag -- so it is pinned, and this check is what keeps it in step.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Relative, resolved against ROOT at call time so the tests can point the whole
# check at a synthetic tree.
REQUIREMENTS_NAME = "requirements-security.txt"
PRE_COMMIT_NAME = ".pre-commit-config.yaml"

# Files that must not restate a semgrep version: they install the requirements
# file instead. A reintroduced `semgrep==<v>` here is the drift this check exists
# for, even when the version happens to agree today.
MUST_NOT_PIN = (
    Path("Makefile"),
    Path(".forgejo/workflows/security-scan.yml"),
)

_REQUIREMENT = re.compile(r"^semgrep==([^\s;#]+)", re.MULTILINE)
_HOOK_REV = re.compile(
    r"-\s*repo:\s*https://github\.com/semgrep/pre-commit\s*\n\s*rev:\s*v?([^\s#]+)"
)
# Only a pip-style pin. The prose in these files discusses versions freely, and
# a check that cannot tell a sentence from an install command is not a check.
_RESTATED = re.compile(r"(?<![\w.-])semgrep==([^\s;#\\]+)")


def _required_version() -> str | None:
    requirements = ROOT / REQUIREMENTS_NAME
    if not requirements.is_file():
        return None
    found = _REQUIREMENT.findall(requirements.read_text(encoding="utf-8"))
    if len(found) != 1:
        return None
    return found[0]


def main() -> int:
    requirements = ROOT / REQUIREMENTS_NAME
    pre_commit = ROOT / PRE_COMMIT_NAME
    required = _required_version()
    if required is None:
        print(
            f"[ERROR] {REQUIREMENTS_NAME} does not pin exactly one "
            "`semgrep==<version>`. That file is the single source of truth for "
            "this toolchain, so this check cannot run without it."
        )
        return 1

    failures: list[str] = []

    for relative in MUST_NOT_PIN:
        path = ROOT / relative
        if not path.is_file():
            failures.append(f"{relative}: expected to exist, and it does not")
            continue
        for match in _RESTATED.finditer(path.read_text(encoding="utf-8")):
            # A commented-out line is still an instruction someone will uncomment.
            failures.append(
                f"{relative}: restates `semgrep=={match.group(1)}`. Install "
                f"`-r {REQUIREMENTS_NAME}` instead -- a second pin is a second "
                "scanner the accepted-risk notes were not written against."
            )

    if not pre_commit.is_file():
        failures.append(f"{PRE_COMMIT_NAME}: expected to exist, and it does not")
    else:
        revs = _HOOK_REV.findall(pre_commit.read_text(encoding="utf-8"))
        if len(revs) != 1:
            failures.append(
                f"{PRE_COMMIT_NAME}: expected exactly one "
                f"semgrep/pre-commit hook, found {len(revs)}"
            )
        elif revs[0] != required:
            failures.append(
                f"{PRE_COMMIT_NAME}: semgrep hook is at v{revs[0]}, "
                f"but {REQUIREMENTS_NAME} pins {required}. The hook takes a git "
                "tag and cannot read the requirements file, so it has to be "
                "bumped with it."
            )

    if failures:
        print(f"Security toolchain pins: FAILED ({len(failures)} finding(s))")
        for failure in failures:
            print(f"  [ERROR] {failure}")
        print(
            "\n        A security toolchain pinned in several places is several "
            "different\n        scanners, and this estate's accepted-risk notes "
            "are written against one."
        )
        return 1

    print(
        f"Security toolchain pins: PASSED — semgrep {required} in "
        f"{REQUIREMENTS_NAME}, matched by the pre-commit hook; "
        f"{len(MUST_NOT_PIN)} install site(s) restate no version"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
