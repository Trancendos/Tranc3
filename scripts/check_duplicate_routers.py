#!/usr/bin/env python3
"""Guard against the "two sources of truth" dead-router pattern recurring.

`docs/governance/MONOLITH-EXTRACTION-FINDINGS.md` documents a real, repeated bug
class in this repo: a `src/<name>/routes.py` router gets extracted into a real,
deployed `workers/<name>/` nanoservice, but the old in-process
`app.include_router(...)` mount in `api.py` is never removed — leaving two live
implementations of the same service reachable at once. 7 were found and removed
in one pass (taimra, studio, lab, chronos, devocity, artifactory, vrar3d).

An 8th, Resonate, was *also* removed that same pass and had to be reverted: the
worker turned out to implement a different feature (scoring) than the router it
was meant to replace (escalation) — not a superset. That mistake happened
because the only check run was "does anything else import this router object",
which cannot tell a true duplicate from two services that merely share a name.
**This script cannot either** — matching HTTP route paths/behavior requires
reading the code, which is exactly what caught Resonate. So this script does
NOT auto-remove anything. It only flags routers that *look* like the same
duplicate pattern (mounted in api.py + a same-service worker is live in
compose + nothing else in-process imports the router) so a human/agent
investigates with the same rigor as the original sweep, and it fails loudly if
a router already confirmed to be a genuine duplicate reappears without ever
being unmounted.

Exit status: 0 when nothing new needs investigating, 1 otherwise.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
API_PY = ROOT / "api.py"
COMPOSE = ROOT / "docker-compose.production.yml"

# Router variable name (as used in `app.include_router(_x_router)`) -> the
# src module it's imported from and the compose service name of the worker
# that (claims to) supersede it. Only services actually investigated belong
# here — this is a curated map, not a name-guessing heuristic, because name
# guessing is exactly how the Resonate false-positive would have been missed
# in the *other* direction (assuming "same name" implies "same behavior").
#
# Add an entry here only after doing the same check the findings doc
# describes: confirm the worker's actual route paths cover the router's.
ROUTER_TO_WORKER: dict[str, tuple[str, str]] = {
    "_resonate_router": ("src.resonate.routes", "resonate"),
    "_imind_router": ("src.imind.routes", "imind"),
    "_basement_router": ("src.basement.routes", "basement"),
    "_cryptex_router": ("src.cryptex.routes", "cryptex"),
    "_library_router": ("src.library.routes", "library-service"),
    "_search_router": ("src.routers.search_api", "search-service"),
    "_turingshub_router": ("src.personality.turingshub.routes", "turings-hub-service"),
    # Confirmed-safe removals from the 2026-08-08 sweep — kept here (even
    # though `_mounted_routers()` will skip them while unmounted) so that if
    # one is ever re-added to api.py without a fresh equivalence check, this
    # script fails immediately instead of the mount silently going stale
    # again.
    "_taimra_router": ("src.taimra.routes", "taimra"),
    "_studio_router": ("src.studio.routes", "the-studio"),
    "_lab_router": ("src.lab.routes", "the-lab"),
    "_chronos_router": ("src.chronos.routes", "cron-service"),
    "_devocity_router": ("src.devocity.routes", "devocity"),
    "_artifactory_router": ("src.artifactory.routes", "artifactory-service"),
    "_vrar3d_router": ("src.vrar3d.routes", "vrar3d"),
}

# Routers where the in-process mount is known to be *intentionally* kept —
# real in-process callers, a verified non-equivalent worker, or genuinely
# core/load-bearing logic. Each needs a one-line reason so this table stays
# self-explanatory instead of becoming an unreviewed escape hatch.
KNOWN_COUPLED: dict[str, str] = {
    "_resonate_router": (
        "workers/resonate/ implements a different feature (scoring) than this "
        "router (escalation) — see MONOLITH-EXTRACTION-FINDINGS.md"
    ),
    "_imind_router": (
        "src/tranquility/wellbeing.py imports src.imind.protocol directly "
        "in-process; router-only removal not yet verified for HTTP equivalence"
    ),
    "_basement_router": (
        "src/observability/observatory.py calls get_basement() synchronously "
        "on the SECURITY/CRITICAL audit path — needs an HTTP bridge with "
        "explicit failure semantics before unmounting"
    ),
    "_cryptex_router": (
        "real in-process callers: section7/information_router.py, "
        "mcp/server.py, security/middleware.py"
    ),
    "_library_router": (
        "real in-process callers: section7/information_router.py, "
        "observability/library_pipeline.py, models/knowledge.py, "
        "event_bus/wiring.py"
    ),
    "_turingshub_router": (
        "core/load-bearing AI response pipeline dependency, not a "
        "nanoservice duplicate"
    ),
    "_search_router": (
        "PENDING VERIFICATION: MONOLITH-EXTRACTION-FINDINGS.md flags this as "
        "needing an HTTP-route-equivalence check against workers/search-service/ "
        "before any removal decision (not done yet) — kept mounted, not a "
        "confirmed keep"
    ),
}

INCLUDE_ROUTER_RE = re.compile(r"app\.include_router\((_\w+_router)\)")


def _mounted_routers() -> set[str]:
    return set(INCLUDE_ROUTER_RE.findall(API_PY.read_text(encoding="utf-8")))


def _compose_services() -> dict[str, dict]:
    services = yaml.safe_load(COMPOSE.read_text(encoding="utf-8")).get("services") or {}
    return {name: (svc or {}) for name, svc in services.items()}


def _has_external_caller(src_module: str) -> list[str]:
    """Grep for in-process importers of `src_module` outside api.py and tests/."""
    dotted = re.escape(src_module)
    pattern = rf"from {dotted} import|import {dotted}\b"
    try:
        result = subprocess.run(
            ["grep", "-rlE", pattern, "--include=*.py", str(ROOT / "src"), str(ROOT / "workers")],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        print("ERROR: grep not available", file=sys.stderr)
        return ["<grep unavailable>"]

    module_path = ROOT / (src_module.replace(".", "/") + ".py")
    callers = []
    for line in result.stdout.splitlines():
        path = Path(line)
        if path.resolve() == module_path.resolve():
            continue
        if "tests" in path.parts:
            continue
        callers.append(str(path.relative_to(ROOT)))
    return callers


def main() -> int:
    mounted = _mounted_routers()
    compose = _compose_services()

    problems: list[str] = []
    checked = 0

    for router_var, (src_module, worker_name) in ROUTER_TO_WORKER.items():
        if router_var not in mounted:
            # Was removed (or renamed) — nothing to guard here anymore.
            continue

        worker_svc = compose.get(worker_name)
        if worker_svc is None or "build" not in worker_svc:
            # The claimed worker isn't actually a deployed build target —
            # stale table entry, not a live duplicate risk. Warn, don't fail.
            print(
                f"NOTE: {router_var} -> {worker_name} in ROUTER_TO_WORKER but "
                f"'{worker_name}' has no live `build:` service in compose; "
                "table may be stale."
            )
            continue

        checked += 1
        callers = _has_external_caller(src_module)
        reason = KNOWN_COUPLED.get(router_var)

        if not callers and not reason:
            problems.append(
                f"  ✗ {router_var} ({src_module}) is mounted in api.py, "
                f"'{worker_name}' is live in compose, and no other in-process "
                f"code imports {src_module} — looks like the dead-duplicate "
                "pattern. Investigate with the same rigor as "
                "MONOLITH-EXTRACTION-FINDINGS.md (compare actual HTTP route "
                "paths, don't assume): either unmount it, or add it to "
                "KNOWN_COUPLED here with a reason."
            )
        elif callers and not reason:
            print(
                f"NOTE: {router_var} has in-process callers ({', '.join(callers)}) "
                "but no KNOWN_COUPLED entry explaining them — consider adding one "
                "for documentation."
            )

    if problems:
        print(
            f"check_duplicate_routers FAILED — {len(problems)} router(s) look like "
            "unremoved dead duplicates:",
            file=sys.stderr,
        )
        for p in problems:
            print(p, file=sys.stderr)
        return 1

    print(f"check_duplicate_routers OK ({checked} tracked router/worker pairs checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
