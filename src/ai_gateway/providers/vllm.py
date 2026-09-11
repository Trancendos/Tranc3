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

from src.utils.url_guard import is_http_url

logger = logging.getLogger("tranc3.ai_gateway.providers.vllm")

# VLLM_BASE_URL is operator-supplied, so it selects the scheme and therefore which
# urllib handler runs.
#
# An earlier revision validated it once at import and annotated the three urlopen
# calls "scheme validated at import". That was false twice over: nothing in the
# repository imports this module, so the check never executed -- and had it
# executed, a malformed value would have raised during import of an *optional*
# zero-cost provider, taking down startup for a component whose every other path
# degrades quietly. cubic caught both on PR #1207.
#
# The check now runs where the URL is used. `_base()` returns None for anything
# that is not http/https, and each caller degrades the way it already degrades
# when the service is simply down.
_VLLM_BASE = os.getenv("VLLM_BASE_URL", "http://localhost:8090/v1")
_DEFAULT_MODEL = os.getenv("VLLM_DEFAULT_MODEL", "meta-llama/Llama-3.2-3B-Instruct")


def _base() -> Optional[str]:
    """The configured base URL, or None if its scheme is not http/https."""
    if not is_http_url(_VLLM_BASE):
        logger.warning("vllm: refusing non-http(s) VLLM_BASE_URL %r", _VLLM_BASE)
        return None
    return _VLLM_BASE


def is_available() -> bool:
    base = _base()
    if base is None:
        return False
    try:
        req = urllib.request.Request(f"{base}/models", method="GET")
        urllib.request.urlopen(req, timeout=2)  # nosec B310 — scheme checked by _base()
        return True
    except Exception:
        return False


def list_models() -> List[str]:
    base = _base()
    if base is None:
        return [_DEFAULT_MODEL]
    try:
        req = urllib.request.Request(f"{base}/models", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:  # nosec B310 — scheme checked by _base()
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
    base = _base()
    if base is None:
        raise RuntimeError(
            f"VLLM_BASE_URL has a non-http(s) scheme: {_VLLM_BASE!r}. "
            "Raising here rather than returning a stub, because chat() has no "
            "degraded answer that is not a lie about the model's output."
        )
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
        f"{base}/chat/completions",
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
