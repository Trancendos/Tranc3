"""The service identity spine — one service, resolvable across every namespace.

The platform names the same service four different ways, each in a subsystem
that cannot see the others:

    ServiceID       SRV-SPARK-001            EA workbook / CMDB
    PID             PID-SPK                  PLATFORM_ENTITIES.md, src/entities/platform.py
    Location name   "The Spark"              roles registry, src/exchange/, CranBania
    Port            8000                     docker-compose.production.yml, worker binds

Each of those is authoritative for its own subsystem, and that is fine. What
was missing is the join. Without it every cross-domain question in the ITIL4
architecture — which Location owns the service this incident is about, which
seats answer for it, which Exchange resources it produces, what its blast
radius is — has to be answered by a human reading two files side by side.

`02_service_inventory.csv` has carried the `PID` column all along and all 40
distinct values resolve to a real entity, so this module is a join over data
that already agrees, not a new mapping invented here. The one thing it adds
is a place for the join to live.

What it deliberately does NOT do
--------------------------------
It resolves identity. It does not assert that a service is healthy, deployed,
or in scope — those are separate questions with their own sources. And a
service with no PID is not an error: 15 of the 92 services are cross-cutting
infrastructure (LangChain, LiteLLM, the API gateway) rather than one of the 43
named Locations. `resolve()` returns a record whose `pid` is None for those,
rather than refusing or guessing, because guessing a Location for the API
gateway would put a wrong owner on every incident it ever raises.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field, replace
from functools import lru_cache
from typing import Optional

from src.entities.platform import (
    LocationEntity,
    get_entity_by_pid,
    get_entity_for_location,
    get_entity_for_port,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SERVICE_INVENTORY = os.path.join(
    REPO_ROOT, "docs", "architecture", "ea-workbook", "02_service_inventory.csv"
)


@dataclass(frozen=True)
class ServiceIdentity:
    """One service, named in every namespace that has a name for it.

    `pid`, `location` and `entity` are None together or set together: a
    service either maps onto one of the 43 canonical Locations or it does
    not. `unmapped_reason` says which, so a caller that needs an owner can
    tell "no Location owns this" from "the lookup failed".
    """

    service_id: str
    service_name: str
    pid: Optional[str] = None
    location: Optional[str] = None
    entity: Optional[LocationEntity] = None
    tier3_ai: str = ""
    tier2_prime: str = ""
    owner: str = ""
    criticality_code: str = ""
    depends_on_services: tuple[str, ...] = field(default_factory=tuple)
    unmapped_reason: Optional[str] = None
    # How many services this Location owns in total. The Observatory owns six.
    # A caller that resolved by PID, Location name or port got ONE of these
    # back, chosen deterministically, and needs to know when that choice was
    # made on its behalf -- silently returning 1 of 6 is how a blast radius
    # ends up five services short.
    location_service_count: int = 1

    @property
    def is_mapped_to_location(self) -> bool:
        return self.entity is not None

    @property
    def location_is_ambiguous(self) -> bool:
        """True when this Location owns more than one service.

        When True, prefer `services_for_location()` over `resolve()`.
        """
        return self.location_service_count > 1


class IdentityResolutionError(LookupError):
    """Raised when an identifier cannot be resolved in any namespace."""


def _split_deps(raw: str) -> tuple[str, ...]:
    """Split the workbook's semicolon-separated DependsOnServices field.

    Parsed once here so a blast-radius walk consumes ServiceIDs rather than
    re-learning the CSV's separator convention at every call site.
    """
    return tuple(d.strip() for d in (raw or "").split(";") if d.strip())


@lru_cache(maxsize=1)
def _index() -> dict[str, ServiceIdentity]:
    """Build the ServiceID -> ServiceIdentity index from the EA workbook.

    Cached because the CSV is a committed, hand-verified artefact that does
    not change at runtime. Tests that need a fresh read call `reset_cache()`.
    """
    index: dict[str, ServiceIdentity] = {}
    with open(_SERVICE_INVENTORY, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            service_id = (row.get("ServiceID") or "").strip()
            if not service_id:
                continue
            pid = (row.get("PID") or "").strip() or None
            entity = get_entity_by_pid(pid) if pid else None

            if pid and entity is None:
                # The CSV names a PID that the entity registry does not know.
                # That is a real inconsistency between two committed sources,
                # so it is recorded rather than silently dropped.
                reason = f"PID {pid} is not a known platform entity"
                pid_out, location = None, None
            elif not pid:
                reason = "cross-cutting service, not one of the 43 Locations"
                pid_out, location = None, None
            else:
                reason = None
                pid_out, location = pid, entity.location

            index[service_id] = ServiceIdentity(
                service_id=service_id,
                service_name=(row.get("ServiceName") or "").strip(),
                pid=pid_out,
                location=location,
                entity=entity,
                tier3_ai=(row.get("Tier3AI") or "").strip(),
                tier2_prime=(row.get("Tier2Prime") or "").strip(),
                owner=(row.get("Owner") or "").strip(),
                criticality_code=(row.get("CriticalityCode") or "").strip(),
                depends_on_services=_split_deps(row.get("DependsOnServices", "")),
                unmapped_reason=reason,
            )

    # Second pass: a service cannot know how many siblings its Location has
    # until every row is read.
    per_location: dict[str, int] = {}
    for identity in index.values():
        if identity.location:
            per_location[identity.location] = per_location.get(identity.location, 0) + 1
    for service_id, identity in list(index.items()):
        if identity.location:
            index[service_id] = replace(
                identity, location_service_count=per_location[identity.location]
            )
    return index


def reset_cache() -> None:
    """Drop the cached index. For tests that rewrite the CSV."""
    _index.cache_clear()


def resolve(identifier: str | int) -> ServiceIdentity:
    """Resolve any of the four identifiers to one ServiceIdentity.

    Accepts a ServiceID, a PID, a Location name, or a port. Raises
    IdentityResolutionError rather than returning None, because a caller
    that has an identifier in hand and gets nothing back is almost always
    looking at a typo or a stale reference, and a silent None turns that
    into a wrong answer further downstream.
    """
    index = _index()

    if isinstance(identifier, int):
        entity = get_entity_for_port(identifier)
        if entity is None:
            raise IdentityResolutionError(f"no entity binds port {identifier}")
        return _by_entity(entity, index, f"port {identifier}")

    key = (identifier or "").strip()
    if not key:
        raise IdentityResolutionError("empty identifier")

    if key in index:
        return index[key]

    entity = get_entity_by_pid(key) or get_entity_for_location(key)
    if entity is not None:
        return _by_entity(entity, index, key)

    raise IdentityResolutionError(f"{key!r} is not a known ServiceID, PID, or Location name")


def _by_entity(
    entity: LocationEntity, index: dict[str, ServiceIdentity], asked_for: str
) -> ServiceIdentity:
    """Resolve a Location to one of its services.

    A Location can own several services, so this picks the lowest ServiceID
    for determinism -- the same input must always give the same answer, or
    two callers reading the same CMDB disagree about who owns an incident.
    The returned record carries `location_service_count`, and
    `location_is_ambiguous` is True whenever a choice was made here.
    """
    owned = sorted(
        (
            i
            for i in index.values()
            if i.entity is not None and i.entity.location == entity.location
        ),
        key=lambda i: i.service_id,
    )
    if owned:
        return owned[0]
    raise IdentityResolutionError(
        f"{asked_for} resolves to Location {entity.location!r}, "
        "which has no service in the EA workbook"
    )


def services_for_location(location: str) -> list[ServiceIdentity]:
    """Every CMDB service owned by one Location.

    A Location can own more than one service — this returns all of them,
    where `resolve()` returns the first. Blast radius needs all of them.
    """
    entity = get_entity_for_location(location) or get_entity_by_pid(location)
    if entity is None:
        raise IdentityResolutionError(f"{location!r} is not a known Location")
    return [
        s
        for s in _index().values()
        if s.entity is not None and s.entity.location == entity.location
    ]


def unmapped_services() -> list[ServiceIdentity]:
    """Services that map onto no Location, with the reason for each.

    Intended to be read, not suppressed. A service appearing here for the
    'cross-cutting' reason is expected; one appearing for an unresolvable
    PID is a genuine inconsistency between two committed sources.
    """
    return [s for s in _index().values() if not s.is_mapped_to_location]


def coverage() -> dict[str, int]:
    """How much of the estate the identity spine actually joins."""
    all_services = list(_index().values())
    mapped = [s for s in all_services if s.is_mapped_to_location]
    broken = [
        s
        for s in all_services
        if not s.is_mapped_to_location
        and s.unmapped_reason
        and s.unmapped_reason.startswith("PID ")
    ]
    return {
        "services": len(all_services),
        "mapped_to_location": len(mapped),
        "cross_cutting": len(all_services) - len(mapped) - len(broken),
        "broken_pid_reference": len(broken),
        "distinct_locations": len({s.entity.location for s in mapped if s.entity}),
    }
