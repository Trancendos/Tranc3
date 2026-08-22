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

    def test_list_all_effective(self):
        from src.entities.effective import list_all_effective
        entities = list_all_effective()
        assert len(entities) > 0
        assert any(e.pid == "PID-LAB" for e in entities)

        # Test with overrides applied
        ov_map = {"PID-LAB": {"lead_ai": "New Leader", "tier_lead_ai": "2"}}
        entities_ov = list_all_effective(overrides_by_pid=ov_map)
        lab = next(e for e in entities_ov if e.pid == "PID-LAB")
        assert lab.lead_ai == "New Leader"
        assert lab.display_tier("lead_ai", 3) == 2

    def test_display_tier(self):
        ent = resolve_entity("PID-LAB", {"tier_agent_beta": "not_an_int", "tier_bot_01": "2"})
        assert ent is not None

        # test fallback
        assert ent.display_tier("agent_beta", 4) == 4

        # test valid string parsing
        assert ent.display_tier("bot_01", 5) == 2

        # test missing key fallback
        assert ent.display_tier("missing_key", 99) == 99

    def test_tier_overrides_invalid_and_valid(self):
        ov = {
            "tier_agent_beta": "notanint",
            "tier_bot_01": "1",
            "tier_lead_ai": "invalid"
        }
        ent = resolve_entity("PID-LAB", ov)
        assert ent is not None

        assert ent.agent_beta is not None
        # fallback to 4
        assert ent.agent_beta.tier == 4
        assert ent.agent_beta.tier_override is None

        assert ent.bots["01"] is not None
        # applies valid override
        assert ent.bots["01"].tier == 1
        assert ent.bots["01"].tier_override == 1

        # lead tier defaults to 3 on invalid
        assert ent.overrides_applied["tier_lead_ai"] == "invalid"

    def test_missing_agents_and_bots(self):
        # Arcadian Exchange typically does not have standard agents/bots
        ent = resolve_entity("PID-ARC")
        if ent is not None:
            assert ent.agent_alpha is None or ent.agent_alpha.role == "alpha"

    def test_missing_agent_beta(self):
        # Temporarily monkeypatch the cache to ensure we get a None agent_beta
        ent_base = get_entity_by_pid("PID-LAB")
        assert ent_base is not None
        old_beta = getattr(ent_base, "agent_beta", None)
        ent_base.agent_beta = None

        try:
            ent = resolve_entity("PID-LAB", {"tier_agent_beta": "notanint"})
            assert ent is not None
            assert getattr(ent, "agent_beta", None) is None
        finally:
            ent_base.agent_beta = old_beta

    def test_missing_bot(self):
        # Temporarily monkeypatch the cache to ensure we get a None bot
        ent_base = get_entity_by_pid("PID-LAB")
        assert ent_base is not None
        old_bot = getattr(ent_base, "bot_01", None)
        ent_base.bot_01 = None

        try:
            ent = resolve_entity("PID-LAB", {"tier_bot_01": "notanint"})
            assert ent is not None
            assert ent.bots.get("01") is None
        finally:
            ent_base.bot_01 = old_bot
