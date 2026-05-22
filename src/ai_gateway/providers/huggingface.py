"""
HuggingFace Provider — Free Inference API
===========================================
Uses HuggingFace's free Inference API for model hosting.

Requires: HF_API_TOKEN (free tier available)
Zero-cost: Free tier provides generous rate limits.
"""

from __future__ import annotations

import logging
import time

import httpx

from src.ai_gateway.providers.base import AIProvider
from src.ai_gateway.types import AIRequest, AIResponse, ProviderHealth

logger = logging.getLogger("tranc3.ai_gateway.huggingface")

# Popular free models on HuggingFace
FREE_MODELS = [
    "meta-llama/Llama-3.2-3B-Instruct",
    "mistralai/Mistral-7B-Instruct-v0.3",
    "microsoft/Phi-3-mini-4k-instruct",
    "google/gemma-2-2b-it",
]


class HuggingFaceProvider(AIProvider):
    """
    HuggingFace Inference API provider.

    Uses HuggingFace's free inference API with generous
    rate limits on the free tier.
    """

    def __init__(
        self,
        api_key: str = "",
        default_model: str = "meta-llama/Llama-3.2-3B-Instruct",
        base_url: str = "https://api-inference.huggingface.co",
    ) -> None:
        super().__init__(name="huggingface", base_url=base_url, api_key=api_key)
        self.default_model = default_model

    async def complete(self, request: AIRequest) -> AIResponse:
        """Generate a completion using HuggingFace Inference API."""
        start = time.monotonic()
        model = request.model or self.default_model

        payload = {
            "inputs": request.prompt,
            "parameters": {
                "max_new_tokens": request.max_tokens,
                "temperature": request.temperature,
                "top_p": request.top_p,
                "return_full_text": False,
            },
        }

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/models/{model}",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()

            latency_ms = (time.monotonic() - start) * 1000

            # HuggingFace returns a list of generated texts
            if isinstance(data, list) and data:
                text = data[0].get("generated_text", "")
            else:
                text = str(data)

            return AIResponse(
                text=text,
                model=model,
                provider=self.name,
                tokens_prompt=0,  # HF doesn't always return token counts
                tokens_completion=0,
                tokens_total=0,
                latency_ms=latency_ms,
            )
        except httpx.HTTPStatusError as e:
            # Model loading — HF returns 503 when model is loading
            if e.response.status_code == 503:
                raise RuntimeError(f"HuggingFace model {model} is loading, try again later") from None
            raise RuntimeError(f"HuggingFace HTTP error: {e.response.status_code}") from None
        except Exception as e:
            raise RuntimeError(f"HuggingFace error: {e}") from None
        return None

    async def health_check(self) -> ProviderHealth:
        """Check HuggingFace API availability."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                start = time.monotonic()
                headers = {}
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"
                response = await client.get(
                    f"{self.base_url}/models/{self.default_model}",
                    headers=headers,
                )
                latency_ms = (time.monotonic() - start) * 1000

                if response.status_code == 200:
                    return ProviderHealth(
                        provider=self.name,
                        healthy=True,
                        latency_ms=latency_ms,
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
        """List free models on HuggingFace."""
        return FREE_MODELS
