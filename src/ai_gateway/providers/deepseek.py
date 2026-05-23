# src/ai_gateway/providers/deepseek.py — DeepSeek AI Provider
# DeepSeek API — extremely cheap inference with reasoning models.
#
# Cost: $0.14/M input tokens (deepseek-chat), $0.55/M (deepseek-reasoner)
# Free alternative: Use deepseek/deepseek-r1:free via OpenRouter instead
# Models: deepseek-chat, deepseek-reasoner
#
# Requires: DEEPSEEK_API_KEY environment variable

from __future__ import annotations

import logging
import os
import time
from typing import Dict, List, Optional

from src.ai_gateway.providers.base import AIProvider
from src.ai_gateway.types import AIRequest, AIResponse, ProviderHealth

logger = logging.getLogger("tranc3.ai_gateway.deepseek")

DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_MODELS = [
    "deepseek-chat",          # $0.14/M input, $0.28/M output
    "deepseek-reasoner",      # $0.55/M input, $2.19/M output (R1 reasoning)
]


class DeepSeekProvider(AIProvider):
    """DeepSeek AI provider with ultra-cheap inference.

    DeepSeek offers some of the cheapest API pricing in the industry,
    making it the best "near-zero-cost" option for high-volume usage.
    The deepseek-chat model costs just $0.14/M input tokens, while
    the deepseek-reasoner (R1) provides advanced reasoning at $0.55/M.

    For truly zero-cost usage, use the OpenRouter provider with the
    deepseek/deepseek-r1:free model instead.

    Note: This provider uses the OpenAI-compatible API format.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = DEEPSEEK_BASE_URL,
        default_model: str = "deepseek-chat",
    ) -> None:
        super().__init__(
            name="deepseek",
            base_url=base_url,
            api_key=api_key or os.getenv("DEEPSEEK_API_KEY", ""),
        )
        self._default_model = default_model
        self._client = None

    def _get_client(self):
        """Lazy-initialize the OpenAI-compatible client."""
        if self._client is not None:
            return self._client

        if not self.api_key:
            raise RuntimeError(
                "DEEPSEEK_API_KEY is required. Get one at https://platform.deepseek.com/ "
                "For zero-cost, use OpenRouter with deepseek/deepseek-r1:free instead."
            )

        try:
            from openai import OpenAI
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )
        except ImportError:
            logger.info("openai package not installed, using httpx fallback")
            self._client = _DeepSeekHttpxClient(self.api_key, self.base_url)

        return self._client

    async def complete(self, request: AIRequest) -> AIResponse:
        """Generate a completion using DeepSeek's API."""
        import asyncio

        model = request.model or self._default_model
        start = time.monotonic()

        client = self._get_client()

        # Build messages
        messages = []
        if request.messages:
            messages = request.messages
        else:
            messages = [{"role": "user", "content": request.prompt}]

        try:
            if hasattr(client, 'chat'):
                # OpenAI SDK
                response = await asyncio.to_thread(
                    client.chat.completions.create,
                    model=model,
                    messages=messages,
                    max_tokens=request.max_tokens,
                    temperature=request.temperature,
                )
                choice = response.choices[0]
                usage = response.usage

                return AIResponse(
                    text=choice.message.content or "",
                    model=model,
                    provider="deepseek",
                    tokens_prompt=usage.prompt_tokens if usage else 0,
                    tokens_completion=usage.completion_tokens if usage else 0,
                    tokens_total=usage.total_tokens if usage else 0,
                    latency_ms=(time.monotonic() - start) * 1000,
                    finish_reason=choice.finish_reason,
                    metadata={"cost_tier": "near_zero"},
                )
            else:
                return await client.complete(
                    model=model,
                    messages=messages,
                    max_tokens=request.max_tokens,
                    temperature=request.temperature,
                    start_time=start,
                )

        except Exception as e:
            logger.error("DeepSeek completion failed: %s", str(e))
            raise

    async def health_check(self) -> ProviderHealth:
        """Check DeepSeek API health."""
        if not self.api_key:
            return ProviderHealth(
                provider="deepseek",
                healthy=False,
                error="DEEPSEEK_API_KEY not configured",
            )

        try:
            return ProviderHealth(
                provider="deepseek",
                healthy=True,
                models_available=DEEPSEEK_MODELS,
            )
        except Exception as e:
            return ProviderHealth(
                provider="deepseek",
                healthy=False,
                error=str(e),
            )

    def get_models(self) -> list[str]:
        """List available DeepSeek models."""
        return DEEPSEEK_MODELS


class _DeepSeekHttpxClient:
    """Fallback DeepSeek client using httpx."""

    def __init__(self, api_key: str, base_url: str):
        self._api_key = api_key
        self._base_url = base_url
        self._httpx = None

    def _get_httpx(self):
        if self._httpx is None:
            try:
                import httpx
                self._httpx = httpx.AsyncClient(
                    base_url=self._base_url,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=60.0,  # DeepSeek reasoner can take longer
                )
            except ImportError:
                raise RuntimeError(
                    "Either 'openai' or 'httpx' package is required. "
                    "Install with: pip install openai  OR  pip install httpx"
                )
        return self._httpx

    async def complete(
        self,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float,
        start_time: float,
    ) -> AIResponse:
        client = self._get_httpx()

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        response = await client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()

        choice = data["choices"][0]
        usage = data.get("usage", {})

        return AIResponse(
            text=choice["message"]["content"],
            model=model,
            provider="deepseek",
            tokens_prompt=usage.get("prompt_tokens", 0),
            tokens_completion=usage.get("completion_tokens", 0),
            tokens_total=usage.get("total_tokens", 0),
            latency_ms=(time.monotonic() - start_time) * 1000,
            finish_reason=choice.get("finish_reason"),
            metadata={"cost_tier": "near_zero"},
        )
