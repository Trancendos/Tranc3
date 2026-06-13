"""
AI Gateway Providers — Base class and implementations
=======================================================
Zero-cost providers prioritised:
  Ollama (local) → Groq (free cloud) → Gemini (free cloud)
  → Cerebras (free cloud) → SambaNova (free cloud)
  → OpenRouter (free models) → HuggingFace (free tier)
  → Offline (deterministic stub)

All cloud providers are skipped gracefully when their API key env var
is not set, ensuring the zero-cost mandate is never violated.
"""

from src.ai_gateway.providers.base import AIProvider
from src.ai_gateway.providers.cerebras import CerebrasProvider
from src.ai_gateway.providers.embeddings import (
    EmbeddingRouter,
    GeminiEmbeddingProvider,
    OllamaEmbeddingProvider,
)
from src.ai_gateway.providers.gemini import GeminiProvider
from src.ai_gateway.providers.groq import GroqProvider
from src.ai_gateway.providers.huggingface import HuggingFaceProvider
from src.ai_gateway.providers.offline import OfflineProvider
from src.ai_gateway.providers.ollama import OllamaProvider
from src.ai_gateway.providers.openrouter import OpenRouterProvider
from src.ai_gateway.providers.sambanova import SambanovaProvider

__all__ = [
    "AIProvider",
    # Inference providers
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
]
