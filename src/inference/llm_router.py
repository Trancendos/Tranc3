# src/inference/llm_router.py
# Production LLM Router — routes inference requests to available providers
# with automatic fallback, rate limiting, and cost tracking.
#
# Priority: Local Tranc3 → HuggingFace Inference → Groq → OpenAI-compatible
# Zero-cost first: free tiers before paid APIs.

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─── Provider enum ────────────────────────────────────────────────

class Provider(str, Enum):
    LOCAL      = "local"          # Tranc3 trained model
    HUGGINGFACE = "huggingface"   # HF Inference API (free tier)
    GROQ       = "groq"           # Groq Cloud (free tier available)
    OPENAI     = "openai"         # Any OpenAI-compatible endpoint
    FALLBACK   = "fallback"       # Deterministic bootstrap response


# ─── Configuration ────────────────────────────────────────────────

@dataclass
class ProviderConfig:
    name: Provider
    api_key_env: str              # environment variable holding the key
    base_url: str
    model_id: str
    max_tokens: int = 256
    timeout_seconds: float = 30.0
    enabled: bool = True
    cost_per_1k_tokens: float = 0.0   # USD, 0 = free
    rate_limit_rpm: int = 60          # requests per minute

    @property
    def api_key(self) -> Optional[str]:
        return os.getenv(self.api_key_env)


# ─── Default provider configurations ─────────────────────────────

DEFAULT_PROVIDERS: List[ProviderConfig] = [
    ProviderConfig(
        name=Provider.LOCAL,
        api_key_env="TRANC3_LOCAL_KEY",
        base_url="",
        model_id="tranc3-base",
        max_tokens=256,
        cost_per_1k_tokens=0.0,
        rate_limit_rpm=1000,
    ),
    ProviderConfig(
        name=Provider.HUGGINGFACE,
        api_key_env="HF_API_KEY",
        base_url="https://api-inference.huggingface.co/models",
        model_id=os.getenv("HF_MODEL_ID", "microsoft/phi-3-mini-4k-instruct"),
        max_tokens=256,
        timeout_seconds=30.0,
        cost_per_1k_tokens=0.0,
        rate_limit_rpm=30,
    ),
    ProviderConfig(
        name=Provider.GROQ,
        api_key_env="GROQ_API_KEY",
        base_url="https://api.groq.com/openai/v1",
        model_id=os.getenv("GROQ_MODEL_ID", "llama-3.1-8b-instant"),
        max_tokens=256,
        timeout_seconds=30.0,
        cost_per_1k_tokens=0.0,
        rate_limit_rpm=30,
    ),
    ProviderConfig(
        name=Provider.OPENAI,
        api_key_env="OPENAI_API_KEY",
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        model_id=os.getenv("OPENAI_MODEL_ID", "gpt-3.5-turbo"),
        max_tokens=256,
        timeout_seconds=30.0,
        cost_per_1k_tokens=0.5,
        rate_limit_rpm=60,
    ),
    ProviderConfig(
        name=Provider.FALLBACK,
        api_key_env="TRANC3_FALLBACK_KEY",
        base_url="",
        model_id="tranc3-bootstrap",
        max_tokens=256,
        cost_per_1k_tokens=0.0,
        rate_limit_rpm=10000,
    ),
]


# ─── Request / Response types ─────────────────────────────────────

@dataclass
class GenerationRequest:
    prompt: str
    personality: str = "tranc3-base"
    system_prompt: Optional[str] = None
    max_tokens: int = 256
    temperature: float = 0.8
    top_p: float = 0.9
    preferred_provider: Optional[Provider] = None


@dataclass
class GenerationResponse:
    text: str
    provider: Provider
    model: str
    tokens_used: int = 0
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    from_cache: bool = False
    fallback_used: bool = False


# ─── Rate limiter (token bucket) ──────────────────────────────────

class _RateLimiter:
    """Simple token-bucket rate limiter per provider."""

    def __init__(self, rpm: int):
        self._rpm = rpm
        self._tokens = rpm
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._rpm, self._tokens + elapsed * (self._rpm / 60.0))
            self._last_refill = now
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False


# ─── Simple response cache ────────────────────────────────────────

class _ResponseCache:
    """In-memory LRU cache for identical prompts (Redis-backed in production)."""

    def __init__(self, max_size: int = 500, ttl_seconds: float = 300.0):
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._store: Dict[str, tuple[float, GenerationResponse]] = {}

    def _key(self, req: GenerationRequest) -> str:
        raw = f"{req.prompt}|{req.personality}|{req.system_prompt}|{req.max_tokens}|{req.temperature}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def get(self, req: GenerationRequest) -> Optional[GenerationResponse]:
        k = self._key(req)
        entry = self._store.get(k)
        if entry is None:
            return None
        ts, resp = entry
        if time.monotonic() - ts > self._ttl:
            del self._store[k]
            return None
        return resp

    def put(self, req: GenerationRequest, resp: GenerationResponse) -> None:
        k = self._key(req)
        if len(self._store) >= self._max_size:
            oldest = min(self._store, key=lambda x: self._store[x][0])
            del self._store[oldest]
        self._store[k] = (time.monotonic(), resp)


# ─── The Router ────────────────────────────────────────────────────

class LLMRouter:
    """
    Multi-provider LLM router with fallback chain, rate limiting, and caching.

    Priority order (zero-cost first):
      1. Local Tranc3 model (if trained weights exist)
      2. HuggingFace Inference API (free tier)
      3. Groq Cloud (free tier)
      4. OpenAI-compatible endpoint (paid — last resort)

    If no provider is available, returns an honest bootstrap response.
    """

    def __init__(self, providers: Optional[List[ProviderConfig]] = None):
        self._providers = providers or DEFAULT_PROVIDERS
        self._limiters: Dict[Provider, _RateLimiter] = {}
        self._cache = _ResponseCache()
        self._local_engine = None
        self._stats: Dict[str, Any] = {
            "total_requests": 0,
            "cache_hits": 0,
            "provider_counts": {p.name.value: 0 for p in self._providers},
            "fallback_count": 0,
            "error_counts": {p.name.value: 0 for p in self._providers},
        }

        for p in self._providers:
            self._limiters[p.name] = _RateLimiter(p.rate_limit_rpm)

        logger.info(
            "LLMRouter initialised with %d providers: %s",
            len(self._providers),
            [p.name.value for p in self._providers],
        )

    # ─── Public API ──────────────────────────────────────────────

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Generate a response using the best available provider."""
        self._stats["total_requests"] += 1

        # Check cache first
        cached = self._cache.get(request)
        if cached is not None:
            self._stats["cache_hits"] += 1
            return GenerationResponse(
                text=cached.text,
                provider=cached.provider,
                model=cached.model,
                tokens_used=cached.tokens_used,
                latency_ms=0.0,
                cost_usd=0.0,
                from_cache=True,
                fallback_used=cached.fallback_used,
            )

        # Build provider priority list
        providers = self._build_priority(request.preferred_provider)

        last_error: Optional[str] = None
        for provider_cfg in providers:
            if not provider_cfg.enabled:
                continue

            # Check rate limit
            limiter = self._limiters.get(provider_cfg.name)
            if limiter and not await limiter.acquire():
                logger.warning("Rate limit hit for %s, skipping", provider_cfg.name.value)
                continue

            # Check API key (except local and fallback)
            if provider_cfg.name not in (Provider.LOCAL, Provider.FALLBACK):
                if not provider_cfg.api_key:
                    continue

            # Attempt generation
            try:
                t0 = time.monotonic()
                response = await self._call_provider(provider_cfg, request)
                response.latency_ms = (time.monotonic() - t0) * 1000

                # Track stats
                self._stats["provider_counts"][provider_cfg.name.value] += 1

                # Cache the response
                self._cache.put(request, response)

                return response

            except Exception as exc:
                last_error = str(exc)
                self._stats["error_counts"][provider_cfg.name.value] += 1
                logger.warning(
                    "Provider %s failed: %s — trying next",
                    provider_cfg.name.value,
                    exc,
                )
                continue

        # All providers failed — return honest bootstrap response
        self._stats["fallback_count"] += 1
        return self._fallback_response(request, last_error)

    async def health_check(self) -> Dict[str, Any]:
        """Return health status of all providers."""
        statuses = {}
        for p in self._providers:
            if not p.enabled:
                statuses[p.name.value] = {"status": "disabled"}
                continue

            if p.name == Provider.LOCAL:
                statuses[p.name.value] = {
                    "status": "ok" if self._local_engine and self._local_engine._loaded else "not_trained",
                    "model": p.model_id,
                }
            elif p.name == Provider.FALLBACK:
                statuses[p.name.value] = {"status": "always_ok"}
            else:
                has_key = bool(p.api_key)
                statuses[p.name.value] = {
                    "status": "configured" if has_key else "no_api_key",
                    "model": p.model_id,
                    "base_url": p.base_url,
                }

        return {
            "router_status": "operational",
            "providers": statuses,
            "stats": self._stats,
            "cache_size": len(self._cache._store),
        }

    def get_stats(self) -> Dict[str, Any]:
        """Return router statistics."""
        return dict(self._stats)

    def set_local_engine(self, engine: Any) -> None:
        """Set the local Tranc3Engine instance."""
        self._local_engine = engine

    # ─── Provider implementations ────────────────────────────────

    async def _call_provider(
        self, cfg: ProviderConfig, request: GenerationRequest
    ) -> GenerationResponse:
        if cfg.name == Provider.LOCAL:
            return await self._call_local(cfg, request)
        elif cfg.name == Provider.HUGGINGFACE:
            return await self._call_huggingface(cfg, request)
        elif cfg.name == Provider.GROQ:
            return await self._call_openai_compatible(cfg, request)
        elif cfg.name == Provider.OPENAI:
            return await self._call_openai_compatible(cfg, request)
        elif cfg.name == Provider.FALLBACK:
            return self._fallback_response(request, None)
        else:
            raise ValueError(f"Unknown provider: {cfg.name}")

    async def _call_local(
        self, cfg: ProviderConfig, request: GenerationRequest
    ) -> GenerationResponse:
        """Use the local Tranc3 model if trained weights exist."""
        if self._local_engine is None:
            # Try to load
            try:
                from src.core.tranc3_inference import Tranc3Engine
                self._local_engine = Tranc3Engine()
                self._local_engine.load()
            except Exception as exc:
                raise RuntimeError(f"Local engine load failed: {exc}")

        if self._local_engine._bootstrap_mode:
            raise RuntimeError("Local model not trained yet — bootstrap mode")

        result = await self._local_engine.generate(
            prompt=request.prompt,
            personality=request.personality,
            system_prompt=request.system_prompt,
            max_new_tokens=request.max_tokens,
            temperature=request.temperature,
            top_p=request.top_p,
        )

        return GenerationResponse(
            text=result.get("response", ""),
            provider=Provider.LOCAL,
            model="tranc3-local",
            tokens_used=result.get("tokens", 0),
        )

    async def _call_huggingface(
        self, cfg: ProviderConfig, request: GenerationRequest
    ) -> GenerationResponse:
        """Call HuggingFace Inference API (free tier)."""
        import httpx

        system = request.system_prompt or f"You are TRANC3 ({request.personality})."
        payload = {
            "inputs": f"<|system|>\n{system}<|end|>\n<|user|>\n{request.prompt}<|end|>\n<|assistant|>\n",
            "parameters": {
                "max_new_tokens": min(request.max_tokens, cfg.max_tokens),
                "temperature": request.temperature,
                "top_p": request.top_p,
                "return_full_text": False,
            },
            "options": {"wait_for_model": True},
        }

        url = f"{cfg.base_url}/{cfg.model_id}"
        headers = {
            "Authorization": f"Bearer {cfg.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=cfg.timeout_seconds) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        if isinstance(data, list) and data:
            text = data[0].get("generated_text", "")
        elif isinstance(data, dict) and "generated_text" in data:
            text = data["generated_text"]
        else:
            text = str(data)

        # Clean up any remaining special tokens
        for marker in ("<|end|>", "<|assistant|>", "<|user|>", "<|system|>"):
            text = text.replace(marker, "").strip()

        return GenerationResponse(
            text=text,
            provider=Provider.HUGGINGFACE,
            model=cfg.model_id,
            tokens_used=len(text.split()),  # approximate
        )

    async def _call_openai_compatible(
        self, cfg: ProviderConfig, request: GenerationRequest
    ) -> GenerationResponse:
        """Call any OpenAI-compatible API (Groq, OpenAI, local Ollama, etc.)."""
        import httpx

        system = request.system_prompt or f"You are TRANC3 ({request.personality})."
        payload = {
            "model": cfg.model_id,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": request.prompt},
            ],
            "max_tokens": min(request.max_tokens, cfg.max_tokens),
            "temperature": request.temperature,
            "top_p": request.top_p,
        }

        headers = {
            "Authorization": f"Bearer {cfg.api_key}",
            "Content-Type": "application/json",
        }

        url = f"{cfg.base_url}/chat/completions"

        async with httpx.AsyncClient(timeout=cfg.timeout_seconds) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        text = data["choices"][0]["message"]["content"]
        tokens_used = data.get("usage", {}).get("completion_tokens", 0)

        return GenerationResponse(
            text=text,
            provider=cfg.name,
            model=cfg.model_id,
            tokens_used=tokens_used,
        )

    # ─── Priority ordering ────────────────────────────────────────

    def _build_priority(
        self, preferred: Optional[Provider] = None
    ) -> List[ProviderConfig]:
        """Build provider priority list. Zero-cost first, preferred provider first."""
        by_name = {p.name: p for p in self._providers}
        order = [Provider.LOCAL, Provider.HUGGINGFACE, Provider.GROQ, Provider.OPENAI, Provider.FALLBACK]

        # If preferred, move it to front
        if preferred and preferred in by_name:
            order.remove(preferred)
            order.insert(0, preferred)

        return [by_name[name] for name in order if name in by_name]

    # ─── Honest fallback ──────────────────────────────────────────

    def _fallback_response(
        self, request: GenerationRequest, last_error: Optional[str]
    ) -> GenerationResponse:
        """Honest bootstrap response when no providers are available."""
        personalities = {
            "dorris-fontaine": "financial analyst",
            "cornelius-macintyre": "orchestration coordinator",
            "the-guardian": "security specialist",
            "vesper-nightingale": "healthcare advisor",
            "atlas-meridian": "infrastructure architect",
        }
        role = personalities.get(request.personality, "assistant")

        text = (
            f"TRANC3 ({request.personality} — {role}) is available but no LLM provider "
            f"is currently configured. To enable AI responses, set one of these environment variables:\n\n"
            f"  • HF_API_KEY — HuggingFace Inference API (free tier, 30 req/min)\n"
            f"  • GROQ_API_KEY — Groq Cloud (free tier, fast inference)\n"
            f"  • OPENAI_API_KEY — OpenAI-compatible endpoint\n"
            f"  • Or train the local model: python train.py\n\n"
            f"Your prompt was: '{request.prompt[:200]}'"
        )
        if last_error:
            text += f"\n\nLast provider error: {last_error}"

        return GenerationResponse(
            text=text,
            provider=Provider.FALLBACK,
            model="tranc3-bootstrap",
            fallback_used=True,
        )


# ─── Module-level singleton ────────────────────────────────────────

_router: Optional[LLMRouter] = None


def get_router() -> LLMRouter:
    """Return the singleton LLM router."""
    global _router
    if _router is None:
        _router = LLMRouter()
    return _router
