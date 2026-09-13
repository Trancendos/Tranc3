"""llama.cpp server provider — lightweight CPU/GPU inference (MIT, 0-cost).

llama-server exposes an OpenAI-compatible API on port 8091 (default).
Extremely lightweight: runs on CPU, 4-bit quantised models fit in <4GB RAM.

Zero-cost: fully self-hosted, no API keys, no per-token billing.
Use case: lowest-resource fallback when Ollama is unavailable.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import Any, Dict, List, Optional

from src.utils.url_guard import is_http_url

logger = logging.getLogger("tranc3.ai_gateway.providers.llamacpp")

# Operator-supplied, so it selects the scheme -- see the note in vllm.py for why
# this is checked per call rather than once at import.
_BASE = os.getenv("LLAMACPP_BASE_URL", "http://localhost:8091")
_DEFAULT_MODEL = os.getenv("LLAMACPP_MODEL", "local")


def _base() -> Optional[str]:
    """The configured base URL, or None if its scheme is not http/https."""
    if not is_http_url(_BASE):
        logger.warning("llamacpp: refusing non-http(s) LLAMACPP_BASE_URL %r", _BASE)
        return None
    return _BASE


def is_available() -> bool:
    base = _base()
    if base is None:
        return False
    try:
        req = urllib.request.Request(f"{base}/health", method="GET")
        urllib.request.urlopen(req, timeout=2)  # nosec B310 — scheme checked by _base()
        return True
    except Exception:
        return False


def chat(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    **kwargs: Any,
) -> str:
    base = _base()
    if base is None:
        raise RuntimeError(
            f"LLAMACPP_BASE_URL has a non-http(s) scheme: {_BASE!r}. "
            "Raising rather than degrading: chat() has no honest stub answer."
        )
    payload = json.dumps(
        {
            "model": model or _DEFAULT_MODEL,
            "messages": messages,
            "temperature": temperature,
            "n_predict": max_tokens,
            "stream": False,
        }
    ).encode()
    req = urllib.request.Request(
        f"{base}/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:  # nosec B310 — scheme checked by _base()
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


async def achat(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    **kwargs: Any,
) -> str:
    import asyncio

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: chat(messages, model, **kwargs))
