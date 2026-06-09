"""
Trancendos AI API — Self-Hosted Worker (infinity-ai)
====================================================
Replaces CF ai-api.
Provides an OpenAI-compatible API proxy with Ollama-first routing,
priority-based failover (Ollama → OpenRouter → HuggingFace → Offline),
token budgets, and caching.

Port: 8009
Maps to: The Spark / AI Gateway
Zero-cost: Ollama local inference, free-tier OpenRouter, HuggingFace free inference, offline fallback.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from collections import OrderedDict
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from shared_core.sanitize import sanitize_for_log
from src.database.encrypted_sqlite import connect as sqlite3_connect
from src.entities.health_metadata import health_entity_block

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
WORKER_PORT = 8009
WORKER_NAME = "infinity-ai"
DB_PATH = Path(__file__).parent / "data" / "ai_gateway.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Provider configuration — zero-cost providers only
OLLAMA_BASE_URL = "http://localhost:11434"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
HUGGINGFACE_BASE_URL = "https://api-inference.huggingface.co"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ProviderName(str, Enum):
    ollama = "ollama"
    openrouter = "openrouter"
    huggingface = "huggingface"
    offline = "offline"


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "llama3.2"
    messages: List[ChatMessage]
    max_tokens: int = 1024
    temperature: float = 0.7
    stream: bool = False
    tenant_id: Optional[str] = None


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class ChatCompletionUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:12]}")
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str = ""
    choices: List[ChatCompletionChoice] = Field(default_factory=list)
    usage: ChatCompletionUsage = Field(default_factory=ChatCompletionUsage)
    provider: str = ""  # Which provider served the request


class TokenBudget(BaseModel):
    tenant_id: str
    daily_limit: int = 100_000
    used_today: int = 0
    last_reset: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# LRU Cache
# ---------------------------------------------------------------------------


class LRUCache:
    """Simple LRU cache for AI responses."""

    def __init__(self, max_size: int = 500):
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._max_size = max_size
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            return None

    def put(self, key: str, value: Any):
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            else:
                self._cache[key] = value
            if len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    def clear(self):
        with self._lock:
            self._cache.clear()


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


class AIDatabase:
    """SQLite-backed storage for token budgets, usage, and request logs."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3_connect(str(self.db_path), timeout=10)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    @contextmanager
    def _cursor(self):
        conn = self._get_conn()
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _init_db(self):
        with self._cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS token_budgets (
                    tenant_id TEXT PRIMARY KEY,
                    daily_limit INTEGER DEFAULT 100000,
                    used_today INTEGER DEFAULT 0,
                    last_reset TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS request_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL,
                    tenant_id TEXT,
                    model TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    prompt_tokens INTEGER DEFAULT 0,
                    completion_tokens INTEGER DEFAULT 0,
                    total_tokens INTEGER DEFAULT 0,
                    latency_ms INTEGER,
                    success INTEGER DEFAULT 1,
                    error_message TEXT,
                    timestamp TEXT NOT NULL
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_reqlog_tenant ON request_log(tenant_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_reqlog_timestamp ON request_log(timestamp)")

    def get_budget(self, tenant_id: str) -> TokenBudget:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM token_budgets WHERE tenant_id=?", (tenant_id,)).fetchone()
        if row:
            budget = TokenBudget(
                tenant_id=row["tenant_id"],
                daily_limit=row["daily_limit"],
                used_today=row["used_today"],
                last_reset=datetime.fromisoformat(row["last_reset"]),
            )
        else:
            budget = TokenBudget(tenant_id=tenant_id)
        # Auto-reset if day changed
        now = datetime.now(timezone.utc)
        if (now - budget.last_reset) >= timedelta(days=1):
            budget.used_today = 0
            budget.last_reset = now
            self._save_budget(budget)
        return budget

    def _save_budget(self, budget: TokenBudget):
        with self._cursor() as cur:
            cur.execute(
                "INSERT OR REPLACE INTO token_budgets (tenant_id, daily_limit, used_today, last_reset) VALUES (?,?,?,?)",
                (
                    budget.tenant_id,
                    budget.daily_limit,
                    budget.used_today,
                    budget.last_reset.isoformat(),
                ),
            )

    def record_usage(self, tenant_id: str, tokens_used: int):
        budget = self.get_budget(tenant_id)
        budget.used_today += tokens_used
        self._save_budget(budget)

    def check_budget(self, tenant_id: str, tokens_requested: int) -> bool:
        budget = self.get_budget(tenant_id)
        return (budget.used_today + tokens_requested) <= budget.daily_limit

    def log_request(
        self,
        request_id: str,
        tenant_id: Optional[str],
        model: str,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: Optional[int],
        success: bool,
        error: Optional[str] = None,
    ):
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO request_log (request_id, tenant_id, model, provider, prompt_tokens, completion_tokens, total_tokens, latency_ms, success, error_message, timestamp) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    request_id,
                    tenant_id,
                    model,
                    provider,
                    prompt_tokens,
                    completion_tokens,
                    prompt_tokens + completion_tokens,
                    latency_ms,
                    int(success),
                    error or "",
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def get_usage_stats(self, tenant_id: Optional[str] = None, hours: int = 24) -> Dict[str, Any]:
        conn = self._get_conn()
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        if tenant_id:
            rows = conn.execute(
                "SELECT provider, COUNT(*) as count, SUM(total_tokens) as tokens, AVG(latency_ms) as avg_latency, SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) as errors FROM request_log WHERE tenant_id=? AND timestamp>=? GROUP BY provider",
                (tenant_id, cutoff),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT provider, COUNT(*) as count, SUM(total_tokens) as tokens, AVG(latency_ms) as avg_latency, SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) as errors FROM request_log WHERE timestamp>=? GROUP BY provider",
                (cutoff,),
            ).fetchall()
        return {"stats": [dict(r) for r in rows]}


# ---------------------------------------------------------------------------
# Provider Clients (zero-cost — no paid APIs)
# ---------------------------------------------------------------------------


class OllamaClient:
    """Ollama local inference client — primary zero-cost provider."""

    def __init__(self, base_url: str = OLLAMA_BASE_URL):
        self.base_url = base_url.rstrip("/")
        self._available: Optional[bool] = None

    async def complete(
        self,
        model: str,
        messages: List[ChatMessage],
        max_tokens: int,
        temperature: float,
    ) -> Optional[Dict[str, Any]]:
        import urllib.error
        import urllib.request

        try:
            payload = {
                "model": model,
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "stream": False,
                "options": {"num_predict": max_tokens, "temperature": temperature},
            }
            data = json.dumps(payload).encode()
            req = urllib.request.Request(
                f"{self.base_url}/api/chat",
                data=data,
                method="POST",
            )
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode())
                return result
        except Exception as e:
            logger.warning(
                "Ollama request failed: %s", sanitize_for_log(e)
            )  # codeql[py/cleartext-logging]
            self._available = False
            return None

    async def health_check(self) -> bool:
        import urllib.request

        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception:
            self._available = False
            return False


class OpenRouterClient:
    """OpenRouter free-tier client — secondary zero-cost provider."""

    FREE_MODELS = [
        "meta-llama/llama-3.2-3b-instruct:free",
        "qwen/qwen-2.5-72b-instruct:free",
        "google/gemma-2-9b-it:free",
        "mistralai/mistral-7b-instruct:free",
    ]

    def __init__(self, base_url: str = OPENROUTER_BASE_URL, api_key: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    async def complete(
        self,
        model: str,
        messages: List[ChatMessage],
        max_tokens: int,
        temperature: float,
    ) -> Optional[Dict[str, Any]]:
        import urllib.error
        import urllib.request

        try:
            # Use free model if the requested model isn't free
            actual_model = model
            if not model.endswith(":free"):
                actual_model = self.FREE_MODELS[0]

            payload = {
                "model": actual_model,
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            data = json.dumps(payload).encode()
            req = urllib.request.Request(
                f"{self.base_url}/chat/completions",
                data=data,
                method="POST",
            )
            req.add_header("Content-Type", "application/json")
            req.add_header("HTTP-Referer", "https://trancendos.com")
            req.add_header("X-Title", "Tranc3 AI Gateway")
            if self.api_key:
                req.add_header("Authorization", f"Bearer {self.api_key}")
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            logger.warning(
                "OpenRouter HTTP error: %s %s", e.code, sanitize_for_log(e.reason)
            )  # codeql[py/cleartext-logging]
            return None
        except Exception as e:
            logger.warning(
                "OpenRouter request failed: %s", sanitize_for_log(e)
            )  # codeql[py/cleartext-logging]
            return None


class HuggingFaceClient:
    """HuggingFace Inference API client — free-tier provider."""

    FREE_MODELS = [
        "meta-llama/Llama-3.2-3B-Instruct",
        "mistralai/Mistral-7B-Instruct-v0.3",
        "microsoft/Phi-3-mini-4k-instruct",
    ]

    def __init__(self, base_url: str = HUGGINGFACE_BASE_URL, api_key: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    async def complete(
        self,
        model: str,
        messages: List[ChatMessage],
        max_tokens: int,
        temperature: float,
    ) -> Optional[Dict[str, Any]]:
        import urllib.error
        import urllib.request

        try:
            prompt = "\n".join(f"{m.role}: {m.content}" for m in messages) + "\nassistant:"
            payload = {
                "inputs": prompt,
                "parameters": {"max_new_tokens": max_tokens, "temperature": temperature},
            }
            data = json.dumps(payload).encode()
            actual_model = model if "/" in model else self.FREE_MODELS[0]
            req = urllib.request.Request(
                f"{self.base_url}/models/{actual_model}",
                data=data,
                method="POST",
            )
            req.add_header("Content-Type", "application/json")
            if self.api_key:
                req.add_header("Authorization", f"Bearer {self.api_key}")
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode())
                if isinstance(result, list) and len(result) > 0:
                    text = result[0].get("generated_text", "")
                    return {"content": text}
                elif isinstance(result, dict) and "error" in result:
                    logger.warning(
                        "HuggingFace error: %s", sanitize_for_log(result["error"])
                    )  # codeql[py/cleartext-logging]
                    return None
                return result
        except urllib.error.HTTPError as e:
            if e.code == 503:
                logger.info("HuggingFace model loading, will retry later")
            else:
                logger.warning("HuggingFace HTTP error: %s", e.code)
            return None
        except Exception as e:
            logger.warning(
                "HuggingFace request failed: %s", sanitize_for_log(e)
            )  # codeql[py/cleartext-logging]
            return None


class OfflineClient:
    """Offline fallback — deterministic responses when no provider is available."""

    FALLBACK_RESPONSES = {
        "default": "I'm currently operating in offline mode. My local AI service is not available right now. Please try again later when the Ollama service is restored.",
        "greeting": "Hello! I'm in offline mode right now, but I'm still here to help. Full AI capabilities will return when the local service is restored.",
        "error": "I apologize, but I'm unable to process your request at this time due to service unavailability. Your request has been logged and will be processed once services are restored.",
    }

    async def complete(
        self,
        model: str,
        messages: List[ChatMessage],
        max_tokens: int,
        temperature: float,
    ) -> Dict[str, Any]:
        # Simple keyword matching for offline responses
        last_msg = messages[-1].content.lower() if messages else ""
        if any(w in last_msg for w in ["hello", "hi", "hey", "greet"]):
            content = self.FALLBACK_RESPONSES["greeting"]
        elif any(w in last_msg for w in ["error", "fail", "problem", "issue"]):
            content = self.FALLBACK_RESPONSES["error"]
        else:
            content = self.FALLBACK_RESPONSES["default"]
        return {"content": content, "done": True, "model": "offline-fallback"}


# ---------------------------------------------------------------------------
# AI Gateway Router
# ---------------------------------------------------------------------------


class AIGatewayRouter:
    """Routes AI requests through provider priority chain with caching and budget tracking."""

    def __init__(self, db: AIDatabase):
        self.db = db
        self.cache = LRUCache(max_size=500)
        self.ollama = OllamaClient()
        self.openrouter = OpenRouterClient()
        self.huggingface = HuggingFaceClient()
        self.offline = OfflineClient()
        # Provider priority: Ollama first (free+local), then free-tier cloud, then offline
        self._provider_map = {
            ProviderName.ollama: self.ollama,
            ProviderName.openrouter: self.openrouter,
            ProviderName.huggingface: self.huggingface,
            ProviderName.offline: self.offline,
        }
        self.providers = self._default_provider_order()

    def _default_provider_order(self) -> list:
        return [
            (ProviderName.ollama, self.ollama),
            (ProviderName.openrouter, self.openrouter),
            (ProviderName.huggingface, self.huggingface),
            (ProviderName.offline, self.offline),
        ]

    def _adaptive_provider_order(self) -> list:
        """Reorder cloud providers via zero-cost rotator (Ollama always first)."""
        if os.environ.get("ADAPTIVE_ROTATION_ENABLED", "true").lower() not in (
            "1",
            "true",
            "yes",
        ):
            return self._default_provider_order()
        try:
            from src.adaptive.provider_rotator import get_provider_rotator

            rotator = get_provider_rotator()
            name_map = {
                "ollama": ProviderName.ollama,
                "openrouter": ProviderName.openrouter,
                "huggingface": ProviderName.huggingface,
                "offline": ProviderName.offline,
            }
            keys: list[str] = ["ollama"]
            active = rotator.active_provider()
            if active and active not in keys and active in name_map:
                keys.append(active)
            for p in rotator._state.providers:
                if p not in keys and p in name_map:
                    keys.append(p)
            if "offline" not in keys:
                keys.append("offline")
            ordered = []
            for k in keys:
                enum_name = name_map.get(k)
                if enum_name and enum_name in self._provider_map:
                    ordered.append((enum_name, self._provider_map[enum_name]))
            return ordered or self._default_provider_order()
        except Exception as exc:
            logger.warning(
                "Adaptive order fallback: %s", sanitize_for_log(exc)
            )  # codeql[py/cleartext-logging]
            return self._default_provider_order()

    def _make_cache_key(
        self,
        model: str,
        messages: List[ChatMessage],
        max_tokens: int,
        temperature: float,
        tenant_id: Optional[str],
    ) -> str:
        msg_str = "|".join(f"{m.role}:{m.content}" for m in messages)
        raw = f"{tenant_id or 'default'}:{model}:{msg_str}:{max_tokens}:{temperature}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    async def route(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        request_id = f"req-{uuid.uuid4().hex[:12]}"
        tenant_id = request.tenant_id or "default"
        start_time = time.time()

        # Check token budget
        estimated_tokens = request.max_tokens + sum(
            len(m.content.split()) for m in request.messages
        )
        if not self.db.check_budget(tenant_id, estimated_tokens):
            raise HTTPException(
                429,
                "Token budget exceeded for today. Try again tomorrow or contact admin.",
            )

        # Check cache
        cache_key = self._make_cache_key(
            request.model,
            request.messages,
            request.max_tokens,
            request.temperature,
            tenant_id,
        )
        cached = self.cache.get(cache_key)
        if cached:
            cached.provider = "cache"
            return cached

        # Try providers in priority order (adaptive rotation when enabled)
        providers = self._adaptive_provider_order()
        last_error = None
        for provider_name, provider in providers:
            try:
                result = await provider.complete(
                    request.model,
                    request.messages,
                    request.max_tokens,
                    request.temperature,
                )
                if result is None:
                    continue

                # Normalize response
                content = ""
                if isinstance(result, dict):
                    if "message" in result:
                        content = result["message"].get("content", "")
                    elif "choices" in result and result["choices"]:
                        content = result["choices"][0].get("message", {}).get("content", "")
                    elif "content" in result:
                        content = result["content"]
                    elif "generated_text" in result:
                        content = result["generated_text"]

                # Estimate tokens (rough: 1 token ≈ 4 chars)
                prompt_tokens = sum(len(m.content) // 4 for m in request.messages)
                completion_tokens = max(1, len(content) // 4)

                response = ChatCompletionResponse(
                    model=request.model,
                    choices=[
                        ChatCompletionChoice(
                            message=ChatMessage(role="assistant", content=content),
                            finish_reason="stop",
                        ),
                    ],
                    usage=ChatCompletionUsage(
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=prompt_tokens + completion_tokens,
                    ),
                    provider=provider_name.value,
                )

                # Record usage
                latency_ms = int((time.time() - start_time) * 1000)
                self.db.record_usage(tenant_id, completion_tokens)
                self.db.log_request(
                    request_id=request_id,
                    tenant_id=tenant_id,
                    model=request.model,
                    provider=provider_name.value,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    latency_ms=latency_ms,
                    success=True,
                )

                # Cache successful responses
                self.cache.put(cache_key, response)

                try:
                    from src.adaptive.provider_rotator import get_provider_rotator

                    get_provider_rotator().record_success(provider_name.value)
                except Exception:
                    pass

                return response

            except Exception as e:
                last_error = str(e)
                logger.warning(  # codeql[py/cleartext-logging]
                    "Provider %s failed: %s", provider_name.value, sanitize_for_log(e)
                )
                try:
                    from src.adaptive.provider_rotator import get_provider_rotator

                    rate_limited = "429" in str(e) or "rate" in str(e).lower()
                    get_provider_rotator().record_failure(
                        provider_name.value, rate_limited=rate_limited
                    )
                except Exception:
                    pass
                continue

        # All providers failed — use offline as last resort
        result = await self.offline.complete(
            request.model,
            request.messages,
            request.max_tokens,
            request.temperature,
        )
        content = result.get("content", "")
        latency_ms = int((time.time() - start_time) * 1000)
        self.db.log_request(
            request_id=request_id,
            tenant_id=tenant_id,
            model=request.model,
            provider="offline",
            prompt_tokens=0,
            completion_tokens=len(content) // 4,
            latency_ms=latency_ms,
            success=False,
            error=last_error,
        )
        return ChatCompletionResponse(
            model=request.model,
            choices=[
                ChatCompletionChoice(
                    message=ChatMessage(role="assistant", content=content),
                    finish_reason="stop",
                ),
            ],
            usage=ChatCompletionUsage(total_tokens=len(content) // 4),
            provider="offline",
        )


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

db = AIDatabase(DB_PATH)
router = AIGatewayRouter(db)

app = FastAPI(
    title="Infinity AI — AI API Gateway",
    description="Self-hosted OpenAI-compatible API with Ollama-first routing. Replaces CF ai-api.",
    version="1.0.0",
)

from src.observability.prometheus_mount import mount_prometheus_endpoint

mount_prometheus_endpoint(app, "infinity-ai")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


_INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")


async def require_internal_auth(
    x_internal_secret: str = Header(default="", alias="X-Internal-Secret"),
) -> None:
    if not _INTERNAL_SECRET:
        return
    if x_internal_secret != _INTERNAL_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Internal-Secret header")


_router = APIRouter(dependencies=[Depends(require_internal_auth)])
STARTED_AT = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Health & Info
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    ollama_ok = await router.ollama.health_check()
    return {
        "entity": health_entity_block(8009, "infinity-ai"),
        "status": "healthy" if ollama_ok else "degraded",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "ollama_available": ollama_ok,
        "providers": ["ollama", "openrouter", "huggingface", "offline"],
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
    }


@_router.get("/v1/models")
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
        {"id": "qwen/qwen-2.5-72b-instruct:free", "object": "model", "owned_by": "openrouter"},
        {"id": "offline-fallback", "object": "model", "owned_by": "local"},
    ]
    return {"object": "list", "data": models}


# ---------------------------------------------------------------------------
# Chat Completions (OpenAI-compatible)
# ---------------------------------------------------------------------------


@_router.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """OpenAI-compatible chat completions endpoint with provider failover."""
    return await router.route(request)


# Also support /chat/completions without v1 prefix
@_router.post("/chat/completions")
async def chat_completions_no_v1(request: ChatCompletionRequest):
    """Chat completions without /v1 prefix."""
    return await router.route(request)


# ---------------------------------------------------------------------------
# Token Budget & Usage
# ---------------------------------------------------------------------------


@_router.get("/usage/{tenant_id}")
async def get_usage(tenant_id: str):
    """Get token budget and usage for a tenant."""
    budget = db.get_budget(tenant_id)
    return {
        "tenant_id": tenant_id,
        "daily_limit": budget.daily_limit,
        "used_today": budget.used_today,
        "remaining": budget.daily_limit - budget.used_today,
        "last_reset": budget.last_reset.isoformat(),
    }


@_router.get("/usage/{tenant_id}/stats")
async def get_usage_stats(tenant_id: str, hours: int = Query(24, ge=1, le=168)):
    """Get detailed usage statistics for a tenant."""
    return db.get_usage_stats(tenant_id=tenant_id, hours=hours)


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------


@_router.post("/admin/budget")
async def set_budget(tenant_id: str, daily_limit: int = 100_000):
    """Set the daily token budget for a tenant."""
    budget = db.get_budget(tenant_id)
    budget.daily_limit = daily_limit
    db._save_budget(budget)
    return {"ok": True, "tenant_id": tenant_id, "daily_limit": daily_limit}


@_router.post("/admin/cache/clear")
async def clear_cache():
    """Clear the response cache."""
    router.cache.clear()
    return {"ok": True, "message": "Cache cleared"}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

app.include_router(_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
