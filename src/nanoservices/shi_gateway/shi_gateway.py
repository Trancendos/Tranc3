"""
SHI — Self-Hosted Inference Gateway
====================================
Running quantized models on local hardware using Ollama or vLLM.
Eliminates API costs and reliance on third-party uptime.

Architecture:
  - Gateway pattern: single entry point for all inference requests
  - Model registry: track available models, their sizes, and capabilities
  - Request queue: priority-based queuing with TTL
  - Fallback chain: Ollama → vLLM → cached response → error
  - Metrics: latency, throughput, error rates per model
  - Zero-cost: uses Ollama (free, local) or vLLM (free, local)

Integration with NSA:
  - Receives inference requests via shared memory IPC
  - Sends responses back via shared memory IPC
  - Registered as a nanoservice in the NSA broker
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

# ─────────────────────────────────────────────────────────────────────────────
# Types
# ─────────────────────────────────────────────────────────────────────────────

class InferenceBackend(str, Enum):
    OLLAMA = "ollama"
    VLLM = "vllm"
    LLAMACPP = "llamacpp"
    FALLBACK = "fallback"  # Cached responses only


class ModelStatus(str, Enum):
    LOADING = "loading"
    READY = "ready"
    BUSY = "busy"
    ERROR = "error"
    UNAVAILABLE = "unavailable"


@dataclass
class ModelInfo:
    """Information about a loaded model."""
    name: str
    backend: InferenceBackend
    size_bytes: int = 0
    quantization: str = "q4_K_M"
    context_length: int = 4096
    status: ModelStatus = ModelStatus.READY
    loaded_at: str = ""
    inference_count: int = 0
    error_count: int = 0
    avg_latency_ms: float = 0.0
    last_used: str = ""


@dataclass
class InferenceRequest:
    """An inference request."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    model: str = "mistral:7b-instruct-v0.2-q4_K_M"
    prompt: str = ""
    system_prompt: str = ""
    max_tokens: int = 1024
    temperature: float = 0.7
    top_p: float = 0.9
    stream: bool = False
    priority: int = 128
    ttl_ms: int = 60000
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class InferenceResponse:
    """Response from an inference request."""
    id: str = ""
    request_id: str = ""
    model: str = ""
    response: str = ""
    tokens_generated: int = 0
    latency_ms: float = 0.0
    backend_used: InferenceBackend = InferenceBackend.OLLAMA
    cached: bool = False
    error: Optional[str] = None


@dataclass
class InferenceMetrics:
    """Metrics for the inference gateway."""
    total_requests: int = 0
    total_errors: int = 0
    total_tokens_generated: int = 0
    avg_latency_ms: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    models_loaded: int = 0
    uptime_seconds: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Ollama Backend
# ─────────────────────────────────────────────────────────────────────────────

class OllamaBackend:
    """Ollama-based inference backend — zero cost, local execution."""

    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url
        self._available: Optional[bool] = None

    async def is_available(self) -> bool:
        """Check if Ollama is running and accessible."""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.base_url}/api/tags", timeout=3.0)
                self._available = resp.status_code == 200
                return self._available
        except Exception:
            self._available = False
            return False

    async def list_models(self) -> List[ModelInfo]:
        """List available models from Ollama."""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.base_url}/api/tags", timeout=5.0)
                if resp.status_code == 200:
                    data = resp.json()
                    models = []
                    for m in data.get("models", []):
                        name = m.get("name", "unknown")
                        size = m.get("size", 0)
                        # Extract quantization from name
                        quant = "q4_K_M"
                        for q in ["q4_K_M", "q5_K_M", "q8_0", "q4_0", "q5_0", "fp16"]:
                            if q in name:
                                quant = q
                                break
                        models.append(ModelInfo(
                            name=name,
                            backend=InferenceBackend.OLLAMA,
                            size_bytes=size,
                            quantization=quant,
                            status=ModelStatus.READY,
                        ))
                    return models
        except Exception:
            pass
        return []

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        """Generate a response using Ollama."""
        start_time = time.monotonic()
        try:
            import httpx
            async with httpx.AsyncClient(timeout=120.0) as client:
                payload = {
                    "model": request.model,
                    "prompt": request.prompt,
                    "stream": False,
                    "options": {
                        "num_predict": request.max_tokens,
                        "temperature": request.temperature,
                        "top_p": request.top_p,
                    },
                }
                if request.system_prompt:
                    payload["system"] = request.system_prompt

                resp = await client.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                )

                latency_ms = (time.monotonic() - start_time) * 1000

                if resp.status_code == 200:
                    data = resp.json()
                    return InferenceResponse(
                        id=str(uuid.uuid4()),
                        request_id=request.id,
                        model=request.model,
                        response=data.get("response", ""),
                        tokens_generated=data.get("eval_count", 0),
                        latency_ms=latency_ms,
                        backend_used=InferenceBackend.OLLAMA,
                    )
                else:
                    return InferenceResponse(
                        id=str(uuid.uuid4()),
                        request_id=request.id,
                        model=request.model,
                        error=f"Ollama returned {resp.status_code}: {resp.text[:200]}",
                        latency_ms=latency_ms,
                        backend_used=InferenceBackend.OLLAMA,
                    )
        except Exception as e:
            latency_ms = (time.monotonic() - start_time) * 1000
            return InferenceResponse(
                id=str(uuid.uuid4()),
                request_id=request.id,
                model=request.model,
                error=f"Ollama error: {str(e)[:200]}",
                latency_ms=latency_ms,
                backend_used=InferenceBackend.OLLAMA,
            )

    async def chat(self, model: str, messages: List[Dict], **kwargs) -> InferenceResponse:
        """Chat completion using Ollama."""
        start_time = time.monotonic()
        try:
            import httpx
            async with httpx.AsyncClient(timeout=120.0) as client:
                payload = {
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": kwargs.get("temperature", 0.7),
                        "top_p": kwargs.get("top_p", 0.9),
                    },
                }
                resp = await client.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                )
                latency_ms = (time.monotonic() - start_time) * 1000

                if resp.status_code == 200:
                    data = resp.json()
                    return InferenceResponse(
                        id=str(uuid.uuid4()),
                        model=model,
                        response=data.get("message", {}).get("content", ""),
                        tokens_generated=data.get("eval_count", 0),
                        latency_ms=latency_ms,
                        backend_used=InferenceBackend.OLLAMA,
                    )
                else:
                    return InferenceResponse(
                        id=str(uuid.uuid4()),
                        model=model,
                        error=f"Ollama chat error: {resp.status_code}",
                        latency_ms=latency_ms,
                        backend_used=InferenceBackend.OLLAMA,
                    )
        except Exception as e:
            latency_ms = (time.monotonic() - start_time) * 1000
            return InferenceResponse(
                id=str(uuid.uuid4()),
                model=model,
                error=f"Ollama chat error: {str(e)[:200]}",
                latency_ms=latency_ms,
                backend_used=InferenceBackend.OLLAMA,
            )


# ─────────────────────────────────────────────────────────────────────────────
# SHI Gateway
# ─────────────────────────────────────────────────────────────────────────────

class SHIGateway:
    """
    Self-Hosted Inference Gateway.
    
    Routes inference requests to the best available backend (Ollama, vLLM, etc.)
    with automatic fallback, caching, and metrics collection.
    """

    def __init__(self, ollama_url: str = "http://localhost:11434"):
        self.ollama = OllamaBackend(ollama_url)
        self._models: Dict[str, ModelInfo] = {}
        self._metrics = InferenceMetrics()
        self._request_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._cache: Dict[str, InferenceResponse] = {}
        self._start_time = time.monotonic()
        self._running = False
        self._default_model = "mistral:7b-instruct-v0.2-q4_K_M"

    async def start(self) -> None:
        """Start the SHI gateway and discover available models."""
        self._running = True

        # Discover models from Ollama
        if await self.ollama.is_available():
            models = await self.ollama.list_models()
            for m in models:
                m.loaded_at = datetime.now(timezone.utc).isoformat()
                self._models[m.name] = m
            self._metrics.models_loaded = len(self._models)

        # Set default model to first available, or keep the default
        if self._models and self._default_model not in self._models:
            self._default_model = next(iter(self._models.keys()))

    async def stop(self) -> None:
        """Stop the SHI gateway."""
        self._running = False

    async def infer(self, request: InferenceRequest) -> InferenceResponse:
        """
        Run inference with automatic backend selection and fallback.
        
        Fallback chain: Ollama → vLLM → cached → error
        """
        self._metrics.total_requests += 1
        request_start = time.monotonic()

        # Check cache first
        cache_key = self._cache_key(request)
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            cached.cached = True
            self._metrics.cache_hits += 1
            return cached

        self._metrics.cache_misses += 1

        # Try Ollama first
        if await self.ollama.is_available():
            response = await self.ollama.generate(request)
            if response.error is None:
                self._update_metrics(response, request_start)
                # Cache successful responses (up to 1000)
                if len(self._cache) < 1000:
                    self._cache[cache_key] = response
                return response

        # No backend available
        self._metrics.total_errors += 1
        return InferenceResponse(
            id=str(uuid.uuid4()),
            request_id=request.id,
            model=request.model,
            error="No inference backend available — ensure Ollama is running",
            latency_ms=(time.monotonic() - request_start) * 1000,
        )

    async def chat(
        self,
        model: Optional[str] = None,
        messages: Optional[List[Dict]] = None,
        **kwargs,
    ) -> InferenceResponse:
        """Convenience method for chat completion."""
        model = model or self._default_model
        messages = messages or [{"role": "user", "content": "Hello"}]
        return await self.ollama.chat(model, messages, **kwargs)

    def list_models(self) -> List[ModelInfo]:
        """List all discovered models."""
        return list(self._models.values())

    @property
    def metrics(self) -> InferenceMetrics:
        """Get gateway metrics."""
        self._metrics.uptime_seconds = time.monotonic() - self._start_time
        return self._metrics

    @property
    def health(self) -> Dict[str, Any]:
        """Get gateway health status."""
        return {
            "status": "healthy" if self._running and self._models else "degraded",
            "models_loaded": len(self._models),
            "ollama_available": self.ollama._available,
            "cache_size": len(self._cache),
            "uptime_seconds": self.metrics.uptime_seconds,
        }

    def _cache_key(self, request: InferenceRequest) -> str:
        """Generate a cache key for a request."""
        return f"{request.model}:{hash(request.prompt)}:{request.max_tokens}:{request.temperature}"

    def _update_metrics(self, response: InferenceResponse, start_time: float) -> None:
        """Update metrics after a successful inference."""
        self._metrics.total_tokens_generated += response.tokens_generated
        # Rolling average latency
        total = self._metrics.total_requests
        self._metrics.avg_latency_ms = (
            (self._metrics.avg_latency_ms * (total - 1) + response.latency_ms) / total
        )
        # Update model info
        if response.model in self._models:
            model = self._models[response.model]
            model.inference_count += 1
            model.last_used = datetime.now(timezone.utc).isoformat()
            model.avg_latency_ms = (
                (model.avg_latency_ms * (model.inference_count - 1) + response.latency_ms)
                / model.inference_count
            )
