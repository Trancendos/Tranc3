"""Regression tests for tenant model authorization and cache isolation."""
import pytest

from src.ai_gateway.gateway import AIGateway, AIGatewayError
from src.ai_gateway.types import AIRequest, AIResponse, ProviderHealth, RouteRule, TenantAIConfig
from src.ai_gateway.providers.base import AIProvider


class StubProvider(AIProvider):
    def __init__(self):
        super().__init__("stub")
        self.calls = 0

    async def complete(self, request):
        self.calls += 1
        return AIResponse(text=f"reply-{self.calls}", model=request.model or "stub-default",
                          provider=self.name, tokens_total=1)

    async def health_check(self):
        return ProviderHealth(provider=self.name, healthy=True)

    def get_models(self):
        return ["approved", "denied"]


def configured_gateway():
    gateway = AIGateway()
    provider = StubProvider()
    gateway.register_provider(provider)
    return gateway, provider


@pytest.mark.asyncio
async def test_denied_requested_model_never_calls_provider():
    gateway, provider = configured_gateway()
    tenant = TenantAIConfig(tenant_id="a", routes=[RouteRule(provider="stub")],
                            blocked_models=["denied"], cache_enabled=False)
    with pytest.raises(AIGatewayError) as error:
        await gateway.route(AIRequest(prompt="hi", model="denied"), tenant)
    assert error.value.code == "MODEL_NOT_ALLOWED"
    assert provider.calls == 0


@pytest.mark.asyncio
async def test_route_override_cannot_bypass_model_allowlist():
    gateway, provider = configured_gateway()
    tenant = TenantAIConfig(tenant_id="a",
                            routes=[RouteRule(provider="stub", model="denied")],
                            allowed_models=["approved"], cache_enabled=False)
    with pytest.raises(AIGatewayError):
        await gateway.route(AIRequest(prompt="hi"), tenant)
    assert provider.calls == 0


@pytest.mark.asyncio
async def test_approved_route_model_is_forwarded():
    gateway, provider = configured_gateway()
    tenant = TenantAIConfig(tenant_id="a",
                            routes=[RouteRule(provider="stub", model="approved")],
                            allowed_models=["approved"], cache_enabled=False)
    result = await gateway.route(AIRequest(prompt="hi"), tenant)
    assert result.model == "approved"
    assert provider.calls == 1


def test_cache_key_includes_entire_prompt_messages_and_policy():
    gateway, _ = configured_gateway()
    tenant = TenantAIConfig(tenant_id="a", routes=[RouteRule(provider="stub")])
    prompt = "x" * 210
    a = AIRequest(prompt=prompt + "a")
    b = AIRequest(prompt=prompt + "b")
    assert gateway._make_cache_key(a, tenant) != gateway._make_cache_key(b, tenant)
    c = AIRequest(prompt="same", messages=[{"role": "user", "content": "one"}])
    d = AIRequest(prompt="same", messages=[{"role": "user", "content": "two"}])
    assert gateway._make_cache_key(c, tenant) != gateway._make_cache_key(d, tenant)
    tenant2 = tenant.model_copy(update={"blocked_models": ["denied"]})
    assert gateway._make_cache_key(c, tenant) != gateway._make_cache_key(c, tenant2)
