#!/usr/bin/env python3
"""Say who owns a change and what it touches, before anyone reviews it.

WHY THIS EXISTS
---------------
`actions/labeler` maps path globs to labels. It is a good tool and this
repository keeps it. But it has two limits that matter here, and one of them is
why its check has never gone green.

**The trap.** `label.yml` runs on `pull_request_target`, which reads the
workflow AND its configuration from the BASE branch. A pull request that
creates or fixes `.github/labeler.yml` therefore cannot make the check pass --
the run that would validate it is reading the old base. The check stays red
until the change merges, and a check that is always red teaches reviewers to
ignore red, which is how a real failure gets waved through beside eleven fake
ones. This script runs inside `ci.yml` on `pull_request`, against the PR's own
tree, so it says something true on the first run.

**The limit.** A path glob knows about directories. It does not know that
`workers/the-lab/` is The Lab, whose Lead AIs are The Dr. and Slime, or that a
change to `docker-compose.production.yml`'s port mappings is a routing change
that four Locations depend on. In this estate ownership is a Town Hall concept
with a register behind it -- `src/entities/platform.py`, 43 Locations, each
with a `worker_path` -- and that register is right there, unused by triage.

So this reads the same `.github/labeler.yml` the action reads (one vocabulary,
not two), and adds two things the action cannot produce:

  OWNERSHIP  which of the 43 Locations this change lands in, derived from the
             entity register rather than a hand-maintained second list. A
             change nobody owns is reported as unowned, which is a question
             for the Town Hall rather than a silence.

  SURFACES   the risk surfaces the change crosses, each declared here with a
             written reason. Not severity -- this makes no judgement about
             whether the change is good -- but "a reviewer should know this
             touches the merge gate before they read the diff".

It applies no labels and needs no token. It writes to the job summary, which is
free, works on forks, and cannot be blocked by a permissions model.

    python scripts/triage_change.py                    # vs origin/main
    python scripts/triage_change.py --base <ref>
    python scripts/triage_change.py --json out.json
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LABELER = ROOT / ".github/labeler.yml"

# Risk surfaces. Each entry is (label, globs, why a reviewer should be told).
# The reasons are the point: a surface with no reason is a category somebody
# invented, and it will be ignored within a month.
SURFACES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (
        "touches-the-gate",
        (
            "scripts/check_*.py",
            "scripts/immune_scan.py",
            "scripts/vulnerability_census.py",
            ".github/workflows/production-gate.yml",
            ".github/workflows/ci.yml",
        ),
        "changes a control that decides whether other changes may merge — "
        "a defect here is invisible until something it should have caught gets through",
    ),
    (
        "touches-suppression",
        (
            "config/immune/adjudications.yaml",
            ".trivyignore",
            ".secrets.baseline",
            ".typos.toml",
            "config/immune/*ceiling*",
            ".security_learning/*",
        ),
        "widens or narrows what the estate has decided not to look at",
    ),
    (
        "touches-auth",
        (
            "src/auth/**",
            "workers/infinity-auth/**",
            "src/townhall/route_auth.py",
            "Dimensional/service_auth*.py",
        ),
        "changes who may do what; the blast radius is every route behind it",
    ),
    (
        "touches-secrets",
        (
            "src/security/vault_client.py",
            "workers/infinity-void/**",
            "cloudflare/infinity-void/**",
            "workers/vault-service/**",
        ),
        "The Void — the estate's secret custody",
    ),
    (
        "touches-routing",
        ("docker-compose*.yml", "**/Dockerfile", "api.py"),
        "changes where traffic goes or which port a service answers on; "
        "the class of defect that leaves a deployed Location unreachable",
    ),
    (
        "touches-pins",
        (
            ".gitmodules",
            "requirements*.txt",
            "package-lock.json",
            "pnpm-lock.yaml",
            "Cargo.lock",
            "go.sum",
            "poetry.lock",
        ),
        "moves the dependency surface the census and the merge gate measure",
    ),
    (
        "touches-entity-register",
        ("src/entities/platform.py", "PLATFORM_ENTITIES.md", "CLAUDE.md", "config/estate/*.yaml"),
        "changes the canonical description of the platform that other tooling derives from",
    ),
)


def _run(args: list[str]) -> str:
    proc = subprocess.run(  # noqa: S603,S607 - fixed argv, no shell
        args, cwd=str(ROOT), capture_output=True, text=True, check=False
    )
    return proc.stdout if proc.returncode == 0 else ""


def changed_files(base: str) -> list[str]:
    """Files this change touches, deduplicated.

    An unresolved merge makes git emit one entry per stage, so the same path
    arrives two or three times and every count derived from it is inflated.
    """
    out = _run(["git", "diff", "--name-only", f"{base}...HEAD"])
    if not out.strip():
        out = _run(["git", "diff", "--name-only", base])
    return sorted({line.strip() for line in out.splitlines() if line.strip()})


def _matches(path: str, pattern: str) -> bool:
    """Glob match with `**` meaning "at any depth", as labeler treats it."""
    if fnmatch.fnmatch(path, pattern):
        return True
    if "**/" in pattern and fnmatch.fnmatch(path, pattern.replace("**/", "", 1)):
        return True
    # `dir/**` should match `dir/file` as well as `dir/a/b`.
    if pattern.endswith("/**") and path.startswith(pattern[:-3] + "/"):
        return True
    return False


def path_labels(files: list[str]) -> dict[str, list[str]]:
    """Labels from .github/labeler.yml — the same file the action reads.

    Sharing the config is deliberate. Two vocabularies for the same question
    diverge, and the divergence is invisible because each one looks correct on
    its own.
    """
    if not LABELER.exists():
        return {}
    config = yaml.safe_load(LABELER.read_text(encoding="utf-8")) or {}
    hits: dict[str, list[str]] = {}
    for label, globs in config.items():
        if not isinstance(globs, list):
            continue
        matched = [f for f in files if any(_matches(f, str(g)) for g in globs)]
        if matched:
            hits[str(label)] = matched
    return hits


def location_owners(files: list[str]) -> tuple[dict[str, list[str]], list[str]]:
    """Attribute each file to the Location that owns its path.

    Derived from `src/entities/platform.py`, not from a second hand-kept list,
    so a Location whose worker_path moves is re-attributed automatically. The
    longest matching prefix wins, so `workers/the-lab/` beats `workers/`.
    """
    try:
        from src.entities.platform import PLATFORM_ENTITIES
    except Exception as exc:  # pragma: no cover - the register must import
        print(f"entity register unreadable: {exc}", file=sys.stderr)
        return {}, list(files)

    prefixes: list[tuple[str, str]] = []
    for entity in PLATFORM_ENTITIES.values():
        path = (entity.worker_path or "").strip().strip("/")
        if path:
            prefixes.append((path, entity.location))
    prefixes.sort(key=lambda pair: -len(pair[0]))

    owned: dict[str, list[str]] = {}
    unowned: list[str] = []
    for file in files:
        for prefix, location in prefixes:
            if file == prefix or file.startswith(prefix + "/"):
                owned.setdefault(location, []).append(file)
                break
        else:
            unowned.append(file)
    return owned, unowned


def risk_surfaces(files: list[str]) -> list[tuple[str, str, list[str]]]:
    found = []
    for label, globs, why in SURFACES:
        matched = [f for f in files if any(_matches(f, g) for g in globs)]
        if matched:
            found.append((label, why, matched))
    return found


def render(files: list[str], base: str) -> str:
    labels = path_labels(files)
    owned, unowned = location_owners(files)
    surfaces = risk_surfaces(files)

    out: list[str] = [f"## Change triage — {len(files)} file(s) against `{base}`", ""]

    if labels:
        out.append("**Labels** (from `.github/labeler.yml`, the same file `actions/labeler` reads)")
        out.append("")
        for label in sorted(labels):
            out.append(f"- `{label}` — {len(labels[label])} file(s)")
        out.append("")

    out.append("**Locations this change lands in** (from the 43-entity register)")
    out.append("")
    if owned:
        for location in sorted(owned):
            names = ", ".join(sorted(owned[location])[:4])
            more = f" (+{len(owned[location]) - 4} more)" if len(owned[location]) > 4 else ""
            out.append(f"- **{location}** — {names}{more}")
    else:
        out.append("- none — this change lands outside every Location's `worker_path`")
    if unowned:
        out.append("")
        # An unowned doc or script is fine -- those are estate-wide. An unowned
        # SERVICE path is not: it means a worker exists that no Location in the
        # register claims, and an unowned service is exactly what "unrouted"
        # means in the Backlog Routing Register. Name them rather than folding
        # them into a count, because a count is not a question anyone can answer.
        orphan_services = sorted(
            {
                "/".join(file.split("/")[:2])
                for file in unowned
                if file.startswith("workers/") and file.count("/") >= 2
            }
        )
        out.append(
            f"- _{len(unowned)} file(s) owned by no Location._ Not a defect on its own — "
            "`scripts/`, `tests/`, `docs/` and the repository root are estate-wide."
        )
        if orphan_services:
            out.append("")
            out.append(
                f"- ⚠ **{len(orphan_services)} service path(s) claimed by no Location** — "
                "a worker with no owner in `src/entities/platform.py`. This is the "
                "Town Hall's question, and it is what `_unrouted_` means in the "
                "Backlog Routing Register:"
            )
            for service in orphan_services[:10]:
                out.append(f"  - `{service}/`")
            if len(orphan_services) > 10:
                out.append(f"  - _(+{len(orphan_services) - 10} more)_")
    out.append("")

    if surfaces:
        out.append("**Surfaces crossed** — what a reviewer should know before reading the diff")
        out.append("")
        for label, why, matched in surfaces:
            out.append(f"- `{label}` — {why}")
            for file in sorted(matched)[:3]:
                out.append(f"  - `{file}`")
            if len(matched) > 3:
                out.append(f"  - _(+{len(matched) - 3} more)_")
        out.append("")
    else:
        out.append("**Surfaces crossed** — none of the declared risk surfaces.")
        out.append("")

    out.append(
        "_Computed from this pull request's own tree. `label.yml` runs on "
        "`pull_request_target`, which reads its configuration from the base "
        "branch, so it cannot report on a change to that configuration until "
        "the change has merged._"
    )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--base", default="origin/main", help="what to diff against")
    parser.add_argument("--json", metavar="PATH", help="also write a machine-readable summary")
    args = parser.parse_args(argv)

    files = changed_files(args.base)
    if not files:
        print(f"No files changed against {args.base} — nothing to triage.")
        return 0

    summary = render(files, args.base)
    print(summary)

    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as handle:
            handle.write(summary + "\n")

    if args.json:
        owned, unowned = location_owners(files)
        target = Path(args.json)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {
                    "base": args.base,
                    "files": len(files),
                    "labels": sorted(path_labels(files)),
                    "locations": sorted(owned),
                    "unowned": len(unowned),
                    "surfaces": [label for label, _, _ in risk_surfaces(files)],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
