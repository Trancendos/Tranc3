"""Tests for src/entities/effective.py — effective name resolution."""

from __future__ import annotations

from src.entities.effective import build_overrides_map, resolve_entity
from src.entities.platform import PLATFORM_ENTITIES, get_entity_by_pid


class TestEffectiveEntity:
    def test_resolve_lab_without_overrides(self):
        ent = resolve_entity("PID-LAB")
        assert ent is not None
        assert ent.location_key == "The Lab"
        assert ent.agent_beta is not None
        assert ent.agent_beta.code_name == "Syntax-Sage"
        assert ent.agent_beta.tier == 4

    def test_resolve_with_location_override(self):
        ov = {"location": "The Laboratory"}
        ent = resolve_entity("PID-LAB", ov)
        assert ent is not None
        assert ent.location == "The Laboratory"
        assert ent.canonical_location == "The Lab"

    def test_lead_ais_without_overrides(self):
        ent = resolve_entity("PID-LAB")
        assert ent is not None
        assert ent.lead_ais == ["The Dr. (Nikolai O'denhime)", "Slime"]

    def test_lead_ais_reflects_primary_override(self):
        ov = {"lead_ai": "New Dr."}
        ent = resolve_entity("PID-LAB", ov)
        assert ent is not None
        assert ent.lead_ai == "New Dr."
        # The overridden name replaces its own slot in the list — not a
        # stale canonical entry contradicting the resolved lead_ai — while
        # the untouched co-lead is left alone.
        assert ent.lead_ais == ["New Dr.", "Slime"]

    def test_build_overrides_map_from_rows(self):
        rows = [
            {"entity_type": "lead_ai", "slot": "", "override_name": "Dr. Slime"},
            {"entity_type": "tier", "slot": "agent_beta", "override_name": "4"},
        ]
        m = build_overrides_map(rows)
        assert m["lead_ai"] == "Dr. Slime"
        assert m["tier_agent_beta"] == "4"

    def test_unknown_pid_returns_none(self):
        assert resolve_entity("PID-INVALID") is None

    def test_syntax_sage_not_in_primes(self):
        entity = get_entity_by_pid("PID-LAB")
        assert entity is not None
        primes = list(entity.primes) if entity.primes else []
        assert "Syntax-Sage" not in primes
        assert "Sage" not in primes

    def test_lead_ai_is_always_a_member_of_lead_ais(self):
        # resolve_entity()'s lead_ais override substitution (effective.py)
        # matches list entries against entity.lead_ai by value — if a
        # future multi-lead entity's lead_ai ever fell out of sync with its
        # own lead_ais list, an admin override to lead_ai would silently
        # fail to replace anything, reproducing the exact self-contradiction
        # bug this module was fixed for. Guard the invariant every entity
        # actually relies on. Single-lead entities leave lead_ais empty
        # (not a duplicate [lead_ai]) — the substitution logic only matters
        # once an entity actually has a lead_ais list to substitute within.
        for entity in PLATFORM_ENTITIES.values():
            if not entity.lead_ais:
                continue
            assert entity.lead_ai in entity.lead_ais, (
                f"{entity.lead_ai!r} not present in its own lead_ais {entity.lead_ais!r}"
            )

    def test_build_overrides_map_with_store(self, monkeypatch):
        """
        Requires mocking OverrideStore and fetching a list of overrides.
        We mock the internal db fetch of OverrideStore to return a list of overrides,
        which are then passed into build_overrides_map.
        """
        import src.entities.override_store as override_store

        class MockCursor:
            def fetchall(self):
                return [
                    {
                        "location_pid": "PID-LAB",
                        "entity_type": "lead_ai",
                        "slot": "",
                        "override_name": "Dr. Slime",
                    },
                ]

        class MockConnection:
            def execute(self, *args, **kwargs):
                return MockCursor()

            def close(self):
                pass

        def mock_connect(*args, **kwargs):
            return MockConnection()

        # Mock OverrideStore's db connection and path
        monkeypatch.setattr(override_store, "sqlite3_connect", mock_connect)
        monkeypatch.setattr(override_store.Path, "is_file", lambda self: True)
        override_store.invalidate_override_cache()

        # Fetch a list of overrides using OverrideStore
        all_overrides = override_store.load_all_overrides_by_pid(force=True)

        # build_overrides_map is used internally by load_all_overrides_by_pid
        assert "PID-LAB" in all_overrides
        assert all_overrides["PID-LAB"]["lead_ai"] == "Dr. Slime"
