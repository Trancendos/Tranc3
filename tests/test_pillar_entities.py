"""
Tests for Tranc3 Pillar Entity Architecture
==============================================
Comprehensive tests for the 9 platform locations, entity hierarchy,
tier system, and pillar registry.
"""

from Dimensional.pillars.entities import (
    LOCATION_CONFIGS,
    LOCATIONS,
    EntityTier,
    EntityType,
    PillarEntity,
    PillarLocation,
    PillarLocationConfig,
    PillarRegistry,
    get_pillar_registry,
)

# ──────────────────────────────────────────────
# EntityTier Tests
# ──────────────────────────────────────────────


class TestEntityTier:
    def test_tier_values(self):
        assert EntityTier.HUMAN == 0
        assert EntityTier.ORCHESTRATOR == 1
        assert EntityTier.PRIME == 2
        assert EntityTier.AI == 3
        assert EntityTier.AGENT == 4
        assert EntityTier.BOT == 5

    def test_tier_ordering(self):
        assert EntityTier.HUMAN < EntityTier.ORCHESTRATOR
        assert EntityTier.ORCHESTRATOR < EntityTier.PRIME
        assert EntityTier.PRIME < EntityTier.AI
        assert EntityTier.AI < EntityTier.AGENT
        assert EntityTier.AGENT < EntityTier.BOT


# ──────────────────────────────────────────────
# EntityType Tests
# ──────────────────────────────────────────────


class TestEntityType:
    def test_entity_types(self):
        assert EntityType.HUMAN == "human"
        assert EntityType.ORCHESTRATOR == "orchestrator"
        assert EntityType.PRIME == "prime"
        assert EntityType.AI == "ai"
        assert EntityType.AGENT == "agent"
        assert EntityType.BOT == "bot"


# ──────────────────────────────────────────────
# PillarLocation Tests
# ──────────────────────────────────────────────


class TestPillarLocation:
    def test_nine_locations(self):
        assert len(PillarLocation) == 9

    def test_location_values(self):
        assert PillarLocation.INFINITY_ONE == "infinity_one"
        assert PillarLocation.NEXUS == "nexus"
        assert PillarLocation.HIVE == "hive"
        assert PillarLocation.SENTINEL_STATION == "sentinel_station"
        assert PillarLocation.VAULT == "vault"
        assert PillarLocation.CITADEL == "citadel"
        assert PillarLocation.LIBRARY == "library"
        assert PillarLocation.STUDIO == "studio"
        assert PillarLocation.OBSERVATORY == "observatory"

    def test_locations_list(self):
        assert len(LOCATIONS) == 9
        for loc in LOCATIONS:
            assert isinstance(loc, PillarLocation)


# ──────────────────────────────────────────────
# PillarEntity Tests
# ──────────────────────────────────────────────


class TestPillarEntity:
    def test_create_entity(self):
        entity = PillarEntity(
            name="Test AI",
            entity_type=EntityType.AI,
            tier=EntityTier.AI,
            location=PillarLocation.NEXUS,
        )
        assert entity.name == "Test AI"
        assert entity.entity_type == EntityType.AI
        assert entity.tier == EntityTier.AI
        assert entity.location == PillarLocation.NEXUS
        assert entity.status == "active"

    def test_entity_auto_id(self):
        entity = PillarEntity(
            name="Test",
            entity_type=EntityType.BOT,
            tier=EntityTier.BOT,
            location=PillarLocation.HIVE,
        )
        assert entity.entity_id is not None
        assert len(entity.entity_id) > 0

    def test_add_child(self):
        parent = PillarEntity(
            name="Parent AI",
            entity_type=EntityType.AI,
            tier=EntityTier.AI,
            location=PillarLocation.NEXUS,
        )
        child = PillarEntity(
            name="Child Agent",
            entity_type=EntityType.AGENT,
            tier=EntityTier.AGENT,
            location=PillarLocation.NEXUS,
            parent_id=parent.entity_id,
        )
        parent.add_child(child.entity_id)
        assert child.entity_id in parent.children_ids

    def test_remove_child(self):
        parent = PillarEntity(
            name="Parent AI",
            entity_type=EntityType.AI,
            tier=EntityTier.AI,
            location=PillarLocation.NEXUS,
        )
        child_id = "child-123"
        parent.add_child(child_id)
        parent.remove_child(child_id)
        assert child_id not in parent.children_ids

    def test_entity_with_parent(self):
        entity = PillarEntity(
            name="Agent",
            entity_type=EntityType.AGENT,
            tier=EntityTier.AGENT,
            location=PillarLocation.HIVE,
            parent_id="parent-123",
        )
        assert entity.parent_id == "parent-123"

    def test_entity_defaults(self):
        entity = PillarEntity(
            name="Bot",
            entity_type=EntityType.BOT,
            tier=EntityTier.BOT,
            location=PillarLocation.VAULT,
        )
        assert entity.children_ids == []
        assert entity.metadata == {}
        assert entity.created_at is not None


# ──────────────────────────────────────────────
# PillarLocationConfig Tests
# ──────────────────────────────────────────────


class TestPillarLocationConfig:
    def test_create_config(self):
        config = PillarLocationConfig(
            location=PillarLocation.NEXUS,
            display_name="The Nexus",
            description="AI Hub",
            bridge_port=8050,
        )
        assert config.location == PillarLocation.NEXUS
        assert config.display_name == "The Nexus"
        assert config.bridge_port == 8050

    def test_location_configs_exist(self):
        assert len(LOCATION_CONFIGS) == 9
        for loc in PillarLocation:
            assert loc in LOCATION_CONFIGS

    def test_location_config_ports(self):
        assert LOCATION_CONFIGS[PillarLocation.INFINITY_ONE].bridge_port == 8070
        assert LOCATION_CONFIGS[PillarLocation.NEXUS].bridge_port == 8050
        assert LOCATION_CONFIGS[PillarLocation.HIVE].bridge_port == 8060


# ──────────────────────────────────────────────
# PillarRegistry Tests
# ──────────────────────────────────────────────


class TestPillarRegistry:
    def test_create_registry(self):
        registry = PillarRegistry()
        assert registry.total_entities == 0

    def test_register_entity(self):
        registry = PillarRegistry()
        entity = PillarEntity(
            name="Test AI",
            entity_type=EntityType.AI,
            tier=EntityTier.AI,
            location=PillarLocation.NEXUS,
        )
        registry.register(entity)
        assert registry.total_entities == 1

    def test_unregister_entity(self):
        registry = PillarRegistry()
        entity = PillarEntity(
            name="Test AI",
            entity_type=EntityType.AI,
            tier=EntityTier.AI,
            location=PillarLocation.NEXUS,
        )
        registry.register(entity)
        result = registry.unregister(entity.entity_id)
        assert result is not None
        assert registry.total_entities == 0

    def test_get_entity(self):
        registry = PillarRegistry()
        entity = PillarEntity(
            name="Test AI",
            entity_type=EntityType.AI,
            tier=EntityTier.AI,
            location=PillarLocation.NEXUS,
        )
        registry.register(entity)
        found = registry.get(entity.entity_id)
        assert found is not None
        assert found.name == "Test AI"

    def test_get_nonexistent_entity(self):
        registry = PillarRegistry()
        assert registry.get("nonexistent") is None

    def test_get_by_location(self):
        registry = PillarRegistry()
        registry.register(
            PillarEntity(
                name="Nexus AI",
                entity_type=EntityType.AI,
                tier=EntityTier.AI,
                location=PillarLocation.NEXUS,
            )
        )
        registry.register(
            PillarEntity(
                name="Hive AI",
                entity_type=EntityType.AI,
                tier=EntityTier.AI,
                location=PillarLocation.HIVE,
            )
        )
        nexus_entities = registry.get_by_location(PillarLocation.NEXUS)
        assert len(nexus_entities) == 1
        assert nexus_entities[0].name == "Nexus AI"

    def test_get_by_tier(self):
        registry = PillarRegistry()
        registry.register(
            PillarEntity(
                name="AI 1",
                entity_type=EntityType.AI,
                tier=EntityTier.AI,
                location=PillarLocation.NEXUS,
            )
        )
        registry.register(
            PillarEntity(
                name="Agent 1",
                entity_type=EntityType.AGENT,
                tier=EntityTier.AGENT,
                location=PillarLocation.NEXUS,
            )
        )
        ai_entities = registry.get_by_tier(EntityTier.AI)
        assert len(ai_entities) == 1

    def test_get_by_type(self):
        registry = PillarRegistry()
        registry.register(
            PillarEntity(
                name="Agent A",
                entity_type=EntityType.AGENT,
                tier=EntityTier.AGENT,
                location=PillarLocation.NEXUS,
            )
        )
        registry.register(
            PillarEntity(
                name="Bot 1",
                entity_type=EntityType.BOT,
                tier=EntityTier.BOT,
                location=PillarLocation.NEXUS,
            )
        )
        agents = registry.get_by_type(EntityType.AGENT)
        assert len(agents) == 1

    def test_get_children(self):
        registry = PillarRegistry()
        parent = PillarEntity(
            name="AI",
            entity_type=EntityType.AI,
            tier=EntityTier.AI,
            location=PillarLocation.NEXUS,
        )
        registry.register(parent)
        child = PillarEntity(
            name="Agent",
            entity_type=EntityType.AGENT,
            tier=EntityTier.AGENT,
            location=PillarLocation.NEXUS,
            parent_id=parent.entity_id,
        )
        registry.register(child)
        parent.add_child(child.entity_id)
        children = registry.get_children(parent.entity_id)
        assert len(children) == 1
        assert children[0].name == "Agent"

    def test_get_parent(self):
        registry = PillarRegistry()
        parent = PillarEntity(
            name="AI",
            entity_type=EntityType.AI,
            tier=EntityTier.AI,
            location=PillarLocation.NEXUS,
        )
        registry.register(parent)
        child = PillarEntity(
            name="Agent",
            entity_type=EntityType.AGENT,
            tier=EntityTier.AGENT,
            location=PillarLocation.NEXUS,
            parent_id=parent.entity_id,
        )
        registry.register(child)
        found_parent = registry.get_parent(child.entity_id)
        assert found_parent is not None
        assert found_parent.entity_id == parent.entity_id

    def test_location_count(self):
        registry = PillarRegistry()
        registry.register(
            PillarEntity(
                name="Nexus AI",
                entity_type=EntityType.AI,
                tier=EntityTier.AI,
                location=PillarLocation.NEXUS,
            )
        )
        assert registry.location_count == 1

    def test_get_location_summary(self):
        registry = PillarRegistry()
        registry.register(
            PillarEntity(
                name="Nexus AI",
                entity_type=EntityType.AI,
                tier=EntityTier.AI,
                location=PillarLocation.NEXUS,
            )
        )
        summary = registry.get_location_summary(PillarLocation.NEXUS)
        assert summary["entity_count"] == 1
        assert summary["location"] == "nexus"

    def test_get_full_summary(self):
        registry = PillarRegistry()
        registry.register(
            PillarEntity(
                name="Nexus AI",
                entity_type=EntityType.AI,
                tier=EntityTier.AI,
                location=PillarLocation.NEXUS,
            )
        )
        summary = registry.get_full_summary()
        assert "total_entities" in summary
        assert "active_locations" in summary
        assert "locations" in summary
        assert "by_tier" in summary


# ──────────────────────────────────────────────
# Seed Location Tests
# ──────────────────────────────────────────────


class TestSeedLocation:
    def test_seed_single_location(self):
        registry = PillarRegistry()
        entities = registry.seed_location(PillarLocation.NEXUS)
        assert len(entities) == 8  # 1 Prime + 1 AI + 2 Agents + 4 Bots
        assert registry.total_entities == 8

    def test_seed_location_entity_types(self):
        registry = PillarRegistry()
        entities = registry.seed_location(PillarLocation.NEXUS)
        primes = [e for e in entities if e.entity_type == EntityType.PRIME]
        ais = [e for e in entities if e.entity_type == EntityType.AI]
        agents = [e for e in entities if e.entity_type == EntityType.AGENT]
        bots = [e for e in entities if e.entity_type == EntityType.BOT]
        assert len(primes) == 1
        assert len(ais) == 1
        assert len(agents) == 2
        assert len(bots) == 4

    def test_seed_location_tiers(self):
        registry = PillarRegistry()
        entities = registry.seed_location(PillarLocation.HIVE)
        tier2 = [e for e in entities if e.tier == EntityTier.PRIME]
        tier3 = [e for e in entities if e.tier == EntityTier.AI]
        tier4 = [e for e in entities if e.tier == EntityTier.AGENT]
        tier5 = [e for e in entities if e.tier == EntityTier.BOT]
        assert len(tier2) == 1
        assert len(tier3) == 1
        assert len(tier4) == 2
        assert len(tier5) == 4

    def test_seed_location_hierarchy(self):
        """Verify parent-child relationships in seeded location."""
        registry = PillarRegistry()
        entities = registry.seed_location(PillarLocation.NEXUS)
        prime = [e for e in entities if e.entity_type == EntityType.PRIME][0]
        lead_ai = [e for e in entities if e.entity_type == EntityType.AI][0]
        agents = [e for e in entities if e.entity_type == EntityType.AGENT]
        bots = [e for e in entities if e.entity_type == EntityType.BOT]

        # Lead AI is child of Prime
        assert lead_ai.parent_id == prime.entity_id
        assert lead_ai.entity_id in prime.children_ids

        # Agents are children of Lead AI
        for agent in agents:
            assert agent.parent_id == lead_ai.entity_id

        # Bots are children of Agent Alpha
        agent_alpha = agents[0]
        for bot in bots:
            assert bot.parent_id == agent_alpha.entity_id

    def test_seed_all_locations(self):
        registry = PillarRegistry()
        result = registry.seed_all_locations()
        assert len(result) == 9
        assert registry.total_entities == 9 * 8  # 8 entities per location

    def test_seed_all_creates_hierarchy(self):
        registry = PillarRegistry()
        registry.seed_all_locations()
        # Every location should have a Prime
        for loc in PillarLocation:
            loc_entities = registry.get_by_location(loc)
            primes = [e for e in loc_entities if e.entity_type == EntityType.PRIME]
            assert len(primes) == 1, f"Location {loc.value} should have 1 Prime"

    def test_clear_registry(self):
        registry = PillarRegistry()
        registry.seed_all_locations()
        assert registry.total_entities == 72
        registry.clear()
        assert registry.total_entities == 0


# ──────────────────────────────────────────────
# Singleton Tests
# ──────────────────────────────────────────────


class TestPillarRegistrySingleton:
    def test_get_registry(self):
        registry = get_pillar_registry()
        assert registry is not None
        assert isinstance(registry, PillarRegistry)
