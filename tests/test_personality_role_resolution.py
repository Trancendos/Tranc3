# tests/test_personality_role_resolution.py
# Tests for src/personality/role_resolution.py — bridges the Role Assignment
# Registry (src/roles/registry.py) to the Personality Matrix
# (src/personality/matrix.py), so /chat can resolve a Location's active
# personality from whoever currently holds its Job Description instead of a
# caller-supplied string going stale after a reassignment.

from __future__ import annotations

import pytest

from src.personality.matrix import PersonalityMatrix
from src.personality.role_resolution import AI_NAME_TO_PROFILE_ID, resolve_personality_for_location
from src.roles.registry import RoleRegistry


@pytest.fixture
def registry(tmp_path, monkeypatch):
    reg = RoleRegistry(db_path=tmp_path / "role_registry_test.db")
    monkeypatch.setattr("src.roles.registry._registry", reg)
    # assign_ai()/remove_ai() best-effort-notify the Relations activity feed
    # via the *default* module-level singleton (src/relations/registry.py),
    # which this fixture's temp RoleRegistry doesn't touch or override — left
    # unmocked, every reassignment test here would write real rows into the
    # shared default relations DB. No-op it for the duration of the test.
    monkeypatch.setattr("src.roles.registry._emit_relations_event", lambda *a, **k: None)
    yield reg
    reg.close()


class TestResolvePersonalityForLocation:
    def test_resolves_seeded_assignment(self, registry):
        assert resolve_personality_for_location("Royal Bank of Arcadia") == "dorris-fontaine"

    def test_resolves_after_reassignment(self, registry):
        registry.assign_ai("Royal Bank of Arcadia", "Cornelius MacIntyre", changed_by="test")
        assert resolve_personality_for_location("Royal Bank of Arcadia") == "cornelius-macintyre"

    def test_unknown_location_returns_none(self, registry):
        assert resolve_personality_for_location("Not A Real Location") is None

    def test_vacant_seat_returns_none(self, registry):
        registry.remove_ai("Royal Bank of Arcadia", changed_by="test")
        assert resolve_personality_for_location("Royal Bank of Arcadia") is None

    def test_unmapped_assigned_ai_returns_none(self, registry):
        registry.assign_ai(
            "Royal Bank of Arcadia", "Some New AI Nobody Mapped Yet", changed_by="test"
        )
        assert resolve_personality_for_location("Royal Bank of Arcadia") is None

    def test_the_spark_seed_resolves_via_imfy_mapping(self, registry):
        # The Spark's seed assigned_ai is "Imfy" (src/entities/platform.py's
        # lead_ai) which has no profile of its own — it maps onto
        # norman-hawkins.json, whose own "serves" list already names
        # the-spark. See docs/governance/PERSONALITY-ARCHETYPES.md §3.
        assert resolve_personality_for_location("The Spark") == "norman-hawkins"

    def test_docutari_seed_has_no_profile_yet(self, registry):
        # DocUtari's lead_ai is "Fiddsy" (per trance_one/platform_manifest.py)
        # — a real named AI, but no personality profile has been authored
        # for it yet, so it must resolve to no profile.
        assert resolve_personality_for_location("DocUtari") is None

    def test_the_citadel_and_think_tank_resolve_to_trancendos(self, registry):
        assert resolve_personality_for_location("The Citadel") == "trancendos"
        assert resolve_personality_for_location("Think Tank") == "trancendos"

    def test_infinity_resolves_via_guardian_marcus_magnolia(self, registry):
        # Infinity's seed lead_ai is "The Guardian (Marcus Magnolia)" (synced
        # from trance_one/platform_manifest.py's lead_ais split — see
        # docs/governance/PERSONALITY-ARCHETYPES.md).
        assert resolve_personality_for_location("Infinity") == "the-guardian"

    def test_the_lab_resolves_via_the_dr_nikolai_odenhime(self, registry):
        # The Lab's seed lead_ai is "The Dr. (Nikolai O'denhime)", also
        # synced from trance_one/platform_manifest.py.
        assert resolve_personality_for_location("The Lab") == "the-dr-slime"

    def test_registry_failure_returns_none_instead_of_raising(self, registry, monkeypatch):
        # A Role Registry outage (e.g. its SQLite file can't be opened)
        # must degrade to the caller's fallback, not take /chat down with it.
        def _boom(self, location):
            raise RuntimeError("registry unavailable")

        monkeypatch.setattr(type(registry), "get_role", _boom)
        assert resolve_personality_for_location("Royal Bank of Arcadia") is None


class TestMappingTableIntegrity:
    def test_every_mapped_profile_id_actually_exists(self):
        matrix = PersonalityMatrix()
        available = set(matrix.list_profiles())
        missing = {
            ai_name: profile_id
            for ai_name, profile_id in AI_NAME_TO_PROFILE_ID.items()
            if profile_id is not None and profile_id not in available
        }
        assert not missing, f"Mapped profile ids with no matching profile file: {missing}"

    def test_every_seeded_lead_ai_is_covered(self):
        from src.entities.platform import PLATFORM_ENTITIES

        uncovered = {
            entity.lead_ai
            for entity in PLATFORM_ENTITIES.values()
            if entity.lead_ai not in AI_NAME_TO_PROFILE_ID
        }
        assert not uncovered, f"lead_ai names with no entry in AI_NAME_TO_PROFILE_ID: {uncovered}"
