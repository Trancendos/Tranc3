"""Ownership of things that are not Locations.

Every one of the 43 Locations has a Lead AI who would notice it break. The
Shared Functional Services Core had nobody, and the resulting defects were
concrete: 447 lines of security scanning wired to nothing, three duplicate
CircuitState enums inside the core, telemetry dead in 34 services.

These tests pin the fix: the SFSC has a named, reassignable, audited owner, and
adding that concept did not weaken the registry's existing validation.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.entities.platform import PLATFORM_ENTITIES, PLATFORM_ROLES
from src.roles.registry import RoleRegistry, UnknownLocationError


@pytest.fixture()
def registry() -> RoleRegistry:
    db = Path(tempfile.mkdtemp()) / "roles.db"
    reg = RoleRegistry(db_path=str(db))
    yield reg
    reg.close()


def test_dimensional_is_not_a_location() -> None:
    """The SFSC must stay out of the 43-entity registry.

    A Dimensional has no pillar, no agent teams and no worker port. Adding it to
    PLATFORM_ENTITIES to give it an owner would corrupt the entity model to
    solve a governance problem — and would silently change every count and
    every consumer that iterates the 43.
    """
    assert "Dimensional" in PLATFORM_ROLES
    assert "Dimensional" not in PLATFORM_ENTITIES
    assert len(PLATFORM_ENTITIES) == 43


def test_queen_holds_the_shared_core(registry: RoleRegistry) -> None:
    role = registry.get_role("Dimensional")
    assert role is not None, "the SFSC role must be seeded, not left to an operator"
    assert role.assigned_ai == "The Queen"
    # Her existing HIVE title is the reason she holds it — if that title ever
    # changes, this assignment needs re-justifying rather than silently drifting.
    assert role.job_description == "Head of Data Transport & Swarm Operations"


def test_role_is_reassignable_and_audited(registry: RoleRegistry) -> None:
    """Ownership must be mutable at runtime, or it is documentation, not governance."""
    registry.assign_ai("Dimensional", "Norman Hawkins", changed_by="test", reason="handover")
    assert registry.get_role("Dimensional").assigned_ai == "Norman Hawkins"

    history = registry.get_history("Dimensional")
    assert any(
        h.previous_ai == "The Queen" and h.new_ai == "Norman Hawkins" and h.reason == "handover"
        for h in history
    ), "a reassignment that leaves no audit trail is not accountable"

    registry.assign_ai("Dimensional", "The Queen", changed_by="test", reason="revert")
    assert registry.get_role("Dimensional").assigned_ai == "The Queen"


def test_unknown_keys_are_still_rejected(registry: RoleRegistry) -> None:
    """Relaxing validation for platform roles must not open it to anything."""
    for method in (
        lambda: registry.assign_ai("NotARealThing", "Someone"),
        lambda: registry.remove_ai("NotARealThing"),
        lambda: registry.get_history("NotARealThing"),
    ):
        with pytest.raises(UnknownLocationError):
            method()


def test_platform_role_row_is_not_blank(registry: RoleRegistry) -> None:
    """A role row must read as a different kind of row, not as broken data.

    It legitimately has no pillar. If primary_function were also empty the row
    would look like corruption, so the role's scope stands in for it.
    """
    role = registry.get_role("Dimensional")
    assert role.pillar == ""
    assert "Shared Functional Services Core" in role.primary_function


def test_locations_still_seeded_alongside_roles(registry: RoleRegistry) -> None:
    rows = registry.list_roles()
    assert len(rows) == len(PLATFORM_ENTITIES) + len(PLATFORM_ROLES)
    assert {r.location for r in rows} >= set(PLATFORM_ENTITIES)
