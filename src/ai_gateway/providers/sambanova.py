"""
SambaNova Provider — High-Performance AI Inference (Free Tier)
===============================================================
SambaNova's Reconfigurable Dataflow Unit (RDU) delivers high-throughput,
low-latency inference on large models. Free tier available.

Requires: SAMBANOVA_API_KEY environment variable
Free keys: https://cloud.sambanova.ai/

Model: Meta-Llama-3.3-70B-Instruct (default), Meta-Llama-3.2-3B-Instruct
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, List, Optional

import httpx

from src.ai_gateway.providers.base import AIProvider
from src.ai_gateway.types import AIRequest, AIResponse, ProviderHealth

logger = logging.getLogger("tranc3.ai_gateway.sambanova")

SAMBANOVA_BASE_URL = "https://api.sambanova.ai/v1"

SAMBANOVA_MODELS = [
    "Meta-Llama-3.3-70B-Instruct",
    "Meta-Llama-3.1-405B-Instruct",
    "Meta-Llama-3.2-3B-Instruct",
    "Meta-Llama-3.2-1B-Instruct",
    "Qwen2.5-72B-Instruct",
    "DeepSeek-R1",
]


class SambanovaProvider(AIProvider):
    """
    SambaNova AI provider — RDU-accelerated inference with a free tier.

    SambaNova's Reconfigurable Dataflow Units (RDUs) are purpose-built
    for AI workloads, delivering competitive throughput on large models.
    The free tier provides access to models up to 405B parameters.

    The OpenAI-compatible API ensures seamless integration.

    Zero-Cost Mandate: Only activates when SAMBANOVA_API_KEY is set.
    No key = provider is skipped gracefully in the failover chain.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = SAMBANOVA_BASE_URL,
        default_model: str = "Meta-Llama-3.3-70B-Instruct",
        timeout: float = 90.0,
    ) -> None:
        super().__init__(
            name="sambanova",
            base_url=base_url,
            api_key=api_key or os.getenv("SAMBANOVA_API_KEY", ""),
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
        """Generate a chat completion using SambaNova's OpenAI-compatible API."""
        if not self._is_available():
            raise RuntimeError(
                "SAMBANOVA_API_KEY is not set. Get a free key at https://cloud.sambanova.ai/"
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
                raise RuntimeError("SambaNova rate limit exceeded") from None
            raise RuntimeError(f"SambaNova HTTP error: {status}") from None
        except Exception as e:
            raise RuntimeError(f"SambaNova error: {e}") from None

    async def health_check(self) -> ProviderHealth:
        """Check SambaNova API availability."""
        if not self._is_available():
            return ProviderHealth(
                provider=self.name,
                healthy=False,
                error="SAMBANOVA_API_KEY not configured",
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
                        models_available=models or SAMBANOVA_MODELS,
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
        """List available SambaNova models."""
        return SAMBANOVA_MODELS
