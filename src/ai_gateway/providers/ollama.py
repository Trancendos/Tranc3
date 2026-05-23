"""
Ollama Provider — Local, Zero-Cost AI
=======================================
First priority in the AI gateway failover chain.
Ollama runs locally and costs nothing.

Requires: Ollama running on localhost:11434
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from src.ai_gateway.providers.base import AIProvider
from src.ai_gateway.types import AIRequest, AIResponse, ProviderHealth

logger = logging.getLogger("tranc3.ai_gateway.ollama")

# Common models available in Ollama
DEFAULT_MODELS = [
    "llama3.2",
    "llama3.1",
    "mistral",
    "phi3",
    "gemma2",
    "qwen2",
    "codellama",
]


class OllamaProvider(AIProvider):
    """
    Ollama provider — local, zero-cost AI inference.

    Runs on localhost:11434. No API key needed.
    First in the failover chain: if Ollama is available,
    all requests go here (free, fast, private).
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        default_model: str = "llama3.2",
        timeout: float = 120.0,
    ) -> None:
        super().__init__(name="ollama", base_url=base_url)
        self.default_model = default_model
        self.timeout = timeout
        self._available_models: list[str] | None = None

    async def complete(self, request: AIRequest) -> AIResponse:
        """Generate a completion using Ollama."""
        start = time.monotonic()
        model = request.model or self.default_model

        # Build Ollama request
        payload: dict[str, Any] = {
            "model": model,
            "prompt": request.prompt,
            "stream": False,
            "options": {
                "num_predict": request.max_tokens,
                "temperature": request.temperature,
                "top_p": request.top_p,
            },
        }

        # If messages are provided, use chat API
        if request.messages:
            payload = {
                "model": model,
                "messages": request.messages,
                "stream": False,
                "options": {
                    "num_predict": request.max_tokens,
                    "temperature": request.temperature,
                },
            }
            endpoint = f"{self.base_url}/api/chat"
        else:
            endpoint = f"{self.base_url}/api/generate"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(endpoint, json=payload)
                response.raise_for_status()
                data = response.json()

            latency_ms = (time.monotonic() - start) * 1000

            # Parse response based on API type
            if request.messages:
                text = data.get("message", {}).get("content", "")
            else:
                text = data.get("response", "")

            return AIResponse(
                text=text,
                model=data.get("model", model),
                provider=self.name,
                tokens_prompt=data.get("prompt_eval_count", 0),
                tokens_completion=data.get("eval_count", 0),
                tokens_total=data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
                latency_ms=latency_ms,
                finish_reason="stop" if data.get("done", True) else "length",
            )
        except httpx.ConnectError:
            raise RuntimeError(f"Ollama not available at {self.base_url}") from None
        except httpx.TimeoutException:
            raise RuntimeError(f"Ollama request timed out after {self.timeout}s") from None
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"Ollama HTTP error: {e.response.status_code}") from None
        return None

    async def health_check(self) -> ProviderHealth:
        """Check if Ollama is running and responsive."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                start = time.monotonic()
                response = await client.get(f"{self.base_url}/api/tags")
                latency_ms = (time.monotonic() - start) * 1000

                if response.status_code == 200:
                    models = [m["name"] for m in response.json().get("models", [])]
                    self._available_models = models
                    return ProviderHealth(
                        provider=self.name,
                        healthy=True,
                        latency_ms=latency_ms,
                        models_available=models,
                    )
                return ProviderHealth(
                    provider=self.name,
                    healthy=False,
                    latency_ms=latency_ms,
                    error=f"HTTP {response.status_code}",
                )
        except Exception as e:
            return ProviderHealth(
                provider=self.name,
                healthy=False,
                error=str(e),
            )
        return None

    def get_models(self) -> list[str]:
        """List locally available models."""
        return self._available_models or DEFAULT_MODELS
