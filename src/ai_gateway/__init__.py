"""
Trancendos AI Gateway — Router & Failover Engine
==================================================
Ported from @trancendos/ai-gateway (infinity-adminOS, TypeScript)

Per-tenant conditional routing with automatic failover.
Prioritises zero-cost providers across a multi-provider free chain.

Free Inference Chain (priority order):
  1. Ollama        — local, unlimited, zero-cost (no key needed)
  2. Groq          — 14,400 req/day free, 300+ tok/s (GROQ_API_KEY)
  3. Gemini        — 1,500 req/day free, 1M tok/min (GOOGLE_GEMINI_API_KEY)
  4. Cerebras      — 1M tokens/day free (CEREBRAS_API_KEY)
  5. SambaNova     — free tier, large models (SAMBANOVA_API_KEY)
  6. OpenRouter    — 20+ free models (OPENROUTER_API_KEY)
  7. HuggingFace   — serverless inference free tier (HF_API_TOKEN)
  8. Offline       — deterministic stub, always available

Free Embedding Chain (priority order):
  1. Ollama local  — nomic-embed-text, zero-cost (no key needed)
  2. Gemini API    — text-embedding-004, 1,500 req/day (GOOGLE_GEMINI_API_KEY)

Features:
- Priority-based provider chain (failover)
- Condition-based routing (plan, tags, time)
- Token budget enforcement
- Response caching (in-memory LRU)
- Latency-based failover
- Per-provider health tracking
- Graceful skip of unconfigured providers (no key = no error)

Usage:
    from src.ai_gateway import AIGateway, AIProvider

    gateway = AIGateway()
    gateway.register_provider(OllamaProvider())
    gateway.register_provider(GroqProvider())   # auto-reads GROQ_API_KEY
    response = await gateway.route(AIRequest(prompt="Hello"), tenant_config)

    # Embeddings
    from src.ai_gateway import EmbeddingRouter
    router = EmbeddingRouter()
    vector = await router.embed("Hello, world!")
"""

from src.ai_gateway.gateway import AIGateway, AIGatewayConfig
from src.ai_gateway.providers import (
    AIProvider,
    CerebrasProvider,
    EmbeddingRouter,
    GeminiEmbeddingProvider,
    GeminiProvider,
    GroqProvider,
    HuggingFaceProvider,
    OfflineProvider,
    OllamaEmbeddingProvider,
    OllamaProvider,
    OpenRouterProvider,
    SambanovaProvider,
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
    # Gateway
    "AIGateway",
    "AIGatewayConfig",
    # Base
    "AIProvider",
    # Inference providers (priority order)
    "OllamaProvider",
    "GroqProvider",
    "GeminiProvider",
    "CerebrasProvider",
    "SambanovaProvider",
    "OpenRouterProvider",
    "HuggingFaceProvider",
    "OfflineProvider",
    # Embedding providers
    "EmbeddingRouter",
    "OllamaEmbeddingProvider",
    "GeminiEmbeddingProvider",
    # Types
    "AIRequest",
    "AIResponse",
    "GatewayMetrics",
    "ProviderHealth",
    "ProviderName",
    "RouteRule",
    "TenantAIConfig",
]
