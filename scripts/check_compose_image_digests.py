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

A digest is what lets the CMDB say *which build* is running. Without it the
container register records a name that can point at different bytes tomorrow,
which is the one thing a container inventory exists to prevent.

This guard does not resolve digests -- that needs the registry, and inventing one
would be worse than recording none. It ratchets: known pins are recorded in a
baseline to be burned down, and any *new* un-digested image fails CI.

Three things this guard got wrong on its first pass, all of the same family as
the defect it was built to catch -- a control that runs, reports, and cannot see:

1. It globbed `docker-compose*.yml` at the repository root only. Ten further
   compose files live under `deploy/*/` and `docker/`, carrying 22 more image
   pins, and every one of them passed a gate that had never looked at them.
   `compose_files()` now walks the whole tree, skipping submodules (which are
   other repositories' to guard) and vendored trees.
2. It keyed the baseline on `file:line`. Inserting a service or a comment above a
   listed pin moved it, and the guard then reported the same unchanged pin as
   `[NEW]` at its new line and `[FIXED]` at the old one -- reddening CI for an
   edit that changed nothing. The key is now `file + image`; the live line number
   is still printed, because that is what a reader needs to go fix it.
3. It skipped every interpolated image. `${RUNNER_IMAGE:-code.forgejo.org/forgejo/
   runner:3}` is not unknowable: the default after `:-` is exactly what runs when
   the variable is unset, and all three interpolations in this estate have one.
   Only a bare `${VAR}` is genuinely undecidable here, and those are still
   skipped rather than guessed at. A quoted value (`image: "..."`) is unwrapped
   for the same reason -- YAML quoting is not a property of the image.

Widening the scan took the register from 11 entries to 14. That is the guard
seeing more, not the estate getting worse.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE = REPO_ROOT / "config" / "estate" / "compose_digest_baseline.json"
IMAGE_RE = re.compile(r"^\s*image:\s*(\S+)")
DEFAULTED_VAR_RE = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*:[-=]([^}]*)\}")

# Trees this repository does not own or does not deploy. Submodules are detected
# structurally (a nested `.git`), not by name, so a new one needs no edit here.
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "vendor", "site-packages", ".tox"}


class CannotReadBaseline(RuntimeError):
    """Raised when the baseline cannot be read.

    Without it every pin looks new, so the guard would either fail the whole
    estate or -- worse, if it defaulted to an empty allowance -- pass silently
    while comparing against nothing. See docs/governance/IMMUNE-SYSTEM.md.
    """


@dataclass(frozen=True)
class Pin:
    """One `image:` line in one compose file."""

    file: str
    line: int
    image: str

    @property
    def key(self) -> str:
        """Baseline identity: stable under edits elsewhere in the file."""
        return f"{self.file} {self.image}"

    def located(self) -> str:
        return f"{self.file}:{self.line} {self.image}"


def _is_ours(path: Path, root: Path) -> bool:
    """True when `path` is in this repository rather than a submodule or vendor tree."""
    for parent in path.relative_to(root).parents:
        if parent == Path("."):
            continue
        if parent.name in SKIP_DIRS:
            return False
        # A submodule carries its own `.git` (a file, not a directory). Its
        # compose files are that repository's to pin, not this one's.
        if (root / parent / ".git").exists():
            return False
    return True


def compose_files(root: Path = REPO_ROOT) -> list[Path]:
    """Every compose manifest in this repository, not only the ones at the root."""
    found = {
        path
        for pattern in ("docker-compose*.yml", "docker-compose*.yaml")
        for path in root.rglob(pattern)
        if path.is_file() and _is_ours(path, root)
    }
    return sorted(found)


def resolve(image: str) -> str | None:
    """Return the image that actually runs, or None when it cannot be known.

    `${VAR:-default}` is decidable: `default` is what runs with the variable
    unset. A bare `${VAR}` is not, and a guess would be a finding nobody can act
    on -- the fastest way to get a guard switched off.
    """
    unquoted = image.strip()
    if len(unquoted) >= 2 and unquoted[0] == unquoted[-1] and unquoted[0] in "\"'":
        unquoted = unquoted[1:-1]
    resolved = DEFAULTED_VAR_RE.sub(lambda m: m.group(1), unquoted)
    if "$" in resolved:
        return None
    return resolved


def undigested(root: Path = REPO_ROOT) -> list[Pin]:
    """Every image pin in the estate that carries no @sha256 digest."""
    found: list[Pin] = []
    for path in compose_files(root):
        rel = path.relative_to(root).as_posix()
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = IMAGE_RE.match(line)
            if not match:
                continue
            image = resolve(match.group(1))
            if image is None or "@sha256:" in image:
                continue
            found.append(Pin(file=rel, line=n, image=image))
    return found


def load_baseline(path: Path = BASELINE) -> set[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CannotReadBaseline(f"{path} is missing, so nothing can be compared.") from exc
    except json.JSONDecodeError as exc:
        raise CannotReadBaseline(f"{path} is not valid JSON: {exc}") from exc
    return set(payload.get("undigested", []))


def write_baseline(pins: list[Pin], path: Path = BASELINE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "_comment": (
                    "Compose image pins with no @sha256 digest, keyed on file + image "
                    "so an unrelated edit that moves a line cannot redden CI. This is "
                    "a debt register to burn down, not an allowance to grow. "
                    "scripts/check_compose_image_digests.py fails on any pin not "
                    "listed here."
                ),
                "undigested": sorted({pin.key for pin in pins}),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="rewrite the baseline from the tree (use only when burning entries DOWN)",
    )
    args = parser.parse_args(argv)

    current = undigested()
    by_key = {pin.key: pin for pin in current}

    if args.update_baseline:
        write_baseline(current)
        print(f"baseline written: {len(by_key)} un-digested pin(s)")
        return 0

    try:
        allowed = load_baseline()
    except CannotReadBaseline as exc:
        print(f"cannot check compose image digests: {exc}", file=sys.stderr)
        return 1

    new = sorted(set(by_key) - allowed)
    fixed = sorted(allowed - set(by_key))

    for key in fixed:
        print(f"  [FIXED] {key}")
    if new:
        print("Compose image digests: FAILED")
        for key in new:
            print(f"  [NEW] {by_key[key].located()}")
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
