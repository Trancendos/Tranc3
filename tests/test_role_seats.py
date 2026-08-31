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

    def test_every_location_has_exactly_one_primary_seat(self):
        """`get_role(location)` and both mutations default to the `primary`
        seat, so a Location without one is a Location whose default seat reads
        as a missing row -- None from get_role, UnknownLocationError from
        assign_ai. `is_primary` is `holder == lead_ai`, so a roster listing
        co-leads without the canonical name would produce exactly that."""
        for location in PLATFORM_ENTITIES:
            primaries = [s for s in get_seats(location) if s.is_primary]
            assert len(primaries) == 1, location

    def test_a_roster_omitting_its_canonical_lead_still_gets_a_primary(self, monkeypatch):
        """The guard, exercised rather than assumed. Simulates the roster edit
        that would otherwise remove a Location's default seat."""
        import copy

        from src.entities import platform as plat

        entity = copy.deepcopy(PLATFORM_ENTITIES["The Chaos Party"])
        entity.lead_ais = ["Alice Dream"]  # canonical lead_ai dropped
        monkeypatch.setitem(plat.PLATFORM_ENTITIES, "The Chaos Party", entity)

        seats = get_seats("The Chaos Party")
        primaries = [s for s in seats if s.is_primary]
        assert len(primaries) == 1
        assert primaries[0].designed_for == entity.lead_ai

    def test_the_primary_seat_is_first_whatever_the_roster_order(self, monkeypatch):
        """`get_seats` documents "primary first", so make that its own property.

        Today it holds only because every roster happens to list the canonical
        `lead_ai` first. A future roster edit that put a co-lead first would
        quietly falsify the docstring, and the registry's SQL ordering would
        paper over it for reads while `get_seats` callers saw the wrong head.
        """
        import copy

        from src.entities import platform as plat

        entity = copy.deepcopy(PLATFORM_ENTITIES["The Chaos Party"])
        entity.lead_ais = ["Alice Dream", entity.lead_ai]  # co-lead listed first
        monkeypatch.setitem(plat.PLATFORM_ENTITIES, "The Chaos Party", entity)

        seats = get_seats("The Chaos Party")
        assert seats[0].is_primary
        assert seats[0].designed_for == entity.lead_ai
        assert [s.designed_for for s in seats].count(entity.lead_ai) == 1

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


class TestInterruptedMigrationRecovery:
    """A rebuild stopped part-way must resume, not silently reseed.

    The failure this pins is the expensive kind: `sqlite3` autocommits DDL in
    its default legacy mode, so a rebuild written as four bare statements is
    four units of work. Killed between the rename and the copy, the next
    startup would find a `role_assignments` that already had `seat_id`, decide
    no migration was needed, leave the legacy rows stranded in
    `role_assignments_pre_seat`, and let `_seed_defaults` fill the empty table
    with defaults -- replacing every operator reassignment made before the
    upgrade, with nothing anywhere reporting it.
    """

    @staticmethod
    def _interrupted_db(path):
        """A database left exactly as a crash between RENAME and INSERT would."""
        conn = sqlite3.connect(path)
        conn.execute(
            "CREATE TABLE role_assignments_pre_seat ("
            "location TEXT PRIMARY KEY, job_description TEXT NOT NULL, assigned_ai TEXT, "
            "assigned_at REAL NOT NULL, assigned_by TEXT NOT NULL DEFAULT 'system')"
        )
        conn.execute(
            "INSERT INTO role_assignments_pre_seat VALUES (?, ?, ?, ?, ?)",
            ("The Lab", "Chief Engineering Officer", "A Human", time.time(), "operator"),
        )
        # The rebuilt table exists and is empty -- the crash point.
        conn.execute(
            "CREATE TABLE role_assignments ("
            "location TEXT NOT NULL, seat_id TEXT NOT NULL DEFAULT 'primary', "
            "job_description TEXT NOT NULL, assigned_ai TEXT, assigned_at REAL NOT NULL, "
            "assigned_by TEXT NOT NULL DEFAULT 'system', PRIMARY KEY (location, seat_id))"
        )
        conn.commit()
        conn.close()

    def test_a_stranded_operator_assignment_is_recovered(self, tmp_path):
        path = tmp_path / "interrupted.db"
        self._interrupted_db(path)
        reg = RoleRegistry(db_path=path)
        try:
            assert reg.get_role("The Lab").assigned_ai == "A Human", (
                "the pre-crash assignment was replaced by a seeded default"
            )
        finally:
            reg.close()

    def test_the_leftover_table_is_cleaned_up(self, tmp_path):
        path = tmp_path / "interrupted.db"
        self._interrupted_db(path)
        reg = RoleRegistry(db_path=path)
        try:
            assert not reg._has_table("role_assignments_pre_seat")
        finally:
            reg.close()

    def test_recovery_does_not_overwrite_a_newer_row(self, tmp_path):
        """On a resumed rebuild the new table may already hold copied rows. A
        legacy row must not clobber one that was already written."""
        path = tmp_path / "partial.db"
        self._interrupted_db(path)
        conn = sqlite3.connect(path)
        conn.execute(
            "INSERT INTO role_assignments VALUES (?, ?, ?, ?, ?, ?)",
            ("The Lab", "primary", "Chief Engineering Officer", "Newer", time.time(), "operator"),
        )
        conn.commit()
        conn.close()

        reg = RoleRegistry(db_path=path)
        try:
            assert reg.get_role("The Lab").assigned_ai == "Newer"
        finally:
            reg.close()

    def test_recovery_is_idempotent(self, tmp_path):
        path = tmp_path / "interrupted.db"
        self._interrupted_db(path)
        RoleRegistry(db_path=path).close()
        reg = RoleRegistry(db_path=path)
        try:
            assert reg.get_role("The Lab").assigned_ai == "A Human"
            assert len(reg.list_roles()) == len(all_seats())
        finally:
            reg.close()


class TestMigrationRollback:
    """The transaction must actually roll back, or the fix is decorative.

    A rebuild that fails mid-way and leaves the database half-converted is the
    same data-loss shape the transaction was added to prevent -- the `except`
    branch is the part that makes the guarantee real, so it is exercised rather
    than trusted.
    """

    def test_a_failed_rebuild_leaves_the_legacy_table_intact(self, tmp_path, monkeypatch):
        path = tmp_path / "fails.db"
        TestMigrationFromTheLocationOnlySchema._write_pre_seat_db(path)

        real_init = RoleRegistry._init_one_table

        def _explode(self, table):
            if table == "role_assignments":
                raise RuntimeError("disk full mid-rebuild")
            return real_init(self, table)

        monkeypatch.setattr(RoleRegistry, "_init_one_table", _explode)
        with pytest.raises(RuntimeError):
            RoleRegistry(db_path=path)

        # The rename is rolled back with everything else, so the original table
        # is still there under its own name and nothing has been lost.
        conn = sqlite3.connect(path)
        try:
            names = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            assert "role_assignments" in names
            row = conn.execute(
                "SELECT assigned_ai FROM role_assignments WHERE location = 'The Chaos Party'"
            ).fetchone()
            assert row[0] == "A Human"
        finally:
            conn.close()

    def test_a_failed_history_rebuild_also_rolls_back(self, tmp_path, monkeypatch):
        """Both rebuilds carry the same guarantee, so both branches are tested.
        Covering only the first would leave the second's rollback asserted by
        symmetry rather than by execution."""
        path = tmp_path / "history_fails.db"
        TestMigrationFromTheLocationOnlySchema._write_pre_seat_db(path)

        real_init = RoleRegistry._init_one_table

        def _explode(self, table):
            if table == "role_assignment_history":
                raise RuntimeError("disk full mid-rebuild")
            return real_init(self, table)

        monkeypatch.setattr(RoleRegistry, "_init_one_table", _explode)
        with pytest.raises(RuntimeError):
            RoleRegistry(db_path=path)

        conn = sqlite3.connect(path)
        try:
            row = conn.execute(
                "SELECT previous_ai FROM role_assignment_history WHERE location = 'The Chaos Party'"
            ).fetchone()
            assert row[0] == "The Mad Hatter", "the history rollback lost a row"
        finally:
            conn.close()

    def test_the_registry_recovers_on_the_next_open(self, tmp_path, monkeypatch):
        """A failed attempt must not poison later ones."""
        path = tmp_path / "retry.db"
        TestMigrationFromTheLocationOnlySchema._write_pre_seat_db(path)

        real_init = RoleRegistry._init_one_table
        monkeypatch.setattr(
            RoleRegistry,
            "_init_one_table",
            lambda self, table: (
                (_ for _ in ()).throw(RuntimeError("boom"))
                if table == "role_assignments"
                else real_init(self, table)
            ),
        )
        with pytest.raises(RuntimeError):
            RoleRegistry(db_path=path)

        monkeypatch.setattr(RoleRegistry, "_init_one_table", real_init)
        reg = RoleRegistry(db_path=path)
        try:
            assert reg.get_role("The Chaos Party").assigned_ai == "A Human"
        finally:
            reg.close()


class TestUnknownSeatOnRemoval:
    def test_removing_an_unknown_seat_is_refused(self, registry):
        """`assign_ai` already refuses one; `remove_ai` must too, or a typo'd
        seat silently reports success having vacated nothing."""
        with pytest.raises(UnknownLocationError):
            registry.remove_ai("The Chaos Party", seat_id="not-a-seat")
