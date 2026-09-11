"""The risk surfaces of this estate, in one place.

WHY THIS IS A MODULE AND NOT A LIST IN A SCRIPT
-----------------------------------------------
Two things need this list and they need it to agree.

`scripts/triage_change.py` reads it to tell a reviewer what a change touches.
`src/immune/antibody.py` reads it to decide what an automated fix may NEVER
touch. A second copy would drift, and the direction it would drift in is the
dangerous one: a surface added for the reviewer's benefit and not for the
antibody's means an automated change walks into a security-critical path that
the estate had already written down as needing human eyes.

So there is one definition, here, and both import it.

WHAT A SURFACE IS
-----------------
`(label, globs, why)`. The reason is not decoration -- a surface with no stated
reason is a category somebody invented, and it will be ignored within a month.
The reasons are also what an antibody quotes when it refuses, so a refusal
explains itself in the same words a reviewer would have used.
"""

from __future__ import annotations

import fnmatch

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
    # `**/` on every filename pattern, deliberately. A bare `requirements*.txt`
    # or `docker-compose*.yml` is anchored at the repository root, so a change
    # to `workers/vault-service/requirements-worker.txt` -- which is most of
    # this estate's dependency surface, 90-odd workers deep -- raised no
    # surface at all. The two registers disagreed in a way nobody would notice:
    # `.github/labeler.yml` already uses `**/requirements*.txt`, so the LABEL
    # said "dependencies" while the triage summary, whose whole job is telling
    # a reviewer what to look at first, stayed silent. Reported by cubic on
    # PR #1150; the fix is to make this file match the register it claims to
    # read from.
    (
        "touches-routing",
        ("**/docker-compose*.yml", "**/Dockerfile", "api.py"),
        "changes where traffic goes or which port a service answers on; "
        "the class of defect that leaves a deployed Location unreachable",
    ),
    (
        "touches-pins",
        (
            ".gitmodules",
            "**/requirements*.txt",
            "**/package-lock.json",
            "**/pnpm-lock.yaml",
            "**/Cargo.lock",
            "**/go.sum",
            "**/poetry.lock",
        ),
        "moves the dependency surface the census and the merge gate measure",
    ),
    (
        "touches-entity-register",
        ("src/entities/platform.py", "PLATFORM_ENTITIES.md", "CLAUDE.md", "config/estate/*.yaml"),
        "changes the canonical description of the platform that other tooling derives from",
    ),
)


# Surfaces an automated change must never touch on its own.
#
# Not every surface: `touches-routing` and `touches-entity-register` want a
# reviewer's attention, but a mechanical lint fix in one of them is not
# dangerous. These four are different in kind -- a wrong automated edit to a
# gate, an auth path, secret custody, or a suppression list does not merely
# introduce a bug, it removes the thing that would have caught the bug. That is
# the autoimmune case, and it is the one worth being absolute about.
NEVER_AUTOMATED = frozenset(
    {
        "touches-the-gate",
        "touches-auth",
        "touches-secrets",
        "touches-suppression",
    }
)


def matches(path: str, pattern: str) -> bool:
    """Glob match with `**` meaning "at any depth", as actions/labeler treats it.

    Lifted verbatim from `scripts/triage_change.py` rather than reimplemented.
    The first draft of this module wrote a simpler version, which handled
    `**/x` but not `dir/**` -- so the shared copy would have matched slightly
    FEWER paths than the script it was replacing, and a surface the triage
    summary raises would have gone unnoticed by the antibody. A consolidation
    that quietly narrows a security check is worse than the duplication it
    removes, so the more capable of the two implementations is the one that
    survives.
    """
    if fnmatch.fnmatch(path, pattern):
        return True
    if "**/" in pattern and fnmatch.fnmatch(path, pattern.replace("**/", "", 1)):
        return True
    # `dir/**` should match `dir/file` as well as `dir/a/b`.
    if pattern.endswith("/**") and path.startswith(pattern[:-3] + "/"):
        return True
    return False


def surfaces_for(paths: list[str]) -> list[tuple[str, str, list[str]]]:
    """Every surface these paths cross, with the reason and the files."""
    found = []
    for label, globs, why in SURFACES:
        hit = [p for p in paths if any(matches(p, g) for g in globs)]
        if hit:
            found.append((label, why, hit))
    return found


def forbidden_for_automation(paths: list[str]) -> list[tuple[str, str, list[str]]]:
    """The subset of crossed surfaces that no automated change may touch."""
    return [entry for entry in surfaces_for(paths) if entry[0] in NEVER_AUTOMATED]
