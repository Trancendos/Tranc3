"""
Tranc3 Pillar Entities
========================
Pillar entity architecture for the 9 platform locations.

Each location has:
    - Lead AI (Tier 3) — Oversees all operations at the location
    - Prime (Tier 2) — Coordinates between the Lead AI and agents
    - Agent Alpha (Tier 4) — Primary agent for the location
    - Agent Beta (Tier 4) — Secondary agent for the location
    - Bot-01 through Bot-04 (Tier 5) — Bot workers for the location

The 9 Platform Locations:
    1. Infinity One (User Portal)
    2. The Nexus (AI/Agent Hub)
    3. The HIVE (Data Fabric)
    4. Sentinel Station (Security)
    5. Vault (Secrets & Storage)
    6. Citadel (DevOps)
    7. Library (Knowledge)
    8. Studio (Creative)
    9. Observatory (Analytics)
"""

from Dimensional.pillars.entities import (  # noqa: I001
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

__all__ = [
    "EntityTier",
    "EntityType",
    "PillarEntity",
    "PillarLocation",
    "PillarLocationConfig",
    "PillarRegistry",
    "get_pillar_registry",
    "LOCATION_CONFIGS",
    "LOCATIONS",
]
