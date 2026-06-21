"""
FastAPI routes for the infinity-ai worker.
All routes are registered on an APIRouter and included in main.py.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from models import ChatCompletionRequest

from config import INTERNAL_SECRET, PROVIDER_DAILY_LIMITS, WORKER_NAME, WORKER_PORT

# These are injected at startup via init_router()
_db = None
_gateway = None

STARTED_AT = datetime.now(timezone.utc)


def init_router(db, gateway):
    """Inject shared DB and gateway instances after app startup."""
    global _db, _gateway
    _db = db
    _gateway = gateway


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------


async def require_internal_auth(
    x_internal_secret: str = Header(default="", alias="X-Internal-Secret"),
) -> None:
    if not INTERNAL_SECRET:
        return
    if x_internal_secret != INTERNAL_SECRET:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing X-Internal-Secret header",
        )


# ---------------------------------------------------------------------------
# Public routes (no auth)
# ---------------------------------------------------------------------------

public_router = APIRouter()


@public_router.get("/health")
async def health():
    ollama_ok = await _gateway.ollama.health_check()
    return {
        "status": "healthy" if ollama_ok else "degraded",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "ollama_available": ollama_ok,
        "providers": [
            "ollama",
            "groq",
            "cerebras",
            "openrouter",
            "huggingface",
            "together",
            "deepseek",
            "offline",
        ],
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
    }


# ---------------------------------------------------------------------------
# Protected routes (require X-Internal-Secret when INTERNAL_SECRET is set)
# ---------------------------------------------------------------------------

protected_router = APIRouter(dependencies=[Depends(require_internal_auth)])


# ---- Models ----------------------------------------------------------------


@protected_router.get("/v1/models")
async def list_models():
    """OpenAI-compatible models list endpoint."""
    models = [
        {"id": "llama3.2", "object": "model", "owned_by": "ollama"},
        {"id": "llama3.1", "object": "model", "owned_by": "ollama"},
        {"id": "mistral", "object": "model", "owned_by": "ollama"},
        {"id": "phi3", "object": "model", "owned_by": "ollama"},
        {"id": "gemma2", "object": "model", "owned_by": "ollama"},
        {"id": "qwen2", "object": "model", "owned_by": "ollama"},
        {"id": "codellama", "object": "model", "owned_by": "ollama"},
        {
            "id": "meta-llama/llama-3.2-3b-instruct:free",
            "object": "model",
            "owned_by": "openrouter",
        },
        {
            "id": "qwen/qwen-2.5-72b-instruct:free",
            "object": "model",
            "owned_by": "openrouter",
        },
        {"id": "offline-fallback", "object": "model", "owned_by": "local"},
    ]
    return {"object": "list", "data": models}


# ---- Chat completions -------------------------------------------------------


@protected_router.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """OpenAI-compatible chat completions endpoint with provider failover."""
    return await _gateway.route(request)


@protected_router.post("/chat/completions")
async def chat_completions_no_v1(request: ChatCompletionRequest):
    """Chat completions without /v1 prefix."""
    return await _gateway.route(request)


# ---- Token Budget & Usage ---------------------------------------------------


@protected_router.get("/usage/{tenant_id}")
async def get_usage(tenant_id: str):
    """Get token budget and usage for a tenant."""
    budget = _db.get_budget(tenant_id)
    return {
        "tenant_id": tenant_id,
        "daily_limit": budget.daily_limit,
        "used_today": budget.used_today,
        "remaining": budget.daily_limit - budget.used_today,
        "last_reset": budget.last_reset.isoformat(),
    }


@protected_router.get("/usage/{tenant_id}/stats")
async def get_usage_stats(tenant_id: str, hours: int = Query(24, ge=1, le=168)):
    """Get detailed usage statistics for a tenant."""
    return _db.get_usage_stats(tenant_id=tenant_id, hours=hours)


# ---- Admin ------------------------------------------------------------------


@protected_router.post("/admin/budget")
async def set_budget(tenant_id: str, daily_limit: int = 100_000):
    """Set the daily token budget for a tenant."""
    budget = _db.get_budget(tenant_id)
    budget.daily_limit = daily_limit
    _db._save_budget(budget)
    return {"ok": True, "tenant_id": tenant_id, "daily_limit": daily_limit}


@protected_router.post("/admin/cache/clear")
async def clear_cache():
    """Clear the response cache."""
    _gateway.cache.clear()
    return {"ok": True, "message": "Cache cleared"}


# ---- Providers Dashboard ----------------------------------------------------


@protected_router.get("/providers")
async def providers_dashboard():
    """Live provider status dashboard — which providers are active and their availability."""
    ollama_ok = await _gateway.ollama.health_check()

    # Return live dashboard from LimitMonitor when available (has real utilisation data)
    try:
        from src.ai_gateway.limit_monitor import monitor as _lm

        return _lm.get_dashboard()
    except Exception:
        pass

    provider_info: dict = {}
    for pname, _client in _gateway.providers:
        name = pname.value
        available = True
        status = "ok"
        if name == "ollama":
            available = ollama_ok
            status = "unlimited" if ollama_ok else "hard_stop"
        elif name == "offline":
            status = "ok"
            available = True
        else:
            key_map = {
                "groq": "GROQ_API_KEY",
                "cerebras": "CEREBRAS_API_KEY",
                "openrouter": "OPENROUTER_API_KEY",
                "huggingface": "HUGGINGFACE_API_KEY",
                "together": "TOGETHER_API_KEY",
                "deepseek": "DEEPSEEK_API_KEY",
            }
            env_key = key_map.get(name)
            available = bool(env_key and os.environ.get(env_key))
            status = "ok" if available else "cooling_down"

        daily_limit = PROVIDER_DAILY_LIMITS.get(name, -1)
        provider_info[name] = {
            "status": status,
            "available": available,
            "daily_limit": daily_limit,
            "utilisation_pct": 0,
            "daily_req": "0/∞" if daily_limit == -1 else f"0/{daily_limit}",
            "hourly_req": "0/∞" if daily_limit == -1 else f"0/{max(1, daily_limit // 24)}",
            "consecutive_errors": 0,
        }

    available_names = [
        n for n, info in provider_info.items() if info["available"] and n != "offline"
    ]
    active = available_names[0] if available_names else "offline"

    return {
        "active_provider": active,
        "available_providers": available_names,
        "rotating_providers": [],
        "hard_stopped_providers": [],
        "zero_cost_operational": len(available_names) > 0,
        "providers": provider_info,
    }
