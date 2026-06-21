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

logger = logging.getLogger("tranc3.ai_gateway.providers.llamacpp")

_BASE = os.getenv("LLAMACPP_BASE_URL", "http://localhost:8091")
_DEFAULT_MODEL = os.getenv("LLAMACPP_MODEL", "local")


def is_available() -> bool:
    try:
        req = urllib.request.Request(f"{_BASE}/health", method="GET")
        urllib.request.urlopen(req, timeout=2)  # nosec B310
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
    payload = json.dumps({
        "messages": messages,
        "temperature": temperature,
        "n_predict": max_tokens,
        "stream": False,
    }).encode()
    req = urllib.request.Request(
        f"{_BASE}/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:  # nosec B310
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
