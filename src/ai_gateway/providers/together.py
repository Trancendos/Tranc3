"""Together AI provider — open-source model hosting.

HONEST COST NOTE: Together AI is NOT permanently free.
New accounts receive $5 trial credit (enough for ~50M tokens at cheapest rates).
After that, cheapest models are ~$0.1/M tokens (e.g. Llama-3.2-3B).
Included here as a near-zero-cost tier, not as a truly free provider.
The system treats it as CHEAP tier and only routes here when free tiers are exhausted.

API is OpenAI-compatible. Requires TOGETHER_API_KEY.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger("tranc3.ai_gateway.providers.together")

_API_KEY = os.getenv("TOGETHER_API_KEY", "")
_BASE = "https://api.together.xyz/v1"
_DEFAULT_MODEL = os.getenv("TOGETHER_DEFAULT_MODEL", "meta-llama/Llama-3.2-3B-Instruct-Turbo")

# Cheapest models (~$0.06-0.1/M tokens)
CHEAP_MODELS = [
    "meta-llama/Llama-3.2-3B-Instruct-Turbo",
    "meta-llama/Llama-3.2-1B-Instruct-Turbo",
    "google/gemma-2-9b-it",
    "mistralai/Mistral-7B-Instruct-v0.3",
    "Qwen/Qwen2.5-7B-Instruct-Turbo",
]


def is_available() -> bool:
    return bool(_API_KEY)


def chat(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    **kwargs: Any,
) -> str:
    if not is_available():
        raise RuntimeError("Together AI: TOGETHER_API_KEY required")
    model = model or _DEFAULT_MODEL
    payload = json.dumps(
        {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
    ).encode()
    req = urllib.request.Request(
        f"{_BASE}/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_API_KEY}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:  # nosec B310 — HTTPS
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
