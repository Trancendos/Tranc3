"""
AI Gateway Providers — Base class and implementations
=======================================================
Zero-cost providers prioritised:
  Ollama (local) → Groq (free cloud) → Gemini (free cloud)
  → GitHub Models (free — GPT-4o-mini, Llama 3.1 70B, DeepSeek-R1)
  → Cerebras (free cloud) → SambaNova (free cloud)
  → OpenRouter (free models) → HuggingFace (free tier)
  → DeepSeek (free tier)
  → Offline (deterministic stub)

All cloud providers are skipped gracefully when their API key env var
is not set, ensuring the zero-cost mandate is never violated.

GitHub Models requires only a GitHub PAT (github.com/settings/tokens).
No credit card, no payment method, no special scopes needed.
"""

from src.ai_gateway.providers.base import AIProvider
from src.ai_gateway.providers.cerebras import CerebrasProvider
from src.ai_gateway.providers.deepseek import DeepSeekProvider
from src.ai_gateway.providers.embeddings import (
    EmbeddingRouter,
    GeminiEmbeddingProvider,
    OllamaEmbeddingProvider,
)
from src.ai_gateway.providers.gemini import GeminiProvider
from src.ai_gateway.providers.github_models import GitHubModelsProvider
from src.ai_gateway.providers.groq import GroqProvider
from src.ai_gateway.providers.huggingface import HuggingFaceProvider
from src.ai_gateway.providers.offline import OfflineProvider
from src.ai_gateway.providers.ollama import OllamaProvider
from src.ai_gateway.providers.openrouter import OpenRouterProvider
from src.ai_gateway.providers.sambanova import SambanovaProvider

__all__ = [
    "AIProvider",
    # Inference providers (priority order — all zero cost)
    "OllamaProvider",
    "GroqProvider",
    "GeminiProvider",
    "GitHubModelsProvider",
    "CerebrasProvider",
    "SambanovaProvider",
    "OpenRouterProvider",
    "HuggingFaceProvider",
    "DeepSeekProvider",
    "OfflineProvider",
    # Embedding providers
    "EmbeddingRouter",
    "OllamaEmbeddingProvider",
    "GeminiEmbeddingProvider",
]
