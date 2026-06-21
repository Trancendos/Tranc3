"""vLLM provider — self-hosted high-throughput LLM serving (Apache 2.0, 0-cost).

vLLM exposes an OpenAI-compatible API. When running in Docker (see
docker-compose.production.yml), it listens on port 8090.

Zero-cost: fully self-hosted, no API keys, no per-token billing.
Throughput: PagedAttention gives 24x more throughput than naive HuggingFace.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger("tranc3.ai_gateway.providers.vllm")

_VLLM_BASE = os.getenv("VLLM_BASE_URL", "http://localhost:8090/v1")
_DEFAULT_MODEL = os.getenv("VLLM_DEFAULT_MODEL", "meta-llama/Llama-3.2-3B-Instruct")


def is_available() -> bool:
    try:
        req = urllib.request.Request(f"{_VLLM_BASE}/models", method="GET")
        urllib.request.urlopen(req, timeout=2)  # nosec B310 — configured host
        return True
    except Exception:
        return False


def list_models() -> List[str]:
    try:
        req = urllib.request.Request(f"{_VLLM_BASE}/models", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:  # nosec B310
            data = json.loads(resp.read())
            return [m["id"] for m in data.get("data", [])]
    except Exception:
        return [_DEFAULT_MODEL]


def chat(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    **kwargs: Any,
) -> str:
    model = model or _DEFAULT_MODEL
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode()
    req = urllib.request.Request(
        f"{_VLLM_BASE}/chat/completions",
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
