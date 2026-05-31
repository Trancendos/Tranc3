"""
Langfuse AI observability integration — The Observatory.

Thin, optional wrapper around the Langfuse Python SDK.  All public
functions are no-ops if:
  - the ``langfuse`` package is not installed, or
  - LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY env vars are absent.

Usage::

    from src.observability.langfuse_integration import trace_inference

    await trace_inference(
        model="llama3:8b",
        prompt="Hello",
        response="Hi there",
        latency_ms=142.3,
        tokens_used=12,
    )

The module is designed to be safe under concurrent async access.  It
initialises a single global ``Langfuse`` client on first use behind a
threading lock, then reuses it for all subsequent calls.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional import
# ---------------------------------------------------------------------------

try:
    import langfuse as _langfuse_module  # type: ignore[import]

    _LANGFUSE_AVAILABLE = True
except ImportError:
    _LANGFUSE_AVAILABLE = False
    _langfuse_module = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Lazy singleton client
# ---------------------------------------------------------------------------

_client_lock = threading.Lock()
_client: Optional[Any] = None  # langfuse.Langfuse | None
_client_init_attempted = False


def _get_client() -> Optional[Any]:
    """Return the shared Langfuse client, or None if unavailable."""
    global _client, _client_init_attempted  # noqa: PLW0603

    if not _LANGFUSE_AVAILABLE:
        return None

    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY", "")

    if not public_key or not secret_key:
        return None

    # Double-checked locking pattern
    if _client is not None:
        return _client

    with _client_lock:
        if _client is not None:
            return _client
        if _client_init_attempted:
            # Previous attempt failed; don't retry on every call
            return None

        _client_init_attempted = True
        try:
            host = os.environ.get("LANGFUSE_HOST", "http://localhost:3002")
            _client = _langfuse_module.Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                host=host,
            )
            log.info("Langfuse client initialised (host=%s)", host)
        except Exception as exc:  # noqa: BLE001
            log.warning("Langfuse client init failed (observability disabled): %s", exc)
            _client = None

    return _client


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def trace_inference(
    *,
    model: str,
    prompt: str,
    response: str,
    latency_ms: float,
    tokens_used: int,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    """Record a single LLM inference as a Langfuse trace + generation.

    All parameters are keyword-only.  The call is a no-op when Langfuse
    is not configured; it never raises.

    Args:
        model: Model identifier, e.g. ``"llama3:8b"`` or ``"gpt-4o"``.
        prompt: The full prompt text sent to the model.
        response: The model's generated output.
        latency_ms: End-to-end inference latency in milliseconds.
        tokens_used: Total tokens consumed (prompt + completion).
        user_id: Optional opaque user identifier for per-user analytics.
        session_id: Optional session/conversation identifier.
        metadata: Optional free-form dict with extra context.
    """
    client = _get_client()
    if client is None:
        return

    try:
        trace = client.trace(
            name="inference",
            user_id=user_id,
            session_id=session_id,
            metadata=metadata or {},
        )
        trace.generation(
            name="llm-call",
            model=model,
            input=prompt,
            output=response,
            usage={
                "total_tokens": tokens_used,
            },
            metadata={
                "latency_ms": latency_ms,
                **(metadata or {}),
            },
        )
    except Exception as exc:  # noqa: BLE001
        # Observability must never crash the inference path
        log.debug("Langfuse trace_inference failed (ignored): %s", exc)


async def trace_inference_async(
    *,
    model: str,
    prompt: str,
    response: str,
    latency_ms: float,
    tokens_used: int,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    """Async-compatible shim for ``trace_inference``.

    The Langfuse Python SDK is synchronous; this wrapper runs the call
    in the same thread without blocking the event loop for more than a
    few microseconds (the SDK queues internally and flushes via a
    background thread, so the call returns immediately).
    """
    trace_inference(
        model=model,
        prompt=prompt,
        response=response,
        latency_ms=latency_ms,
        tokens_used=tokens_used,
        user_id=user_id,
        session_id=session_id,
        metadata=metadata,
    )


def flush() -> None:
    """Flush any pending traces to Langfuse.

    Call this during graceful shutdown to ensure all buffered events
    are delivered before the process exits.  No-op if unavailable.
    """
    client = _get_client()
    if client is None:
        return
    try:
        client.flush()
    except Exception as exc:  # noqa: BLE001
        log.debug("Langfuse flush failed (ignored): %s", exc)
