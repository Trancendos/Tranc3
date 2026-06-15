"""
Zero-cost AI provider rotation — x8 free-tier providers with hard stops.

Provider chain (priority order):
1. Ollama (local, truly zero-cost, no limits)
2. Groq (free tier: 14,400 req/day, 6,000 tokens/min)
3. OpenRouter :free models (free tier: 200 req/day per model)
4. HuggingFace Inference API (free tier: rate-limited)
5. Together AI (free tier: $25 credit, then stops)
6. DeepSeek API (free tier: limited RPM)
7. Cerebras Cloud (free tier: 30 req/min)
8. Cloudflare Workers AI (free tier: 10,000 neurons/day)

Hard stops: each provider tracks daily/hourly usage.
Rotation: when provider hits 80% of limit, rotate to next.
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
    daily_req_limit: int      # -1 = unlimited
    hourly_req_limit: int     # -1 = unlimited
    daily_token_limit: int    # -1 = unlimited
    stop_threshold: float = 0.80   # rotate at 80% of limit
    hard_stop_threshold: float = 0.95  # refuse at 95%

    # Runtime counters (reset daily/hourly)
    _daily_req: int = field(default=0, init=False, repr=False)
    _hourly_req: int = field(default=0, init=False, repr=False)
    _daily_tokens: int = field(default=0, init=False, repr=False)
    _day_start: float = field(default_factory=time.time, init=False, repr=False)
    _hour_start: float = field(default_factory=time.time, init=False, repr=False)
    _consecutive_errors: int = field(default=0, init=False, repr=False)

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
        if self._consecutive_errors >= 5:
            return False
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
    ProviderLimit(
        name="ollama",
        base_url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
        api_key_env="",
        daily_req_limit=-1,
        hourly_req_limit=-1,
        daily_token_limit=-1,
    ),
    ProviderLimit(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY",
        daily_req_limit=14400,
        hourly_req_limit=250,
        daily_token_limit=500000,
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
        name="deepseek",
        base_url="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY",
        daily_req_limit=500,
        hourly_req_limit=60,
        daily_token_limit=-1,
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
        name="cloudflare_ai",
        base_url=f"https://api.cloudflare.com/client/v4/accounts/{os.getenv('CF_ACCOUNT_ID','')}/ai/v1",
        api_key_env="CF_API_TOKEN",
        daily_req_limit=10000,
        hourly_req_limit=500,
        daily_token_limit=-1,
    ),
]

_provider_index: Dict[str, ProviderLimit] = {p.name: p for p in PROVIDERS}


def get_available_provider() -> Optional[ProviderLimit]:
    """Return the highest-priority available provider that hasn't hit rotation threshold."""
    for p in PROVIDERS:
        if p.is_available() and not p.should_rotate():
            return p
    # All at rotation threshold — return first still available (hard stop not hit)
    for p in PROVIDERS:
        if p.is_available():
            logger.warning("All providers at rotation threshold — using %s at capacity", p.name)
            return p
    logger.error("ALL providers have hit hard-stop limits — refusing request")
    return None


def get_usage_dashboard() -> dict:
    return {p.name: p.usage_summary for p in PROVIDERS}


__all__ = ["PROVIDERS", "ProviderLimit", "get_available_provider", "get_usage_dashboard"]
