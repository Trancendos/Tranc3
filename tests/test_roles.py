# tests/test_roles.py
# Tests for src/roles/registry.py — the Role Assignment Registry
# (Location -> Job Description -> assigned AI).

from __future__ import annotations

import pytest

from src.entities.platform import JOB_DESCRIPTIONS, PLATFORM_ENTITIES
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
        roles = registry.list_roles()
        assert len(roles) == len(PLATFORM_ENTITIES)

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
        assert len(reg2.list_roles()) == len(PLATFORM_ENTITIES)
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
            },
        )

        reg = RoleRegistry(db_path=db_path)
        try:
            assert reg.get_role("Infinity").assigned_ai == "The Guardian (Marcus Magnolia)"
            assert reg.get_role("The Lab").assigned_ai == "The Dr. (Nikolai O'denhime)"
            assert reg.get_role("DocUtari").assigned_ai == "Fiddsy"
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
