"""
Gemini Provider — Google Generative AI (Free Tier)
====================================================
Google's Gemini models via the OpenAI-compatible endpoint.
Generous free tier: 1,500 req/day, 1M tokens/min.

Supports both chat completions and text embeddings (text-embedding-004).

Free Tier: 1,500 requests/day, 15 req/min (gemini-2.0-flash)
Embedding: 1,500 req/day, text-embedding-004 (768-dim)
Requires: GOOGLE_GEMINI_API_KEY environment variable
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, List, Optional

import httpx

from src.ai_gateway.providers.base import AIProvider
from src.ai_gateway.types import AIRequest, AIResponse, ProviderHealth

logger = logging.getLogger("tranc3.ai_gateway.gemini")

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"

# Chat models available on the free tier
GEMINI_CHAT_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
]

# Embedding models available on the free tier
GEMINI_EMBED_MODELS = [
    "text-embedding-004",
]


class GeminiProvider(AIProvider):
    """
    Google Gemini provider via the OpenAI-compatible REST API.

    Uses the generativelanguage.googleapis.com/v1beta/openai endpoint,
    which is fully OpenAI-compatible (same request/response format).

    Free tier: 1,500 requests/day and 15 requests/minute for
    gemini-2.0-flash, making it ideal as a high-quality cloud fallback.

    Zero-Cost Mandate: Only activates when GOOGLE_GEMINI_API_KEY is set.
    No key = provider is skipped gracefully in the failover chain.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = GEMINI_BASE_URL,
        default_model: str = "gemini-2.0-flash",
        timeout: float = 60.0,
    ) -> None:
        super().__init__(
            name="gemini",
            base_url=base_url,
            api_key=api_key or os.getenv("GOOGLE_GEMINI_API_KEY", ""),
        )
        self._default_model = default_model
        self._timeout = timeout

    def _is_available(self) -> bool:
        """Return True only when an API key is configured."""
        return bool(self.api_key)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def complete(self, request: AIRequest) -> AIResponse:
        """Generate a chat completion using Gemini's OpenAI-compatible API."""
        if not self._is_available():
            raise RuntimeError(
                "GOOGLE_GEMINI_API_KEY is not set. "
                "Get a free key at https://aistudio.google.com/apikey"
            )

        model = request.model or self._default_model
        start = time.monotonic()

        messages: List[dict[str, Any]] = request.messages or [
            {"role": "user", "content": request.prompt}
        ]

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "stream": False,
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=self._headers(),
                )
                response.raise_for_status()
                data = response.json()

            latency_ms = (time.monotonic() - start) * 1000
            choice = data.get("choices", [{}])[0]
            usage = data.get("usage", {})

            return AIResponse(
                text=choice.get("message", {}).get("content", ""),
                model=data.get("model", model),
                provider=self.name,
                tokens_prompt=usage.get("prompt_tokens", 0),
                tokens_completion=usage.get("completion_tokens", 0),
                tokens_total=usage.get("total_tokens", 0),
                latency_ms=latency_ms,
                finish_reason=choice.get("finish_reason"),
                metadata={"cost_tier": "free"},
            )
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 429:
                raise RuntimeError("Gemini rate limit exceeded (1,500 req/day)") from None
            raise RuntimeError(f"Gemini HTTP error: {status}") from None
        except Exception as e:
            raise RuntimeError(f"Gemini error: {e}") from None

    async def embed(self, text: str, model: str = "text-embedding-004") -> List[float]:
        """
        Generate a text embedding using Gemini's text-embedding-004 model.

        Free tier: 1,500 requests/day.
        Output dimension: 768 floats.

        Args:
            text: The text to embed.
            model: Embedding model name (default: text-embedding-004).

        Returns:
            List of floats representing the embedding vector.
        """
        if not self._is_available():
            raise RuntimeError(
                "GOOGLE_GEMINI_API_KEY is not set. "
                "Get a free key at https://aistudio.google.com/apikey"
            )

        payload: dict[str, Any] = {
            "model": model,
            "input": text,
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self.base_url}/embeddings",
                    json=payload,
                    headers=self._headers(),
                )
                response.raise_for_status()
                data = response.json()

            # OpenAI-compatible embedding response format
            embedding: List[float] = data["data"][0]["embedding"]
            return embedding
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 429:
                raise RuntimeError("Gemini embedding rate limit exceeded") from None
            raise RuntimeError(f"Gemini embedding HTTP error: {status}") from None
        except Exception as e:
            raise RuntimeError(f"Gemini embedding error: {e}") from None

    async def health_check(self) -> ProviderHealth:
        """Check Gemini API availability."""
        if not self._is_available():
            return ProviderHealth(
                provider=self.name,
                healthy=False,
                error="GOOGLE_GEMINI_API_KEY not configured",
            )

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                start = time.monotonic()
                response = await client.get(
                    f"{self.base_url}/models",
                    headers=self._headers(),
                )
                latency_ms = (time.monotonic() - start) * 1000

                if response.status_code == 200:
                    data = response.json()
                    models = [m.get("id", "") for m in data.get("data", [])]
                    return ProviderHealth(
                        provider=self.name,
                        healthy=True,
                        latency_ms=latency_ms,
                        models_available=models or GEMINI_CHAT_MODELS + GEMINI_EMBED_MODELS,
                    )
                return ProviderHealth(
                    provider=self.name,
                    healthy=False,
                    latency_ms=latency_ms,
                    error=f"HTTP {response.status_code}",
                )
        except Exception as e:
            return ProviderHealth(
                provider=self.name,
                healthy=False,
                error=str(e),
            )

    def get_models(self) -> list[str]:
        """List available Gemini models."""
        return GEMINI_CHAT_MODELS + GEMINI_EMBED_MODELS
