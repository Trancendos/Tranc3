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
