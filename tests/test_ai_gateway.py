"""
Tests for src/ai_gateway/ — AIGateway router, LRU cache, provider failover
============================================================================
"""

import pytest

from src.ai_gateway.gateway import AIGateway, AIGatewayConfig, AIGatewayError, LRUCache
from src.ai_gateway.providers.base import AIProvider
from src.ai_gateway.providers.offline import OfflineProvider
from src.ai_gateway.types import (
    AIRequest,
    AIResponse,
    GatewayMetrics,
    ProviderHealth,
    ProviderName,
    RouteRule,
    TenantAIConfig,
)

# ─────────────────────────────────────────────────────────────────────────────
# LRU Cache Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestLRUCache:
    """LRU cache for AI responses."""

    def test_put_and_get(self):
        cache = LRUCache(max_size=10)
        response = AIResponse(text="hello", model="test", provider="test")
        cache.put("key1", response)
        result = cache.get("key1")
        assert result is not None
        assert result.text == "hello"

    def test_get_missing_key(self):
        cache = LRUCache(max_size=10)
        assert cache.get("nonexistent") is None

    def test_eviction_on_max_size(self):
        cache = LRUCache(max_size=3)
        for i in range(5):
            cache.put(f"key{i}", AIResponse(text=f"val{i}", model="test", provider="test"))
        # Only last 3 should remain
        assert cache.get("key0") is None
        assert cache.get("key1") is None
        assert cache.get("key2") is not None
        assert cache.get("key3") is not None
        assert cache.get("key4") is not None

    def test_put_updates_existing_key(self):
        cache = LRUCache(max_size=10)
        cache.put("key1", AIResponse(text="old", model="test", provider="test"))
        cache.put("key1", AIResponse(text="new", model="test", provider="test"))
        result = cache.get("key1")
        assert result.text == "new"

    def test_get_moves_to_end_lru_order(self):
        cache = LRUCache(max_size=3)
        cache.put("key0", AIResponse(text="v0", model="test", provider="test"))
        cache.put("key1", AIResponse(text="v1", model="test", provider="test"))
        cache.put("key2", AIResponse(text="v2", model="test", provider="test"))

        # Access key0 to make it recently used
        cache.get("key0")

        # Adding key3 should evict key1 (least recently used), not key0
        cache.put("key3", AIResponse(text="v3", model="test", provider="test"))
        assert cache.get("key0") is not None  # Still present
        assert cache.get("key1") is None  # Evicted

    def test_clear(self):
        cache = LRUCache(max_size=10)
        cache.put("key1", AIResponse(text="v1", model="test", provider="test"))
        cache.put("key2", AIResponse(text="v2", model="test", provider="test"))
        cache.clear()
        assert cache.get("key1") is None
        assert cache.get("key2") is None
        assert cache.size == 0

    def test_size_property(self):
        cache = LRUCache(max_size=10)
        assert cache.size == 0
        cache.put("k1", AIResponse(text="v1", model="test", provider="test"))
        assert cache.size == 1
        cache.put("k2", AIResponse(text="v2", model="test", provider="test"))
        assert cache.size == 2


# ─────────────────────────────────────────────────────────────────────────────
# OfflineProvider Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestOfflineProvider:
    """Offline provider — deterministic fallback."""

    @pytest.mark.asyncio
    async def test_complete_returns_response(self):
        provider = OfflineProvider()
        request = AIRequest(prompt="Hello, world!")
        response = await provider.complete(request)
        assert response.text != ""
        assert response.provider == "offline"
        assert response.model == "offline-deterministic"
        assert response.finish_reason == "offline"

    @pytest.mark.asyncio
    async def test_complete_includes_offline_marker(self):
        provider = OfflineProvider()
        request = AIRequest(prompt="Test prompt")
        response = await provider.complete(request)
        assert "[OFFLINE MODE]" in response.text

    @pytest.mark.asyncio
    async def test_health_check_always_healthy(self):
        provider = OfflineProvider()
        health = await provider.health_check()
        assert health.healthy is True
        assert "offline-deterministic" in health.models_available

    def test_get_models(self):
        provider = OfflineProvider()
        models = provider.get_models()
        assert "offline-deterministic" in models

    @pytest.mark.asyncio
    async def test_complete_includes_prompt_preview(self):
        provider = OfflineProvider()
        request = AIRequest(prompt="What is the meaning of life?")
        response = await provider.complete(request)
        assert "meaning of life" in response.text

    @pytest.mark.asyncio
    async def test_complete_has_token_counts(self):
        provider = OfflineProvider()
        request = AIRequest(prompt="Hello there")
        response = await provider.complete(request)
        assert response.tokens_prompt > 0
        assert response.tokens_completion > 0
        assert response.tokens_total == response.tokens_prompt + response.tokens_completion


# ─────────────────────────────────────────────────────────────────────────────
# Mock Provider for Gateway Tests
# ─────────────────────────────────────────────────────────────────────────────


class MockProvider(AIProvider):
    """Mock AI provider for testing."""

    def __init__(
        self,
        name: str = "mock",
        should_fail: bool = False,
        response_text: str = "mock response",
        healthy: bool = True,
    ) -> None:
        super().__init__(name=name)
        self.should_fail = should_fail
        self.response_text = response_text
        self._healthy = healthy
        self.call_count = 0

    async def complete(self, request: AIRequest) -> AIResponse:
        self.call_count += 1
        if self.should_fail:
            raise ConnectionError(f"Provider {self.name} is unavailable")

        return AIResponse(
            text=self.response_text,
            model=f"{self.name}-model",
            provider=self.name,
            tokens_prompt=10,
            tokens_completion=20,
            tokens_total=30,
            latency_ms=50.0,
        )

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(
            provider=self.name,
            healthy=self._healthy,
            latency_ms=10.0,
            models_available=[f"{self.name}-model"],
        )

    def get_models(self) -> list[str]:
        return [f"{self.name}-model"]


# ─────────────────────────────────────────────────────────────────────────────
# AIGatewayConfig Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestAIGatewayConfig:
    """AIGateway configuration."""

    def test_default_config(self):
        config = AIGatewayConfig()
        assert config.cache_size == 1000
        assert config.verbose is False
        assert config.providers == {}

    def test_custom_config(self):
        providers = {"mock": MockProvider()}
        config = AIGatewayConfig(providers=providers, cache_size=500, verbose=True)
        assert len(config.providers) == 1
        assert config.cache_size == 500


# ─────────────────────────────────────────────────────────────────────────────
# AIGateway Routing Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestAIGatewayRouting:
    """AIGateway provider routing and failover."""

    @pytest.mark.asyncio
    async def test_route_to_first_available_provider(self):
        """When tenant config specifies routes, the first healthy provider is used."""
        ollama = MockProvider(name="ollama", response_text="from ollama")
        offline = OfflineProvider()
        gateway = AIGateway(
            config=AIGatewayConfig(
                providers={"ollama": ollama, "offline": offline},
            ),
        )
        request = AIRequest(prompt="Hello")
        tenant_config = TenantAIConfig(
            tenant_id="test",
            routes=[
                RouteRule(provider="ollama", priority=0),
                RouteRule(provider="offline", priority=1),
            ],
        )
        response = await gateway.route(request, tenant_config=tenant_config)
        assert response.text == "from ollama"
        assert response.provider == "ollama"

    @pytest.mark.asyncio
    async def test_failover_to_next_provider(self):
        """When the first provider fails, the gateway falls over to the next."""
        failing = MockProvider(name="ollama", should_fail=True)
        working = MockProvider(name="openrouter", response_text="from openrouter")
        gateway = AIGateway(
            config=AIGatewayConfig(
                providers={"ollama": failing, "openrouter": working},
            ),
        )
        request = AIRequest(prompt="Hello")
        tenant_config = TenantAIConfig(
            tenant_id="test",
            routes=[
                RouteRule(provider="ollama", priority=0),
                RouteRule(provider="openrouter", priority=1),
            ],
        )
        response = await gateway.route(request, tenant_config=tenant_config)
        assert response.text == "from openrouter"
        assert response.provider == "openrouter"
        assert response.failover_index == 1  # Failed over from first

    @pytest.mark.asyncio
    async def test_failover_to_offline_provider(self):
        """When all real providers fail, the offline provider is the last resort."""
        failing1 = MockProvider(name="ollama", should_fail=True)
        failing2 = MockProvider(name="openrouter", should_fail=True)
        offline = OfflineProvider()
        gateway = AIGateway(
            config=AIGatewayConfig(
                providers={"ollama": failing1, "openrouter": failing2, "offline": offline},
            ),
        )
        request = AIRequest(prompt="Hello")
        tenant_config = TenantAIConfig(
            tenant_id="test",
            routes=[
                RouteRule(provider="ollama", priority=0),
                RouteRule(provider="openrouter", priority=1),
                RouteRule(provider="offline", priority=2),
            ],
        )
        response = await gateway.route(request, tenant_config=tenant_config)
        assert response.provider == "offline"
        assert "[OFFLINE MODE]" in response.text

    @pytest.mark.asyncio
    async def test_no_providers_raises_error(self):
        """With no providers and no routes, an error is raised."""
        gateway = AIGateway(config=AIGatewayConfig(providers={}))
        request = AIRequest(prompt="Hello")
        # No tenant config → uses DEFAULT_TENANT_CONFIG which references
        # ollama/openrouter/offline — but none are registered
        with pytest.raises(AIGatewayError) as exc_info:
            await gateway.route(request)
        assert "NO_ROUTES" in exc_info.value.code or "ALL_PROVIDERS_FAILED" in exc_info.value.code

    @pytest.mark.asyncio
    async def test_route_with_default_tenant_config(self):
        """When no tenant config is passed, DEFAULT_TENANT_CONFIG routes are used."""
        ollama = MockProvider(name="ollama", response_text="local inference")
        gateway = AIGateway(
            config=AIGatewayConfig(
                providers={"ollama": ollama},
            ),
        )
        request = AIRequest(prompt="Hello")
        # DEFAULT_TENANT_CONFIG has ollama at priority 0
        response = await gateway.route(request)
        assert response.provider == "ollama"
        assert response.text == "local inference"

    @pytest.mark.asyncio
    async def test_route_skips_unhealthy_provider(self):
        """Unhealthy providers (from previous failures) are skipped."""
        failing = MockProvider(name="ollama", should_fail=True)
        working = MockProvider(name="openrouter", response_text="cloud inference")
        gateway = AIGateway(
            config=AIGatewayConfig(
                providers={"ollama": failing, "openrouter": working},
            ),
        )
        # First call marks ollama as unhealthy
        request = AIRequest(prompt="Hello")
        tenant_config = TenantAIConfig(
            tenant_id="test",
            routes=[
                RouteRule(provider="ollama", priority=0),
                RouteRule(provider="openrouter", priority=1),
            ],
        )
        await gateway.route(request, tenant_config=tenant_config)
        # ollama is now unhealthy
        health = gateway.get_health("ollama")
        assert health is not None
        assert health.healthy is False


# ─────────────────────────────────────────────────────────────────────────────
# AIGateway Caching Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestAIGatewayCaching:
    """AIGateway response caching."""

    @pytest.mark.asyncio
    async def test_cached_response_returned(self):
        """Second identical request is served from cache."""
        provider = MockProvider(name="mock", response_text="cached result")
        gateway = AIGateway(
            config=AIGatewayConfig(
                providers={"mock": provider},
                cache_size=100,
            ),
        )

        tenant_config = TenantAIConfig(
            tenant_id="test",
            routes=[RouteRule(provider="mock", priority=0)],
        )
        request = AIRequest(prompt="What is 2+2?")
        # First call — should hit provider
        response1 = await gateway.route(request, tenant_config=tenant_config)
        assert response1.cached is False
        assert provider.call_count == 1

        # Second call with same prompt — should be cached
        response2 = await gateway.route(request, tenant_config=tenant_config)
        assert response2.cached is True
        assert provider.call_count == 1  # Not called again

    @pytest.mark.asyncio
    async def test_cache_disabled(self):
        """When cache_enabled=False, every request hits the provider."""
        provider = MockProvider(name="mock", response_text="no cache")
        gateway = AIGateway(
            config=AIGatewayConfig(
                providers={"mock": provider},
            ),
        )
        tenant_config = TenantAIConfig(
            tenant_id="test",
            routes=[RouteRule(provider="mock", priority=0)],
            cache_enabled=False,
        )
        request = AIRequest(prompt="What is 2+2?")
        await gateway.route(request, tenant_config=tenant_config)
        await gateway.route(request, tenant_config=tenant_config)
        assert provider.call_count == 2  # Called twice, no caching


# ─────────────────────────────────────────────────────────────────────────────
# AIGateway Token Budget Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestAIGatewayTokenBudget:
    """Token budget enforcement."""

    @pytest.mark.asyncio
    async def test_token_budget_exceeded(self):
        """When token budget is exceeded, an error is raised."""
        provider = MockProvider(name="mock", response_text="result")
        gateway = AIGateway(
            config=AIGatewayConfig(
                providers={"mock": provider},
            ),
        )
        tenant_config = TenantAIConfig(
            tenant_id="test",
            routes=[RouteRule(provider="mock", priority=0)],
            daily_token_budget=10,
            tokens_used_today=100,  # Already exceeded
        )
        request = AIRequest(prompt="Hello")
        with pytest.raises(AIGatewayError) as exc_info:
            await gateway.route(request, tenant_config=tenant_config)
        assert "TOKEN_BUDGET_EXCEEDED" in exc_info.value.code

    @pytest.mark.asyncio
    async def test_token_budget_not_exceeded(self):
        """When under budget, request proceeds normally."""
        provider = MockProvider(name="mock", response_text="result")
        gateway = AIGateway(
            config=AIGatewayConfig(
                providers={"mock": provider},
            ),
        )
        tenant_config = TenantAIConfig(
            tenant_id="test",
            routes=[RouteRule(provider="mock", priority=0)],
            daily_token_budget=10000,
            tokens_used_today=0,
        )
        request = AIRequest(prompt="Hello")
        response = await gateway.route(request, tenant_config=tenant_config)
        assert response.provider == "mock"
        # tokens_used_today should be updated
        assert tenant_config.tokens_used_today > 0


# ─────────────────────────────────────────────────────────────────────────────
# AIGateway Provider Management Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestAIGatewayProviderManagement:
    """Registering and unregistering providers."""

    def test_register_provider(self):
        gateway = AIGateway(config=AIGatewayConfig(providers={}))
        provider = MockProvider(name="test-provider")
        gateway.register_provider(provider)
        assert "test-provider" in gateway.get_providers()

    def test_unregister_provider(self):
        provider = MockProvider(name="test-provider")
        gateway = AIGateway(config=AIGatewayConfig(providers={"test-provider": provider}))
        result = gateway.unregister_provider("test-provider")
        assert result is True
        assert "test-provider" not in gateway.get_providers()

    def test_unregister_nonexistent_provider(self):
        gateway = AIGateway(config=AIGatewayConfig(providers={}))
        result = gateway.unregister_provider("nonexistent")
        assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# AIGateway Metrics Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestAIGatewayMetrics:
    """Gateway metrics tracking."""

    @pytest.mark.asyncio
    async def test_metrics_track_requests(self):
        provider = MockProvider(name="mock", response_text="result")
        gateway = AIGateway(
            config=AIGatewayConfig(
                providers={"mock": provider},
            ),
        )
        tenant_config = TenantAIConfig(
            tenant_id="test",
            routes=[RouteRule(provider="mock", priority=0)],
            cache_enabled=False,
        )
        request = AIRequest(prompt="Hello")
        await gateway.route(request, tenant_config=tenant_config)
        metrics = gateway.get_metrics()
        assert metrics.total_requests == 1

    @pytest.mark.asyncio
    async def test_metrics_track_tokens(self):
        provider = MockProvider(name="mock", response_text="result")
        gateway = AIGateway(
            config=AIGatewayConfig(
                providers={"mock": provider},
            ),
        )
        tenant_config = TenantAIConfig(
            tenant_id="test",
            routes=[RouteRule(provider="mock", priority=0)],
            cache_enabled=False,
        )
        request = AIRequest(prompt="Hello")
        await gateway.route(request, tenant_config=tenant_config)
        metrics = gateway.get_metrics()
        assert metrics.total_tokens > 0

    @pytest.mark.asyncio
    async def test_metrics_track_failover(self):
        failing = MockProvider(name="ollama", should_fail=True)
        working = MockProvider(name="openrouter", response_text="fallback")
        gateway = AIGateway(
            config=AIGatewayConfig(
                providers={"ollama": failing, "openrouter": working},
            ),
        )
        tenant_config = TenantAIConfig(
            tenant_id="test",
            routes=[
                RouteRule(provider="ollama", priority=0),
                RouteRule(provider="openrouter", priority=1),
            ],
            cache_enabled=False,
        )
        request = AIRequest(prompt="Hello")
        await gateway.route(request, tenant_config=tenant_config)
        metrics = gateway.get_metrics()
        assert metrics.failover_count == 1

    def test_reset_metrics(self):
        gateway = AIGateway()
        gateway._metrics.total_requests = 42
        gateway.reset_metrics()
        metrics = gateway.get_metrics()
        assert metrics.total_requests == 0


# ─────────────────────────────────────────────────────────────────────────────
# AIGateway Health Check Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestAIGatewayHealthCheck:
    """Gateway health check aggregation."""

    @pytest.mark.asyncio
    async def test_health_check_all(self):
        provider = MockProvider(name="mock", healthy=True)
        gateway = AIGateway(config=AIGatewayConfig(providers={"mock": provider}))
        results = await gateway.health_check_all()
        assert "mock" in results
        assert results["mock"].healthy is True

    @pytest.mark.asyncio
    async def test_get_health_cached(self):
        provider = MockProvider(name="mock", healthy=True)
        gateway = AIGateway(config=AIGatewayConfig(providers={"mock": provider}))
        # Run health check first
        await gateway.health_check_all()
        health = gateway.get_health("mock")
        assert health is not None
        assert health.healthy is True

    def test_get_health_not_checked(self):
        gateway = AIGateway()
        health = gateway.get_health("nonexistent")
        assert health is None


# ─────────────────────────────────────────────────────────────────────────────
# AIGateway Type Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestAIGatewayTypes:
    """Pydantic model validation for AI gateway types."""

    def test_ai_request_defaults(self):
        req = AIRequest()
        assert req.prompt == ""
        assert req.messages == []
        assert req.model is None
        assert req.max_tokens == 1024
        assert req.temperature == 0.7
        assert req.stream is False

    def test_ai_request_with_messages(self):
        req = AIRequest(
            messages=[
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Hello"},
            ],
        )
        assert len(req.messages) == 2

    def test_ai_response_defaults(self):
        resp = AIResponse()
        assert resp.text == ""
        assert resp.model == ""
        assert resp.provider == ""
        assert resp.tokens_total == 0
        assert resp.latency_ms == 0.0
        assert resp.cached is False
        assert resp.failover_index == 0

    def test_provider_name_enum(self):
        assert ProviderName.OLLAMA.value == "ollama"
        assert ProviderName.OPENROUTER.value == "openrouter"
        assert ProviderName.HUGGINGFACE.value == "huggingface"
        assert ProviderName.OFFLINE.value == "offline"

    def test_provider_health(self):
        health = ProviderHealth(
            provider="ollama",
            healthy=True,
            latency_ms=10.0,
            models_available=["llama3"],
        )
        assert health.healthy is True
        assert "llama3" in health.models_available

    def test_tenant_ai_config_defaults(self):
        config = TenantAIConfig(tenant_id="test")
        assert config.tenant_id == "test"
        assert config.routes == []
        assert config.daily_token_budget is None
        assert config.tokens_used_today == 0
        assert config.cache_enabled is True
        assert config.default_model is None
        assert config.allowed_models == []
        assert config.blocked_models == []

    def test_route_rule_defaults(self):
        rule = RouteRule(provider="ollama")
        assert rule.provider == "ollama"
        assert rule.priority == 0
        assert rule.condition is None
        assert rule.max_latency_ms is None
        assert rule.enabled is True

    def test_gateway_metrics_defaults(self):
        metrics = GatewayMetrics()
        assert metrics.total_requests == 0
        assert metrics.total_tokens == 0
        assert metrics.failover_count == 0
        assert metrics.cache_hits == 0
        assert metrics.errors == 0
        assert metrics.by_provider == {}
