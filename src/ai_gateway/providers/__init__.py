"""
AI Gateway Providers — Base class and implementations
=======================================================
Zero-cost providers prioritised: Ollama (local) → OpenRouter (free) → Offline (deterministic)
"""

from src.ai_gateway.providers.base import AIProvider
from src.ai_gateway.providers.ollama import OllamaProvider
from src.ai_gateway.providers.openrouter import OpenRouterProvider
from src.ai_gateway.providers.offline import OfflineProvider
from src.ai_gateway.providers.huggingface import HuggingFaceProvider

__all__ = [
    "AIProvider",
    "OllamaProvider",
    "OpenRouterProvider",
    "OfflineProvider",
    "HuggingFaceProvider",
]
