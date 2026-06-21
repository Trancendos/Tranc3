"""Cloudflare Workers AI provider — 10,000 neurons/day free tier.

Uses the REST API (no SDK needed). Requires CF_ACCOUNT_ID + CF_AI_API_TOKEN.

Free tier: 10,000 "neurons" (inference units) per day.
Models: Llama 3, Mistral, Phi-2, Gemma, CodeLlama, Whisper (STT), SDXL (image).
Docs: developers.cloudflare.com/workers-ai/models/

Honest caveat: 10K neurons/day is light — roughly 1,000 short chat turns.
Good as a rotation tier but not primary for high-traffic use.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger("tranc3.ai_gateway.providers.cloudflare_ai")

_ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID", "")
_API_TOKEN = os.getenv("CF_AI_API_TOKEN", "")
_DEFAULT_MODEL = os.getenv("CF_AI_DEFAULT_MODEL", "@cf/meta/llama-3.1-8b-instruct")

_BASE_URL = f"https://api.cloudflare.com/client/v4/accounts/{_ACCOUNT_ID}/ai/run"

# Free models available on Workers AI (as of 2026-06)
FREE_MODELS = [
    "@cf/meta/llama-3.1-8b-instruct",
    "@cf/meta/llama-3.2-3b-instruct",
    "@cf/mistral/mistral-7b-instruct-v0.1",
    "@cf/google/gemma-2b-it-lora",
    "@cf/microsoft/phi-2",
    "@cf/qwen/qwen1.5-7b-chat-awq",
    "@cf/deepseek-ai/deepseek-r1-distill-qwen-32b",
]


def is_available() -> bool:
    return bool(_ACCOUNT_ID and _API_TOKEN)


def chat(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    **kwargs: Any,
) -> str:
    if not is_available():
        raise RuntimeError("Cloudflare AI: CF_ACCOUNT_ID and CF_AI_API_TOKEN required")
    model = model or _DEFAULT_MODEL
    payload = json.dumps({
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode()
    req = urllib.request.Request(
        f"{_BASE_URL}/{model}",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_API_TOKEN}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:  # nosec B310 — CF HTTPS endpoint
        data = json.loads(resp.read())
    if not data.get("success"):
        raise RuntimeError(f"Cloudflare AI error: {data.get('errors')}")
    result = data["result"]
    if isinstance(result, dict):
        return result.get("response", "")
    return str(result)


async def achat(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    **kwargs: Any,
) -> str:
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: chat(messages, model, **kwargs))
