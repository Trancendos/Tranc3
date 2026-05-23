"""
AI Gateway Types — Data models and configuration
==================================================
Ported from @trancendos/ai-gateway TypeScript types.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

# ── Enums ────────────────────────────────────────────────────


class ProviderName(str, enum.Enum):
    """Well-known AI provider names."""

    OLLAMA = "ollama"
    OPENROUTER = "openrouter"
    HUGGINGFACE = "huggingface"
    OFFLINE = "offline"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GROQ = "groq"
    DEEPSEEK = "deepseek"


# ── Data Models ──────────────────────────────────────────────


class AIRequest(BaseModel):
    """An AI inference request."""

    prompt: str = ""
    messages: list[dict[str, str]] = Field(default_factory=list)
    model: Optional[str] = None
    max_tokens: int = 1024
    temperature: float = 0.7
    top_p: float = 1.0
    stream: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class AIResponse(BaseModel):
    """An AI inference response."""

    text: str = ""
    model: str = ""
    provider: str = ""
    tokens_prompt: int = 0
    tokens_completion: int = 0
    tokens_total: int = 0
    latency_ms: float = 0.0
    failover_index: int = 0
    cached: bool = False
    finish_reason: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RouteRule(BaseModel):
    """A routing rule for AI requests."""

    provider: str
    model: Optional[str] = None
    priority: int = 0
    condition: Optional[str] = None  # e.g., "plan:free", "tag:fast"
    max_latency_ms: Optional[int] = None
    weight: float = 1.0
    enabled: bool = True


class TenantAIConfig(BaseModel):
    """Per-tenant AI configuration."""

    tenant_id: str
    routes: list[RouteRule] = Field(default_factory=list)
    daily_token_budget: Optional[int] = None
    tokens_used_today: int = 0
    cache_enabled: bool = True
    default_model: Optional[str] = None
    allowed_models: list[str] = Field(default_factory=list)
    blocked_models: list[str] = Field(default_factory=list)


class ProviderHealth(BaseModel):
    """Health status of an AI provider."""

    provider: str
    healthy: bool = True
    latency_ms: float = 0.0
    error: Optional[str] = None
    last_checked: Optional[datetime] = None
    models_available: list[str] = Field(default_factory=list)


class GatewayMetrics(BaseModel):
    """Aggregate metrics for the AI gateway."""

    total_requests: int = 0
    total_tokens: int = 0
    total_latency_ms: float = 0.0
    failover_count: int = 0
    cache_hits: int = 0
    errors: int = 0
    by_provider: dict[str, dict[str, int]] = Field(default_factory=dict)


# ── Default Configurations ───────────────────────────────────

DEFAULT_TENANT_CONFIG = TenantAIConfig(
    tenant_id="default",
    routes=[
        RouteRule(provider="ollama", priority=0),  # First: local, zero-cost
        RouteRule(provider="groq", priority=1),  # Second: free cloud, ultra-low latency
        RouteRule(provider="openrouter", priority=2),  # Third: free cloud models
        RouteRule(provider="offline", priority=3),  # Last: deterministic fallback
    ],
    daily_token_budget=100000,
    cache_enabled=True,
)

FREE_TIER_CONFIG = TenantAIConfig(
    tenant_id="free",
    routes=[
        RouteRule(provider="ollama", priority=0),
        RouteRule(provider="groq", priority=1),  # Free tier: 30 req/min
        RouteRule(provider="offline", priority=2),
    ],
    daily_token_budget=10000,
    cache_enabled=True,
)
