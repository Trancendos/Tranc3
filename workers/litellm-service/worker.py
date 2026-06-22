"""
Trancendos LiteLLM Service — Port 8049
=======================================
Bridges LiteLLM proxy to the Trancendos ecosystem. Implements the x10 free
provider chain with hard-stop limit monitoring and adaptive rotation.

Provider chain (priority order, zero-cost only):
  1. Ollama (unlimited local)
  2. Groq (14 400 req/day free)
  3. Gemini Flash (1 500 req/day free)
  4. Cerebras (30 RPM free)
  5. SambaNova (50 K tok/req free)
  6. GitHub Models (150 req/day free)
  7. Mistral (500 K tok/month free)
  8. OpenRouter (200 req/day free)
  9. HuggingFace (free inference API)
 10. DeepSeek (free tier)

Hard stops:
  - 80 % of daily/monthly limit → rotate to next provider
  - 95 % of limit → refuse request and log

Port: 8049
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
WORKER_PORT = int(os.getenv("PORT", "8049"))
WORKER_NAME = "litellm-service"
VERSION = "1.0.0"

LITELLM_URL = os.getenv("LITELLM_URL", "http://localhost:4000").rstrip("/")
LITELLM_MASTER_KEY = os.getenv("LITELLM_MASTER_KEY", "")

DB_PATH = Path(__file__).parent / "data" / "litellm_usage.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

STARTED_AT = datetime.now(timezone.utc)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)

_http_timeout = httpx.Timeout(60.0, connect=5.0)

# ---------------------------------------------------------------------------
# Provider limits registry (zero-cost)
# ---------------------------------------------------------------------------
PROVIDER_LIMITS: dict[str, dict[str, Any]] = {
    "ollama": {"daily": None, "monthly": None, "rpm": None},  # unlimited local
    "groq": {"daily": 14400, "monthly": None, "rpm": 30},
    "gemini_flash": {"daily": 1500, "monthly": None, "rpm": 15},
    "cerebras": {"daily": None, "monthly": None, "rpm": 30},
    "sambanova": {"daily": None, "monthly": None, "rpm": 10},
    "github_models": {"daily": 150, "monthly": None, "rpm": 10},
    "mistral": {"daily": None, "monthly": 500_000, "rpm": 5},
    "openrouter": {"daily": 200, "monthly": None, "rpm": 20},
    "huggingface": {"daily": None, "monthly": None, "rpm": 5},
    "deepseek": {"daily": None, "monthly": None, "rpm": 5},
}

PROVIDER_ORDER = list(PROVIDER_LIMITS.keys())

# ---------------------------------------------------------------------------
# SQLite usage store
# ---------------------------------------------------------------------------
_db_lock = threading.Lock()


@contextmanager
def _db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _init_db() -> None:
    with _db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS provider_usage (
                provider TEXT NOT NULL,
                period TEXT NOT NULL,  -- 'YYYY-MM-DD' for daily, 'YYYY-MM' for monthly
                period_type TEXT NOT NULL,  -- 'daily' | 'monthly'
                requests INTEGER DEFAULT 0,
                tokens INTEGER DEFAULT 0,
                PRIMARY KEY (provider, period, period_type)
            )
            """
        )


_init_db()


def _get_usage(provider: str) -> dict[str, int]:
    today = date.today().isoformat()
    month = date.today().strftime("%Y-%m")
    with _db() as conn:
        daily_row = conn.execute(
            "SELECT requests, tokens FROM provider_usage WHERE provider=? AND period=? AND period_type='daily'",
            (provider, today),
        ).fetchone()
        monthly_row = conn.execute(
            "SELECT requests, tokens FROM provider_usage WHERE provider=? AND period=? AND period_type='monthly'",
            (provider, month),
        ).fetchone()
    return {
        "daily_requests": daily_row["requests"] if daily_row else 0,
        "daily_tokens": daily_row["tokens"] if daily_row else 0,
        "monthly_requests": monthly_row["requests"] if monthly_row else 0,
        "monthly_tokens": monthly_row["tokens"] if monthly_row else 0,
    }


def _increment_usage(provider: str, tokens: int = 0) -> None:
    today = date.today().isoformat()
    month = date.today().strftime("%Y-%m")
    with _db_lock:
        with _db() as conn:
            for period, ptype in [(today, "daily"), (month, "monthly")]:
                conn.execute(
                    """
                    INSERT INTO provider_usage (provider, period, period_type, requests, tokens)
                    VALUES (?, ?, ?, 1, ?)
                    ON CONFLICT(provider, period, period_type) DO UPDATE SET
                        requests = requests + 1,
                        tokens = tokens + excluded.tokens
                    """,
                    (provider, period, ptype, tokens),
                )


def _provider_available(provider: str) -> tuple[bool, str]:
    """Return (available, reason). False when >= 95% of limit used."""
    usage = _get_usage(provider)
    limits = PROVIDER_LIMITS.get(provider, {})

    if limits.get("daily") and usage["daily_requests"] >= limits["daily"] * 0.95:
        return False, f"Daily limit {limits['daily']} at 95%"
    if limits.get("monthly") and usage["monthly_tokens"] >= limits["monthly"] * 0.95:
        return False, f"Monthly token limit {limits['monthly']} at 95%"
    return True, ""


def _provider_degraded(provider: str) -> bool:
    """Return True when >= 80% of limit used (rotate but don't hard-stop)."""
    usage = _get_usage(provider)
    limits = PROVIDER_LIMITS.get(provider, {})
    if limits.get("daily") and usage["daily_requests"] >= limits["daily"] * 0.80:
        return True
    if limits.get("monthly") and usage["monthly_tokens"] >= limits["monthly"] * 0.80:
        return True
    return False


def _select_provider() -> Optional[str]:
    """Return the first non-degraded available provider."""
    for provider in PROVIDER_ORDER:
        available, _ = _provider_available(provider)
        if available and not _provider_degraded(provider):
            return provider
    # All degraded but not hard-stopped — use first still-available
    for provider in PROVIDER_ORDER:
        available, _ = _provider_available(provider)
        if available:
            return provider
    return None


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    messages: list[dict[str, str]]
    model: str = "llama3.2"
    max_tokens: int = 1024
    temperature: float = 0.7
    provider: Optional[str] = None  # force a specific provider


class EmbedRequest(BaseModel):
    input: str | list[str]
    model: str = "text-embedding-3-small"


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="LiteLLM Service",
    description="x10 free provider chain with limit monitoring",
    version=VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, Any]:
    uptime = (datetime.now(timezone.utc) - STARTED_AT).total_seconds()
    return {"status": "ok", "service": WORKER_NAME, "version": VERSION, "uptime_seconds": uptime}


# ---------------------------------------------------------------------------
# /litellm/models
# ---------------------------------------------------------------------------


@app.get("/litellm/models")
async def list_models() -> dict[str, Any]:
    """List available free models from LiteLLM proxy."""
    try:
        headers = {}
        if LITELLM_MASTER_KEY:
            headers["Authorization"] = f"Bearer {LITELLM_MASTER_KEY}"
        async with httpx.AsyncClient(timeout=_http_timeout) as client:
            resp = await client.get(f"{LITELLM_URL}/models", headers=headers)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.warning("LiteLLM models unavailable: %s", exc)
        # Return curated free model list
        return {
            "object": "list",
            "data": [
                {"id": "ollama/llama3.2", "provider": "ollama", "free": True},
                {"id": "groq/llama-3.1-70b-versatile", "provider": "groq", "free": True},
                {"id": "gemini/gemini-1.5-flash", "provider": "gemini_flash", "free": True},
                {"id": "cerebras/llama3.1-8b", "provider": "cerebras", "free": True},
                {"id": "sambanova/Meta-Llama-3.1-8B-Instruct", "provider": "sambanova", "free": True},
                {"id": "github/gpt-4o-mini", "provider": "github_models", "free": True},
                {"id": "mistral/mistral-small-latest", "provider": "mistral", "free": True},
                {"id": "openrouter/meta-llama/llama-3.2-3b-instruct:free", "provider": "openrouter", "free": True},
                {"id": "huggingface/mistralai/Mistral-7B-Instruct-v0.3", "provider": "huggingface", "free": True},
                {"id": "deepseek/deepseek-chat", "provider": "deepseek", "free": True},
            ],
        }


# ---------------------------------------------------------------------------
# /litellm/chat
# ---------------------------------------------------------------------------


@app.post("/litellm/chat")
async def chat(body: ChatRequest) -> dict[str, Any]:
    """Proxy to LiteLLM /chat/completions with adaptive provider selection."""
    provider = body.provider or _select_provider()
    if provider is None:
        raise HTTPException(status_code=429, detail="All free providers at capacity. Retry tomorrow.")

    # Hard-stop check
    available, reason = _provider_available(provider)
    if not available:
        logger.warning("Provider %s at hard-stop: %s", provider, reason)
        raise HTTPException(status_code=429, detail=f"Provider {provider} limit reached: {reason}")

    if _provider_degraded(provider):
        logger.info("Provider %s degraded (80%% limit) — using anyway", provider)

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if LITELLM_MASTER_KEY:
        headers["Authorization"] = f"Bearer {LITELLM_MASTER_KEY}"

    payload = {
        "model": body.model,
        "messages": body.messages,
        "max_tokens": body.max_tokens,
        "temperature": body.temperature,
    }

    try:
        async with httpx.AsyncClient(timeout=_http_timeout) as client:
            resp = await client.post(
                f"{LITELLM_URL}/chat/completions", json=payload, headers=headers
            )
            resp.raise_for_status()
            result = resp.json()
            tokens_used = result.get("usage", {}).get("total_tokens", 0)
            _increment_usage(provider, tokens=tokens_used)
            result["_provider"] = provider
            return result
    except httpx.HTTPStatusError as exc:
        logger.error("LiteLLM chat error (%s): %s", exc.response.status_code, exc.response.text)
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text) from exc
    except Exception as exc:
        logger.error("LiteLLM unreachable: %s", exc)
        raise HTTPException(status_code=503, detail=f"LiteLLM unavailable: {exc}") from exc


# ---------------------------------------------------------------------------
# /litellm/embed
# ---------------------------------------------------------------------------


@app.post("/litellm/embed")
async def embed(body: EmbedRequest) -> dict[str, Any]:
    """Proxy to LiteLLM /embeddings."""
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if LITELLM_MASTER_KEY:
        headers["Authorization"] = f"Bearer {LITELLM_MASTER_KEY}"
    payload = {"model": body.model, "input": body.input}
    try:
        async with httpx.AsyncClient(timeout=_http_timeout) as client:
            resp = await client.post(f"{LITELLM_URL}/embeddings", json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"LiteLLM unavailable: {exc}") from exc


# ---------------------------------------------------------------------------
# /litellm/usage
# ---------------------------------------------------------------------------


@app.get("/litellm/usage")
async def get_usage() -> dict[str, Any]:
    """Get usage stats per provider."""
    usage = {}
    for provider in PROVIDER_ORDER:
        u = _get_usage(provider)
        limits = PROVIDER_LIMITS[provider]
        available, reason = _provider_available(provider)
        degraded = _provider_degraded(provider)
        usage[provider] = {
            **u,
            "limits": limits,
            "available": available,
            "degraded": degraded,
            "reason": reason if not available else ("approaching limit" if degraded else ""),
        }
    return {"usage": usage, "date": date.today().isoformat()}


# ---------------------------------------------------------------------------
# /litellm/budget
# ---------------------------------------------------------------------------


@app.get("/litellm/budget")
async def get_budget() -> dict[str, Any]:
    """Get budget status for all providers."""
    budget = {}
    for provider in PROVIDER_ORDER:
        u = _get_usage(provider)
        limits = PROVIDER_LIMITS[provider]
        daily_pct = None
        monthly_pct = None
        if limits.get("daily") and limits["daily"]:
            daily_pct = round(u["daily_requests"] / limits["daily"] * 100, 1)
        if limits.get("monthly") and limits["monthly"]:
            monthly_pct = round(u["monthly_tokens"] / limits["monthly"] * 100, 1)
        budget[provider] = {
            "daily_used": u["daily_requests"],
            "daily_limit": limits.get("daily"),
            "daily_pct": daily_pct,
            "monthly_tokens_used": u["monthly_tokens"],
            "monthly_token_limit": limits.get("monthly"),
            "monthly_pct": monthly_pct,
            "status": (
                "hard_stop" if not _provider_available(provider)[0]
                else "degraded" if _provider_degraded(provider)
                else "ok"
            ),
        }
    return {"budget": budget, "preferred_provider": _select_provider()}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
