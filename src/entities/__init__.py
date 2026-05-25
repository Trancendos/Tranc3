"""
Trancendos Platform Entity Registry
"""

from .platform import (
    LOCATION_ABBREVS,
    PILLAR_ABBREVS,
    PLATFORM_ENTITIES,
    PRIME_ABBREVS,
    WORKER_ENTITY_MAP,
    Agent,
    Bot,
    LocationEntity,
    Pillar,
    get_all_ids,
    get_entity_by_aid,
    get_entity_by_pid,
    get_entity_for_location,
    get_entity_for_port,
)

from .lifecycle import (
    LifecycleEmitter,
    LifecycleEvent,
    LifecycleContext,
    LifecycleListener,
)

from .ollama import (
    OllamaClient,
    OllamaConfig,
    OllamaMessage,
    OllamaToolCall,
    OllamaToolSchema,
    OllamaChatResponse,
)

from .tiers import (
    Prime,
    Sovereign,
    HILAApproval,
    HealthReport,
)

__all__ = [
    # Platform entities
    "Agent",
    "Bot",
    "LOCATION_ABBREVS",
    "PILLAR_ABBREVS",
    "PRIME_ABBREVS",
    "LocationEntity",
    "Pillar",
    "PLATFORM_ENTITIES",
    "WORKER_ENTITY_MAP",
    "get_all_ids",
    "get_entity_by_aid",
    "get_entity_by_pid",
    "get_entity_for_location",
    "get_entity_for_port",
    # Lifecycle
    "LifecycleEmitter",
    "LifecycleEvent",
    "LifecycleContext",
    "LifecycleListener",
    # Ollama
    "OllamaClient",
    "OllamaConfig",
    "OllamaMessage",
    "OllamaToolCall",
    "OllamaToolSchema",
    "OllamaChatResponse",
    # Tier 1 & 2
    "Prime",
    "Sovereign",
    "HILAApproval",
    "HealthReport",
]
