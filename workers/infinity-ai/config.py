"""
Configuration for infinity-ai worker (port 8009).
All env-var constants and provider thresholds live here.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Worker identity
# ---------------------------------------------------------------------------
WORKER_PORT: int = int(os.environ.get("PORT", 8009))
WORKER_NAME: str = "infinity-ai"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DB_PATH: Path = Path(__file__).parent / "data" / "ai_gateway.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Provider base URLs
# ---------------------------------------------------------------------------
OLLAMA_BASE_URL: str = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OPENROUTER_BASE_URL: str = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
HUGGINGFACE_BASE_URL: str = os.environ.get(
    "HUGGINGFACE_BASE_URL", "https://api-inference.huggingface.co"
)
GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
CEREBRAS_BASE_URL: str = "https://api.cerebras.ai/v1"
TOGETHER_BASE_URL: str = "https://api.together.xyz/v1"
DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"

# ---------------------------------------------------------------------------
# Provider API keys (read from environment)
# ---------------------------------------------------------------------------
GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "")
CEREBRAS_API_KEY: str = os.environ.get("CEREBRAS_API_KEY", "")
OPENROUTER_API_KEY: str = os.environ.get("OPENROUTER_API_KEY", "")
HUGGINGFACE_API_KEY: str = os.environ.get("HUGGINGFACE_API_KEY", "")
TOGETHER_API_KEY: str = os.environ.get("TOGETHER_API_KEY", "")
DEEPSEEK_API_KEY: str = os.environ.get("DEEPSEEK_API_KEY", "")

# ---------------------------------------------------------------------------
# Provider free-tier daily limits (requests)
# ---------------------------------------------------------------------------
PROVIDER_DAILY_LIMITS: dict[str, int] = {
    "ollama": -1,  # unlimited (local)
    "groq": 14_400,  # free tier
    "cerebras": 1_000,  # free tier
    "openrouter": 200,  # free tier (varies by model)
    "huggingface": 1_000,  # free tier inference API
    "together": 500,  # credit-based approximation
    "deepseek": 1_000,  # generous free tier
    "offline": -1,  # always available
}

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
LRU_CACHE_MAX_SIZE: int = int(os.environ.get("LRU_CACHE_MAX_SIZE", 500))
SMART_CACHE_CAPACITY: int = int(os.environ.get("SMART_CACHE_CAPACITY", 2000))
SMART_CACHE_TTL_S: float = float(os.environ.get("SMART_CACHE_TTL_S", 3600.0))

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
INTERNAL_SECRET: str = os.environ.get("INTERNAL_SECRET", "")

# ---------------------------------------------------------------------------
# Token budget defaults
# ---------------------------------------------------------------------------
DEFAULT_DAILY_TOKEN_LIMIT: int = int(os.environ.get("DEFAULT_DAILY_TOKEN_LIMIT", 100_000))
