"""
AI Gateway — Router & Failover Engine
=======================================
Ported from @trancendos/ai-gateway AIGateway class.

Per-tenant conditional routing with automatic failover.
Prioritises zero-cost providers: Ollama → OpenRouter → Offline.

Features:
- Priority-based provider chain (failover)
- Condition-based routing (plan, tags, time)
- Token budget enforcement
- Response caching (in-memory LRU)
- Latency-based failover
- Per-provider health tracking
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections import OrderedDict

from Dimensional.sanitize import sanitize_for_log
from src.ai_gateway.providers.base import AIProvider
from src.ai_gateway.types import (
    DEFAULT_TENANT_CONFIG,
    AIRequest,
    AIResponse,
    GatewayMetrics,
    ProviderHealth,
    RouteRule,
    TenantAIConfig,
)

logger = logging.getLogger("tranc3.ai_gateway")


class AIGatewayError(Exception):
    """AI gateway specific errors."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


class AIGatewayConfig:
    """Configuration for the AI gateway."""

    def __init__(
        self,
        providers: dict[str, AIProvider] | None = None,
        cache_size: int = 1000,
        verbose: bool = False,
    ) -> None:
        self.providers = providers or {}
        self.cache_size = cache_size
        self.verbose = verbose


class LRUCache:
    """Simple in-memory LRU cache for AI responses."""

    def __init__(self, max_size: int = 1000) -> None:
        self._cache: OrderedDict[str, AIResponse] = OrderedDict()
        self._max_size = max_size

    def get(self, key: str) -> AIResponse | None:
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def put(self, key: str, value: AIResponse) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
        if len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)


class AIGateway:
    """
    AI Gateway — Router & Failover Engine.

    Routes AI requests through a priority-based provider chain,
    automatically failing over on errors. Enforces token budgets,
    caches responses, and tracks per-provider health.

    Usage:
        gateway = AIGateway()
        gateway.register_provider(OllamaProvider())
        gateway.register_provider(OpenRouterProvider(api_key="..."))
        gateway.register_provider(OfflineProvider())

        response = await gateway.route(
            AIRequest(prompt="Hello, world!"),
            TenantAIConfig(tenant_id="user1", routes=[...]),
        )
    """

    def __init__(self, config: AIGatewayConfig | None = None) -> None:
        self._config = config or AIGatewayConfig()
        self._providers: dict[str, AIProvider] = dict(self._config.providers)
        self._cache = LRUCache(max_size=self._config.cache_size)
        self._health_status: dict[str, ProviderHealth] = {}
        self._metrics = GatewayMetrics()

    # ── Provider Management ──────────────────────────────────

    def register_provider(self, provider: AIProvider) -> None:
        """Register a new AI provider."""
        self._providers[provider.name] = provider
        logger.info("ai_provider_registered: %s", sanitize_for_log(provider.name))

    def unregister_provider(self, name: str) -> bool:
        """Remove a provider by name."""
        removed = name in self._providers
        self._providers.pop(name, None)
        self._health_status.pop(name, None)
        return removed

    def get_providers(self) -> dict[str, AIProvider]:
        """Get all registered providers."""
        return dict(self._providers)

    # ── Routing ──────────────────────────────────────────────

    async def route(
        self,
        request: AIRequest,
        tenant_config: TenantAIConfig | None = None,
    ) -> AIResponse:
        """
        Route an AI request through the tenant's provider chain.

        Automatically fails over to the next provider on error.
        Enforces token budgets and caches responses.
        """
        config = tenant_config or DEFAULT_TENANT_CONFIG
        self._metrics.total_requests += 1

        # 0. Capacity guard — check platform daily token budget
        try:
            from src.capacity.guard import CapacityService, get_capacity_guard

            _guard = get_capacity_guard()
            _guard.consume(
                CapacityService.AI_TOKENS_DAILY, amount=0
            )  # peek — actual tokens consumed post-call
            _guard.consume(CapacityService.PLATFORM_REQUESTS_HOURLY, amount=1)
            _guard.consume(CapacityService.PLATFORM_REQUESTS_DAILY, amount=1)
        except Exception as _cap_err:
            from src.capacity.guard import CapacityExceededError

            if isinstance(_cap_err, CapacityExceededError):
                raise AIGatewayError("CAPACITY_EXCEEDED", str(_cap_err)) from _cap_err
            # Non-capacity errors in the guard must never block requests
            pass

        # 1. Check token budget
        if config.daily_token_budget:
            if config.tokens_used_today >= config.daily_token_budget:
                raise AIGatewayError(
                    "TOKEN_BUDGET_EXCEEDED",
                    f"Daily token budget exceeded: {config.tokens_used_today}/{config.daily_token_budget}",
                )

        # 2. Check cache
        if config.cache_enabled:
            cached = self._check_cache(request, config)
            if cached:
                self._metrics.cache_hits += 1
                return cached

        # 3. Resolve applicable routes
        routes = self._resolve_routes(config.routes, request)
        if not routes:
            # Fallback: try all providers in registration order
            routes = [
                RouteRule(provider=name, priority=idx)
                for idx, name in enumerate(self._providers.keys())
            ]

        if not routes:
            raise AIGatewayError(
                "NO_ROUTES", "No applicable routes found and no providers registered",
            )

        # 4. Try each route in priority order
        errors: list[dict[str, str]] = []

        for route_idx, route in enumerate(routes):
            provider = self._providers.get(route.provider)
            if not provider:
                errors.append({"provider": route.provider, "error": "Provider not registered"})
                continue

            # Skip unhealthy providers
            health = self._health_status.get(route.provider)
            if health and not health.healthy:
                if self._config.verbose:
                    logger.info("Skipping unhealthy provider: %s", sanitize_for_log(route.provider))
                continue

            try:
                # Apply route-specific model
                routed_request = request.model_copy(
                    update={
                        "model": route.model or request.model,
                    },
                )

                # Execute with optional timeout
                response = await self._execute_with_timeout(
                    provider,
                    routed_request,
                    route.max_latency_ms,
                )

                # Track failover
                if route_idx > 0:
                    self._metrics.failover_count += 1
                    response.failover_index = route_idx

                # Update metrics
                self._track_success(route.provider, response)

                # Cache response
                if config.cache_enabled:
                    self._cache_response(request, config, response)

                # Update token usage
                config.tokens_used_today += response.tokens_total

                # Capacity guard — record actual token consumption + per-provider requests
                try:
                    from src.capacity.guard import CapacityService, get_capacity_guard

                    _g = get_capacity_guard()
                    if response.tokens_total:
                        _g.consume(CapacityService.AI_TOKENS_DAILY, amount=response.tokens_total)
                        if "cerebras" in route.provider.lower():
                            _g.consume(
                                CapacityService.CEREBRAS_TOKENS, amount=response.tokens_total
                            )
                    _provider = route.provider.lower()
                    if "groq" in _provider:
                        _g.consume(CapacityService.GROQ_REQUESTS, amount=1)
                    elif "gemini" in _provider or "google" in _provider:
                        _g.consume(CapacityService.GEMINI_REQUESTS, amount=1)
                    elif "sambanova" in _provider:
                        _g.consume(CapacityService.SAMBANOVA_REQUESTS, amount=1)
                    elif "openrouter" in _provider:
                        _g.consume(CapacityService.OPENROUTER_REQUESTS, amount=1)
                    elif "huggingface" in _provider or "hf" in _provider:
                        _g.consume(CapacityService.HUGGINGFACE_REQUESTS, amount=1)
                    elif "github" in _provider:
                        _g.consume(CapacityService.GITHUB_MODELS_REQUESTS, amount=1)
                except Exception:
                    pass  # Capacity tracking must never break successful responses

                return response

            except Exception as e:
                errors.append({"provider": route.provider, "error": str(e)})

                # Update health status
                self._health_status[route.provider] = ProviderHealth(
                    provider=route.provider,
                    healthy=False,
                    error=str(e),
                )
                self._track_error(route.provider)

        # All providers failed
        self._metrics.errors += 1
        error_summary = "; ".join(f"{e['provider']}: {e['error']}" for e in errors)
        raise AIGatewayError("ALL_PROVIDERS_FAILED", f"All AI providers failed: {error_summary}")

    # ── Health Checks ────────────────────────────────────────

    async def health_check_all(self) -> dict[str, ProviderHealth]:
        """Run health checks on all providers."""
        results = {}
        for name, provider in self._providers.items():
            try:
                health = await provider.health_check()
                self._health_status[name] = health
                results[name] = health
            except Exception as e:
                result = ProviderHealth(
                    provider=name,
                    healthy=False,
                    error=str(e),
                )
                self._health_status[name] = result
                results[name] = result
        return results

    def get_health(self, provider_name: str) -> ProviderHealth | None:
        """Get cached health status for a provider."""
        return self._health_status.get(provider_name)

    # ── Metrics ──────────────────────────────────────────────

    def get_metrics(self) -> GatewayMetrics:
        """Get aggregate gateway metrics."""
        return self._metrics.model_copy()

    def reset_metrics(self) -> None:
        """Reset all gateway metrics."""
        self._metrics = GatewayMetrics()

    # ── Private ──────────────────────────────────────────────

    def _resolve_routes(self, routes: list[RouteRule], request: AIRequest) -> list[RouteRule]:
        """Resolve applicable routes based on conditions and priority."""
        applicable = []
        for route in routes:
            if not route.enabled:
                continue
            # Check conditions (simple format: "key:value")
            if route.condition:
                if not self._evaluate_condition(route.condition, request):
                    continue
            applicable.append(route)

        # Sort by priority (lower = higher priority)
        return sorted(applicable, key=lambda r: r.priority)

    def _evaluate_condition(self, condition: str, request: AIRequest) -> bool:
        """Evaluate a route condition against the request."""
        # Simple condition format: "key:value"
        if ":" not in condition:
            return True

        key, value = condition.split(":", 1)
        # Check request metadata for condition
        return request.metadata.get(key) == value

    async def _execute_with_timeout(
        self,
        provider: AIProvider,
        request: AIRequest,
        max_latency_ms: int | None = None,
    ) -> AIResponse:
        """Execute a provider call with optional latency limit."""
        import asyncio

        time.monotonic()

        if max_latency_ms:
            try:
                return await asyncio.wait_for(
                    provider.complete(request),
                    timeout=max_latency_ms / 1000.0,
                )
            except asyncio.TimeoutError:
                raise RuntimeError(
                    f"Provider {provider.name} exceeded {max_latency_ms}ms latency",
                ) from None
        else:
            return await provider.complete(request)

    def _check_cache(self, request: AIRequest, config: TenantAIConfig) -> AIResponse | None:
        """Check the response cache."""
        cache_key = self._make_cache_key(request, config)
        cached = self._cache.get(cache_key)
        if cached:
            cached.cached = True
            return cached
        return None

    def _cache_response(
        self, request: AIRequest, config: TenantAIConfig, response: AIResponse,
    ) -> None:
        """Cache a response."""
        cache_key = self._make_cache_key(request, config)
        self._cache.put(cache_key, response)

    def _make_cache_key(self, request: AIRequest, config: TenantAIConfig) -> str:
        """Generate a cache key from request and tenant config."""
        key_data = f"{config.tenant_id}:{request.model or 'default'}:{request.prompt[:200]}:{request.max_tokens}:{request.temperature}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:32]

    def _track_success(self, provider: str, response: AIResponse) -> None:
        """Track a successful provider call."""
        self._metrics.total_tokens += response.tokens_total
        self._metrics.total_latency_ms += response.latency_ms

        if provider not in self._metrics.by_provider:
            self._metrics.by_provider[provider] = {"requests": 0, "tokens": 0, "errors": 0}
        self._metrics.by_provider[provider]["requests"] += 1
        self._metrics.by_provider[provider]["tokens"] += response.tokens_total

    def _track_error(self, provider: str) -> None:
        """Track a provider error."""
        if provider not in self._metrics.by_provider:
            self._metrics.by_provider[provider] = {"requests": 0, "tokens": 0, "errors": 0}
        self._metrics.by_provider[provider]["errors"] += 1
