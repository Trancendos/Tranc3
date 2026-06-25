# src/ai_gateway/providers/mistral_free.py — Mistral La Plateforme Free Tier
#
# Free Tier: 500K tokens/month, no credit card needed
# Models: mistral-small-latest, open-mistral-7b, open-mixtral-8x7b
# Endpoint: api.mistral.ai — European-hosted, GDPR-compliant
#
# Requires: MISTRAL_API_KEY (free signup at console.mistral.ai)

from __future__ import annotations

import logging
import os
import time
from typing import Optional

import httpx

from src.ai_gateway.providers.base import AIProvider
from src.ai_gateway.types import AIRequest, AIResponse, ProviderHealth

logger = logging.getLogger("tranc3.ai_gateway.mistral_free")

MISTRAL_BASE_URL = "https://api.mistral.ai/v1"
MISTRAL_FREE_MODELS = [
    "open-mistral-7b",
    "open-mixtral-8x7b",
    "mistral-small-latest",
]
# Monthly token budget (free tier) — hard stop at 95%
_MONTHLY_TOKEN_BUDGET = 500_000
_STOP_THRESHOLD = 0.95


class MistralFreeProvider(AIProvider):
    """Mistral La Plateforme free tier — 500K tokens/month, GDPR-compliant.

    Zero-Cost Mandate: enforces a monthly token hard stop at 95% of the free
    500K token budget. Switches to next provider when budget is near exhausted.

    EU-hosted (Paris), GDPR Article 28 compliant — preferred for EU users.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: str = "open-mistral-7b",
    ) -> None:
        super().__init__(
            name="mistral-free",
            base_url=MISTRAL_BASE_URL,
            api_key=api_key or os.getenv("MISTRAL_API_KEY", ""),
        )
        self._default_model = default_model
        self._monthly_tokens_used: int = 0
        self._month_start: float = time.time()

    def _reset_if_new_month(self) -> None:
        now = time.time()
        if now - self._month_start >= 2_592_000:  # 30 days
            self._monthly_tokens_used = 0
            self._month_start = now

    def _budget_ok(self) -> bool:
        self._reset_if_new_month()
        return self._monthly_tokens_used < int(_MONTHLY_TOKEN_BUDGET * _STOP_THRESHOLD)

    async def complete(self, request: AIRequest) -> AIResponse:
        if not self.api_key:
            raise RuntimeError(
                "MISTRAL_API_KEY is required. Sign up free at https://console.mistral.ai — "
                "no credit card needed. Free tier: 500K tokens/month."
            )
        if not self._budget_ok():
            raise RuntimeError(
                f"Mistral free monthly budget exhausted "
                f"({self._monthly_tokens_used:,}/{_MONTHLY_TOKEN_BUDGET:,} tokens). "
                "Rotating to next provider."
            )

        model = request.model if request.model in MISTRAL_FREE_MODELS else self._default_model
        messages = (
            request.messages if request.messages else [{"role": "user", "content": request.prompt}]
        )
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": min(request.max_tokens or 512, 4096),
            "temperature": request.temperature or 0.7,
            "stream": False,
        }

        start = time.monotonic()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{MISTRAL_BASE_URL}/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        usage = data.get("usage", {})
        tokens_used = usage.get("total_tokens", 0)
        self._monthly_tokens_used += tokens_used

        text = data["choices"][0]["message"]["content"]
        latency_ms = int((time.monotonic() - start) * 1000)

        return AIResponse(
            text=text,
            model=model,
            provider=self.name,
            tokens_used=tokens_used,
            latency_ms=latency_ms,
            cost=0.0,
            metadata={
                "monthly_tokens_used": self._monthly_tokens_used,
                "monthly_budget": _MONTHLY_TOKEN_BUDGET,
                "budget_pct": round(self._monthly_tokens_used / _MONTHLY_TOKEN_BUDGET * 100, 1),
            },
        )

    async def health_check(self) -> ProviderHealth:
        if not self.api_key:
            return ProviderHealth(provider=self.name, healthy=False, error="No MISTRAL_API_KEY")
        self._reset_if_new_month()
        budget_pct = self._monthly_tokens_used / _MONTHLY_TOKEN_BUDGET * 100
        if budget_pct >= _STOP_THRESHOLD * 100:
            return ProviderHealth(
                provider=self.name,
                healthy=False,
                reason=f"Monthly budget at {budget_pct:.1f}% — hard stop engaged",
            )
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{MISTRAL_BASE_URL}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                resp.raise_for_status()
            return ProviderHealth(
                provider=self.name,
                healthy=True,
                latency_ms=None,
                metadata={"budget_pct": round(budget_pct, 1)},
            )
        except Exception as exc:
            return ProviderHealth(provider=self.name, healthy=False, error=str(exc))

    def get_models(self) -> list[str]:
        return MISTRAL_FREE_MODELS
