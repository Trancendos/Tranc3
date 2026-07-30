# tests/test_ai_gateway_capacity_feed.py
# Tests for the additive CapacityGuard feed wired into AIGateway.route()
# (src/ai_gateway/gateway.py) — see docs/governance/TOKEN-EFFICIENCY-MATRIX.md
# §4. Mirrors tests/test_provider_rotation_capacity_feed.py's pattern for the
# provider-side feed. Verifies real tenant token usage reaches CapacityGuard's
# AI_TOKENS_DAILY service, and that a CapacityGuard failure never affects
# AIGateway's own routing/token-budget behavior.

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.ai_gateway.gateway import AIGateway, AIGatewayConfig
from src.ai_gateway.providers.base import AIProvider
from src.ai_gateway.types import (
    AIRequest,
    AIResponse,
    ProviderHealth,
    RouteRule,
    TenantAIConfig,
)
from src.capacity.guard import CapacityGuard, CapacityService, ServiceLimit


class _MockProvider(AIProvider):
    def __init__(self, name: str, tokens_total: int) -> None:
        super().__init__(name=name)
        self._tokens_total = tokens_total

    async def complete(self, request: AIRequest) -> AIResponse:
        return AIResponse(
            text="ok",
            model=f"{self.name}-model",
            provider=self.name,
            tokens_prompt=0,
            tokens_completion=self._tokens_total,
            tokens_total=self._tokens_total,
        )

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(provider=self.name, healthy=True, latency_ms=1.0)

    def get_models(self) -> list[str]:
        return [f"{self.name}-model"]


@pytest.fixture
def guard():
    return CapacityGuard(
        limits=[ServiceLimit(CapacityService.AI_TOKENS_DAILY, 100_000, 86_400, "test")]
    )


def _gateway_and_config(tokens_total: int = 50):
    provider = _MockProvider(name="ollama", tokens_total=tokens_total)
    gateway = AIGateway(config=AIGatewayConfig(providers={"ollama": provider}))
    tenant_config = TenantAIConfig(
        tenant_id="test-tenant",
        routes=[RouteRule(provider="ollama", priority=0)],
    )
    return gateway, tenant_config


class TestAIGatewayCapacityFeed:
    @pytest.mark.asyncio
    async def test_route_feeds_tokens_into_capacity_guard(self, guard):
        gateway, tenant_config = _gateway_and_config(tokens_total=50)
        with patch("src.capacity.guard.get_capacity_guard", return_value=guard):
            await gateway.route(AIRequest(prompt="hi"), tenant_config=tenant_config)
        assert guard.peek(CapacityService.AI_TOKENS_DAILY) == pytest.approx(0.0005)

    @pytest.mark.asyncio
    async def test_capacity_guard_hard_stop_never_propagates(self, guard):
        gateway, tenant_config = _gateway_and_config(tokens_total=100_000)
        with patch("src.capacity.guard.get_capacity_guard", return_value=guard):
            # Would raise CapacityExceededError inside CapacityGuard at 100%
            # if it were allowed to propagate — route() must still succeed.
            response = await gateway.route(AIRequest(prompt="hi"), tenant_config=tenant_config)
        assert response.provider == "ollama"
        assert tenant_config.tokens_used_today == 100_000

    @pytest.mark.asyncio
    async def test_capacity_guard_import_failure_never_propagates(self):
        gateway, tenant_config = _gateway_and_config(tokens_total=50)
        with patch(
            "src.capacity.guard.get_capacity_guard", side_effect=RuntimeError("unavailable")
        ):
            response = await gateway.route(AIRequest(prompt="hi"), tenant_config=tenant_config)
        assert response.provider == "ollama"
        assert tenant_config.tokens_used_today == 50

    @pytest.mark.asyncio
    async def test_own_token_budget_tracking_unaffected(self, guard):
        gateway, tenant_config = _gateway_and_config(tokens_total=42)
        with patch("src.capacity.guard.get_capacity_guard", return_value=guard):
            await gateway.route(AIRequest(prompt="hi"), tenant_config=tenant_config)
        # AIGateway's own tokens_used_today accounting is unchanged by the feed.
        assert tenant_config.tokens_used_today == 42
