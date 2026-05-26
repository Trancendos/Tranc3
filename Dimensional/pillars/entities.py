"""
Tranc3 Pillar Entity Architecture
===================================
Entity hierarchy for the 9 platform locations with tier-based organization.

Tier System:
    - Tier 0: HUMAN (external operators)
    - Tier 1: ORCHESTRATOR (system-wide coordination)
    - Tier 2: PRIME (location coordination)
    - Tier 3: AI (location intelligence lead)
    - Tier 4: AGENT (operational agents)
    - Tier 5: BOT (worker bots)
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────


class EntityTier(int, Enum):
    """Entity tier levels."""

    HUMAN = 0
    ORCHESTRATOR = 1
    PRIME = 2
    AI = 3
    AGENT = 4
    BOT = 5


class EntityType(str, Enum):
    """Entity type classification."""

    HUMAN = "human"
    ORCHESTRATOR = "orchestrator"
    PRIME = "prime"
    AI = "ai"
    AGENT = "agent"
    BOT = "bot"


class PillarLocation(str, Enum):
    """The 9 platform locations."""

    INFINITY_ONE = "infinity_one"
    NEXUS = "nexus"
    HIVE = "hive"
    SENTINEL_STATION = "sentinel_station"
    VAULT = "vault"
    CITADEL = "citadel"
    LIBRARY = "library"
    STUDIO = "studio"
    OBSERVATORY = "observatory"


# ──────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────


class PillarEntity(BaseModel):
    """A pillar entity with tier, type, and location assignment."""

    entity_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    name: str
    entity_type: EntityType
    tier: EntityTier
    location: PillarLocation
    parent_id: Optional[str] = None
    children_ids: List[str] = Field(default_factory=list)
    status: str = "active"
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def add_child(self, child_id: str) -> None:
        """Add a child entity reference."""
        if child_id not in self.children_ids:
            self.children_ids.append(child_id)

    def remove_child(self, child_id: str) -> None:
        """Remove a child entity reference."""
        if child_id in self.children_ids:
            self.children_ids.remove(child_id)


class PillarLocationConfig(BaseModel):
    """Configuration for a pillar location."""

    location: PillarLocation
    display_name: str
    description: str = ""
    bridge_port: int = 0
    max_entities: int = 100
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ──────────────────────────────────────────────
# Location Definitions
# ──────────────────────────────────────────────

LOCATION_CONFIGS: Dict[PillarLocation, PillarLocationConfig] = {
    PillarLocation.INFINITY_ONE: PillarLocationConfig(
        location=PillarLocation.INFINITY_ONE,
        display_name="Infinity One",
        description="User Portal — primary entry point for all users",
        bridge_port=8070,
    ),
    PillarLocation.NEXUS: PillarLocationConfig(
        location=PillarLocation.NEXUS,
        display_name="The Nexus",
        description="AI/Agent Hub — central coordination for AI agents and bots",
        bridge_port=8050,
    ),
    PillarLocation.HIVE: PillarLocationConfig(
        location=PillarLocation.HIVE,
        display_name="The HIVE",
        description="Data Fabric — data movement, transformation, and storage",
        bridge_port=8060,
    ),
    PillarLocation.SENTINEL_STATION: PillarLocationConfig(
        location=PillarLocation.SENTINEL_STATION,
        display_name="Sentinel Station",
        description="Security — threat detection, defense, and compliance",
        bridge_port=8080,
    ),
    PillarLocation.VAULT: PillarLocationConfig(
        location=PillarLocation.VAULT,
        display_name="Vault",
        description="Secrets & Storage — encrypted storage and key management",
        bridge_port=8090,
    ),
    PillarLocation.CITADEL: PillarLocationConfig(
        location=PillarLocation.CITADEL,
        display_name="Citadel",
        description="DevOps — deployment, CI/CD, and infrastructure management",
        bridge_port=8100,
    ),
    PillarLocation.LIBRARY: PillarLocationConfig(
        location=PillarLocation.LIBRARY,
        display_name="Library",
        description="Knowledge — knowledge base, documentation, and learning",
        bridge_port=8110,
    ),
    PillarLocation.STUDIO: PillarLocationConfig(
        location=PillarLocation.STUDIO,
        display_name="Studio",
        description="Creative — content creation, design, and multimedia",
        bridge_port=8120,
    ),
    PillarLocation.OBSERVATORY: PillarLocationConfig(
        location=PillarLocation.OBSERVATORY,
        display_name="Observatory",
        description="Analytics — metrics, monitoring, and business intelligence",
        bridge_port=8130,
    ),
}

LOCATIONS: List[PillarLocation] = list(PillarLocation)


# ──────────────────────────────────────────────
# Pillar Registry
# ──────────────────────────────────────────────


class PillarRegistry:
    """Registry for pillar entities across all locations."""

    def __init__(self) -> None:
        self._entities: Dict[str, PillarEntity] = {}
        self._by_location: Dict[PillarLocation, List[str]] = {loc: [] for loc in PillarLocation}
        self._by_tier: Dict[EntityTier, List[str]] = {tier: [] for tier in EntityTier}
        self._by_type: Dict[EntityType, List[str]] = {et: [] for et in EntityType}

    def register(self, entity: PillarEntity) -> PillarEntity:
        """Register a pillar entity."""
        self._entities[entity.entity_id] = entity
        self._by_location[entity.location].append(entity.entity_id)
        self._by_tier[entity.tier].append(entity.entity_id)
        self._by_type[entity.entity_type].append(entity.entity_id)
        return entity

    def unregister(self, entity_id: str) -> Optional[PillarEntity]:
        """Unregister a pillar entity."""
        entity = self._entities.pop(entity_id, None)
        if entity:
            if entity_id in self._by_location[entity.location]:
                self._by_location[entity.location].remove(entity_id)
            if entity_id in self._by_tier[entity.tier]:
                self._by_tier[entity.tier].remove(entity_id)
            if entity_id in self._by_type[entity.entity_type]:
                self._by_type[entity.entity_type].remove(entity_id)
        return entity

    def get(self, entity_id: str) -> Optional[PillarEntity]:
        """Get an entity by ID."""
        return self._entities.get(entity_id)

    def get_by_location(self, location: PillarLocation) -> List[PillarEntity]:
        """Get all entities at a location."""
        return [self._entities[eid] for eid in self._by_location[location] if eid in self._entities]

    def get_by_tier(self, tier: EntityTier) -> List[PillarEntity]:
        """Get all entities at a tier."""
        return [self._entities[eid] for eid in self._by_tier[tier] if eid in self._entities]

    def get_by_type(self, entity_type: EntityType) -> List[PillarEntity]:
        """Get all entities of a type."""
        return [self._entities[eid] for eid in self._by_type[entity_type] if eid in self._entities]

    def get_children(self, entity_id: str) -> List[PillarEntity]:
        """Get children of an entity."""
        entity = self._entities.get(entity_id)
        if not entity:
            return []
        return [self._entities[cid] for cid in entity.children_ids if cid in self._entities]

    def get_parent(self, entity_id: str) -> Optional[PillarEntity]:
        """Get parent of an entity."""
        entity = self._entities.get(entity_id)
        if not entity or not entity.parent_id:
            return None
        return self._entities.get(entity.parent_id)

    @property
    def total_entities(self) -> int:
        """Total number of registered entities."""
        return len(self._entities)

    @property
    def location_count(self) -> int:
        """Number of active locations."""
        return len([loc for loc, eids in self._by_location.items() if eids])

    def get_location_summary(self, location: PillarLocation) -> Dict[str, Any]:
        """Get a summary of entities at a location."""
        entities = self.get_by_location(location)
        config = LOCATION_CONFIGS.get(location)
        return {
            "location": location.value,
            "display_name": config.display_name if config else location.value,
            "entity_count": len(entities),
            "entities": {
                tier.name: len([e for e in entities if e.tier == tier]) for tier in EntityTier
            },
        }

    def get_full_summary(self) -> Dict[str, Any]:
        """Get a full summary of the registry."""
        return {
            "total_entities": self.total_entities,
            "active_locations": self.location_count,
            "locations": {loc.value: self.get_location_summary(loc) for loc in PillarLocation},
            "by_tier": {
                tier.name: len([eid for eid in self._by_tier[tier] if eid in self._entities])
                for tier in EntityTier
            },
        }

    def seed_location(self, location: PillarLocation) -> List[PillarEntity]:
        """Seed a location with its standard entity hierarchy.

        Each location gets:
        - 1 Lead AI (Tier 3)
        - 1 Prime (Tier 2)
        - 2 Agents (Tier 4) — Alpha and Beta
        - 4 Bots (Tier 5) — Bot-01 through Bot-04
        """
        config = LOCATION_CONFIGS.get(location)
        location_name = config.display_name if config else location.value
        entities: List[PillarEntity] = []

        # Prime (Tier 2) — coordinates the location
        prime = PillarEntity(
            name=f"{location_name} Prime",
            entity_type=EntityType.PRIME,
            tier=EntityTier.PRIME,
            location=location,
        )
        self.register(prime)
        entities.append(prime)

        # Lead AI (Tier 3) — reports to Prime
        lead_ai = PillarEntity(
            name=f"{location_name} Lead AI",
            entity_type=EntityType.AI,
            tier=EntityTier.AI,
            location=location,
            parent_id=prime.entity_id,
        )
        self.register(lead_ai)
        prime.add_child(lead_ai.entity_id)
        entities.append(lead_ai)

        # Agent Alpha (Tier 4) — reports to Lead AI
        agent_alpha = PillarEntity(
            name=f"{location_name} Agent Alpha",
            entity_type=EntityType.AGENT,
            tier=EntityTier.AGENT,
            location=location,
            parent_id=lead_ai.entity_id,
        )
        self.register(agent_alpha)
        lead_ai.add_child(agent_alpha.entity_id)
        entities.append(agent_alpha)

        # Agent Beta (Tier 4) — reports to Lead AI
        agent_beta = PillarEntity(
            name=f"{location_name} Agent Beta",
            entity_type=EntityType.AGENT,
            tier=EntityTier.AGENT,
            location=location,
            parent_id=lead_ai.entity_id,
        )
        self.register(agent_beta)
        lead_ai.add_child(agent_beta.entity_id)
        entities.append(agent_beta)

        # Bots (Tier 5) — report to Agent Alpha
        for i in range(1, 5):
            bot = PillarEntity(
                name=f"{location_name} Bot-{i:02d}",
                entity_type=EntityType.BOT,
                tier=EntityTier.BOT,
                location=location,
                parent_id=agent_alpha.entity_id,
            )
            self.register(bot)
            agent_alpha.add_child(bot.entity_id)
            entities.append(bot)

        return entities

    def seed_all_locations(self) -> Dict[PillarLocation, List[PillarEntity]]:
        """Seed all 9 platform locations with their entity hierarchies."""
        result: Dict[PillarLocation, List[PillarEntity]] = {}
        for location in PillarLocation:
            result[location] = self.seed_location(location)
        return result

    def clear(self) -> None:
        """Clear all registered entities."""
        self._entities.clear()
        self._by_location = {loc: [] for loc in PillarLocation}
        self._by_tier = {tier: [] for tier in EntityTier}
        self._by_type = {et: [] for et in EntityType}


# ──────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────

_registry: Optional[PillarRegistry] = None


def get_pillar_registry() -> PillarRegistry:
    """Get or create the global PillarRegistry instance."""
    global _registry
    if _registry is None:
        _registry = PillarRegistry()
    return _registry
