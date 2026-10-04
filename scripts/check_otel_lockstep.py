#!/usr/bin/env python3
"""OpenTelemetry's two version series must not drift apart between files.

OpenTelemetry ships its core packages (`api`, `sdk`, `exporter-*`, `proto`)
on a `1.X.0` series and its instrumentation packages on a `0.YbZ` series, and
releases the two together. Pinning one half without the other is not a
version skew that degrades gracefully -- it is unsatisfiable, because
`opentelemetry-sdk 1.45.0` requires `opentelemetry-semantic-conventions
==0.66b0` while `opentelemetry-instrumentation-fastapi 0.65b0` requires
`==0.65b0`. pip resolves a requirements file atomically, so the install
produces nothing.

That happened: renovate bumped the four core pins in `requirements.txt` to
1.45.0 and left the five instrumentation pins at 0.65b0, which took the whole
test suite offline (no PyYAML -> estate_lint exited at import -> collection
INTERNALERROR). Fixing that file alone left the same unsatisfiable pair in
four worker requirements files whose Dockerfiles install them without
suppression, so those image builds would have failed the same way.

What this asserts is consistency, not an arithmetic relationship: every
requirements file that pins both halves must use the same (core,
instrumentation) pair as the root `requirements.txt`. The 21-step offset
between the series (1.44.0 <-> 0.65b0, 1.45.0 <-> 0.66b0) is a convention
upstream could change, so it is corroboration in this docstring rather than
the rule. Whether the root pair itself resolves is asserted by the install
step in `ci.yml`, which no longer suppresses failures -- an offline
consistency check and an online resolution check, each doing the half it can.

Usage:
    python scripts/check_otel_lockstep.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP = {".git", "node_modules", "target", ".venv", "venv"}

# The whole version token, not a prefix of it. Anchoring on `\d+\.\d+\.\d+`
# recorded `1.45.0rc1` and `1.45.0.post1` both as `1.45.0`, so a file pinning a
# pre-release against a release read as consistent with it. Capturing up to the
# first whitespace, `;` (an environment marker) or `#` (a comment) keeps the
# token intact and makes the comparison exact: a release and its own release
# candidate are different pins, and this check exists to notice exactly that
# kind of near-miss.
_VERSION = r"([^\s;#]+)"
_CORE = re.compile(r"^opentelemetry-(?:api|sdk|proto|exporter-[a-z0-9-]+)==" + _VERSION)
_INSTRUMENTATION = re.compile(r"^opentelemetry-instrumentation[a-z0-9-]*==" + _VERSION)


def _requirements_files() -> list:
    return sorted(
        p for p in ROOT.rglob("requirements*.txt") if not SKIP & set(p.relative_to(ROOT).parts)
    )


def _pins(path: Path) -> tuple:
    """The distinct core and instrumentation versions this file pins."""
    core, instrumentation = set(), set()
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if match := _CORE.match(line):
            core.add(match.group(1))
        elif match := _INSTRUMENTATION.match(line):
            instrumentation.add(match.group(1))
    return core, instrumentation


def main() -> int:
    files = _requirements_files()
    if not files:
        print("No requirements files found; this check has nothing to assert.")
        return 1

    root_core, root_instrumentation = _pins(ROOT / "requirements.txt")
    if not root_core or not root_instrumentation:
        print(
            "requirements.txt pins no OpenTelemetry core or instrumentation "
            "packages, so there is no reference pair to compare the rest "
            "against. A check with no reference reports the same PASSED as a "
            "consistent estate."
        )
        return 1

    problems = []
    for versions, label, path in (
        (root_core, "core", "requirements.txt"),
        (root_instrumentation, "instrumentation", "requirements.txt"),
    ):
        if len(versions) > 1:
            problems.append(
                f"  {path}: pins {len(versions)} different {label} versions "
                f"{sorted(versions)}; they ship as one release."
            )

    checked = 0
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        core, instrumentation = _pins(path)
        if not core or not instrumentation:
            continue  # pins only one half, or neither: nothing to compare
        checked += 1
        if len(core) > 1 or len(instrumentation) > 1:
            problems.append(
                f"  {rel}: pins more than one version within a series "
                f"(core {sorted(core)}, instrumentation {sorted(instrumentation)})."
            )
            continue
        if (core, instrumentation) != (root_core, root_instrumentation):
            problems.append(
                f"  {rel}: core {sorted(core)} with instrumentation "
                f"{sorted(instrumentation)}.\n"
                f"        requirements.txt uses core {sorted(root_core)} with "
                f"instrumentation {sorted(root_instrumentation)}.\n"
                f"        Mixing the series is unsatisfiable, not merely "
                f"inconsistent: pip\n        installs nothing from the file."
            )

    if problems:
        print(f"OpenTelemetry lockstep check: FAILED — {len(problems)} problem(s)")
        print("\n".join(problems))
        return 1

    print(
        f"OpenTelemetry lockstep check: PASSED — {checked} of {len(files)} "
        f"requirements files pin both series, all on core {sorted(root_core)[0]} "
        f"with instrumentation {sorted(root_instrumentation)[0]}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
