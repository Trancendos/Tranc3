"""
Trancendos Platform Entity Registry
"""

from .lifecycle import (
    LifecycleContext,
    LifecycleEmitter,
    LifecycleEvent,
    LifecycleListener,
)
from .ollama import (
    OllamaChatResponse,
    OllamaClient,
    OllamaConfig,
    OllamaMessage,
    OllamaToolCall,
    OllamaToolSchema,
)
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
from .templates import (
    InfinityAgent,
    InfinityBot,
    T2ance,
    Tranc3,
    TrancOne,
)
from .tiers import (
    HealthReport,
    HILAApproval,
    Prime,
    Sovereign,
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
    # AI tier base templates
    "InfinityAgent",
    "InfinityBot",
    "T2ance",
    "Tranc3",
    "TrancOne",
]
