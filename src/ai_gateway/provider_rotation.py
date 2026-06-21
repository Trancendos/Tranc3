"""
Zero-cost AI provider rotation — x11 free-tier providers with hard stops.

Provider chain (priority order — rotate at 80%, hard-stop at 95%):
 0. LiteLLM proxy   (local aggregator — delegates to all below)
 1. Ollama          (local, truly zero-cost, no limits)
 2. Groq            (free: 14,400 req/day, 6,000 tokens/min)
 3. Cerebras        (free: 30 req/min, fast inference)
 4. SambaNova       (free: 50K tokens/req, generous limits)
 5. Gemini Flash    (free: 1,500 req/day, 1M tokens/min)
 6. OpenRouter :free (free: 200 req/day per model, 50+ models)
 7. Mistral         (free: Le Chat API, no hard limit documented)
 8. DeepSeek        (free tier: limited RPM)
 9. HuggingFace     (free: rate-limited serverless inference)
10. Together AI     (free: $25 credit, then paid)
11. Cloudflare AI   (free: 10,000 neurons/day)

Hard stops: each provider tracks daily/hourly usage via SQLite (limit_monitor).
Rotation: when provider hits 80% of limit, rotate to next available.
x11 ensures continuous operation even if 8 providers are exhausted.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger("tranc3.ai_gateway.rotation")


@dataclass
class ProviderLimit:
    name: str
    base_url: str
    api_key_env: str
    daily_req_limit: int  # -1 = unlimited
    hourly_req_limit: int  # -1 = unlimited
    daily_token_limit: int  # -1 = unlimited
    stop_threshold: float = 0.80  # rotate at 80% of limit
    hard_stop_threshold: float = 0.95  # refuse at 95%

    # Runtime counters (reset daily/hourly)
    _daily_req: int = field(default=0, init=False, repr=False)
    _hourly_req: int = field(default=0, init=False, repr=False)
    _daily_tokens: int = field(default=0, init=False, repr=False)
    _day_start: float = field(default_factory=time.time, init=False, repr=False)
    _hour_start: float = field(default_factory=time.time, init=False, repr=False)
    _consecutive_errors: int = field(default=0, init=False, repr=False)
    _error_cooldown_until: float = field(default=0.0, init=False, repr=False)

    def _reset_if_needed(self) -> None:
        now = time.time()
        if now - self._day_start >= 86400:
            self._daily_req = 0
            self._daily_tokens = 0
            self._day_start = now
        if now - self._hour_start >= 3600:
            self._hourly_req = 0
            self._hour_start = now

    def is_available(self) -> bool:
        self._reset_if_needed()
        if self._consecutive_errors >= 5 and time.time() < self._error_cooldown_until:
            return False
        if self._consecutive_errors >= 5:
            # Cooldown expired — allow a probe attempt
            self._consecutive_errors = 0
        if self.daily_req_limit != -1:
            if self._daily_req >= int(self.daily_req_limit * self.hard_stop_threshold):
                return False
        if self.hourly_req_limit != -1:
            if self._hourly_req >= int(self.hourly_req_limit * self.hard_stop_threshold):
                return False
        if self.daily_token_limit != -1:
            if self._daily_tokens >= int(self.daily_token_limit * self.hard_stop_threshold):
                return False
        return True

    def should_rotate(self) -> bool:
        self._reset_if_needed()
        if self.daily_req_limit != -1:
            if self._daily_req >= int(self.daily_req_limit * self.stop_threshold):
                return True
        if self.hourly_req_limit != -1:
            if self._hourly_req >= int(self.hourly_req_limit * self.stop_threshold):
                return True
        return False

    def record_request(self, tokens_used: int = 0) -> None:
        self._reset_if_needed()
        self._daily_req += 1
        self._hourly_req += 1
        self._daily_tokens += tokens_used
        self._consecutive_errors = 0

    def record_error(self) -> None:
        self._consecutive_errors += 1
        if self._consecutive_errors >= 5:
            # 5-minute cooldown before allowing probe attempts
            self._error_cooldown_until = time.time() + 300

    @property
    def usage_summary(self) -> dict:
        self._reset_if_needed()
        return {
            "name": self.name,
            "available": self.is_available(),
            "should_rotate": self.should_rotate(),
            "daily_req": self._daily_req,
            "daily_req_limit": self.daily_req_limit,
            "hourly_req": self._hourly_req,
            "hourly_req_limit": self.hourly_req_limit,
            "daily_tokens": self._daily_tokens,
            "consecutive_errors": self._consecutive_errors,
        }


PROVIDERS: List[ProviderLimit] = [
    # ── Tier 0: Local aggregator — delegates to all other providers ──────
    ProviderLimit(
        name="litellm",
        base_url=os.getenv("LITELLM_URL", "http://litellm:4000"),
        api_key_env="LITELLM_MASTER_KEY",
        daily_req_limit=-1,
        hourly_req_limit=-1,
        daily_token_limit=-1,
    ),
    # ── Tier 0b: Self-hosted inference engines (unlimited, zero-cost) ────
    ProviderLimit(
        name="llamacpp",
        base_url=os.getenv("LLAMACPP_BASE_URL", "http://localhost:8091"),
        api_key_env="",
        daily_req_limit=-1,
        hourly_req_limit=-1,
        daily_token_limit=-1,
    ),
    ProviderLimit(
        name="vllm",
        base_url=os.getenv("VLLM_BASE_URL", "http://localhost:8090/v1"),
        api_key_env="",
        daily_req_limit=-1,
        hourly_req_limit=-1,
        daily_token_limit=-1,
    ),
    # ── Tier 1: Local self-hosted (truly unlimited) ──────────────────────
    ProviderLimit(
        name="ollama",
        base_url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
        api_key_env="",
        daily_req_limit=-1,
        hourly_req_limit=-1,
        daily_token_limit=-1,
    ),
    # ── Tier 2: Free cloud providers (no credit card required) ───────────
    ProviderLimit(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY",
        daily_req_limit=14400,
        hourly_req_limit=250,
        daily_token_limit=500000,
    ),
    ProviderLimit(
        name="cerebras",
        base_url="https://api.cerebras.ai/v1",
        api_key_env="CEREBRAS_API_KEY",
        daily_req_limit=1440,
        hourly_req_limit=30,
        daily_token_limit=-1,
    ),
    ProviderLimit(
        name="sambanova",
        base_url="https://fast-api.snova.ai/v1",
        api_key_env="SAMBANOVA_API_KEY",
        daily_req_limit=5000,
        hourly_req_limit=200,
        daily_token_limit=10_000_000,
    ),
    ProviderLimit(
        name="gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        api_key_env="GEMINI_API_KEY",
        daily_req_limit=1500,
        hourly_req_limit=60,
        daily_token_limit=1_000_000,
    ),
    ProviderLimit(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        daily_req_limit=200,
        hourly_req_limit=50,
        daily_token_limit=-1,
    ),
    ProviderLimit(
        name="mistral",
        base_url="https://api.mistral.ai/v1",
        api_key_env="MISTRAL_API_KEY",
        daily_req_limit=2000,
        hourly_req_limit=100,
        daily_token_limit=-1,
    ),
    ProviderLimit(
        name="deepseek",
        base_url="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY",
        daily_req_limit=500,
        hourly_req_limit=60,
        daily_token_limit=-1,
    ),
    ProviderLimit(
        name="huggingface",
        base_url="https://api-inference.huggingface.co",
        api_key_env="HF_API_TOKEN",
        daily_req_limit=1000,
        hourly_req_limit=100,
        daily_token_limit=-1,
    ),
    ProviderLimit(
        name="together",
        base_url="https://api.together.xyz/v1",
        api_key_env="TOGETHER_API_KEY",
        daily_req_limit=500,
        hourly_req_limit=60,
        daily_token_limit=100000,
    ),
    ProviderLimit(
        name="cloudflare_ai",
        base_url=f"https://api.cloudflare.com/client/v4/accounts/{os.getenv('CF_ACCOUNT_ID', '')}/ai/v1",
        api_key_env="CF_API_TOKEN",
        daily_req_limit=10000,
        hourly_req_limit=500,
        daily_token_limit=-1,
    ),
]

PROVIDER_INDEX: Dict[str, ProviderLimit] = {p.name: p for p in PROVIDERS}


try:
    from Dimensional.swarm.ant_colony import AntColonyRouter as _AntColonyRouter

    _aco_router: Optional[_AntColonyRouter] = _AntColonyRouter(
        provider_names=[p.name for p in PROVIDERS]
    )
except Exception:
    _aco_router = None


def get_available_provider(use_aco: bool = True) -> Optional[ProviderLimit]:
    """Return the highest-priority available provider that hasn't hit rotation threshold.

    When use_aco=True and the ACO router is available, uses pheromone-based selection
    (biased toward historically successful, low-latency providers) rather than strict
    priority order. Falls back to priority order if ACO is unavailable.
    """
    available = [p for p in PROVIDERS if p.is_available() and not p.should_rotate()]
    if not available:
        # All at rotation threshold — try providers at capacity before giving up
        available = [p for p in PROVIDERS if p.is_available()]
        if available:
            logger.warning("All providers at rotation threshold — using %s at capacity", available[0].name)

    if not available:
        logger.error("ALL providers have hit hard-stop limits — refusing request")
        return None

    if use_aco and _aco_router is not None:
        available_names = {p.name for p in available}
        candidates = _aco_router.select(n=len(available))
        # pick first ACO candidate that is actually available
        for name in candidates:
            if name in available_names:
                return PROVIDER_INDEX[name]

    return available[0]


def record_provider_outcome(
    provider_name: str, success: bool, latency_ms: float = 0.0
) -> None:
    """Feed ACO pheromone update after a request completes."""
    if _aco_router is None or provider_name not in PROVIDER_INDEX:
        return
    if success:
        _aco_router.record_success(provider_name, latency_ms)
    else:
        _aco_router.record_failure(provider_name)


def get_usage_dashboard() -> dict:
    dashboard = {p.name: p.usage_summary for p in PROVIDERS}
    if _aco_router is not None:
        dashboard["_aco_stats"] = _aco_router.stats()
    return dashboard


__all__ = [
    "PROVIDERS",
    "PROVIDER_INDEX",
    "ProviderLimit",
    "get_available_provider",
    "get_usage_dashboard",
    "record_provider_outcome",
]
