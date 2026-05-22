"""
AI Gateway Providers — Base class and implementations
=======================================================
Zero-cost providers prioritised: Ollama (local) → Groq (free) → OpenRouter (free) → Offline (deterministic)
"""

from src.ai_gateway.providers.base import AIProvider
from src.ai_gateway.providers.deepseek import DeepSeekProvider
from src.ai_gateway.providers.groq import GroqProvider
from src.ai_gateway.providers.huggingface import HuggingFaceProvider
from src.ai_gateway.providers.offline import OfflineProvider
from src.ai_gateway.providers.ollama import OllamaProvider
from src.ai_gateway.providers.openrouter import OpenRouterProvider

__all__ = [
    "AIProvider",
    "DeepSeekProvider",
    "GroqProvider",
    "HuggingFaceProvider",
    "OfflineProvider",
    "OllamaProvider",
    "OpenRouterProvider",
]
