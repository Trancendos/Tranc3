"""Job Description seats: one role per AI, not one per Location.

The registry was keyed by Location alone, so 43 Job Descriptions were being
asked to cover 51 AI seats and eight AIs held no job title at all. They were not
spares: The Mad Hatter runs adversarial testing while Alice Dream runs the
deterministic half, and one title covering both describes neither.

The migration is tested against a real pre-seat database rather than a mock,
because the failure it guards against -- an operator's manual reassignment being
lost, or every co-lead at a Location being rewritten by one assign call -- is a
data-loss failure and would not show up in a schema-shaped assertion.
"""

from __future__ import annotations

import sqlite3
import time

import pytest

from src.entities.platform import (
    CO_LEAD_JOB_DESCRIPTIONS,
    JOB_DESCRIPTIONS,
    PLATFORM_ENTITIES,
    all_seats,
    get_seats,
    seat_id_for,
    seats_without_a_distinct_title,
)
from src.roles.registry import RoleRegistry, UnknownLocationError


@pytest.fixture
def registry(tmp_path):
    reg = RoleRegistry(db_path=tmp_path / "roles.db")
    yield reg
    reg.close()


class TestSeatDerivation:
    def test_every_lead_ai_has_a_seat(self):
        """The count that started this: 43 titles were covering 51 AIs."""
        expected = sum(len(e.lead_ais) or 1 for e in PLATFORM_ENTITIES.values())
        location_seats = [s for s in all_seats() if s.location in PLATFORM_ENTITIES]
        assert len(location_seats) == expected
        assert len(location_seats) > len(JOB_DESCRIPTIONS)

    def test_single_lead_locations_are_unchanged(self):
        """A Location with one AI still yields exactly its existing title."""
        seats = get_seats("The Spark")
        assert len(seats) == 1
        assert seats[0].is_primary
        assert seats[0].job_description == JOB_DESCRIPTIONS["The Spark"]

    def test_co_leads_do_not_share_the_primary_title(self):
        """The defect this model removes. A co-lead falling back to the
        Location's headline title is indistinguishable from having no job."""
        for seat in all_seats():
            if seat.is_primary:
                continue
            primary = next(s for s in get_seats(seat.location) if s.is_primary)
            assert seat.job_description != primary.job_description, (
                f"{seat.designed_for} at {seat.location} has no distinct role"
            )

    def test_no_seat_is_left_untitled(self):
        """Fires the moment a sixth multi-AI Location is added without a title
        for its co-lead, rather than letting it silently inherit one."""
        assert seats_without_a_distinct_title() == []

    def test_functions_come_from_the_seat_s_own_agents(self):
        """A seat's stated function is evidenced by the two agents doing it, so
        the claim cannot drift from the work."""
        alice = next(s for s in get_seats("The Chaos Party") if s.designed_for == "Alice Dream")
        hatter = next(s for s in get_seats("The Chaos Party") if s.is_primary)
        assert alice.functions and hatter.functions
        assert alice.functions != hatter.functions
        assert "deterministic" in " ".join(alice.functions).lower()

    def test_seat_ids_are_unique_within_a_location(self):
        for location in PLATFORM_ENTITIES:
            ids = [s.seat_id for s in get_seats(location)]
            assert len(ids) == len(set(ids)), location

    def test_seat_id_is_stable_and_slugged(self):
        assert seat_id_for("Alice Dream") == "alice-dream"
        assert seat_id_for("The Dr. (Nikolai O'denhime)") == "the-dr-nikolai-o-denhime"

    def test_an_unknown_name_yields_no_seats(self):
        """Neither a Location nor a platform role. Returning [] rather than
        raising keeps `all_seats()` composable, but it must be [] and not a
        seat with empty fields, which would read as a real role."""
        assert get_seats("Nowhere At All") == []

    def test_a_non_location_platform_role_gets_one_primary_seat(self):
        """The Shared Functional Services Core is seated in the same table so
        "who holds what" has one answer, but it is not a Location: no pillar,
        no agent team, no worker port."""
        from src.entities.platform import PLATFORM_ROLES

        role_id = next(iter(PLATFORM_ROLES))
        seats = get_seats(role_id)
        assert len(seats) == 1
        assert seats[0].is_primary and seats[0].seat_id == "primary"
        assert seats[0].designed_for == PLATFORM_ROLES[role_id].default_holder
        assert seats[0].functions == ()

    def test_every_declared_co_lead_title_matches_a_real_roster_entry(self):
        """A title for an AI who is not on the Location's roster is a typo that
        would otherwise sit unnoticed, since nothing reads it."""
        for location, ai in CO_LEAD_JOB_DESCRIPTIONS:
            assert location in PLATFORM_ENTITIES, location
            assert ai in PLATFORM_ENTITIES[location].lead_ais, f"{ai} not a lead at {location}"


class TestRegistrySeats:
    def test_all_seats_are_seeded(self, registry):
        rows = registry.list_roles()
        assert len(rows) == len(all_seats())

    def test_a_location_returns_all_its_seats(self, registry):
        seats = registry.get_location_seats("Arcadian Exchange")
        assert len(seats) == 5
        assert [s.assigned_ai for s in seats][0] == "Clarence Porter"
        assert len({s.job_description for s in seats}) == 5

    def test_get_role_defaults_to_the_primary_seat(self, registry):
        assert registry.get_role("The Lab").assigned_ai == "The Dr. (Nikolai O'denhime)"

    def test_assigning_one_seat_leaves_its_siblings_alone(self, registry):
        """The bug the composite key would have introduced if the writes had not
        been scoped: `WHERE location = ?` now matches every seat."""
        registry.assign_ai("The Chaos Party", "Stand-In", seat_id="alice-dream")
        seats = {s.seat_id: s.assigned_ai for s in registry.get_location_seats("The Chaos Party")}
        assert seats["alice-dream"] == "Stand-In"
        assert seats["primary"] == "The Mad Hatter"

    def test_vacating_one_seat_leaves_its_siblings_alone(self, registry):
        registry.remove_ai("Infinity", seat_id="the-orb-of-orisis")
        seats = {s.seat_id: s.assigned_ai for s in registry.get_location_seats("Infinity")}
        assert seats["the-orb-of-orisis"] is None
        assert seats["primary"] == "The Guardian (Marcus Magnolia)"

    def test_an_unknown_seat_is_refused_rather_than_silently_created(self, registry):
        with pytest.raises(UnknownLocationError):
            registry.assign_ai("The Chaos Party", "Nobody", seat_id="does-not-exist")

    def test_history_records_which_seat_moved(self, registry):
        registry.assign_ai("TateKing", "Stand-In", seat_id="sam-king", reason="cover")
        entries = registry.get_history("TateKing", seat_id="sam-king")
        assert entries and entries[0].seat_id == "sam-king"
        assert entries[0].new_ai == "Stand-In"

    def test_history_without_a_seat_filter_returns_the_whole_location(self, registry):
        registry.assign_ai("TateKing", "A", seat_id="primary")
        registry.assign_ai("TateKing", "B", seat_id="sam-king")
        assert len(registry.get_history("TateKing")) == 2


class TestMigrationFromTheLocationOnlySchema:
    """A persisted DB written before seats existed must survive the rebuild."""

    @staticmethod
    def _write_pre_seat_db(path):
        conn = sqlite3.connect(path)
        conn.execute(
            "CREATE TABLE role_assignments ("
            "location TEXT PRIMARY KEY, job_description TEXT NOT NULL, assigned_ai TEXT, "
            "assigned_at REAL NOT NULL, assigned_by TEXT NOT NULL DEFAULT 'system')"
        )
        conn.execute(
            "CREATE TABLE role_assignment_history ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, location TEXT NOT NULL, previous_ai TEXT, "
            "new_ai TEXT, changed_at REAL NOT NULL, changed_by TEXT NOT NULL, "
            "reason TEXT NOT NULL DEFAULT '')"
        )
        # An operator's manual reassignment, which must not be lost.
        conn.execute(
            "INSERT INTO role_assignments VALUES (?, ?, ?, ?, ?)",
            (
                "The Chaos Party",
                "Head of Quality Assurance & Testing",
                "A Human",
                time.time(),
                "operator",
            ),
        )
        conn.execute(
            "INSERT INTO role_assignment_history (location, previous_ai, new_ai, changed_at, changed_by, reason) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                "The Chaos Party",
                "The Mad Hatter",
                "A Human",
                time.time(),
                "operator",
                "holiday cover",
            ),
        )
        conn.commit()
        conn.close()

    def test_an_operator_reassignment_survives_the_rebuild(self, tmp_path):
        path = tmp_path / "legacy.db"
        self._write_pre_seat_db(path)
        reg = RoleRegistry(db_path=path)
        try:
            assert reg.get_role("The Chaos Party").assigned_ai == "A Human"
        finally:
            reg.close()

    def test_pre_seat_rows_become_the_primary_seat(self, tmp_path):
        path = tmp_path / "legacy.db"
        self._write_pre_seat_db(path)
        reg = RoleRegistry(db_path=path)
        try:
            assert reg.get_role("The Chaos Party", "primary").assigned_ai == "A Human"
        finally:
            reg.close()

    def test_new_seats_are_backfilled_alongside_the_migrated_rows(self, tmp_path):
        """Migration alone would leave the co-lead seats missing; the seed pass
        has to run over the rebuilt table too."""
        path = tmp_path / "legacy.db"
        self._write_pre_seat_db(path)
        reg = RoleRegistry(db_path=path)
        try:
            seats = {s.seat_id for s in reg.get_location_seats("The Chaos Party")}
            assert seats == {"primary", "alice-dream"}
        finally:
            reg.close()

    def test_history_survives_the_rebuild(self, tmp_path):
        path = tmp_path / "legacy.db"
        self._write_pre_seat_db(path)
        reg = RoleRegistry(db_path=path)
        try:
            entries = reg.get_history("The Chaos Party")
            assert len(entries) == 1
            assert entries[0].previous_ai == "The Mad Hatter"
            assert entries[0].seat_id == "primary"
        finally:
            reg.close()

    def test_migration_is_idempotent(self, tmp_path):
        path = tmp_path / "legacy.db"
        self._write_pre_seat_db(path)
        RoleRegistry(db_path=path).close()
        reg = RoleRegistry(db_path=path)
        try:
            assert reg.get_role("The Chaos Party").assigned_ai == "A Human"
            assert len(reg.list_roles()) == len(all_seats())
        finally:
            reg.close()
