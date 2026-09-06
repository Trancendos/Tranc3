# tests/test_roles.py
# Tests for src/roles/registry.py — the Role Assignment Registry
# (Location -> Job Description -> assigned AI).

from __future__ import annotations

import sqlite3

import pytest

from src.entities.platform import (
    EXTERNAL_SEATS,
    JOB_DESCRIPTIONS,
    PLATFORM_ENTITIES,
    PLATFORM_ROLES,
    all_seats,
    get_seats,
    seats_without_a_distinct_title,
)
from src.roles.registry import RoleRegistry, UnknownLocationError


@pytest.fixture
def registry(tmp_path):
    db_path = tmp_path / "role_registry_test.db"
    reg = RoleRegistry(db_path=db_path)
    yield reg
    reg.close()


class TestJobDescriptions:
    def test_every_entity_has_a_job_description(self):
        assert set(JOB_DESCRIPTIONS.keys()) == set(PLATFORM_ENTITIES.keys())

    def test_count_matches_platform_entities(self):
        assert len(JOB_DESCRIPTIONS) == len(PLATFORM_ENTITIES) == 43


class TestSeeding:
    def test_seeds_one_row_per_entity(self, registry):
        # The registry now also seeds non-Location platform roles (the Shared
        # Functional Services Core), so the expected count is Locations plus
        # roles rather than Locations alone. Asserting the union rather than a
        # literal keeps this honest if either set grows.
        # One row per SEAT, not per Location. The five Locations with more than
        # one Lead AI now carry a row each for their co-leads, which is the
        # point of the seat model -- 43 Job Descriptions were previously being
        # asked to cover 51 AIs. The set of *locations* is unchanged, so that
        # assertion still holds and is what pins the seeding coverage.
        roles = registry.list_roles()
        assert len(roles) == len(all_seats())
        assert len(roles) > len(PLATFORM_ENTITIES) + len(PLATFORM_ROLES)
        assert {r.location for r in roles} == set(PLATFORM_ENTITIES) | set(PLATFORM_ROLES)

    def test_seed_assigns_canonical_lead_ai(self, registry):
        role = registry.get_role("Royal Bank of Arcadia")
        assert role is not None
        assert role.assigned_ai == "Dorris Fontaine"
        assert role.job_description == "Chief Financial Officer"

    def test_seed_is_idempotent_across_reconnect(self, tmp_path):
        db_path = tmp_path / "reopen.db"
        reg1 = RoleRegistry(db_path=db_path)
        reg1.close()
        reg2 = RoleRegistry(db_path=db_path)
        assert len(reg2.list_roles()) == len(all_seats())
        reg2.close()


class TestGetRole:
    def test_get_known_location(self, registry):
        role = registry.get_role("The Nexus")
        assert role is not None
        assert role.location == "The Nexus"
        assert role.pillar == "Architectural"

    def test_get_unknown_location_returns_none(self, registry):
        assert registry.get_role("Nonexistent Place") is None


class TestAssignAi:
    def test_reassign_updates_current_holder(self, registry):
        updated = registry.assign_ai(
            "Royal Bank of Arcadia", "New CFO AI", changed_by="admin:alice", reason="rotation"
        )
        assert updated.assigned_ai == "New CFO AI"
        assert updated.assigned_by == "admin:alice"

    def test_reassign_preserves_job_description(self, registry):
        updated = registry.assign_ai("Royal Bank of Arcadia", "New CFO AI")
        assert updated.job_description == "Chief Financial Officer"

    def test_unknown_location_raises(self, registry):
        with pytest.raises(UnknownLocationError):
            registry.assign_ai("Nonexistent Place", "Someone")

    def test_blank_ai_name_rejected(self, registry):
        with pytest.raises(ValueError):
            registry.assign_ai("The Nexus", "")
        with pytest.raises(ValueError):
            registry.assign_ai("The Nexus", "   ")

    def test_reassign_records_history(self, registry):
        registry.assign_ai("The Nexus", "Replacement AI", changed_by="admin:bob", reason="test")
        history = registry.get_history("The Nexus")
        assert len(history) == 1
        assert history[0].previous_ai == "Nexus-Prime"
        assert history[0].new_ai == "Replacement AI"
        assert history[0].changed_by == "admin:bob"

    def test_multiple_reassignments_all_recorded(self, registry):
        registry.assign_ai("The Nexus", "AI-1")
        registry.assign_ai("The Nexus", "AI-2")
        registry.assign_ai("The Nexus", "AI-3")
        history = registry.get_history("The Nexus")
        assert len(history) == 3
        # Most recent first.
        assert [h.new_ai for h in history] == ["AI-3", "AI-2", "AI-1"]


class TestRemoveAi:
    def test_remove_clears_assigned_ai(self, registry):
        updated = registry.remove_ai("The HIVE", changed_by="admin:carol")
        assert updated.assigned_ai is None

    def test_remove_records_history_with_null_new_ai(self, registry):
        registry.remove_ai("The HIVE", changed_by="admin:carol", reason="stepping down")
        history = registry.get_history("The HIVE")
        assert history[0].new_ai is None
        assert history[0].previous_ai == "The Queen"
        assert history[0].reason == "stepping down"

    def test_unknown_location_raises(self, registry):
        with pytest.raises(UnknownLocationError):
            registry.remove_ai("Nonexistent Place")

    def test_can_reassign_after_removal(self, registry):
        registry.remove_ai("The HIVE")
        updated = registry.assign_ai("The HIVE", "Fresh AI")
        assert updated.assigned_ai == "Fresh AI"


class TestHistory:
    def test_unknown_location_raises(self, registry):
        with pytest.raises(UnknownLocationError):
            registry.get_history("Nonexistent Place")

    def test_no_history_before_any_change(self, registry):
        assert registry.get_history("Luminous") == []


class TestRenameMigration:
    """A DB seeded before Infinity/The Lab/DocUtari's lead_ai names were
    reconciled to trance_one/platform_manifest.py's spelling (2026-07-24)
    must not get stuck resolving to the retired name forever — see
    docs/governance/LOCATION-FUNCTIONS.md's Verification Log."""

    def _seed_stale_db(self, db_path, overrides: dict) -> None:
        import sqlite3
        import time

        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """
            CREATE TABLE role_assignments (
                location TEXT PRIMARY KEY,
                job_description TEXT NOT NULL,
                assigned_ai TEXT,
                assigned_at REAL NOT NULL,
                assigned_by TEXT NOT NULL DEFAULT 'system'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE role_assignment_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                location TEXT NOT NULL,
                previous_ai TEXT,
                new_ai TEXT,
                changed_at REAL NOT NULL,
                changed_by TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT ''
            )
            """
        )
        now = time.time()
        for location, entity in PLATFORM_ENTITIES.items():
            assigned_ai = overrides.get(location, entity.lead_ai)
            conn.execute(
                "INSERT INTO role_assignments "
                "(location, job_description, assigned_ai, assigned_at, assigned_by) "
                "VALUES (?, ?, ?, ?, ?)",
                (location, JOB_DESCRIPTIONS.get(location, ""), assigned_ai, now, "system:seed"),
            )
        conn.commit()
        conn.close()

    def test_retired_names_are_backfilled_on_open(self, tmp_path):
        db_path = tmp_path / "stale.db"
        self._seed_stale_db(
            db_path,
            {
                "Infinity": "The Guardian (Anchor: Orb of Orisis)",
                "The Lab": "The Dr. & Slime",
                "DocUtari": "To be Defined",
                "TateKing": "Benji Tate & Sam King",
                "Arcadian Exchange": "The Porter Family",
            },
        )

        reg = RoleRegistry(db_path=db_path)
        try:
            assert reg.get_role("Infinity").assigned_ai == "The Guardian (Marcus Magnolia)"
            assert reg.get_role("The Lab").assigned_ai == "The Dr. (Nikolai O'denhime)"
            assert reg.get_role("DocUtari").assigned_ai == "Fiddsy"
            assert reg.get_role("TateKing").assigned_ai == "Benji Tate"
            assert reg.get_role("Arcadian Exchange").assigned_ai == "Clarence Porter"
        finally:
            reg.close()

    def test_migration_is_recorded_in_history(self, tmp_path):
        db_path = tmp_path / "stale_history.db"
        self._seed_stale_db(db_path, {"Infinity": "The Guardian (Anchor: Orb of Orisis)"})

        reg = RoleRegistry(db_path=db_path)
        try:
            history = reg.get_history("Infinity")
            assert len(history) == 1
            assert history[0].previous_ai == "The Guardian (Anchor: Orb of Orisis)"
            assert history[0].new_ai == "The Guardian (Marcus Magnolia)"
        finally:
            reg.close()

    def test_operator_reassignment_is_not_clobbered(self, tmp_path):
        db_path = tmp_path / "reassigned.db"
        self._seed_stale_db(db_path, {"The Lab": "A Different Operator-Assigned AI"})

        reg = RoleRegistry(db_path=db_path)
        try:
            assert reg.get_role("The Lab").assigned_ai == "A Different Operator-Assigned AI"
            assert reg.get_history("The Lab") == []
        finally:
            reg.close()

    def test_migration_is_idempotent_across_reconnect(self, tmp_path):
        db_path = tmp_path / "idempotent.db"
        self._seed_stale_db(db_path, {"DocUtari": "To be Defined"})

        reg1 = RoleRegistry(db_path=db_path)
        reg1.close()
        reg2 = RoleRegistry(db_path=db_path)
        try:
            assert reg2.get_role("DocUtari").assigned_ai == "Fiddsy"
            assert len(reg2.get_history("DocUtari")) == 1
        finally:
            reg2.close()


class TestExternalMandate:
    """The Arcadian Exchange trades in two directions.

    Each Porter holds an internal (user-facing) procurement seat and an
    external (market-facing) revenue seat -- two entwined Job Descriptions per
    AI, ten across the Location. The pairing is what makes them entwined: the
    price intelligence that tells a seat what to buy tells its twin what the
    same resource is worth selling.
    """

    LOCATION = "Arcadian Exchange"

    def test_ten_seats_five_of_each_mandate(self):
        seats = get_seats(self.LOCATION)
        assert len(seats) == 10
        assert sum(1 for s in seats if s.mandate == "internal") == 5
        assert sum(1 for s in seats if s.is_external) == 5

    def test_every_porter_holds_one_seat_of_each_mandate(self):
        seats = get_seats(self.LOCATION)
        by_ai: dict[str, set[str]] = {}
        for seat in seats:
            by_ai.setdefault(seat.designed_for, set()).add(seat.mandate)
        assert len(by_ai) == 5
        for ai, mandates in by_ai.items():
            assert mandates == {"internal", "external"}, ai

    def test_external_titles_are_distinct_from_their_internal_twins(self):
        titles = [s.job_description for s in get_seats(self.LOCATION)]
        assert len(set(titles)) == len(titles)

    def test_every_external_seat_names_an_internal_seat_that_exists(self):
        # The guard in get_seats drops an external seat whose twin is missing,
        # so a broken pairing would show up as a short list rather than a
        # loud failure. Assert the catalogue itself is intact.
        for location, externals in EXTERNAL_SEATS.items():
            internal_ids = {s.seat_id for s in get_seats(location) if s.mandate == "internal"}
            for external in externals:
                assert external.paired_with in internal_ids, external.seat_id

    def test_external_seats_do_not_count_as_untitled_co_leads(self):
        # External seats are non-primary by construction but always carry an
        # explicit title, so they must not be reported by the co-lead check.
        assert seats_without_a_distinct_title() == []

    def test_registry_seeds_and_orders_both_mandates(self, registry):
        seats = registry.get_location_seats(self.LOCATION)
        assert len(seats) == 10
        assert seats[0].seat_id == "primary"
        mandates = [s.mandate for s in seats]
        # Every internal seat precedes every external one.
        assert mandates == ["internal"] * 5 + ["external"] * 5

    def test_each_external_seat_seeds_to_the_ai_it_was_designed_for(self, registry):
        for seat in registry.get_location_seats(self.LOCATION):
            if seat.mandate == "external":
                assert seat.assigned_ai == seat.designed_for

    def test_external_seats_backfill_into_a_pre_existing_database(self, tmp_path):
        # A database created before the external mandate existed must gain the
        # new seats on the next startup without disturbing a manual
        # reassignment an operator already made to an internal one.
        db_path = tmp_path / "backfill.db"
        reg = RoleRegistry(db_path=db_path)
        reg.assign_ai(self.LOCATION, "Dorris Fontaine", seat_id="ann-porter", changed_by="operator")
        reg.close()

        conn = sqlite3.connect(db_path)
        conn.execute("DELETE FROM role_assignments WHERE seat_id LIKE '%-external'")
        conn.commit()
        conn.close()

        reopened = RoleRegistry(db_path=db_path)
        try:
            seats = {s.seat_id: s for s in reopened.get_location_seats(self.LOCATION)}
            assert len(seats) == 10
            assert seats["ann-porter"].assigned_ai == "Dorris Fontaine"
            assert seats["ann-porter-external"].assigned_ai == "Ann Porter"
        finally:
            reopened.close()

    def test_an_external_seat_can_be_reassigned_independently_of_its_twin(self, registry):
        registry.assign_ai(
            self.LOCATION,
            "Renik",
            seat_id="george-porter-external",
            changed_by="operator",
        )
        seats = {s.seat_id: s for s in registry.get_location_seats(self.LOCATION)}
        assert seats["george-porter-external"].assigned_ai == "Renik"
        # The internal twin is untouched -- the composite key scopes the write.
        assert seats["george-porter"].assigned_ai == "George Porter"

    def test_no_other_location_has_an_external_mandate(self):
        # Selling outside Trancendos is a decision about what the platform is
        # willing to trade, so it is deliberately confined to the commercial
        # desk until someone writes down a reason to widen it.
        assert set(EXTERNAL_SEATS) == {self.LOCATION}
        external_locations = {s.location for s in all_seats() if s.is_external}
        assert external_locations == {self.LOCATION}
