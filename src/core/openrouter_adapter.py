# src/core/openrouter_adapter.py
# OpenRouter free-tier adapter — accesses free LLMs via OpenRouter's API.
#
# OpenRouter provides free access to several capable models:
#   meta-llama/llama-3.2-1b-instruct:free
#   meta-llama/llama-3.2-3b-instruct:free
#   google/gemma-3-1b-it:free
#   mistralai/mistral-7b-instruct:free
#   microsoft/phi-3-mini-128k-instruct:free
#   nousresearch/hermes-3-llama-3.1-405b:free (occasionally available)
#
# No API key is required for truly-free models (rate-limited but free).
# Set OPENROUTER_API_KEY in .env for higher rate limits.
#
# Docs: https://openrouter.ai/docs

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

_OPENROUTER_BASE = "https://openrouter.ai/api/v1"
_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# Free models — ordered by capability/speed trade-off.
# The :free suffix means OpenRouter routes to a free endpoint.
FREE_MODELS: List[str] = [
    "meta-llama/llama-3.2-3b-instruct:free",
    "meta-llama/llama-3.2-1b-instruct:free",
    "google/gemma-3-1b-it:free",
    "microsoft/phi-3-mini-128k-instruct:free",
    "mistralai/mistral-7b-instruct:free",
]

_DEFAULT_FREE_MODEL = os.getenv("OPENROUTER_MODEL", FREE_MODELS[0])
_TIMEOUT = 60.0

# HTTP/Referer headers requested by OpenRouter (no auth required for :free models)
_SITE_URL = os.getenv("OPENROUTER_SITE_URL", "https://trancendos.com")
_APP_NAME = "Tranc3"


def _headers() -> Dict[str, str]:
    h = {
        "Content-Type": "application/json",
        "HTTP-Referer": _SITE_URL,
        "X-Title": _APP_NAME,
    }
    if _API_KEY:
        h["Authorization"] = f"Bearer {_API_KEY}"
    return h


async def generate(
    prompt: str,
    model: Optional[str] = None,
    system_prompt: Optional[str] = None,
    max_tokens: int = 512,
    temperature: float = 0.8,
    top_p: float = 0.9,
) -> Dict[str, Any]:
    """
    Generate a completion via OpenRouter.

    Tries the preferred model first; falls back through FREE_MODELS on 429/5xx.
    Returns {} on complete failure so the caller can try the next tier.
    """
    chosen = model or _DEFAULT_FREE_MODEL
    candidates = [chosen] + [m for m in FREE_MODELS if m != chosen]

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    for candidate_model in candidates:
        payload = {
            "model": candidate_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        }
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    f"{_OPENROUTER_BASE}/chat/completions",
                    json=payload,
                    headers=_headers(),
                )
                if resp.status_code in (429, 503) and candidate_model != candidates[-1]:
                    logger.debug("openrouter rate-limited on %s, trying next", candidate_model)
                    continue
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                logger.info(
                    "openrouter.generate model=%s tokens=%s",
                    candidate_model,
                    usage.get("total_tokens", 0),
                )
                return {
                    "response": content,
                    "model": candidate_model,
                    "tokens": usage.get("total_tokens", 0),
                    "trained": True,
                    "backend": "openrouter",
                }
        except httpx.ConnectError:
            logger.debug("openrouter: network unreachable")
            return {}
        except Exception as exc:
            logger.warning("openrouter.generate error model=%s: %s", candidate_model, exc)
            continue

    return {}


def list_free_models() -> List[str]:
    """Return the current list of known free OpenRouter models."""
    return list(FREE_MODELS)
