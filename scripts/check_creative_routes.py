#!/usr/bin/env python3
"""Verify every creative capability's endpoint exists in the *deployed* image.

Why this check exists
---------------------
`src/creative/routing.py` claims to describe the estate as measured. Its first
version measured the wrong files. Several creative Locations ship two FastAPI
applications — a thin `main.py` and a much richer `worker.py` — and the
Dockerfile `CMD` decides which one a container runs. Reading `worker.py`
because it is the larger and more interesting file produced a route table
naming endpoints that no running service exposes: Warp Radio marked ROUTED at
`POST /playlists` when its deployed image serves no POST at all.

`CLAUDE.md` already records this exact trap for the port defects of issue
#188 — "re-verified against each worker's actual Dockerfile CMD, not just its
Python default". A route table is the same problem one level up, so this is
the same verification, automated.

What it does
------------
For each capability that names an endpoint: read the worker's Dockerfile
`CMD`, resolve which module it runs, collect the routes that module declares
(following a router factory imported from a sibling module in the same
directory), and confirm the capability's method and path are among them.

It is deliberately conservative. When the entrypoint cannot be resolved the
check reports UNVERIFIABLE and fails, rather than passing on the assumption
that the route is probably fine — an unverifiable claim in a route table is
the thing this check exists to stop.
"""

from __future__ import annotations

import ast
import json
import re
import shlex
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.creative.routing import CAPABILITIES, RouteStatus  # noqa: E402

_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


def entrypoint_for(worker_dir: Path) -> tuple[Path | None, str]:
    """Resolve the module a container actually runs, from its Dockerfile CMD.

    Returns (path, explanation). The path is None when the CMD cannot be read
    or does not name a Python module this checker understands.
    """
    dockerfile = worker_dir / "Dockerfile"
    if not dockerfile.exists():
        return None, f"{worker_dir.name}: no Dockerfile"

    cmd: str | None = None
    for line in dockerfile.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith(("CMD", "ENTRYPOINT")):
            cmd = stripped
    if cmd is None:
        return None, f"{worker_dir.name}: Dockerfile declares no CMD or ENTRYPOINT"

    body = cmd.split(None, 1)[1].strip()
    if body.startswith("["):
        try:
            argv = [str(a) for a in json.loads(body)]
        except json.JSONDecodeError:
            return None, f"{worker_dir.name}: CMD is not valid JSON: {body}"
    else:
        argv = shlex.split(body)

    # `python main.py` / `python3 worker.py`
    for arg in argv:
        if arg.endswith(".py"):
            module = worker_dir / arg
            return (module, "") if module.exists() else (None, f"CMD names missing {arg}")

    # `uvicorn main:app --host ...`
    for arg in argv:
        if ":" in arg and not arg.startswith("-"):
            module = worker_dir / f"{arg.split(':', 1)[0]}.py"
            if module.exists():
                return module, ""

    return None, f"{worker_dir.name}: cannot tell what CMD runs: {' '.join(argv)}"


def _decorator_routes(tree: ast.AST, prefixes: dict[str, str]) -> set[tuple[str, str]]:
    """Every (METHOD, path) declared by an @app./@router. decorator."""
    found: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
                continue
            method = dec.func.attr.lower()
            if method not in _HTTP_METHODS or not dec.args:
                continue
            first = dec.args[0]
            if not isinstance(first, ast.Constant) or not isinstance(first.value, str):
                continue
            owner = getattr(dec.func.value, "id", "")
            found.add((method.upper(), prefixes.get(owner, "") + first.value))
    return found


def _router_prefixes(tree: ast.AST) -> dict[str, str]:
    """Variable name -> prefix, for `x = APIRouter(prefix="/y")`.

    A prefix that is not a plain literal is skipped rather than guessed; the
    resulting missing route surfaces as a failure, which is the safe way round.
    """
    prefixes: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        func = node.value.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name != "APIRouter":
            continue
        prefix = ""
        for kw in node.value.keywords:
            if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                prefix = str(kw.value.value)
        for target in node.targets:
            if isinstance(target, ast.Name):
                prefixes[target.id] = prefix
    return prefixes


def routes_of(module: Path, _seen: set[Path] | None = None) -> set[tuple[str, str]]:
    """Routes a module declares, following router factories in the same directory.

    TranceFlow's deployed `main.py` builds its app from
    `router._make_tranceflow_router`, so a checker that read only the
    entrypoint would find one health route and call every real endpoint
    missing.
    """
    seen = _seen if _seen is not None else set()
    if module in seen:
        return set()
    seen.add(module)

    tree = ast.parse(module.read_text(), filename=str(module))
    found = _decorator_routes(tree, _router_prefixes(tree))

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            sibling = module.parent / f"{node.module.split('.')[0]}.py"
            if sibling.exists():
                found |= routes_of(sibling, seen)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                sibling = module.parent / f"{alias.name.split('.')[0]}.py"
                if sibling.exists():
                    found |= routes_of(sibling, seen)
    return found


def _path_matches(declared: str, wanted: str) -> bool:
    """Compare paths, treating `{param}` segments as wildcards."""
    pattern = re.sub(
        r"\{[^}]+\}", "[^/]+", re.escape(declared).replace(r"\{", "{").replace(r"\}", "}")
    )
    pattern = re.sub(r"\{[^}]+\}", "[^/]+", pattern)
    return re.fullmatch(pattern, wanted) is not None


# Imaginarium's fan-out addresses sibling Locations by service key. The keys
# are its SERVICE_URLS names; the values are the worker directories, so a leg
# can be checked against the same deployed-entrypoint truth as a capability.
_FAN_OUT_DIRS = {
    "photo_studio": "workers/sashas-photo-studio",
    "fabulousa": "workers/fabulousa-service",
    "tranceflow": "workers/tranceflow",
    "tateking": "workers/tateking",
    "warp_radio": "workers/warp-radio",
    "the_studio": "workers/the-studio",
}


def _fan_out_legs() -> list[dict]:
    """Read FAN_OUT_LEGS out of the worker without importing it.

    The module raises at import when INTERNAL_SECRET is unset, which is
    correct behaviour for a worker and unhelpful for a static check, so the
    table is read from the AST instead.
    """
    source = (REPO / "workers" / "imaginarium" / "worker.py").read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
            continue
        if node.target.id != "FAN_OUT_LEGS" or node.value is None:
            continue
        legs = []
        for element in node.value.elts:
            leg = {}
            for key, value in zip(element.keys, element.values, strict=True):
                if isinstance(key, ast.Constant) and isinstance(value, ast.Constant):
                    leg[key.value] = value.value
            legs.append(leg)
        return legs
    raise SystemExit("check_creative_routes: FAN_OUT_LEGS not found in imaginarium/worker.py")


def _check_endpoint(label: str, worker_dir_name: str, method: str, path: str) -> str | None:
    """Return a problem description, or None when the endpoint is served."""
    worker_dir = REPO / worker_dir_name
    if not worker_dir.is_dir():
        return f"{label}: worker_dir {worker_dir_name} does not exist"

    module, why = entrypoint_for(worker_dir)
    if module is None:
        return f"{label}: UNVERIFIABLE — {why}"

    declared = routes_of(module)
    if any(m == method and _path_matches(p, path) for m, p in declared):
        return None
    same = sorted(p for m, p in declared if m == method)
    return (
        f"{label}: {method} {path} is not served by {module.relative_to(REPO)} "
        f"(the module its Dockerfile CMD runs). {method} routes there: "
        f"{', '.join(same) or 'none'}"
    )


def main(argv: list[str] | None = None) -> int:
    problems: list[str] = []
    checked = 0

    for cap in CAPABILITIES:
        if not cap.path:
            # ABSENT capabilities name no endpoint. There is nothing to verify,
            # and inventing one would defeat the point of recording absence.
            continue
        if not cap.worker_dir:
            problems.append(
                f"{cap.id}: names {cap.method} {cap.path} but no worker_dir to check it against"
            )
            continue

        worker_dir = REPO / cap.worker_dir
        if not worker_dir.is_dir():
            problems.append(f"{cap.id}: worker_dir {cap.worker_dir} does not exist")
            continue

        checked += 1
        problem = _check_endpoint(cap.id, cap.worker_dir, cap.method, cap.path)
        if problem:
            problems.append(problem)

    # The same verification for Imaginarium's fan-out. A leg pointing at an
    # un-deployed route fails on every brief and marks the project "partial",
    # which reads as an outage rather than as an unbuilt feature.
    for leg in _fan_out_legs():
        label = f"fan-out leg {leg.get('key', '?')}"
        key, path = leg.get("service", ""), leg.get("path", "")
        if not key or not path:
            problems.append(f"{label}: incomplete declaration")
            continue
        directory = _FAN_OUT_DIRS.get(key)
        if directory is None:
            problems.append(f"{label}: unknown service key {key!r}")
            continue
        checked += 1
        problem = _check_endpoint(label, directory, "POST", path)
        if problem:
            problems.append(problem)

    if problems:
        print("Creative route check: FAILED")
        for p in problems:
            print(f"  [ERROR] {p}")
        print()
        print(
            "Each capability's endpoint must exist in the module the worker's "
            "Dockerfile CMD actually runs — not in a sibling worker.py that no "
            "container executes."
        )
        return 1

    absent = sum(1 for c in CAPABILITIES if c.status is RouteStatus.ABSENT)
    print(
        f"Creative route check: PASSED — {checked} endpoint(s) verified against their "
        f"deployed entrypoint, {absent} capability recorded as having none"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
