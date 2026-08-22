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
from pathlib import Path, PurePosixPath

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


def _pairs(value) -> list[tuple[str, str]]:
    """compose accepts a mapping OR a list of "KEY=VALUE" strings for both
    `labels:` and `environment:`. Normalise once instead of twice."""
    if isinstance(value, dict):
        return [(str(k), str(v)) for k, v in value.items()]
    if isinstance(value, list):
        return [
            ((x.split("=", 1) + [""])[0], (x.split("=", 1) + [""])[1])
            for x in value
            if isinstance(x, str)
        ]
    return []


def _ports_from_mapping(svc: dict) -> set[int]:
    """Published `ports:` -- "8069:8069", "127.0.0.1:8069:8069", {published: 8069}."""
    found: set[int] = set()
    entries = svc.get("ports")
    for entry in entries if isinstance(entries, list) else []:
        if isinstance(entry, dict):
            for key in ("published", "target"):
                with contextlib.suppress(KeyError, TypeError, ValueError):
                    found.add(int(entry[key]))
        else:
            for part in str(entry).split("/")[0].split(":"):
                if part.isascii() and part.isdigit():
                    found.add(int(part))
    return found


def _ports_from_traefik_labels(svc: dict) -> set[int]:
    """Traefik's `loadbalancer.server.port` -- how most workers are actually routed."""
    return {
        int(value.strip())
        for key, value in _pairs(svc.get("labels"))
        if "loadbalancer.server.port" in key and value.strip().isascii() and value.strip().isdigit()
    }


def _ports_from_environment(svc: dict) -> set[int]:
    """PORT-suffixed env values -- PORT, HIVE_PORT, CACHE_PORT and friends."""
    return {
        int(value.strip())
        for key, value in _pairs(svc.get("environment"))
        if key.upper().endswith("PORT") and value.strip().isascii() and value.strip().isdigit()
    }


def _routed_ports(compose_text: str) -> set[int]:
    """Every port compose actually routes, parsed rather than grepped.

    A regex over the whole file -- even one anchored on non-digit boundaries --
    still matches a port inside an image tag, a digest, or an unrelated numeric
    field, so `port-unrouted` could pass for a port compose never routes. That
    is the failure this guard exists to catch, so the guard must not commit it.

    Three places genuinely route a port, and each is its own extractor above: a
    published `ports:` mapping, a Traefik `loadbalancer.server.port` label, and
    a PORT-ish environment value.
    """
    try:
        doc = yaml.safe_load(compose_text)
    except yaml.YAMLError:
        return set()
    # `or {}` only rescues the FALSY non-mappings. A truthy scalar or list root
    # -- a compose file that is one string, or a YAML list -- reaches .get() and
    # raises AttributeError, and the same holds for a truthy non-mapping
    # `services:` value reaching .values(). An unparseable compose must make
    # this guard measure nothing, never crash it.
    if not isinstance(doc, dict):
        return set()
    services = doc.get("services")
    if not isinstance(services, dict):
        return set()

    routed: set[int] = set()
    for svc in services.values():
        if not isinstance(svc, dict):
            continue
        routed |= _ports_from_mapping(svc)
        routed |= _ports_from_traefik_labels(svc)
        routed |= _ports_from_environment(svc)
    return routed


def _violation(rule: str, pid: str, loc: str, detail: str) -> dict:
    return {"rule": rule, "pid": pid, "location": loc, "detail": detail}


def _path_violations(pid: str, loc: str, wp: str, api: str) -> list[dict]:
    """Everything that can be wrong with a Location's worker_path."""
    # Containment first, because the on-disk check CANNOT catch it:
    # `REPO / "/tmp"` is `/tmp`, not `<repo>/tmp` -- pathlib's `/` discards the
    # left side entirely when the right side is absolute -- and `/tmp` exists,
    # so an absolute worker_path would be certified valid while naming
    # something unrelated to this repository. `..` escapes the same way.
    escape = None
    if PurePosixPath(wp).is_absolute():
        escape = "is absolute"
    elif ".." in PurePosixPath(wp).parts:
        escape = "contains a '..' component"
    if escape:
        return [
            _violation(
                "path-escapes-repo",
                pid,
                loc,
                f"worker_path {wp!r} {escape}; a Location must live inside this repository",
            )
        ]

    try:
        exists = (REPO / wp.rstrip("/")).exists()
    except (OSError, ValueError):
        # An embedded null byte or an over-long name raises rather than
        # returning False. Unreadable is not the same as fine.
        exists = False
    if not exists:
        return [_violation("path-missing", pid, loc, f"worker_path {wp!r} does not exist on disk")]

    if pid in NON_WORKER_LOCATIONS:
        return []  # correct by design -- see NON_WORKER_LOCATIONS

    mounted = _router_is_mounted(wp, api)
    if not mounted and not _live_worker_dir(wp):
        return [
            _violation(
                "path-unserved",
                pid,
                loc,
                f"worker_path {wp!r} is neither mounted in api.py nor backed by a "
                f"workers/ directory",
            )
        ]
    if wp.startswith("src/") and not mounted:
        # Only a src/ path api.py does not mount is stale. A path already
        # pointing at workers/ is correct BY DESIGN -- a standalone worker is
        # not supposed to be mounted in api.py, and flagging it would make this
        # gate the very thing it exists to catch: a check that reports
        # confidently and wrongly.
        return [
            _violation(
                "path-superseded",
                pid,
                loc,
                f"worker_path {wp!r} is a src/ router api.py does not mount; "
                f"workers/{_live_worker_dir(wp)}/ is the live service",
            )
        ]
    return []


def _port_violations(pid, loc, wp, port, compose: str, routed: set[int]) -> list[dict]:
    """A port must be set wherever compose routes one, and must be one it routes."""
    if pid in NON_WORKER_LOCATIONS:
        return []
    if not port:
        leaf = _live_worker_dir(wp) if wp else None
        if leaf and re.search(rf"^  {re.escape(leaf)}:", compose, re.M):
            return [
                _violation(
                    "port-unset",
                    pid,
                    loc,
                    f"no worker_port, but compose routes service {leaf!r} -- this "
                    f"Location is invisible to the Admin OS worker map and to "
                    f"health metadata",
                )
            ]
        return []
    if port not in routed:
        return [
            _violation("port-unrouted", pid, loc, f"worker_port {port} appears nowhere in compose")
        ]
    return []


def collect_violations() -> list[dict]:
    api, compose = _api_text(), _compose_text()
    routed = _routed_ports(compose)
    violations: list[dict] = []
    by_path: dict[str, list[str]] = defaultdict(list)

    for entity in PLATFORM_ENTITIES.values():
        pid, loc = entity.pid, entity.location
        wp = (getattr(entity, "worker_path", None) or "").strip()
        port = getattr(entity, "worker_port", None)

        if not wp:
            # A Location that declares NOTHING must not pass by declaring
            # nothing. Every path rule needs a worker_path, so an absent one
            # used to mean an absent verdict -- the guard built to catch a
            # registry describing less than it should, silently accepting the
            # emptiest possible description. That is exactly how the original
            # drift went unseen: 27 of 43 Locations carried no port, and no
            # output said so.
            if pid not in NON_WORKER_LOCATIONS:
                violations.append(
                    _violation(
                        "metadata-missing",
                        pid,
                        loc,
                        "no worker_path; a Location that is not in "
                        "NON_WORKER_LOCATIONS must say where it lives",
                    )
                )
            continue

        by_path[wp.rstrip("/")].append(f"{pid} ({loc})")
        path_problems = _path_violations(pid, loc, wp, api)
        violations += path_problems
        # A path that escapes the repo is not a base to judge a port against.
        if not any(v["rule"] == "path-escapes-repo" for v in path_problems):
            violations += _port_violations(pid, loc, wp, port, compose, routed)

    # No two Locations may share a path -- a shared path identifies neither.
    for path, holders in sorted(by_path.items()):
        if len(holders) > 1:
            violations.append(
                _violation(
                    "path-shared",
                    "-",
                    ", ".join(holders),
                    f"{len(holders)} Locations share worker_path {path!r}; "
                    f"the registry cannot tell them apart",
                )
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
