"""
OpenRouter Provider — Free Cloud AI Fallback
===============================================
Second priority in the AI gateway failover chain.
OpenRouter offers free models with rate limits.

Requires: OPENROUTER_API_KEY (free tier available)
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from src.ai_gateway.providers.base import AIProvider
from src.ai_gateway.types import AIRequest, AIResponse, ProviderHealth

logger = logging.getLogger("tranc3.ai_gateway.openrouter")

# Free models available on OpenRouter
FREE_MODELS = [
    "meta-llama/llama-3.2-3b-instruct:free",
    "qwen/qwen-2.5-72b-instruct:free",
    "mistralai/mistral-7b-instruct:free",
    "google/gemma-2-9b-it:free",
]


class OpenRouterProvider(AIProvider):
    """
    OpenRouter provider — free cloud AI inference.

    Offers free-tier models with rate limits.
    Second in the failover chain after Ollama.
    """

    def __init__(
        self,
        api_key: str = "",
        default_model: str = "meta-llama/llama-3.2-3b-instruct:free",
        base_url: str = "https://openrouter.ai/api/v1",
    ) -> None:
        super().__init__(name="openrouter", base_url=base_url, api_key=api_key)
        self.default_model = default_model

    async def complete(self, request: AIRequest) -> AIResponse:
        """Generate a completion using OpenRouter."""
        start = time.monotonic()
        model = request.model or self.default_model

        # Build OpenAI-compatible request
        messages = request.messages or [{"role": "user", "content": request.prompt}]

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "stream": False,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://trancendos.com",
            "X-Title": "Tranc3 AI Gateway",
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
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
            )
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"OpenRouter HTTP error: {e.response.status_code}") from None
        except Exception as e:
            raise RuntimeError(f"OpenRouter error: {e}") from None
        return None

    async def health_check(self) -> ProviderHealth:
        """Check OpenRouter availability."""
        if not self.api_key:
            return ProviderHealth(
                provider=self.name,
                healthy=False,
                error="No API key configured",
            )
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                start = time.monotonic()
                response = await client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                latency_ms = (time.monotonic() - start) * 1000

                if response.status_code == 200:
                    models = [m.get("id", "") for m in response.json().get("data", [])]
                    free = [m for m in models if ":free" in m]
                    return ProviderHealth(
                        provider=self.name,
                        healthy=True,
                        latency_ms=latency_ms,
                        models_available=free or FREE_MODELS,
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
        return None

    def get_models(self) -> list[str]:
        """List free models available on OpenRouter."""
        return FREE_MODELS
