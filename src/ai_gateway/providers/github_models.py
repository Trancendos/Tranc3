# src/ai_gateway/providers/github_models.py — GitHub Models Provider (Free Tier)
# Free access to GPT-4o, Llama 3.1 70B, DeepSeek-R1, Mistral, Phi-3 and more.
#
# Free Tier (genuinely free, no credit card):
#   GPT-4o:           50 requests/day, 10 RPM
#   GPT-4o-mini:      150 requests/day, 15 RPM
#   Llama 3.1 70B:    150 requests/day, 15 RPM
#   DeepSeek-R1:      150 requests/day, 15 RPM
#   Phi-3 mini:       150 requests/day, 15 RPM
#   Token limits:     8,000 input + 4,000 output per request
#
# Requires: GITHUB_TOKEN environment variable (any GitHub PAT — no special scopes)
# Docs: https://docs.github.com/github-models

from __future__ import annotations

import logging
import os
import time
from typing import Optional

import httpx

from src.ai_gateway.providers.base import AIProvider
from src.ai_gateway.types import AIRequest, AIResponse, ProviderHealth

logger = logging.getLogger("tranc3.ai_gateway.github_models")

GITHUB_MODELS_BASE_URL = "https://models.inference.ai.azure.com"
GITHUB_MODELS_AVAILABLE = [
    "gpt-4o",
    "gpt-4o-mini",
    "meta-llama-3.1-70b-instruct",
    "meta-llama-3.1-8b-instruct",
    "deepseek-r1",
    "mistral-small",
    "phi-3-mini-128k-instruct",
    "phi-3-medium-128k-instruct",
]


class GitHubModelsProvider(AIProvider):
    """GitHub Models — free access to GPT-4o, Llama 3.1, DeepSeek-R1 and more.

    Uses a standard GitHub Personal Access Token (PAT) — no special scopes
    required, no credit card, no payment method. The account just needs to
    be a GitHub account.

    Honest constraints:
    - GPT-4o: 50 requests/day, 10 RPM
    - Smaller models (gpt-4o-mini, Llama, etc.): 150 requests/day, 15 RPM
    - 8K input + 4K output tokens per request
    - Prototyping tier — meant for development, not production scale
    - Rate limits are strict; this provider is used in rotation after
      higher-volume free providers are exhausted.

    Zero-Cost Mandate: This provider operates entirely within the free tier.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: str = "gpt-4o-mini",
    ) -> None:
        super().__init__(
            name="github-models",
            base_url=GITHUB_MODELS_BASE_URL,
            api_key=api_key or os.getenv("GITHUB_TOKEN", ""),
        )
        self._default_model = default_model

    async def complete(self, request: AIRequest) -> AIResponse:
        """Generate a completion using GitHub Models free tier."""
        if not self.api_key:
            raise RuntimeError(
                "GITHUB_TOKEN is required for GitHub Models. "
                "Create a free Personal Access Token at https://github.com/settings/tokens "
                "(no special scopes needed). "
                "Free tier: 50 req/day for GPT-4o, 150 req/day for other models."
            )

        model = request.model or self._default_model
        start = time.monotonic()

        messages = request.messages or [{"role": "user", "content": request.prompt}]

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": min(request.max_tokens or 1024, 4000),
            "temperature": request.temperature,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{GITHUB_MODELS_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        choice = data["choices"][0]
        usage = data.get("usage", {})

        return AIResponse(
            text=choice["message"]["content"] or "",
            model=model,
            provider="github-models",
            tokens_prompt=usage.get("prompt_tokens", 0),
            tokens_completion=usage.get("completion_tokens", 0),
            tokens_total=usage.get("total_tokens", 0),
            latency_ms=(time.monotonic() - start) * 1000,
            finish_reason=choice.get("finish_reason"),
        )

    async def health_check(self) -> ProviderHealth:
        """Check GitHub Models availability."""
        if not self.api_key:
            return ProviderHealth(
                provider="github-models",
                healthy=False,
                error="GITHUB_TOKEN not configured — create a free PAT at github.com/settings/tokens",
            )

        try:
            start = time.monotonic()
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{GITHUB_MODELS_BASE_URL}/info",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
            latency = (time.monotonic() - start) * 1000

            return ProviderHealth(
                provider="github-models",
                healthy=response.status_code < 500,
                latency_ms=latency,
                models_available=GITHUB_MODELS_AVAILABLE,
            )
        except Exception as e:
            return ProviderHealth(
                provider="github-models",
                healthy=False,
                error=str(e),
            )

    def get_models(self) -> list[str]:
        """List available GitHub Models free-tier models."""
        return GITHUB_MODELS_AVAILABLE
