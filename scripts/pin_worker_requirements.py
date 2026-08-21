#!/usr/bin/env python3
"""Convert floating worker requirements (`>=`, `~=`, bare) into exact `==` pins.

Why: a floating pin resolves to whatever is newest at image-build time, so two
builds of the same commit can ship different dependency trees. That is the
"non-reproducible builds" gap called out in docs/GO_LIVE_GAP_ANALYSIS.md §5 and
the remaining half of Stage 6 in
docs/architecture/PYTHON-3.14-UPGRADE-ASSESSMENT.md.

What it pins to: the newest stable release that BOTH satisfies the existing
constraint AND has an artifact usable on CPython 3.14 / linux-x86_64 (the same
test scripts/check_python314_readiness.py applies). That is deliberately close
to what a build would resolve to today, so pinning does not silently move a
worker onto a different major version — it freezes the version it was already
going to get, while keeping the estate 3.14-ready.

Prereleases are never selected. Packages already pinned with `==` are left
untouched. Editable/`-r` lines and comments are preserved verbatim.

By default this only reports. Pass --write to rewrite the files.

Usage:
    python scripts/pin_worker_requirements.py                # dry run, all workers
    python scripts/pin_worker_requirements.py --write        # apply
    python scripts/pin_worker_requirements.py tranceflow     # scope to workers
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
REQUIREMENTS_NAMES = ("requirements-worker.txt", "requirements.txt")

_PRERELEASE = re.compile(r"(dev|rc|a|b)\d+$")
# name[extras]<op>version — captures the pieces we need to rebuild the line.
_REQ = re.compile(r"^(?P<name>[A-Za-z0-9._-]+)(?P<extras>\[[^\]]*\])?\s*(?P<rest>.*)$")

_cache: Dict[str, Optional[dict]] = {}


def _pypi(package: str) -> Optional[dict]:
    if package in _cache:
        return _cache[package]
    try:
        with urllib.request.urlopen(  # noqa: S310
            f"https://pypi.org/pypi/{package}/json", timeout=30
        ) as response:
            data = json.load(response)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError):
        data = None
    _cache[package] = data
    return data


def _usable_on_314(files: List[dict]) -> bool:
    wheels = [f.get("filename", "") for f in files if f.get("filename", "").endswith(".whl")]
    if any("py3-none-any" in fn or "py2.py3-none-any" in fn for fn in wheels):
        return True
    for fn in wheels:
        linux = ("manylinux" in fn or "musllinux" in fn) and "x86_64" in fn
        if linux and ("cp314" in fn or "abi3" in fn):
            return True
    return False


def _key(version: str) -> Tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", version))


def _satisfies_floor(version: str, floor: Optional[str]) -> bool:
    if floor is None:
        return True
    try:
        return _key(version) >= _key(floor)
    except ValueError:
        return True


def _floor_from(rest: str) -> Optional[str]:
    """Extract the lower bound from a `>=X` / `~=X` constraint, if any."""
    match = re.search(r"(?:>=|~=|>)\s*([0-9][0-9A-Za-z._-]*)", rest)
    return match.group(1) if match else None


def _has_stable_release(data: dict) -> bool:
    """Does this package publish any non-prerelease version at all?

    The OpenTelemetry instrumentation packages ship only `0.NNbM` versions —
    PEP 440 reads the `bM` as a beta, but for those projects it *is* the
    release channel, and pip installs them because nothing else exists. So a
    package with no stable line has its prereleases treated as its releases,
    rather than being left unpinnable forever.
    """
    return any(
        files and not _PRERELEASE.search(version)
        for version, files in data.get("releases", {}).items()
    )


def resolve(package: str, floor: Optional[str]) -> Optional[str]:
    data = _pypi(package)
    if data is None:
        return None
    allow_prerelease = not _has_stable_release(data)
    candidates = []
    for version, files in data.get("releases", {}).items():
        if not files:
            continue
        if _PRERELEASE.search(version) and not allow_prerelease:
            continue
        try:
            _key(version)
        except ValueError:
            continue
        if not _satisfies_floor(version, floor):
            continue
        if _usable_on_314(files):
            candidates.append(version)
    if not candidates:
        return None
    return max(candidates, key=_key)


def process(path: Path, write: bool) -> List[Tuple[str, str]]:
    changes: List[Tuple[str, str]] = []
    out_lines: List[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.split("#", 1)[0].strip()
        # Comments, blanks, flags and already-exact pins pass through untouched.
        if not stripped or stripped.startswith("-") or "==" in stripped:
            out_lines.append(raw)
            continue
        match = _REQ.match(stripped)
        if not match:
            out_lines.append(raw)
            continue
        name = match.group("name")
        extras = match.group("extras") or ""
        rest = match.group("rest") or ""
        if ";" in rest:  # environment markers — leave alone, too easy to break
            out_lines.append(raw)
            continue
        version = resolve(name, _floor_from(rest))
        if version is None:
            out_lines.append(raw)
            continue
        new_line = f"{name}{extras}=={version}"
        changes.append((stripped, new_line))
        out_lines.append(new_line)
    if write and changes:
        path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    return changes


def main(argv: List[str]) -> int:
    write = "--write" in argv
    wanted = {a for a in argv[1:] if not a.startswith("--")}

    total = 0
    for worker_dir in sorted(d for d in WORKERS_DIR.iterdir() if d.is_dir()):
        if wanted and worker_dir.name not in wanted:
            continue
        for filename in REQUIREMENTS_NAMES:
            path = worker_dir / filename
            if not path.is_file():
                continue
            changes = process(path, write)
            if changes:
                total += len(changes)
                print(f"{path.relative_to(REPO_ROOT)}")
                for before, after in changes:
                    print(f"    {before:<45} -> {after}")
            break

    verb = "Pinned" if write else "Would pin"
    print(f"\n{verb} {total} requirement(s).")
    if total and not write:
        print("Re-run with --write to apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
