"""
Embedding Providers — Free Vector Embedding Generation
========================================================
Provides text embedding capabilities using free-tier providers.

Providers (in priority order):
  1. Ollama local — nomic-embed-text (zero-cost, offline, ~768-dim)
  2. Gemini API  — text-embedding-004 (free, 1,500 req/day, 768-dim)

Both are zero-cost. Ollama is always preferred because it requires no
API key and has no rate limit, but it requires Ollama running locally
with the nomic-embed-text model pulled.

Usage:
    from src.ai_gateway.providers.embeddings import EmbeddingRouter

    router = EmbeddingRouter()
    vector = await router.embed("Hello, world!")
"""

from __future__ import annotations

import logging
import os
import time
from typing import List, Optional

import httpx

logger = logging.getLogger("tranc3.ai_gateway.embeddings")

# Default Ollama embedding model — pull with: ollama pull nomic-embed-text
OLLAMA_EMBED_MODEL = "nomic-embed-text"

# Default Gemini embedding model
GEMINI_EMBED_MODEL = "text-embedding-004"


class OllamaEmbeddingProvider:
    """
    Local embedding provider using Ollama's nomic-embed-text model.

    Zero-cost, offline-capable. Requires Ollama running locally with
    nomic-embed-text pulled: `ollama pull nomic-embed-text`.

    Output: 768-dimensional float vectors.
    """

    def __init__(
        self,
        base_url: str = "",
        model: str = OLLAMA_EMBED_MODEL,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url or os.getenv("OLLAMA_URL", "http://localhost:11434")
        self.model = model
        self.timeout = timeout
        self.name = "ollama-embed"

    async def embed(self, text: str) -> List[float]:
        """
        Generate an embedding using Ollama's /api/embeddings endpoint.

        Args:
            text: The text to embed.

        Returns:
            List of floats (embedding vector).

        Raises:
            RuntimeError: If Ollama is not available or the model is not pulled.
        """
        payload = {
            "model": self.model,
            "prompt": text,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

            embedding: List[float] = data.get("embedding", [])
            if not embedding:
                raise RuntimeError(
                    f"Ollama returned empty embedding for model {self.model}. "
                    f"Pull with: ollama pull {self.model}"
                )
            return embedding

        except httpx.ConnectError:
            raise RuntimeError(
                f"Ollama not available at {self.base_url}. Start with: ollama serve"
            ) from None
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 404:
                raise RuntimeError(
                    f"Ollama model '{self.model}' not found. Pull with: ollama pull {self.model}"
                ) from None
            raise RuntimeError(f"Ollama embedding HTTP error: {status}") from None
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Ollama embedding error: {e}") from None

    async def is_available(self) -> bool:
        """Check if Ollama embedding service is available."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                if response.status_code != 200:
                    return False
                models = [m["name"] for m in response.json().get("models", [])]
                # Accept both "nomic-embed-text" and "nomic-embed-text:latest"
                return any(self.model in m for m in models)
        except Exception:
            return False


class GeminiEmbeddingProvider:
    """
    Cloud embedding provider using Google Gemini's text-embedding-004.

    Free tier: 1,500 requests/day.
    Output: 768-dimensional float vectors (same dimensionality as nomic-embed-text).

    Requires GOOGLE_GEMINI_API_KEY environment variable.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = GEMINI_EMBED_MODEL,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai",
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key or os.getenv("GOOGLE_GEMINI_API_KEY", "")
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self.name = "gemini-embed"

    def _is_available(self) -> bool:
        return bool(self.api_key)

    async def embed(self, text: str) -> List[float]:
        """
        Generate an embedding using Gemini's text-embedding-004 model.

        Args:
            text: The text to embed.

        Returns:
            List of 768 floats (embedding vector).

        Raises:
            RuntimeError: If the API key is not configured or a request fails.
        """
        if not self._is_available():
            raise RuntimeError(
                "GOOGLE_GEMINI_API_KEY is not set. "
                "Get a free key at https://aistudio.google.com/apikey"
            )

        payload = {
            "model": self.model,
            "input": text,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/embeddings",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()

            embedding: List[float] = data["data"][0]["embedding"]
            return embedding

        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 429:
                raise RuntimeError("Gemini embedding rate limit exceeded (1,500 req/day)") from None
            raise RuntimeError(f"Gemini embedding HTTP error: {status}") from None
        except Exception as e:
            raise RuntimeError(f"Gemini embedding error: {e}") from None

    async def is_available(self) -> bool:
        """Check if Gemini embedding service is available."""
        return self._is_available()


class EmbeddingRouter:
    """
    Zero-cost embedding router with automatic failover.

    Priority chain:
      1. Ollama local (nomic-embed-text) — if running and model is pulled
      2. Gemini API (text-embedding-004) — if GOOGLE_GEMINI_API_KEY is set

    Both produce 768-dimensional vectors, so they are interchangeable
    and downstream vector stores don't need to know which was used.

    If neither is available, raises RuntimeError.
    """

    def __init__(
        self,
        ollama_url: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
    ) -> None:
        self._ollama = OllamaEmbeddingProvider(
            base_url=ollama_url or os.getenv("OLLAMA_URL", "http://localhost:11434"),
        )
        self._gemini = GeminiEmbeddingProvider(
            api_key=gemini_api_key or os.getenv("GOOGLE_GEMINI_API_KEY", ""),
        )

    async def embed(self, text: str) -> List[float]:
        """
        Embed text using the best available free provider.

        Tries Ollama first (zero-cost, offline), then falls back to Gemini.

        Args:
            text: The text to embed.

        Returns:
            List of floats (768-dimensional vector).

        Raises:
            RuntimeError: If no embedding provider is available.
        """
        errors = []

        # 1. Try Ollama local
        try:
            start = time.monotonic()
            vector = await self._ollama.embed(text)
            latency_ms = (time.monotonic() - start) * 1000
            logger.debug("Embedding via ollama in %.1fms, dim=%d", latency_ms, len(vector))
            return vector
        except Exception as e:
            errors.append(f"ollama-embed: {e}")
            logger.debug("Ollama embedding failed, trying Gemini: %s", e)

        # 2. Try Gemini cloud
        try:
            start = time.monotonic()
            vector = await self._gemini.embed(text)
            latency_ms = (time.monotonic() - start) * 1000
            logger.debug("Embedding via gemini in %.1fms, dim=%d", latency_ms, len(vector))
            return vector
        except Exception as e:
            errors.append(f"gemini-embed: {e}")
            logger.debug("Gemini embedding failed: %s", e)

        error_summary = "; ".join(errors)
        raise RuntimeError(
            f"All embedding providers failed. "
            f"For Ollama: run `ollama pull nomic-embed-text`. "
            f"For Gemini: set GOOGLE_GEMINI_API_KEY. "
            f"Errors: {error_summary}"
        )

    async def get_available_providers(self) -> dict[str, bool]:
        """Return availability status for all embedding providers."""
        return {
            "ollama-embed": await self._ollama.is_available(),
            "gemini-embed": await self._gemini.is_available(),
        }
