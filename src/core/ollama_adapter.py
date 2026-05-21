# src/core/ollama_adapter.py
# Ollama adapter — auto-detects a locally running Ollama instance and uses it
# as a real LLM backend for Tranc3.  Zero cost, fully self-owned inference.
#
# Ollama runs at http://localhost:11434 by default and exposes an
# OpenAI-compatible API, so this adapter is a thin httpx wrapper.
#
# To install Ollama (free):
#   Linux:   curl -fsSL https://ollama.com/install.sh | sh
#   macOS:   brew install ollama
#   Windows: winget install Ollama.Ollama
#
# Then pull a model:
#   ollama pull llama3.2:1b    # 1B params, ~800MB, runs on CPU
#   ollama pull qwen2.5:0.5b   # 0.5B params, ~400MB, fastest
#   ollama pull phi4-mini       # 3.8B, excellent quality/size ratio

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

_OLLAMA_BASE = os.getenv("OLLAMA_URL", "http://localhost:11434")
_DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:1b")

# Timeout for availability probe (fast — don't block startup)
_PROBE_TIMEOUT = 1.5
# Timeout for actual generation
_GEN_TIMEOUT = 120.0


async def is_available() -> bool:
    """Return True if Ollama is reachable at OLLAMA_URL."""
    try:
        async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT) as client:
            resp = await client.get(f"{_OLLAMA_BASE}/api/tags")
            return resp.status_code == 200
    except Exception:
        return False


async def list_models() -> List[str]:
    """Return names of models available in this Ollama instance."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{_OLLAMA_BASE}/api/tags")
            resp.raise_for_status()
            data = resp.json()
            return [m["name"] for m in data.get("models", [])]
    except Exception as exc:
        logger.debug("ollama.list_models failed: %s", exc)
        return []


async def generate(
    prompt: str,
    model: Optional[str] = None,
    system_prompt: Optional[str] = None,
    max_tokens: int = 512,
    temperature: float = 0.8,
    top_p: float = 0.9,
) -> Dict[str, Any]:
    """
    Generate a completion via Ollama's OpenAI-compatible /v1/chat/completions endpoint.

    Returns a dict with keys: response, model, tokens, trained, backend.
    Falls back to None (caller should try next tier) if Ollama is unavailable.
    """
    chosen_model = model or _DEFAULT_MODEL
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": chosen_model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=_GEN_TIMEOUT) as client:
            resp = await client.post(
                f"{_OLLAMA_BASE}/v1/chat/completions",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            logger.debug("ollama.generate model=%s tokens=%s", chosen_model, usage.get("total_tokens", 0))
            return {
                "response": content,
                "model": chosen_model,
                "tokens": usage.get("total_tokens", 0),
                "trained": True,
                "backend": "ollama",
            }
    except httpx.ConnectError:
        logger.debug("ollama.generate: not reachable at %s", _OLLAMA_BASE)
        return {}
    except Exception as exc:
        logger.warning("ollama.generate error model=%s: %s", chosen_model, exc)
        return {}


async def embed(text: str, model: Optional[str] = None) -> List[float]:
    """
    Generate an embedding via Ollama's /api/embeddings endpoint.
    Returns [] if Ollama is unavailable.
    """
    chosen_model = model or os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{_OLLAMA_BASE}/api/embeddings",
                json={"model": chosen_model, "prompt": text},
            )
            resp.raise_for_status()
            return resp.json().get("embedding", [])
    except Exception as exc:
        logger.debug("ollama.embed failed: %s", exc)
        return []
