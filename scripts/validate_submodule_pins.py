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
    # List form with the default shell=False: the OS receives argv directly, so
    # there is no shell to interpret metacharacters and no command injection to
    # escape. The real exposure here is *argument* injection — see _url_is_safe.
    return subprocess.run(  # noqa: S603 — argv list, shell=False, inputs validated below
        cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout
    )


def _url_is_safe(url: str) -> tuple[bool, str]:
    """Reject submodule URLs that git would treat as something other than a URL.

    `.gitmodules` is repository content, so on a pull request — especially from a
    fork — its contents are attacker-controlled. Passing such a value straight to
    `git fetch` is unsafe even with shell=False, because git parses leading
    dashes as options: a URL of `--upload-pack=<cmd>` becomes a flag that runs
    `<cmd>`. The `ext::` transport is worse still — it executes its argument by
    design. This is the shape of CVE-2018-17456, and it is exactly the risk a
    generic "subprocess without a static string" warning is pointing at.

    Validating the value is the fix; quoting it is not, since no shell is
    involved. Returns (ok, reason-when-not-ok).
    """
    if not url:
        return False, "empty url"
    if url.startswith("-"):
        return False, f"refusing url parsed as a git option: {url!r}"
    # ext:: runs an arbitrary command; the others are the transports git itself
    # restricts via protocol.allow for the same reason.
    lowered = url.lower()
    for scheme in ("ext::", "ext:", "file://", "sftp://"):
        if lowered.startswith(scheme):
            return False, f"refusing unsafe transport {scheme!r} in url: {url!r}"
    return True, ""


def _submodule_urls() -> dict[str, str]:
    """Map submodule path -> remote URL, read from .gitmodules.

    Delegates the parse to `git config --file`, which is the only thing that
    reads the format correctly. Hand-rolling it looks simple and is not:
    `.gitmodules` holds git-config keys, so `URL =` is as valid as `url =`, the
    keys may appear in any order within a section, and values can be quoted. A
    naive line scan mismatches all three and reports "no url for this gitlink",
    which this script would then surface as a broken pin on a healthy repo.
    """
    if not (ROOT / ".gitmodules").is_file():
        return {}
    proc = _run(["git", "config", "--file", ".gitmodules", "--list"])
    if proc.returncode != 0:
        return {}
    paths: dict[str, str] = {}
    remotes: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        key, sep, value = line.partition("=")
        if not sep:
            continue
        name, _, field = key.removeprefix("submodule.").rpartition(".")
        if field == "path":
            paths[name] = value
        elif field == "url":
            remotes[name] = value
    return {paths[name]: url for name, url in remotes.items() if name in paths}


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

    `url` is validated by _url_is_safe before it reaches git, and `sha` is a
    40-hex string matched out of `git ls-tree` output, so neither can be read as
    an option. `--` closes the option list regardless.
    """
    ok, reason = _url_is_safe(url)
    if not ok:
        return False, reason
    try:
        proc = _run(["git", "fetch", "--dry-run", "--depth", "1", "--", url, sha])
    except subprocess.TimeoutExpired:
        # An unresponsive remote must not abort the run — the other pins still
        # need checking, and a traceback would replace the actionable report.
        return False, "git fetch timed out — pin not verifiable"
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
        print(
            json.dumps({"results": [asdict(r) for r in results], "broken": len(broken)}, indent=2)
        )
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
            print("Fix: re-pin to a commit that exists on the submodule's default branch.")
            print("Run from the superproject — the broken path has no working tree to cd into,")
            print("and --remote follows the submodule's own default branch rather than assuming")
            print("it is called 'main':")
            for r in broken:
                print(f"    git submodule update --init --remote -- {r.path}")
            print("    git add <paths> && git commit   # records the corrected gitlink")

    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
