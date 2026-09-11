"""A Mendix-shaped domain model for the Trancendos platform.

The owner asked for entities, attributes and associations with permissions and
routing, structured the way Mendix structures a domain model. That is a good fit,
and the reason it fits is worth stating, because it is what makes the model
useful rather than decorative.

Mendix's shape, and what each part becomes here:

    Mendix                     Trancendos
    ----------------------     --------------------------------------------
    Module                     Location (each of the 43 owns a domain model)
    Module role                Job Description seat (56 already exist)
    Entity                     A CI class -- Location, AI, Container, Datastore
    Attribute                  A field on that CI, stored or calculated
    Association                A relationship, with an owning side
    Access rule                What a seat may read or write, member by member
    XPath constraint           A PostgreSQL row-level security predicate
    Page / microflow           An HTTP route, with its port and path prefix

The payoff is that one model generates four things that are currently maintained
separately and drift from each other: the database schema, the permission
policies, the route table, and the CMDB's CI classes. A platform that adds a
Location today must remember to touch all four. A platform with a domain model
touches one.

Two Mendix rules are kept deliberately, because both encode something this estate
has got wrong before:

* **Associations have an owner.** The arrow says which side the relationship
  belongs to. Without it, "The Ice Box custodies 174 containers" and "174
  containers are custodied by The Ice Box" become two facts that can disagree.

* **Access is member-level and additive.** A rule grants access to named
  attributes, not to a whole entity, and multiple rules for one role combine.
  Entity-level permissions are what produce "read access to the Location" and
  then a surprise that it included the secrets column.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class AttributeType(str, Enum):
    """Deliberately small. Each maps to exactly one PostgreSQL type."""

    STRING = "String"
    INTEGER = "Integer"
    BOOLEAN = "Boolean"
    DECIMAL = "Decimal"
    DATETIME = "DateTime"
    ENUM = "Enumeration"
    JSON = "JSON"

    @property
    def sql(self) -> str:
        return {
            "String": "TEXT",
            "Integer": "BIGINT",
            "Boolean": "BOOLEAN",
            "Decimal": "NUMERIC",
            "DateTime": "TIMESTAMPTZ",
            "Enumeration": "TEXT",
            "JSON": "JSONB",
        }[self.value]


class Multiplicity(str, Enum):
    ONE_TO_ONE = "1-1"
    ONE_TO_MANY = "1-*"
    MANY_TO_MANY = "*-*"


class Access(str, Enum):
    """Mendix's three levels, unchanged. None is the default, not an absence."""

    NONE = "None"
    READ = "Read"
    READ_WRITE = "ReadWrite"


@dataclass
class Attribute:
    name: str
    type: AttributeType
    #: Mendix distinguishes a StoredValue from a CalculatedValue. The distinction
    #: matters for DDL: a calculated attribute gets no column, and writing one is
    #: a modelling error rather than a runtime one.
    stored: bool = True
    required: bool = False
    default: Optional[str] = None
    description: str = ""
    #: True when this attribute holds a secret. Drives both the default access
    #: rule (None) and the audit posture, so a secret cannot be exposed by a rule
    #: someone wrote in a hurry.
    sensitive: bool = False

    @property
    def column(self) -> str:
        return _snake(self.name)


@dataclass
class Association:
    name: str
    #: The owning side. The arrow, in Mendix's notation.
    owner: str
    target: str
    multiplicity: Multiplicity = Multiplicity.ONE_TO_MANY
    description: str = ""
    #: True when the association must be populated. A container's custodian is
    #: required; its jurisdiction is not.
    required: bool = False


@dataclass
class AccessRule:
    """What one role may do, member by member.

    `constraint` is Mendix's XPath slot, expressed here as a SQL predicate because
    that is what PostgreSQL row-level security takes. Keeping the slot rather than
    dropping it is the point: a rule with no constraint grants access to every
    row, and that has to be a visible choice rather than an omission.
    """

    role: str
    #: Attribute names this rule grants access to. "*" means every attribute that
    #: is not marked sensitive -- sensitive members must always be named.
    members: List[str]
    access: Access = Access.READ
    constraint: str = ""
    description: str = ""


@dataclass
class Entity:
    name: str
    #: The Location that owns this entity, i.e. its Mendix module.
    module: str
    description: str = ""
    #: Mendix's persistable/non-persistable distinction. A non-persistable entity
    #: gets no table.
    persistable: bool = True
    attributes: List[Attribute] = field(default_factory=list)
    access_rules: List[AccessRule] = field(default_factory=list)
    #: Where this entity's content is read from today, so the model can be checked
    #: against the estate rather than believed.
    source: str = ""

    @property
    def table(self) -> str:
        return _snake(self.name)

    @property
    def schema(self) -> str:
        return _snake(self.module)

    @property
    def qualified(self) -> str:
        return f"{self.schema}.{self.table}"

    def attribute(self, name: str) -> Optional[Attribute]:
        return next((a for a in self.attributes if a.name == name), None)

    @property
    def sensitive_attributes(self) -> List[str]:
        return [a.name for a in self.attributes if a.sensitive]


@dataclass
class Route:
    """An HTTP entry point: the routing half of the model.

    Held alongside entities rather than apart from them because the owner's point
    stands -- ports, network and security structure follow from the same model.
    A route names the entity it exposes, so "which routes can reach the table
    holding secrets" is a query, not an investigation.
    """

    path: str
    module: str
    port: Optional[int] = None
    host_rule: str = ""
    exposes: List[str] = field(default_factory=list)
    public: bool = False


@dataclass
class DomainModel:
    entities: List[Entity] = field(default_factory=list)
    associations: List[Association] = field(default_factory=list)
    routes: List[Route] = field(default_factory=list)
    #: Module (Location) -> the roles defined in it, from the Job Description seats.
    module_roles: Dict[str, List[str]] = field(default_factory=dict)

    def entity(self, name: str) -> Optional[Entity]:
        return next((e for e in self.entities if e.name == name), None)

    def modules(self) -> List[str]:
        return sorted({e.module for e in self.entities})

    def to_dict(self) -> Dict[str, object]:
        return {
            "modules": self.modules(),
            "module_roles": self.module_roles,
            "entities": [
                {
                    "name": e.name,
                    "module": e.module,
                    "schema": e.schema,
                    "table": e.table,
                    "persistable": e.persistable,
                    "description": e.description,
                    "source": e.source,
                    "attributes": [
                        {
                            "name": a.name,
                            "type": a.type.value,
                            "sql_type": a.type.sql,
                            "column": a.column,
                            "stored": a.stored,
                            "required": a.required,
                            "sensitive": a.sensitive,
                            "default": a.default,
                            "description": a.description,
                        }
                        for a in e.attributes
                    ],
                    "access_rules": [
                        {
                            "role": r.role,
                            "members": r.members,
                            "access": r.access.value,
                            "constraint": r.constraint,
                            "description": r.description,
                        }
                        for r in e.access_rules
                    ],
                }
                for e in self.entities
            ],
            "associations": [
                {
                    "name": a.name,
                    "owner": a.owner,
                    "target": a.target,
                    "multiplicity": a.multiplicity.value,
                    "required": a.required,
                    "description": a.description,
                }
                for a in self.associations
            ],
            "routes": [
                {
                    "path": r.path,
                    "module": r.module,
                    "port": r.port,
                    "host_rule": r.host_rule,
                    "exposes": r.exposes,
                    "public": r.public,
                }
                for r in self.routes
            ],
        }


def _snake(name: str) -> str:
    """Identifier -> snake_case, splitting camelCase before lowering.

    Lowering first turns `ciId` into `ciid`, which is a column name nobody would
    write and nobody can read back. The boundary has to be found while the case
    information still exists.
    """
    import re

    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    spaced = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", spaced)
    slug = re.sub(r"[^A-Za-z0-9]+", "_", spaced).strip("_").lower()
    return re.sub(r"_+", "_", slug) or "unnamed"
