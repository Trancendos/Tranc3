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
import sqlite3
import time
from pathlib import Path
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

_DB_PATH = Path(os.getenv("DATA_DIR", "/tmp")) / "mistral_budget.db"


def _open_db() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS monthly_budget "
        "(month TEXT PRIMARY KEY, tokens_used INTEGER NOT NULL DEFAULT 0)"
    )
    conn.commit()
    return conn


def _current_month() -> str:
    return time.strftime("%Y-%m")


class MistralFreeProvider(AIProvider):
    """Mistral La Plateforme free tier — 500K tokens/month, GDPR-compliant.

    Zero-Cost Mandate: enforces a monthly token hard stop at 95% of the free
    500K token budget. Token usage is persisted to SQLite so restarts don't
    reset the counter mid-month.

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
        # Ensure schema exists at startup; do not hold a persistent connection.
        _open_db().close()

    def _get_monthly_tokens(self) -> int:
        with _open_db() as conn:
            row = conn.execute(
                "SELECT tokens_used FROM monthly_budget WHERE month=?", (_current_month(),)
            ).fetchone()
        return row[0] if row else 0

    def _add_monthly_tokens(self, count: int) -> None:
        with _open_db() as conn:
            conn.execute(
                "INSERT INTO monthly_budget (month, tokens_used) VALUES (?, ?) "
                "ON CONFLICT(month) DO UPDATE SET tokens_used = tokens_used + excluded.tokens_used",
                (_current_month(), count),
            )
            conn.commit()

    def _budget_ok(self) -> bool:
        return self._get_monthly_tokens() < int(_MONTHLY_TOKEN_BUDGET * _STOP_THRESHOLD)

    async def complete(self, request: AIRequest) -> AIResponse:
        if not self.api_key:
            raise RuntimeError(
                "MISTRAL_API_KEY is required. Sign up free at https://console.mistral.ai — "
                "no credit card needed. Free tier: 500K tokens/month."
            )
        if not self._budget_ok():
            used = self._get_monthly_tokens()
            raise RuntimeError(
                f"Mistral free monthly budget exhausted "
                f"({used:,}/{_MONTHLY_TOKEN_BUDGET:,} tokens). "
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
        self._add_monthly_tokens(tokens_used)
        monthly_used = self._get_monthly_tokens()

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
                "monthly_tokens_used": monthly_used,
                "monthly_budget": _MONTHLY_TOKEN_BUDGET,
                "budget_pct": round(monthly_used / _MONTHLY_TOKEN_BUDGET * 100, 1),
            },
        )

    async def health_check(self) -> ProviderHealth:
        if not self.api_key:
            return ProviderHealth(provider=self.name, healthy=False, error="No MISTRAL_API_KEY")
        budget_pct = self._get_monthly_tokens() / _MONTHLY_TOKEN_BUDGET * 100
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
