#!/usr/bin/env python3
"""Report which workers are ready to move to Python 3.14, and what blocks the rest.

Stage 2 of docs/architecture/PYTHON-3.14-UPGRADE-ASSESSMENT.md called out that
dependency risk there was "reasoned from known release-cadence patterns, not
from an actual pip install against 3.14". This script is what turns that into
verified fact: it reads every worker's pinned requirements and asks PyPI, for
each exact pinned version, whether an artifact usable by CPython 3.14 on
linux/x86_64 actually exists.

"Usable on 3.14/linux-x86_64" means one of:
  - a pure-Python wheel (py3-none-any) — interpreter-independent
  - a cp314 manylinux/musllinux x86_64 wheel
  - an abi3 manylinux/musllinux x86_64 wheel (stable ABI, forward-compatible)

Anything else is reported as a blocker, together with the lowest stable version
that *would* work — which is the actual remediation step, not just a warning.

The linux/x86_64 restriction is deliberate: every worker ships as a
linux/amd64 `python:*-slim` container, so a macOS or Windows cp314 wheel proves
nothing about whether the image will build.

Network access to pypi.org is required. Exit code is 0 when every worker is
ready, 1 when at least one is blocked — so this can gate a rollout batch in CI
if desired, but it is not wired into any workflow by default (the upgrade is a
staged project, not a merge gate).

Usage:
    python scripts/check_python314_readiness.py              # all workers
    python scripts/check_python314_readiness.py analytics-service cache-service
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKERS_DIR = REPO_ROOT / "workers"

# Requirements filenames seen across the worker estate (they are not consistent).
REQUIREMENTS_NAMES = ("requirements-worker.txt", "requirements.txt")

_PRERELEASE = re.compile(r"(dev|rc|a|b)\d+$")

_cache: Dict[str, Optional[dict]] = {}


def _pypi(package: str) -> Optional[dict]:
    if package in _cache:
        return _cache[package]
    url = f"https://pypi.org/pypi/{package}/json"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310
            data = json.load(response)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError):
        data = None
    _cache[package] = data
    return data


def _usable_kind(files: List[dict]) -> Optional[str]:
    """Return how this release is usable on 3.14/linux-x86_64, or None."""
    wheels = [f.get("filename", "") for f in files if f.get("filename", "").endswith(".whl")]
    if any("py3-none-any" in fn or "py2.py3-none-any" in fn for fn in wheels):
        return "pure-python"
    for fn in wheels:
        linux = ("manylinux" in fn or "musllinux" in fn) and "x86_64" in fn
        if linux and "cp314" in fn:
            return "cp314"
        if linux and "abi3" in fn:
            return "abi3"
    return None


def _version_key(version: str) -> Tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", version))


def _lowest_working_version(data: dict, at_least: str) -> Optional[str]:
    """Lowest stable release >= at_least that is usable on 3.14."""
    floor = _version_key(at_least)
    candidates = []
    for version, files in data.get("releases", {}).items():
        if _PRERELEASE.search(version):
            continue
        try:
            key = _version_key(version)
        except ValueError:
            continue
        if key < floor:
            continue
        if _usable_kind(files):
            candidates.append(version)
    if not candidates:
        return None
    return min(candidates, key=_version_key)


def parse_pins(path: Path) -> List[Tuple[str, str]]:
    """Extract (package, version) for exact `==` pins only.

    Non-pinned requirements (`>=`, `~=`, bare names) are skipped rather than
    guessed at: what they resolve to at build time is exactly the thing this
    script cannot know, and pretending otherwise would report false confidence.
    They are surfaced separately by the caller.
    """
    pins = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        if "==" not in line:
            continue
        name, _, version = line.partition("==")
        version = version.split(";", 1)[0].strip()
        name = name.strip().split("[", 1)[0]
        if name and version:
            pins.append((name, version))
    return pins


def count_unpinned(path: Path) -> int:
    total = 0
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        if "==" not in line:
            total += 1
    return total


def check_worker(worker_dir: Path) -> Optional[dict]:
    req_path = None
    for name in REQUIREMENTS_NAMES:
        candidate = worker_dir / name
        if candidate.is_file():
            req_path = candidate
            break
    if req_path is None:
        return None

    blockers = []
    for package, version in parse_pins(req_path):
        data = _pypi(package)
        if data is None:
            blockers.append((package, version, "pypi-lookup-failed", None))
            continue
        files = data.get("releases", {}).get(version)
        if files is None:
            blockers.append((package, version, "version-not-on-pypi", None))
            continue
        if _usable_kind(files):
            continue
        blockers.append(
            (package, version, "no-3.14-artifact", _lowest_working_version(data, version))
        )

    return {
        "worker": worker_dir.name,
        "requirements": req_path.relative_to(REPO_ROOT).as_posix(),
        "blockers": blockers,
        "unpinned": count_unpinned(req_path),
    }


def main(argv: List[str]) -> int:
    if not WORKERS_DIR.is_dir():
        print(f"No workers directory at {WORKERS_DIR}", file=sys.stderr)
        return 2

    wanted = set(argv[1:])
    worker_dirs = sorted(d for d in WORKERS_DIR.iterdir() if d.is_dir())
    if wanted:
        worker_dirs = [d for d in worker_dirs if d.name in wanted]

    ready, blocked, skipped, unpinned_workers = [], [], [], []
    for worker_dir in worker_dirs:
        result = check_worker(worker_dir)
        if result is None:
            skipped.append(worker_dir.name)
            continue
        if result["unpinned"]:
            unpinned_workers.append((result["worker"], result["unpinned"]))
        (blocked if result["blockers"] else ready).append(result)

    print(
        f"Python 3.14 readiness — {len(ready)} ready, {len(blocked)} blocked, "
        f"{len(skipped)} without a requirements file\n"
    )

    if ready:
        print(f"READY ({len(ready)}) — every pinned dependency has a 3.14/linux-x86_64 artifact:")
        for result in ready:
            print(f"  {result['worker']}")
        print()

    if blocked:
        print(f"BLOCKED ({len(blocked)}):")
        for result in blocked:
            print(f"  {result['worker']}  ({result['requirements']})")
            for package, version, reason, fix in result["blockers"]:
                suffix = f" -> bump to {fix}" if fix else " -> no working stable release found"
                print(f"      {package}=={version}  [{reason}]{suffix}")
        print()

    if unpinned_workers:
        print(
            "UNPINNED requirements (resolve to whatever is latest at build time — "
            "readiness above covers only the exact pins):"
        )
        for name, count in unpinned_workers:
            print(f"  {name}: {count} unpinned")
        print()

    if skipped:
        print(f"No requirements file ({len(skipped)}): {', '.join(skipped)}")

    return 1 if blocked else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
