#!/usr/bin/env python3
"""Assert the entity registry still describes the architecture that is deployed.

WHY THIS EXISTS

`src/entities/platform.py` is the platform's identity source of truth. When
Locations migrated from in-process `src/` routers to standalone `workers/`
services, the registry was not updated with them. The result was measured on
2026-08-22: fifteen Locations pointed at a router `api.py` does not mount,
`src/academy/` did not exist at all, six Locations shared the single path
`src/studio/`, and 27 of 43 carried no `worker_port`.

None of that was visible from any output. `system_viewer._worker_catalog()`
emits a row only for a Location that has a port, so the Admin OS system view
showed 16 of 43 Locations and reported nothing about the other 27. Health
metadata resolves entities *by port*, so those 27 could not produce a health
block either. The view was not wrong. It was blind, and confidently so.

The absence of this check is why the drift happened, and why it would happen
again after any repair. So the check lands first and the repair is measured
against it -- a repair with no gate is a claim, not a result.

BASELINE

Landing a gate that fails on 42 pre-existing violations would block every
unrelated pull request, so known violations are recorded in
`config/estate/entity_registry_baseline.json` with the date and the reason.
CI fails on anything NEW. The repair drives the baseline to empty; when it is
empty this file becomes a plain gate with nothing to forgive.

Run `--write-baseline` to record the current state, `--check` to enforce.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.entities.platform import PLATFORM_ENTITIES  # noqa: E402

BASELINE = REPO / "config" / "estate" / "entity_registry_baseline.json"

# Locations that are deliberately not FastAPI workers. Each is a real part of
# the estate whose "path" is a frontend, a deploy tree or a test suite, so
# "mounted in api.py or backed by workers/" is the wrong question to ask of it.
# Listed explicitly rather than baselined: a baseline says "known debt, fix it",
# and these are correct as they stand.
NON_WORKER_LOCATIONS = {
    "PID-ARC": "Arcadia is the web frontend (web/), not a worker",
    "PID-WRK": "The Workshop is Forgejo, deployed from deploy/forgejo/",
    "PID-TCP": "The Chaos Party's in-repo half is the test suite (tests/)",
    "PID-CTL": "The Citadel is the compose/Traefik deploy tree (deploy/)",
}
COMPOSE = REPO / "docker-compose.production.yml"
API = REPO / "api.py"


def _api_text() -> str:
    return API.read_text(encoding="utf-8") if API.exists() else ""


def _compose_text() -> str:
    return COMPOSE.read_text(encoding="utf-8") if COMPOSE.exists() else ""


def _router_is_mounted(worker_path: str, api: str) -> bool:
    """True if api.py imports from this package or mounts its router.

    Two spellings are accepted because the estate uses both: a direct
    `from src.x.routes import ...` and the `_x_router` include pattern.
    """
    pkg = worker_path.strip("/").replace("/", ".")
    leaf = worker_path.strip("/").split("/")[-1]
    if re.search(rf"\bfrom\s+{re.escape(pkg)}[\s.]", api):
        return True
    return bool(re.search(rf"_{re.escape(leaf)}_router\b", api))


def _live_worker_dir(worker_path: str) -> str | None:
    """The workers/ directory that supersedes this src/ path, if one exists."""
    leaf = worker_path.strip("/").split("/")[-1]
    workers = REPO / "workers"
    if not workers.is_dir():
        return None
    norm = leaf.replace("_", "-")
    for d in sorted(workers.iterdir()):
        if not d.is_dir():
            continue
        if d.name == norm or d.name == f"the-{norm}" or d.name == f"{norm}-service":
            return d.name
    return None


def _routed_ports(compose_text: str) -> set[int]:
    """Every port compose actually routes, parsed rather than grepped.

    A regex over the whole file -- even one anchored on non-digit boundaries --
    still matches a port inside an image tag, a digest, or an unrelated numeric
    field, so `port-unrouted` could pass for a port compose never routes. That
    is the failure this guard exists to catch, so the guard must not commit it.

    Three places genuinely route a port: a published `ports:` mapping, a
    Traefik `loadbalancer.server.port` label, and a PORT-ish environment value.
    """
    routed: set[int] = set()
    try:
        doc = yaml.safe_load(compose_text) or {}
    except yaml.YAMLError:
        return routed
    for svc in (doc.get("services") or {}).values():
        if not isinstance(svc, dict):
            continue
        for entry in svc.get("ports") or []:
            # "8069:8069", "127.0.0.1:8069:8069", or {published: 8069}
            if isinstance(entry, dict):
                for key in ("published", "target"):
                    with contextlib.suppress(TypeError, ValueError):
                        routed.add(int(entry[key]))
            else:
                for part in str(entry).split("/")[0].split(":"):
                    if part.isdigit():
                        routed.add(int(part))
        labels = svc.get("labels") or []
        label_items = (
            labels.items()
            if isinstance(labels, dict)
            else ((x.split("=", 1) + [""])[:2] for x in labels if isinstance(x, str))
        )
        for key, value in label_items:
            if "loadbalancer.server.port" in str(key) and str(value).strip().isdigit():
                routed.add(int(str(value).strip()))
        env = svc.get("environment") or {}
        env_items = (
            env.items()
            if isinstance(env, dict)
            else ((x.split("=", 1) + [""])[:2] for x in env if isinstance(x, str))
        )
        for key, value in env_items:
            if str(key).upper().endswith("PORT") and str(value).strip().isdigit():
                routed.add(int(str(value).strip()))
    return routed


def collect_violations() -> list[dict]:
    api, compose = _api_text(), _compose_text()
    routed = _routed_ports(compose)
    violations: list[dict] = []
    by_path: dict[str, list[str]] = defaultdict(list)

    for entity in PLATFORM_ENTITIES.values():
        pid = entity.pid
        loc = entity.location
        wp = (getattr(entity, "worker_path", None) or "").strip()
        port = getattr(entity, "worker_port", None)

        if not wp:
            # A Location that declares NOTHING must not pass by declaring
            # nothing. Every check below is guarded by `if wp:`, so an absent
            # worker_path used to mean an absent verdict -- the guard built to
            # catch a registry describing less than it should, silently
            # accepting the emptiest possible description. That is exactly how
            # the original drift went unseen: 27 of 43 Locations carried no
            # port, and no output said so.
            if pid not in NON_WORKER_LOCATIONS:
                violations.append(
                    {
                        "rule": "metadata-missing",
                        "pid": pid,
                        "location": loc,
                        "detail": (
                            "no worker_path; a Location that is not in "
                            "NON_WORKER_LOCATIONS must say where it lives"
                        ),
                    }
                )
            continue

        if wp:
            by_path[wp.rstrip("/")].append(f"{pid} ({loc})")

            # 1. the path must exist on disk
            try:
                path_exists = (REPO / wp.rstrip("/")).exists()
            except (OSError, ValueError):
                # An embedded null byte or an over-long name raises instead of
                # returning False. Treat it as missing -- unreadable is not
                # the same as fine.
                path_exists = False
            if not path_exists:
                violations.append(
                    {
                        "rule": "path-missing",
                        "pid": pid,
                        "location": loc,
                        "detail": f"worker_path {wp!r} does not exist on disk",
                    }
                )
            # 2. it must be served -- mounted in api.py, or a live workers/ dir
            elif pid in NON_WORKER_LOCATIONS:
                pass  # correct by design -- see NON_WORKER_LOCATIONS
            elif not _router_is_mounted(wp, api) and not _live_worker_dir(wp):
                violations.append(
                    {
                        "rule": "path-unserved",
                        "pid": pid,
                        "location": loc,
                        "detail": f"worker_path {wp!r} is neither mounted in api.py "
                        f"nor backed by a workers/ directory",
                    }
                )
            elif wp.startswith("src/") and not _router_is_mounted(wp, api):
                # Only a src/ path that api.py does not mount is stale. A path
                # already pointing at workers/ is correct BY DESIGN -- a
                # standalone worker is not supposed to be mounted in api.py,
                # and flagging it would make this gate the very thing it
                # exists to catch: a check that reports confidently and wrongly.
                live = _live_worker_dir(wp)
                violations.append(
                    {
                        "rule": "path-superseded",
                        "pid": pid,
                        "location": loc,
                        "detail": f"worker_path {wp!r} is a src/ router api.py does "
                        f"not mount; workers/{live}/ is the live service",
                    }
                )

        # 4. a port must be set wherever compose routes one
        if pid in NON_WORKER_LOCATIONS:
            pass
        elif not port:
            leaf = _live_worker_dir(wp) if wp else None
            if leaf and re.search(rf"^  {re.escape(leaf)}:", compose, re.M):
                violations.append(
                    {
                        "rule": "port-unset",
                        "pid": pid,
                        "location": loc,
                        "detail": f"no worker_port, but compose routes service {leaf!r} "
                        f"-- this Location is invisible to the Admin OS "
                        f"worker map and to health metadata",
                    }
                )
        elif port not in routed:
            violations.append(
                {
                    "rule": "port-unrouted",
                    "pid": pid,
                    "location": loc,
                    "detail": f"worker_port {port} appears nowhere in compose",
                }
            )

    # 3. no two Locations may share a path -- a shared path cannot identify either
    for path, holders in sorted(by_path.items()):
        if len(holders) > 1:
            violations.append(
                {
                    "rule": "path-shared",
                    "pid": "-",
                    "location": ", ".join(holders),
                    "detail": f"{len(holders)} Locations share worker_path {path!r}; "
                    f"the registry cannot tell them apart",
                }
            )

    return violations


def _key(v: dict) -> str:
    return f"{v['rule']}|{v['pid']}|{v['location']}"


def load_baseline() -> set[str]:
    if not BASELINE.exists():
        return set()
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    return {_key(v) for v in data.get("accepted", [])}


def write_baseline(violations: list[dict]) -> None:
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(
        json.dumps(
            {
                "recorded": date.today().isoformat(),
                "why": (
                    "Pre-existing registry drift, measured before the conformance guard "
                    "existed. CI fails on anything NEW; these are the known set the "
                    "repair has to empty. An entry removed from here can never come back "
                    "silently -- it becomes a hard failure."
                ),
                "accepted": sorted(violations, key=_key),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


RULE_ORDER = [
    "path-missing",
    "path-shared",
    "path-unserved",
    "path-superseded",
    "port-unset",
    "port-unrouted",
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="fail on new violations")
    ap.add_argument(
        "--write-baseline", action="store_true", help="record current violations as accepted"
    )
    args = ap.parse_args()

    violations = collect_violations()
    grouped: dict[str, list[dict]] = defaultdict(list)
    for v in violations:
        grouped[v["rule"]].append(v)

    print(f"entity registry conformance -- {len(PLATFORM_ENTITIES)} Locations checked")
    print()
    for rule in RULE_ORDER:
        rows = grouped.get(rule, [])
        if not rows:
            continue
        print(f"  {rule}  ({len(rows)})")
        for v in rows:
            print(f"      {v['pid']:<9} {v['location'][:34]:<36} {v['detail']}")
        print()

    if args.write_baseline:
        write_baseline(violations)
        print(f"baseline written: {len(violations)} accepted violations")
        return 0

    accepted = load_baseline()
    new = [v for v in violations if _key(v) not in accepted]
    stale = accepted - {_key(v) for v in violations}

    if stale:
        print(
            f"{len(stale)} baselined violation(s) no longer occur -- "
            f"re-run --write-baseline to shrink the baseline:"
        )
        for s in sorted(stale):
            print(f"      {s}")
        print()

    if not args.check:
        print(f"total {len(violations)} violation(s); {len(accepted)} baselined")
        return 0

    if new:
        print(f"FAILED: {len(new)} violation(s) not in the baseline")
        for v in new:
            print(f"      {v['rule']:<17} {v['location']}: {v['detail']}")
        return 1

    print(
        f"entity registry conformance: PASSED "
        f"({len(violations)} known, 0 new{'; ' + str(len(stale)) + ' fixed' if stale else ''})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
