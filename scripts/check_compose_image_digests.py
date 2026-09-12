#!/usr/bin/env python3
"""Fail when a compose service gains an image pin without a content digest.

Why this exists
---------------
cubic flagged `docs/architecture/sbom/weaviate.cdx.json` on PR #1207: the
container's reference was the mutable tag `cr.weaviate.io/semitechnologies/
weaviate:1.25.4` while sibling SBOMs pinned `@sha256:`. The finding was right and
the location was not -- those SBOMs are generated from
`docker-compose.production.yml`, so the SBOM was faithfully reporting a compose
pin that has no digest. Editing the SBOM would have made the inventory disagree
with the deployment while fixing nothing.

Measured across every compose file: **11 of 148 image pins carry no digest**, and
eight of those are `:latest`, which is a weaker pin than the one that was
reported. So the finding was a class, not an instance.

A digest is what lets the CMDB say *which build* is running. Without it the
container register records a name that can point at different bytes tomorrow,
which is the one thing a container inventory exists to prevent.

This guard does not resolve digests -- that needs the registry, and inventing one
would be worse than recording none. It ratchets: the 11 known pins are recorded
in a baseline to be burned down, and any *new* un-digested image fails CI.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE = REPO_ROOT / "config" / "estate" / "compose_digest_baseline.json"
IMAGE_RE = re.compile(r"^\s*image:\s*(\S+)")


class CannotReadBaseline(RuntimeError):
    """Raised when the baseline cannot be read.

    Without it every pin looks new, so the guard would either fail the whole
    estate or -- worse, if it defaulted to an empty allowance -- pass silently
    while comparing against nothing. See docs/governance/IMMUNE-SYSTEM.md.
    """


def compose_files(root: Path = REPO_ROOT) -> list[Path]:
    return sorted(root.glob("docker-compose*.yml"))


def undigested(root: Path = REPO_ROOT) -> list[str]:
    """Return "<file>:<line> <image>" for every image pin lacking @sha256."""
    found: list[str] = []
    for path in compose_files(root):
        rel = path.relative_to(root)
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = IMAGE_RE.match(line)
            if not match:
                continue
            image = match.group(1)
            # Interpolated images are resolved at deploy time; this file cannot
            # know what they become, and guessing would be a false finding.
            if image.startswith("$") or "${" in image:
                continue
            if "@sha256:" not in image:
                found.append(f"{rel}:{n} {image}")
    return found


def load_baseline(path: Path = BASELINE) -> set[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CannotReadBaseline(f"{path} is missing, so nothing can be compared.") from exc
    except json.JSONDecodeError as exc:
        raise CannotReadBaseline(f"{path} is not valid JSON: {exc}") from exc
    return set(payload.get("undigested", []))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="rewrite the baseline from the tree (use only when burning entries DOWN)",
    )
    args = parser.parse_args(argv)

    current = undigested()

    if args.update_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(
            json.dumps(
                {
                    "_comment": (
                        "Compose image pins with no @sha256 digest. This is a debt "
                        "register to burn down, not an allowance to grow. "
                        "scripts/check_compose_image_digests.py fails on any pin not "
                        "listed here."
                    ),
                    "undigested": sorted(current),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"baseline written: {len(current)} un-digested pin(s)")
        return 0

    try:
        allowed = load_baseline()
    except CannotReadBaseline as exc:
        print(f"cannot check compose image digests: {exc}", file=sys.stderr)
        return 1

    new = sorted(set(current) - allowed)
    fixed = sorted(allowed - set(current))

    for entry in fixed:
        print(f"  [FIXED] {entry}")
    if new:
        print("Compose image digests: FAILED")
        for entry in new:
            print(f"  [NEW] {entry}")
            print(
                "        This image pin has no @sha256 digest, so the container "
                "register\n        cannot say which build is running. Pin the "
                "digest, or record it in\n        the baseline with a reason if it "
                "genuinely cannot be pinned."
            )
        return 1

    print(
        f"Compose image digests: PASSED — {len(compose_files())} file(s), "
        f"{len(allowed)} known un-digested pin(s), {len(fixed)} newly fixed, none added"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
