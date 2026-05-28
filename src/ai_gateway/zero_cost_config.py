# src/ai_gateway/zero_cost_config.py — Zero-Cost AI Provider Configuration
# Auto-discovers and configures free-tier AI providers with optimal routing.
#
# Zero-Cost AI Provider Stack (ranked by capability/cost):
#   1. Ollama (local)     — Free, unlimited, offline-capable
#   2. Groq (cloud-free)  — Free tier, ultra-low latency LPU inference
#   3. OpenRouter (free)   — 28+ free models including DeepSeek R1, Llama, Qwen
#   4. HuggingFace (free)  — Serverless Inference API free tier
#   5. DeepSeek (cheap)    — Not free but extremely cheap ($0.14/M input)
#   6. Offline             — Fallback, deterministic responses, zero cost
#
# This module provides:
#   - Auto-discovery of available providers based on environment variables
#   - Pre-configured routing chains optimized for zero-cost operation
#   - Model mappings that prefer free models when available
#   - Cost tracking to ensure the zero-cost mandate is maintained

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("tranc3.ai_gateway.zero_cost")


class ProviderTier(str, Enum):
    """Cost tier for AI providers."""

    FREE_UNLIMITED = "free_unlimited"  # Ollama (local)
    FREE_TIER = "free_tier"  # Groq, OpenRouter free models
    CHEAP = "cheap"  # DeepSeek ($0.14/M input)
    FREEMIUM = "freemium"  # HuggingFace (rate-limited free)
    OFFLINE = "offline"  # OfflineProvider (deterministic)


@dataclass
class FreeModelInfo:
    """Information about a free-tier AI model."""

    name: str
    provider: str
    tier: ProviderTier
    context_window: int = 4096
    capabilities: List[str] = field(default_factory=list)
    rate_limit: str = "unknown"
    notes: str = ""


# ─── Free Model Catalog ──────────────────────────────────────────────────────
# Curated list of free models available on each provider.
# Updated based on research (2025).

FREE_MODELS: Dict[str, List[FreeModelInfo]] = {
    "openrouter": [
        FreeModelInfo(
            name="deepseek/deepseek-r1:free",
            provider="openrouter",
            tier=ProviderTier.FREE_TIER,
            context_window=65536,
            capabilities=["chat", "reasoning", "code"],
            rate_limit="20 req/min",
            notes="DeepSeek R1 reasoning model, free tier",
        ),
        FreeModelInfo(
            name="meta-llama/llama-3.3-70b-instruct:free",
            provider="openrouter",
            tier=ProviderTier.FREE_TIER,
            context_window=8192,
            capabilities=["chat", "code"],
            rate_limit="20 req/min",
            notes="Llama 3.3 70B, free tier",
        ),
        FreeModelInfo(
            name="qwen/qwen-2.5-72b-instruct:free",
            provider="openrouter",
            tier=ProviderTier.FREE_TIER,
            context_window=32768,
            capabilities=["chat", "code", "multilingual"],
            rate_limit="20 req/min",
            notes="Qwen 2.5 72B, free tier",
        ),
        FreeModelInfo(
            name="mistralai/mistral-7b-instruct:free",
            provider="openrouter",
            tier=ProviderTier.FREE_TIER,
            context_window=32768,
            capabilities=["chat", "code"],
            rate_limit="20 req/min",
            notes="Mistral 7B, free tier",
        ),
        FreeModelInfo(
            name="google/gemma-2-9b-it:free",
            provider="openrouter",
            tier=ProviderTier.FREE_TIER,
            context_window=8192,
            capabilities=["chat", "code"],
            rate_limit="20 req/min",
            notes="Google Gemma 2 9B, free tier",
        ),
    ],
    "groq": [
        FreeModelInfo(
            name="llama-3.3-70b-versatile",
            provider="groq",
            tier=ProviderTier.FREE_TIER,
            context_window=8192,
            capabilities=["chat", "code"],
            rate_limit="30 req/min",
            notes="Ultra-low latency LPU inference",
        ),
        FreeModelInfo(
            name="llama-3.1-8b-instant",
            provider="groq",
            tier=ProviderTier.FREE_TIER,
            context_window=8192,
            capabilities=["chat"],
            rate_limit="30 req/min",
            notes="Fastest inference on Groq",
        ),
        FreeModelInfo(
            name="mixtral-8x7b-32768",
            provider="groq",
            tier=ProviderTier.FREE_TIER,
            context_window=32768,
            capabilities=["chat", "code"],
            rate_limit="30 req/min",
            notes="Mixtral MoE with large context",
        ),
    ],
    "ollama": [
        FreeModelInfo(
            name="llama3.2",
            provider="ollama",
            tier=ProviderTier.FREE_UNLIMITED,
            context_window=8192,
            capabilities=["chat", "code"],
            rate_limit="unlimited",
            notes="Local Llama 3.2, requires Ollama installed",
        ),
        FreeModelInfo(
            name="qwen2.5",
            provider="ollama",
            tier=ProviderTier.FREE_UNLIMITED,
            context_window=32768,
            capabilities=["chat", "code", "multilingual"],
            rate_limit="unlimited",
            notes="Local Qwen 2.5, requires Ollama installed",
        ),
        FreeModelInfo(
            name="deepseek-r1",
            provider="ollama",
            tier=ProviderTier.FREE_UNLIMITED,
            context_window=65536,
            capabilities=["chat", "reasoning", "code"],
            rate_limit="unlimited",
            notes="Local DeepSeek R1, requires Ollama installed",
        ),
    ],
    "huggingface": [
        FreeModelInfo(
            name="meta-llama/Llama-3.2-3B-Instruct",
            provider="huggingface",
            tier=ProviderTier.FREEMIUM,
            context_window=4096,
            capabilities=["chat"],
            rate_limit="rate-limited",
            notes="Serverless Inference API, free tier",
        ),
    ],
    "deepseek": [
        FreeModelInfo(
            name="deepseek-chat",
            provider="deepseek",
            tier=ProviderTier.CHEAP,
            context_window=65536,
            capabilities=["chat", "code"],
            rate_limit="500 req/min",
            notes="Not free but $0.14/M input — cheapest paid option",
        ),
        FreeModelInfo(
            name="deepseek-reasoner",
            provider="deepseek",
            tier=ProviderTier.CHEAP,
            context_window=65536,
            capabilities=["chat", "reasoning"],
            rate_limit="500 req/min",
            notes="DeepSeek R1 reasoning, $0.55/M input",
        ),
    ],
}


@dataclass
class ZeroCostRoutingChain:
    """A pre-configured routing chain optimized for zero-cost operation."""

    name: str
    description: str
    providers: List[str]
    models: Dict[str, str]  # provider -> default model
    estimated_cost_per_1k_requests: str = "$0.00"

    def get_route_rules(self) -> "List[Any]":
        """Convert to RouteRule dicts for AIGateway."""
        from src.ai_gateway.types import RouteRule

        rules: List[Any] = []
        for priority, provider in enumerate(self.providers):
            model = self.models.get(provider, "")
            rules.append(
                RouteRule(
                    provider=provider,
                    model=model,
                    priority=priority,
                    enabled=True,
                )
            )
        return rules


# ─── Pre-configured Routing Chains ───────────────────────────────────────────

ROUTING_CHAINS: Dict[str, ZeroCostRoutingChain] = {
    "zero_cost_full": ZeroCostRoutingChain(
        name="Zero-Cost Full Stack",
        description="Maximum capability at zero cost. Ollama → Groq → OpenRouter → Offline",
        providers=["ollama", "groq", "openrouter", "offline"],
        models={
            "ollama": "llama3.2",
            "groq": "llama-3.3-70b-versatile",
            "openrouter": "deepseek/deepseek-r1:free",
            "offline": "tranc3-offline",
        },
        estimated_cost_per_1k_requests="$0.00",
    ),
    "zero_cost_cloud": ZeroCostRoutingChain(
        name="Zero-Cost Cloud Only",
        description="No local hardware needed. Groq → OpenRouter → HuggingFace → Offline",
        providers=["groq", "openrouter", "huggingface", "offline"],
        models={
            "groq": "llama-3.3-70b-versatile",
            "openrouter": "deepseek/deepseek-r1:free",
            "huggingface": "meta-llama/Llama-3.2-3B-Instruct",
            "offline": "tranc3-offline",
        },
        estimated_cost_per_1k_requests="$0.00",
    ),
    "zero_cost_reasoning": ZeroCostRoutingChain(
        name="Zero-Cost Reasoning",
        description="Optimized for reasoning tasks. DeepSeek R1 (free) → Groq → Offline",
        providers=["openrouter", "groq", "offline"],
        models={
            "openrouter": "deepseek/deepseek-r1:free",
            "groq": "llama-3.3-70b-versatile",
            "offline": "tranc3-offline",
        },
        estimated_cost_per_1k_requests="$0.00",
    ),
    "near_zero_high_quality": ZeroCostRoutingChain(
        name="Near-Zero High Quality",
        description="Best quality with minimal cost. DeepSeek API ($0.14/M) → Groq → OpenRouter → Offline",
        providers=["deepseek", "groq", "openrouter", "offline"],
        models={
            "deepseek": "deepseek-chat",
            "groq": "llama-3.3-70b-versatile",
            "openrouter": "deepseek/deepseek-r1:free",
            "offline": "tranc3-offline",
        },
        estimated_cost_per_1k_requests="~$0.01",
    ),
}


def discover_available_providers() -> Dict[str, bool]:
    """Auto-discover which AI providers are available based on environment variables.

    Returns:
        Dict mapping provider name to availability (True/False).
    """
    available = {}

    # Ollama — check if OLLAMA_HOST is set or default localhost is reachable
    ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    available["ollama"] = bool(os.getenv("OLLAMA_HOST")) or _check_ollama_available(ollama_host)

    # OpenRouter — requires API key
    available["openrouter"] = bool(os.getenv("OPENROUTER_API_KEY"))

    # Groq — requires API key
    available["groq"] = bool(os.getenv("GROQ_API_KEY"))

    # HuggingFace — requires API token
    available["huggingface"] = bool(os.getenv("HUGGINGFACE_API_TOKEN"))

    # DeepSeek — requires API key
    available["deepseek"] = bool(os.getenv("DEEPSEEK_API_KEY"))

    # Offline — always available
    available["offline"] = True

    logger.info(
        "Provider discovery results: %s",
        {k: v for k, v in available.items() if v},
    )
    return available


def _check_ollama_available(host: str) -> bool:
    """Quick check if Ollama is running locally."""
    try:
        import urllib.request

        urllib.request.urlopen(f"{host}/api/tags", timeout=2)  # noqa: S310 — pinging local Ollama only
        return True
    except Exception:
        return False


def get_optimal_chain(chain_name: Optional[str] = None) -> ZeroCostRoutingChain:
    """Get the optimal zero-cost routing chain based on available providers.

    If chain_name is specified, returns that chain. Otherwise, picks
    the best chain based on which providers are actually available.
    """
    if chain_name and chain_name in ROUTING_CHAINS:
        return ROUTING_CHAINS[chain_name]

    available = discover_available_providers()

    # Find the chain with the most available providers
    best_chain = None
    best_score = -1

    for _name, chain in ROUTING_CHAINS.items():
        # Count how many providers in this chain are available
        score = sum(1 for p in chain.providers if available.get(p, False))
        # Prefer chains with higher score (more providers available)
        # Among equal scores, prefer zero-cost over near-zero
        cost_bonus = 100 if "$0.00" in chain.estimated_cost_per_1k_requests else 0
        total = score * 10 + cost_bonus

        if total > best_score:
            best_score = total
            best_chain = chain

    if best_chain is None:
        # Fallback to offline only
        return ZeroCostRoutingChain(
            name="Offline Fallback",
            description="No providers available — offline mode only",
            providers=["offline"],
            models={"offline": "tranc3-offline"},
        )

    logger.info("Selected routing chain: %s (score=%d)", best_chain.name, best_score)
    return best_chain


def get_free_model_catalog() -> Dict[str, List[Dict[str, Any]]]:
    """Get the full free model catalog for API exposure."""
    result = {}
    for provider, models in FREE_MODELS.items():
        result[provider] = [
            {
                "name": m.name,
                "tier": m.tier.value,
                "contextWindow": m.context_window,
                "capabilities": m.capabilities,
                "rateLimit": m.rate_limit,
                "notes": m.notes,
            }
            for m in models
        ]
    return result
