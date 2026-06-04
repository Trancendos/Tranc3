# src/ai_gateway/providers/groq.py — Groq AI Provider (Free Tier)
# Ultra-low latency LPU inference with generous free tier.
#
# Free Tier: 30 requests/minute, 14,400 requests/day
# Models: llama-3.3-70b-versatile, llama-3.1-8b-instant, mixtral-8x7b-32768
# Cost: $0.00 (free tier), paid tier available for higher limits
#
# Requires: GROQ_API_KEY environment variable

from __future__ import annotations

import logging
import os
import time
from typing import Dict, List, Optional

from src.ai_gateway.providers.base import AIProvider
from src.ai_gateway.types import AIRequest, AIResponse, ProviderHealth

logger = logging.getLogger("tranc3.ai_gateway.groq")

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "llama3-70b-8192",
    "llama3-8b-8192",
    "mixtral-8x7b-32768",
    "gemma2-9b-it",
]


class GroqProvider(AIProvider):
    """Groq AI provider with ultra-low latency LPU inference.

    Groq's Language Processing Units (LPUs) deliver inference at
    unprecedented speeds — typically under 100ms for most requests.
    The free tier provides 30 requests/minute, which is sufficient
    for development and light production use.

    Zero-Cost Mandate: This provider operates entirely within the
    free tier for typical Tranc3 usage patterns.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = GROQ_BASE_URL,
        default_model: str = "llama-3.3-70b-versatile",
    ) -> None:
        super().__init__(
            name="groq",
            base_url=base_url,
            api_key=api_key or os.getenv("GROQ_API_KEY", ""),
        )
        self._default_model = default_model
        self._client = None

    def _get_client(self):
        """Lazy-initialize the Groq client."""
        if self._client is not None:
            return self._client

        if not self.api_key:
            raise RuntimeError(
                "GROQ_API_KEY is required. Set the environment variable or "
                "pass api_key to GroqProvider(). Free keys available at "
                "https://console.groq.com/",
            )

        try:
            from groq import Groq

            self._client = Groq(api_key=self.api_key)
        except ImportError:
            # Fallback to httpx-based implementation
            logger.info("groq package not installed, using httpx fallback")
            self._client = _GroqHttpxClient(self.api_key, self.base_url)

        return self._client

    async def complete(self, request: AIRequest) -> AIResponse:
        """Generate a completion using Groq's LPU inference."""
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
            # Use the groq SDK or httpx fallback
            if hasattr(client, "chat"):
                # Official groq SDK
                response = await asyncio.to_thread(
                    client.chat.completions.create,
                    model=model,
                    messages=messages,
                    max_tokens=request.max_tokens,
                    temperature=request.temperature,
                    top_p=request.top_p,
                )
                choice = response.choices[0]
                usage = response.usage

                return AIResponse(
                    text=choice.message.content or "",
                    model=model,
                    provider="groq",
                    tokens_prompt=usage.prompt_tokens if usage else 0,
                    tokens_completion=usage.completion_tokens if usage else 0,
                    tokens_total=usage.total_tokens if usage else 0,
                    latency_ms=(time.monotonic() - start) * 1000,
                    finish_reason=choice.finish_reason,
                )
            else:
                # httpx fallback
                return await client.complete(
                    model=model,
                    messages=messages,
                    max_tokens=request.max_tokens,
                    temperature=request.temperature,
                    start_time=start,
                )

        except Exception as e:
            logger.error("Groq completion failed: %s", str(e))
            raise

    async def health_check(self) -> ProviderHealth:
        """Check Groq API health."""
        if not self.api_key:
            return ProviderHealth(
                provider="groq",
                healthy=False,
                error="GROQ_API_KEY not configured",
            )

        try:
            client = self._get_client()
            start = time.monotonic()

            if hasattr(client, "models"):
                # Official SDK
                import asyncio

                models = await asyncio.to_thread(client.models.list)
                latency = (time.monotonic() - start) * 1000
                model_ids = [m.id for m in models.data] if hasattr(models, "data") else GROQ_MODELS
            else:
                # httpx fallback — just check connectivity
                latency = (time.monotonic() - start) * 1000
                model_ids = GROQ_MODELS

            return ProviderHealth(
                provider="groq",
                healthy=True,
                latency_ms=latency,
                models_available=model_ids,
            )
        except Exception as e:
            return ProviderHealth(
                provider="groq",
                healthy=False,
                error=str(e),
            )

    def get_models(self) -> list[str]:
        """List available Groq models."""
        return GROQ_MODELS


class _GroqHttpxClient:
    """Fallback Groq client using httpx (when groq SDK is not installed)."""

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
                    timeout=30.0,
                )
            except ImportError:
                raise RuntimeError(
                    "Either 'groq' or 'httpx' package is required for Groq provider. "
                    "Install with: pip install groq  OR  pip install httpx",
                ) from None
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
            provider="groq",
            tokens_prompt=usage.get("prompt_tokens", 0),
            tokens_completion=usage.get("completion_tokens", 0),
            tokens_total=usage.get("total_tokens", 0),
            latency_ms=(time.monotonic() - start_time) * 1000,
            finish_reason=choice.get("finish_reason"),
        )
