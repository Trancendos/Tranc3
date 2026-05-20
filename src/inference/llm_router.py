"""
src/inference/llm_router.py
Multi-provider LLM router — zero-cost model.

Priority chain (all free):
  1. Tranc3Engine  — local weights (if trained, MODEL_PATH set)
  2. Ollama        — local model server (OLLAMA_URL, default localhost:11434)
  3. OpenRouter    — free :free suffix models (OPENROUTER_API_KEY optional)
  4. HuggingFace   — Inference API free tier (HF_API_KEY optional)
  5. Groq          — free tier 6k RPM (GROQ_API_KEY optional)
  6. Stub          — honest error telling user what env vars to set

Each provider is tried in sequence; on failure the next is attempted.
All providers implement the same async interface: generate(prompt) → str.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

logger = logging.getLogger("tranc3.inference.router")

_TIMEOUT = httpx.Timeout(60.0, connect=5.0)


# ---------------------------------------------------------------------------
# Provider enum + config
# ---------------------------------------------------------------------------

class Provider(str, Enum):
    TRANC3   = "tranc3"
    OLLAMA   = "ollama"
    OPENROUTER = "openrouter"
    HUGGINGFACE = "huggingface"
    GROQ     = "groq"
    STUB     = "stub"


@dataclass
class ProviderConfig:
    provider: Provider
    enabled: bool = True
    model: str = ""
    base_url: str = ""
    api_key: str = ""
    # runtime stats
    total_calls: int = field(default=0, repr=False)
    failures: int = field(default=0, repr=False)
    last_error: str = field(default="", repr=False)


@dataclass
class LLMRequest:
    prompt: str
    system: str = "You are a helpful assistant."
    max_tokens: int = 1024
    temperature: float = 0.7
    stream: bool = False


@dataclass
class LLMResponse:
    text: str
    provider: Provider
    model: str
    latency_ms: float
    tokens_used: int = 0
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Individual provider implementations
# ---------------------------------------------------------------------------

async def _try_tranc3(cfg: ProviderConfig, req: LLMRequest, client: httpx.AsyncClient) -> str:
    """Call the local Tranc3Engine via the nanoservices proxy."""
    url = os.getenv("TRANC3_ENGINE_URL", "http://localhost:8000/v1/chat")
    resp = await client.post(url, json={
        "messages": [
            {"role": "system", "content": req.system},
            {"role": "user", "content": req.prompt},
        ],
        "max_tokens": req.max_tokens,
        "temperature": req.temperature,
    }, timeout=_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    return data.get("response") or data["choices"][0]["message"]["content"]


async def _try_ollama(cfg: ProviderConfig, req: LLMRequest, client: httpx.AsyncClient) -> str:
    base = os.getenv("OLLAMA_URL", "http://localhost:11434")
    model = os.getenv("OLLAMA_MODEL", "llama3.2:1b")
    resp = await client.post(f"{base}/api/chat", json={
        "model": model,
        "messages": [
            {"role": "system", "content": req.system},
            {"role": "user", "content": req.prompt},
        ],
        "stream": False,
        "options": {"num_predict": req.max_tokens, "temperature": req.temperature},
    }, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()["message"]["content"]


async def _try_openrouter(cfg: ProviderConfig, req: LLMRequest, client: httpx.AsyncClient) -> str:
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not set")
    model = os.getenv("OPENROUTER_MODEL", "mistralai/mistral-7b-instruct:free")
    resp = await client.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://trancendos.com",
            "X-Title": "Tranc3",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": req.system},
                {"role": "user", "content": req.prompt},
            ],
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


async def _try_huggingface(cfg: ProviderConfig, req: LLMRequest, client: httpx.AsyncClient) -> str:
    api_key = os.getenv("HF_API_KEY", "")
    if not api_key:
        raise ValueError("HF_API_KEY not set")
    model = os.getenv("HF_MODEL", "mistralai/Mistral-7B-Instruct-v0.3")
    full_prompt = f"<s>[INST] {req.system}\n\n{req.prompt} [/INST]"
    resp = await client.post(
        f"https://api-inference.huggingface.co/models/{model}",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "inputs": full_prompt,
            "parameters": {
                "max_new_tokens": req.max_tokens,
                "temperature": req.temperature,
                "return_full_text": False,
            },
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, list):
        return data[0].get("generated_text", "")
    return str(data)


async def _try_groq(cfg: ProviderConfig, req: LLMRequest, client: httpx.AsyncClient) -> str:
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set")
    model = os.getenv("GROQ_MODEL", "llama3-8b-8192")  # free tier model
    resp = await client.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": req.system},
                {"role": "user", "content": req.prompt},
            ],
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _stub_response(req: LLMRequest) -> str:
    missing = []
    for var, provider in [
        ("OLLAMA_URL", "Ollama (free local)"),
        ("OPENROUTER_API_KEY", "OpenRouter (free tier)"),
        ("HF_API_KEY", "HuggingFace (free tier)"),
        ("GROQ_API_KEY", "Groq (free tier, 6k RPM)"),
        ("MODEL_PATH", "Tranc3Engine (local weights)"),
    ]:
        if not os.getenv(var):
            missing.append(f"  {var} → {provider}")
    hint = "\n".join(missing) if missing else "  (all providers attempted and failed)"
    return (
        f"[Tranc3 — No inference provider available]\n"
        f"Set one of these env vars to enable AI responses:\n{hint}\n\n"
        f"Your prompt was: {req.prompt[:200]}"
    )


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

_PROVIDER_FNS = {
    Provider.TRANC3:      _try_tranc3,
    Provider.OLLAMA:      _try_ollama,
    Provider.OPENROUTER:  _try_openrouter,
    Provider.HUGGINGFACE: _try_huggingface,
    Provider.GROQ:        _try_groq,
}


class LLMRouter:
    """
    Tries each provider in sequence and returns the first successful response.
    All providers are zero-cost (local or free tier).
    """

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None
        self._stats: Dict[Provider, Dict[str, Any]] = {
            p: {"calls": 0, "failures": 0, "last_error": ""} for p in Provider
        }

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=_TIMEOUT)
        return self._client

    async def generate(self, req: LLMRequest) -> LLMResponse:
        client = self._get_client()
        priority: List[Provider] = [
            Provider.TRANC3,
            Provider.OLLAMA,
            Provider.OPENROUTER,
            Provider.HUGGINGFACE,
            Provider.GROQ,
        ]
        for provider in priority:
            fn = _PROVIDER_FNS.get(provider)
            if fn is None:
                continue
            t0 = time.monotonic()
            try:
                self._stats[provider]["calls"] += 1
                text = await fn(ProviderConfig(provider=provider), req, client)
                latency_ms = (time.monotonic() - t0) * 1000
                logger.info("LLMRouter: %s succeeded (%.0fms)", provider, latency_ms)
                return LLMResponse(
                    text=text,
                    provider=provider,
                    model=provider.value,
                    latency_ms=latency_ms,
                )
            except Exception as exc:
                latency_ms = (time.monotonic() - t0) * 1000
                self._stats[provider]["failures"] += 1
                self._stats[provider]["last_error"] = str(exc)
                logger.debug("LLMRouter: %s failed (%.0fms): %s", provider, latency_ms, exc)

        # All failed — honest stub
        return LLMResponse(
            text=_stub_response(req),
            provider=Provider.STUB,
            model="stub",
            latency_ms=0,
            error="All providers failed",
        )

    async def health(self) -> Dict[str, Any]:
        return {
            "providers": {
                p.value: {
                    "calls": s["calls"],
                    "failures": s["failures"],
                    "success_rate": (
                        round((s["calls"] - s["failures"]) / s["calls"] * 100, 1)
                        if s["calls"] > 0 else None
                    ),
                    "last_error": s["last_error"] or None,
                }
                for p, s in self._stats.items()
            }
        }

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# Module-level singleton
_router: Optional[LLMRouter] = None


def get_router() -> LLMRouter:
    global _router
    if _router is None:
        _router = LLMRouter()
    return _router
