# client/client.py — HTTP client for calling the Tranc3 Bots service.
#
# The main Tranc3 application imports this to delegate tasks to the bots service.
#
# Usage:
#   client = BotClient(base_url="http://localhost:8080")
#   result = await client.generate("Tell me a story")
#   embed  = await client.embed("Hello world")
#
# Environment:
#   TRANC3_BOTS_URL — base URL of the bots service (default: http://localhost:8080)
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

_DEFAULT_URL = os.getenv("TRANC3_BOTS_URL", "http://localhost:8080")


class BotClientError(Exception):
    pass


class BotClient:
    """Async HTTP client for the Tranc3 Bots service."""

    def __init__(self, base_url: str = _DEFAULT_URL, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def _post(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=self.timeout) as http:
                r = await http.post(f"{self.base_url}{endpoint}", json=payload)
                r.raise_for_status()
                return r.json()
        except Exception as exc:
            raise BotClientError(f"Bot call {endpoint} failed: {exc}") from exc

    async def _get(self, endpoint: str) -> Dict[str, Any]:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=self.timeout) as http:
                r = await http.get(f"{self.base_url}{endpoint}")
                r.raise_for_status()
                return r.json()
        except Exception as exc:
            raise BotClientError(f"Bot GET {endpoint} failed: {exc}") from exc

    # ── Inference bots ─────────────────────────────────────────────────────────

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 256,
        temperature: float = 0.7,
        personality: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await self._post(
            "/generate",
            {
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "personality": personality,
            },
        )

    async def embed(self, text: str, dim: int = 128) -> List[float]:
        r = await self._post("/embed", {"text": text, "dim": dim})
        return r.get("embedding", [])

    async def emotion(self, text: str) -> Dict[str, Any]:
        return await self._post("/emotion", {"text": text})

    async def tokenize(self, text: str) -> Dict[str, Any]:
        return await self._post("/tokenize", {"text": text})

    async def consciousness(self, text: str) -> Dict[str, Any]:
        return await self._post("/consciousness", {"text": text})

    async def personality(self, text: str) -> Dict[str, Any]:
        return await self._post("/personality", {"text": text})

    async def predict(self, context: str, steps: int = 1) -> Dict[str, Any]:
        return await self._post("/predict", {"context": context, "steps": steps})

    # ── Utility bots ──────────────────────────────────────────────────────────

    async def code(self, task: str, language: str = "python") -> Dict[str, Any]:
        return await self._post("/code", {"task": task, "language": language})

    async def memory_store(self, key: str, value: Any) -> Dict[str, Any]:
        return await self._post("/memory", {"action": "store", "key": key, "value": value})

    async def memory_retrieve(self, key: str) -> Any:
        r = await self._post("/memory", {"action": "retrieve", "key": key})
        return r.get("value")

    async def memory_list(self) -> List[str]:
        r = await self._post("/memory", {"action": "list"})
        return r.get("keys", [])

    async def monitor(self) -> Dict[str, Any]:
        return await self._get("/monitor")

    async def search(self, query: str, limit: int = 5, source: str = "local") -> Dict[str, Any]:
        return await self._post("/search", {"query": query, "limit": limit, "source": source})

    async def summarise(self, text: str, ratio: float = 0.3) -> str:
        r = await self._post("/summarise", {"text": text, "ratio": ratio})
        return r.get("summary", "")

    async def run(self, bot_type: str, **kwargs) -> Dict[str, Any]:
        """Generic passthrough for any bot type."""
        return await self._post(f"/run/{bot_type}", {"payload": kwargs})

    # ── Health ─────────────────────────────────────────────────────────────────

    async def health(self) -> Dict[str, Any]:
        return await self._get("/health")

    async def is_available(self) -> bool:
        try:
            await self.health()
            return True
        except BotClientError:
            return False
