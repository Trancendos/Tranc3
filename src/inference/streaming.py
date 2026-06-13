"""
Streaming inference — Server-Sent Events (SSE) token-by-token output.

Wraps Ollama, llama.cpp, and any provider that supports streaming.
Falls back to chunked simulation for providers that don't stream natively.

Usage in FastAPI:
    from src.inference.streaming import stream_completion

    @app.post("/v1/chat/completions/stream")
    async def chat_stream(request: ChatRequest):
        return StreamingResponse(
            stream_completion(request.messages, request.model),
            media_type="text/event-stream",
        )
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncIterator, Dict, List, Optional

import httpx

logger = logging.getLogger("tranc3.inference.streaming")

_OLLAMA_URL = "http://localhost:11434"
_LLAMA_CPP_URL = "http://localhost:8080"


async def _stream_ollama(
    messages: List[Dict],
    model: str = "llama3.2:1b",
    temperature: float = 0.7,
    max_tokens: int = 512,
) -> AsyncIterator[str]:
    """Stream tokens from Ollama via its native streaming chat API."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{_OLLAMA_URL}/api/chat",
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                        content = chunk.get("message", {}).get("content", "")
                        if content:
                            yield content
                        if chunk.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue
    except Exception as exc:
        logger.warning("Ollama streaming failed: %s — falling back to simulation", exc)


async def _stream_llama_cpp(
    prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 512,
) -> AsyncIterator[str]:
    """Stream tokens from llama.cpp HTTP server."""
    payload = {
        "prompt": prompt,
        "n_predict": max_tokens,
        "temperature": temperature,
        "stream": True,
        "stop": ["</s>", "[INST]"],
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{_LLAMA_CPP_URL}/completion",
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        token = chunk.get("content", "")
                        if token:
                            yield token
                        if chunk.get("stop"):
                            break
                    except json.JSONDecodeError:
                        continue
    except Exception as exc:
        logger.warning("llama.cpp streaming failed: %s", exc)


async def _simulate_stream(text: str, chunk_size: int = 4) -> AsyncIterator[str]:
    """Simulate streaming by chunking a complete response."""
    words = text.split(" ")
    for i in range(0, len(words), chunk_size):
        chunk = " ".join(words[i : i + chunk_size])
        if i + chunk_size < len(words):
            chunk += " "
        yield chunk
        await asyncio.sleep(0.02)


def _messages_to_prompt(messages: List[Dict]) -> str:
    """Convert chat messages to a single prompt string."""
    parts = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            parts.append(f"[INST] <<SYS>>\n{content}\n<</SYS>>\n\n")
        elif role == "user":
            parts.append(f"{content} [/INST] ")
        elif role == "assistant":
            parts.append(f"{content} </s><s>[INST] ")
    return "".join(parts)


async def stream_completion(
    messages: List[Dict],
    model: str = "llama3.2:1b",
    temperature: float = 0.7,
    max_tokens: int = 512,
    provider: Optional[str] = None,
) -> AsyncIterator[str]:
    """
    Unified streaming entry point. Tries Ollama first, then llama.cpp,
    then falls back to simulated streaming from a complete response.

    Yields raw token strings. Callers wrap these into SSE format.
    """
    # Try Ollama streaming
    if provider in (None, "ollama"):
        try:
            async with httpx.AsyncClient(timeout=3.0) as probe:
                await probe.get(f"{_OLLAMA_URL}/api/tags")
            # Ollama is up — stream from it
            async for token in _stream_ollama(messages, model, temperature, max_tokens):
                yield token
            return
        except Exception:
            pass

    # Try llama.cpp streaming
    if provider in (None, "llama_cpp"):
        try:
            async with httpx.AsyncClient(timeout=2.0) as probe:
                await probe.get(f"{_LLAMA_CPP_URL}/health")
            prompt = _messages_to_prompt(messages)
            async for token in _stream_llama_cpp(prompt, temperature, max_tokens):
                yield token
            return
        except Exception:
            pass

    # Fallback: get full response from ai_gateway, simulate streaming
    try:
        from src.ai_gateway.gateway import AIGateway

        gw = AIGateway()
        user_content = next(
            (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"),
            "",
        )
        result = await gw.route(user_content, metadata={"stream": True})
        text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not text:
            text = result.get("text", result.get("content", "No response available."))
        async for chunk in _simulate_stream(text):
            yield chunk
    except Exception as exc:
        logger.error("All streaming providers failed: %s", exc)
        yield "I'm currently operating in offline mode. Please check that Ollama is running."


def make_sse_event(data: str, event_type: str = "token") -> str:
    """Format a string as an SSE event."""
    return f"event: {event_type}\ndata: {json.dumps({'content': data})}\n\n"


def make_sse_done() -> str:
    """SSE stream terminator (OpenAI-compatible)."""
    return "data: [DONE]\n\n"


async def stream_sse(
    messages: List[Dict],
    model: str = "llama3.2:1b",
    temperature: float = 0.7,
    max_tokens: int = 512,
    provider: Optional[str] = None,
) -> AsyncIterator[str]:
    """
    Like stream_completion but wraps each token in SSE format.
    Suitable for direct use in FastAPI StreamingResponse.
    """
    async for token in stream_completion(messages, model, temperature, max_tokens, provider):
        yield make_sse_event(token)
    yield make_sse_done()
