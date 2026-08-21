#!/usr/bin/env python3
"""Fail if a package's version override disagrees between its declaration sites.

WHY THIS EXISTS

`web/` declares dependency overrides in three places, and all three are load-
bearing for a different installer:

  * `package.json` -> `overrides`        — npm, which is what CI's `npm ci` uses
  * `package.json` -> `pnpm.overrides`   — pnpm 10 and earlier
  * `pnpm-workspace.yaml` -> `overrides` — pnpm 11+, which no longer reads the
    `pnpm` key in package.json at all

An override is a security control here, not a preference: these entries exist to
force a transitive dependency past a published advisory. So the failure mode of
drift is not a build error, it is a *silently reintroduced vulnerability* in
whichever installer was left behind.

That is not hypothetical. Both halves of it have already happened in this estate:

  * `web/pnpm-lock.yaml` resolved dompurify 3.4.12 and nanoid 3.3.17 -- both
    covered by live advisories -- while package.json's npm `overrides` had been
    patched. npm was safe; pnpm was not; nothing reported a problem.
  * In InfinityStyles #115 an override was declared only under package.json's
    `pnpm` key, which pnpm 11 ignores, so it was inert while appearing to be a
    control.

Neither was caught by a test, because in both cases every file *looked*
deliberate on its own. Only comparing them catches it.

WHAT COUNTS AS DRIFT

A package present in more than one site with different specifiers. A package
present in only one site is NOT flagged: a genuinely npm-only or pnpm-only pin is
legitimate, and warning about it would train people to ignore this check.

Exit 0 when every shared key agrees, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Each entry: a directory, and the sites within it that must agree.
PACKAGES = ("web",)


def _load_sites(pkg_dir: Path) -> dict[str, dict[str, str]]:
    """site label -> {package: specifier} for every override site present."""
    sites: dict[str, dict[str, str]] = {}

    pj = pkg_dir / "package.json"
    if pj.is_file():
        try:
            data = json.loads(pj.read_text())
        except json.JSONDecodeError as exc:
            raise SystemExit(f"[ERROR] {pj} is not valid JSON: {exc}") from exc
        if isinstance(data.get("overrides"), dict):
            sites["package.json:overrides"] = dict(data["overrides"])
        pnpm_block = (data.get("pnpm") or {}).get("overrides")
        if isinstance(pnpm_block, dict):
            sites["package.json:pnpm.overrides"] = dict(pnpm_block)

    ws = pkg_dir / "pnpm-workspace.yaml"
    if ws.is_file():
        # Parsed without PyYAML so this check has no dependency of its own -- a
        # guard that cannot run because its own import is missing is worse than
        # no guard. The file's `overrides:` block is a flat `key: value` mapping.
        block: dict[str, str] = {}
        in_block = False
        for raw in ws.read_text().splitlines():
            if raw.strip().startswith("#") or not raw.strip():
                continue
            if not raw.startswith((" ", "\t")):
                in_block = raw.split(":", 1)[0].strip() == "overrides"
                continue
            if in_block and ":" in raw:
                k, _, v = raw.partition(":")
                block[k.strip()] = v.strip().strip("'\"")
        if block:
            sites["pnpm-workspace.yaml:overrides"] = block

    return sites


def check_package(rel_dir: str) -> list[str]:
    """Return one message per override key whose sites disagree; empty if they agree."""
    pkg_dir = REPO / rel_dir
    sites = _load_sites(pkg_dir)
    if len(sites) < 2:
        return []

    problems = []
    every_key = {k for s in sites.values() for k in s}
    for key in sorted(every_key):
        declared = {label: s[key] for label, s in sites.items() if key in s}
        # Present in only one site is a deliberate single-installer pin, not drift.
        if len(declared) < 2:
            continue
        if len(set(declared.values())) > 1:
            rendered = "; ".join(f"{label} = {spec}" for label, spec in sorted(declared.items()))
            problems.append(f"{rel_dir}: '{key}' disagrees across sites — {rendered}")
    return problems


def main() -> int:
    """Check every package for override drift; exit non-zero on the first findings."""
    ap = argparse.ArgumentParser(description="Check dependency override sites agree.")
    ap.add_argument("--check", action="store_true", help="accepted for symmetry; always checks")
    ap.parse_args()

    problems = []
    checked = 0
    for pkg in PACKAGES:
        sites = _load_sites(REPO / pkg)
        if sites:
            checked += 1
        problems.extend(check_package(pkg))

    if problems:
        print("[ERROR] dependency override drift:\n", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        print(
            "\n        These sites feed different installers (npm / pnpm 10 / pnpm 11+).\n"
            "        A disagreement means one installer resolves a version the others\n"
            "        forbid — which is how a patched advisory comes back.",
            file=sys.stderr,
        )
        return 1

    print(f"Override sync check: PASSED ({checked} package(s), all shared keys agree)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
