"""The domain model must generate a schema that fails closed and tells the truth.

The model is Mendix-shaped so that one description produces the database schema,
the permission policies and the route table. That only pays off if the generated
artifacts are trustworthy, which means two properties in particular:

* **Row-level security fails closed.** PostgreSQL returns nothing from a table
  with RLS enabled and no policy. Generating ENABLE without policies is therefore
  the safe direction to be incomplete in -- and generating policies without ENABLE
  is the unsafe one, because the policies then decorate a table anyone can read.

* **An unchecked property is never reported as passing.** The conformance report
  exists to show where the estate is incomplete. A property the checker could not
  evaluate must say so; the moment "could not check" renders as "fine", the report
  is worse than not having one.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.domain.build import build_model  # noqa: E402
from src.domain.conformance import UNCHECKED, assess  # noqa: E402
from src.domain.ddl import generate, rls_ddl  # noqa: E402
from src.domain.model import (  # noqa: E402
    Access,
    AccessRule,
    Attribute,
    AttributeType,
    Entity,
    _snake,
)

SQL_OUT = REPO / "docs" / "architecture" / "domain-model.sql"
JSON_OUT = REPO / "docs" / "architecture" / "domain-model.json"
CONFORMANCE_OUT = REPO / "docs" / "architecture" / "conformance.json"


@pytest.fixture(scope="module")
def model():
    return build_model()


@pytest.fixture(scope="module")
def sql(model) -> str:
    return generate(model)


# ── Shape ────────────────────────────────────────────────────────────────────


def test_every_entity_belongs_to_a_real_location(model):
    from src.entities.platform import PLATFORM_ENTITIES

    for entity in model.entities:
        assert entity.module in PLATFORM_ENTITIES, (
            f"{entity.name} is owned by {entity.module!r}, which is not one of the "
            "43 Locations. A module that is not a Location has no seats, so its "
            "entities have no roles to grant access to."
        )


def test_every_association_names_modelled_entities(model):
    names = {e.name for e in model.entities}
    for association in model.associations:
        assert association.owner in names, (
            f"{association.name}: owner {association.owner} unmodelled"
        )
        assert association.target in names, (
            f"{association.name}: target {association.target} unmodelled"
        )


def test_the_two_container_relationships_stay_separate(model):
    """Custody and jurisdiction must not collapse into one column."""
    names = {a.name for a in model.associations}
    assert "ContainerCustodiedBy" in names
    assert "ContainerUnderJurisdictionOf" in names

    custody = next(a for a in model.associations if a.name == "ContainerCustodiedBy")
    jurisdiction = next(a for a in model.associations if a.name == "ContainerUnderJurisdictionOf")
    assert custody.required, "custody must be required — every container has a custodian"
    assert not jurisdiction.required, (
        "jurisdiction must stay optional — 86 containers are third-party images "
        "running nobody's code here, and forcing a value would invent an owner."
    )


def test_module_roles_come_from_the_seats(model):
    from src.entities.platform import PLATFORM_ENTITIES

    assert len(model.module_roles) > 30, "most Locations should define module roles"
    for location in model.module_roles:
        assert location in PLATFORM_ENTITIES


# ── Generated DDL ────────────────────────────────────────────────────────────


def test_every_persistable_entity_gets_a_table(model, sql):
    for entity in model.entities:
        if not entity.persistable:
            continue
        assert f"CREATE TABLE IF NOT EXISTS {entity.qualified}" in sql, (
            f"{entity.name} has no CREATE TABLE"
        )


def test_every_table_enables_row_level_security(model, sql):
    """The property that makes an unmodelled table return nothing."""
    for entity in model.entities:
        if not entity.persistable:
            continue
        assert f"ALTER TABLE {entity.qualified} ENABLE ROW LEVEL SECURITY;" in sql, (
            f"{entity.qualified} has no RLS. A table without it is readable by "
            "anyone who can reach the database, whatever the access rules say."
        )
        assert f"ALTER TABLE {entity.qualified} FORCE ROW LEVEL SECURITY;" in sql, (
            f"{entity.qualified} does not FORCE RLS, so the table owner bypasses "
            "every policy — and the application connects as the owner more often "
            "than anyone intends."
        )


def test_no_policy_is_created_on_a_table_without_rls_enabled(model, sql):
    """Policies on an unprotected table read as security and are decoration."""
    for entity in model.entities:
        if "CREATE POLICY" in sql and entity.qualified in sql:
            has_policy = f"ON {entity.qualified} FOR" in sql
            if has_policy:
                assert f"ALTER TABLE {entity.qualified} ENABLE ROW LEVEL SECURITY;" in sql


def test_calculated_attributes_get_no_column(model, sql):
    for entity in model.entities:
        for attribute in entity.attributes:
            if attribute.stored:
                continue
            assert f"    {attribute.column} " not in sql, (
                f"{entity.name}.{attribute.name} is calculated but has a column. A "
                "derived value stored in a row becomes a stale copy."
            )


def test_session_settings_are_documented_in_the_ddl(sql):
    assert "SET LOCAL trancendos.location" in sql
    assert "SET LOCAL trancendos.role" in sql
    assert "LOCAL" in sql, (
        "the DDL must say LOCAL — a session setting that outlives its transaction "
        "leaks into the next request on a pooled connection"
    )


# ── Conformance honesty ──────────────────────────────────────────────────────


def test_unchecked_is_distinguishable_from_passing():
    rows = assess()
    statuses = {r.env_status for r in rows} | {r.dependency_status for r in rows}
    assert UNCHECKED in statuses or all(s != UNCHECKED for s in statuses)
    for row in rows:
        if row.env_status == UNCHECKED:
            assert not row.complete, (
                f"{row.location} is marked complete while its env vars were never "
                "checked. Unchecked is not passed."
            )


def test_registry_lookup_actually_finds_entries():
    """Guard against the parser silently matching nothing.

    An earlier version looked for `entries`/`registry` keys in a file whose list
    lives under `components`, found neither, and reported 0 of 43 Locations as
    having a registry value — a clean, confident, entirely wrong finding.
    """
    from src.domain.conformance import _registry_refs

    refs = _registry_refs()
    assert len(refs) > 10, (
        f"only {len(refs)} registry refs parsed. config/estate/registry.yaml holds "
        "93 components; a near-empty result means the parser stopped matching the "
        "file's shape, not that the registry emptied."
    )


def test_conformance_covers_every_location():
    from src.entities.platform import PLATFORM_ENTITIES

    rows = assess()
    assert {r.location for r in rows} == set(PLATFORM_ENTITIES)


# ── Generated output stays current ───────────────────────────────────────────


def test_generated_output_is_current():
    result = subprocess.run(
        [sys.executable, "scripts/build_domain_model.py", "--check"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def test_published_json_matches_the_built_model(model):
    assert json.loads(JSON_OUT.read_text(encoding="utf-8")) == model.to_dict()


# ── Probes ───────────────────────────────────────────────────────────────────


class TestTheGuardsWouldCatchIt:
    def test_camel_case_columns_split_before_lowering(self):
        assert _snake("ciId") == "ci_id"
        assert _snake("sbomRef") == "sbom_ref"
        assert _snake("The Ice Box") == "the_ice_box"

    def test_an_entity_with_no_rules_still_enables_rls(self):
        entity = Entity(name="Orphan", module="The Citadel")
        out = rls_ddl(entity)
        assert "ENABLE ROW LEVEL SECURITY" in out
        assert "CREATE POLICY" not in out
        assert "fail closed" in out, (
            "an entity with no access rules must say why it returns nothing"
        )

    def test_a_wildcard_rule_on_a_sensitive_entity_is_flagged(self):
        entity = Entity(
            name="Secretive",
            module="The Void",
            attributes=[Attribute("apiKey", AttributeType.STRING, sensitive=True)],
            access_rules=[AccessRule(role="*", members=["*"], access=Access.READ)],
        )
        out = rls_ddl(entity)
        assert "WARNING" in out and "api_key" not in out.split("WARNING")[0], (
            "a '*' member grant on an entity holding a secret must be flagged"
        )

    def test_sensitive_detection_does_not_fire_on_ordinary_key_names(self):
        from src.domain.build import _sensitive

        assert _sensitive("apiKey") and _sensitive("secret_token") and _sensitive("password")
        assert not _sensitive("sort_order") and not _sensitive("primary_function")
