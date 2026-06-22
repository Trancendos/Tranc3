"""
Trancendos AI Gateway — Router & Failover Engine
==================================================
Ported from @trancendos/ai-gateway (infinity-adminOS, TypeScript)

Per-tenant conditional routing with automatic failover.
Prioritises zero-cost providers across a multi-provider free chain.

Free Inference Chain (priority order — x10 providers):
  1. Ollama        — local, unlimited, zero-cost (no key needed)
  2. Groq          — 14,400 req/day free, 300+ tok/s (GROQ_API_KEY)
  3. Gemini        — 1,500 req/day free, 1M tok/min (GOOGLE_GEMINI_API_KEY)
  4. Cerebras      — 30 RPM, wafer-scale inference (CEREBRAS_API_KEY)
  5. SambaNova     — 50K tokens/req free (SAMBANOVA_API_KEY)
  6. GitHub Models — GPT-4o-mini, Llama 70B — any GitHub PAT (GITHUB_TOKEN)
  7. Mistral       — 500K tokens/month, EU-hosted, GDPR (MISTRAL_API_KEY)
  8. OpenRouter    — 200 req/day, 50+ free models (OPENROUTER_API_KEY)
  9. HuggingFace   — serverless inference free tier (HF_API_TOKEN)
 10. DeepSeek      — free tier (DEEPSEEK_API_KEY)
 11. Offline       — deterministic stub, always available

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
from src.ai_gateway.providers.github_models import GitHubModelsProvider
from src.ai_gateway.providers.mistral_free import MistralFreeProvider
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
    "GitHubModelsProvider",
    "MistralFreeProvider",
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
