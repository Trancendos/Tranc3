"""
Offline Provider — Deterministic Fallback
===========================================
Last resort in the AI gateway failover chain.
Provides deterministic responses when no AI is available.

Zero-cost: No external dependencies. Always available.
"""

from __future__ import annotations

import logging
import time

from src.ai_gateway.providers.base import AIProvider
from src.ai_gateway.types import AIRequest, AIResponse, ProviderHealth

logger = logging.getLogger("tranc3.ai_gateway.offline")


class OfflineProvider(AIProvider):
    """
    Offline provider — deterministic fallback.

    When all other AI providers fail, this provider returns
    structured responses indicating the system is in offline mode.
    Always available, always zero-cost.
    """

    def __init__(self) -> None:
        super().__init__(name="offline")

    async def complete(self, request: AIRequest) -> AIResponse:
        """Generate a deterministic offline response."""
        start = time.monotonic()

        # Build a helpful offline response
        prompt_preview = (
            request.prompt[:100] + "..." if len(request.prompt) > 100 else request.prompt
        )
        response_text = (
            f"[OFFLINE MODE] I'm currently unable to connect to any AI providers. "
            f"Your request has been logged and will be processed when connectivity is restored.\n\n"
            f"Request summary: {prompt_preview}"
        )

        latency_ms = (time.monotonic() - start) * 1000

        return AIResponse(
            text=response_text,
            model="offline-deterministic",
            provider=self.name,
            tokens_prompt=len(request.prompt.split()),
            tokens_completion=len(response_text.split()),
            tokens_total=len(request.prompt.split()) + len(response_text.split()),
            latency_ms=latency_ms,
            finish_reason="offline",
            metadata={"offline": True, "original_model": request.model},
        )

    async def health_check(self) -> ProviderHealth:
        """Offline provider is always healthy."""
        return ProviderHealth(
            provider=self.name,
            healthy=True,
            latency_ms=0.0,
            models_available=["offline-deterministic"],
        )

    def get_models(self) -> list[str]:
        """List available offline models."""
        return ["offline-deterministic"]
