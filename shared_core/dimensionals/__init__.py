"""
Trancendos Dimensional Services — The Dimensional's
=====================================================
The Dimensional's package provides the service registry and communication
infrastructure for the Infinity Ecosystem. In the Trancendos Universe,
"Dimensional's" refers to the shared-core services that form the backbone
of the platform — each dimensional service represents a fundamental
capability domain that operates across the entire ecosystem.

Architecture:
    Dimensional's → Service Bus → Underverse → Per-App Nanoservices

Components:
    - DimensionalServiceRegistry: Registry of all dimensional services
      with pillar associations, tier requirements, and health tracking
    - DimensionalServiceBus: Communication bus that routes messages
      between dimensional services, with Sentinel Station integration
    - Underverse: Per-app nanoservice registry that organizes
      domain-specific microservices under their parent dimensional

Naming Convention:
    "Shared-Core" = "Dimensional's" in the Trancendos Universe
    Each dimensional service is governed by a Prime and associated
    with a Pillar of the Infinity Ecosystem.

Usage:
    from shared_core.dimensionals import DimensionalServiceRegistry, get_dimensional_registry

    registry = get_dimensional_registry()
    registry.register(DimensionalService(
        id="gateway",
        name="Gateway Dimensional",
        pillar=Pillar.ARCHITECTURAL,
        tier=Tier.PRIME,
        ...
    ))
"""

from shared_core.dimensionals.registry import (  # codeql[py/cyclic-import]
    DimensionalService,
    DimensionalServiceRegistry,
    DimensionalServiceStatus,
    get_dimensional_registry,
)
from shared_core.dimensionals.service_bus import (  # codeql[py/cyclic-import]
    DimensionalServiceBus,
    get_dimensional_bus,
)
from shared_core.dimensionals.underverse import (  # codeql[py/cyclic-import]
    UnderverseModule,
    UnderverseRegistry,
    get_underverse_registry,
)

__all__ = [
    # Registry
    "DimensionalService",
    "DimensionalServiceRegistry",
    "DimensionalServiceStatus",
    "get_dimensional_registry",
    # Service Bus
    "DimensionalServiceBus",
    "get_dimensional_bus",
    # Underverse
    "UnderverseModule",
    "UnderverseRegistry",
    "get_underverse_registry",
]
