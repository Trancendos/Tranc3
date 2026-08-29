"""What else breaks when this service does — and how much of that we actually know.

The ITIL4-AILP architecture prices every incident on blast radius: which
business services are upstream, which systems downstream, how many users are
affected. That question needs a dependency graph. This estate has one, and it
is mostly empty.

Measured, not assumed
---------------------
    92 services in the EA workbook
    10 have any inbound dependency recorded
    82 have none at all
    86 of those inbound edges point at one service (Infinity, the auth layer)

So a traversal that simply reports what it finds would answer "nothing depends
on this" for **89% of the estate**, and an incident prioritiser trusting that
number would quietly downgrade real P1s. The graph's sparseness is not a
detail to mention in a docstring; it is the single most important thing a
caller needs to know, so it is a field on every result.

`BlastRadius.has_dependency_data` is False when the origin has no recorded
inbound edges. In that state `affected` is empty and **means nothing** —
`unknown_rather_than_empty` says so directly. The Enhanced Direction's
instruction is the one followed here: use graph traversal for blast radius,
but never assume graph completeness, and always report the unknown portion
alongside the known one.

Two sources, both used
----------------------
`02_service_inventory.csv`'s `DependsOnServices` column covers all 92 services
but names only 10 distinct targets. `15_dependencies.csv` is a proper edge
table with strength, criticality and failure impact — and holds 7 edges across
6 sources, covering the anchor services only. Neither is sufficient alone;
both are read, and a dependency recorded in both is merged into one edge
carrying both sources, so a reader can tell a richly-described dependency
from a bare reference without losing the description to the duplicate.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from typing import Dict, Optional, Set, Tuple

from src.cmdb.identity import (
    IdentityResolutionError,
    ServiceIdentity,
    resolve,
)
from src.cmdb.identity import (
    _index as _identity_index,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_EDGE_TABLE = os.path.join(REPO_ROOT, "docs", "architecture", "ea-workbook", "15_dependencies.csv")

#: How far a traversal will walk. Beyond this the transitive claim is weaker
#: than the noise it adds — on a graph this sparse, a 4-hop path is a story.
DEFAULT_MAX_HOPS = 3


class Confidence(str, Enum):
    """How much weight a caller may put on one affected node."""

    #: A directly recorded edge. Something says, in the workbook, that this
    #: service depends on the origin.
    KNOWN = "known"
    #: Reached by following more than one recorded edge. Each hop is recorded,
    #: but the *combination* is inferred and no one has verified it end to end.
    PROBABLE = "probable"


class EdgeSource(str, Enum):
    """Which workbook file recorded the dependency."""

    #: 02_service_inventory.csv `DependsOnServices` — a bare reference, no
    #: strength or failure impact.
    INVENTORY = "service_inventory"
    #: 15_dependencies.csv — carries strength, criticality and failure impact.
    EDGE_TABLE = "dependency_table"


@dataclass(frozen=True)
class AffectedService:
    """One service the origin's failure would reach."""

    service_id: str
    service_name: str
    location: Optional[str]
    tier3_ai: Optional[str]
    tier2_prime: Optional[str]
    hops: int
    #: The chain walked to get here, origin first.
    path: Tuple[str, ...]
    confidence: Confidence
    sources: Tuple[EdgeSource, ...]
    criticality_code: str = ""
    failure_impact: str = ""

    def to_dict(self) -> dict:
        return {
            "service_id": self.service_id,
            "service_name": self.service_name,
            "location": self.location,
            "tier3_ai": self.tier3_ai,
            "tier2_prime": self.tier2_prime,
            "hops": self.hops,
            "path": list(self.path),
            "confidence": self.confidence.value,
            "sources": [s.value for s in self.sources],
            "criticality_code": self.criticality_code,
            "failure_impact": self.failure_impact,
        }


@dataclass(frozen=True)
class EstateCoverage:
    """How much of the estate has any dependency data at all.

    Returned with every blast radius so a caller never has to go and find out
    separately how much the answer is worth.
    """

    services: int
    with_inbound_edges: int
    without_inbound_edges: int

    @property
    def fraction_covered(self) -> float:
        return self.with_inbound_edges / self.services if self.services else 0.0

    def to_dict(self) -> dict:
        return {
            "services": self.services,
            "with_inbound_edges": self.with_inbound_edges,
            "without_inbound_edges": self.without_inbound_edges,
            "fraction_covered": round(self.fraction_covered, 4),
        }


@dataclass(frozen=True)
class BlastRadius:
    """What a failure of `origin` would reach, and how far that is trustworthy."""

    origin: ServiceIdentity
    affected: Tuple[AffectedService, ...] = field(default_factory=tuple)
    #: False when nothing in either workbook file records anything depending on
    #: the origin. `affected` is then empty and carries no information.
    has_dependency_data: bool = False
    coverage: EstateCoverage = field(default_factory=lambda: EstateCoverage(0, 0, 0))
    max_hops: int = DEFAULT_MAX_HOPS

    @property
    def unknown_rather_than_empty(self) -> bool:
        """True when 'nothing affected' means 'nothing recorded'.

        The distinction this module exists for. An incident prioritiser that
        treats this as a genuine zero will downgrade a real P1 — 82 of the
        estate's 92 services are in this state.
        """
        return not self.has_dependency_data

    @property
    def known(self) -> Tuple[AffectedService, ...]:
        return tuple(a for a in self.affected if a.confidence is Confidence.KNOWN)

    @property
    def probable(self) -> Tuple[AffectedService, ...]:
        return tuple(a for a in self.affected if a.confidence is Confidence.PROBABLE)

    @property
    def locations(self) -> Tuple[str, ...]:
        """Distinct Locations touched, for routing rather than counting."""
        return tuple(sorted({a.location for a in self.affected if a.location}))

    @property
    def caveat(self) -> str:
        """One sentence a human should read before acting on this."""
        if self.unknown_rather_than_empty:
            return (
                f"No dependency data recorded for {self.origin.service_id}. This is "
                f"NOT a finding that nothing depends on it — "
                f"{self.coverage.without_inbound_edges} of "
                f"{self.coverage.services} services are in the same state."
            )
        if self.origin.location_is_ambiguous:
            return (
                f"{self.origin.location} owns "
                f"{self.origin.location_service_count} services; this radius "
                f"covers {self.origin.service_id} only. Use "
                f"services_for_location() to widen it."
            )
        return (
            f"Based on {self.coverage.with_inbound_edges} of "
            f"{self.coverage.services} services having any recorded dependency. "
            f"Absent nodes are unverified, not absent."
        )

    def to_dict(self) -> dict:
        return {
            "origin": {
                "service_id": self.origin.service_id,
                "location": self.origin.location,
                "tier3_ai": self.origin.tier3_ai or None,
                "location_is_ambiguous": self.origin.location_is_ambiguous,
            },
            "has_dependency_data": self.has_dependency_data,
            "unknown_rather_than_empty": self.unknown_rather_than_empty,
            "affected_count": len(self.affected),
            "known": [a.to_dict() for a in self.known],
            "probable": [a.to_dict() for a in self.probable],
            "locations": list(self.locations),
            "coverage": self.coverage.to_dict(),
            "max_hops": self.max_hops,
            "caveat": self.caveat,
        }


@dataclass(frozen=True)
class _Edge:
    """target depends on source.

    `sources` is plural because both workbook files record some of the same
    dependencies. Keeping only the first one seen discards the edge table's
    criticality and failure impact for every edge the inventory also names —
    which is every edge the edge table has. They are merged instead.
    """

    source: str
    target: str
    sources: Tuple[EdgeSource, ...]
    criticality_code: str = ""
    failure_impact: str = ""


@lru_cache(maxsize=1)
def _edges() -> Tuple[_Edge, ...]:
    """Every recorded dependency edge, from both workbook sources, merged.

    Keyed by (source, target) so a dependency both files record becomes one
    edge carrying both sources and whatever description the richer file has,
    rather than two edges of which the walk would only ever see the first.
    """
    merged: Dict[Tuple[str, str], _Edge] = {}

    def _add(
        source: str,
        target: str,
        origin: EdgeSource,
        criticality_code: str = "",
        failure_impact: str = "",
    ) -> None:
        key = (source, target)
        existing = merged.get(key)
        if existing is None:
            merged[key] = _Edge(
                source=source,
                target=target,
                sources=(origin,),
                criticality_code=criticality_code,
                failure_impact=failure_impact,
            )
            return
        merged[key] = _Edge(
            source=source,
            target=target,
            sources=(
                existing.sources if origin in existing.sources else existing.sources + (origin,)
            ),
            # Only the edge table carries these, so a non-empty value is
            # always the more specific one; never let a bare reference blank
            # out a description already recorded.
            criticality_code=existing.criticality_code or criticality_code,
            failure_impact=existing.failure_impact or failure_impact,
        )

    # 02_service_inventory.csv: "this service depends on those".
    for identity in _identity_index().values():
        for depends_on in identity.depends_on_services:
            _add(depends_on, identity.service_id, EdgeSource.INVENTORY)

    # 15_dependencies.csv: the richer edge table, anchor services only.
    if os.path.exists(_EDGE_TABLE):
        with open(_EDGE_TABLE, newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                source = (row.get("TargetID") or "").strip()
                target = (row.get("SourceID") or "").strip()
                if not source or not target:
                    continue
                _add(
                    source,
                    target,
                    EdgeSource.EDGE_TABLE,
                    criticality_code=(row.get("CriticalityCode") or "").strip(),
                    failure_impact=(row.get("FailureImpactDescription") or "").strip(),
                )

    return tuple(merged.values())


@lru_cache(maxsize=1)
def _dependants() -> Dict[str, Tuple[_Edge, ...]]:
    """service_id -> the edges of everything that depends on it."""
    index: Dict[str, list[_Edge]] = {}
    for edge in _edges():
        index.setdefault(edge.source, []).append(edge)
    return {k: tuple(v) for k, v in index.items()}


def reset_cache() -> None:
    """Drop the cached graph. For tests that rewrite the workbook."""
    _edges.cache_clear()
    _dependants.cache_clear()
    coverage.cache_clear()


@lru_cache(maxsize=1)
def coverage() -> EstateCoverage:
    """How much of the estate has any inbound dependency recorded."""
    services = _identity_index()
    dependants = _dependants()
    with_edges = sum(1 for sid in services if dependants.get(sid))
    return EstateCoverage(
        services=len(services),
        with_inbound_edges=with_edges,
        without_inbound_edges=len(services) - with_edges,
    )


def blast_radius(identifier: str | int, max_hops: int = DEFAULT_MAX_HOPS) -> BlastRadius:
    """What a failure of `identifier` would reach.

    Accepts anything `src.cmdb.identity.resolve` accepts — a ServiceID, a PID,
    a Location name or a port. Raises IdentityResolutionError for an unknown
    identifier rather than returning an empty radius, because an empty radius
    for a typo is indistinguishable from an empty radius for a real service
    with no recorded dependants.
    """
    if max_hops < 1:
        raise ValueError("max_hops must be at least 1")

    origin = resolve(identifier)
    dependants = _dependants()
    services = _identity_index()

    seen: Set[str] = {origin.service_id}
    affected: list[AffectedService] = []
    # (service_id, hops, path)
    frontier: list[Tuple[str, int, Tuple[str, ...]]] = [
        (origin.service_id, 0, (origin.service_id,))
    ]

    while frontier:
        current, hops, path = frontier.pop(0)
        if hops >= max_hops:
            continue
        for edge in dependants.get(current, ()):
            if edge.target in seen:
                # Already reached, by an equal or shorter path — breadth-first
                # guarantees the first arrival is the shortest, so the earlier
                # (higher-confidence) record stands.
                continue
            seen.add(edge.target)
            identity = services.get(edge.target)
            next_path = path + (edge.target,)
            affected.append(
                AffectedService(
                    service_id=edge.target,
                    service_name=identity.service_name if identity else "",
                    location=identity.location if identity else None,
                    tier3_ai=(identity.tier3_ai or None) if identity else None,
                    tier2_prime=(identity.tier2_prime or None) if identity else None,
                    hops=hops + 1,
                    path=next_path,
                    confidence=(Confidence.KNOWN if hops == 0 else Confidence.PROBABLE),
                    sources=edge.sources,
                    criticality_code=edge.criticality_code,
                    failure_impact=edge.failure_impact,
                )
            )
            frontier.append((edge.target, hops + 1, next_path))

    affected.sort(key=lambda a: (a.hops, a.service_id))
    return BlastRadius(
        origin=origin,
        affected=tuple(affected),
        has_dependency_data=bool(dependants.get(origin.service_id)),
        coverage=coverage(),
        max_hops=max_hops,
    )


def services_without_dependency_data() -> Tuple[str, ...]:
    """Every service a blast radius cannot say anything useful about.

    Intended to be read and shrunk, not suppressed. Each entry is a service
    whose incidents will be prioritised without impact information.
    """
    dependants = _dependants()
    return tuple(sorted(sid for sid in _identity_index() if not dependants.get(sid)))


def safe_blast_radius(identifier: str | int, max_hops: int = DEFAULT_MAX_HOPS):
    """`blast_radius` that returns None instead of raising on a bad identifier.

    For callers walking a list of service strings from elsewhere — an incident
    feed, a log line — where one unresolvable entry should not abort the batch.
    Deliberately a separate function: the default stays strict.
    """
    try:
        return blast_radius(identifier, max_hops=max_hops)
    except IdentityResolutionError:
        return None
