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
            # `scripts/*.py` and not a list of names. The first version named
            # `check_*.py` plus two files, which left `pre_deploy_quality_gate.py`,
            # `security_score.py`, `zero_cost_audit.py`, `citadel_preflight.py`
            # and thirty-odd others unprotected -- an automated ruff proposal
            # could have rewritten the production gate's own entrypoints.
            # Reported by cubic on PR #1150.
            #
            # Measured: 70 distinct `scripts/*.py` files are invoked by
            # `.github/workflows/*.yml`, and `check_*.py` covers 32 of them.
            # Listing the other 38 would be a second inventory to keep in step
            # with CI, which is the kind of list that goes stale silently.
            #
            # The generalisation is honest rather than lazy: this repository's
            # `scripts/` holds estate machinery only -- checks, builders,
            # censuses, audits, deploy plans -- and no application code. There
            # are 135 files there and zero subdirectories, so "a change under
            # scripts/ touches the gate" is a true statement about this tree,
            # not a convenient over-approximation. `tests/test_immune.py`
            # asserts every workflow-invoked script is covered, so the claim is
            # checked rather than asserted.
            "scripts/*.py",
            # `.forgejo/scripts/cf_deploy_plan.py` is a real deploy entrypoint,
            # invoked by `.github/workflows/deploy-cloudflare.yml:94`, and it
            # lives outside `scripts/`. Found by cubic on PR #1150 through the
            # TEST rather than the code: the coverage assertion's regex captured
            # a substring, trimmed the path to `scripts/cf_deploy_plan.py`, and
            # reported it covered — the exact false confidence the test exists
            # to prevent. Both are fixed; this is the half that protects the
            # script.
            ".forgejo/scripts/*.py",
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
        # `Dockerfile*`, not `Dockerfile`. Measured against this tree, the
        # exact-name pattern missed four real ones: `docker/Dockerfile.api`,
        # `Dockerfile.web`, `Dockerfile.worker` and
        # `deploy/forgejo/runner.Dockerfile` -- images whose CMD decides which
        # port a service answers on, which is precisely what this surface is
        # for. Reported by cubic on PR #1150.
        ("**/docker-compose*.yml", "**/Dockerfile*", "**/*.Dockerfile", "api.py"),
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
    if _segmented_match(path, pattern):
        return True
    if "**/" in pattern and _segmented_match(path, pattern.replace("**/", "", 1)):
        return True
    # `dir/**` should match `dir/file` as well as `dir/a/b`.
    if pattern.endswith("/**") and path.startswith(pattern[:-3] + "/"):
        return True
    return False


def _segmented_match(path: str, pattern: str) -> bool:
    """`fnmatch`, except a single `*` stops at a separator.

    `fnmatch` translates `*` to `.*`, which crosses `/`. So `scripts/*.py`
    matched `scripts/a/b/c.py`, and — the direction that actually bites —
    `**/Dockerfile` matched any path ENDING in Dockerfile at any depth only by
    accident, while `src/auth/**` and `scripts/check_*.py` silently claimed
    paths they were never meant to. actions/labeler, whose semantics the
    docstring above promises, treats `*` as within-a-segment and `**` as
    any-depth. Reported by cubic on PR #1150.

    Implemented by matching segment for segment: the pattern's segments and the
    path's segments must correspond one to one, with each pair compared by
    `fnmatch` in isolation so no wildcard can reach past its own segment. The
    `**` cases are still handled by the caller above, which is where they were
    already understood.
    """
    path_parts = path.split("/")
    pattern_parts = pattern.split("/")

    # `**` is matched as a WHOLE SEGMENT standing for any run of segments,
    # including none. The previous version handed any pattern containing `**`
    # straight to `fnmatch`, which re-introduced the separator crossing this
    # function exists to prevent — for precisely the patterns that needed it
    # most, since `**/requirements*.txt` and `**/Dockerfile*` are the ones that
    # span directories. So `src/requirements-thing/x.py` could be classified
    # under a `requirements` surface it has nothing to do with. Reported by
    # cubic on PR #1150.
    if "**" in pattern_parts:
        return _match_with_double_star(path_parts, pattern_parts)
    if len(path_parts) != len(pattern_parts):
        return False
    return all(fnmatch.fnmatch(p, g) for p, g in zip(path_parts, pattern_parts, strict=True))


def _match_with_double_star(path_parts: list[str], pattern_parts: list[str]) -> bool:
    """Segment-wise match where `**` absorbs zero or more whole segments.

    Recursive rather than clever: at each `**` try consuming nothing, then one
    segment, then two, and so on. The pattern lists here are a handful of
    segments long, so the branching cost is irrelevant and the readability is
    worth more than an optimised automaton nobody will re-derive.
    """
    if not pattern_parts:
        return not path_parts
    head, *rest = pattern_parts
    if head == "**":
        # `**` may absorb any number of leading path segments, including none.
        for taken in range(len(path_parts) + 1):
            if _match_with_double_star(path_parts[taken:], rest):
                return True
        return False
    if not path_parts:
        return False
    if not fnmatch.fnmatch(path_parts[0], head):
        return False
    return _match_with_double_star(path_parts[1:], rest)


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
