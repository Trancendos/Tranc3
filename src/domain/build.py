"""Derive the domain model from the registers the platform already keeps.

Same discipline as the taxonomy and the CI register: the *shape* is designed, the
*content* is read. An entity's attributes come from the dataclass that already
defines them, its module from the Location that already owns it, its roles from
the Job Description seats that already exist, and its routes from compose.

Nothing here declares a Location, an AI or a seat. If the platform gains a 44th
Location, this model gains a module without an edit.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

from src.domain.model import (
    Access,
    AccessRule,
    Association,
    Attribute,
    AttributeType,
    DomainModel,
    Entity,
    Multiplicity,
    Route,
)

REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "docker-compose.production.yml"

#: The Location that owns the platform-wide CMDB entities. The Citadel is the
#: estate's own infrastructure Location, which is where records *about* the
#: estate belong -- not in whichever Location happens to be described by a row.
CMDB_MODULE = "The Citadel"

#: Custodian of containment, per the shared-jurisdiction model.
CUSTODY_MODULE = "The Ice Box"

#: Attribute names that hold secrets wherever they appear. Matched on the name
#: rather than declared per entity, because the failure mode is a new entity
#: gaining a `token` field and nobody remembering to mark it.
SENSITIVE_HINTS = ("secret", "password", "token", "key", "credential", "passphrase")

#: Names ending in `_key` that are structural, not credentials. Listed rather
#: than pattern-matched: the cost of a false positive here is an attribute
#: needlessly locked down, and the cost of a false negative is a secret exposed
#: by a wildcard access rule. So anything not on this list is treated as a
#: credential.
_BENIGN_KEY_NAMES = frozenset(
    {"primary_key", "sort_key", "partition_key", "foreign_key", "natural_key", "ci_key"}
)


def _sensitive(name: str) -> bool:
    """Does this attribute name look like it holds a credential?

    Snake-cased first, not merely lowered. `apiKey".lower()` is `apikey`, which
    matches no underscore-separated hint -- so the attribute most obviously
    holding a secret was the one this check missed. Found by its own probe.
    """
    from src.domain.model import _snake

    normalised = _snake(name)

    # `key` is the awkward one: `api_key` and `signing_key` are credentials,
    # `primary_key` and `sort_key` are not. An earlier version's comment claimed
    # to make that distinction while the code flagged every `*_key` including
    # `primary_key` -- a comment and a rule disagreeing, which is the defect this
    # codebase keeps finding. The benign names are now named.
    if normalised in _BENIGN_KEY_NAMES:
        return False
    if normalised.endswith("_key") or normalised == "key":
        return True

    return any(hint in normalised for hint in SENSITIVE_HINTS if hint != "key")


def _attr(
    name: str,
    type_: AttributeType,
    *,
    required: bool = False,
    description: str = "",
    stored: bool = True,
) -> Attribute:
    return Attribute(
        name=name,
        type=type_,
        required=required,
        description=description,
        stored=stored,
        sensitive=_sensitive(name),
    )


# ── Entities ─────────────────────────────────────────────────────────────────


def _location_entity(roles: Dict[str, List[str]]) -> Entity:
    entity = Entity(
        name="Location",
        module=CMDB_MODULE,
        description="One of the platform's named Locations.",
        source="src/entities/platform.py::PLATFORM_ENTITIES",
        attributes=[
            _attr("pid", AttributeType.STRING, required=True, description="PID-XXX"),
            _attr("name", AttributeType.STRING, required=True),
            _attr("pillar", AttributeType.ENUM, required=True),
            _attr("primaryFunction", AttributeType.STRING),
            _attr("onlineMode", AttributeType.STRING),
            _attr("offlineMode", AttributeType.STRING),
            _attr("workerPath", AttributeType.STRING),
            _attr("workerPort", AttributeType.INTEGER),
            _attr("status", AttributeType.ENUM),
        ],
    )
    # Every seat in the estate may read the Location register; only the Location's
    # own seats may write its row. The constraint is what makes that true at the
    # row level rather than at the endpoint.
    entity.access_rules = [
        AccessRule(
            role="*",
            members=["*"],
            access=Access.READ,
            description="The Location register is readable platform-wide.",
        ),
        AccessRule(
            role="Location seat",
            members=["primaryFunction", "onlineMode", "offlineMode", "status"],
            access=Access.READ_WRITE,
            constraint="name = current_setting('trancendos.location', true)",
            description="A Location's own seats may edit its operational fields.",
        ),
    ]
    return entity


def _ai_entity() -> Entity:
    entity = Entity(
        name="AI",
        module=CMDB_MODULE,
        description="A named AI, at one of the three orchestration tiers.",
        source="src/entities/platform.py + src/personality/profiles/",
        attributes=[
            _attr("aid", AttributeType.STRING, required=True, description="AID-XXX-NN"),
            _attr("name", AttributeType.STRING, required=True),
            _attr(
                "tier",
                AttributeType.ENUM,
                required=True,
                description="Trance-One / T2ance / Tranc3",
            ),
            _attr("baseModel", AttributeType.STRING),
            _attr("profileRef", AttributeType.STRING, description="personality profile path"),
            _attr("seatCount", AttributeType.INTEGER, stored=False, description="calculated"),
        ],
    )
    entity.access_rules = [
        AccessRule(role="*", members=["*"], access=Access.READ),
        AccessRule(
            role="Turing's Hub seat",
            members=["profileRef", "baseModel"],
            access=Access.READ_WRITE,
            description="Turing's Hub is the AI creation centre and owns personality assignment.",
        ),
    ]
    return entity


def _container_entity() -> Entity:
    entity = Entity(
        name="Container",
        module=CUSTODY_MODULE,
        description="A containerised unit. Jurisdiction may be unknown; custody may not.",
        source="src/cmdb/containers.py",
        attributes=[
            _attr("ciId", AttributeType.STRING, required=True),
            _attr("service", AttributeType.STRING, required=True),
            _attr("image", AttributeType.STRING),
            _attr("provenance", AttributeType.ENUM, required=True, description="built | pulled"),
            _attr("runsAsRoot", AttributeType.BOOLEAN, required=True),
            _attr("sbomRef", AttributeType.STRING),
            _attr("sbomScope", AttributeType.ENUM, description="source | image"),
            _attr("ports", AttributeType.JSON),
            _attr("volumes", AttributeType.JSON),
        ],
    )
    entity.access_rules = [
        AccessRule(role="*", members=["service", "image", "provenance"], access=Access.READ),
        AccessRule(
            role="The Ice Box seat",
            members=["*"],
            access=Access.READ_WRITE,
            description="The custodian of containment may edit every container record.",
        ),
        AccessRule(
            role="Location seat",
            members=["service", "image", "sbomRef", "ports"],
            access=Access.READ,
            constraint=(
                # The generated column is container_under_jurisdiction_of_id, a
                # BIGINT key; `jurisdiction` is not a column on this table and
                # PostgreSQL rejected the policy outright. The session setting
                # carries a Location NAME, so the predicate has to resolve it
                # rather than compare a name to an id.
                "container_under_jurisdiction_of_id IN ("
                "SELECT id FROM the_citadel.location "
                "WHERE name = current_setting('trancendos.location', true))"
            ),
            description="A Location sees its own containers in full detail.",
        ),
    ]
    return entity


def _datastore_entity() -> Entity:
    entity = Entity(
        name="Datastore",
        module=CMDB_MODULE,
        description="A database or cache the estate opens.",
        source="src/cmdb/datastores.py",
        attributes=[
            _attr("ciId", AttributeType.STRING, required=True),
            _attr("name", AttributeType.STRING, required=True),
            _attr("engine", AttributeType.ENUM, required=True),
            _attr("locator", AttributeType.STRING),
            _attr("fileBacked", AttributeType.BOOLEAN, required=True),
            _attr("disposition", AttributeType.ENUM, description="migrate | keep | delete"),
        ],
    )
    entity.access_rules = [
        AccessRule(role="*", members=["name", "engine", "fileBacked"], access=Access.READ),
        AccessRule(
            role="The Citadel seat",
            members=["*"],
            access=Access.READ_WRITE,
        ),
    ]
    return entity


def _seat_entity() -> Entity:
    entity = Entity(
        name="RoleSeat",
        module="The Town Hall",
        description="One Job Description at one Location — the platform's module role.",
        source="src/entities/platform.py::get_seats",
        attributes=[
            _attr("seatId", AttributeType.STRING, required=True),
            _attr("location", AttributeType.STRING, required=True),
            _attr("jobDescription", AttributeType.STRING, required=True),
            _attr("designedFor", AttributeType.STRING),
            _attr("isPrimary", AttributeType.BOOLEAN),
            _attr("mandate", AttributeType.ENUM, description="internal | external"),
        ],
    )
    entity.access_rules = [
        AccessRule(role="*", members=["*"], access=Access.READ),
        AccessRule(
            role="The Town Hall seat",
            members=["*"],
            access=Access.READ_WRITE,
            description="Assignment is a governance decision and belongs to the Town Hall.",
        ),
    ]
    return entity


# ── Associations ─────────────────────────────────────────────────────────────


def _associations() -> List[Association]:
    return [
        Association(
            name="LocationHasSeats",
            owner="Location",
            target="RoleSeat",
            # One Location, many RoleSeats: the key belongs on role_seat. This
            # read ONE_TO_MANY when ONE_TO_MANY meant "key on the owner", which
            # put a single location_has_seats_id on `location`.
            multiplicity=Multiplicity.ONE_TO_MANY,
            required=True,
            description="Each Location defines the seats that are its module roles.",
        ),
        Association(
            name="SeatHeldByAI",
            owner="RoleSeat",
            target="AI",
            # Declared ONE_TO_ONE until 2026-09-28, which this estate disproves:
            # Rocking Ricki is the Lead AI of The Lighthouse, The Warp Tunnel and
            # Warp Radio, and Voxx of The Studio and Imaginarium. A UNIQUE on the
            # AI key -- which is what 1-1 generates -- would have made the schema
            # reject the register it is built from.
            multiplicity=Multiplicity.MANY_TO_ONE,
            description="Mutable at runtime via the Role Assignment Registry.",
        ),
        Association(
            name="ContainerCustodiedBy",
            owner="Container",
            target="Location",
            multiplicity=Multiplicity.MANY_TO_ONE,
            required=True,
            description=(
                "Always The Ice Box. Required: a container with no custodian is the "
                "one case the shared-jurisdiction model exists to prevent."
            ),
        ),
        Association(
            name="ContainerUnderJurisdictionOf",
            owner="Container",
            target="Location",
            multiplicity=Multiplicity.MANY_TO_ONE,
            required=False,
            description=(
                "Whose code runs inside. Optional on purpose: 86 containers are "
                "third-party images running nobody's code here."
            ),
        ),
        Association(
            name="DatastoreOwnedBy",
            owner="Datastore",
            target="Location",
            multiplicity=Multiplicity.MANY_TO_ONE,
            description="114 are currently unrouted and await a Town Hall decision.",
        ),
        Association(
            name="ContainerRunsDatastore",
            owner="Container",
            target="Datastore",
            # A Datastore lives inside one Container; a Container may hold
            # several. The key belongs on datastore, not on container.
            multiplicity=Multiplicity.ONE_TO_MANY,
            description=(
                "A file-backed store inside a container's writable layer dies with "
                "the container unless a volume is mounted. This edge is what makes "
                "that answerable per store rather than per service."
            ),
        ),
        Association(
            name="LocationDependsOnLocation",
            owner="Location",
            target="Location",
            multiplicity=Multiplicity.MANY_TO_MANY,
            description="The dependency graph blast radius is computed over.",
        ),
    ]


# ── Routes ───────────────────────────────────────────────────────────────────

_HOST_RE = re.compile(r"Host\(`([^`]+)`\)")
_PREFIX_RE = re.compile(r"PathPrefix\(`([^`]+)`\)")
_LB_PORT_RE = re.compile(r"loadbalancer\.server\.port\s*[=:]\s*\"?(\d+)")


def _routes() -> List[Route]:
    """Read from compose: Traefik rules, published ports, and what they expose."""
    try:
        import yaml
    except ImportError:  # pragma: no cover
        return []
    if not COMPOSE.is_file():
        return []

    from src.cmdb.containers import discover as discover_containers

    by_service = {c.service: c for c in discover_containers()}
    document = yaml.safe_load(COMPOSE.read_text(encoding="utf-8")) or {}
    routes: List[Route] = []

    for name, spec in sorted((document.get("services") or {}).items()):
        if not isinstance(spec, dict):
            continue
        labels = spec.get("labels") or []
        if isinstance(labels, dict):
            labels = [f"{k}={v}" for k, v in labels.items()]
        blob = "\n".join(str(label) for label in labels)

        hosts = _HOST_RE.findall(blob)
        prefixes = _PREFIX_RE.findall(blob)
        if not hosts and not prefixes:
            continue

        container = by_service.get(name)

        # Traefik's own loadbalancer.server.port is the port the router forwards
        # to. Taking the first numeric segment of the first published mapping
        # instead gave Forgejo port 2222, because its SSH mapping is listed
        # before its HTTP one -- a route table recording the host-side SSH port
        # as the HTTP entry point. The published mapping stays as the fallback
        # for services that set no label.
        port = None
        labelled = _LB_PORT_RE.search(blob)
        if labelled:
            port = int(labelled.group(1))
        else:
            for mapping in container.ports if container else []:
                for part in str(mapping).split(":"):
                    if part.isdigit():
                        port = int(part)
                        break
                if port:
                    break

        module = (container.jurisdiction if container else "") or "_unrouted_"
        # One Route per entry point, not per service. A single rule can carry
        # several PathPrefixes -- tranc3-backend's carries `/api/backend` AND
        # `/mcp` -- and a service can declare several routers with different
        # hosts. Keeping only prefixes[0] and hosts[0] dropped every entry point
        # after the first from a table whose purpose is to be authoritative.
        for host in hosts or [""]:
            for prefix in prefixes or ["/"]:
                routes.append(
                    Route(
                        path=prefix,
                        module=module,
                        port=port,
                        host_rule=host,
                        # A route reachable on a public host rule with no auth
                        # middleware is the network-security question this model
                        # exists to make answerable; recorded, not judged, here.
                        public=bool(host),
                    )
                )
    return routes


# ── Assembly ─────────────────────────────────────────────────────────────────


def module_roles() -> Dict[str, List[str]]:
    """Each Location's module roles, from its Job Description seats."""
    try:
        from src.entities.platform import PLATFORM_ENTITIES, get_seats
    except Exception:  # pragma: no cover - defensive
        return {}
    roles: Dict[str, List[str]] = {}
    for location in sorted(PLATFORM_ENTITIES):
        titles = [s.job_description for s in get_seats(location) if s.job_description]
        if titles:
            roles[location] = sorted(set(titles))
    return roles


def build_model() -> DomainModel:
    roles = module_roles()
    return DomainModel(
        entities=[
            _location_entity(roles),
            _ai_entity(),
            _seat_entity(),
            _container_entity(),
            _datastore_entity(),
        ],
        associations=_associations(),
        routes=_routes(),
        module_roles=roles,
    )
