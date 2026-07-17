"""
AI routing logic for the infinity-ai worker.

Contains:
  - All provider client classes (OllamaClient, GroqClient, CerebrasClient,
    OpenRouterClient, HuggingFaceClient, TogetherClient, DeepSeekClient,
    OfflineClient)
  - LRU cache
  - AIGatewayRouter (AdaptiveRotation, provider failover, caching, budget)
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import HTTPException
from models import (
    ChatCompletionChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionUsage,
    ChatMessage,
    ProviderName,
)

from config import (
    CEREBRAS_API_KEY,
    CEREBRAS_BASE_URL,
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    GROQ_API_KEY,
    GROQ_BASE_URL,
    HUGGINGFACE_API_KEY,
    HUGGINGFACE_BASE_URL,
    LRU_CACHE_MAX_SIZE,
    OLLAMA_BASE_URL,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    SMART_CACHE_CAPACITY,
    SMART_CACHE_TTL_S,
    TOGETHER_API_KEY,
    TOGETHER_BASE_URL,
    WORKER_NAME,
)
from database import AIDatabase
from sanitize import sanitize_for_log

logger = logging.getLogger(WORKER_NAME)

# ---------------------------------------------------------------------------
# Smart semantic cache (optional — falls back to built-in LRU if unavailable)
# ---------------------------------------------------------------------------
_SMART_CACHE = None
try:
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from src.ai_gateway.smart_cache import get_cache as _get_smart_cache

    _SMART_CACHE = _get_smart_cache(capacity=SMART_CACHE_CAPACITY, ttl_s=SMART_CACHE_TTL_S)
except Exception:
    pass


# ---------------------------------------------------------------------------
# LRU Cache
# ---------------------------------------------------------------------------


class LRUCache:
    """Simple LRU cache for AI responses."""

    def __init__(self, max_size: int = 500):
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._max_size = max_size
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            return None

    def put(self, key: str, value: Any):
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            else:
                self._cache[key] = value
            if len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    def clear(self):
        with self._lock:
            self._cache.clear()


# ---------------------------------------------------------------------------
# Provider Clients (zero-cost — no paid APIs)
# ---------------------------------------------------------------------------


class OllamaClient:
    """Ollama local inference client — primary zero-cost provider."""

    def __init__(self, base_url: str = OLLAMA_BASE_URL):
        self.base_url = base_url.rstrip("/")
        self._available: Optional[bool] = None

    async def complete(
        self,
        model: str,
        messages: List[ChatMessage],
        max_tokens: int,
        temperature: float,
    ) -> Optional[Dict[str, Any]]:
        try:
            payload = {
                "model": model,
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "stream": False,
                "options": {"num_predict": max_tokens, "temperature": temperature},
            }
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=120.0,
                )
                if resp.status_code == 200:
                    return resp.json()
                return None
        except Exception as e:
            logger.warning("Ollama request failed: %s", e)
            self._available = False
            return None

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.base_url}/api/tags", timeout=5.0)
                return resp.status_code == 200
        except Exception:
            self._available = False
            return False


class OpenRouterClient:
    """OpenRouter free-tier client — secondary zero-cost provider."""

    FREE_MODELS = [
        "meta-llama/llama-3.2-3b-instruct:free",
        "qwen/qwen-2.5-72b-instruct:free",
        "google/gemma-2-9b-it:free",
        "mistralai/mistral-7b-instruct:free",
    ]

    def __init__(self, base_url: str = OPENROUTER_BASE_URL, api_key: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or OPENROUTER_API_KEY

    async def complete(
        self,
        model: str,
        messages: List[ChatMessage],
        max_tokens: int,
        temperature: float,
    ) -> Optional[Dict[str, Any]]:
        import urllib.error
        import urllib.request

        try:
            actual_model = model
            if not model.endswith(":free"):
                actual_model = self.FREE_MODELS[0]

            payload = {
                "model": actual_model,
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            data = json.dumps(payload).encode()
            req = urllib.request.Request(
                f"{self.base_url}/chat/completions",
                data=data,
                method="POST",
            )
            req.add_header("Content-Type", "application/json")
            req.add_header("HTTP-Referer", "https://trancendos.com")
            req.add_header("X-Title", "Tranc3 AI Gateway")
            if self.api_key:
                req.add_header("Authorization", f"Bearer {self.api_key}")
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            logger.warning("OpenRouter HTTP error: %s %s", e.code, e.reason)
            return None
        except Exception as e:
            logger.warning("OpenRouter request failed: %s", e)
            return None


class HuggingFaceClient:
    """HuggingFace Inference API client — free-tier provider."""

    FREE_MODELS = [
        "meta-llama/Llama-3.2-3B-Instruct",
        "mistralai/Mistral-7B-Instruct-v0.3",
        "microsoft/Phi-3-mini-4k-instruct",
    ]

    def __init__(self, base_url: str = HUGGINGFACE_BASE_URL, api_key: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or HUGGINGFACE_API_KEY

    async def complete(
        self,
        model: str,
        messages: List[ChatMessage],
        max_tokens: int,
        temperature: float,
    ) -> Optional[Dict[str, Any]]:
        import urllib.error
        import urllib.request

        try:
            prompt = "\n".join(f"{m.role}: {m.content}" for m in messages) + "\nassistant:"
            payload = {
                "inputs": prompt,
                "parameters": {"max_new_tokens": max_tokens, "temperature": temperature},
            }
            data = json.dumps(payload).encode()
            actual_model = model if "/" in model else self.FREE_MODELS[0]
            req = urllib.request.Request(
                f"{self.base_url}/models/{actual_model}",
                data=data,
                method="POST",
            )
            req.add_header("Content-Type", "application/json")
            if self.api_key:
                req.add_header("Authorization", f"Bearer {self.api_key}")
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode())
                if isinstance(result, list) and len(result) > 0:
                    text = result[0].get("generated_text", "")
                    return {"content": text}
                elif isinstance(result, dict) and "error" in result:
                    logger.warning("HuggingFace error: %s", result["error"])
                    return None
                return result
        except urllib.error.HTTPError as e:
            if e.code == 503:
                logger.info("HuggingFace model loading, will retry later")
            else:
                logger.warning("HuggingFace HTTP error: %s", e.code)
            return None
        except Exception as e:
            logger.warning("HuggingFace request failed: %s", e)
            return None


class GroqClient:
    """Groq free-tier client — ultra-low latency LLaMA/Mixtral inference."""

    FREE_MODELS = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "mixtral-8x7b-32768",
        "gemma2-9b-it",
    ]

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or GROQ_API_KEY
        self.base_url = GROQ_BASE_URL

    async def complete(
        self,
        model: str,
        messages: List[ChatMessage],
        max_tokens: int,
        temperature: float,
    ) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            return None
        import urllib.error
        import urllib.request

        try:
            actual_model = model if model in self.FREE_MODELS else self.FREE_MODELS[0]
            payload = {
                "model": actual_model,
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            data = json.dumps(payload).encode()
            req = urllib.request.Request(
                f"{self.base_url}/chat/completions", data=data, method="POST"
            )
            req.add_header("Content-Type", "application/json")
            req.add_header("Authorization", f"Bearer {self.api_key}")
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            logger.warning("Groq HTTP %s: %s", e.code, e.reason)
            return None
        except Exception as e:
            logger.warning("Groq request failed: %s", sanitize_for_log(e))
            return None


class CerebrasClient:
    """Cerebras free-tier client — high-speed inference via Cerebras AI Cloud."""

    FREE_MODELS = ["llama3.1-8b", "llama3.3-70b"]

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or CEREBRAS_API_KEY
        self.base_url = CEREBRAS_BASE_URL

    async def complete(
        self,
        model: str,
        messages: List[ChatMessage],
        max_tokens: int,
        temperature: float,
    ) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            return None
        import urllib.error
        import urllib.request

        try:
            actual_model = model if model in self.FREE_MODELS else self.FREE_MODELS[0]
            payload = {
                "model": actual_model,
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            data = json.dumps(payload).encode()
            req = urllib.request.Request(
                f"{self.base_url}/chat/completions", data=data, method="POST"
            )
            req.add_header("Content-Type", "application/json")
            req.add_header("Authorization", f"Bearer {self.api_key}")
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            logger.warning("Cerebras HTTP %s: %s", e.code, e.reason)
            return None
        except Exception as e:
            logger.warning("Cerebras request failed: %s", sanitize_for_log(e))
            return None


class TogetherClient:
    """Together AI client — free-tier with $25 credit, generous open-source models."""

    FREE_MODELS = [
        "meta-llama/Llama-3.2-3B-Instruct-Turbo",
        "mistralai/Mixtral-8x7B-Instruct-v0.1",
        "togethercomputer/RedPajama-INCITE-Chat-3B-v1",
    ]

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or TOGETHER_API_KEY
        self.base_url = TOGETHER_BASE_URL

    async def complete(
        self,
        model: str,
        messages: List[ChatMessage],
        max_tokens: int,
        temperature: float,
    ) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            return None
        import urllib.error
        import urllib.request

        try:
            actual_model = model if "/" in model else self.FREE_MODELS[0]
            payload = {
                "model": actual_model,
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            data = json.dumps(payload).encode()
            req = urllib.request.Request(
                f"{self.base_url}/chat/completions", data=data, method="POST"
            )
            req.add_header("Content-Type", "application/json")
            req.add_header("Authorization", f"Bearer {self.api_key}")
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
                content = result["choices"][0]["message"]["content"]
                return {"content": content, "model": actual_model, "provider": "together"}
        except Exception as e:
            logger.warning("Together request failed: %s", sanitize_for_log(e))
            return None


class DeepSeekClient:
    """DeepSeek client — free API with generous limits, OpenAI-compatible."""

    FREE_MODEL = "deepseek-chat"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or DEEPSEEK_API_KEY
        self.base_url = DEEPSEEK_BASE_URL

    async def complete(
        self,
        model: str,
        messages: List[ChatMessage],
        max_tokens: int,
        temperature: float,
    ) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            return None
        import urllib.error
        import urllib.request

        try:
            payload = {
                "model": self.FREE_MODEL,
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            data = json.dumps(payload).encode()
            req = urllib.request.Request(
                f"{self.base_url}/chat/completions", data=data, method="POST"
            )
            req.add_header("Content-Type", "application/json")
            req.add_header("Authorization", f"Bearer {self.api_key}")
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
                content = result["choices"][0]["message"]["content"]
                return {"content": content, "model": self.FREE_MODEL, "provider": "deepseek"}
        except Exception as e:
            logger.warning("DeepSeek request failed: %s", sanitize_for_log(e))
            return None


class OfflineClient:
    """Offline fallback — deterministic responses when no provider is available."""

    FALLBACK_RESPONSES = {
        "default": (
            "I'm currently operating in offline mode. My local AI service is not available "
            "right now. Please try again later when the Ollama service is restored."
        ),
        "greeting": (
            "Hello! I'm in offline mode right now, but I'm still here to help. "
            "Full AI capabilities will return when the local service is restored."
        ),
        "error": (
            "I apologize, but I'm unable to process your request at this time due to "
            "service unavailability. Your request has been logged and will be processed "
            "once services are restored."
        ),
    }

    async def complete(
        self,
        model: str,
        messages: List[ChatMessage],
        max_tokens: int,
        temperature: float,
    ) -> Dict[str, Any]:
        last_msg = messages[-1].content.lower() if messages else ""
        if any(w in last_msg for w in ["hello", "hi", "hey", "greet"]):
            content = self.FALLBACK_RESPONSES["greeting"]
        elif any(w in last_msg for w in ["error", "fail", "problem", "issue"]):
            content = self.FALLBACK_RESPONSES["error"]
        else:
            content = self.FALLBACK_RESPONSES["default"]
        return {"content": content, "done": True, "model": "offline-fallback"}


# ---------------------------------------------------------------------------
# AI Gateway Router (AdaptiveRotation)
# ---------------------------------------------------------------------------


class AIGatewayRouter:
    """Routes AI requests through provider priority chain with caching and budget tracking.

    Provider rotation order (LimitMonitor x8 AdaptiveRotation):
      ollama → groq → cerebras → openrouter → huggingface → together → deepseek → offline
    """

    def __init__(self, db: AIDatabase):
        self.db = db
        self.cache = LRUCache(max_size=LRU_CACHE_MAX_SIZE)
        self._smart_cache = _SMART_CACHE
        self.ollama = OllamaClient()
        self.groq = GroqClient()
        self.cerebras = CerebrasClient()
        self.openrouter = OpenRouterClient()
        self.huggingface = HuggingFaceClient()
        self.together = TogetherClient()
        self.deepseek = DeepSeekClient()
        self.offline = OfflineClient()
        # Provider priority: local first → fast cloud free tiers → offline fallback
        self.providers = [
            (ProviderName.ollama, self.ollama),
            (ProviderName.groq, self.groq),
            (ProviderName.cerebras, self.cerebras),
            (ProviderName.openrouter, self.openrouter),
            (ProviderName.huggingface, self.huggingface),
            (ProviderName.together, self.together),
            (ProviderName.deepseek, self.deepseek),
            (ProviderName.offline, self.offline),
        ]

    def reset_daily_counts_if_needed(self) -> None:
        """Placeholder for per-provider daily request-count reset.

        No per-provider counters are tracked yet (the providers dashboard in
        router.py currently reports static placeholder utilisation); this
        exists so the background reset loop in main.py has something to call
        once that tracking is implemented.
        """

    def _make_cache_key(
        self,
        model: str,
        messages: List[ChatMessage],
        max_tokens: int,
        temperature: float,
        tenant_id: Optional[str],
    ) -> str:
        msg_str = "|".join(f"{m.role}:{m.content}" for m in messages)
        raw = f"{tenant_id or 'default'}:{model}:{msg_str}:{max_tokens}:{temperature}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    async def route(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        request_id = f"req-{uuid.uuid4().hex[:12]}"
        tenant_id = request.tenant_id or "default"
        start_time = time.time()

        # Check token budget
        estimated_tokens = request.max_tokens + sum(
            len(m.content.split()) for m in request.messages
        )
        if not self.db.check_budget(tenant_id, estimated_tokens):
            raise HTTPException(
                429,
                "Token budget exceeded for today. Try again tomorrow or contact admin.",
            )

        # Check smart semantic cache first (near-duplicate detection), then basic LRU
        prompt_text = " ".join(m.content for m in request.messages)
        cache_tags = {"tenant": tenant_id, "model": request.model}
        if self._smart_cache is not None:
            smart_hit = self._smart_cache.get(prompt_text, tags=cache_tags)
            if smart_hit is not None:
                smart_hit.provider = "smart-cache"
                return smart_hit

        cache_key = self._make_cache_key(
            request.model,
            request.messages,
            request.max_tokens,
            request.temperature,
            tenant_id,
        )
        cached = self.cache.get(cache_key)
        if cached:
            cached.provider = "cache"
            return cached

        # Try providers in priority order
        last_error = None
        for provider_name, provider in self.providers:
            try:
                result = await provider.complete(
                    request.model,
                    request.messages,
                    request.max_tokens,
                    request.temperature,
                )
                if result is None:
                    continue

                # Normalize response
                content = ""
                if isinstance(result, dict):
                    if "message" in result:
                        content = result["message"].get("content", "")
                    elif "choices" in result and result["choices"]:
                        content = result["choices"][0].get("message", {}).get("content", "")
                    elif "content" in result:
                        content = result["content"]
                    elif "generated_text" in result:
                        content = result["generated_text"]

                # Estimate tokens (rough: 1 token ≈ 4 chars)
                prompt_tokens = sum(len(m.content) // 4 for m in request.messages)
                completion_tokens = max(1, len(content) // 4)

                response = ChatCompletionResponse(
                    model=request.model,
                    choices=[
                        ChatCompletionChoice(
                            message=ChatMessage(role="assistant", content=content),
                            finish_reason="stop",
                        )
                    ],
                    usage=ChatCompletionUsage(
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=prompt_tokens + completion_tokens,
                    ),
                    provider=provider_name.value,
                )

                # Record usage
                latency_ms = int((time.time() - start_time) * 1000)
                self.db.record_usage(tenant_id, completion_tokens)
                self.db.log_request(
                    request_id=request_id,
                    tenant_id=tenant_id,
                    model=request.model,
                    provider=provider_name.value,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    latency_ms=latency_ms,
                    success=True,
                )

                # Cache successful responses (both basic LRU and smart semantic cache)
                self.cache.put(cache_key, response)
                if self._smart_cache is not None:
                    self._smart_cache.put(prompt_text, response, tags=cache_tags)

                # Feed outcome to genetic optimizer for evolutionary provider ranking
                try:
                    from src.ai_gateway.limit_monitor import monitor as _lm

                    _lm.record_provider_outcome(
                        provider_name.value, success=True, latency_ms=float(latency_ms)
                    )
                except Exception:
                    pass

                return response

            except HTTPException:
                raise
            except Exception as e:
                last_error = str(e)
                logger.warning(  # codeql[py/cleartext-logging]
                    "Provider %s failed: %s",
                    provider_name.value,
                    sanitize_for_log(e),
                )
                try:
                    from src.adaptive.provider_rotator import get_provider_rotator

                    rate_limited = "429" in str(e) or "rate" in str(e).lower()
                    get_provider_rotator().record_failure(
                        provider_name.value,
                        rate_limited=rate_limited,
                    )
                except Exception:
                    pass
                try:
                    from src.ai_gateway.limit_monitor import monitor as _lm

                    _lm.record_provider_outcome(provider_name.value, success=False, latency_ms=0.0)
                except Exception:
                    pass
                continue

        # All providers failed — use offline as last resort
        result = await self.offline.complete(
            request.model, request.messages, request.max_tokens, request.temperature
        )
        content = result.get("content", "")
        latency_ms = int((time.time() - start_time) * 1000)
        self.db.log_request(
            request_id=request_id,
            tenant_id=tenant_id,
            model=request.model,
            provider="offline",
            prompt_tokens=0,
            completion_tokens=len(content) // 4,
            latency_ms=latency_ms,
            success=False,
            error=last_error,
        )
        return ChatCompletionResponse(
            model=request.model,
            choices=[
                ChatCompletionChoice(
                    message=ChatMessage(role="assistant", content=content),
                    finish_reason="stop",
                )
            ],
            usage=ChatCompletionUsage(total_tokens=len(content) // 4),
            provider="offline",
        )
