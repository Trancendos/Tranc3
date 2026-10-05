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
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.domain.build import build_model  # noqa: E402
from src.domain.conformance import UNCHECKED, assess  # noqa: E402
from src.domain.ddl import _role_slug, generate, rls_ddl  # noqa: E402
from src.domain.model import (  # noqa: E402
    Access,
    AccessRule,
    Attribute,
    AttributeType,
    Entity,
    Multiplicity,
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
    """An unchecked property must be visible AND must not count as passing.

    The first version of this test asserted

        UNCHECKED in statuses or all(s != UNCHECKED for s in statuses)

    which is `A or not A`: true when the value is present and true when it is
    absent. It passed without ever establishing that the report produces an
    unchecked state at all -- a test that cannot fail, in the file whose subject
    is checks that cannot fail. Sourcery caught it.

    It now demands the state exist, since this estate has Locations whose
    environment cannot be scanned, and a report that stopped producing
    `unchecked` would mean the distinction had been lost rather than earned.
    """
    rows = assess()
    unchecked = [r for r in rows if UNCHECKED in (r.env_status, r.dependency_status)]
    assert unchecked, (
        "no Location reports an unchecked property. Either every Location became "
        "scannable -- refresh this expectation deliberately -- or 'could not "
        "check' is now rendering as a pass, which is the failure this file exists "
        "to prevent."
    )
    for row in unchecked:
        assert not row.complete, (
            f"{row.location} is marked complete while a property was never "
            "checked. Unchecked is not passed."
        )


def test_the_summary_key_names_the_number_of_properties_it_counts():
    """The count's name and the predicate behind it must agree.

    They did not. The key read `complete_on_all_six` while `complete` was the
    conjunction of five properties, and `DOMAIN-MODEL.md` printed a five-row
    table under a "Complete on all six" total. The sixth, `in_domain_model`,
    compared a Location name against the model's module names -- of which there
    are three -- so it could be true for at most three of 43 Locations while six
    were reported complete.

    Nothing asserted the relationship, so nothing caught it. This does.
    """
    from src.domain.conformance import LocationConformance, summary

    spelled = {"five": 5, "six": 6, "seven": 7, "four": 4, "three": 3}
    keys = [k for k in summary() if k.startswith("complete_on_all_")]
    assert len(keys) == 1, f"expected exactly one completeness key, found {keys}"
    word = keys[0].rsplit("_", 1)[-1]
    assert word in spelled, f"completeness key {keys[0]!r} does not name a number"
    assert spelled[word] == len(LocationConformance.PROPERTIES), (
        f"{keys[0]!r} claims {spelled[word]} properties; complete() is the "
        f"conjunction of {len(LocationConformance.PROPERTIES)}: "
        f"{list(LocationConformance.PROPERTIES)}"
    )


def test_a_withdrawn_observation_is_not_counted_as_conformance():
    """`names_a_model_module` is reported and must stay out of completeness.

    It is kept because it is a true measurement, and excluded because it is a
    category error as a conformance property: three of 43 Locations share a name
    with a model module, and that says nothing about whether the Location
    conforms to anything.
    """
    from src.domain.conformance import LocationConformance, summary

    assert "names_a_model_module" not in LocationConformance.PROPERTIES
    totals = summary()
    assert totals["names_a_model_module"] < totals["locations"], (
        "every Location names a model module, which would make this observation "
        "vacuous rather than merely non-conformance"
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


# ── The generated schema must be valid SQL, not merely current ───────────────


def _create_tables(sql: str) -> dict[str, list[str]]:
    """table name -> the column names its CREATE TABLE declares."""
    tables: dict[str, list[str]] = {}
    for block in re.finditer(
        r"CREATE TABLE IF NOT EXISTS\s+([\w.]+)\s*\((.*?)\n\);", sql, re.DOTALL
    ):
        name, body = block.group(1), block.group(2)
        columns = []
        for line in body.splitlines():
            line = line.strip().rstrip(",")
            if not line or line.upper().startswith(("PRIMARY KEY", "UNIQUE", "CONSTRAINT")):
                continue
            columns.append(line.split()[0])
        tables[name] = columns
    return tables


def test_no_generated_table_declares_a_column_twice():
    """PostgreSQL refuses the file, not the statement.

    `LocationDependsOnLocation` is Location -> Location, and the generator
    derived the join column name from each side's table, producing

        location_id BIGINT ... ,
        location_id BIGINT ... ,
        PRIMARY KEY (location_id, location_id)

    Applying the committed schema to PostgreSQL 16 stopped there with
    `column "location_id" appears twice in primary key constraint`, so every
    statement after it -- the whole row-level-security section -- was never
    created. The artifact was regenerated and current, and could not be applied;
    "current" was the only property anything checked.
    """
    sql = (REPO / "docs/architecture/domain-model.sql").read_text(encoding="utf-8")
    tables = _create_tables(sql)
    assert tables, "no CREATE TABLE statements found -- has the generator changed shape?"

    duplicated = {
        name: [c for c in columns if columns.count(c) > 1]
        for name, columns in tables.items()
        if len(set(columns)) != len(columns)
    }
    assert not duplicated, f"these tables declare a column more than once: {duplicated}"

    for key in re.finditer(r"PRIMARY KEY \(([^)]+)\)", sql):
        parts = [p.strip() for p in key.group(1).split(",")]
        assert len(set(parts)) == len(parts), f"PRIMARY KEY ({key.group(1)}) names a column twice"


def test_every_policy_predicate_names_a_column_its_table_has():
    """A policy on a column that does not exist is refused at CREATE time.

    The container rule for a Location seat was written against `jurisdiction`.
    The generated column is `container_under_jurisdiction_of_id`, so PostgreSQL
    rejected the policy -- and because the file had already failed earlier, the
    rejection was never even reached.

    Bare identifiers compared against `current_setting(...)` are the shape the
    access rules use, and are checkable without a database.
    """
    sql = (REPO / "docs/architecture/domain-model.sql").read_text(encoding="utf-8")
    tables = _create_tables(sql)
    for alter in re.finditer(r"ALTER TABLE ([\w.]+) ADD COLUMN IF NOT EXISTS\s+(\w+)", sql):
        tables.setdefault(alter.group(1), []).append(alter.group(2))

    unknown: list[str] = []
    for policy in re.finditer(
        r"CREATE POLICY (\w+) ON ([\w.]+) FOR \w+ USING \((.*?)\)(?:;| WITH CHECK)",
        sql,
        re.DOTALL,
    ):
        name, table, predicate = policy.group(1), policy.group(2), policy.group(3)

        # A subquery's WHERE clause names ITS table's columns, not the policy
        # table's. The first version of this check flagged
        # `WHERE name = current_setting(...)` inside a lookup against
        # the_citadel.location as a missing column on the_ice_box.container --
        # a guard that rejects a correct schema, which is the failure mode one
        # step removed from a guard that cannot fail. Each subquery is checked
        # against its own FROM table, then removed before the outer scan.
        scopes = [(table, predicate)]
        for sub in re.finditer(r"SELECT\s+\w+\s+FROM\s+([\w.]+)\s+WHERE\s+([^)]+)", predicate):
            scopes.append((sub.group(1), sub.group(2)))
        outer = re.sub(r"SELECT\s+\w+\s+FROM\s+[\w.]+\s+WHERE\s+[^)]+", "", predicate)
        scopes[0] = (table, outer)

        for scope_table, clause in scopes:
            columns = set(tables.get(scope_table, []))
            for identifier in re.findall(r"(?<![\w.'])([a-z_][a-z0-9_]*)\s*(?:=|IN)\s", clause):
                if identifier in {"true", "false", "current_setting"}:
                    continue
                if identifier not in columns:
                    unknown.append(f"{name} on {scope_table} tests {identifier!r}")

    assert not unknown, (
        "these policies test a column their table does not declare, so "
        f"CREATE POLICY fails: {unknown}"
    )


def test_a_write_rule_does_not_grant_insert_or_delete(model, sql):
    """`Access.READ_WRITE` must not become `FOR ALL`.

    `Access` carries Mendix's three levels, so "write" is a single value covering
    every statement, and PostgreSQL's `FOR ALL` is INSERT, UPDATE and DELETE. The
    generator used to map one onto the other, which handed every READ_WRITE rule
    powers its own description disclaimed -- a Location seat could delete the
    Location register row under a rule that said it "may edit its operational
    fields". These are derived registers a build pipeline populates, so that is a
    widening, not a convenience.

    A rule that genuinely needs INSERT or DELETE should extend the model rather
    than arrive as a side effect of the enum's coarseness, so this asserts the
    absence of `FOR ALL` across the whole generated schema rather than only on the
    rules that exist today.
    """
    assert "FOR ALL" not in sql, (
        "a FOR ALL policy grants INSERT and DELETE; emit FOR SELECT and FOR UPDATE"
    )

    writable = [
        (entity, rule)
        for entity in model.entities
        if entity.persistable
        for rule in entity.access_rules
        if rule.access is Access.READ_WRITE
    ]
    assert writable, "no READ_WRITE rules found — this test would pass vacuously"

    for entity, rule in writable:
        slug = _role_slug(rule.role)
        matching = [
            line
            for line in sql.splitlines()
            if line.startswith("CREATE POLICY")
            and f"ON {entity.qualified} " in line
            and f"_{slug}_w " in line
        ]
        assert matching, f"{entity.name}/{rule.role}: no write policy emitted"
        for line in matching:
            assert " FOR UPDATE " in line, f"{entity.name}/{rule.role}: {line}"


def test_every_write_rule_also_emits_a_read_policy(model, sql):
    """Narrowing the write policy must not remove the read it used to imply.

    `FOR ALL` covered SELECT. Splitting it into FOR UPDATE alone would silently
    drop a read the rule granted, which would be the same class of defect in the
    opposite direction.
    """
    for entity in model.entities:
        if not entity.persistable:
            continue
        for rule in entity.access_rules:
            if rule.access is not Access.READ_WRITE:
                continue
            slug = _role_slug(rule.role)
            reads = [
                line
                for line in sql.splitlines()
                if line.startswith("CREATE POLICY")
                and f"ON {entity.qualified} " in line
                and f"_{slug}_r " in line
                and " FOR SELECT " in line
            ]
            assert reads, f"{entity.name}/{rule.role}: write rule emits no read policy"


def test_a_required_association_column_is_added_then_constrained(sql):
    """`ADD COLUMN ... NOT NULL` with no default fails on a populated table.

    PostgreSQL rejects it the moment the table already holds a row, and this file
    is meant to be re-applicable to a live database — every table, index and
    association column is `IF NOT EXISTS` for exactly that reason. The one
    statement that was not re-applicable was the required association column, and
    nothing noticed because no test applies this schema to a database holding
    data (there is none to apply it to here, so this check is textual).

    So: add nullable, then constrain separately. Re-applying to a populated
    database then adds the column and stops at a NOT NULL it cannot satisfy,
    naming the rows that need a reference, instead of failing before the column
    exists at all. The backfill is deliberately not generated — which row points
    where is the data's business.
    """
    offenders = [
        line
        for line in sql.splitlines()
        if "ADD COLUMN IF NOT EXISTS" in line and "NOT NULL" in line
    ]
    assert not offenders, (
        "a required column added NOT NULL in one statement cannot be applied to a "
        f"populated table: {offenders}"
    )

    required = [
        association
        for association in build_model().associations
        if association.required and association.multiplicity is not Multiplicity.MANY_TO_MANY
    ]
    assert required, "no required non-join associations found — this test would pass vacuously"
    constrained = sql.count("SET NOT NULL")
    assert constrained == len(required), (
        f"{len(required)} required association(s) but {constrained} SET NOT NULL statement(s)"
    )
