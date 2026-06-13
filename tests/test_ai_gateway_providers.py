"""
Tests for AI Gateway new providers: Gemini, Cerebras, SambaNova, EmbeddingRouter
==================================================================================
All tests are offline — no real API calls are made. Providers are tested for:
- Graceful skip when API key is not configured
- Correct request/response structure
- Health check reporting when key is absent
- Circuit breaker participation (unhealthy -> skipped in gateway)
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai_gateway.gateway import AIGateway, AIGatewayConfig
from src.ai_gateway.providers.cerebras import CerebrasProvider
from src.ai_gateway.providers.embeddings import (
    EmbeddingRouter,
    GeminiEmbeddingProvider,
    OllamaEmbeddingProvider,
)
from src.ai_gateway.providers.gemini import GeminiProvider
from src.ai_gateway.providers.groq import GroqProvider
from src.ai_gateway.providers.offline import OfflineProvider
from src.ai_gateway.providers.sambanova import SambanovaProvider
from src.ai_gateway.types import AIRequest, ProviderName, RouteRule, TenantAIConfig

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

_FAKE_OPENAI_RESPONSE = {
    "choices": [
        {
            "message": {"content": "Hello from provider"},
            "finish_reason": "stop",
        }
    ],
    "model": "test-model",
    "usage": {
        "prompt_tokens": 10,
        "completion_tokens": 20,
        "total_tokens": 30,
    },
}


def _make_mock_http_response(json_data: dict, status_code: int = 200):
    """Create a mock httpx response."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_data
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


# ──────────────────────────────────────────────────────────────────────────────
# GeminiProvider tests
# ──────────────────────────────────────────────────────────────────────────────


class TestGeminiProvider:
    """GeminiProvider — free cloud provider (GOOGLE_GEMINI_API_KEY)."""

    def test_name(self):
        p = GeminiProvider()
        assert p.name == "gemini"

    def test_no_key_is_not_available(self):
        p = GeminiProvider(api_key="")
        assert not p._is_available()

    def test_key_set_is_available(self):
        p = GeminiProvider(api_key="test-key")
        assert p._is_available()

    def test_reads_env_var(self):
        with patch.dict(os.environ, {"GOOGLE_GEMINI_API_KEY": "env-key"}):
            p = GeminiProvider()
            assert p.api_key == "env-key"
            assert p._is_available()

    @pytest.mark.asyncio
    async def test_complete_raises_without_key(self):
        p = GeminiProvider(api_key="")
        with pytest.raises(RuntimeError, match="GOOGLE_GEMINI_API_KEY"):
            await p.complete(AIRequest(prompt="Hello"))

    @pytest.mark.asyncio
    async def test_health_check_no_key(self):
        p = GeminiProvider(api_key="")
        health = await p.health_check()
        assert health.healthy is False
        assert "GOOGLE_GEMINI_API_KEY" in (health.error or "")

    @pytest.mark.asyncio
    async def test_complete_success(self):
        p = GeminiProvider(api_key="test-key")
        mock_resp = _make_mock_http_response(_FAKE_OPENAI_RESPONSE)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_ctx.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_ctx

            response = await p.complete(AIRequest(prompt="Hello"))

        assert response.provider == "gemini"
        assert response.text == "Hello from provider"
        assert response.tokens_total == 30
        assert response.metadata.get("cost_tier") == "free"

    @pytest.mark.asyncio
    async def test_embed_raises_without_key(self):
        p = GeminiProvider(api_key="")
        with pytest.raises(RuntimeError, match="GOOGLE_GEMINI_API_KEY"):
            await p.embed("Hello")

    @pytest.mark.asyncio
    async def test_embed_success(self):
        p = GeminiProvider(api_key="test-key")
        mock_embed_response = {
            "data": [{"embedding": [0.1, 0.2, 0.3]}],
        }
        mock_resp = _make_mock_http_response(mock_embed_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_ctx.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_ctx

            vector = await p.embed("Hello world")

        assert vector == [0.1, 0.2, 0.3]

    def test_get_models(self):
        p = GeminiProvider()
        models = p.get_models()
        assert "gemini-2.0-flash" in models
        assert "text-embedding-004" in models


# ──────────────────────────────────────────────────────────────────────────────
# CerebrasProvider tests
# ──────────────────────────────────────────────────────────────────────────────


class TestCerebrasProvider:
    """CerebrasProvider — free cloud provider (CEREBRAS_API_KEY)."""

    def test_name(self):
        p = CerebrasProvider()
        assert p.name == "cerebras"

    def test_no_key_is_not_available(self):
        p = CerebrasProvider(api_key="")
        assert not p._is_available()

    def test_key_set_is_available(self):
        p = CerebrasProvider(api_key="test-key")
        assert p._is_available()

    def test_reads_env_var(self):
        with patch.dict(os.environ, {"CEREBRAS_API_KEY": "cbr-key"}):
            p = CerebrasProvider()
            assert p.api_key == "cbr-key"

    @pytest.mark.asyncio
    async def test_complete_raises_without_key(self):
        p = CerebrasProvider(api_key="")
        with pytest.raises(RuntimeError, match="CEREBRAS_API_KEY"):
            await p.complete(AIRequest(prompt="Hello"))

    @pytest.mark.asyncio
    async def test_health_check_no_key(self):
        p = CerebrasProvider(api_key="")
        health = await p.health_check()
        assert health.healthy is False
        assert "CEREBRAS_API_KEY" in (health.error or "")

    @pytest.mark.asyncio
    async def test_complete_success(self):
        p = CerebrasProvider(api_key="test-key")
        mock_resp = _make_mock_http_response(_FAKE_OPENAI_RESPONSE)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_ctx.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_ctx

            response = await p.complete(AIRequest(prompt="Hello"))

        assert response.provider == "cerebras"
        assert response.text == "Hello from provider"
        assert response.tokens_total == 30

    def test_get_models(self):
        p = CerebrasProvider()
        models = p.get_models()
        assert "llama3.3-70b" in models
        assert "llama3.1-8b" in models


# ──────────────────────────────────────────────────────────────────────────────
# SambanovaProvider tests
# ──────────────────────────────────────────────────────────────────────────────


class TestSambanovaProvider:
    """SambanovaProvider — free cloud provider (SAMBANOVA_API_KEY)."""

    def test_name(self):
        p = SambanovaProvider()
        assert p.name == "sambanova"

    def test_no_key_is_not_available(self):
        p = SambanovaProvider(api_key="")
        assert not p._is_available()

    def test_key_set_is_available(self):
        p = SambanovaProvider(api_key="test-key")
        assert p._is_available()

    def test_reads_env_var(self):
        with patch.dict(os.environ, {"SAMBANOVA_API_KEY": "snova-key"}):
            p = SambanovaProvider()
            assert p.api_key == "snova-key"

    @pytest.mark.asyncio
    async def test_complete_raises_without_key(self):
        p = SambanovaProvider(api_key="")
        with pytest.raises(RuntimeError, match="SAMBANOVA_API_KEY"):
            await p.complete(AIRequest(prompt="Hello"))

    @pytest.mark.asyncio
    async def test_health_check_no_key(self):
        p = SambanovaProvider(api_key="")
        health = await p.health_check()
        assert health.healthy is False
        assert "SAMBANOVA_API_KEY" in (health.error or "")

    @pytest.mark.asyncio
    async def test_complete_success(self):
        p = SambanovaProvider(api_key="test-key")
        mock_resp = _make_mock_http_response(_FAKE_OPENAI_RESPONSE)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_ctx.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_ctx

            response = await p.complete(AIRequest(prompt="Hello"))

        assert response.provider == "sambanova"
        assert response.text == "Hello from provider"

    def test_get_models(self):
        p = SambanovaProvider()
        models = p.get_models()
        assert "Meta-Llama-3.3-70B-Instruct" in models
        assert "DeepSeek-R1" in models


# ──────────────────────────────────────────────────────────────────────────────
# GroqProvider tests (existing, just confirm key env var behaviour)
# ──────────────────────────────────────────────────────────────────────────────


class TestGroqProviderKeyHandling:
    """GroqProvider — key env var and health check when key is absent."""

    def test_name(self):
        p = GroqProvider(api_key="")
        assert p.name == "groq"

    def test_reads_env_var(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "groq-key"}):
            p = GroqProvider()
            assert p.api_key == "groq-key"

    @pytest.mark.asyncio
    async def test_health_check_no_key(self):
        p = GroqProvider(api_key="")
        health = await p.health_check()
        assert health.healthy is False
        assert "GROQ_API_KEY" in (health.error or "")

    def test_get_models(self):
        p = GroqProvider()
        models = p.get_models()
        assert "llama-3.3-70b-versatile" in models


# ──────────────────────────────────────────────────────────────────────────────
# EmbeddingRouter tests
# ──────────────────────────────────────────────────────────────────────────────


class TestOllamaEmbeddingProvider:
    """OllamaEmbeddingProvider — local zero-cost embeddings."""

    def test_name(self):
        p = OllamaEmbeddingProvider()
        assert p.name == "ollama-embed"

    def test_default_model(self):
        p = OllamaEmbeddingProvider()
        assert p.model == "nomic-embed-text"

    @pytest.mark.asyncio
    async def test_embed_success(self):
        p = OllamaEmbeddingProvider()
        mock_resp = _make_mock_http_response({"embedding": [0.1] * 768})

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_ctx.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_ctx

            vector = await p.embed("Hello world")

        assert len(vector) == 768
        assert all(v == 0.1 for v in vector)

    @pytest.mark.asyncio
    async def test_embed_empty_raises(self):
        p = OllamaEmbeddingProvider()
        mock_resp = _make_mock_http_response({"embedding": []})

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_ctx.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_ctx

            with pytest.raises(RuntimeError, match="nomic-embed-text"):
                await p.embed("Hello")


class TestGeminiEmbeddingProvider:
    """GeminiEmbeddingProvider — cloud 768-dim embeddings."""

    def test_name(self):
        p = GeminiEmbeddingProvider()
        assert p.name == "gemini-embed"

    def test_no_key_not_available(self):
        p = GeminiEmbeddingProvider(api_key="")
        assert not p._is_available()

    def test_key_set_available(self):
        p = GeminiEmbeddingProvider(api_key="key")
        assert p._is_available()

    @pytest.mark.asyncio
    async def test_embed_raises_without_key(self):
        p = GeminiEmbeddingProvider(api_key="")
        with pytest.raises(RuntimeError, match="GOOGLE_GEMINI_API_KEY"):
            await p.embed("Hello")

    @pytest.mark.asyncio
    async def test_embed_success(self):
        p = GeminiEmbeddingProvider(api_key="test-key")
        mock_resp = _make_mock_http_response({"data": [{"embedding": [0.5] * 768}]})

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_ctx.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_ctx

            vector = await p.embed("Hello world")

        assert len(vector) == 768


class TestEmbeddingRouter:
    """EmbeddingRouter — zero-cost automatic failover."""

    @pytest.mark.asyncio
    async def test_uses_ollama_first(self):
        """Router should prefer Ollama when it returns a valid embedding."""
        router = EmbeddingRouter()

        async def mock_ollama_embed(text):
            return [0.1, 0.2, 0.3]

        async def mock_gemini_embed(text):
            raise RuntimeError("Should not be called")

        router._ollama.embed = mock_ollama_embed
        router._gemini.embed = mock_gemini_embed

        vector = await router.embed("Hello")
        assert vector == [0.1, 0.2, 0.3]

    @pytest.mark.asyncio
    async def test_falls_back_to_gemini(self):
        """Router falls back to Gemini when Ollama fails."""
        router = EmbeddingRouter()

        async def mock_ollama_embed(text):
            raise RuntimeError("Ollama not available")

        async def mock_gemini_embed(text):
            return [0.5, 0.6, 0.7]

        router._ollama.embed = mock_ollama_embed
        router._gemini.embed = mock_gemini_embed

        vector = await router.embed("Hello")
        assert vector == [0.5, 0.6, 0.7]

    @pytest.mark.asyncio
    async def test_raises_when_all_fail(self):
        """Router raises RuntimeError when both providers fail."""
        router = EmbeddingRouter()

        async def fail(text):
            raise RuntimeError("Provider unavailable")

        router._ollama.embed = fail
        router._gemini.embed = fail

        with pytest.raises(RuntimeError, match="All embedding providers failed"):
            await router.embed("Hello")

    @pytest.mark.asyncio
    async def test_get_available_providers(self):
        """get_available_providers returns correct availability dict."""
        router = EmbeddingRouter(ollama_url="http://localhost:11434")

        router._ollama.is_available = AsyncMock(return_value=True)
        router._gemini.is_available = AsyncMock(return_value=False)

        result = await router.get_available_providers()
        assert result["ollama-embed"] is True
        assert result["gemini-embed"] is False


# ──────────────────────────────────────────────────────────────────────────────
# Gateway integration: new providers participate in circuit breaker
# ──────────────────────────────────────────────────────────────────────────────


class TestNewProvidersInGateway:
    """New providers integrate with the AIGateway circuit breaker."""

    @pytest.mark.asyncio
    async def test_gemini_skipped_when_no_key(self):
        """Gemini (no key) fails → gateway falls over to offline."""
        gemini = GeminiProvider(api_key="")
        offline = OfflineProvider()
        gateway = AIGateway(
            config=AIGatewayConfig(
                providers={"gemini": gemini, "offline": offline},
            )
        )
        tenant_config = TenantAIConfig(
            tenant_id="test",
            routes=[
                RouteRule(provider="gemini", priority=0),
                RouteRule(provider="offline", priority=1),
            ],
        )
        response = await gateway.route(AIRequest(prompt="Hello"), tenant_config=tenant_config)
        assert response.provider == "offline"
        assert "[OFFLINE MODE]" in response.text

    @pytest.mark.asyncio
    async def test_cerebras_skipped_when_no_key(self):
        """Cerebras (no key) fails → gateway falls over to offline."""
        cerebras = CerebrasProvider(api_key="")
        offline = OfflineProvider()
        gateway = AIGateway(
            config=AIGatewayConfig(
                providers={"cerebras": cerebras, "offline": offline},
            )
        )
        tenant_config = TenantAIConfig(
            tenant_id="test",
            routes=[
                RouteRule(provider="cerebras", priority=0),
                RouteRule(provider="offline", priority=1),
            ],
        )
        response = await gateway.route(AIRequest(prompt="Hello"), tenant_config=tenant_config)
        assert response.provider == "offline"

    @pytest.mark.asyncio
    async def test_sambanova_skipped_when_no_key(self):
        """SambaNova (no key) fails → gateway falls over to offline."""
        sambanova = SambanovaProvider(api_key="")
        offline = OfflineProvider()
        gateway = AIGateway(
            config=AIGatewayConfig(
                providers={"sambanova": sambanova, "offline": offline},
            )
        )
        tenant_config = TenantAIConfig(
            tenant_id="test",
            routes=[
                RouteRule(provider="sambanova", priority=0),
                RouteRule(provider="offline", priority=1),
            ],
        )
        response = await gateway.route(AIRequest(prompt="Hello"), tenant_config=tenant_config)
        assert response.provider == "offline"

    @pytest.mark.asyncio
    async def test_full_new_chain_falls_to_offline(self):
        """All new providers unconfigured → offline is the final fallback."""
        gateway = AIGateway(
            config=AIGatewayConfig(
                providers={
                    "groq": GroqProvider(api_key=""),
                    "gemini": GeminiProvider(api_key=""),
                    "cerebras": CerebrasProvider(api_key=""),
                    "sambanova": SambanovaProvider(api_key=""),
                    "offline": OfflineProvider(),
                }
            )
        )
        tenant_config = TenantAIConfig(
            tenant_id="test",
            routes=[
                RouteRule(provider="groq", priority=0),
                RouteRule(provider="gemini", priority=1),
                RouteRule(provider="cerebras", priority=2),
                RouteRule(provider="sambanova", priority=3),
                RouteRule(provider="offline", priority=4),
            ],
        )
        response = await gateway.route(AIRequest(prompt="Hello"), tenant_config=tenant_config)
        assert response.provider == "offline"
        assert "[OFFLINE MODE]" in response.text


# ──────────────────────────────────────────────────────────────────────────────
# ProviderName enum covers new providers
# ──────────────────────────────────────────────────────────────────────────────


class TestProviderNameEnum:
    """ProviderName enum includes all providers."""

    def test_new_providers_in_enum(self):
        names = {p.value for p in ProviderName}
        assert "groq" in names
        assert "gemini" in names
        assert "cerebras" in names
        assert "sambanova" in names

    def test_existing_providers_still_present(self):
        names = {p.value for p in ProviderName}
        assert "ollama" in names
        assert "openrouter" in names
        assert "huggingface" in names
        assert "offline" in names
