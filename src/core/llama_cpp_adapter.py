"""
llama.cpp HTTP Adapter — direct GGUF inference for Luminous.

Connects to a running llama.cpp server (./main --server -m model.gguf).
More memory-efficient than Ollama, supports:
  - Streaming completions (SSE)
  - Slot-based KV cache (--slots N)
  - Q4_K_M/Q5_K_M quantization
  - Context lengths up to 4096+ (model-dependent)

Default: http://localhost:8080  (llama.cpp default HTTP port)

Zero-cost: llama.cpp is MIT-licensed, free, no API key needed.

Install:
    git clone https://github.com/ggerganov/llama.cpp && cd llama.cpp && make
    ./main -m path/to/model.Q4_K_M.gguf --server -c 2048 -t 8 -ngl 0

Model recommendations (4-8GB RAM, CPU-only):
    - mistral-7b-instruct-v0.2.Q4_K_M.gguf  (~4.4GB)  — best quality/speed
    - llama-3.2-3b-instruct.Q5_K_M.gguf     (~2.2GB)  — faster, less quality
    - phi-3-mini-128k-instruct.Q4_K_M.gguf  (~2.2GB)  — long context
"""

from __future__ import annotations

import logging
import os
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

logger = logging.getLogger("tranc3.core.llama_cpp")

_DEFAULT_URL = os.getenv("LLAMA_CPP_URL", "http://localhost:8080")
_REQUEST_TIMEOUT = 120.0


def _messages_to_prompt_llama3(messages: List[Dict]) -> str:
    """Convert chat messages to Llama-3 instruct format."""
    parts = ["<|begin_of_text|>"]
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        parts.append(f"<|start_header_id|>{role}<|end_header_id|>\n\n{content}<|eot_id|>")
    parts.append("<|start_header_id|>assistant<|end_header_id|>\n\n")
    return "".join(parts)


def _messages_to_prompt_mistral(messages: List[Dict]) -> str:
    """Convert chat messages to Mistral instruct format."""
    parts = []
    system = next((m["content"] for m in messages if m.get("role") == "system"), "")
    non_system = [m for m in messages if m.get("role") != "system"]

    for i, msg in enumerate(non_system):
        role = msg.get("role")
        content = msg.get("content", "")
        if role == "user":
            prefix = f"[INST] {system}\n\n" if i == 0 and system else "[INST] "
            parts.append(f"{prefix}{content} [/INST] ")
        elif role == "assistant":
            parts.append(f"{content}</s>")
    return "".join(parts)


async def is_available(base_url: str = _DEFAULT_URL) -> bool:
    """Check if the llama.cpp HTTP server is reachable."""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{base_url}/health")
            return resp.status_code == 200
    except Exception:
        return False


async def get_model_info(base_url: str = _DEFAULT_URL) -> Optional[Dict]:
    """Get information about the loaded model."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base_url}/props")
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass
    return None


async def generate(
    messages: List[Dict],
    base_url: str = _DEFAULT_URL,
    temperature: float = 0.7,
    max_tokens: int = 512,
    top_p: float = 0.95,
    stop: Optional[List[str]] = None,
    prompt_format: str = "auto",
) -> Dict[str, Any]:
    """
    Generate a completion from llama.cpp HTTP server (non-streaming).

    Returns an OpenAI-compatible response dict.
    """
    prompt = _messages_to_prompt_mistral(messages)
    if prompt_format == "llama3":
        prompt = _messages_to_prompt_llama3(messages)

    payload: Dict[str, Any] = {
        "prompt": prompt,
        "n_predict": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
        "stream": False,
        "stop": stop or ["</s>", "[INST]", "<|eot_id|>"],
        "cache_prompt": True,  # Enable KV cache reuse
    }

    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            resp = await client.post(f"{base_url}/completion", json=payload)
            resp.raise_for_status()
            data = resp.json()

            content = data.get("content", "")
            tokens_predicted = data.get("tokens_predicted", 0)
            tokens_evaluated = data.get("tokens_evaluated", 0)

            return {
                "id": "llamacpp-1",
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": tokens_evaluated,
                    "completion_tokens": tokens_predicted,
                    "total_tokens": tokens_evaluated + tokens_predicted,
                },
                "provider": "llama_cpp",
            }

    except httpx.TimeoutException:
        return {"error": "llama.cpp request timed out", "provider": "llama_cpp"}
    except Exception as exc:
        logger.warning("llama.cpp generate error: %s", exc)
        return {"error": str(exc), "provider": "llama_cpp"}


async def stream_generate(
    messages: List[Dict],
    base_url: str = _DEFAULT_URL,
    temperature: float = 0.7,
    max_tokens: int = 512,
    prompt_format: str = "auto",
) -> AsyncIterator[str]:
    """
    Stream tokens from llama.cpp HTTP server (SSE).
    Yields raw token strings.
    """
    import json as _json

    prompt = _messages_to_prompt_mistral(messages)
    if prompt_format == "llama3":
        prompt = _messages_to_prompt_llama3(messages)

    payload = {
        "prompt": prompt,
        "n_predict": max_tokens,
        "temperature": temperature,
        "stream": True,
        "cache_prompt": True,
        "stop": ["</s>", "[INST]", "<|eot_id|>"],
    }

    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            async with client.stream("POST", f"{base_url}/completion", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = _json.loads(data_str)
                        token = chunk.get("content", "")
                        if token:
                            yield token
                        if chunk.get("stop"):
                            break
                    except _json.JSONDecodeError:
                        continue
    except Exception as exc:
        logger.warning("llama.cpp stream error: %s", exc)
        yield ""


async def list_slots(base_url: str = _DEFAULT_URL) -> List[Dict]:
    """Return KV cache slot status (requires llama.cpp --slots flag)."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base_url}/slots")
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass
    return []
