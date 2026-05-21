"""
Trancendos AI Gateway — Router & Failover Engine
==================================================
Ported from @trancendos/ai-gateway (infinity-adminOS, TypeScript)

Per-tenant conditional routing with automatic failover.
Prioritises zero-cost providers (Ollama → OpenRouter free → offline).

Features:
- Priority-based provider chain (failover)
- Condition-based routing (plan, tags, time)
- Token budget enforcement
- Response caching (in-memory)
- Latency-based failover
- Per-provider health tracking

Usage:
    from src.ai_gateway import AIGateway, AIProvider

    gateway = AIGateway()
    gateway.register_provider(OllamaProvider())
    response = await gateway.route(AIRequest(prompt="Hello"), tenant_config)
"""

from src.ai_gateway.gateway import AIGateway, AIGatewayConfig
from src.ai_gateway.providers import (
    AIProvider,
    OllamaProvider,
    OpenRouterProvider,
    OfflineProvider,
    HuggingFaceProvider,
)
from src.ai_gateway.types import (
    AIRequest,
    AIResponse,
    GatewayMetrics,
    ProviderHealth,
    ProviderName,
    RouteRule,
    TenantAIConfig,
)

__all__ = [
    "AIGateway",
    "AIGatewayConfig",
    "AIProvider",
    "OllamaProvider",
    "OpenRouterProvider",
    "OfflineProvider",
    "HuggingFaceProvider",
    "AIRequest",
    "AIResponse",
    "GatewayMetrics",
    "ProviderHealth",
    "ProviderName",
    "RouteRule",
    "TenantAIConfig",
]
