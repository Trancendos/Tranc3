#!/usr/bin/env python3
"""Verify every submodule gitlink points at a commit that actually exists upstream.

Why this exists
---------------
A submodule gitlink is just a SHA recorded in the superproject's tree. Nothing in
git checks that the SHA is still reachable in the submodule's remote, so a force
push, a rebased branch, or a deleted fork upstream can silently invalidate it.
The failure does not surface until someone clones fresh and runs
``git submodule update --init``, which then dies with::

    fatal: remote error: upload-pack: not our ref <sha>

and — because the run aborts partway — leaves *every* submodule with a bare
``.git`` and no working tree, not just the broken one. Any build step using a
submodule path as its context (``docker-compose.production.yml`` builds The Town
Hall from ``workers/cranbania``) then fails for what looks like an unrelated
reason.

This check makes that condition fail loudly in CI, on the PR that introduces it,
instead of at deploy time on someone else's machine.

Usage
-----
    python scripts/validate_submodule_pins.py          # check all submodules
    python scripts/validate_submodule_pins.py --json   # machine-readable

Exit codes: 0 = every pin reachable, 1 = at least one unreachable or unverifiable.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class PinResult:
    path: str
    url: str
    sha: str
    reachable: bool
    detail: str


def _run(cmd: list[str], timeout: int = 90) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)


def _submodule_urls() -> dict[str, str]:
    """Map submodule path -> remote URL, read from .gitmodules."""
    gitmodules = ROOT / ".gitmodules"
    if not gitmodules.is_file():
        return {}
    urls: dict[str, str] = {}
    path = None
    for raw in gitmodules.read_text(errors="ignore").splitlines():
        line = raw.strip()
        if line.startswith("path"):
            path = line.split("=", 1)[1].strip()
        elif line.startswith("url") and path:
            urls[path] = line.split("=", 1)[1].strip()
            path = None
    return urls


def _recorded_pins() -> dict[str, str]:
    """Map submodule path -> pinned SHA, read from the superproject gitlink.

    Uses `git ls-tree` rather than `git submodule status`: ls-tree reads the
    committed tree entry directly, so it reports the pin even when the submodule
    has never been initialised (status prefixes those with '-' and can be empty).
    """
    proc = _run(["git", "ls-tree", "-r", "HEAD"])
    if proc.returncode != 0:
        return {}
    pins: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        # <mode> commit <sha>\t<path>   — mode 160000 marks a gitlink
        m = re.match(r"^160000 commit ([0-9a-f]{40})\t(.+)$", line)
        if m:
            pins[m.group(2)] = m.group(1)
    return pins


def _is_reachable(url: str, sha: str) -> tuple[bool, str]:
    """True when `sha` can be fetched from `url`.

    `git ls-remote <url> <sha>` only matches advertised refs, so it misses a
    commit that is real but not itself a branch tip. Ask the remote to serve the
    object directly instead — that is exactly what `git submodule update` does,
    so it fails in the same cases and no others.
    """
    proc = _run(["git", "fetch", "--dry-run", "--depth", "1", url, sha])
    if proc.returncode == 0:
        return True, "reachable"
    stderr = (proc.stderr or "").strip().splitlines()
    detail = stderr[-1] if stderr else f"git fetch exited {proc.returncode}"
    return False, detail


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args()

    urls = _submodule_urls()
    pins = _recorded_pins()

    if not pins:
        print("No submodule gitlinks found — nothing to validate.")
        return 0

    results: list[PinResult] = []
    for path, sha in sorted(pins.items()):
        url = urls.get(path, "")
        if not url:
            results.append(
                PinResult(path, "", sha, False, "no url in .gitmodules for this gitlink")
            )
            continue
        ok, detail = _is_reachable(url, sha)
        results.append(PinResult(path, url, sha, ok, detail))

    broken = [r for r in results if not r.reachable]

    if args.json:
        print(json.dumps({"results": [asdict(r) for r in results], "broken": len(broken)}, indent=2))
    else:
        for r in results:
            mark = "✓" if r.reachable else "✗"
            print(f"{mark} {r.path} @ {r.sha[:10]} — {r.detail}")
        if broken:
            print()
            print(f"{len(broken)} submodule pin(s) unreachable upstream.")
            print("A fresh `git submodule update --init` will fail, and will leave")
            print("ALL submodules without a working tree — not only the broken one.")
            print()
            print("Fix: re-pin to a commit that exists on the submodule's default branch:")
            for r in broken:
                print(f"    git -C {r.path} fetch origin && git -C {r.path} checkout origin/main")
            print("    git add <paths> && git commit   # records the corrected gitlink")

    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
