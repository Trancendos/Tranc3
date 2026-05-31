"""Tests for src/entities/effective.py — effective name resolution."""

from __future__ import annotations

import pytest

from src.entities.effective import build_overrides_map, resolve_entity
from src.entities.platform import get_entity_by_pid


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
