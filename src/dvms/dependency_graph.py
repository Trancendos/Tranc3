"""Which Locations share this dependency, and what does each Location depend on?

WHY THIS EXISTS

`surface_owner.py` answers "who owns this manifest". That is one direction of a
two-way question the platform owner asked for directly: open a Location's
record, go to its dependencies, pick one, and see every OTHER service that
depends on it.

Without the reverse direction a finding reads as one Location's problem. With
it, `starlette` is visibly a **shared** dependency, an upgrade is visibly a
change with a blast radius, and "which Locations does this affect" stops being
a question somebody answers by grepping.

WHAT IT IS AND IS NOT

It is a DECLARED-dependency graph, built from manifests. It is not a resolved
one: `requirements.txt` names direct dependencies and the transitive closure
lives in the installed environment, which this deliberately does not read —
resolving would need a network and would make a topology query depend on PyPI
being up.

So the graph answers "which Locations DECLARE this package" exactly, and
"which Locations are affected by a vulnerability in it" as a lower bound. That
distinction is recorded on every result rather than left for a reader to
discover, because a lower bound presented as a total is the kind of number that
gets trusted and then quietly under-reports.
"""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List, Optional, Set

from src.dvms.surface_owner import resolve_surface

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# A requirement line's package name: everything before the first version
# specifier, extra, marker or comment. `-r other.txt` and `-e .` are directives,
# not packages, and are skipped rather than recorded as a dependency named "-r".
_REQ_NAME = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*(?:[<>=!~;]|$)"
)

# Directories whose manifests describe somebody else's tree.
_EXCLUDED = ("node_modules", ".git", ".venv", "venv", "__pycache__", "compliance/magna-carta")


@dataclass
class PackageUsage:
    """One package, and everywhere it is declared."""

    package: str
    ecosystem: str
    locations: List[str] = field(default_factory=list)
    manifests: List[str] = field(default_factory=list)
    #: Manifests whose owning Location could not be resolved. Always reported,
    #: never folded into `locations` — a blast radius that quietly omits the
    #: services it could not place is worse than one that says it is partial.
    unrouted_manifests: List[str] = field(default_factory=list)

    @property
    def is_shared(self) -> bool:
        return len(self.locations) > 1

    def to_dict(self) -> Dict:
        return {
            "package": self.package,
            "ecosystem": self.ecosystem,
            "locations": self.locations,
            "manifests": self.manifests,
            "unrouted_manifests": self.unrouted_manifests,
            "shared": self.is_shared,
            "note": (
                "DECLARED dependencies only — the transitive closure is not resolved, "
                "so this is a lower bound on the Locations a vulnerability reaches."
            ),
        }


def _excluded(path: str) -> bool:
    return any(part in path for part in _EXCLUDED)


def _pip_packages(path: str) -> Set[str]:
    """Declared package names in one requirements file."""
    found: Set[str] = set()
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                line = raw.split("#", 1)[0].strip()
                if not line or line.startswith("-"):
                    continue
                match = _REQ_NAME.match(line)
                if match:
                    found.add(match.group("name").lower())
    except OSError:
        return set()
    return found


def _npm_packages(path: str) -> Set[str]:
    """Declared dependencies in one package.json, both runtime and dev.

    Dev dependencies are included on purpose: a build-time package with a
    vulnerability still runs on a machine holding this estate's source and
    tokens, and excluding them is how a supply-chain compromise gets classed as
    out of scope.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, ValueError):
        return set()
    if not isinstance(document, dict):
        return set()
    found: Set[str] = set()
    for section in ("dependencies", "devDependencies", "optionalDependencies"):
        block = document.get(section)
        if isinstance(block, dict):
            found.update(str(name).lower() for name in block)
    return found


def _walk(patterns) -> List[str]:
    out: List[str] = []
    for root, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [
            d for d in dirs if d not in {"node_modules", ".git", ".venv", "venv", "__pycache__"}
        ]
        for name in files:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, REPO_ROOT).replace(os.sep, "/")
            if _excluded(rel):
                continue
            if any(re.fullmatch(pattern, name) for pattern in patterns):
                out.append(rel)
    return sorted(out)


@lru_cache(maxsize=1)
def build_graph() -> Dict[str, PackageUsage]:
    """{package: PackageUsage} across every manifest in the estate."""
    graph: Dict[str, PackageUsage] = {}
    by_package: Dict[str, Set[str]] = defaultdict(set)
    manifests_of: Dict[str, Set[str]] = defaultdict(set)
    unrouted_of: Dict[str, Set[str]] = defaultdict(set)
    ecosystem_of: Dict[str, str] = {}

    sources = [(rel, "pip", _pip_packages) for rel in _walk([r"requirements.*\.txt"])]
    sources += [(rel, "npm", _npm_packages) for rel in _walk([r"package\.json"])]

    for rel, ecosystem, reader in sources:
        owner = resolve_surface(rel if ecosystem == "pip" else os.path.dirname(rel) or ".")
        for package in reader(os.path.join(REPO_ROOT, rel)):
            key = f"{ecosystem}:{package}"
            ecosystem_of[key] = ecosystem
            manifests_of[key].add(rel)
            if owner.responsible:
                by_package[key].add(owner.responsible)
            else:
                unrouted_of[key].add(rel)

    for key, ecosystem in ecosystem_of.items():
        graph[key] = PackageUsage(
            package=key.split(":", 1)[1],
            ecosystem=ecosystem,
            locations=sorted(by_package.get(key, set())),
            manifests=sorted(manifests_of[key]),
            unrouted_manifests=sorted(unrouted_of.get(key, set())),
        )
    return graph


def usage(package: str, ecosystem: str = "pip") -> Optional[PackageUsage]:
    """Everywhere one package is declared — the reverse lookup."""
    return build_graph().get(f"{ecosystem}:{package.lower()}")


def dependencies_of(location: str) -> Dict[str, List[str]]:
    """{ecosystem: [packages]} this Location declares.

    The forward direction: open a Location's record and see what it depends on.
    """
    out: Dict[str, Set[str]] = defaultdict(set)
    for entry in build_graph().values():
        if location in entry.locations:
            out[entry.ecosystem].add(entry.package)
    return {ecosystem: sorted(names) for ecosystem, names in sorted(out.items())}


def shared_packages(minimum: int = 2) -> List[PackageUsage]:
    """Packages declared by `minimum` or more Locations, widest blast radius first.

    This is the list that decides upgrade order. A package in twenty Locations
    is a different kind of change from one in a single worker, and treating
    them the same is how a routine bump becomes an estate-wide outage.
    """
    entries = [e for e in build_graph().values() if len(e.locations) >= minimum]
    return sorted(entries, key=lambda e: (-len(e.locations), e.ecosystem, e.package))


def blast_radius(package: str, ecosystem: str = "pip") -> Dict:
    """What a change to this package reaches. The question a Change record asks."""
    entry = usage(package, ecosystem)
    if entry is None:
        return {
            "package": package,
            "ecosystem": ecosystem,
            "known": False,
            "reason": "not declared in any manifest in this estate",
        }
    result = entry.to_dict()
    result["known"] = True
    return result


def reset_cache() -> None:
    build_graph.cache_clear()
