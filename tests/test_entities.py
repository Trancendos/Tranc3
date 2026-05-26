# tests/test_entities.py
# Tests for src/entities/platform.py
# Covers Pillar, Bot, Agent, LocationEntity, PLATFORM_ENTITIES registry,
# WORKER_ENTITY_MAP, ID assignment, and lookup functions.

from __future__ import annotations

from src.entities.platform import (
    LOCATION_ABBREVS,
    PILLAR_ABBREVS,
    PLATFORM_ENTITIES,
    PRIME_ABBREVS,
    WORKER_ENTITY_MAP,
    Agent,
    Bot,
    Pillar,
    get_all_ids,
    get_entity_by_aid,
    get_entity_by_pid,
    get_entity_for_location,
    get_entity_for_port,
)

# ── Pillar enum ──────────────────────────────────────────────────────


class TestPillar:
    def test_all_pillars_defined(self):
        expected = {
            "Architectural",
            "Commercial / Financial",
            "Creativity",
            "Development (Code)",
            "Knowledge",
            "Security",
            "DevOps",
            "Wellbeing",
        }
        actual = {p.value for p in Pillar}
        assert actual == expected

    def test_pillar_is_str(self):
        assert isinstance(Pillar.SECURITY, str)


# ── Bot and Agent dataclasses ────────────────────────────────────────


class TestBot:
    def test_defaults(self):
        bot = Bot(code_name="Test-Bot", description="A test bot")
        assert bot.code_name == "Test-Bot"
        assert bot.nid == ""

    def test_nid_assigned(self):
        bot = Bot(code_name="Test-Bot", description="A test bot", nid="NID-NXS-01")
        assert bot.nid == "NID-NXS-01"


class TestAgent:
    def test_defaults(self):
        agent = Agent(code_name="Test-Agent", description="A test agent")
        assert agent.code_name == "Test-Agent"
        assert agent.sid == ""

    def test_sid_assigned(self):
        agent = Agent(code_name="Test-Agent", description="A test agent", sid="SID-NXS-01")
        assert agent.sid == "SID-NXS-01"


# ── LocationEntity ───────────────────────────────────────────────────


class TestLocationEntity:
    def test_to_health_meta(self):
        entity = PLATFORM_ENTITIES["The Nexus"]
        meta = entity.to_health_meta()
        assert meta["location"] == "The Nexus"
        assert meta["pillar"] == "Architectural"
        assert meta["lead_ai"] == "Nexus-Prime"
        assert isinstance(meta["primes"], list)
        assert isinstance(meta["primary_function"], str)


# ── PLATFORM_ENTITIES registry ──────────────────────────────────────


class TestPlatformEntities:
    def test_43_locations(self):
        assert len(PLATFORM_ENTITIES) == 43

    def test_all_pillars_represented(self):
        pillars = {e.pillar for e in PLATFORM_ENTITIES.values()}
        for p in Pillar:
            assert p in pillars, f"No entity with pillar {p.value}"

    def test_all_have_lead_ai(self):
        for name, entity in PLATFORM_ENTITIES.items():
            assert entity.lead_ai, f"{name} has no lead_ai"

    def test_all_have_primary_function(self):
        for name, entity in PLATFORM_ENTITIES.items():
            assert entity.primary_function, f"{name} has no primary_function"

    def test_all_have_abilities(self):
        for name, entity in PLATFORM_ENTITIES.items():
            assert len(entity.abilities) > 0, f"{name} has no abilities"

    def test_all_have_primes(self):
        for name, entity in PLATFORM_ENTITIES.items():
            assert len(entity.primes) > 0, f"{name} has no primes"

    def test_all_have_agents(self):
        for name, entity in PLATFORM_ENTITIES.items():
            assert entity.agent_alpha.code_name, f"{name} missing agent_alpha"
            assert entity.agent_beta.code_name, f"{name} missing agent_beta"

    def test_all_have_bots(self):
        for name, entity in PLATFORM_ENTITIES.items():
            assert entity.bot_01.code_name, f"{name} missing bot_01"
            assert entity.bot_02.code_name, f"{name} missing bot_02"
            assert entity.bot_03.code_name, f"{name} missing bot_03"
            assert entity.bot_04.code_name, f"{name} missing bot_04"

    def test_guardian_canonical_names(self):
        """Verify the Guardian naming convention is correct in entity data."""
        infinity = PLATFORM_ENTITIES["Infinity"]
        assert infinity.lead_ai == "The Guardian (Anchor: Orb of Orisis)"

        the_void = PLATFORM_ENTITIES["The Void"]
        assert "The Guardian (Marcus Magnolia)" in the_void.primes


# ── Universal ID Taxonomy ────────────────────────────────────────────


class TestUniversalIDs:
    def test_all_entities_have_pid(self):
        for name, entity in PLATFORM_ENTITIES.items():
            assert entity.pid.startswith("PID-"), f"{name} has bad PID: {entity.pid}"

    def test_all_entities_have_aid(self):
        for name, entity in PLATFORM_ENTITIES.items():
            assert entity.aid.startswith("AID-"), f"{name} has bad AID: {entity.aid}"

    def test_all_agents_have_sid(self):
        for name, entity in PLATFORM_ENTITIES.items():
            assert entity.agent_alpha.sid.startswith("SID-"), (
                f"{name} agent_alpha has bad SID: {entity.agent_alpha.sid}"
            )
            assert entity.agent_beta.sid.startswith("SID-"), (
                f"{name} agent_beta has bad SID: {entity.agent_beta.sid}"
            )

    def test_all_bots_have_nid(self):
        for name, entity in PLATFORM_ENTITIES.items():
            for bot_attr in ("bot_01", "bot_02", "bot_03", "bot_04"):
                bot = getattr(entity, bot_attr)
                assert bot.nid.startswith("NID-"), f"{name} {bot_attr} has bad NID: {bot.nid}"

    def test_pid_matches_abbrev(self):
        for name, entity in PLATFORM_ENTITIES.items():
            abbrev = LOCATION_ABBREVS.get(name)
            if abbrev:
                assert entity.pid == f"PID-{abbrev}", (
                    f"{name} PID mismatch: expected PID-{abbrev}, got {entity.pid}"
                )

    def test_aid_format(self):
        for name, entity in PLATFORM_ENTITIES.items():
            abbrev = LOCATION_ABBREVS.get(name)
            if abbrev:
                assert entity.aid == f"AID-{abbrev}-01", (
                    f"{name} AID mismatch: expected AID-{abbrev}-01, got {entity.aid}"
                )


# ── WORKER_ENTITY_MAP ────────────────────────────────────────────────


class TestWorkerEntityMap:
    def test_primary_worker_ports(self):
        assert 8004 in WORKER_ENTITY_MAP
        assert WORKER_ENTITY_MAP[8004] == "The Nexus"

    def test_supporting_worker_ports(self):
        assert 8006 in WORKER_ENTITY_MAP
        assert WORKER_ENTITY_MAP[8006] == "Infinity"

    def test_all_mapped_ports_have_entities(self):
        for port, name in WORKER_ENTITY_MAP.items():
            assert name in PLATFORM_ENTITIES, f"Port {port} maps to unknown entity '{name}'"


# ── Lookup functions ─────────────────────────────────────────────────


class TestLookupFunctions:
    def test_get_entity_for_port(self):
        entity = get_entity_for_port(8004)
        assert entity is not None
        assert entity.location == "The Nexus"

    def test_get_entity_for_port_unknown(self):
        assert get_entity_for_port(9999) is None

    def test_get_entity_for_location(self):
        entity = get_entity_for_location("Infinity")
        assert entity is not None
        assert entity.lead_ai == "The Guardian (Anchor: Orb of Orisis)"

    def test_get_entity_for_location_unknown(self):
        assert get_entity_for_location("Nonexistent") is None

    def test_get_entity_by_pid(self):
        entity = get_entity_by_pid("PID-NXS")
        assert entity is not None
        assert entity.location == "The Nexus"

    def test_get_entity_by_pid_unknown(self):
        assert get_entity_by_pid("PID-XXX") is None

    def test_get_entity_by_aid(self):
        entity = get_entity_by_aid("AID-NXS-01")
        assert entity is not None
        assert entity.location == "The Nexus"

    def test_get_entity_by_aid_unknown(self):
        assert get_entity_by_aid("AID-XXX-99") is None


# ── get_all_ids() ────────────────────────────────────────────────────


class TestGetAllIds:
    def test_returns_list(self):
        ids = get_all_ids()
        assert isinstance(ids, list)
        assert len(ids) > 0

    def test_total_ids(self):
        """43 locations × 7 IDs each (PID + AID + 2 SIDs + 4 NIDs) = 301."""
        ids = get_all_ids()
        # 43 PIDs + 43 AIDs + 86 SIDs + 172 NIDs = 344
        assert len(ids) == 344

    def test_each_entry_has_id_field(self):
        ids = get_all_ids()
        for entry in ids:
            assert "id" in entry
            assert "tier" in entry
            assert "name" in entry

    def test_tiers_present(self):
        ids = get_all_ids()
        tiers = {entry["tier"] for entry in ids}
        assert "Location" in tiers
        assert 3 in tiers
        assert 4 in tiers
        assert 5 in tiers


# ── Abbreviation dictionaries ────────────────────────────────────────


class TestAbbreviationDicts:
    def test_location_abbrevs_cover_all_entities(self):
        for name in PLATFORM_ENTITIES:
            assert name in LOCATION_ABBREVS, f"Missing LOCATION_ABBREVS for '{name}'"

    def test_pillar_abbrevs_match_enum(self):
        for p in Pillar:
            assert p.value in PILLAR_ABBREVS, f"Missing PILLAR_ABBREVS for '{p.value}'"

    def test_prime_abbrevs_non_empty(self):
        assert len(PRIME_ABBREVS) > 0

    def test_location_abbrevs_3_chars(self):
        for name, abbrev in LOCATION_ABBREVS.items():
            assert len(abbrev) == 3, f"Abbrev for '{name}' is not 3 chars: '{abbrev}'"
